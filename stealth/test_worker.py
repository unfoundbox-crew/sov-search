"""Stdlib-asyncio pytest suite for TierRouter. No network, no browsers."""

import asyncio

from worker import (
    CAMOUFOX_PIN,
    MAX_CTX,
    PATCHRIGHT_PIN,
    SCRAPLING_PIN,
    TierRouter,
)


def test_200_never_escalates():
    r = TierRouter(responder=lambda url: (200, "# hello"))
    out = asyncio.run(r.fetch("https://example.com/a"))
    assert out == {"markdown": "# hello", "status": 200, "tier_used": 1}
    assert r.escalations == 0


def test_403_escalates_once_and_reuses_profile():
    r = TierRouter(responder=lambda url: (403, "forbidden"))
    first = asyncio.run(r.fetch("https://blocked.example/p1"))
    second = asyncio.run(r.fetch("https://blocked.example/p2"))
    assert first["tier_used"] == 3 and second["tier_used"] == 3
    assert r.escalations == 2
    assert first["markdown"] != "forbidden"  # canned Tier-3 markdown returned
    # Same host -> same persistent profile reused.
    assert "Profile: profile-1" in first["markdown"]
    assert "Profile: profile-1" in second["markdown"]
    assert r.last_escalation["profile_reused"] == "profile-1"


def test_empty_body_escalates():
    r = TierRouter(responder=lambda url: (200, "   "))
    out = asyncio.run(r.fetch("https://empty.example/"))
    assert out["tier_used"] == 3
    assert r.escalations == 1


def test_challenge_body_escalates():
    r = TierRouter(responder=lambda url: (429, "cloudflare challenge captcha"))
    out = asyncio.run(r.fetch("https://hard.example/"))
    assert out["tier_used"] == 3


def test_9_concurrent_jobs_max_8_active():
    async def slow(url):
        await asyncio.sleep(0.05)
        return 200, "# slow"

    async def main():
        r = TierRouter(rps=1000)  # no throttle interference
        # Wrap slow responder synchronously: responder itself is sync,
        # so simulate latency via fetch-level sleep instead.
        async def job(i):
            async with r.sem:
                r.active += 1
                r.max_active = max(r.max_active, r.active)
                try:
                    await asyncio.sleep(0.05)
                    return i
                finally:
                    r.active -= 1

        await asyncio.gather(*[job(i) for i in range(9)])
        return r

    r = asyncio.run(main())
    assert r.max_active == 8, f"max_active={r.max_active}"
    assert MAX_CTX == 8


def test_pool_guard_via_fetch():
    async def main():
        import time

        def responder(url):
            return 200, "# x"

        r = TierRouter(responder=responder, rps=1000)
        orig = r.try_tier1

        def slow_tier1(url):
            import time as _t

            _t.sleep(0.02)
            return orig(url)

        # Make fetch slow by patching _throttle to sleep while holding sem.
        orig_throttle = r._throttle

        async def slow_throttle(url):
            await asyncio.sleep(0.02)
            await orig_throttle(url)

        r._throttle = slow_throttle
        await asyncio.gather(*[r.fetch(f"https://pool.example/{i}") for i in range(9)])
        return r

    r = asyncio.run(main())
    assert r.max_active <= 8
    assert r.max_active == 8


def test_pins_non_empty():
    assert SCRAPLING_PIN and CAMOUFOX_PIN and PATCHRIGHT_PIN
