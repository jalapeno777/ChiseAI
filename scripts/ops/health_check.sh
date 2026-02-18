#!/bin/bash
#
# ChiseAI Health Check Script
# Comprehensive health check for operators
# Usage: ./scripts/ops/health_check.sh [--verbose]
#
# Exit codes:
#   0 = healthy
#   1 = warnings
#   2 = critical
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# Counters
PASS_COUNT=0
WARN_COUNT=0
FAIL_COUNT=0

# Flags
VERBOSE=false
if [[ "$1" == "--verbose" ]]; then
    VERBOSE=true
fi

# Helper functions
print_header() {
    echo -e "\n${BOLD}=== $1 ===${NC}"
}

print_pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
    ((PASS_COUNT++))
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
    ((WARN_COUNT++))
}

print_fail() {
    echo -e "${RED}[FAIL]${NC} $1"
    ((FAIL_COUNT++))
}

print_info() {
    if [[ "$VERBOSE" == true ]]; then
        echo -e "  $1"
    fi
}

# ==================== CHECKS ====================

check_docker_containers() {
    print_header "Docker Containers"
    
    local required_containers=("chiseai-api" "chiseai-redis" "chiseai-postgres")
    local all_running=true
    
    for container in "${required_containers[@]}"; do
        if docker ps --filter "name=$container" --filter "status=running" --format "{{.Names}}" | grep -q "^${container}$"; then
            print_pass "$container is running"
            if [[ "$VERBOSE" == true ]]; then
                local status=$(docker ps --filter "name=$container" --format "{{.Status}}")
                print_info "Status: $status"
            fi
        else
            print_fail "$container is not running"
            all_running=false
        fi
    done
    
    # Check optional containers
    local optional_containers=("chise-dashboard" "chiseai-grafana")
    for container in "${optional_containers[@]}"; do
        if docker ps --filter "name=$container" --filter "status=running" --format "{{.Names}}" | grep -q "^${container}$"; then
            print_pass "$container is running (optional)"
        else
            print_warn "$container is not running (optional)"
        fi
    done
    
    $all_running
}

check_redis() {
    print_header "Redis Health"
    
    # Connectivity test
    if redis-cli -p 6380 PING 2>/dev/null | grep -q "PONG"; then
        print_pass "Redis connectivity OK"
    else
        print_fail "Redis connectivity FAILED"
        return 1
    fi
    
    # Memory usage
    local memory_info=$(redis-cli -p 6380 INFO memory 2>/dev/null)
    local used_memory=$(echo "$memory_info" | grep "^used_memory:" | cut -d: -f2 | tr -d '\r')
    local max_memory=$(echo "$memory_info" | grep "^maxmemory:" | cut -d: -f2 | tr -d '\r')
    
    if [[ -n "$max_memory" && "$max_memory" != "0" ]]; then
        local usage_pct=$(echo "scale=2; ($used_memory / $max_memory) * 100" | bc 2>/dev/null || echo "0")
        if (( $(echo "$usage_pct < 70" | bc -l 2>/dev/null || echo "1") )); then
            print_pass "Redis memory usage: ${usage_pct}%"
        elif (( $(echo "$usage_pct < 85" | bc -l 2>/dev/null || echo "1") )); then
            print_warn "Redis memory usage: ${usage_pct}%"
        else
            print_fail "Redis memory usage: ${usage_pct}%"
        fi
        print_info "Used: $(echo "$memory_info" | grep "^used_memory_human:" | cut -d: -f2 | tr -d '\r')"
    else
        print_pass "Redis memory: $(echo "$memory_info" | grep "^used_memory_human:" | cut -d: -f2 | tr -d '\r')"
    fi
    
    # Connected clients
    local clients=$(redis-cli -p 6380 INFO clients 2>/dev/null | grep "^connected_clients:" | cut -d: -f2 | tr -d '\r')
    print_info "Connected clients: $clients"
    
    return 0
}

