#!/bin/bash
# Paper Trading Pipeline Manager
# Manages the continuous paper trading metrics emitter
# For PAPER-DIAG-001: Added health check command and improved error handling

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PID_FILE="/tmp/continuous_paper_emitter.pid"
STATUS_FILE="/tmp/continuous_paper_emitter.status"
LOG_DIR="$PROJECT_DIR/logs"
LOG_FILE="$LOG_DIR/continuous_paper_emitter.log"
MONITOR_LOG="$LOG_DIR/paper_trading_monitor.log"

# Ensure log directory exists
mkdir -p "$LOG_DIR"

# Environment variables
export INFLUXDB_URL="${INFLUXDB_URL:-http://host.docker.internal:18087}"
export INFLUXDB_TOKEN="${INFLUXDB_TOKEN:-REDACTED_INFLUXDB_TOKEN}"
export INFLUXDB_ORG="${INFLUXDB_ORG:-chiseai}"
export INFLUXDB_BUCKET="${INFLUXDB_BUCKET:-chiseai}"
export EMIT_INTERVAL="${EMIT_INTERVAL:-5}"
export REDIS_HOST="${REDIS_HOST:-host.docker.internal}"
export REDIS_PORT="${REDIS_PORT:-6380}"

# Cleanup function for trap
cleanup_on_exit() {
    local exit_code=$?
    if [ $exit_code -ne 0 ]; then
        echo "Error occurred (exit code: $exit_code), cleaning up..."
        rm -f "$PID_FILE"
    fi
    exit $exit_code
}

trap cleanup_on_exit EXIT

get_redis_value() {
    local key="$1"
    python3 -c "
import redis
import os
try:
    r = redis.Redis(host=os.getenv('REDIS_HOST', 'host.docker.internal'), port=int(os.getenv('REDIS_PORT', '6380')), decode_responses=True, socket_connect_timeout=2)
    value = r.get('$key')
    print(value if value else 'N/A')
except Exception as e:
    print('ERROR: ' + str(e))
" 2>/dev/null || echo "N/A"
}

