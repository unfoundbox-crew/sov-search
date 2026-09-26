#!/usr/bin/env bash
# zim.sh — serve local ZIM files over HTTP (offline backbone).
# Usage: ZIM_DIR=/data/zim ./zim.sh   (default ZIM_DIR ./zim)
# No downloads happen here. The wget lines below are commented,
# version-pinned names for the quarterly manual re-pull.
set -euo pipefail

ZIM_DIR="${ZIM_DIR:-./zim}"
PORT="${PORT:-8080}"

# --- Quarterly re-pull (manual, full-file; Kiwix ZIMs have NO incremental update) ---
# Re-pull cadence: once per quarter. Delete old file, fetch new, restart serve.
# Wikipedia EN nopic (no pictures keeps the box small):
#   wget -O wikipedia_en_nopic.zim "https://download.kiwix.org/zim/wikipedia/wikipedia_en_all_nopic_2026-08.zim"
# Per-site StackExchange splits (one ZIM per site, NOT the giant stackexchange.com bundle):
#   wget -O stackoverflow.zim  "https://download.kiwix.org/zim/stackexchange/stackexchange_stackoverflow.com_2026-08.zim"
#   wget -O serverfault.zim    "https://download.kiwix.org/zim/stackexchange/stackexchange_serverfault.com_2026-08.zim"
#   wget -O superuser.zim      "https://download.kiwix.org/zim/stackexchange/stackexchange_superuser.com_2026-08.zim"
# NOTE: bump the YYYY-MM stamps each quarter; no delta/sync mechanism exists.

if ! ls "$ZIM_DIR"/*.zim >/dev/null 2>&1; then
  echo "No .zim files in $ZIM_DIR — fetch per the commented wget lines, then rerun." >&2
  exit 1
fi

echo "Serving $ZIM_DIR/*.zim on :$PORT"
exec kiwix-serve --port "$PORT" "$ZIM_DIR"/*.zim