check_api_health() {
    print_header "API Health"
    
    # Basic health check
    local health_response
    health_response=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/api/v1/health 2>/dev/null || echo "000")
    
    if [[ "$health_response" == "200" ]]; then
        print_pass "API health endpoint responding"
    else
        print_fail "API health endpoint not responding (HTTP $health_response)"
        return 1
    fi
    
    # Response time check
    local response_time
    response_time=$(curl -s -o /dev/null -w "%{time_total}" http://localhost:8001/api/v1/health 2>/dev/null || echo "999")
    if (( $(echo "$response_time < 1.0" | bc -l 2>/dev/null || echo "0") )); then
        print_pass "API response time: ${response_time}s"
    elif (( $(echo "$response_time < 3.0" | bc -l 2>/dev/null || echo "0") )); then
        print_warn "API response time: ${response_time}s"
    else
        print_fail "API response time: ${response_time}s"
    fi
    
    # Execution mode
    local mode
    mode=$(curl -s http://localhost:8001/api/v1/execution/mode 2>/dev/null | jq -r '.mode' 2>/dev/null || echo "unknown")
    print_info "Execution mode: $mode"
    
    return 0
}

check_data_freshness() {
    print_header "Data Freshness"
    
    local freshness_response
    freshness_response=$(curl -s http://localhost:8001/api/v1/health/data-freshness 2>/dev/null)
    
    if [[ -z "$freshness_response" ]]; then
        print_fail "Data freshness endpoint not responding"
        return 1
    fi
    
    # Parse sources and check age
    local sources_count
    sources_count=$(echo "$freshness_response" | jq '.sources | length' 2>/dev/null || echo "0")
    
    if [[ "$sources_count" -eq 0 ]]; then
        print_warn "No data sources configured"
        return 0
    fi
    
    print_info "Monitoring $sources_count data source(s)"
    
    # Check each source
    local stale_sources=0
    local critical_sources=0
    
    while IFS= read -r source; do
        local name=$(echo "$source" | jq -r '.name')
        local age=$(echo "$source" | jq -r '.age_seconds')
        
        if [[ "$age" == "null" ]] || [[ -z "$age" ]]; then
            continue
        fi
        
        if (( $(echo "$age < 60" | bc -l 2>/dev/null || echo "0") )); then
            print_info "$name: ${age}s (fresh)"
        elif (( $(echo "$age < 180" | bc -l 2>/dev/null || echo "0") )); then
            print_warn "$name: ${age}s (stale)"
            ((stale_sources++))
        else
            print_fail "$name: ${age}s (critical)"
            ((critical_sources++))
        fi
    done < <(echo "$freshness_response" | jq -c '.sources[]' 2>/dev/null)
    
    if [[ "$critical_sources" -eq 0 && "$stale_sources" -eq 0 ]]; then
        print_pass "All data sources are fresh"
    fi
    
    return 0
}

check_kill_switch() {
    print_header "Kill Switch Status"
    
    local ks_response
    ks_response=$(curl -s http://localhost:8001/api/v1/execution/kill-switch/status 2>/dev/null)
    
    if [[ -z "$ks_response" ]]; then
        print_fail "Kill switch endpoint not responding"
        return 1
    fi
    
    local state
    state=$(echo "$ks_response" | jq -r '.state' 2>/dev/null || echo "unknown")
    
    case "$state" in
        "ARMED"|"armed")
            print_pass "Kill switch is ARMED (ready)"
            ;;
        "TRIGGERED"|"triggered")
            print_fail "Kill switch is TRIGGERED - trading halted"
            ;;
        "DISABLED"|"disabled")
            print_warn "Kill switch is DISABLED"
            ;;
        *)
            print_warn "Kill switch state unknown: $state"
            ;;
    esac
    
    # Additional details
    local last_trigger
    last_trigger=$(echo "$ks_response" | jq -r '.last_trigger // "never"')
    if [[ "$last_trigger" != "never" && "$last_trigger" != "null" ]]; then
        print_info "Last trigger: $last_trigger"
    fi
    
    local positions_closed
    positions_closed=$(echo "$ks_response" | jq -r '.positions_closed // "N/A"')
    if [[ "$positions_closed" != "N/A" && "$positions_closed" != "null" ]]; then
        print_info "Positions closed: $positions_closed"
    fi
    
    return 0
}

check_alerts() {
    print_header "Active Alerts"
    
    local alerts_response
    alerts_response=$(curl -s http://localhost:8001/api/v1/alerts/active 2>/dev/null)
    
    if [[ -z "$alerts_response" ]]; then
        print_warn "Alerts endpoint not responding"
        return 0
    fi
    
    local alert_count
    alert_count=$(echo "$alerts_response" | jq '.alerts | length' 2>/dev/null || echo "0")
    
    if [[ "$alert_count" -eq 0 ]]; then
        print_pass "No active alerts"
        return 0
    fi
    
    # Count by severity
    local critical_count=$(echo "$alerts_response" | jq '[.alerts[] | select(.severity == "critical")] | length' 2>/dev/null || echo "0")
    local warning_count=$(echo "$alerts_response" | jq '[.alerts[] | select(.severity == "warning")] | length' 2>/dev/null || echo "0")
    
    if [[ "$critical_count" -gt 0 ]]; then
        print_fail "$critical_count critical alert(s) active"
    fi
    
    if [[ "$warning_count" -gt 0 ]]; then
        print_warn "$warning_count warning(s) active"
    fi
    
    if [[ "$critical_count" -eq 0 && "$warning_count" -eq 0 ]]; then
        print_pass "$alert_count info alert(s) active"
    fi
    
    # Show alert details in verbose mode
    if [[ "$VERBOSE" == true ]]; then
        echo "$alerts_response" | jq -r '.alerts[] | "  - [\(.severity)] \(.alert_type): \(.message)"' 2>/dev/null || true
    fi
    
    return 0
}

# ==================== MAIN ====================

echo -e "${BOLD}ChiseAI Health Check${NC}"
echo "Started at: $(date)"
echo "================================"

# Run all checks
check_docker_containers || true
check_redis || true
check_api_health || true
check_data_freshness || true
check_kill_switch || true
check_alerts || true

# Summary
print_header "SUMMARY"
echo -e "${GREEN}Passed:${NC}  $PASS_COUNT"
echo -e "${YELLOW}Warnings:${NC} $WARN_COUNT"
echo -e "${RED}Failed:${NC}  $FAIL_COUNT"
echo ""

# Determine exit code
if [[ "$FAIL_COUNT" -gt 0 ]]; then
    echo -e "${RED}Overall Status: CRITICAL${NC}"
    exit 2
elif [[ "$WARN_COUNT" -gt 0 ]]; then
    echo -e "${YELLOW}Overall Status: WARNINGS${NC}"
    exit 1
else
    echo -e "${GREEN}Overall Status: HEALTHY${NC}"
    exit 0
fi
