#!/bin/bash
# Diagnostic script for crontab scheduler verification
# Checks if midnight summary job is present and functional
# For CH-KIMI-DIAG-001-crontab

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
OUTPUT_DIR="${PROJECT_ROOT}/_bmad-output"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
DATESTAMP=$(date +"%Y%m%d_%H%M%S")
OUTPUT_FILE="${OUTPUT_DIR}/crontab_check_${DATESTAMP}.json"

# Ensure output directory exists
mkdir -p "${OUTPUT_DIR}"

# Generate UUID-like identifier
CHECK_ID=$(cat /proc/sys/kernel/random/uuid 2>/dev/null || echo "diag-$(date +%s)-$$")

# Initialize result variables
CRONTAB_PRESENT=false
MIDNIGHT_JOB_FOUND=false
MIDNIGHT_JOB_LINE=""
CRON_DAEMON_RUNNING=false
CHISEAI_JOBS=()
RECOMMENDATION=""

# Colors for terminal output (if supported)
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $*"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*"
}

echo "=========================================="
echo "Crontab Scheduler Diagnostic"
echo "Check ID: ${CHECK_ID}"
echo "Timestamp: ${TIMESTAMP}"
echo "=========================================="
echo ""

# 1. Check if crontab exists
log_info "Checking crontab..."
CRONTAB_CONTENT=$(crontab -l 2>/dev/null || echo "")
if [ -n "${CRONTAB_CONTENT}" ]; then
    CRONTAB_PRESENT=true
    log_info "✓ Crontab found"
else
    log_warn "✗ No crontab for current user"
fi

# 2. Check for midnight summary job
log_info "Checking for midnight summary job..."
if [ "${CRONTAB_PRESENT}" = true ]; then
    # Look for midnight job (0 0 * * *) related to ChiseAI daily summary
    MIDNIGHT_LINE=$(echo "${CRONTAB_CONTENT}" | grep -E "^0 0 \* \* \*.*daily_summary" || echo "")
    
    if [ -n "${MIDNIGHT_LINE}" ]; then
        MIDNIGHT_JOB_FOUND=true
        MIDNIGHT_JOB_LINE="${MIDNIGHT_LINE}"
        log_info "✓ Midnight summary job found:"
        echo "    ${MIDNIGHT_JOB_LINE}"
    else
        log_warn "✗ Midnight summary job not found"
    fi
fi

# 3. Check cron daemon status
log_info "Checking cron daemon status..."
CRON_PID=$(pgrep -x "cron" || pgrep -x "crond" || echo "")
if [ -n "${CRON_PID}" ]; then
    CRON_DAEMON_RUNNING=true
    log_info "✓ Cron daemon running (PID: ${CRON_PID})"
else
    log_warn "✗ Cron daemon not running"
fi

