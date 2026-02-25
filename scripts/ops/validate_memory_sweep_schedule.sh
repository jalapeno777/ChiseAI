#!/bin/bash
#
# Memory Sweep Schedule Validation Script
# 
# Validates that memory sweep is properly scheduled and configured.
# Returns exit code 0 if all checks pass, non-zero if any fail.
#
# Usage:
#   bash scripts/ops/validate_memory_sweep_schedule.sh
#   bash scripts/ops/validate_memory_sweep_schedule.sh --verbose
#
# Exit codes:
#   0 - All checks passed
#   1 - One or more checks failed
#   2 - Script error

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
MEMORY_SWEEP_SCRIPT="${PROJECT_ROOT}/scripts/ops/memory_sweep.py"

# Colors for output (if terminal supports it)
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Counters
PASS_COUNT=0
FAIL_COUNT=0
WARN_COUNT=0

# Verbose mode
VERBOSE=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --verbose|-v)
            VERBOSE=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [--verbose|-v] [--help|-h]"
            echo ""
            echo "Validates memory sweep scheduling configuration."
            echo ""
            echo "Options:"
            echo "  --verbose, -v    Show detailed output"
            echo "  --help, -h       Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 2
            ;;
    esac
done

# Helper functions
print_pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
    ((PASS_COUNT++))
}

print_fail() {
    echo -e "${RED}[FAIL]${NC} $1"
    ((FAIL_COUNT++))
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
    ((WARN_COUNT++))
}

print_info() {
    if [[ "$VERBOSE" == true ]]; then
        echo "[INFO] $1"
    fi
}

print_section() {
    echo ""
    echo "========================================"
    echo "$1"
    echo "========================================"
}

# Check if running in a terminal
if [[ -t 1 ]]; then
    : # Colors already set
else
    RED=''
    GREEN=''
    YELLOW=''
    NC=''
fi

# ============================================
# CHECK 1: Memory Sweep Script Exists
# ============================================
print_section "Checking Memory Sweep Script"

if [[ -f "$MEMORY_SWEEP_SCRIPT" ]]; then
    print_pass "Memory sweep script exists: $MEMORY_SWEEP_SCRIPT"
    
    if [[ -x "$MEMORY_SWEEP_SCRIPT" ]]; then
        print_pass "Memory sweep script is executable"
    else
        print_warn "Memory sweep script is not executable (chmod +x may be needed)"
    fi
    
    if [[ "$VERBOSE" == true ]]; then
        SCRIPT_LINES=$(wc -l < "$MEMORY_SWEEP_SCRIPT")
        print_info "Script has $SCRIPT_LINES lines"
    fi
else
    print_fail "Memory sweep script not found: $MEMORY_SWEEP_SCRIPT"
fi

# ============================================
# CHECK 2: Cron Job Scheduling
# ============================================
print_section "Checking Cron Job Scheduling"

CRON_FOUND=false
CRON_USER=""

# Check user crontab
if crontab -l 2>/dev/null | grep -q "memory_sweep"; then
    CRON_FOUND=true
    CRON_USER="current user ($(whoami))"
    print_pass "Cron job found in user crontab"
    
    if [[ "$VERBOSE" == true ]]; then
        echo "  Cron entry:"
        crontab -l | grep "memory_sweep" | sed 's/^/    /'
    fi
fi

