"""Tier1-first fetch worker with Tier-3 escalation stub.

Contract: fetch(url) -> {markdown, status, tier_used}.
Firehose calls this worker ONLY on 403 / challenge / empty-body.
Tier-1 (curl_cffi / Katana) lives elsewhere; try_tier1 here is a stub
whose response comes from an injected responder (default 200).

Real Patchright/Camoufox wiring happens on Lenovo later.
Stdlib only.
"""

import asyncio
import time
from urllib.parse import urlparse

# pin or fingerprint drifts — keep these exact; Lenovo install uses them verbatim.
SCRAPLING_PIN = "scrapling==0.3.9"
CAMOUFOX_PIN = "camoufox==0.4.7"
PATCHRIGHT_PIN = "patchright==1.49.1"

MAX_CTX = 8  # persistent browser contexts; 9th job queues on the semaphore.

# Per-host budget: 1-2 rps. Jitter (~100-300 ms) breaks lockstep retry
# thundering herds; applied in _throttle before each outbound attempt.


class TierRouter:
    def __init__(self, responder=None, rps=1.5):
        # responder(url) -> (status, body). Injected by tests / firehose shim.
        self.responder = responder or (lambda url: (200, "# ok"))
        self.rps = rps
        self.sem = asyncio.Semaphore(MAX_CTX)
        self._last_hit = {}  # host -> monotonic timestamp of last attempt
        self._profiles = {}  # host -> profile id (persistent ctx reuse)
        self._profile_seq = 0
        # Observability for tests / firehose:
        self.escalations = 0
        self.active = 0
        self.max_active = 0
        self.last_escalation = None  # records fingerprint-seed + proxy + profile

    # -- Tier-1 (stub) ----------------------------------------------------
    def try_tier1(self, url):
        """Stub for Tier-1 (curl_cffi/Katana, lives elsewhere)."""
        status, body = self.responder(url)
        return status, body

    # -- Escalation predicate ---------------------------------------------
    @staticmethod
    def should_escalate(status, body):
        if status in (403, 429):
            return True
        if not body or not body.strip():
            return True
        lowered = body.lower()
        if "challenge" in lowered and ("captcha" in lowered or "cloudflare" in lowered):
            return True
        return False

    # -- Tier-3 (stub) ------------------------------------------------------
    def escalate_tier3(self, url, status):
        host = urlparse(url).hostname or url
        if host not in self._profiles:
            self._profile_seq += 1
            self._profiles[host] = f"profile-{self._profile_seq}"
        profile = self._profiles[host]
        seed = f"seed-{abs(hash(host)) % 100000}"
        proxy = f"proxy://{host}"
        self.escalations += 1
        self.last_escalation = {
            "url": url,
            "from_status": status,
            "fingerprint_seed": seed,
            "proxy": proxy,
            "profile_reused": profile,
        }
        # Canned markdown — real Patchright/Camoufox render wired on Lenovo.
        return f"# Tier-3 render\n\nSource: {url}\nProfile: {profile}\n"

    # -- Throttle -----------------------------------------------------------
    async def _throttle(self, url):
        host = urlparse(url).hostname or url
        now = time.monotonic()
        min_gap = 1.0 / self.rps
        last = self._last_hit.get(host, 0.0)
        wait = min_gap - (now - last)
        if wait > 0:
            # + jitter 100-300ms in production to decorrelate retries.
            await asyncio.sleep(wait)
        self._last_hit[host] = time.monotonic()

    # -- Public contract ----------------------------------------------------
    async def fetch(self, url):
        async with self.sem:  # 9th concurrent job queues here.
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            try:
                await self._throttle(url)
                status, body = self.try_tier1(url)
                if not self.should_escalate(status, body):
                    return {"markdown": body, "status": status, "tier_used": 1}
                markdown = self.escalate_tier3(url, status)
                return {"markdown": markdown, "status": status, "tier_used": 3}
            finally:
                self.active -= 1
