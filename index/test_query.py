"""test_query.py — stub pipeline checks (stdlib + pytest)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from query import assert_no_egress, chunk, rrf_fuse, search

DOCS = [
    {"id": "d1", "text": "sparse retrieval with bm25 ranking function"},
    {"id": "d2", "text": "dense embeddings for semantic search retrieval"},
    {"id": "d3", "text": "reciprocal rank fusion merges ranked lists"},
    {"id": "d4", "text": "unrelated cooking recipes for dinner"},
]


def test_rrf_deterministic_order():
    a = [("x", 9.0), ("y", 1.0)]
    b = [("y", 9.0), ("x", 1.0)]
    r1 = rrf_fuse([a, b])
    r2 = rrf_fuse([a, b])
    assert r1 == r2
    # symmetric ranks -> tie -> id ascending
    assert [d for d, _ in r1] == ["x", "y"]


def test_rrf_winner_first():
    a = [("x", 5.0), ("y", 4.0)]
    b = [("x", 5.0), ("z", 4.0)]
    fused = rrf_fuse([a, b])
    assert fused[0][0] == "x"


def test_chunk_overlap_correct():
    words = [f"w{i}" for i in range(1000)]
    ch = chunk(" ".join(words), size=512, overlap=0.15)
    assert len(ch) == 3  # starts at 0, 435, 870 (step = round(512*0.85))
    first, second = ch[0].split(), ch[1].split()
    assert len(first) == 512
    assert second[:77] == first[-77:]  # 512 - 435 shared words


def test_chunk_empty():
    assert chunk("") == []


def test_stub_search_returns_top_k():
    res = search("bm25 retrieval ranking", DOCS, k=2)
    assert len(res) == 2
    assert res[0][0] == "d1"


def test_no_socket_egress():
    with assert_no_egress():
        res = search("semantic search", DOCS, k=3)
    assert len(res) == 3
