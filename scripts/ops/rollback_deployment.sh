#!/bin/bash
#
# Deployment Rollback Script
# Performs automatic rollback of deployments based on health degradation
#
# Usage:
#   ./rollback_deployment.sh <deployment_id> [version]
#
# For PAPER-003-004: Event-Driven Self-Healing Automation
#

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
DEPLOYMENT_LOG_DIR="${PROJECT_ROOT}/logs/deployments"
DOCKER_COMPOSE_FILE="${PROJECT_ROOT}/docker-compose.yml"

# Ensure directories exist
mkdir -p "$DEPLOYMENT_LOG_DIR"

# Logging
log_info() {
    echo -e "${GREEN}[$(date -Iseconds)] INFO${NC} $1"
    echo "[$(date -Iseconds)] INFO $1" >> "$DEPLOYMENT_LOG_DIR/rollback.log"
}

log_warn() {
    echo -e "${YELLOW}[$(date -Iseconds)] WARN${NC} $1"
    echo "[$(date -Iseconds)] WARN $1" >> "$DEPLOYMENT_LOG_DIR/rollback.log"
}

log_error() {
    echo -e "${RED}[$(date -Iseconds)] ERROR${NC} $1" >&2
    echo "[$(date -Iseconds)] ERROR $1" >> "$DEPLOYMENT_LOG_DIR/rollback.log"
}

# Show usage
usage() {
    cat << EOF
Deployment Rollback Script

Usage:
    $0 <deployment_id> [version]

Arguments:
    deployment_id    The deployment ID to rollback
    version          (Optional) Target version to rollback to

Examples:
    $0 deploy-2024-01-15-v1.2.3
    $0 deploy-2024-01-15-v1.2.3 v1.2.2

EOF
}

# Get previous version from git
get_previous_version() {
    local current_version="$1"
    
    # Get tag before current
    git tag --sort=-creatordate | grep -A 1 "^${current_version}$" | tail -1 || echo ""
}

# Rollback Docker deployment
rollback_docker() {
    local deployment_id="$1"
    local target_version="$2"
    
    log_info "Rolling back Docker deployment $deployment_id to $target_version"
    
    # Pull previous image
    local image_name="chiseai/api"
    
    log_info "Pulling image: ${image_name}:${target_version}"
    
    if ! docker pull "${image_name}:${target_version}" 2>/dev/null; then
        log_warn "Could not pull image, using local cache"
    fi
    
    # Update docker-compose to use previous version
    log_info "Updating docker-compose configuration"
    
    if [[ -f "$DOCKER_COMPOSE_FILE" ]]; then
        # Backup current compose file
        cp "$DOCKER_COMPOSE_FILE" "${DOCKER_COMPOSE_FILE}.backup.$(date +%s)"
        
        # Update image tag
        sed -i "s|image: ${image_name}:.*|image: ${image_name}:${target_version}|" "$DOCKER_COMPOSE_FILE"
        
        # Restart services
        log_info "Restarting services with previous version"
        if docker-compose -f "$DOCKER_COMPOSE_FILE" up -d --no-deps --build chiseai-api-final 2>/dev/null; then
            log_info "Services restarted successfully"
            return 0
        else
            log_error "Failed to restart services"
            return 1
        fi
    else
        log_error "Docker compose file not found: $DOCKER_COMPOSE_FILE"
        return 1
    fi
}

# Verify rollback
verify_rollback() {
    local deployment_id="$1"
    local target_version="$2"
    
    log_info "Verifying rollback for $deployment_id"
    
    # Wait for services to start
    sleep 10
    
    # Check health endpoint
    local max_attempts=6
    local attempt=1
    
    while [[ $attempt -le $max_attempts ]]; do
        log_info "Health check attempt $attempt/$max_attempts"
        
        if curl -s "http://localhost:8001/health" 2>/dev/null | grep -q "healthy"; then
            log_info "Rollback verified - services healthy"
            return 0
        fi
        
        sleep 5
        attempt=$((attempt + 1))
    done
    
    log_error "Rollback verification failed - services unhealthy"
    return 1
}

