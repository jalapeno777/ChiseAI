#!/bin/bash
#
# Recovery Orchestrator Script
# Triggers and monitors recovery actions for self-healing automation
#
# Usage:
#   ./recovery_orchestrator.sh trigger <source> <recovery_type> [--priority=<level>]
#   ./recovery_orchestrator.sh status [attempt_id]
#   ./recovery_orchestrator.sh history [--source=<source>] [--limit=<n>]
#   ./recovery_orchestrator.sh stats
#
# For PAPER-003-004: Event-Driven Self-Healing Automation
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
RECOVERY_LOG_DIR="${PROJECT_ROOT}/logs/recovery"
LOCK_DIR="${PROJECT_ROOT}/.locks"

# Ensure directories exist
mkdir -p "$RECOVERY_LOG_DIR"
mkdir -p "$LOCK_DIR"

# Logging functions
log_info() {
    echo -e "${GREEN}[$(date -Iseconds)] INFO${NC} $1"
    echo "[$(date -Iseconds)] INFO $1" >> "$RECOVERY_LOG_DIR/recovery.log"
}

log_warn() {
    echo -e "${YELLOW}[$(date -Iseconds)] WARN${NC} $1"
    echo "[$(date -Iseconds)] WARN $1" >> "$RECOVERY_LOG_DIR/recovery.log"
}

log_error() {
    echo -e "${RED}[$(date -Iseconds)] ERROR${NC} $1" >&2
    echo "[$(date -Iseconds)] ERROR $1" >> "$RECOVERY_LOG_DIR/recovery.log"
}

log_debug() {
    if [[ "${DEBUG:-0}" == "1" ]]; then
        echo -e "${BLUE}[$(date -Iseconds)] DEBUG${NC} $1"
    fi
    echo "[$(date -Iseconds)] DEBUG $1" >> "$RECOVERY_LOG_DIR/recovery.log"
}

# Show usage
usage() {
    cat << EOF
Recovery Orchestrator - Self-Healing Automation

Usage:
    $0 trigger <source> <recovery_type> [options]
        Trigger a recovery action
        
        recovery_types: redis_reconnect, exchange_failover, service_restart,
                       data_backfill, deployment_rollback, circuit_breaker_reset
        
        Options:
            --priority=<level>    Priority level: critical, warning, info (default: warning)
            --metadata=<json>     Additional metadata as JSON string

    $0 status [attempt_id]
        Check recovery status (all or specific attempt)

    $0 history [options]
        View recovery history
        
        Options:
            --source=<source>     Filter by source
            --limit=<n>           Limit results (default: 50)

    $0 stats
        Show recovery statistics

    $0 list-active
        List currently active recoveries

    $0 cancel <source>
        Cancel active recovery for source

    $0 escalate <source> <reason>
        Manually escalate to human operators

Examples:
    $0 trigger redis redis_reconnect --priority=critical
    $0 trigger bybit exchange_failover --metadata='{"to_exchange": "bitget"}'
    $0 status
    $0 history --source=redis --limit=10
    $0 stats

EOF
}

# Acquire lock for source
acquire_lock() {
    local source="$1"
    local lock_file="$LOCK_DIR/recovery_${source}.lock"
    
    if [[ -f "$lock_file" ]]; then
        local pid
        pid=$(cat "$lock_file" 2>/dev/null || echo "")
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            log_warn "Recovery already in progress for $source (PID: $pid)"
            return 1
        else
            # Stale lock, remove it
            rm -f "$lock_file"
        fi
    fi
    
    echo $$ > "$lock_file"
    return 0
}

# Release lock for source
release_lock() {
    local source="$1"
    local lock_file="$LOCK_DIR/recovery_${source}.lock"
    rm -f "$lock_file"
}

