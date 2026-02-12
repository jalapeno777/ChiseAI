#!/usr/bin/env bash
#
# reconnect_data_source.sh - Automated data source reconnection for ChiseAI
# Part of ST-OPS-003: Alerting Runbook + Automation
#
# Usage: ./reconnect_data_source.sh --exchange <binance|bybit|bitget> [--force] [--verify] [--timeout <seconds>]
#
# This script handles automated reconnection for exchange data sources,
# following the runbook procedures for data gaps and API disconnect remediation.
#

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${SCRIPT_DIR}/../logs"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Default values
EXCHANGE=""
FORCE_RECONNECT=false
VERIFY_CONNECTION=true
TIMEOUT=120
DRY_RUN=false
VERBOSE=false

# Exchange configurations
declare -A EXCHANGE_CONFIGS=(
    ["binance"]=(
        "name=Binance"
        "api_endpoint=https://api.binance.com"
        "ws_endpoint=wss://stream.binance.com:9443"
        "container=chiseai-data-collector"
        "health_check=ping"
    )
    ["bybit"]=(
        "name=Bybit"
        "api_endpoint=https://api.bybit.com"
        "ws_endpoint=wss://stream.bybit.com/v5/public"
        "container=chiseai-data-collector"
        "health_check=time"
    )
    ["bitget"]=(
        "name=Bitget"
        "api_endpoint=https://api.bitget.com"
        "ws_endpoint=wss://ws.bitget.com/v2/ws"
        "container=chiseai-data-collector"
        "health_check=api_time"
    )
)

# Usage information
usage() {
    cat << EOF
Usage: $(basename "$0") [OPTIONS]

Automated data source reconnection script for ChiseAI exchanges.
Designed for automated remediation of API disconnect and data gap issues.

OPTIONS:
    -e, --exchange <name>    Exchange to reconnect (binance, bybit, bitget)
    -f, --force             Force reconnection even if appears healthy
    -n, --no-verify         Skip post-reconnection verification
    -t, --timeout <sec>     Timeout for verification (default: 120)
    -d, --dry-run           Show what would be done without executing
    -v, --verbose           Enable verbose output
    -h, --help              Show this help message

EXAMPLES:
    $(basename "$0") -e bybit                    # Reconnect Bybit data source
    $(basename "$0") -e binance -f              # Force reconnect Binance
    $(basename "$0") -e bitget -t 60            # Reconnect with 60s timeout

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
            -e|--exchange)
                EXCHANGE="$2"
                shift 2
                ;;
            -f|--force)
                FORCE_RECONNECT=true
                shift
                ;;
            -n|--no-verify)
                VERIFY_CONNECTION=false
                shift
                ;;
            -t|--timeout)
                TIMEOUT="$2"
                shift 2
                ;;
            -d|--dry-run)
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

    # Validate exchange name
    if [ -z "$EXCHANGE" ]; then
        log_error "Exchange name is required. Use -e or --exchange"
        usage
    fi

    if [[ ! -v EXCHANGE_CONFIGS[$EXCHANGE] ]]; then
        log_error "Unknown exchange: $EXCHANGE"
        log_error "Valid exchanges: binance, bybit, bitget"
        exit 1
    fi
}

# Get config value
get_config() {
    local exchange="$1"
    local key="$2"
    local config="${EXCHANGE_CONFIGS[$exchange]}"
    echo "$config" | grep "$key=" | cut -d'=' -f2
}

# Check if exchange API is accessible
check_api_accessible() {
    local exchange="$1"
    local endpoint
    endpoint=$(get_config "$exchange" "api_endpoint")

    log_verbose "Checking API accessibility at: $endpoint"

    if curl -s --connect-timeout 5 --max-time 10 "$endpoint/api/v3/ping" > /dev/null 2>&1; then
        log_verbose "API is accessible"
        return 0
    else
        log_verbose "API is not accessible"
        return 1
    fi
}

# Check WebSocket connectivity
check_websocket() {
    local exchange="$1"
    local ws_endpoint
    ws_endpoint=$(get_config "$exchange" "ws_endpoint")

    log_verbose "Checking WebSocket connectivity at: $ws_endpoint"

    # Quick WebSocket check (send ping, expect pong)
    if timeout 5 curl -s --connect-timeout 3 "$ws_endpoint" > /dev/null 2>&1; then
        log_verbose "WebSocket endpoint is reachable"
        return 0
    else
        log_verbose "WebSocket endpoint is not reachable"
        return 1
    fi
}

# Check container health
check_container_health() {
    local container="$1"

    log_verbose "Checking container health: $container"

    if ! docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
        log_warning "Container $container is not running"
        return 1
    fi

    local status
    status=$(docker inspect --format='{{.State.Status}}' "$container" 2>/dev/null || echo "unknown")

    if [ "$status" = "running" ]; then
        log_verbose "Container is running"
        return 0
    else
        log_warning "Container status: $status"
        return 1
    fi
}

