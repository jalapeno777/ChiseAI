#!/bin/bash
#
# ChiseAI Kill Switch Status Check
# Quick kill-switch status check for operators
# Usage: ./scripts/ops/kill_switch_check.sh [--json]
#
# Exit codes:
#   0 = ARMED (ready for trading)
#   1 = TRIGGERED (trading halted)
#   2 = DISABLED (manually disabled)
#   3 = ERROR (endpoint not responding or other error)
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# Configuration
API_ENDPOINT="http://localhost:8001/api/v1/execution/kill-switch/status"
JSON_OUTPUT=false

# Parse arguments
if [[ "$1" == "--json" ]]; then
    JSON_OUTPUT=true
fi

# Fetch kill switch status
fetch_status() {
    local response
    response=$(curl -s -w "\n%{http_code}" "$API_ENDPOINT" 2>/dev/null || echo -e "\n000")
    
    local http_code=$(echo "$response" | tail -n1)
    local body=$(echo "$response" | sed '$d')
    
    if [[ "$http_code" != "200" ]]; then
        if [[ "$JSON_OUTPUT" == true ]]; then
            echo '{"error": "API not responding", "http_code": '"$http_code"', "exit_code": 3}'
        else
            echo -e "${RED}[ERROR]${NC} Kill switch endpoint not responding"
            echo "  HTTP Code: $http_code"
            echo "  Endpoint: $API_ENDPOINT"
        fi
        exit 3
    fi
    
    echo "$body"
}

# Parse and display status
parse_and_display() {
    local json_data="$1"
    
    # Extract fields
    local state=$(echo "$json_data" | jq -r '.state // "unknown"')
    local last_trigger=$(echo "$json_data" | jq -r '.last_trigger // "never"')
    local positions_closed=$(echo "$json_data" | jq -r '.positions_closed // "N/A"')
    local triggered_at=$(echo "$json_data" | jq -r '.triggered_at // "N/A"')
    local trigger_reason=$(echo "$json_data" | jq -r '.trigger_reason // "N/A"')
    local circuit_breaker=$(echo "$json_data" | jq -r '.circuit_breaker // "N/A"')
    
    if [[ "$JSON_OUTPUT" == true ]]; then
        # Add exit_code to JSON output
        local exit_code=3
        case "${state^^}" in
            "ARMED") exit_code=0 ;;
            "TRIGGERED") exit_code=1 ;;
            "DISABLED") exit_code=2 ;;
        esac
        echo "$json_data" | jq --arg code "$exit_code" '. + {exit_code: ($code | tonumber)}'
        exit $exit_code
    fi
    
    # Human-readable output
    echo -e "${BOLD}Kill Switch Status${NC}"
    echo "=================="
    echo ""
    
    # State with color
    case "${state^^}" in
        "ARMED")
            echo -e "State: ${GREEN}● ARMED${NC} (ready for trading)"
            ;;
        "TRIGGERED")
            echo -e "State: ${RED}● TRIGGERED${NC} (trading halted)"
            ;;
        "DISABLED")
            echo -e "State: ${YELLOW}● DISABLED${NC} (manually disabled)"
            ;;
        *)
            echo -e "State: ${YELLOW}? UNKNOWN${NC} ($state)"
            ;;
    esac
    
    # Additional details
    echo ""
    echo -e "${BOLD}Details:${NC}"
    
    if [[ "$last_trigger" != "never" && "$last_trigger" != "null" && -n "$last_trigger" ]]; then
        echo "  Last trigger: $last_trigger"
    else
        echo "  Last trigger: never"
    fi
    
    if [[ "$positions_closed" != "N/A" && "$positions_closed" != "null" ]]; then
        echo "  Positions closed: $positions_closed"
    fi
    
    if [[ "$triggered_at" != "N/A" && "$triggered_at" != "null" ]]; then
        echo "  Triggered at: $triggered_at"
    fi
    
    if [[ "$trigger_reason" != "N/A" && "$trigger_reason" != "null" ]]; then
        echo "  Trigger reason: $trigger_reason"
    fi
    
    if [[ "$circuit_breaker" != "N/A" && "$circuit_breaker" != "null" ]]; then
        echo ""
        echo -e "${BOLD}Circuit Breaker:${NC}"
        local cb_state=$(echo "$json_data" | jq -r '.circuit_breaker.state // "unknown"')
        local cb_failures=$(echo "$json_data" | jq -r '.circuit_breaker.consecutive_failures // "0"')
        echo "  State: $cb_state"
        echo "  Consecutive failures: $cb_failures"
    fi
    
    # Grafana reference
    echo ""
    echo -e "${BLUE}Grafana Panel:${NC} ChiseAI > Paper Trading > Kill-Switch Status"
    
    # Return appropriate exit code
    case "${state^^}" in
        "ARMED")
            exit 0
            ;;
        "TRIGGERED")
            exit 1
            ;;
        "DISABLED")
            exit 2
            ;;
        *)
            exit 3
            ;;
    esac
}

# Main execution
main() {
    local status_json
    status_json=$(fetch_status)
    parse_and_display "$status_json"
}

main "$@"
