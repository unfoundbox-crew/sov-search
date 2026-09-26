"""Tests for dedup.py (Lane C). Pure functions, timestamps simulated."""

import time

from dedup import exact_seen, hamming, lsh_dup, minhash_sig, near_dup, simhash64
from parse import entry_id

BASE = ("markets rallied on tuesday as investors welcomed the central bank decision "
        "to cut interest rates with technology shares leading broad gains across the board "
        "while analysts noted that trading volume was well above its monthly average "
        "and volatility indexes fell to their lowest level since spring")
NEAR = BASE.replace("tuesday", "wednesday")  # 1-word change
DIFF = ("quantum error correction thresholds for surface codes improve yearly "
        "with new decoder designs and longer coherence times")


def test_exact_dup_caught():
    seen = set()
    h = entry_id("g-1", "https://ex.com/a")
    assert not exact_seen(h, seen)
    seen.add(h)
    assert exact_seen(h, seen)


def test_near_dup_one_word_change():
    a, b = simhash64(BASE), simhash64(NEAR)
    assert isinstance(a, int) and isinstance(b, int)
    assert hamming(a, b) <= 3
    assert near_dup(b, [a], thresh=3)


def test_distinct_kept():
    a, d = simhash64(BASE), simhash64(DIFF)
    assert hamming(a, d) > 3
    assert not near_dup(d, [a], thresh=3)
    assert not lsh_dup(minhash_sig(DIFF), [minhash_sig(BASE)])


def test_syndication_pair_linked_by_minhash():
    # Same story, reworded tail + same body keywords: high word overlap.
    s1 = minhash_sig(BASE + " stocks close higher on rate cut hopes", n=128)
    s2 = minhash_sig(BASE + " stocks close higher on rate cut optimism", n=128)
    assert len(s1) == 128 and len(s2) == 128
    assert lsh_dup(s2, [s1], threshold=0.8)


def test_window_7d_logic_simulated():
    now = time.time()
    day = 86400
    old_fp = simhash64(BASE)  # 10 days ago: outside window
    fresh = simhash64(NEAR)
    window = [(now - 10 * day, old_fp), (now - 1 * day, fresh)]
    current = simhash64(BASE)  # same story re-fetched
    recent_only = [fp for ts, fp in window if now - ts <= 7 * day]
    assert old_fp not in recent_only  # stale entry evicted
    assert near_dup(current, recent_only, thresh=3)  # fresh entry still matches
    assert not near_dup(current, [old_fp if False else simhash64(DIFF)], thresh=3)