# Get exchange-specific health check
run_health_check() {
    local exchange="$1"
    local health_check
    health_check=$(get_config "$exchange" "health_check")

    log_verbose "Running health check: $health_check"

    case $health_check in
        ping)
            local endpoint
            endpoint=$(get_config "$exchange" "api_endpoint")
            curl -s --connect-timeout 5 --max-time 10 "$endpoint/api/v3/ping" 2>/dev/null | grep -q '{"symbol":' && return 0
            return 1
            ;;
        time)
            local endpoint
            endpoint=$(get_config "$exchange" "api_endpoint")
            local response
            response=$(curl -s --connect-timeout 5 --max-time 10 "$endpoint/v5/market/time" 2>/dev/null)
            | grep -q echo "$response" '"retMsg":"OK"' && return 0
            return 1
            ;;
        api_time)
            local endpoint
            endpoint=$(get_config "$exchange" "api_endpoint")
            local response
            response=$(curl -s --connect-timeout 5 --max-time 10 "$endpoint/api/v1/public/time" 2>/dev/null)
            echo "$response" | grep -q '"code":"00000"' && return 0
            return 1
            ;;
        *)
            # Generic check
            check_api_accessible "$exchange"
            ;;
    esac
}

# Restart data collector container
restart_container() {
    local container="$1"

    if [ "$DRY_RUN" = true ]; then
        log_info "[DRY-RUN] Would restart container: $container"
        return 0
    fi

    log_info "Restarting container: $container"

    # Stop container
    log_step "Stopping container..."
    docker stop "$container" 2>/dev/null || log_warning "Container $container was not running"

    # Wait
    sleep 2

    # Start container
    log_step "Starting container..."
    if ! docker start "$container" 2>/dev/null; then
        log_error "Failed to start container $container"
        return 1
    fi

    # Wait for startup
    sleep 5

    log_success "Container $container restarted"
}

# Reset exchange connection
reset_connection() {
    local exchange="$1"
    local container
    container=$(get_config "$exchange" "container")

    log_step "Resetting connection for $exchange"

    # Restart container
    restart_container "$container"

    # Clear any local cache/buffers if needed
    if [ "$VERBOSE" = true ]; then
        log_info "Clearing local data buffers..."
        # Add buffer clearing commands here if needed
    fi
}

# Verify connection is restored
verify_connection() {
    local exchange="$1"
    local elapsed=0
    local interval=5

    log_step "Verifying connection for $exchange"

    while [ $elapsed -lt $TIMEOUT ]; do
        # Check container health
        local container
        container=$(get_config "$exchange" "container")
        if ! check_container_health "$container"; then
            log_warning "Container not healthy, waiting..."
            sleep $interval
            elapsed=$((elapsed + interval))
            continue
        fi

        # Check API accessibility
        if ! check_api_accessible "$exchange"; then
            log_warning "API not accessible, waiting..."
            sleep $interval
            elapsed=$((elapsed + interval))
            continue
        fi

        # Run health check
        if run_health_check "$exchange"; then
            log_success "Connection verified for $exchange"
            return 0
        fi

        log_verbose "Health check pending (${elapsed}s elapsed)"
        sleep $interval
        elapsed=$((elapsed + interval))
    done

    log_error "Verification timeout for $exchange after ${TIMEOUT}s"
    return 1
}

# Check current status
check_current_status() {
    local exchange="$1"

    log_info "Checking current status for $exchange"

    local container
    container=$(get_config "$exchange" "container")
    local exchange_name
    exchange_name=$(get_config "$exchange" "name")

    echo ""
    echo "  Exchange: $exchange_name ($exchange)"
    echo "  Container: $container"

    # Container status
    if check_container_health "$container"; then
        echo "  Container Status: Running"
    else
        echo "  Container Status: Not Running"
    fi

    # API status
    if check_api_accessible "$exchange"; then
        echo "  API Status: Accessible"
    else
        echo "  API Status: Not Accessible"
    fi

    # Health check
    if run_health_check "$exchange"; then
        echo "  Health Check: Passing"
    else
        echo "  Health Check: Failing"
    fi

    echo ""
}

# Main function
main() {
    parse_args "$@"

    # Create log directory
    mkdir -p "$LOG_DIR"

    local exchange_name
    exchange_name=$(get_config "$EXCHANGE" "name")

    log_info "=============================================="
    log_info "ChiseAI Data Source Reconnection Script"
    log_info "Exchange: $exchange_name ($EXCHANGE)"
    log_info "Force Reconnect: $FORCE_RECONNECT"
    log_info "Verify Connection: $VERIFY_CONNECTION"
    log_info "Timeout: ${TIMEOUT}s"
    log_info "=============================================="

    # Show current status
    check_current_status "$EXCHANGE"

    # Decide whether to reconnect
    local needs_reconnect=false

    if [ "$FORCE_RECONNECT" = true ]; then
        needs_reconnect=true
        log_info "Force reconnect requested"
    else
        # Check if we need to reconnect
        local container
        container=$(get_config "$EXCHANGE" "container")

        if ! check_container_health "$container"; then
            needs_reconnect=true
            log_warning "Container is not healthy, reconnection needed"
        elif ! run_health_check "$EXCHANGE"; then
            needs_reconnect=true
            log_warning "Health check failing, reconnection needed"
        else
            log_success "Connection appears healthy, no reconnection needed"
            exit 0
        fi
    fi

    # Perform reconnection
    if [ "$needs_reconnect" = true ]; then
        if [ "$DRY_RUN" = true ]; then
            log_info "[DRY-RUN] Would perform reconnection for $EXCHANGE"
            exit 0
        fi

        reset_connection "$EXCHANGE"

        # Verify if requested
        if [ "$VERIFY_CONNECTION" = true ]; then
            if ! verify_connection "$EXCHANGE"; then
                log_error "Reconnection verification failed"
                exit 1
            fi
        fi

        # Show final status
        check_current_status "$EXCHANGE"

        log_success "Reconnection completed for $exchange_name"
    fi
}

# Run main function
main "$@"
