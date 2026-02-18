#!/usr/bin/env bash
#
# reconnect_redis.sh - Automated Redis reconnection for ChiseAI
# Part of PAPER-003-005: Executable Runbook Framework
#
# Usage: ./reconnect_redis.sh [--force] [--dry-run] [--timeout <seconds>]
#
# This script handles automated reconnection for Redis failures,
# following the runbook procedures for Redis failure response.
#

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${SCRIPT_DIR}/../../logs"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Default values
FORCE_RECONNECT=false
TIMEOUT=60
DRY_RUN=false
VERBOSE=false

# Usage information
usage() {
    cat << EOF
Usage: $(basename "$0") [OPTIONS]

Automated Redis reconnection script for ChiseAI.
Designed for automated remediation of Redis connectivity issues.

OPTIONS:
    -f, --force             Force reconnection even if appears healthy
    -t, --timeout <sec>     Timeout for verification (default: 60)
    -d, --dry-run           Show what would be done without executing
    -v, --verbose           Enable verbose output
    -h, --help              Show this help message

EXAMPLES:
    $(basename "$0")                             # Check and reconnect if needed
    $(basename "$0") -f                          # Force reconnection
    $(basename "$0") -t 120                      # Reconnect with 2min timeout

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
            -f|--force)
                FORCE_RECONNECT=true
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
}

# Check if Redis container is running
check_container() {
    log_verbose "Checking Redis container status"
    
    if docker ps --format '{{.Names}}' | grep -q "^chiseai-redis$"; then
        log_verbose "Redis container is running"
        return 0
    else
        log_verbose "Redis container is not running"
        return 1
    fi
}

# Test Redis connectivity
test_connectivity() {
    log_verbose "Testing Redis connectivity"
    
    if redis-cli -p 6380 PING 2>/dev/null | grep -q "PONG"; then
        log_verbose "Redis connectivity test passed"
        return 0
    else
        log_verbose "Redis connectivity test failed"
        return 1
    fi
}

# Check Redis health
check_health() {
    log_verbose "Checking Redis health"
    
    local elapsed=0
    local interval=2
    
    while [ $elapsed -lt $TIMEOUT ]; do
        if test_connectivity; then
            log_success "Redis is healthy"
            return 0
        fi
        
        log_verbose "Health check pending (${elapsed}s elapsed)"
        sleep $interval
        elapsed=$((elapsed + interval))
    done
    
    log_error "Health check timeout after ${TIMEOUT}s"
    return 1
}

# Restart Redis container
restart_redis() {
    if [ "$DRY_RUN" = true ]; then
        log_info "[DRY-RUN] Would restart Redis container"
        return 0
    fi
    
    log_step "Restarting Redis container"
    
    # Try to save data before restart
    log_info "Attempting to save Redis data..."
    redis-cli -p 6380 BGSAVE 2>/dev/null || log_warning "Could not trigger BGSAVE"
    sleep 2
    
    # Stop container
    log_step "Stopping Redis container..."
    docker stop chiseai-redis 2>/dev/null || log_warning "Container was not running"
    
    # Wait
    sleep 2
    
    # Start container
    log_step "Starting Redis container..."
    if ! docker start chiseai-redis 2>/dev/null; then
        log_error "Failed to start Redis container"
        return 1
    fi
    
    # Wait for startup
    log_info "Waiting for Redis to start..."
    sleep 5
    
    log_success "Redis container restarted"
}

# Main function
main() {
    parse_args "$@"
    
    # Create log directory
    mkdir -p "$LOG_DIR"
    
    log_info "=============================================="
    log_info "ChiseAI Redis Reconnection Script"
    log_info "Force Reconnect: $FORCE_RECONNECT"
    log_info "Timeout: ${TIMEOUT}s"
    log_info "=============================================="
    
    # Check current status
    local container_running=false
    local redis_healthy=false
    
    if check_container; then
        container_running=true
        log_info "Redis container: Running"
    else
        log_warning "Redis container: Not Running"
    fi
    
    if test_connectivity; then
        redis_healthy=true
        log_info "Redis connectivity: OK"
    else
        log_warning "Redis connectivity: Failed"
    fi
    
    # Decide whether to reconnect
    local needs_reconnect=false
    
    if [ "$FORCE_RECONNECT" = true ]; then
        needs_reconnect=true
        log_info "Force reconnect requested"
    elif [ "$container_running" = false ]; then
        needs_reconnect=true
        log_warning "Container not running, reconnection needed"
    elif [ "$redis_healthy" = false ]; then
        needs_reconnect=true
        log_warning "Redis not healthy, reconnection needed"
    else
        log_success "Redis appears healthy, no reconnection needed"
        exit 0
    fi
    
    # Perform reconnection
    if [ "$needs_reconnect" = true ]; then
        if [ "$DRY_RUN" = true ]; then
            log_info "[DRY-RUN] Would perform Redis reconnection"
            exit 0
        fi
        
        restart_redis
        
        # Verify reconnection
        if ! check_health; then
            log_error "Reconnection verification failed"
            exit 1
        fi
        
        log_success "Redis reconnection completed successfully"
    fi
}

# Run main function
main "$@"