# Log rollback to audit
to_audit() {
    local deployment_id="$1"
    local from_version="$2"
    local to_version="$3"
    local status="$4"
    
    local audit_entry
    audit_entry=$(cat << EOF
{
    "timestamp": "$(date -Iseconds)",
    "event": "deployment_rollback",
    "deployment_id": "$deployment_id",
    "from_version": "$from_version",
    "to_version": "$to_version",
    "status": "$status",
    "triggered_by": "self-healing-automation"
}
EOF
)
    
    echo "$audit_entry" >> "$DEPLOYMENT_LOG_DIR/audit.jsonl"
    
    # Also log to InfluxDB if available
    if curl -s "http://localhost:18086/health" >/dev/null 2>&1; then
        local timestamp
        timestamp=$(date +%s)000000000
        curl -s -X POST "http://localhost:18086/write?db=chiseai" \
            --data-binary "rollback,deployment_id=${deployment_id} from_version=\"${from_version}\",to_version=\"${to_version}\",status=\"${status}\" ${timestamp}" \
            >/dev/null 2>&1 || true
    fi
}

# Main rollback function
rollback() {
    local deployment_id="$1"
    local target_version="${2:-}"
    
    log_info "Starting rollback for deployment: $deployment_id"
    
    # Get current version if not specified
    if [[ -z "$target_version" ]]; then
        target_version=$(get_previous_version "$deployment_id")
        if [[ -z "$target_version" ]]; then
            log_error "Could not determine previous version"
            return 1
        fi
        log_info "Auto-detected previous version: $target_version"
    fi
    
    # Perform rollback
    if rollback_docker "$deployment_id" "$target_version"; then
        # Verify rollback
        if verify_rollback "$deployment_id" "$target_version"; then
            log_info "Rollback completed successfully"
            log_to_audit "$deployment_id" "$deployment_id" "$target_version" "success"
            
            # Send notification
            send_notification "$deployment_id" "$target_version" "success"
            
            return 0
        else
            log_error "Rollback verification failed"
            log_to_audit "$deployment_id" "$deployment_id" "$target_version" "verification_failed"
            return 1
        fi
    else
        log_error "Rollback failed"
        log_to_audit "$deployment_id" "$deployment_id" "$target_version" "failed"
        return 1
    fi
}

# Send notification
send_notification() {
    local deployment_id="$1"
    local target_version="$2"
    local status="$3"
    
    local message="Deployment rollback completed: ${deployment_id} -> ${target_version} (${status})"
    
    # Discord webhook
    if [[ -n "${DISCORD_WEBHOOK_URL:-}" ]]; then
        curl -s -X POST "$DISCORD_WEBHOOK_URL" \
            -H "Content-Type: application/json" \
            -d "{
                \"content\": \"🔄 ${message}\",
                \"embeds\": [{
                    \"title\": \"Deployment Rollback\",
                    \"description\": \"Automated rollback completed\",
                    \"color\": ${status == "success" ? 3066993 : 15158332},
                    \"fields\": [
                        {\"name\": \"Deployment\", \"value\": \"${deployment_id}\", \"inline\": true},
                        {\"name\": \"Version\", \"value\": \"${target_version}\", \"inline\": true},
                        {\"name\": \"Status\", \"value\": \"${status}\", \"inline\": true}
                    ],
                    \"timestamp\": \"$(date -Iseconds)\"
                }]
            }" >/dev/null 2>&1 || true
    fi
}

# Main
main() {
    if [[ $# -lt 1 ]]; then
        usage
        exit 1
    fi
    
    local deployment_id="$1"
    local target_version="${2:-}"
    
    rollback "$deployment_id" "$target_version"
}

main "$@"
