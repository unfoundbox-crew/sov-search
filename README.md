# sov-search

Local-first search stack: a self-hosted SearXNG cluster plus fetch workers and an offline corpus pipeline.

## Layout

- `compose/` — 3× SearXNG behind Caddy `:8888`, Valkey (no persistence), optional Tor sidecar. Lenovo deploy notes inside.
- `stealth/` — tiered fetch worker: curl_cffi impersonation → Scrapling → headless browser escalation (Lenovo only).
- `firehose/` — ingest pipeline: parse, dedup, schedule, SQLite store (`schema.sql`), with fixtures and tests.
- `index/` — query layer over the store, with tests.
- `offline/` — offline corpus tools: Common Crawl slicing, arXiv caps, ZIM builds.

## Test

```bash
python -m pytest
```

Secrets are never committed — placeholders only (`@SEARXNG_SECRET@`, `@MORTY_KEY@`). See `compose/README.md` and `stealth/README.md` for details.
