"""Schema tests: PRAGMAs, DDL shape, FTS sync triggers."""

import sqlite3

import store


def test_wal_on(tmp_path):
    conn = store.init(tmp_path / "t.db")
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.upper() == "WAL"
    assert conn.execute("PRAGMA synchronous").fetchone()[0] in (1, "NORMAL", "normal")
    assert conn.execute("PRAGMA temp_store").fetchone()[0] in (2, "MEMORY", "memory")
    conn.close()


def test_tables_and_indexes(tmp_path):
    conn = store.init(tmp_path / "t.db")
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table','virtual table')")}
    assert {"feeds", "items", "items_fts"} <= tables
    idx = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert "idx_feeds_tier_checked" in idx
    assert "idx_items_fetched" in idx
    trig = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
    assert {"items_ai", "items_ad", "items_au"} <= trig
    conn.close()


def test_fts_triggers_fire(tmp_path):
    conn = store.init(tmp_path / "t.db")
    gh = store.insert_item(conn, guid="g1", link="https://x.example/1",
                           title="running rivers", body="banksy mural festival",
                           fetched_at=1)
    hits = conn.execute(
        "SELECT rowid FROM items_fts WHERE items_fts MATCH 'run'").fetchall()
    assert len(hits) == 1  # porter stemming: run matches running
    assert hits[0][0] == conn.execute(
        "SELECT id FROM items WHERE guid_hash=?", (gh,)).fetchone()[0]
    # update syncs
    conn.execute("UPDATE items SET title='quiet ledger' WHERE guid_hash=?", (gh,))
    conn.commit()
    assert conn.execute(
        "SELECT rowid FROM items_fts WHERE items_fts MATCH 'run'").fetchall() == []
    assert len(conn.execute(
        "SELECT rowid FROM items_fts WHERE items_fts MATCH 'ledger'").fetchall()) == 1
    # delete syncs
    conn.execute("DELETE FROM items WHERE guid_hash=?", (gh,))
    conn.commit()
    assert conn.execute(
        "SELECT rowid FROM items_fts WHERE items_fts MATCH 'ledger'").fetchall() == []
    conn.close()


def test_guid_hash_unique(tmp_path):
    conn = store.init(tmp_path / "t.db")
    a = store.insert_item(conn, guid="g", link="https://x.example/1", fetched_at=1)
    b = store.insert_item(conn, guid="g", link="https://x.example/1", fetched_at=2)
    assert a == b
    assert conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 1
    conn.close()
