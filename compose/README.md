# SOV Search — SearXNG cluster (Lenovo)

3x SearXNG behind Caddy `:8888`, Valkey (no persistence), optional Tor sidecar.

## Deploy (Lenovo)

```bash
ssh lenovo
cd /opt/sov-search/compose  # or wherever this dir is synced
openssl rand -hex 32         # generate secret
export SEARXNG_SECRET='<paste-hex>'
export MORTY_KEY='<paste-hex>'  # if morty proxy enabled
docker compose up -d
docker compose ps
```

Secrets: never committed. Placeholders only in repo (`@SEARXNG_SECRET@`, `@MORTY_KEY@`).

## Health checks

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8888/
docker compose logs searxng 2>&1 | grep -Ei 'suspend|429|captcha' | head -20
docker compose exec valkey valkey-cli ping  # expect PONG
docker compose exec valkey valkey-cli info server | head -5
```

## limiter.toml trusted_proxies note

`limiter.toml` (botdetection) must trust Caddy so real client IPs pass through.
`X-Real-IP` / `X-Forwarded-For` are set in `Caddyfile`; add Caddy's network
to `trusted_proxies` in `limiter.toml`, e.g. the `sov` subnet or gateway IP.
Without this the limiter sees only the proxy IP and throttles everyone as one client.

## Engine enable list

Enabled by default (privacy-friendly, low-captcha): `brave`, `duckduckgo`,
`startpage`, `mojeek`, `marginalia`, `mwmbl`, `wikipedia`, `stackoverflow`,
`arxiv`, `github`.

Removed in `settings.yml`: `google`, `bing` (captcha / suspend risk).
