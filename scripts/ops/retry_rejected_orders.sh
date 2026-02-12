#!/usr/bin/env bash
#
# retry_rejected_orders.sh - Automated retry for rejected trading orders
# Part of ST-OPS-003: Alerting Runbook + Automation
#
# Usage: ./retry_rejected_orders.sh [--max_attempts <num>] [--backoff <seconds>] [--symbol <symbol>] [--dry_run]
#
# This script handles automated retry for rejected orders,
# following the runbook procedures for order rejection remediation.
#

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"
LOG_DIR="${SCRIPT_DIR}/../logs"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
MAX_ATTEMPTS="${MAX_ATTEMPTS:-3}"
BACKOFF_SECONDS="${BACKOFF_SECONDS:-60}"
SYMBOL=""
STATUS_FILTER="rejected"
DRY_RUN=false
VERBOSE=false

# Rejection reasons that can be retried
declare -A RETRYABLE_REASONS=(
    ["TIMEOUT"]=true
    ["NETWORK_ERROR"]=true
    ["RATE_LIMIT"]=true
    ["TEMPORARY_UNAVAILABLE"]=true
    ["INSUFFICIENT_FUNDS"]=false  # Need to handle differently
    ["RISK_CHECK_FAILED"]=false  # Need manual intervention
    ["BELOW_MIN_ORDER_SIZE"]=true
    ["INVALID_PRICE"]=true
)

# Usage information
usage() {
    cat << EOF
Usage: $(basename "$0") [OPTIONS]

Automated order retry script for ChiseAI trading system.
Designed for automated remediation of order rejection issues.

OPTIONS:
    -m, --max_attempts <num>   Maximum retry attempts (default: 3)
    -b, --backoff <sec>       Backoff time between retries (default: 60s)
    -s, --symbol <symbol>     Filter by symbol (e.g., BTCUSDT)
    -f, --filter <status>     Filter by order status (default: rejected)
    -n, --dry_run             Show what would be done without executing
    -v, --verbose             Enable verbose output
    -h, --help               Show this help message

ENVIRONMENT VARIABLES:
    API_BASE_URL              API base URL (default: http://localhost:8000)

EXAMPLES:
    $(basename "$0")                           # Retry all rejected orders
    $(basename "$0") -m 5 -b 120              # Retry up to 5 times with 2min backoff
    $(basename "$0") -s BTCUSDT                # Retry only BTCUSDT orders
    $(basename "$0") -n                        # Dry run to see what would be retried

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

log_order() {
    echo -e "${CYAN}[ORDER]${NC} $*"
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
            -m|--max_attempts)
                MAX_ATTEMPTS="$2"
                shift 2
                ;;
            -b|--backoff)
                BACKOFF_SECONDS="$2"
                shift 2
                ;;
            -s|--symbol)
                SYMBOL="$2"
                shift 2
                ;;
            -f|--filter)
                STATUS_FILTER="$2"
                shift 2
                ;;
            -n|--dry_run)
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
}

# Validate retryable reason
is_retryable() {
    local reason="$1"

    # Normalize reason
    reason=$(echo "$reason" | tr '[:lower:]' '[:upper:]')

    # Check if retryable
    if [[ -v RETRYABLE_REASONS[$reason] ]]; then
        if [ "${RETRYABLE_REASONS[$reason]}" = "true" ]; then
            return 0
        else
            return 1
        fi
    fi

    # Default: retry unknown reasons
    log_verbose "Unknown rejection reason: $reason, will retry"
    return 0
}

# Get rejected orders from API
get_rejected_orders() {
    local url="${API_BASE_URL}/api/v1/orders?status=${STATUS_FILTER}"

    if [ -n "$SYMBOL" ]; then
        url="${url}&symbol=${SYMBOL}"
    fi

    log_verbose "Fetching orders from: $url"

    local response
    response=$(curl -s --connect-timeout 10 --max-time 30 "$url" 2>/dev/null)

    if [ -z "$response" ]; then
        log_error "Failed to fetch orders from API"
        return 1
    fi

    echo "$response"
}

# Parse orders from response
parse_orders() {
    local response="$1"
    local orders_json="$response"

    # Check if jq is available
    if ! command -v jq &> /dev/null; then
        log_error "jq is required but not installed"
        return 1
    fi

    # Parse orders (output as JSON array)
    echo "$orders_json" | jq -c '.orders[]?'
}

# Get order details
get_order_details() {
    local order_id="$1"

    local url="${API_BASE_URL}/api/v1/orders/${order_id}"

    local response
    response=$(curl -s --connect-timeout 10 --max-time 30 "$url" 2>/dev/null)

    if [ -z "$response" ]; then
        log_error "Failed to fetch order details for: $order_id"
        return 1
    fi

    echo "$response"
}

# Cancel an order
cancel_order() {
    local order_id="$1"

    if [ "$DRY_RUN" = true ]; then
        log_info "[DRY-RUN] Would cancel order: $order_id"
        return 0
    fi

    log_info "Cancelling order: $order_id"

    local url="${API_BASE_URL}/api/v1/orders/${order_id}"
    local response
    response=$(curl -s -X DELETE --connect-timeout 10 --max-time 30 "$url" 2>/dev/null)

    if echo "$response" | jq -e '.status == "cancelled"' > /dev/null 2>&1; then
        log_success "Order cancelled: $order_id"
        return 0
    else
        log_warning "Failed to cancel order: $order_id"
        log_verbose "Response: $response"
        return 1
    fi
}

