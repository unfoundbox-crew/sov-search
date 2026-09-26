"""Dedup primitives for the firehose (Lane C). Pure functions, no DB.

Pipeline order (enforced by caller, Lane B store):
  1. exact_seen() on guid_hash -> dup_of = original
  2. near_dup() on simhash within 7-day window (hamming <= 3)
  3. lsh_dup() on minhash signature (est. Jaccard >= 0.8) for syndication

SWAP POINTS:
- simhash64(): placeholder char-3gram variant. Swap with `simhash-py`
  (Simhash(text).value) — same int64 contract, same hamming().
- minhash_sig(): placeholder deterministic sha256-mins. Swap with
  `datasketch.MinHash(num_perm=n)` — same list-of-ints contract.
"""

from __future__ import annotations

import hashlib
import re

_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str | None) -> list[str]:
    if not text:
        return []
    return _WORD_RE.findall(text.lower())


def exact_seen(guid_hash: str, seen: set) -> bool:
    """True if guid_hash already in seen set (exact duplicate)."""
    return guid_hash in seen


def simhash64(text: str | None) -> int:
    """64-bit simhash placeholder over char 3-grams.

    Real simhash-py hashes token features with random projections; this
    does the same shape with md5-per-gram bit voting so hamming distance
    behaves the same way for tests. Swap: Simhash(text).value.
    """
    text = (text or "").lower()
    if not text:
        return 0
    grams = [text[i:i + 3] for i in range(max(1, len(text) - 2))]
    acc = [0] * 64
    for g in grams:
        h = int(hashlib.md5(g.encode("utf-8")).hexdigest(), 16) & ((1 << 64) - 1)
        for b in range(64):
            acc[b] += 1 if (h >> b) & 1 else -1
    fp = 0
    for b in range(64):
        if acc[b] > 0:
            fp |= (1 << b)
    return fp


def hamming(a: int, b: int) -> int:
    """Hamming distance between two int fingerprints."""
    return bin(a ^ b).count("1")


def near_dup(simhash: int, window_list: list, thresh: int = 3) -> bool:
    """True if any fingerprint in window_list is within thresh bits.

    window_list: list of ints, or list of (simhash, ...) tuples/dicts —
    first int-like element is used, so callers can pass (ts, simhash) rows.
    """
    for item in window_list:
        cand = item
        if isinstance(item, dict):
            cand = item.get("simhash", 0)
        elif isinstance(item, (tuple, list)) and len(item) >= 2 and isinstance(item[1], int):
            cand = item[1]
        elif isinstance(item, (tuple, list)) and len(item) >= 1:
            cand = item[0]
        if hamming(simhash, int(cand)) <= thresh:
            return True
    return False


def minhash_sig(text: str | None, n: int = 128) -> list[int]:
    """Placeholder MinHash signature: per-seed min over word tokens.

    sig[i] = min over tokens of sha256(f"{i}||{token}"). Deterministic,
    no random state. Swap: datasketch.MinHash(num_perm=n) digest().
    Empty text -> [0]*n.
    """
    toks = _tokens(text)
    if not toks:
        return [0] * n
    sig: list[int] = []
    for i in range(n):
        best = None
        for t in toks:
            h = int(hashlib.sha256(f"{i}||{t}".encode("utf-8")).hexdigest(), 16)
            if best is None or h < best:
                best = h
        sig.append(best if best is not None else 0)
    return sig


def _est_jaccard(a: list[int], b: list[int]) -> float:
    if not a or len(a) != len(b):
        return 0.0
    return sum(1 for x, y in zip(a, b) if x == y) / len(a)


def lsh_dup(sig: list[int], index: list[list[int]], threshold: float = 0.8) -> bool:
    """True if any signature in index has est. Jaccard >= threshold.

    index: list of existing signatures (the LSH bucket/window in prod;
    callers pre-filter by band here — linear scan is the placeholder).
    Swap: datasketch.MinHashLSH query.
    """
    for other in index:
        if _est_jaccard(sig, other) >= threshold:
            return True
    return False
