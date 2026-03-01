#!/bin/bash
# Daily BrainEval Scheduler
# For ST-BRAIN-EVAL-002: BrainEval Scheduling Infrastructure
#
# # SAFETY: No risk cap logic modified
# # SAFETY: No promotion gate logic modified
# # SAFETY: No live trading flow modified
#
# This script runs MiniBrainEval daily.
# Designed to be run via cron at 06:00 UTC daily.
#
# Cron configuration:
#   0 6 * * * /path/to/ChiseAI/scripts/evaluation/run_daily_eval.sh
#
# Or use systemd timer for more robust scheduling.

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
OUTPUT_DIR="${PROJECT_ROOT}/_bmad-output/brain-eval"
LOG_DIR="${OUTPUT_DIR}/logs"
LOG_FILE="${LOG_DIR}/daily_eval.log"
LOCK_FILE="/tmp/chiseai_daily_eval.lock"

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
        log "ERROR: Daily evaluation already running (PID: ${PID})"
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
log "Starting daily BrainEval"
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

# Create output directories
mkdir -p "${OUTPUT_DIR}/daily"
mkdir -p "${OUTPUT_DIR}/logs"

# Run daily evaluation
log "Running daily evaluation..."
START_TIME=$(date +%s)

if python3 scripts/evaluation/schedule_brain_eval.py \
    --cadence daily \
    --output-dir "${OUTPUT_DIR}" \
    "$@" >> "${LOG_FILE}" 2>&1; then
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))
    log "✓ Daily evaluation completed successfully (took ${DURATION}s)"
    exit_code=0
else
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))
    log "✗ Daily evaluation failed (took ${DURATION}s)"
    exit_code=1
fi

log "=========================================="
log "Daily BrainEval completed"
log "=========================================="
log ""

exit ${exit_code}
