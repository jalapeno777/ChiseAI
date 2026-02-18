#!/bin/bash
# Daily Summary Cron Script
# For PAPER-LIVE-001: Daily Summary Scheduler
#
# This script is designed to be run via cron at midnight daily.
# It generates and sends the daily trading summary to Discord.
#
# Usage:
#   Add to crontab: 0 0 * * * /path/to/ChiseAI/scripts/cron/daily_summary.sh
#
# Or use systemd timer for more robust scheduling.

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
LOG_DIR="${PROJECT_ROOT}/logs"
LOG_FILE="${LOG_DIR}/daily_summary.log"
LOCK_FILE="/tmp/chiseai_daily_summary.lock"

# Create log directory if it doesn't exist
mkdir -p "${LOG_DIR}"

# Logging function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "${LOG_FILE}"
}

# Check if already running (prevent overlapping executions)
if [ -f "${LOCK_FILE}" ]; then
    PID=$(cat "${LOCK_FILE}")
    if ps -p "${PID}" > /dev/null 2>&1; then
        log "ERROR: Daily summary already running (PID: ${PID})"
        exit 1
    else
        log "WARNING: Stale lock file found, removing"
        rm -f "${LOCK_FILE}"
    fi
fi

# Create lock file
echo $$ > "${LOCK_FILE}"

# Cleanup function
cleanup() {
    rm -f "${LOCK_FILE}"
}
trap cleanup EXIT

log "=========================================="
log "Starting daily summary generation"
log "=========================================="

# Change to project root
cd "${PROJECT_ROOT}"

# Check if virtual environment exists and activate it
if [ -d "venv" ]; then
    # shellcheck source=/dev/null
    source venv/bin/activate
    log "Activated virtual environment"
elif [ -d ".venv" ]; then
    # shellcheck source=/dev/null
    source .venv/bin/activate
    log "Activated virtual environment"
fi

# Check Python availability
if ! command -v python3 > /dev/null 2>&1; then
    log "ERROR: python3 not found"
    exit 1
fi

# Run health check first
log "Running health check..."
if ! python3 scripts/run_daily_summary.py --health-check >> "${LOG_FILE}" 2>&1; then
    log "WARNING: Health check failed, continuing anyway"
fi

# Generate and send daily summary
log "Generating daily summary report..."
START_TIME=$(date +%s)

if python3 scripts/run_daily_summary.py "$@" >> "${LOG_FILE}" 2>&1; then
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))
    log "✓ Daily summary sent successfully (took ${DURATION}s)"
    exit_code=0
else
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))
    log "✗ Failed to send daily summary (took ${DURATION}s)"
    exit_code=1
fi

log "=========================================="
log "Daily summary generation completed"
log "=========================================="
log ""

exit ${exit_code}