# Retry an order
retry_order() {
    local order_id="$1"

    if [ "$DRY_RUN" = true ]; then
        log_info "[DRY-RUN] Would retry order: $order_id"
        return 0
    fi

    log_info "Retrying order: $order_id"

    local url="${API_BASE_URL}/api/v1/orders/${order_id}/retry"
    local response
    response=$(curl -s -X POST --connect-timeout 10 --max-time 60 "$url" 2>/dev/null)

    if echo "$response" | jq -e '.status == "submitted" or .status == "filled"' > /dev/null 2>&1; then
        log_success "Order retry submitted: $order_id"
        return 0
    else
        log_warning "Failed to retry order: $order_id"
        log_verbose "Response: $response"
        return 1
    fi
}

# Get order status from details
get_order_status() {
    local order_json="$1"
    echo "$order_json" | jq -r '.status // "unknown"'
}

# Get rejection reason from order
get_rejection_reason() {
    local order_json="$1"
    echo "$order_json" | jq -r '.rejection_reason // "UNKNOWN"'
}

# Get attempt count from order
get_attempt_count() {
    local order_json="$1"
    echo "$order_json" | jq -r '.retry_count // 0'
}

# Get symbol from order
get_order_symbol() {
    local order_json="$1"
    echo "$order_json" | jq -r '.symbol // "UNKNOWN"'
}

# Get order ID from order
get_order_id() {
    local order_json="$1"
    echo "$order_json" | jq -r '.order_id // "unknown"'
}

# Process a single order
process_order() {
    local order_json="$1"

    local order_id
    order_id=$(get_order_id "$order_json")

    local symbol
    symbol=$(get_order_symbol "$order_json")

    local status
    status=$(get_order_status "$order_json")

    local reason
    reason=$(get_rejection_reason "$order_json")

    local attempts
    attempts=$(get_attempt_count "$order_json")

    log_order "Processing order: $order_id ($symbol) - Status: $status - Reason: $reason (attempt: $attempts)"

    # Check if already retried too many times
    if [ "$attempts" -ge "$MAX_ATTEMPTS" ]; then
        log_warning "Order $order_id has exceeded max attempts ($MAX_ATTEMPTS), skipping"
        return 0
    fi

    # Check if retryable
    if ! is_retryable "$reason"; then
        case "$reason" in
            "INSUFFICIENT_FUNDS")
                log_warning "Order $order_id requires manual intervention (insufficient funds)"
                log_info "Suggested action: Cancel order and resubmit with adjusted quantity"
                ;;
            "RISK_CHECK_FAILED")
                log_warning "Order $order_id requires risk system review"
                log_info "Suggested action: Review risk limits and adjust order parameters"
                ;;
            *)
                log_warning "Order $order_id has non-retryable reason: $reason"
                ;;
        esac
        return 0
    fi

    # Cancel the rejected order first
    cancel_order "$order_id"

    # Wait for backoff
    log_info "Waiting ${BACKOFF_SECONDS}s before retry..."
    sleep "$BACKOFF_SECONDS"

    # Retry the order
    retry_order "$order_id"

    return 0
}

# Process all orders
process_all_orders() {
    local response
    response=$(get_rejected_orders)

    if [ -z "$response" ] || [ "$response" = "null" ]; then
        log_info "No rejected orders found"
        return 0
    fi

    local order_count
    order_count=$(echo "$response" | jq '.orders | length' 2>/dev/null || echo "0")

    if [ "$order_count" -eq 0 ]; then
        log_info "No rejected orders found"
        return 0
    fi

    log_info "Found $order_count rejected order(s)"

    # Process each order
    local success_count=0
    local fail_count=0

    while IFS= read -r order_json; do
        if [ -z "$order_json" ]; then
            continue
        fi

        # Check symbol filter
        local order_symbol
        order_symbol=$(get_order_symbol "$order_json")

        if [ -n "$SYMBOL" ] && [ "$order_symbol" != "$SYMBOL" ]; then
            log_verbose "Skipping order $order_symbol (filter: $SYMBOL)"
            continue
        fi

        # Process order
        if process_order "$order_json"; then
            success_count=$((success_count + 1))
        else
            fail_count=$((fail_count + 1))
        fi

        # Wait between orders
        sleep 2

    done < <(parse_orders "$response")

    # Summary
    log_info "=============================================="
    log_info "Order Retry Summary"
    log_info "Total processed: $((success_count + fail_count))"
    log_info "Successful: $success_count"
    log_info "Failed: $fail_count"
    log_info "=============================================="
}

# Main function
main() {
    parse_args "$@"

    # Create log directory
    mkdir -p "$LOG_DIR"

    log_info "=============================================="
    log_info "ChiseAI Order Retry Script"
    log_info "Max Attempts: $MAX_ATTEMPTS"
    log_info "Backoff: ${BACKOFF_SECONDS}s"
    log_info "Symbol Filter: ${SYMBOL:-all}"
    log_info "Status Filter: $STATUS_FILTER"
    log_info "Dry Run: $DRY_RUN"
    log_info "=============================================="

    # Process orders
    process_all_orders

    log_success "Order retry process completed"
}

# Run main function
main "$@"
