#!/usr/bin/env bash
#
# LLM Provider Preflight Check Script
# Story: LLM-PROVIDER-FIX-001-LOCKIN
# Phase: C - Lock-in Reproducibility
#
# Usage: ./scripts/preflight/llm_provider_check.sh [--json] [--quiet]
#
# Exit Codes:
#   0 - All configured providers working
#   1 - One or more providers failed
#   2 - Script error (missing dependencies)
#

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Output mode
OUTPUT_MODE="normal"
QUIET_MODE=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --json)
            OUTPUT_MODE="json"
            shift
            ;;
        --quiet)
            QUIET_MODE=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [--json] [--quiet]"
            echo ""
            echo "Options:"
            echo "  --json    Output results as JSON"
            echo "  --quiet   Only show errors"
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 2
            ;;
    esac
done

# Results tracking
declare -A RESULTS
declare -A LATENCIES
declare -A ERRORS
TOTAL_TESTS=0
PASSED=0
FAILED=0
SKIPPED=0

# Color codes (disabled in JSON/quiet mode)
if [[ "$OUTPUT_MODE" == "normal" ]] && [[ -t 1 ]] && [[ "$QUIET_MODE" == "false" ]]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[0;33m'
    BLUE='\033[0;34m'
    NC='\033[0m' # No Color
else
    RED=''
    GREEN=''
    YELLOW=''
    BLUE=''
    NC=''
fi

# Helper functions
log() {
    if [[ "$QUIET_MODE" == "false" ]]; then
        echo -e "$1"
    fi
}

log_error() {
    echo -e "${RED}ERROR: $1${NC}" >&2
}

test_provider() {
    local name="$1"
    local url="$2"
    local model="$3"
    local api_key="$4"
    
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    
    if [[ -z "$api_key" ]]; then
        RESULTS["$name"]="SKIP"
        ERRORS["$name"]="API key not configured"
        SKIPPED=$((SKIPPED + 1))
        return 0
    fi
    
    local start_time=$(date +%s.%N)
    
    # Make the request
    local response
    local http_code
    
    response=$(curl -s -w "\n%{http_code}" \
        -X POST "$url" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $api_key" \
        -d "{
            \"model\": \"$model\",
            \"messages\": [{\"role\": \"user\", \"content\": \"Reply with OK\"}],
            \"max_tokens\": 10
        }" \
        --connect-timeout 10 \
        --max-time 30 \
        2>/dev/null) || {
        local end_time=$(date +%s.%N)
        local latency=$(echo "$end_time - $start_time" | bc)
        LATENCIES["$name"]=$(printf "%.2f" "$latency")
        RESULTS["$name"]="FAIL"
        ERRORS["$name"]="Connection failed"
        FAILED=$((FAILED + 1))
        return 1
    }
    
    local end_time=$(date +%s.%N)
    local latency=$(echo "$end_time - $start_time" | bc)
    LATENCIES["$name"]=$(printf "%.2f" "$latency")
    
    http_code=$(echo "$response" | tail -n1)
    local body=$(echo "$response" | sed '$d')
    
    if [[ "$http_code" == "200" ]]; then
        RESULTS["$name"]="OK"
        PASSED=$((PASSED + 1))
        return 0
    else
        RESULTS["$name"]="FAIL"
        # Extract error message from JSON
        local error_msg
        error_msg=$(echo "$body" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    if 'error' in data:
        err = data['error']
        if isinstance(err, dict):
            msg = err.get('message', err.get('code', 'Unknown error'))
            print(msg[:50] if len(msg) > 50 else msg)
        else:
            print(str(err)[:50])
    else:
        print('HTTP $http_code')
except:
    print('HTTP $http_code')
" 2>/dev/null || echo "HTTP $http_code")
        ERRORS["$name"]="$http_code: $error_msg"
        FAILED=$((FAILED + 1))
        return 1
    fi
}

# Main execution
main() {
    # Print header
    if [[ "$OUTPUT_MODE" == "normal" ]] && [[ "$QUIET_MODE" == "false" ]]; then
        echo "=== LLM Provider Preflight Check ==="
        echo "Timestamp: $TIMESTAMP"
        echo ""
    fi
    
    # Test KIMI Direct
    if [[ "$QUIET_MODE" == "false" ]] && [[ "$OUTPUT_MODE" == "normal" ]]; then
        printf "[1/4] Testing KIMI Direct... "
    fi
    test_provider "KIMI Direct" \
        "https://api.moonshot.cn/v1/chat/completions" \
        "kimi-k2.5" \
        "${KIMI_API_KEY:-}"
    if [[ "$OUTPUT_MODE" == "normal" ]] && [[ "$QUIET_MODE" == "false" ]]; then
        if [[ "${RESULTS[KIMI Direct]}" == "OK" ]]; then
            echo -e "${GREEN}OK${NC} (${LATENCIES[KIMI Direct]}s)"
        elif [[ "${RESULTS[KIMI Direct]}" == "SKIP" ]]; then
            echo -e "${YELLOW}SKIP${NC} (no API key)"
        else
            echo -e "${RED}FAIL${NC} (${ERRORS[KIMI Direct]})"
        fi
    fi
    
    # Test KIMI Adapter (if available)
    if [[ "$QUIET_MODE" == "false" ]] && [[ "$OUTPUT_MODE" == "normal" ]]; then
        printf "[2/4] Testing KIMI Adapter... "
    fi
    # Check if adapter is reachable
    if curl -s --connect-timeout 2 "http://chiseai-kimi-adapter:8002/health" > /dev/null 2>&1; then
        test_provider "KIMI Adapter" \
            "http://chiseai-kimi-adapter:8002/v1/chat/completions" \
            "kimi-for-coding" \
            "${KIMI_API_KEY:-}"
    else
        RESULTS["KIMI Adapter"]="SKIP"
        ERRORS["KIMI Adapter"]="Adapter not reachable"
        SKIPPED=$((SKIPPED + 1))
    fi
    if [[ "$OUTPUT_MODE" == "normal" ]] && [[ "$QUIET_MODE" == "false" ]]; then
        if [[ "${RESULTS[KIMI Adapter]}" == "OK" ]]; then
            echo -e "${GREEN}OK${NC} (${LATENCIES[KIMI Adapter]}s)"
        elif [[ "${RESULTS[KIMI Adapter]}" == "SKIP" ]]; then
            echo -e "${YELLOW}SKIP${NC} (${ERRORS[KIMI Adapter]})"
        else
            echo -e "${RED}FAIL${NC} (${ERRORS[KIMI Adapter]})"
        fi
    fi
    
    # Test Z.ai Coding
    if [[ "$QUIET_MODE" == "false" ]] && [[ "$OUTPUT_MODE" == "normal" ]]; then
        printf "[3/4] Testing Z.ai Coding... "
    fi
    test_provider "Z.ai Coding" \
        "https://api.z.ai/api/coding/paas/v4/chat/completions" \
        "glm-5" \
        "${ZAI_API_KEY:-}"
    if [[ "$OUTPUT_MODE" == "normal" ]] && [[ "$QUIET_MODE" == "false" ]]; then
        if [[ "${RESULTS[Z.ai Coding]}" == "OK" ]]; then
            echo -e "${GREEN}OK${NC} (${LATENCIES[Z.ai Coding]}s)"
        elif [[ "${RESULTS[Z.ai Coding]}" == "SKIP" ]]; then
            echo -e "${YELLOW}SKIP${NC} (no API key)"
        else
            echo -e "${RED}FAIL${NC} (${ERRORS[Z.ai Coding]})"
        fi
    fi
    
    # Test Zhipu
    if [[ "$QUIET_MODE" == "false" ]] && [[ "$OUTPUT_MODE" == "normal" ]]; then
        printf "[4/4] Testing Zhipu... "
    fi
    test_provider "Zhipu" \
        "https://open.bigmodel.cn/api/paas/v4/chat/completions" \
        "glm-4.7" \
        "${ZHIPU_API_KEY:-}"
    if [[ "$OUTPUT_MODE" == "normal" ]] && [[ "$QUIET_MODE" == "false" ]]; then
        if [[ "${RESULTS[Zhipu]}" == "OK" ]]; then
            echo -e "${GREEN}OK${NC} (${LATENCIES[Zhipu]}s)"
        elif [[ "${RESULTS[Zhipu]}" == "SKIP" ]]; then
            echo -e "${YELLOW}SKIP${NC} (no API key)"
        else
            echo -e "${RED}FAIL${NC} (${ERRORS[Zhipu]})"
        fi
    fi
    
    # Output results
    if [[ "$OUTPUT_MODE" == "json" ]]; then
        # Build JSON output
        python3 -c "
import json
results = {
    'timestamp': '$TIMESTAMP',
    'summary': {
        'total': $TOTAL_TESTS,
        'passed': $PASSED,
        'failed': $FAILED,
        'skipped': $SKIPPED
    },
    'providers': {
        'kimi_direct': {
            'status': '${RESULTS[KIMI Direct]:-UNKNOWN}',
            'latency_s': ${LATENCIES[KIMI Direct]:-null},
            'error': '${ERRORS[KIMI Direct]:-}'
        },
        'kimi_adapter': {
            'status': '${RESULTS[KIMI Adapter]:-UNKNOWN}',
            'latency_s': ${LATENCIES[KIMI Adapter]:-null},
            'error': '${ERRORS[KIMI Adapter]:-}'
        },
        'zai_coding': {
            'status': '${RESULTS[Z.ai Coding]:-UNKNOWN}',
            'latency_s': ${LATENCIES[Z.ai Coding]:-null},
            'error': '${ERRORS[Z.ai Coding]:-}'
        },
        'zhipu': {
            'status': '${RESULTS[Zhipu]:-UNKNOWN}',
            'latency_s': ${LATENCIES[Zhipu]:-null},
            'error': '${ERRORS[Zhipu]:-}'
        }
    },
    'exit_code': $(if [[ $FAILED -gt 0 ]]; then echo 1; else echo 0; fi)
}
print(json.dumps(results, indent=2))
"
    elif [[ "$QUIET_MODE" == "false" ]]; then
        echo ""
        echo "Summary: $PASSED/$TOTAL_TESTS working, $FAILED failed, $SKIPPED skipped"
    fi
    
    # Exit code
    if [[ $FAILED -gt 0 ]]; then
        if [[ "$QUIET_MODE" == "false" ]] && [[ "$OUTPUT_MODE" == "normal" ]]; then
            echo "Exit Code: 1"
        fi
        exit 1
    else
        if [[ "$QUIET_MODE" == "false" ]] && [[ "$OUTPUT_MODE" == "normal" ]]; then
            echo "Exit Code: 0"
        fi
        exit 0
    fi
}

# Run main
main "$@"
