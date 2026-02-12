#!/usr/bin/env bash
#
# restart_api.sh - Automated API restart for ChiseAI services
# Part of ST-OPS-003: Alerting Runbook + Automation
#
# Usage: ./restart_api.sh [--service <service_name>] [--force] [--timeout <seconds>]
#
# This script handles automated restarts for API disconnection issues,
# following the runbook procedures for API disconnect remediation.
#

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/../config/ops_config.yaml"
LOG_DIR="${SCRIPT_DIR}/../logs"
HEALTH_ENDPOINT="${HEALTH_ENDPOINT:-http://localhost:8000/health}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
SERVICE_NAME=""
FORCE_RESTART=false
TIMEOUT=60
DRY_RUN=false
VERBOSE=false

# Services that can be restarted
declare -A SERVICES=(
    ["api"]="chiseai-api"
    ["data-collector"]="chiseai-data-collector"
    ["trading-bot"]="chiseai-trading-bot"
    ["feature-engine"]="chiseai-feature-engine"
    ["all"]="all"
)

# Usage information
usage() {
    cat << EOF
Usage: $(basename "$0") [OPTIONS]

Automated API restart script for ChiseAI services.
Designed for automated remediation of API disconnection issues.

OPTIONS:
    -s, --service <name>    Service to restart (api, data-collector, trading-bot, feature-engine, all)
    -f, --force            Force restart even if healthy
    -t, --timeout <sec>    Timeout for health check (default: 60)
    -n, --dry-run          Show what would be done without executing
    -v, --verbose          Enable verbose output
    -h, --help             Show this help message

EXAMPLES:
    $(basename "$0") -s api                          # Restart API service
    $(basename "$0") -s all -f                       # Force restart all services
    $(basename "$0") -s data-collector -t 120        # Restart with 2min timeout

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

# Verbose logging
log_verbose() {
    if [ "$VERBOSE" = true ]; then
        echo -e "[DEBUG] $(date '+%Y-%m-%d %H:%M:%S') $*"
    fi
}

# Parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            -s|--service)
                SERVICE_NAME="$2"
                shift 2
                ;;
            -f|--force)
                FORCE_RESTART=true
                shift
                ;;
            -t|--timeout)
                TIMEOUT="$2"
                shift 2
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

    # Validate service name
    if [ -z "$SERVICE_NAME" ]; then
        log_error "Service name is required. Use -s or --service"
        usage
    fi

    if [[ ! -v SERVICES[$SERVICE_NAME] ]]; then
        log_error "Unknown service: $SERVICE_NAME"
        log_error "Valid services: api, data-collector, trading-bot, feature-engine, all"
        exit 1
    fi
}

# Check if service exists
check_service_exists() {
    local service="$1"
    if [ "$service" = "all" ]; then
        return 0
    fi

    if docker ps --format '{{.Names}}' | grep -q "^${SERVICES[$service]}$"; then
        return 0
    else
        return 1
    fi
}

# Get service status
get_service_status() {
    local service="$1"
    local container_name="${SERVICES[$service]}"

    if ! check_service_exists "$service"; then
        echo "not_found"
        return 1
    fi

    local status
    status=$(docker inspect --format='{{.State.Status}}' "$container_name" 2>/dev/null || echo "unknown")

    case $status in
        running)
            echo "running"
            ;;
        exited)
            echo "stopped"
            ;;
        created)
            echo "created"
            ;;
        *)
            echo "unknown"
            ;;
    esac
}

# Check service health
check_health() {
    local service="$1"
    local container_name="${SERVICES[$service]}"
    local elapsed=0
    local interval=2

    log_verbose "Checking health for $service (container: $container_name)"

    while [ $elapsed -lt $TIMEOUT ]; do
        # Check if container is running
        if ! docker ps --format '{{.Names}}' | grep -q "^${container_name}$"; then
            log_warning "Container $container_name is not running"
            sleep $interval
            elapsed=$((elapsed + interval))
            continue
        fi

        # Try to check health via container health check or API
        local health_status
        health_status=$(docker inspect --format='{{.State.Health.Status}}' "$container_name" 2>/dev/null || echo "none")

        if [ "$health_status" = "healthy" ]; then
            log_success "$service is healthy"
            return 0
        fi

        # If no health check, use container status
        local container_status
        container_status=$(docker inspect --format='{{.State.Status}}' "$container_name" 2>/dev/null || echo "unknown")

        if [ "$container_status" = "running" ]; then
            log_success "$service is running"
            return 0
        fi

        log_verbose "Health check: $health_status, Status: $container_status (${elapsed}s elapsed)"
        sleep $interval
        elapsed=$((elapsed + interval))
    done

    log_error "Health check timeout for $service after ${TIMEOUT}s"
    return 1
}

