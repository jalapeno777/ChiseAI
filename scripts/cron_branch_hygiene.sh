#!/bin/bash
#
# Cron script for branch hygiene automation
# Run this script hourly to maintain branch hygiene
#
# Installation:
#   Add to crontab: 0 * * * * /path/to/repo/scripts/cron_branch_hygiene.sh
#
# Environment variables (set in .env or export before running):
#   GITEA_TOKEN - Required. Gitea API token
#   GITEA_BASE_URL - Optional. Default: http://host.docker.internal:3000
#   GITEA_OWNER - Optional. Default: craig
#   GITEA_REPO - Optional. Default: ChiseAI
#   REDIS_HOST - Optional. Default: host.docker.internal
#   REDIS_PORT - Optional. Default: 6380
#   BRANCH_HYGIENE_DRY_RUN - Optional. Set to "1" for dry run mode
#

set -euo pipefail

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Load .env if it exists
if [[ -f "${REPO_ROOT}/.env" ]]; then
    # shellcheck source=/dev/null
    source "${REPO_ROOT}/.env"
fi

# Check required environment variables
if [[ -z "${GITEA_TOKEN:-}" ]]; then
    echo "ERROR: GITEA_TOKEN environment variable is required" >&2
    exit 1
fi

# Set defaults
export GITEA_BASE_URL="${GITEA_BASE_URL:-http://host.docker.internal:3000}"
export GITEA_OWNER="${GITEA_OWNER:-craig}"
export GITEA_REPO="${GITEA_REPO:-ChiseAI}"
export REDIS_HOST="${REDIS_HOST:-host.docker.internal}"
export REDIS_PORT="${REDIS_PORT:-6380}"

# Optional dry run
DRY_RUN_FLAG=""
if [[ "${BRANCH_HYGIENE_DRY_RUN:-}" == "1" ]]; then
    DRY_RUN_FLAG="--dry-run"
    echo "[DRY RUN MODE] No branches will be deleted"
fi

# Log file
LOG_DIR="${REPO_ROOT}/_bmad-output/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/branch_hygiene_$(date +%Y%m%d_%H%M%S).log"

# Run branch hygiene
echo "Starting branch hygiene check at $(date)"
echo "Log file: ${LOG_FILE}"

python3 "${SCRIPT_DIR}/branch_hygiene.py" \
    --base-url "${GITEA_BASE_URL}" \
    --owner "${GITEA_OWNER}" \
    --repo "${GITEA_REPO}" \
    ${DRY_RUN_FLAG} \
    --check all \
    --redis-host "${REDIS_HOST}" \
    --redis-port "${REDIS_PORT}" \
    2>&1 | tee "${LOG_FILE}"

EXIT_CODE=${PIPESTATUS[0]}

if [[ ${EXIT_CODE} -eq 0 ]]; then
    echo "Branch hygiene check completed successfully at $(date)"
else
    echo "Branch hygiene check failed with exit code ${EXIT_CODE} at $(date)" >&2
fi

exit ${EXIT_CODE}
