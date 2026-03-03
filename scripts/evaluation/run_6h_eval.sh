#!/bin/bash
# SAFETY: No risk cap logic modified
# SAFETY: No promotion gate logic modified
# SAFETY: No live trading flow modified
#
# 6-hour BrainEval cadence runner
# Calls run_mini_eval.py for KPI snapshot persistence

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
LOG_DIR="${PROJECT_ROOT}/_bmad-output/brain-eval/logs"
OUTPUT_DIR="${PROJECT_ROOT}/_bmad-output/brain-eval/kpi-snapshots"
LOCK_FILE="/tmp/run_6h_eval.lock"

# Acquire lock (prevent concurrent runs)
exec 200>"${LOCK_FILE}"
flock -n 200 || {
    echo "Another 6h eval is already running, exiting"
    exit 0
}

# Create directories
mkdir -p "${LOG_DIR}"
mkdir -p "${OUTPUT_DIR}"

LOG_FILE="${LOG_DIR}/6h-$(date +%Y%m%d-%H%M%S).log"

echo "========================================" | tee -a "${LOG_FILE}"
echo "6-Hour Mini Eval (KPI Snapshot)" | tee -a "${LOG_FILE}"
echo "Started: $(date -Iseconds)" | tee -a "${LOG_FILE}"
echo "Lock File: ${LOCK_FILE}" | tee -a "${LOG_FILE}"
echo "========================================" | tee -a "${LOG_FILE}"

# Run the evaluation
cd "${PROJECT_ROOT}"
python3 "${SCRIPT_DIR}/run_mini_eval.py" \
    --output-dir "${OUTPUT_DIR}" \
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
