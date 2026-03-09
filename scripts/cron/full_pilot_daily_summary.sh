#!/usr/bin/env bash
# Full Pilot Daily Executive Summary Cron Wrapper

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../.. && pwd)"
cd "$REPO_ROOT"

LOG_DIR="$REPO_ROOT/logs/full-pilot"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/daily-summary-$(date -u +%Y%m%d).log"

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] full-pilot daily summary start" >> "$LOG_FILE"
python3 scripts/ops/post_daily_full_pilot_summary.py --regenerate >> "$LOG_FILE" 2>&1
rc=$?
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] full-pilot daily summary end rc=$rc" >> "$LOG_FILE"
exit "$rc"
