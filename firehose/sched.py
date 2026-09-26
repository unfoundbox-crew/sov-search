"""Lane B: asyncio scheduler skeleton for firehose MVP.

Real network path is a skeleton (urllib-based, not exercised in tests).
Dry-run mode simulates the whole sweep from the fixture with no network.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import pathlib
import time
import urllib.parse

try:  # fast path; hashlib fallback keeps tests green without the dep
    import xxhash  # type: ignore

    def body_hash(data: bytes) -> str:
        return xxhash.xxh64(data).hexdigest()
except ImportError:

    def body_hash(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

try:
    from .store import TIER_INTERVALS, get_due_feeds, init, record_fetch
except ImportError:  # imported as top-level module (pytest in lane dir)
    from store import TIER_INTERVALS, get_due_feeds, init, record_fetch

MAX_BACKOFF_SECS = 4 * 3600  # 4h cap
BACKOFF_BASE_SECS = 60


def backoff_secs(err_count: int) -> int:
    """Exponential backoff: 60 * 2**err_count, capped at 4h."""
    return min(BACKOFF_BASE_SECS * (2**err_count), MAX_BACKOFF_SECS)


def build_conditional_headers(feed: dict) -> dict:
    """Conditional-GET headers from stored validators."""
    headers: dict = {}
    if feed.get("etag"):
        headers["If-None-Match"] = feed["etag"]
    if feed.get("last_modified"):
        headers["If-Modified-Since"] = feed["last_modified"]
    return headers


def host_of(url: str) -> str:
    return urllib.parse.urlparse(url).netloc


class HostLimiter:
    """Per-host Semaphore(2) registry."""

    def __init__(self, permits: int = 2):
        self.permits = permits
        self._sems: dict[str, asyncio.Semaphore] = {}

    def for_host(self, host: str) -> asyncio.Semaphore:
        if host not in self._sems:
            self._sems[host] = asyncio.Semaphore(self.permits)
        return self._sems[host]


def handle_fetch_result(
    feed: dict, status: int, body: bytes | None, now: int
) -> dict:
    """Classify a fetch outcome. Pure function — unit-tested.

    Returns action dict: {"action": "parse"|"skip_304"|"skip_hash"|"backoff",
    "backoff_until"?, "body_hash"?}.
    """
    if status == 304:
        return {"action": "skip_304"}
    if status == 429 or 500 <= status <= 599:
        err_count = (feed.get("err_count") or 0) + 1
        wait = backoff_secs(err_count)
        return {"action": "backoff", "backoff_until": now + wait}
    if body is not None:
        h = body_hash(body)
        if feed.get("last_body_hash") and h == feed["last_body_hash"]:
            return {"action": "skip_hash", "body_hash": h}
        return {"action": "parse", "body_hash": h}
    return {"action": "parse", "body_hash": None}


async def fetch_one(feed: dict, limiter: HostLimiter, now: int) -> dict:
    """Skeleton for one conditional fetch. 304 short-circuits before parse."""
    sem = limiter.for_host(host_of(feed["url"]))
    async with sem:
        headers = build_conditional_headers(feed)
        # Real HTTP lives here (conditional GET with headers); skeleton only.
        await asyncio.sleep(0)
        return {"feed": feed, "headers": headers, "result": {"action": "parse"}}


def load_fixture(path: str | pathlib.Path | None = None) -> list[dict]:
    p = pathlib.Path(path) if path else pathlib.Path(__file__).parent / "fixtures" / "feeds.fixture.json"
    return json.loads(p.read_text())


async def dry_run_sweep(db_path: str | pathlib.Path, now: int | None = None) -> dict:
    """No-network sweep: seed fixture feeds, mark due ones checked.

    Simulates conditional-GET against stored validators: feeds that already
    have an etag simulate a 304 (skip parse); otherwise simulate 200 with a
    fake body whose hash is recorded. Returns stats.
    """
    from store import upsert_feed

    now = now if now is not None else int(time.time())
    conn = init(db_path)
    feeds = load_fixture()
    for f in feeds:
        upsert_feed(conn, f["url"], f["domain"], f["tier"])
        # Seed validators present in the fixture so 304 path is exercised.
        if f.get("etag") or f.get("last_modified"):
            conn.execute(
                "UPDATE feeds SET etag=?, last_modified=? WHERE url=?",
                (f.get("etag"), f.get("last_modified"), f["url"]),
            )
    conn.commit()

    due = get_due_feeds(conn, now)
    stats = {"total": len(feeds), "due": len(due), "skipped_304": 0, "fetched": 0}
    limiter = HostLimiter()
    for row in due:
        feed = dict(row)
        async with limiter.for_host(host_of(feed["url"])):
            result = handle_fetch_result(
                feed, 304 if feed.get("etag") else 200,
                None if feed.get("etag") else f"body:{feed['url']}".encode(),
                now,
            )
            if result["action"] == "skip_304":
                record_fetch(conn, feed["url"], etag=feed["etag"],
                             last_modified=feed["last_modified"],
                             body_hash=feed["last_body_hash"], checked_at=now)
                stats["skipped_304"] += 1
            else:
                record_fetch(conn, feed["url"], etag=feed["etag"],
                             last_modified=feed["last_modified"],
                             body_hash=result.get("body_hash"), checked_at=now)
                stats["fetched"] += 1
    conn.close()
    return stats


async def poll_loop(db_path: str | pathlib.Path, stop_after: int | None = None) -> None:
    """Tier poll loop skeleton. stop_after=N exits after N iterations (tests)."""
    limiter = HostLimiter()
    conn = init(db_path)
    i = 0
    while True:
        now = int(time.time())
        for feed in get_due_feeds(conn, now):
            await fetch_one(dict(feed), limiter, now)
        i += 1
        if stop_after is not None and i >= stop_after:
            break
        await asyncio.sleep(min(TIER_INTERVALS.values()))
    conn.close()
