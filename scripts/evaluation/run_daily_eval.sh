#!/bin/bash
# SAFETY: No risk cap logic modified
# SAFETY: No promotion gate logic modified
# SAFETY: No live trading flow modified
#
# Daily BrainEval cadence runner
# Runs mini_brain_eval.py with daily cadence

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
LOG_DIR="${PROJECT_ROOT}/_bmad-output/brain-eval/logs"
OUTPUT_DIR="${PROJECT_ROOT}/_bmad-output/brain-eval"

# Create log directory
mkdir -p "${LOG_DIR}"

LOG_FILE="${LOG_DIR}/daily-$(date +%Y%m%d-%H%M%S).log"

echo "========================================" | tee -a "${LOG_FILE}"
echo "Daily BrainEval Cadence" | tee -a "${LOG_FILE}"
echo "Started: $(date -Iseconds)" | tee -a "${LOG_FILE}"
echo "========================================" | tee -a "${LOG_FILE}"

# Run the evaluation
cd "${PROJECT_ROOT}"
python3 "${SCRIPT_DIR}/mini_brain_eval.py" \
    --cadence daily \
    --output-dir "${OUTPUT_DIR}" \
    2>&1 | tee -a "${LOG_FILE}"

EXIT_CODE=${PIPESTATUS[0]}

echo "" | tee -a "${LOG_FILE}"
echo "========================================" | tee -a "${LOG_FILE}"
echo "Completed: $(date -Iseconds)" | tee -a "${LOG_FILE}"
echo "Exit Code: ${EXIT_CODE}" | tee -a "${LOG_FILE}"
echo "========================================" | tee -a "${LOG_FILE}"

exit ${EXIT_CODE}