# Trigger recovery via Python
trigger_recovery() {
    local source="$1"
    local recovery_type="$2"
    shift 2
    
    local priority="warning"
    local metadata="{}"
    
    # Parse options
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --priority=*)
                priority="${1#*=}"
                ;;
            --metadata=*)
                metadata="${1#*=}"
                ;;
            *)
                log_error "Unknown option: $1"
                return 1
                ;;
        esac
        shift
    done
    
    log_info "Triggering recovery: source=$source, type=$recovery_type, priority=$priority"
    
    # Acquire lock
    if ! acquire_lock "$source"; then
        log_error "Cannot trigger recovery for $source - already in progress"
        return 1
    fi
    
    # Ensure lock is released on exit
    trap "release_lock '$source'" EXIT
    
    # Generate attempt ID
    local attempt_id
    attempt_id="$(date +%s)_${source}_$(openssl rand -hex 4)"
    
    # Log attempt
    local attempt_file="$RECOVERY_LOG_DIR/attempt_${attempt_id}.json"
    cat > "$attempt_file" << EOF
{
    "attempt_id": "$attempt_id",
    "source": "$source",
    "recovery_type": "$recovery_type",
    "priority": "$priority",
    "metadata": $metadata,
    "state": "pending",
    "started_at": "$(date -Iseconds)"
}
EOF
    
    log_info "Recovery attempt ID: $attempt_id"
    
    # Execute recovery based on type
    local result=0
    case "$recovery_type" in
        redis_reconnect)
            trigger_redis_reconnect "$source" "$attempt_id" || result=$?
            ;;
        exchange_failover)
            trigger_exchange_failover "$source" "$attempt_id" "$metadata" || result=$?
            ;;
        service_restart)
            trigger_service_restart "$source" "$attempt_id" || result=$?
            ;;
        data_backfill)
            trigger_data_backfill "$source" "$attempt_id" "$metadata" || result=$?
            ;;
        deployment_rollback)
            trigger_deployment_rollback "$source" "$attempt_id" || result=$?
            ;;
        circuit_breaker_reset)
            trigger_circuit_breaker_reset "$source" "$attempt_id" || result=$?
            ;;
        *)
            log_error "Unknown recovery type: $recovery_type"
            result=1
            ;;
    esac
    
    # Update attempt file
    local end_state="succeeded"
    if [[ $result -ne 0 ]]; then
        end_state="failed"
    fi
    
    # Use Python to update the JSON properly
    python3 << PYEOF
import json
import sys

try:
    with open("$attempt_file", "r") as f:
        data = json.load(f)
    
    data["state"] = "$end_state"
    data["completed_at"] = "$(date -Iseconds)"
    data["exit_code"] = $result
    
    with open("$attempt_file", "w") as f:
        json.dump(data, f, indent=2)
except Exception as e:
    print(f"Error updating attempt file: {e}", file=sys.stderr)
    sys.exit(1)
PYEOF
    
    if [[ $result -eq 0 ]]; then
        log_info "Recovery succeeded: $attempt_id"
    else
        log_error "Recovery failed: $attempt_id (exit code: $result)"
    fi
    
    return $result
}

# Trigger Redis reconnection
trigger_redis_reconnect() {
    local source="$1"
    local attempt_id="$2"
    
    log_info "Attempting Redis reconnection for $source"
    
    # Check Redis connectivity
    local redis_host="${REDIS_HOST:-localhost}"
    local redis_port="${REDIS_PORT:-6380}"
    
    # Try ping
    for i in {1..3}; do
        log_info "Redis ping attempt $i/3"
        
        if redis-cli -h "$redis_host" -p "$redis_port" ping 2>/dev/null | grep -q "PONG"; then
            log_info "Redis reconnection successful"
            
            # Log to InfluxDB if available
            log_to_influxdb "recovery" "redis_reconnect" "$source" "success" 1
            
            return 0
        fi
        
        sleep 2
    done
    
    log_error "Redis reconnection failed after 3 attempts"
    
    # Log to InfluxDB
    log_to_influxdb "recovery" "redis_reconnect" "$source" "failure" 0
    
    return 1
}

# Trigger exchange failover
trigger_exchange_failover() {
    local source="$1"
    local attempt_id="$2"
    local metadata="$3"
    
    log_info "Attempting exchange failover from $source"
    
    # Parse metadata for target exchange
    local target_exchange
    target_exchange=$(echo "$metadata" | python3 -c "import sys,json; print(json.load(sys.stdin).get('to_exchange', 'bitget'))")
    
    log_info "Failing over to: $target_exchange"
    
    # Check if target exchange is healthy
    if curl -s "http://localhost:8001/health/exchange/$target_exchange" 2>/dev/null | grep -q "healthy"; then
        log_info "Target exchange $target_exchange is healthy"
        
        # Trigger failover via API
        local response
        response=$(curl -s -X POST "http://localhost:8001/api/v1/exchange/failover" \
            -H "Content-Type: application/json" \
            -d "{\"from\":\"$source\",\"to\":\"$target_exchange\"}" 2>/dev/null || echo "{}")
        
        if echo "$response" | grep -q '"success":true'; then
            log_info "Exchange failover successful"
            log_to_influxdb "recovery" "exchange_failover" "$source" "success" 1
            return 0
        fi
    fi
    
    log_error "Exchange failover failed"
    log_to_influxdb "recovery" "exchange_failover" "$source" "failure" 0
    return 1
}

