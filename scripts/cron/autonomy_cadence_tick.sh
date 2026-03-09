#!/usr/bin/env bash
# Unified Autonomy Cadence Tick Wrapper
# Runs one scheduler tick (non-daemon) for cron-based deployment.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../.. && pwd)"
cd "$SCRIPT_DIR"

LOG_DIR="$SCRIPT_DIR/logs/autonomy-cadence"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/tick-$(date -u +%Y%m%d).log"

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] autonomy cadence tick start" >> "$LOG_FILE"

python3 scripts/evaluation/autonomy_cadence_controller.py >> "$LOG_FILE" 2>&1
rc=$?

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] autonomy cadence tick end rc=$rc" >> "$LOG_FILE"
exit "$rc"