# Check system crontabs
for cron_file in /etc/crontab /etc/cron.d/*; do
    if [[ -f "$cron_file" ]] && grep -q "memory_sweep" "$cron_file" 2>/dev/null; then
        CRON_FOUND=true
        CRON_USER="system ($cron_file)"
        print_pass "Cron job found in $cron_file"
        
        if [[ "$VERBOSE" == true ]]; then
            echo "  Cron entry:"
            grep "memory_sweep" "$cron_file" | sed 's/^/    /'
        fi
    fi
done

# Check /var/spool/cron (various locations)
for spool_dir in /var/spool/cron /var/spool/cron/crontabs; do
    if [[ -d "$spool_dir" ]]; then
        for user_crontab in "$spool_dir"/*; do
            if [[ -f "$user_crontab" ]] && grep -q "memory_sweep" "$user_crontab" 2>/dev/null; then
                CRON_FOUND=true
                CRON_USER="user ($(basename "$user_crontab"))"
                print_pass "Cron job found in $user_crontab"
            fi
        done
    fi
done

if [[ "$CRON_FOUND" == false ]]; then
    print_warn "No cron job found for memory_sweep"
    echo "  To schedule with cron, add to crontab:"
    echo "  0 2 * * * cd $PROJECT_ROOT && python3 scripts/ops/memory_sweep.py --full-sweep >> /var/log/chiseai/memory_sweep.log 2>&1"
fi

# ============================================
# CHECK 3: Systemd Timer Scheduling
# ============================================
print_section "Checking Systemd Timer Scheduling"

SYSTEMD_FOUND=false

if command -v systemctl >/dev/null 2>&1; then
    # Check for chiseai-memory-sweep timer
    if systemctl list-timers --all 2>/dev/null | grep -q "chiseai-memory-sweep"; then
        SYSTEMD_FOUND=true
        print_pass "Systemd timer 'chiseai-memory-sweep' found"
        
        if [[ "$VERBOSE" == true ]]; then
            echo "  Timer status:"
            systemctl list-timers --all | grep "chiseai-memory-sweep" | sed 's/^/    /'
            
            echo "  Next run:"
            systemctl list-timers --all | grep -A1 "chiseai-memory-sweep" | tail -1 | sed 's/^/    /'
        fi
        
        # Check if timer is enabled
        if systemctl is-enabled chiseai-memory-sweep.timer >/dev/null 2>&1; then
            print_pass "Systemd timer is enabled"
        else
            print_warn "Systemd timer exists but is not enabled"
        fi
        
        # Check if timer is active
        if systemctl is-active chiseai-memory-sweep.timer >/dev/null 2>&1; then
            print_pass "Systemd timer is active"
        else
            print_warn "Systemd timer exists but is not active"
        fi
    else
        print_info "No systemd timer 'chiseai-memory-sweep' found"
    fi
    
    # Check for any memory sweep related timers
    if systemctl list-timers --all 2>/dev/null | grep -qi "memory"; then
        if [[ "$SYSTEMD_FOUND" == false ]]; then
            print_warn "Found other timers with 'memory' in name:"
            systemctl list-timers --all | grep -i "memory" | sed 's/^/  /'
        fi
    fi
else
    print_info "systemctl not available (not a systemd system)"
fi

if [[ "$SYSTEMD_FOUND" == false && "$CRON_FOUND" == false ]]; then
    print_fail "No scheduling mechanism found (neither cron nor systemd timer)"
    echo ""
    echo "ACTION REQUIRED: Schedule the memory sweep using one of these methods:"
    echo ""
    echo "Option 1 - Cron (simplest):"
    echo "  crontab -e"
    echo "  # Add: 0 2 * * * cd $PROJECT_ROOT && python3 scripts/ops/memory_sweep.py --full-sweep >> /var/log/chiseai/memory_sweep.log 2>&1"
    echo ""
    echo "Option 2 - Systemd timer (recommended for production):"
    echo "  See docs/runbooks/memory-sweep-scheduling.md for setup instructions"
fi

# ============================================
# CHECK 4: Redis Connectivity
# ============================================
print_section "Checking Redis Connectivity"

REDIS_HOST="${REDIS_HOST:-host.docker.internal}"
REDIS_PORT="${REDIS_PORT:-6380}"

print_info "Checking Redis at $REDIS_HOST:$REDIS_PORT"

# Check if redis-cli is available
if command -v redis-cli >/dev/null 2>&1; then
    if redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" ping >/dev/null 2>&1; then
        print_pass "Redis is reachable at $REDIS_HOST:$REDIS_PORT"
        
        # Check for iterlog entries
        ITERLOG_COUNT=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" --scan --pattern "bmad:chiseai:iterlog:story:*" 2>/dev/null | wc -l)
        if [[ "$ITERLOG_COUNT" -gt 0 ]]; then
            print_pass "Found $ITERLOG_COUNT iterlog entries in Redis"
        else
            print_warn "No iterlog entries found in Redis"
        fi
    else
        print_fail "Cannot connect to Redis at $REDIS_HOST:$REDIS_PORT"
        echo "  ACTION: Ensure Redis is running and accessible"
        echo "  Docker: docker ps --filter name=redis"
        echo "  Test: redis-cli -h $REDIS_HOST -p $REDIS_PORT ping"
    fi
else
    print_warn "redis-cli not installed, skipping Redis connectivity test"
    
    # Try Python fallback
    if command -v python3 >/dev/null 2>&1; then
        print_info "Attempting Redis check via Python..."
        if python3 -c "
import sys
try:
    import redis
    r = redis.Redis(host='$REDIS_HOST', port=$REDIS_PORT, socket_connect_timeout=5)
    r.ping()
    sys.exit(0)
except Exception as e:
    print(f'Error: {e}', file=sys.stderr)
    sys.exit(1)
" 2>/dev/null; then
            print_pass "Redis is reachable at $REDIS_HOST:$REDIS_PORT (via Python)"
        else
            print_fail "Cannot connect to Redis at $REDIS_HOST:$REDIS_PORT (via Python)"
        fi
    fi
fi

# ============================================
# CHECK 5: Qdrant Connectivity
# ============================================
print_section "Checking Qdrant Connectivity"

QDRANT_HOST="${QDRANT_HOST:-host.docker.internal}"
QDRANT_PORT="${QDRANT_PORT:-6334}"

print_info "Checking Qdrant at $QDRANT_HOST:$QDRANT_PORT"

# Try curl first
if command -v curl >/dev/null 2>&1; then
    if curl -s "http://$QDRANT_HOST:$QDRANT_PORT/collections" >/dev/null 2>&1; then
        print_pass "Qdrant is reachable at $QDRANT_HOST:$QDRANT_PORT"
        
        # Check for ChiseAI collection
        if curl -s "http://$QDRANT_HOST:$QDRANT_PORT/collections/ChiseAI" >/dev/null 2>&1; then
            print_pass "ChiseAI collection exists in Qdrant"
            
            if [[ "$VERBOSE" == true ]]; then
                COLLECTION_INFO=$(curl -s "http://$QDRANT_HOST:$QDRANT_PORT/collections/ChiseAI" 2>/dev/null)
                print_info "Collection info: $COLLECTION_INFO"
            fi
        else
            print_warn "ChiseAI collection not found in Qdrant"
        fi
    else
        print_fail "Cannot connect to Qdrant at $QDRANT_HOST:$QDRANT_PORT"
        echo "  ACTION: Ensure Qdrant is running and accessible"
        echo "  Docker: docker ps --filter name=qdrant"
        echo "  Test: curl http://$QDRANT_HOST:$QDRANT_PORT/collections"
    fi
else
    print_warn "curl not installed, trying Python fallback..."
    
    if command -v python3 >/dev/null 2>&1; then
        if python3 -c "
import sys
try:
    from qdrant_client import QdrantClient
    client = QdrantClient(host='$QDRANT_HOST', port=$QDRANT_PORT, timeout=5)
    client.get_collections()
    sys.exit(0)
except Exception as e:
    print(f'Error: {e}', file=sys.stderr)
    sys.exit(1)
" 2>/dev/null; then
            print_pass "Qdrant is reachable at $QDRANT_HOST:$QDRANT_PORT (via Python)"
        else
            print_fail "Cannot connect to Qdrant at $QDRANT_HOST:$QDRANT_PORT (via Python)"
        fi
    else
        print_warn "Neither curl nor Python with qdrant-client available"
    fi
fi

# ============================================
# CHECK 6: Feature Flags
# ============================================
print_section "Checking Feature Flags"

if command -v redis-cli >/dev/null 2>&1; then
    FLAGS_CHECKED=false
    
    # Check memory sweep enabled flag
    SWEEP_ENABLED=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" GET "chise:feature_flags:governance:memory_sweep_enabled" 2>/dev/null || echo "")
    if [[ -n "$SWEEP_ENABLED" ]]; then
        FLAGS_CHECKED=true
        if [[ "$SWEEP_ENABLED" == "true" ]]; then
            print_pass "Feature flag 'memory_sweep_enabled' is set to 'true'"
        else
            print_warn "Feature flag 'memory_sweep_enabled' is set to '$SWEEP_ENABLED'"
        fi
    else
        print_warn "Feature flag 'memory_sweep_enabled' is not set (default: disabled)"
        echo "  To enable: redis-cli -h $REDIS_HOST -p $REDIS_PORT SET chise:feature_flags:governance:memory_sweep_enabled true"
    fi
    
    # Check other related flags
    for flag in "memory_promotion_enabled" "memory_dedup_enabled" "contradiction_detection_enabled"; do
        FLAG_VALUE=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" GET "chise:feature_flags:governance:$flag" 2>/dev/null || echo "")
        if [[ -n "$FLAG_VALUE" ]]; then
            print_info "Feature flag '$flag' is set to '$FLAG_VALUE'"
        else
            print_info "Feature flag '$flag' is not set (default: disabled)"
        fi
    done
else
    print_warn "Cannot check feature flags (redis-cli not available)"
fi

# ============================================
# CHECK 7: Log Directory
# ============================================
print_section "Checking Log Directory"

LOG_DIR="/var/log/chiseai"
if [[ -d "$LOG_DIR" ]]; then
    print_pass "Log directory exists: $LOG_DIR"
    
    if [[ -w "$LOG_DIR" ]]; then
        print_pass "Log directory is writable"
    else
        print_warn "Log directory is not writable by current user"
    fi
    
    # Check for existing logs
    if [[ -f "$LOG_DIR/memory_sweep.log" ]]; then
        LAST_RUN=$(stat -c %y "$LOG_DIR/memory_sweep.log" 2>/dev/null | cut -d' ' -f1)
        print_pass "Memory sweep log exists (last modified: $LAST_RUN)"
        
        if [[ "$VERBOSE" == true ]]; then
            LOG_LINES=$(wc -l < "$LOG_DIR/memory_sweep.log")
            print_info "Log file has $LOG_LINES lines"
        fi
    else
        print_info "No memory_sweep.log found (sweep may not have run yet)"
    fi
else
    print_warn "Log directory does not exist: $LOG_DIR"
    echo "  To create: sudo mkdir -p $LOG_DIR && sudo chown \$USER:\$USER $LOG_DIR"
fi

# ============================================
# CHECK 8: Python Environment
# ============================================
print_section "Checking Python Environment"

if command -v python3 >/dev/null 2>&1; then
    PYTHON_VERSION=$(python3 --version 2>&1)
    print_pass "Python is available: $PYTHON_VERSION"
    
    # Check required modules
    REQUIRED_MODULES=("redis")
    for module in "${REQUIRED_MODULES[@]}"; do
        if python3 -c "import $module" 2>/dev/null; then
            print_pass "Python module '$module' is installed"
        else
            print_warn "Python module '$module' is not installed"
            echo "  Install: pip install $module"
        fi
    done
    
    # Check optional modules
    OPTIONAL_MODULES=("qdrant_client")
    for module in "${OPTIONAL_MODULES[@]}"; do
        if python3 -c "import $module" 2>/dev/null; then
            print_pass "Python module '$module' is installed (optional)"
        else
            print_info "Python module '$module' is not installed (optional)"
        fi
    done
else
    print_fail "Python 3 is not installed"
fi

# ============================================
# CHECK 9: Test Run (Dry Run)
# ============================================
print_section "Testing Memory Sweep (Dry Run)"

if [[ -f "$MEMORY_SWEEP_SCRIPT" ]] && command -v python3 >/dev/null 2>&1; then
    print_info "Running memory sweep in dry-run mode..."
    
    if cd "$PROJECT_ROOT" && python3 "$MEMORY_SWEEP_SCRIPT" --dry-run >/tmp/memory_sweep_test.log 2>&1; then
        print_pass "Dry-run sweep completed successfully"
        
        if [[ "$VERBOSE" == true && -f /tmp/memory_sweep_test.log ]]; then
            echo "  Dry-run output:"
            tail -20 /tmp/memory_sweep_test.log | sed 's/^/    /'
        fi
    else
        print_fail "Dry-run sweep failed"
        if [[ -f /tmp/memory_sweep_test.log ]]; then
            echo "  Error output:"
            tail -10 /tmp/memory_sweep_test.log | sed 's/^/    /'
        fi
    fi
    
    # Cleanup
    rm -f /tmp/memory_sweep_test.log
else
    print_info "Skipping dry-run test (script or Python not available)"
fi

# ============================================
# Summary
# ============================================
print_section "Validation Summary"

echo "Total checks:"
echo "  Passed:   $PASS_COUNT"
echo "  Failed:   $FAIL_COUNT"
echo "  Warnings: $WARN_COUNT"
echo ""

if [[ $FAIL_COUNT -eq 0 ]]; then
    echo -e "${GREEN}✓ All critical checks passed!${NC}"
    
    if [[ $WARN_COUNT -gt 0 ]]; then
        echo -e "${YELLOW}⚠ There are $WARN_COUNT warning(s) that should be addressed.${NC}"
    fi
    
    echo ""
    echo "Memory sweep scheduling appears to be properly configured."
    exit 0
else
    echo -e "${RED}✗ $FAIL_COUNT check(s) failed.${NC}"
    echo ""
    echo "Please address the failures above before relying on automated memory sweeps."
    echo "Refer to docs/runbooks/memory-sweep-scheduling.md for setup instructions."
    exit 1
fi
