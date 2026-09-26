"""Lane B: sqlite3 storage helpers for firehose MVP. stdlib only."""

from __future__ import annotations

import hashlib
import pathlib
import sqlite3

SCHEMA_PATH = pathlib.Path(__file__).with_name("schema.sql")

TIER_INTERVALS = {0: 300, 1: 900, 2: 3600}


def init(db_path: str | pathlib.Path) -> sqlite3.Connection:
    """Open DB, apply PRAGMAs, create schema. Returns connection (Row factory)."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_PATH.read_text())
    return conn


def upsert_feed(conn: sqlite3.Connection, url: str, domain: str, tier: int) -> None:
    conn.execute(
        """INSERT INTO feeds(url, domain, tier) VALUES (?, ?, ?)
           ON CONFLICT(url) DO UPDATE SET domain=excluded.domain, tier=excluded.tier""",
        (url, domain, tier),
    )
    conn.commit()


def get_due_feeds(
    conn: sqlite3.Connection, now: int
) -> list[sqlite3.Row]:
    """Feeds due for polling. Tier intervals: T0 300s / T1 900s / T2 3600s.

    Due iff never checked, or interval elapsed, AND not inside backoff window.
    """
    due: list[sqlite3.Row] = []
    for tier, interval in TIER_INTERVALS.items():
        rows = conn.execute(
            """SELECT * FROM feeds
               WHERE tier = ?
                 AND (last_checked IS NULL OR (? - last_checked) >= ?)
                 AND (backoff_until IS NULL OR backoff_until <= ?)""",
            (tier, now, interval, now),
        ).fetchall()
        due.extend(rows)
    return due


def record_fetch(
    conn: sqlite3.Connection,
    url: str,
    *,
    etag: str | None = None,
    last_modified: str | None = None,
    body_hash: str | None = None,
    checked_at: int = 0,
    error: bool = False,
    backoff_until: int | None = None,
) -> None:
    """Update feed after a fetch attempt.

    Success: store validators + body hash, stamp last_checked, reset err_count,
    clear backoff. Error: bump err_count, stamp last_checked, set backoff window.
    """
    if error:
        conn.execute(
            """UPDATE feeds SET last_checked=?, err_count=err_count+1,
               backoff_until=? WHERE url=?""",
            (checked_at, backoff_until, url),
        )
    else:
        conn.execute(
            """UPDATE feeds SET etag=?, last_modified=?, last_body_hash=?,
               last_checked=?, err_count=0, backoff_until=NULL WHERE url=?""",
            (etag, last_modified, body_hash, checked_at, url),
        )
    conn.commit()


def guid_hash(guid: str, link: str) -> str:
    return hashlib.sha256(f"{guid}||{link}".encode()).hexdigest()


def insert_item(
    conn: sqlite3.Connection,
    *,
    guid: str,
    link: str,
    title: str | None = None,
    body: str | None = None,
    published: int | None = None,
    fetched_at: int = 0,
    simhash: int | None = None,
    minhash: str | None = None,
    dup_of: str | None = None,
) -> str:
    """Insert one item. guid_hash = sha256(guid||link). Returns guid_hash."""
    gh = guid_hash(guid, link)
    conn.execute(
        """INSERT OR IGNORE INTO items
           (guid_hash, url, title, body, published, fetched_at, simhash, minhash, dup_of)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (gh, link, title, body, published, fetched_at, simhash, minhash, dup_of),
    )
    conn.commit()
    return gh
