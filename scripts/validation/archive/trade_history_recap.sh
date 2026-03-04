#!/bin/bash
# Trade History Recap Cron Script
# For ST-TRADING-001: Nightly Trade History Recap
#
# This script is designed to be run via cron at midnight UTC daily.
# It generates and sends the trade history recap to Discord #trading channel.
#
# Usage:
#   Add to crontab: 0 0 * * * /path/to/ChiseAI/scripts/cron/trade_history_recap.sh
#
# Or use systemd timer for more robust scheduling.
#
# ============================================================================
# CRON SETUP (idempotent - safe to run multiple times):
# ============================================================================
# To schedule this script to run daily at 00:00 UTC, add this line to crontab:
#
#   0 0 * * * /home/tacopants/projects/ChiseAI/scripts/cron/trade_history_recap.sh >> /home/tacopants/projects/ChiseAI/logs/trade_history_recap.log 2>&1
#
# To install the cron job (run once):
#   (crontab -l 2>/dev/null; echo "0 0 * * * /home/tacopants/projects/ChiseAI/scripts/cron/trade_history_recap.sh >> /home/tacopants/projects/ChiseAI/logs/trade_history_recap.log 2>&1") | crontab -
#
# To verify the cron job is installed:
#   crontab -l | grep trade_history_recap
#
# To remove the cron job:
#   crontab -l | grep -v trade_history_recap | crontab -
#
# Manual execution:
#   # Normal run (sends to #trading)
#   ./scripts/cron/trade_history_recap.sh
#
#   # Test run (sends test message)
#   ./scripts/cron/trade_history_recap.sh --test
#
#   # Dry run (no Discord message)
#   ./scripts/cron/trade_history_recap.sh --dry-run
#
# ============================================================================

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
LOG_DIR="${PROJECT_ROOT}/logs"
LOG_FILE="${LOG_DIR}/trade_history_recap.log"
LOCK_FILE="/tmp/chiseai_trade_history_recap.lock"

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
        log "ERROR: Trade history recap already running (PID: ${PID})"
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
log "Starting trade history recap generation"
log "=========================================="

# Change to project root
cd "${PROJECT_ROOT}"

# Load environment variables if .env exists
if [ -f ".env" ]; then
    # shellcheck source=/dev/null
    set -a
    source .env
    set +a
    log "Loaded environment from .env file"
fi

# Check if virtual environment exists and activate it
if [ -d "venv" ]; then
    # shellcheck source=/dev/null
    source venv/bin/activate
    log "Activated virtual environment (venv)"
elif [ -d ".venv" ]; then
    # shellcheck source=/dev/null
    source .venv/bin/activate
    log "Activated virtual environment (.venv)"
fi

# Check Python availability
if ! command -v python3 > /dev/null 2>&1; then
    log "ERROR: python3 not found"
    exit 1
fi

# Check required environment variables
if [ -z "${DISCORD_TRADING_WEBHOOK_URL:-}" ] && [ -z "${DISCORD_WEBHOOK_URL:-}" ]; then
    log "WARNING: Neither DISCORD_TRADING_WEBHOOK_URL nor DISCORD_WEBHOOK_URL is set"
    log "Discord messages will fail unless --dry-run is used"
fi

# Run the Python script
log "Generating trade history recap..."
START_TIME=$(date +%s)

# Pass through any command line arguments
if python3 scripts/run_trade_history_recap.py "$@" >> "${LOG_FILE}" 2>&1; then
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))
    log "✓ Trade history recap completed successfully (took ${DURATION}s)"
    exit_code=0
else
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))
    log "✗ Failed to generate trade history recap (took ${DURATION}s)"
    exit_code=1
fi

log "=========================================="
log "Trade history recap generation completed"
log "=========================================="
log ""

exit ${exit_code}