# Stop service
stop_service() {
    local service="$1"
    local container_name="${SERVICES[$service]}"

    if [ "$DRY_RUN" = true ]; then
        log_info "[DRY-RUN] Would stop container: $container_name"
        return 0
    fi

    log_info "Stopping service: $service (container: $container_name)"

    if ! docker stop "$container_name" 2>/dev/null; then
        log_warning "Failed to stop $container_name (may not be running)"
    fi

    log_success "Service $service stopped"
}

# Start service
start_service() {
    local service="$1"
    local container_name="${SERVICES[$service]}"

    if [ "$DRY_RUN" = true ]; then
        log_info "[DRY-RUN] Would start container: $container_name"
        return 0
    fi

    log_info "Starting service: $service (container: $container_name)"

    if ! docker start "$container_name" 2>/dev/null; then
        log_error "Failed to start $container_name"
        return 1
    fi

    log_success "Service $service started"
}

# Restart service
restart_service() {
    local service="$1"

    log_info "Restarting service: $service"

    # Stop first
    if ! stop_service "$service"; then
        log_warning "Stop failed for $service, attempting start anyway"
    fi

    # Wait briefly
    sleep 2

    # Start
    if ! start_service "$service"; then
        log_error "Failed to restart $service"
        return 1
    fi

    # Wait for startup
    sleep 5

    # Check health
    if ! check_health "$service"; then
        log_warning "$service may not be fully healthy"
    fi

    log_success "Service $service restarted successfully"
}

# Get all running services
get_running_services() {
    local running=()

    for service in "${!SERVICES[@]}"; do
        if [ "$service" = "all" ]; then
            continue
        fi

        if check_service_exists "$service"; then
            local status
            status=$(get_service_status "$service")
            if [ "$status" = "running" ]; then
                running+=("$service")
            fi
        fi
    done

    echo "${running[@]}"
}

# Main function
main() {
    parse_args "$@"

    # Create log directory
    mkdir -p "$LOG_DIR"

    log_info "=============================================="
    log_info "ChiseAI Service Restart Script"
    log_info "Service: $SERVICE_NAME"
    log_info "Force Restart: $FORCE_RESTART"
    log_info "Timeout: ${TIMEOUT}s"
    log_info "=============================================="

    # Handle "all" services
    if [ "$SERVICE_NAME" = "all" ]; then
        log_info "Processing all services"

        local running_services
        running_services=$(get_running_services)

        if [ -z "$running_services" ]; then
            log_warning "No running services found"
            exit 0
        fi

        log_info "Running services: ${running_services[*]}"

        for service in $running_services; do
            if [ "$FORCE_RESTART" = true ] || [ "$(get_service_status "$service")" != "running" ]; then
                restart_service "$service"
            else
                log_info "Skipping $service (already running, force not set)"
            fi
        done
    else
        # Handle single service
        if ! check_service_exists "$SERVICE_NAME"; then
            log_error "Service $SERVICE_NAME not found"
            log_error "Available services: ${!SERVICES[*]}"
            exit 1
        fi

        local current_status
        current_status=$(get_service_status "$SERVICE_NAME")

        log_info "Current status of $SERVICE_NAME: $current_status"

        if [ "$current_status" = "running" ] && [ "$FORCE_RESTART" = false ]; then
            log_info "Service is already running. Use --force to force restart."

            # Still check health
            if check_health "$SERVICE_NAME"; then
                log_success "Service is healthy, no restart needed"
                exit 0
            else
                log_warning "Service may be unhealthy, consider restarting with --force"
                exit 1
            fi
        fi

        restart_service "$SERVICE_NAME"
    fi

    log_success "Restart operation completed"
}

# Run main function
main "$@"
