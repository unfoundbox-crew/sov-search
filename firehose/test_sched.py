"""Scheduler tests: due-query tiers, 304 skip, backoff cap, dry-run sweep."""

import asyncio
import json
import pathlib

import sched
import store

NOW = 1_780_000_000


def seed(conn, url, tier, last_checked=None, backoff_until=None, etag=None, h=None):
    store.upsert_feed(conn, url, url.split("/")[2], tier)
    conn.execute(
        "UPDATE feeds SET last_checked=?, backoff_until=?, etag=?, last_body_hash=? WHERE url=?",
        (last_checked, backoff_until, etag, h, url),
    )
    conn.commit()


def test_due_query_respects_tiers(tmp_path):
    conn = store.init(tmp_path / "t.db")
    seed(conn, "https://a.example/0", 0, NOW - 301)   # T0 interval 300 -> due
    seed(conn, "https://b.example/0", 0, NOW - 299)   # not due
    seed(conn, "https://c.example/1", 1, NOW - 901)   # T1 interval 900 -> due
    seed(conn, "https://d.example/1", 1, NOW - 100)   # not due
    seed(conn, "https://e.example/2", 2, NOW - 3601)  # T2 interval 3600 -> due
    seed(conn, "https://f.example/2", 2, None)        # never checked -> due
    seed(conn, "https://g.example/0", 0, NOW - 9999, backoff_until=NOW + 600)
    due = {r["url"] for r in store.get_due_feeds(conn, NOW)}
    assert due == {"https://a.example/0", "https://c.example/1",
                   "https://e.example/2", "https://f.example/2"}
    conn.close()


def test_304_skips_parse():
    feed = {"etag": '"x"', "last_body_hash": "h", "err_count": 0}
    assert sched.handle_fetch_result(feed, 304, b"whatever", NOW)["action"] == "skip_304"


def test_body_hash_skip():
    body = b"same body"
    h = sched.body_hash(body)
    feed = {"etag": None, "last_body_hash": h, "err_count": 0}
    assert sched.handle_fetch_result(feed, 200, body, NOW)["action"] == "skip_hash"
    feed2 = {"etag": None, "last_body_hash": "other", "err_count": 0}
    assert sched.handle_fetch_result(feed2, 200, body, NOW)["action"] == "parse"


def test_backoff_caps_at_4h():
    assert sched.backoff_secs(0) == 60
    assert sched.backoff_secs(100) == 4 * 3600
    assert max(sched.backoff_secs(n) for n in range(20)) <= 4 * 3600
    r = sched.handle_fetch_result({"err_count": 50}, 503, None, NOW)
    assert r["action"] == "backoff"
    assert r["backoff_until"] - NOW == 4 * 3600
    r429 = sched.handle_fetch_result({"err_count": 0}, 429, None, NOW)
    assert r429["action"] == "backoff"


def test_conditional_headers_builder():
    h = sched.build_conditional_headers({"etag": '"a"', "last_modified": "Thu, 10 Sep 2026 12:00:00 GMT"})
    assert h == {"If-None-Match": '"a"', "If-Modified-Since": "Thu, 10 Sep 2026 12:00:00 GMT"}
    assert sched.build_conditional_headers({}) == {}


def test_host_limiter_permits():
    lim = sched.HostLimiter()
    assert lim.for_host("a.example")._value == 2
    assert lim.for_host("a.example") is lim.for_host("a.example")


def test_dry_run_sweep_of_fixture(tmp_path):
    db = tmp_path / "dry.db"
    stats = asyncio.run(sched.dry_run_sweep(db, NOW))
    fixture = json.loads((pathlib.Path(sched.__file__).parent / "fixtures" / "feeds.fixture.json").read_text())
    assert stats["total"] == 10 == len(fixture)
    assert stats["due"] == 10  # fresh DB, all never checked
    assert stats["skipped_304"] + stats["fetched"] == 10
    # second sweep immediately after: nothing due (all just checked)
    conn = store.init(db)
    assert store.get_due_feeds(conn, NOW) == []
    conn.close()
