#!/usr/bin/env bash
#
# trigger_kill_switch.sh - Trigger kill switch for emergency situations
# Part of PAPER-003-005: Executable Runbook Framework
#
# Usage: ./trigger_kill_switch.sh [--reason <reason>] [--portfolio <id>] [--dry-run]
#
# This script triggers the kill switch to halt all trading operations.
#

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_ENDPOINT="${API_ENDPOINT:-http://localhost:8001}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Default values
REASON="manual_trigger"
PORTFOLIO_ID=""
DRY_RUN=false

# Usage information
usage() {
    cat << EOF
Usage: $(basename "$0") [OPTIONS]

Trigger kill switch to halt all trading operations.

OPTIONS:
    -r, --reason <reason>    Reason for triggering kill switch
    -p, --portfolio <id>     Specific portfolio ID (if applicable)
    -d, --dry-run           Show what would be done without executing
    -h, --help              Show this help message

EXAMPLES:
    $(basename "$0") -r "manual_emergency"
    $(basename "$0") -r "margin_threshold" -p portfolio_001

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

# Parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
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
}

# Trigger kill switch via API
trigger_kill_switch() {
    log_step "Triggering kill switch"
    
    local payload
    if [ -n "$PORTFOLIO_ID" ]; then
        payload="{\"reason\": \"$REASON\", \"portfolio_id\": \"$PORTFOLIO_ID\"}"
    else
        payload="{\"reason\": \"$REASON\"}"
    fi
    
    if [ "$DRY_RUN" = true ]; then
        log_info "[DRY-RUN] Would trigger kill switch"
        log_info "[DRY-RUN] Payload: $payload"
        return 0
    fi
    
    # Call API to pause execution
    local response
    if ! response=$(curl -s -X POST "$API_ENDPOINT/api/v1/execution/pause" \
        -H "Content-Type: application/json" \
        -d "$payload" 2>/dev/null); then
        log_error "Failed to trigger kill switch via API"
        return 1
    fi
    
    log_success "Kill switch triggered successfully"
    log_info "Response: $response"
}

# Cancel all pending orders
cancel_orders() {
    log_step "Cancelling all pending orders"
    
    if [ "$DRY_RUN" = true ]; then
        log_info "[DRY-RUN] Would cancel all pending orders"
        return 0
    fi
    
    local response
    if ! response=$(curl -s -X POST "$API_ENDPOINT/api/v1/orders/cancel-all" \
        -H "Content-Type: application/json" \
        -d "{\"reason\": \"kill_switch_triggered\"}" 2>/dev/null); then
        log_warning "Failed to cancel orders via API"
        return 1
    fi
    
    log_success "Orders cancelled"
}

# Main function
main() {
    parse_args "$@"
    
    log_info "=============================================="
    log_info "ChiseAI Kill Switch Trigger"
    log_info "Reason: $REASON"
    if [ -n "$PORTFOLIO_ID" ]; then
        log_info "Portfolio: $PORTFOLIO_ID"
    fi
    log_info "=============================================="
    
    if [ "$DRY_RUN" = true ]; then
        log_warning "[DRY-RUN MODE] No actual changes will be made"
    else
        log_warning "⚠️  KILL SWITCH WILL HALT ALL TRADING OPERATIONS"
        log_warning "Press Ctrl+C within 3 seconds to cancel..."
        sleep 3
    fi
    
    # Trigger kill switch
    if ! trigger_kill_switch; then
        log_error "Failed to trigger kill switch"
        exit 1
    fi
    
    # Cancel orders
    cancel_orders
    
    log_success "Kill switch procedures completed"
    log_info "Trading operations are now halted"
}

# Run main function
main "$@"