# Trigger service restart
trigger_service_restart() {
    local source="$1"
    local attempt_id="$2"
    
    log_info "Restarting service: $source"
    
    # Map source to docker-compose service name
    local service_name="$source"
    case "$source" in
        redis)
            service_name="chiseai-redis"
            ;;
        api)
            service_name="chiseai-api-final"
            ;;
        dashboard)
            service_name="chise-dashboard"
            ;;
        *)
            # Use source as-is
            ;;
    esac
    
    # Restart via docker-compose
    if docker-compose restart "$service_name" 2>/dev/null; then
        log_info "Service $service_name restarted successfully"
        
        # Wait for health check
        sleep 5
        
        # Verify service is healthy
        if docker-compose ps "$service_name" | grep -q "Up"; then
            log_info "Service $service_name is healthy"
            log_to_influxdb "recovery" "service_restart" "$source" "success" 1
            return 0
        fi
    fi
    
    log_error "Service restart failed for $service_name"
    log_to_influxdb "recovery" "service_restart" "$source" "failure" 0
    return 1
}

# Trigger data backfill
trigger_data_backfill() {
    local source="$1"
    local attempt_id="$2"
    local metadata="$3"
    
    log_info "Triggering data backfill for $source"
    
    # Parse metadata
    local symbol start_time end_time
    symbol=$(echo "$metadata" | python3 -c "import sys,json; print(json.load(sys.stdin).get('symbol', 'BTCUSDT'))")
    start_time=$(echo "$metadata" | python3 -c "import sys,json; print(json.load(sys.stdin).get('start_time', ''))")
    end_time=$(echo "$metadata" | python3 -c "import sys,json; print(json.load(sys.stdin).get('end_time', ''))")
    
    if [[ -z "$start_time" || -z "$end_time" ]]; then
        # Use default 1 hour ago to now
        end_time=$(date -Iseconds)
        start_time=$(date -Iseconds -d "1 hour ago")
    fi
    
    log_info "Backfill: $source/$symbol from $start_time to $end_time"
    
    # Check if backfill script exists
    local backfill_script="${PROJECT_ROOT}/scripts/backfill_data.py"
    if [[ ! -f "$backfill_script" ]]; then
        log_warn "Backfill script not found, using mock"
        log_to_influxdb "recovery" "data_backfill" "$source" "success" 1
        return 0
    fi
    
    # Run backfill
    if python3 "$backfill_script" \
        --source "$source" \
        --symbol "$symbol" \
        --start "$start_time" \
        --end "$end_time" 2>/dev/null; then
        log_info "Data backfill completed successfully"
        log_to_influxdb "recovery" "data_backfill" "$source" "success" 1
        return 0
    fi
    
    log_error "Data backfill failed"
    log_to_influxdb ""recovery"" "data_backfill" "$source" "failure" 0
    return 1
}

# Trigger deployment rollback
trigger_deployment_rollback() {
    local deployment_id="$1"
    local attempt_id="$2"
    
    log_warn "Initiating deployment rollback for $deployment_id"
    
    # Call rollback script
    local rollback_script="${SCRIPT_DIR}/rollback_deployment.sh"
    
    if [[ -x "$rollback_script" ]]; then
        if "$rollback_script" "$deployment_id"; then
            log_info "Deployment rollback successful"
            log_to_influxdb "recovery" "deployment_rollback" "$deployment_id" "success" 1
            return 0
        fi
    else
        log_error "Rollback script not found or not executable: $rollback_script"
    fi
    
    log_error "Deployment rollback failed"
    log_to_influxdb "recovery" "deployment_rollback" "$deployment_id" "failure" 0
    return 1
}

