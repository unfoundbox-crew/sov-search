# Stealth fetch worker — Lenovo wiring notes

Lane D stub. `worker.py` runs here with stubs only. Real browsers run on Lenovo.

## Tier-1: curl_cffi (Lenovo)

```
python -m curl_cffi.requests --impersonate chrome124 get <URL>
```

Keep UA ↔ TLS ↔ geo consistent (see rule below). 403 / challenge /
empty body → hand the URL to this worker's `fetch()`.

## Tiers via Scrapling (Lenovo)

- Tier-1/2: Scrapling auto-match + flags for light JS.
- Tier-3 only on escalation: full headless browser, persistent context.

## Tier-3: Patchright headed snippet (Lenovo only, text — not executed here)

```
from patchright.async_api import async_playwright
async with async_playwright() as p:
    browser = await p.chromium.launch(channel="chrome", headless=False)
    ctx = await browser.new_context(persistent=True, user_data_dir="./profiles/p1")
    page = await ctx.new_page()
    await page.goto(url)
    md = await page.content()  # → convert to markdown downstream
```

## Tier-3: Camoufox snippet (Lenovo only, text — not executed here)

```
from camoufox.async_api import AsyncCamoufox
async with AsyncCamoufox(geoip=True, humanize=True,
                         user_data_dir="./profiles/p1") as browser:
    page = await browser.new_page()
    await page.goto(url)
```

## cf_clearance reuse

Persist `cf_clearance` cookie per (host, profile). Reuse the same
`user_data_dir` on retry before rotating fingerprint-seed or proxy.

## Consistency rule

UA ↔ TLS ↔ geo must agree: the User-Agent string, the TLS fingerprint
(impersonation target), and the egress geo (proxy + `geoip`) must tell
the same story, or the challenge rate goes up. Rotate all three together.
