#!/usr/bin/env bash
#
# log_incident.sh - Log an incident for post-mortem analysis
# Part of PAPER-003-005: Executable Runbook Framework
#
# Usage: ./log_incident.sh --type <type> --severity <level> [--reason <reason>] [--portfolio <id>]
#
# This script creates an incident record for kill switch and other critical events.
#

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${SCRIPT_DIR}/../../logs/incidents"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Default values
INCIDENT_TYPE=""
SEVERITY=""
REASON=""
PORTFOLIO_ID=""
DRY_RUN=false

# Usage information
usage() {
    cat << EOF
Usage: $(basename "$0") --type <type> --severity <level> [OPTIONS]

Log an incident for post-mortem analysis.

REQUIRED:
    -t, --type <type>         Incident type (kill_switch, redis_failure, api_disconnect, etc.)
    -s, --severity <level>   Severity level (emergency, critical, warning, info)

OPTIONS:
    -r, --reason <reason>    Reason or trigger for the incident
    -p, --portfolio <id>     Portfolio ID affected
    -d, --dry-run           Show what would be done without executing
    -h, --help              Show this help message

EXAMPLES:
    $(basename "$0") -t kill_switch -s emergency -r "margin > 95%"
    $(basename "$0") -t redis_failure -s critical -p portfolio_001

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

# Parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            -t|--type)
                INCIDENT_TYPE="$2"
                shift 2
                ;;
            -s|--severity)
                SEVERITY="$2"
                shift 2
                ;;
            -r|--reason)
                REASON="$2"
                shift 2
                ;;
            -p|--portfolio)
                PORTFOLIO_ID="$2"
                shift 2
                ;;
            -d|--dry-run)
                DRY_RUN=true
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
    
    # Validate required arguments
    if [ -z "$INCIDENT_TYPE" ]; then
        log_error "Incident type is required. Use -t or --type"
        usage
    fi
    
    if [ -z "$SEVERITY" ]; then
        log_error "Severity is required. Use -s or --severity"
        usage
    fi
}

# Create incident record
create_incident() {
    local timestamp
    timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    
    local incident_id
    incident_id="INC-$(date +%Y%m%d-%H%M%S)-$(echo "$INCIDENT_TYPE" | tr '[:lower:]' '[:upper:]' | tr '_' '-')"
    
    local incident_file="$LOG_DIR/${incident_id}.json"
    
    local incident_data
    incident_data=$(cat << EOF
{
  "incident_id": "$incident_id",
  "timestamp": "$timestamp",
  "type": "$INCIDENT_TYPE",
  "severity": "$SEVERITY",
  "reason": "$REASON",
  "portfolio_id": "$PORTFOLIO_ID",
  "status": "open",
  "logged_by": "runbook_executor"
}
EOF
)
    
    if [ "$DRY_RUN" = true ]; then
        log_info "[DRY-RUN] Would create incident: $incident_id"
        echo "$incident_data"
        return
    fi
    
    # Create log directory
    mkdir -p "$LOG_DIR"
    
    # Write incident file
    echo "$incident_data" > "$incident_file"
    
    log_success "Incident logged: $incident_id"
    log_info "Incident file: $incident_file"
}

# Main function
main() {
    parse_args "$@"
    
    log_info "=============================================="
    log_info "ChiseAI Incident Logger"
    log_info "Type: $INCIDENT_TYPE"
    log_info "Severity: $SEVERITY"
    log_info "=============================================="
    
    create_incident
}

# Run main function
main "$@"