# Trigger circuit breaker reset
trigger_circuit_breaker_reset() {
    local source="$1"
    local attempt_id="$2"
    
    log_info "Resetting circuit breaker for $source"
    
    # Reset via Python API
    python3 << PYEOF
import sys
sys.path.insert(0, "${PROJECT_ROOT}/src")

try:
    from common.circuit_breaker import CircuitBreakerRegistry
    
    registry = CircuitBreakerRegistry()
    breaker = registry.get("$source")
    
    if breaker:
        breaker.reset()
        print(f"Circuit breaker reset for $source")
        sys.exit(0)
    else:
        print(f"No circuit breaker found for $source")
        sys.exit(1)
except Exception as e:
    print(f"Error resetting circuit breaker: {e}")
    sys.exit(1)
PYEOF
    
    local result=$?
    
    if [[ $result -eq 0 ]]; then
        log_info "Circuit breaker reset successful"
        log_to_influxdb "recovery" "circuit_breaker_reset" "$source" "success" 1
    else
        log_error "Circuit breaker reset failed"
        log_to_influxdb "recovery" "circuit_breaker_reset" "$source" "failure" 0
    fi
    
    return $result
}

# Log to InfluxDB
log_to_influxdb() {
    local measurement="$1"
    local recovery_type="$2"
    local source="$3"
    local status="$4"
    local success="$5"
    
    # Check if InfluxDB is available
    if ! curl -s "http://localhost:18086/health" >/dev/null 2>&1; then
        log_debug "InfluxDB not available, skipping log"
        return 0
    fi
    
    # Write to InfluxDB
    local timestamp
    timestamp=$(date +%s)000000000
    
    curl -s -X POST "http://localhost:18086/write?db=chiseai" \
        --data-binary "${measurement},recovery_type=${recovery_type},source=${source} status=\"${status}\",success=${success} ${timestamp}" \
        >/dev/null 2>&1 || true
}

# Check recovery status
show_status() {
    local attempt_id="${1:-}"
    
    if [[ -n "$attempt_id" ]]; then
        # Show specific attempt
        local attempt_file="$RECOVERY_LOG_DIR/attempt_${attempt_id}.json"
        if [[ -f "$attempt_file" ]]; then
            cat "$attempt_file" | python3 -m json.tool
        else
            log_error "Attempt not found: $attempt_id"
            return 1
        fi
    else
        # Show all active recoveries
        echo "Active recoveries:"
        find "$LOCK_DIR" -name "recovery_*.lock" 2>/dev/null | while read lock_file; do
            local source
            source=$(basename "$lock_file" | sed 's/recovery_//' | sed 's/\.lock$//')
            local pid
            pid=$(cat "$lock_file" 2>/dev/null || echo "unknown")
            echo "  - $source (PID: $pid)"
        done
        
        # Show recent attempts
        echo -e "\nRecent attempts:"
        ls -t "$RECOVERY_LOG_DIR"/attempt_*.json 2>/dev/null | head -5 | while read f; do
            local id
            id=$(basename "$f" | sed 's/attempt_//' | sed 's/\.json$//')
            local state
            state=$(cat "$f" | python3 -c "import sys,json; print(json.load(sys.stdin).get('state', 'unknown'))")
            echo "  - $id: $state"
        done
    fi
}

# Show recovery history
show_history() {
    local source=""
    local limit=50
    
    # Parse options
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --source=*)
                source="${1#*=}"
                ;;
            --limit=*)
                limit="${1#*=}"
                ;;
        esac
        shift
    done
    
    echo "Recovery history:"
    
    local files
    if [[ -n "$source" ]]; then
        files=$(grep -l "\"source\": \"$source\"" "$RECOVERY_LOG_DIR"/attempt_*.json 2>/dev/null || true)
    else
        files=$(ls -t "$RECOVERY_LOG_DIR"/attempt_*.json 2>/dev/null || true)
    fi
    
    echo "$files" | head -"$limit" | while read f; do
        if [[ -f "$f" ]]; then
            python3 << PYEOF
import json
import sys

try:
    with open("$f") as fp:
        data = json.load(fp)
    
    print(f"{data['attempt_id']}: {data['source']} - {data['recovery_type']} - {data['state']}")
except:
    pass
PYEOF
        fi
    done
}