get_redis_heartbeat() {
    python3 -c "
import redis
import os
from datetime import datetime, timezone
try:
    r = redis.Redis(host=os.getenv('REDIS_HOST', 'host.docker.internal'), port=int(os.getenv('REDIS_PORT', '6380')), decode_responses=True, socket_connect_timeout=2)
    hb = r.hgetall('paper_trading:heartbeat')
    if hb:
        print(f\"status={hb.get('status', 'N/A')}\")
        print(f\"last_heartbeat={hb.get('last_heartbeat', 'N/A')}\")
        print(f\"pid={hb.get('pid', 'N/A')}\")
    else:
        print('No heartbeat found in Redis')
except Exception as e:
    print(f'ERROR: {e}')
" 2>/dev/null || echo "Redis unavailable"
}

check_influxdb_data() {
    local bucket="${INFLUXDB_BUCKET:-chiseai}"
    local query='from(bucket: "'"$bucket"'") |> range(start: -5m) |> filter(fn: (r) => r._measurement == "paper_portfolio") |> last()'
    
    local result
    result=$(curl -s -X POST "${INFLUXDB_URL}/api/v2/query?org=${INFLUXDB_ORG}" \
        -H "Authorization: Token ${INFLUXDB_TOKEN}" \
        -H "Content-Type: application/vnd.flux" \
        -H "Accept: application/csv" \
        --data-raw "$query" \
        --max-time 5 2>/dev/null || echo "")
    
    if echo "$result" | grep -q "paper_portfolio"; then
        echo "DATA_FOUND"
    else
        echo "NO_DATA"
    fi
}

start() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo "Paper trading emitter already running (PID: $PID)"
            return 1
        else
            echo "Removing stale PID file"
            rm -f "$PID_FILE"
        fi
    fi

    echo "Starting paper trading continuous emitter..."
    cd "$PROJECT_DIR"
    
    # Ensure log file exists
    touch "$LOG_FILE"
    
    nohup python3 scripts/continuous_paper_emitter.py >> "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    echo "Started with PID: $(cat "$PID_FILE")"
    echo "Logs: $LOG_FILE"
    
    # Wait a moment and verify
    sleep 2
    NEW_PID=$(cat "$PID_FILE" 2>/dev/null || echo "")
    if [ -n "$NEW_PID" ] && ps -p "$NEW_PID" > /dev/null 2>&1; then
        echo "Emitter verified running (PID: $NEW_PID)"
    else
        echo "WARNING: Emitter may have failed to start. Check logs: $LOG_FILE"
        rm -f "$PID_FILE"
        return 1
    fi
    
    # Update Redis status
    python3 -c "
import redis
import os
from datetime import datetime, timezone
try:
    r = redis.Redis(host=os.getenv('REDIS_HOST', 'host.docker.internal'), port=int(os.getenv('REDIS_PORT', '6380')), decode_responses=True, socket_connect_timeout=2)
    r.set('paper_trading:status', 'active')
    r.set('paper_trading:last_restart', datetime.now(timezone.utc).isoformat())
    r.set('paper_trading:emitter_pid', '$(cat "$PID_FILE")')
    print('Redis status updated')
except Exception as e:
    print(f'Redis update skipped: {e}')
" 2>/dev/null || echo "Redis update skipped"
}

stop() {
    local found_pid=""
    
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo "Stopping paper trading emitter (PID: $PID)..."
            kill "$PID" 2>/dev/null || true
            found_pid="$PID"
            # Wait for process to exit
            for i in {1..5}; do
                if ! ps -p "$PID" > /dev/null 2>&1; then
                    break
                fi
                sleep 1
            done
            echo "Stopped"
        else
            echo "Process not running, removing stale PID file"
        fi
        rm -f "$PID_FILE"
    else
        echo "No PID file found"
    fi
    
    # Also try to kill by process name as fallback
    local pgrep_result
    pgrep_result=$(pgrep -f "continuous_paper_emitter.py" | head -1 || echo "")
    if [ -n "$pgrep_result" ] && [ "$pgrep_result" != "$found_pid" ]; then
        echo "Found additional process (PID: $pgrep_result), stopping..."
        kill "$pgrep_result" 2>/dev/null || true
    fi
    
    # Update Redis status
    python3 -c "
import redis
import os
try:
    r = redis.Redis(host=os.getenv('REDIS_HOST', 'host.docker.internal'), port=int(os.getenv('REDIS_PORT', '6380')), decode_responses=True, socket_connect_timeout=2)
    r.set('paper_trading:status', 'stopped')
    print('Redis status updated to stopped')
except Exception as e:
    pass
" 2>/dev/null || true
    
    # Clean up status file
    rm -f "$STATUS_FILE"
}

status() {
    local exit_code=0
    
    echo "=== Paper Trading Emitter Status ==="
    echo ""
    
    # Check PID file
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo "Process Status: RUNNING (PID: $PID)"
            echo "PID File: $PID_FILE (valid)"
        else
            echo "Process Status: NOT RUNNING"
            echo "PID File: $PID_FILE (STALE - PID $PID not found)"
            exit_code=1
        fi
    else
        # Check if process is running without PID file
        local running_pid
        running_pid=$(pgrep -f "continuous_paper_emitter.py" | head -1 || echo "")
        if [ -n "$running_pid" ]; then
            echo "Process Status: RUNNING (PID: $running_pid)"
            echo "PID File: NOT FOUND (process running without PID file)"
            # Create PID file for consistency
            echo "$running_pid" > "$PID_FILE"
            echo "(Created PID file)"
        else
            echo "Process Status: NOT RUNNING"
            echo "PID File: NOT FOUND"
            exit_code=1
        fi
    fi
    
    echo ""
    echo "Log File: $LOG_FILE"
    if [ -f "$LOG_FILE" ]; then
        echo "Last 5 log lines:"
        tail -5 "$LOG_FILE" 2>/dev/null || echo "  (unable to read log)"
    else
        echo "  (log file not found)"
    fi
    
    echo ""
    echo "Redis Status:"
    get_redis_heartbeat | sed 's/^/  /'
    
    return $exit_code
}

health() {
    local exit_code=0
    local issues=()
    
    echo "=== Paper Trading Health Check ==="
    echo "Timestamp: $(date -Iseconds)"
    echo ""
    
    # 1. Check if process is running
    echo "[1/4] Checking process status..."
    local is_running=false
    local actual_pid=""
    
    if [ -f "$PID_FILE" ]; then
        local pid_from_file
        pid_from_file=$(cat "$PID_FILE")
        if ps -p "$pid_from_file" > /dev/null 2>&1; then
            is_running=true
            actual_pid="$pid_from_file"
            echo "  ✓ Process running (PID: $pid_from_file from PID file)"
        else
            echo "  ✗ PID file exists but process not running (stale PID: $pid_from_file)"
            issues+=("Stale PID file")
            exit_code=1
        fi
    else
        local pgrep_result
        pgrep_result=$(pgrep -f "continuous_paper_emitter.py" | head -1 || echo "")
        if [ -n "$pgrep_result" ]; then
            is_running=true
            actual_pid="$pgrep_result"
            echo "  ✓ Process running (PID: $pgrep_result, no PID file)"
            echo "  (Creating PID file for consistency)"
            echo "$pgrep_result" > "$PID_FILE"
        else
            echo "  ✗ Process not running"
            issues+=("Process not running")
            exit_code=1
        fi
    fi
    
    # 2. Check for recent data in InfluxDB
    echo ""
    echo "[2/4] Checking InfluxDB for recent data (last 5 minutes)..."
    local influxdb_result
    influxdb_result=$(check_influxdb_data)
    
    if [ "$influxdb_result" = "DATA_FOUND" ]; then
        echo "  ✓ Recent data found in InfluxDB"
    else
        echo "  ✗ No recent data in InfluxDB"
        issues+=("No recent InfluxDB data")
        exit_code=1
    fi
    
    # 3. Check Redis status
    echo ""
    echo "[3/4] Checking Redis status..."
    local redis_status
    redis_status=$(get_redis_value "paper_trading:status")
    
    if [ "$redis_status" = "active" ]; then
        echo "  ✓ Redis status: active"
    elif [ "$redis_status" = "stopped" ]; then
        echo "  ✗ Redis status: stopped (mismatch with process state)"
        if [ "$is_running" = true ]; then
            issues+=("Redis status mismatch: shows stopped but process running")
        fi
        exit_code=1
    elif [[ "$redis_status" == ERROR* ]] || [ "$redis_status" = "N/A" ]; then
        echo "  ! Redis unavailable ($redis_status)"
        echo "    (This is a warning, not a failure)"
    else
        echo "  ? Redis status: $redis_status (unexpected value)"
    fi
    
    # Show heartbeat info
    echo ""
    echo "  Redis heartbeat details:"
    get_redis_heartbeat | sed 's/^/    /'
    
    # 4. Check status file
    echo ""
    echo "[4/4] Checking local status file..."
    if [ -f "$STATUS_FILE" ]; then
        echo "  ✓ Status file exists: $STATUS_FILE"
        local status_content
        status_content=$(cat "$STATUS_FILE" 2>/dev/null || echo "(unable to read)")
        echo "  Content:"
        echo "$status_content" | sed 's/^/    /'
    else
        echo "  ! Status file not found: $STATUS_FILE"
        echo "    (This is a warning, emitter may not have started yet)"
    fi
    
    # Summary
    echo ""
    echo "=== Health Check Summary ==="
    if [ $exit_code -eq 0 ]; then
        echo "✓ ALL CHECKS PASSED"
        echo "Paper trading emitter is healthy and emitting data."
    else
        echo "✗ HEALTH CHECK FAILED"
        echo "Issues found:"
        for issue in "${issues[@]}"; do
            echo "  - $issue"
        done
        echo ""
        echo "Recommendation: Run '$0 restart' to restart the emitter"
    fi
    
    return $exit_code
}

restart() {
    echo "Restarting paper trading emitter..."
    stop
    sleep 1
    start
}

monitor() {
    echo "Running paper trading monitor (auto-restart enabled)..."
    python3 "$PROJECT_DIR/scripts/paper_trading_monitor.py" --check-interval 60 --auto-restart
}

case "${1:-}" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    restart)
        restart
        ;;
    status)
        status
        ;;
    health)
        health
        ;;
    monitor)
        monitor
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|health|monitor}"
        echo ""
        echo "Commands:"
        echo "  start    - Start the paper trading emitter"
        echo "  stop     - Stop the paper trading emitter"
        echo "  restart  - Restart the paper trading emitter"
        echo "  status   - Show basic status (process, logs, Redis)"
        echo "  health   - Comprehensive health check (process, InfluxDB, Redis, status file)"
        echo "  monitor  - Run continuous monitoring with auto-restart"
        echo ""
        echo "For cron usage, run monitor script directly:"
        echo "  */2 * * * * cd $PROJECT_DIR && python3 scripts/paper_trading_monitor.py"
        exit 1
        ;;
esac
