#!/bin/bash
# SAFETY: No risk cap logic modified
# SAFETY: No promotion gate logic modified
# SAFETY: No live trading flow modified
#
# Daily Trends cadence runner
# Calls run_daily_trends.py for trend rollups and daily reflection

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
LOG_DIR="${PROJECT_ROOT}/_bmad-output/brain-eval/logs"
LOCK_FILE="/tmp/run_daily_eval.lock"

# Acquire lock (prevent concurrent runs)
exec 200>"${LOCK_FILE}"
flock -n 200 || {
    echo "Another daily eval is already running, exiting"
    exit 0
}

# Create directories
mkdir -p "${LOG_DIR}"

LOG_FILE="${LOG_DIR}/daily-$(date +%Y%m%d-%H%M%S).log"

echo "========================================" | tee -a "${LOG_FILE}"
echo "Daily Trends Rollup & Reflection" | tee -a "${LOG_FILE}"
echo "Started: $(date -Iseconds)" | tee -a "${LOG_FILE}"
echo "Lock File: ${LOCK_FILE}" | tee -a "${LOG_FILE}"
echo "========================================" | tee -a "${LOG_FILE}"

# Run the evaluation
cd "${PROJECT_ROOT}"
python3 "${SCRIPT_DIR}/run_daily_trends.py" \
    2>&1 | tee -a "${LOG_FILE}"

EXIT_CODE=${PIPESTATUS[0]}

echo "" | tee -a "${LOG_FILE}"
echo "========================================" | tee -a "${LOG_FILE}"
echo "Completed: $(date -Iseconds)" | tee -a "${LOG_FILE}"
echo "Exit Code: ${EXIT_CODE}" | tee -a "${LOG_FILE}"
echo "========================================" | tee -a "${LOG_FILE}"

# Release lock
flock -u 200

exit ${EXIT_CODE}
