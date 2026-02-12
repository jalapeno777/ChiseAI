#!/bin/bash
# Grafana Dashboard Watchdog Management Script
#
# Usage:
#   ./watchdog.sh start|stop|restart|status|logs
#
# Environment:
#   GRAFANA_URL - Grafana base URL
#   GRAFANA_USER - Grafana admin username
#   GRAFANA_PASSWORD - Grafana admin password

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../../.." && pwd)"
VENV_PATH="${PROJECT_ROOT}/venv"
WATCHDOG_SCRIPT="${PROJECT_ROOT}/scripts/grafana-watchdog.py"
PIDFILE="/tmp/grafana-watchdog.pid"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_venv() {
    if [[ ! -d "$VENV_PATH" ]]; then
        log_error "Virtual environment not found at $VENV_PATH"
        log_info "Create it with: python3 -m venv $VENV_PATH"
        exit 1
    fi
}

check_watchdog_script() {
    if [[ ! -f "$WATCHDOG_SCRIPT" ]]; then
        log_error "Watchdog script not found at $WATCHDOG_SCRIPT"
        exit 1
    fi
}

start_watchdog() {
    check_venv
    check_watchdog_script
    
    if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
        log_warn "Watchdog is already running (PID: $(cat "$PIDFILE"))"
        exit 0
    fi
    
    log_info "Starting Grafana Dashboard Watchdog..."
    
    source "$VENV_PATH/bin/activate"
    
    # Install dependencies if needed
    pip install -q watchdog requests 2>/dev/null || true
    
    nohup python3 "$WATCHDOG_SCRIPT" > /tmp/grafana-watchdog.log 2>&1 &
    echo $! > "$PIDFILE"
    
    sleep 2
    
    if kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
        log_info "Watchdog started successfully (PID: $(cat "$PIDFILE"))"
        log_info "Log file: /tmp/grafana-watchdog.log"
    else
        log_error "Failed to start watchdog"
        rm -f "$PIDFILE"
        exit 1
    fi
}

stop_watchdog() {
    if [[ ! -f "$PIDFILE" ]]; then
        log_warn "PID file not found - watchdog may not be running"
        
        # Try to find and kill any running watchdog processes
        local pids
        pids=$(pgrep -f "grafana-watchdog.py" || true)
        if [[ -n "$pids" ]]; then
            log_info "Found watchdog processes: $pids"
            echo "$pids" | xargs kill -TERM 2>/dev/null || true
            sleep 2
            echo "$pids" | xargs kill -KILL 2>/dev/null || true
            log_info "Watchdog stopped"
        else
            log_warn "No watchdog processes found"
        fi
        return
    fi
    
    local pid
    pid=$(cat "$PIDFILE")
    
    if kill -0 "$pid" 2>/dev/null; then
        log_info "Stopping watchdog (PID: $pid)..."
        kill -TERM "$pid" 2>/dev/null || true
        
        # Wait for process to stop
        local count=0
        while kill -0 "$pid" 2>/dev/null && [[ $count -lt 10 ]]; do
            sleep 1
            ((count++))
        done
        
        if kill -0 "$pid" 2>/dev/null; then
            log_warn "Force killing watchdog..."
            kill -KILL "$pid" 2>/dev/null || true
        fi
        
        log_info "Watchdog stopped"
    else
        log_warn "Watchdog process not found (PID: $pid)"
    fi
    
    rm -f "$PIDFILE"
}

restart_watchdog() {
    stop_watchdog
    sleep 2
    start_watchdog
}

status_watchdog() {
    if [[ -f "$PIDFILE" ]]; then
        local pid
        pid=$(cat "$PIDFILE")
        if kill -0 "$pid" 2>/dev/null; then
            log_info "Watchdog is running (PID: $pid)"
            log_info "Log file: /tmp/grafana-watchdog.log"
            
            # Show recent log entries
            if [[ -f /tmp/grafana-watchdog.log ]]; then
                echo ""
                echo "Recent log entries:"
                tail -n 10 /tmp/grafana-watchdog.log
            fi
        else
            log_warn "PID file exists but process is not running"
            rm -f "$PIDFILE"
        fi
    else
        # Check for any running watchdog processes
        local pids
        pids=$(pgrep -f "grafana-watchdog.py" || true)
        if [[ -n "$pids" ]]; then
            log_warn "Watchdog is running but no PID file found (PIDs: $pids)"
        else
            log_info "Watchdog is not running"
        fi
    fi
}

logs_watchdog() {
    if [[ -f /tmp/grafana-watchdog.log ]]; then
        tail -f /tmp/grafana-watchdog.log
    else
        log_warn "Log file not found: /tmp/grafana-watchdog.log"
    fi
}

test_watchdog() {
    log_info "Testing Grafana Dashboard Watchdog..."
    
    # Check if Grafana is accessible
    local grafana_url="${GRAFANA_URL:-http://host.docker.internal:3001}"
    log_info "Checking Grafana at $grafana_url..."
    
    if curl -s "$grafana_url/api/health" > /dev/null 2>&1; then
        log_info "Grafana is accessible"
    else
        log_warn "Grafana is not accessible at $grafana_url"
    fi
    
    # Check dashboards directory
    local dashboards_path="${PROJECT_ROOT}/infrastructure/grafana/provisioning/dashboards"
    if [[ -d "$dashboards_path" ]]; then
        log_info "Dashboards directory exists: $dashboards_path"
        local count
        count=$(find "$dashboards_path" -name "*.json" | wc -l)
        log_info "Found $count dashboard JSON files"
    else
        log_warn "Dashboards directory not found: $dashboards_path"
    fi
    
    # Check Python dependencies
    check_venv
    source "$VENV_PATH/bin/activate"
    
    if python3 -c "import watchdog" 2>/dev/null; then
        log_info "watchdog library is installed"
    else
        log_warn "watchdog library is not installed"
    fi
    
    if python3 -c "import requests" 2>/dev/null; then
        log_info "requests library is installed"
    else
        log_warn "requests library is not installed"
    fi
    
    log_info "Test complete"
}

# Main command handler
case "${1:-}" in
    start)
        start_watchdog
        ;;
    stop)
        stop_watchdog
        ;;
    restart)
        restart_watchdog
        ;;
    status)
        status_watchdog
        ;;
    logs)
        logs_watchdog
        ;;
    test)
        test_watchdog
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs|test}"
        echo ""
        echo "Commands:"
        echo "  start   - Start the watchdog daemon"
        echo "  stop    - Stop the watchdog daemon"
        echo "  restart - Restart the watchdog daemon"
        echo "  status  - Check watchdog status"
        echo "  logs    - Watch the log file"
        echo "  test    - Run tests and checks"
        echo ""
        echo "Environment Variables:"
        echo "  GRAFANA_URL      - Grafana base URL (default: http://host.docker.internal:3001)"
        echo "  GRAFANA_USER     - Grafana admin username"
        echo "  GRAFANA_PASSWORD - Grafana admin password"
        exit 1
        ;;
esac