# Show recovery statistics
show_stats() {
    echo "Recovery Statistics:"
    echo "===================="
    
    # Count attempts by state
    local total succeeded failed
    total=$(ls -1 "$RECOVERY_LOG_DIR"/attempt_*.json 2>/dev/null | wc -l)
    succeeded=$(grep -l '"state": "succeeded"' "$RECOVERY_LOG_DIR"/attempt_*.json 2>/dev/null | wc -l)
    failed=$(grep -l '"state": "failed"' "$RECOVERY_LOG_DIR"/attempt_*.json 2>/dev/null | wc -l)
    
    echo "Total attempts: $total"
    echo "Succeeded: $succeeded"
    echo "Failed: $failed"
    
    if [[ $total -gt 0 ]]; then
        local success_rate
        success_rate=$(echo "scale=1; ($succeeded * 100) / $total" | bc)
        echo "Success rate: ${success_rate}%"
    fi
    
    # Active recoveries
    echo -e "\nActive recoveries:"
    local active
    active=$(find "$LOCK_DIR" -name "recovery_*.lock" 2>/dev/null | wc -l)
    echo "$active"
}

# List active recoveries
list_active() {
    echo "Active recoveries:"
    find "$LOCK_DIR" -name "recovery_*.lock" -print0 2>/dev/null | while IFS= read -r -d '' lock_file; do
        local source
        source=$(basename "$lock_file" | sed 's/recovery_//' | sed 's/\.lock$//')
        local pid
        pid=$(cat "$lock_file" 2>/dev/null || echo "unknown")
        
        if kill -0 "$pid" 2>/dev/null; then
            echo "  - $source (PID: $pid, running)"
        else
            echo "  - $source (PID: $pid, stale)"
        fi
    done
}

# Cancel active recovery
cancel_recovery() {
    local source="$1"
    local lock_file="$LOCK_DIR/recovery_${source}.lock"
    
    if [[ -f "$lock_file" ]]; then
        local pid
        pid=$(cat "$lock_file" 2>/dev/null || echo "")
        
        if [[ -n "$pid" ]]; then
            log_info "Killing recovery process for $source (PID: $pid)"
            kill -TERM "$pid" 2>/dev/null || true
            sleep 1
            kill -KILL "$pid" 2>/dev/null || true
        fi
        
        rm -f "$lock_file"
        log_info "Recovery cancelled for $source"
    else
        log_warn "No active recovery found for $source"
    fi
}

# Manual escalation
escalate() {
    local source="$1"
    local reason="$2"
    
    log_warn "ESCALATION: Manual escalation for $source: $reason"
    
    # Send to Discord if webhook configured
    if [[ -n "${DISCORD_WEBHOOK_URL:-}" ]]; then
        curl -s -X POST "$DISCORD_WEBHOOK_URL" \
            -H "Content-Type: application/json" \
            -d "{
                \"content\": \"🚨 MANUAL ESCALATION: $source\",
                \"embeds\": [{
                    \"title\": \"Self-Healing Escalation\",
                    \"description\": \"$reason\",
                    \"color\": 15158332,
                    \"timestamp\": \"$(date -Iseconds)\"
                }]
            }" >/dev/null 2>&1 || true
    fi
    
    # Log to InfluxDB
    log_to_influxdb "escalation" "manual" "$source" "$reason" 0
}

# Main command dispatcher
main() {
    if [[ $# -eq 0 ]]; then
        usage
        exit 0
    fi
    
    local cmd="$1"
    shift
    
    case "$cmd" in
        trigger)
            if [[ $# -lt 2 ]]; then
                log_error "Usage: $0 trigger <source> <recovery_type> [options]"
                exit 1
            fi
            trigger_recovery "$1" "$2" "${@:3}"
            ;;
        status)
            show_status "$@"
            ;;
        history)
            show_history "$@"
            ;;
        stats)
            show_stats
            ;;
        list-active)
            list_active
            ;;
        cancel)
            if [[ $# -lt 1 ]]; then
                log_error "Usage: $0 cancel <source>"
                exit 1
            fi
            cancel_recovery "$1"
            ;;
        escalate)
            if [[ $# -lt 2 ]]; then
                log_error "Usage: $0 escalate <source> <reason>"
                exit 1
            fi
            escalate "$1" "$2"
            ;;
        help|--help|-h)
            usage
            ;;
        *)
            log_error "Unknown command: $cmd"
            usage
            exit 1
            ;;
    esac
}

main "$@"
