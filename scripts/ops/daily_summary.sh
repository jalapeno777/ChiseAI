#!/usr/bin/env bash
#
# daily_summary.sh - Generate daily summary for paper trading operations
# Part of PAPER-003-003: Automated Reporting and Anomaly Detection
#
# Usage: ./daily_summary.sh [--mode=paper|live] [--date=YYYY-MM-DD] [--output <file>]
#
# This script triggers the daily report generation via the reporting module.
#

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
LOG_DIR="${PROJECT_ROOT}/logs"
REPORTS_DIR="${PROJECT_ROOT}/reports"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Default values
MODE="paper"
DATE=""
OUTPUT=""
DRY_RUN=false
VERBOSE=false
USE_MOCK=false
DISCORD_WEBHOOK=""

# Usage information
usage() {
    cat << EOF
Usage: $(basename "$0") [OPTIONS]

Generate daily summary report for paper trading operations.

OPTIONS:
    -m, --mode <mode>          Trading mode: paper or live (default: paper)
    -d, --date <date>          Date for summary (default: yesterday)
    -o, --output <file>        Output file (default: stdout)
    --discord <webhook>        Discord webhook URL for notification
    --mock                     Use mock data for testing
    -n, --dry-run              Show what would be done without executing
    -v, --verbose              Enable verbose output
    -h, --help                 Show this help message

EXAMPLES:
    $(basename "$0")                           # Today's paper summary
    $(basename "$0") -m paper -d 2026-02-17    # Specific date
    $(basename "$0") -o /tmp/summary.md        # Save to file
    $(basename "$0") --discord <webhook_url>   # Send to Discord

EOF
    exit 0
}

# Log functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $(date '+%Y-%m-%d %H:%M:%S') $*"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $(date '+%Y-%m-%d %H:%M:%S') $*"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $(date '+%Y-%m-%d %H:%M:%S') $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $(date '+%Y-%m-%d %H:%M:%S') $*"
}

log_step() {
    echo -e "${CYAN}[STEP]${NC} $(date '+%Y-%m-%d %H:%M:%S') $*"
}

log_verbose() {
    if [ "$VERBOSE" = true ]; then
        echo -e "[DEBUG] $(date '+%Y-%m-%d %H:%M:%S') $*"
    fi
}

# Parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            -m|--mode)
                MODE="$2"
                shift 2
                ;;
            -d|--date)
                DATE="$2"
                shift 2
                ;;
            -o|--output)
                OUTPUT="$2"
                shift 2
                ;;
            --discord)
                DISCORD_WEBHOOK="$2"
                shift 2
                ;;
            --mock)
                USE_MOCK=true
                shift
                ;;
            -n|--dry-run)
                DRY_RUN=true
                shift
                ;;
            -v|--verbose)
                VERBOSE=true
                shift
                ;;
            -h|--help)
                usage
                ;;
            *)
                log_error "Unknown option: $1"
                usage
                ;;
        esac
    done
    
    # Validate mode
    if [[ "$MODE" != "paper" && "$MODE" != "live" ]]; then
        log_error "Invalid mode: $MODE. Must be 'paper' or 'live'"
        exit 1
    fi
}

# Generate report using Python module
generate_report() {
    log_step "Generating daily report via Python module"
    
    local python_cmd="${PROJECT_ROOT}/.venv/bin/python"
    if [ ! -f "$python_cmd" ]; then
        python_cmd="python3"
    fi
    
    local date_arg=""
    if [ -n "$DATE" ]; then
        date_arg="--date $DATE"
    fi
    
    local mock_arg=""
    if [ "$USE_MOCK" = true ]; then
        mock_arg="--mock"
    fi
    
    # Run Python script to generate report
    local report
    report=$($python_cmd -c "
import asyncio
import sys
sys.path.insert(0, '${PROJECT_ROOT}/src')

from reporting.daily_generator import DailyReportGenerator
from datetime import datetime

async def main():
    generator = DailyReportGenerator()
    
    date = None
    if '${DATE}':
        date = datetime.strptime('${DATE}', '%Y-%m-%d')
    
    report = await generator.generate_report(date=date, use_mock_data=${USE_MOCK})
    print(report.to_markdown())

asyncio.run(main())
" 2>&1)
    
    if [ $? -ne 0 ]; then
        log_error "Failed to generate report: $report"
        exit 1
    fi
    
    echo "$report"
}

# Send to Discord
send_discord() {
    local content="$1"
    
    if [ -z "$DISCORD_WEBHOOK" ]; then
        log_verbose "No Discord webhook configured, skipping"
        return 0
    fi
    
    log_step "Sending report to Discord"
    
    # Truncate if too long (Discord limit is 2000 chars)
    local truncated="${content:0:1900}"
    if [ "${#content}" -gt 1900 ]; then
        truncated="${truncated}...\n\n*(Report truncated)*"
    fi
    
    local payload
    payload=$(jq -n --arg content "$truncated" '{content: $content}')
    
    local response
    response=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "$payload" \
        "$DISCORD_WEBHOOK" 2>&1)
    
    if [ $? -eq 0 ]; then
        log_success "Report sent to Discord"
    else
        log_error "Failed to send to Discord: $response"
    fi
}

# Main function
main() {
    parse_args "$@"
    
    # Create directories
    mkdir -p "$LOG_DIR"
    mkdir -p "$REPORTS_DIR"
    
    log_info "=============================================="
    log_info "ChiseAI Daily Summary Report"
    log_info "Mode: $MODE"
    log_info "Date: ${DATE:-yesterday}"
    log_info "=============================================="
    
    if [ "$DRY_RUN" = true ]; then
        log_info "[DRY-RUN] Would generate daily report"
        log_info "[DRY-RUN] Mode: $MODE"
        log_info "[DRY-RUN] Date: ${DATE:-yesterday}"
        log_info "[DRY-RUN] Mock data: $USE_MOCK"
        [ -n "$DISCORD_WEBHOOK" ] && log_info "[DRY-RUN] Discord webhook: configured"
        exit 0
    fi
    
    # Generate report
    local report
    report=$(generate_report)
    
    # Output report
    if [ -n "$OUTPUT" ]; then
        echo "$report" > "$OUTPUT"
        log_success "Report saved to: $OUTPUT"
    else
        echo "$report"
    fi
    
    # Send to Discord if configured
    if [ -n "$DISCORD_WEBHOOK" ]; then
        send_discord "$report"
    fi
    
    log_success "Daily summary generation completed"
}

# Run main function
main "$@"
