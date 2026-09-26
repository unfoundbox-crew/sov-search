"""query.py — hybrid-query stub pipeline with injectable backends.

Stages: chunk (real, stdlib) -> bm25_top (injected) -> dense_top
(injected) -> rrf_fuse (real) -> rerank_top (stub passthrough).

Later real-model swap (NOT here, no network/models on this box):
  dense   = BGE-M3 int8 on MPS, per-chunk embeddings
  rerank  = bge-reranker-v2-m3 cross-encoder top-k reorder
The injected-backend seams (bm25_fn / dense_fn / rerank_fn) are where
those swap in. search() wires the stub chain.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Sequence
from contextlib import contextmanager


# ---------------- chunk (real) ----------------

def chunk(text: str, size: int = 512, overlap: float = 0.15) -> list[str]:
    """Word-based chunks of `size` words with fractional `overlap`.

    overlap=0.15 on size=512 -> step 436 (round), so consecutive
    chunks share the last ~76 words.
    """
    words = text.split()
    if not words:
        return []
    step = max(1, int(round(size * (1 - overlap))))
    return [" ".join(words[i:i + size]) for i in range(0, len(words), step)]


# ---------------- stub backends ----------------

Doc = dict  # {"id": str, "text": str}

_TOKEN_RE = None


def _tokens(s: str) -> list[str]:
    import re

    global _TOKEN_RE
    return re.findall(r"[a-z0-9]+", s.lower())


def bm25_stub(query: str, docs: Sequence[Doc], k: int = 20) -> list[tuple[str, float]]:
    """In-memory TF stub standing in for a real BM25 index."""
    qt = set(_tokens(query))
    scored = []
    for d in docs:
        tf = Counter(_tokens(d["text"]))
        score = float(sum(tf[t] for t in qt))
        scored.append((d["id"], score))
    scored.sort(key=lambda kv: (-kv[1], kv[0]))
    return scored[:k]


def dense_stub(query: str, docs: Sequence[Doc], k: int = 20) -> list[tuple[str, float]]:
    """Token-overlap stub standing in for BGE-M3 dense retrieval."""
    qt = set(_tokens(query))
    scored = []
    for d in docs:
        dt = set(_tokens(d["text"]))
        inter = len(qt & dt)
        union = len(qt | dt) or 1
        scored.append((d["id"], inter / union))
    scored.sort(key=lambda kv: (-kv[1], kv[0]))
    return scored[:k]


# ---------------- rrf_fuse (real) ----------------

def rrf_fuse(lists: Sequence[Sequence[tuple[str, float]]], k: int = 60) -> list[tuple[str, float]]:
    """Reciprocal-rank fuse: score(d) = sum 1/(k + rank). Deterministic.

    Ties broken by doc id ascending so output order is stable.
    Returns full fused ranking (caller slices top-k).
    """
    acc: dict[str, float] = {}
    for lst in lists:
        for rank, (doc_id, _) in enumerate(lst, start=1):
            acc[doc_id] = acc.get(doc_id, 0.0) + 1.0 / (k + rank)
    return sorted(acc.items(), key=lambda kv: (-kv[1], kv[0]))


# ---------------- rerank stub ----------------

def rerank_stub(cands: Sequence[tuple[str, float]], k: int = 20) -> list[tuple[str, float]]:
    """Score passthrough — keeps fused order, slices top-k."""
    return list(cands[:k])


# ---------------- pipeline ----------------

def search(
    q: str,
    docs: Sequence[Doc],
    k: int = 20,
    bm25_fn: Callable = bm25_stub,
    dense_fn: Callable = dense_stub,
    rerank_fn: Callable = rerank_stub,
) -> list[tuple[str, float]]:
    b = bm25_fn(q, docs, k=k * 2)
    d = dense_fn(q, docs, k=k * 2)
    fused = rrf_fuse([b, d])
    return rerank_fn(fused, k=k)


# ---------------- no-egress helper ----------------

@contextmanager
def assert_no_egress():
    """Fail if any code path opens a socket (stub pipeline must stay offline).

    Usage in tests: `with assert_no_egress(): search(...)`.
    """
    import socket as _socket

    real = _socket.socket

    def _blocked(*a, **kw):
        raise AssertionError("network egress attempted in stub pipeline")

    _socket.socket = _blocked  # type: ignore[assignment]
    try:
        yield
    finally:
        _socket.socket = real