# 4. Find all ChiseAI-related jobs
log_info "Searching for ChiseAI-related cron jobs..."
if [ "${CRONTAB_PRESENT}" = true ]; then
    # Parse crontab for ChiseAI jobs
    while IFS= read -r line; do
        # Skip comments and empty lines
        [[ "$line" =~ ^#.*$ ]] && continue
        [[ -z "$line" ]] && continue
        
        # Check if line contains ChiseAI-related content
        if echo "$line" | grep -qiE "(chiseai|daily_summary|paper_trading)"; then
            # Extract schedule and command
            if [[ "$line" =~ ^([0-9*,/-]+[[:space:]]+[0-9*,/-]+[[:space:]]+[0-9*,/-]+[[:space:]]+[0-9*,/-]+[[:space:]]+[0-9*,/-]+)[[:space:]]+(.+)$ ]]; then
                SCHEDULE="${BASH_REMATCH[1]}"
                COMMAND="${BASH_REMATCH[2]}"
                
                # Determine description
                DESCRIPTION="ChiseAI scheduled task"
                if echo "$line" | grep -q "daily_summary"; then
                    DESCRIPTION="Daily summary generation"
                elif echo "$line" | grep -q "paper_trading"; then
                    DESCRIPTION="Paper trading daily check"
                elif echo "$line" | grep -q "@reboot"; then
                    DESCRIPTION="Startup script"
                    SCHEDULE="@reboot"
                    COMMAND="${line#@reboot }"
                fi
                
                CHISEAI_JOBS+=("{\"schedule\":\"${SCHEDULE}\",\"command\":\"${COMMAND}\",\"description\":\"${DESCRIPTION}\"}")
                log_info "Found: ${DESCRIPTION}"
            fi
        fi
    done <<< "${CRONTAB_CONTENT}"
fi

# 5. Verify script referenced exists
SCRIPT_EXISTS=false
if [ "${MIDNIGHT_JOB_FOUND}" = true ]; then
    log_info "Verifying referenced script exists..."
    SCRIPT_PATH=$(echo "${MIDNIGHT_JOB_LINE}" | awk '{for(i=6;i<=NF;i++) print $i}' | head -1)
    # Handle both direct script paths and commands with arguments
    if [ -f "${SCRIPT_PATH}" ]; then
        SCRIPT_EXISTS=true
        log_info "✓ Script exists: ${SCRIPT_PATH}"
        
        # Check if executable
        if [ -x "${SCRIPT_PATH}" ]; then
            log_info "✓ Script is executable"
        else
            log_warn "✗ Script is not executable"
        fi
    else
        # Try to extract from the command (might be wrapped)
        EXTRACTED_PATH=$(echo "${MIDNIGHT_JOB_LINE}" | grep -oE '/home/[^[:space:]]+\.sh' || echo "")
        if [ -n "${EXTRACTED_PATH}" ] && [ -f "${EXTRACTED_PATH}" ]; then
            SCRIPT_EXISTS=true
            log_info "✓ Script exists: ${EXTRACTED_PATH}"
        else
            log_warn "✗ Script not found: ${SCRIPT_PATH}"
        fi
    fi
fi

# 6. Check last execution (if log exists)
LAST_EXECUTION="unknown"
LOG_FILE="/home/tacopants/projects/ChiseAI/logs/daily_summary_cron.log"
if [ -f "${LOG_FILE}" ]; then
    LAST_LINE=$(tail -1 "${LOG_FILE}" 2>/dev/null || echo "")
    if [ -n "${LAST_LINE}" ]; then
        LAST_EXECUTION=$(echo "${LAST_LINE}" | grep -oE '^\[[0-9]{4}-[0-9]{2}-[0-9]{2}' | tr -d '[]' || echo "unknown")
        log_info "Last execution recorded: ${LAST_EXECUTION}"
    fi
else
    log_warn "No log file found at ${LOG_FILE}"
fi

# 7. Generate recommendation
if [ "${CRONTAB_PRESENT}" = false ]; then
    RECOMMENDATION="No crontab exists. Install midnight summary job using: crontab -e and add: 0 0 * * * /home/tacopants/projects/ChiseAI/scripts/cron/daily_summary.sh >> /home/tacopants/projects/ChiseAI/logs/daily_summary_cron.log 2>&1"
elif [ "${MIDNIGHT_JOB_FOUND}" = false ]; then
    RECOMMENDATION="Midnight summary job missing. Add to crontab: 0 0 * * * /home/tacopants/projects/ChiseAI/scripts/cron/daily_summary.sh >> /home/tacopants/projects/ChiseAI/logs/daily_summary_cron.log 2>&1"
elif [ "${CRON_DAEMON_RUNNING}" = false ]; then
    RECOMMENDATION="Cron daemon not running. Start with: sudo service cron start or sudo systemctl start cron"
elif [ "${SCRIPT_EXISTS}" = false ]; then
    RECOMMENDATION="Midnight job configured but script not found. Verify script path or reinstall."
else
    RECOMMENDATION="All checks passed. Midnight summary job is properly configured and cron daemon is running."
fi

echo ""
echo "=========================================="
echo "Diagnostic Summary"
echo "=========================================="
echo "Crontab Present: ${CRONTAB_PRESENT}"
echo "Midnight Job Found: ${MIDNIGHT_JOB_FOUND}"
echo "Cron Daemon Running: ${CRON_DAEMON_RUNNING}"
echo "Script Exists: ${SCRIPT_EXISTS}"
echo "ChiseAI Jobs Found: ${#CHISEAI_JOBS[@]}"
echo ""
echo "Recommendation: ${RECOMMENDATION}"
echo "=========================================="

# Build JSON output
JOBS_JSON="["
for i in "${!CHISEAI_JOBS[@]}"; do
    if [ $i -gt 0 ]; then
        JOBS_JSON+=","
    fi
    JOBS_JSON+="${CHISEAI_JOBS[$i]}"
done
JOBS_JSON+="]"

# Escape special characters for JSON
MIDNIGHT_JOB_LINE_ESCAPED=$(echo "${MIDNIGHT_JOB_LINE}" | sed 's/\\/\\\\/g; s/"/\\"/g; s/\t/\\t/g')
RECOMMENDATION_ESCAPED=$(echo "${RECOMMENDATION}" | sed 's/\\/\\\\/g; s/"/\\"/g')

# Write JSON output
cat > "${OUTPUT_FILE}" << EOF
{
  "check_id": "${CHECK_ID}",
  "timestamp": "${TIMESTAMP}",
  "crontab_present": ${CRONTAB_PRESENT},
  "midnight_job_found": ${MIDNIGHT_JOB_FOUND},
  "midnight_job_line": "${MIDNIGHT_JOB_LINE_ESCAPED}",
  "cron_daemon_running": ${CRON_DAEMON_RUNNING},
  "script_exists": ${SCRIPT_EXISTS},
  "last_execution": "${LAST_EXECUTION}",
  "chiseai_jobs": ${JOBS_JSON},
  "recommendation": "${RECOMMENDATION_ESCAPED}"
}
EOF

echo ""
log_info "Diagnostic complete. Output saved to: ${OUTPUT_FILE}"

# Return exit code based on status
if [ "${MIDNIGHT_JOB_FOUND}" = true ] && [ "${CRON_DAEMON_RUNNING}" = true ] && [ "${SCRIPT_EXISTS}" = true ]; then
    exit 0
else
    exit 1
fi
