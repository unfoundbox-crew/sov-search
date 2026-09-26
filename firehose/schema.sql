-- firehose MVP schema (Lane B: scheduler + store)
-- RETENTION: rows older than 90d ship-to-parquet first, then DELETE.
--   Do NOT delete from items/items_fts without first exporting the
--   evicted window to parquet (cold store). Enforced by janitor, not by DDL.

PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA cache_size=-64000;
PRAGMA temp_store=MEMORY;

CREATE TABLE IF NOT EXISTS feeds (
  url           TEXT PRIMARY KEY,
  domain        TEXT NOT NULL,
  tier          INTEGER NOT NULL CHECK (tier IN (0, 1, 2)),
  etag          TEXT,
  last_modified TEXT,
  last_body_hash TEXT,
  last_checked  INTEGER,
  backoff_until INTEGER,
  err_count     INTEGER NOT NULL DEFAULT 0
);

-- guid_hash is the logical PK (sha256 of guid||link, see store.insert_item).
-- id exists solely as the integer rowid that items_fts content_rowid needs.
CREATE TABLE IF NOT EXISTS items (
  id         INTEGER PRIMARY KEY,
  guid_hash  TEXT NOT NULL UNIQUE,
  url        TEXT NOT NULL,
  title      TEXT,
  body       TEXT,
  published  INTEGER,
  fetched_at INTEGER NOT NULL,
  simhash    INTEGER,
  minhash    TEXT,
  dup_of     TEXT REFERENCES items(guid_hash)
);

CREATE VIRTUAL TABLE IF NOT EXISTS items_fts USING fts5(
  title, body,
  content='items', content_rowid='id',
  tokenize='porter'
);

CREATE TRIGGER IF NOT EXISTS items_ai AFTER INSERT ON items BEGIN
  INSERT INTO items_fts(rowid, title, body)
  VALUES (new.id, new.title, new.body);
END;

CREATE TRIGGER IF NOT EXISTS items_ad AFTER DELETE ON items BEGIN
  INSERT INTO items_fts(items_fts, rowid, title, body)
  VALUES ('delete', old.id, old.title, old.body);
END;

CREATE TRIGGER IF NOT EXISTS items_au AFTER UPDATE ON items BEGIN
  INSERT INTO items_fts(items_fts, rowid, title, body)
  VALUES ('delete', old.id, old.title, old.body);
  INSERT INTO items_fts(rowid, title, body)
  VALUES (new.id, new.title, new.body);
END;

CREATE INDEX IF NOT EXISTS idx_feeds_tier_checked ON feeds(tier, last_checked);
CREATE INDEX IF NOT EXISTS idx_items_fetched ON items(fetched_at);
