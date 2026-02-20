#!/bin/bash
# Woodpecker Database Health Monitor
# Usage: ./monitor_woodpecker_db.sh
# Can be run via cron every 5 minutes or as a systemd timer
# 
# Environment variables:
#   ALERT_WEBHOOK_URL - Discord/Slack webhook for alerts (optional)
#   LOG_DIR - Directory for log files (default: /var/log/chiseai)

set -e

# Configuration
LOG_DIR="${LOG_DIR:-/var/log/chiseai}"
LOG_FILE="$LOG_DIR/woodpecker_db_monitor.log"
ALERT_WEBHOOK="${ALERT_WEBHOOK_URL:-}"
POSTGRES_CONTAINER="chiseai-postgres"
WOODPECKER_CONTAINER="woodpecker-server"

# Ensure log directory exists
mkdir -p "$LOG_DIR"

# Timestamp
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# Alert function
send_alert() {
    local level="$1"
    local message="$2"
    local full_message="[$TIMESTAMP] $level: $message"
    
    # Log to file
    echo "$full_message" >> "$LOG_FILE"
    
    # Send webhook alert if configured
    if [ -n "$ALERT_WEBHOOK" ] && [ "$level" = "CRITICAL" ] || [ "$level" = "ERROR" ]; then
        curl -s -X POST -H "Content-Type: application/json" \
            -d "{\"content\":\"🚨 $full_message\"}" \
            "$ALERT_WEBHOOK" > /dev/null 2>&1 || true
    fi
    
    # Also output to stderr for systemd/cron
    echo "$full_message" >&2
}

# Health check functions
check_postgres_running() {
    docker ps --filter name="$POSTGRES_CONTAINER" --format "{{.Names}}" | grep -q "$POSTGRES_CONTAINER"
}

check_postgres_ready() {
    docker exec "$POSTGRES_CONTAINER" pg_isready -p 5434 -U chiseai > /dev/null 2>&1
}

check_woodpecker_user() {
    docker exec "$POSTGRES_CONTAINER" psql -p 5434 -U chiseai -t -c "SELECT 1 FROM pg_roles WHERE rolname='woodpecker';" 2>/dev/null | grep -q "1"
}

check_woodpecker_db() {
    docker exec "$POSTGRES_CONTAINER" psql -p 5434 -U chiseai -t -c "SELECT 1 FROM pg_database WHERE datname='woodpecker';" 2>/dev/null | grep -q "1"
}

check_woodpecker_connection() {
    docker exec "$POSTGRES_CONTAINER" psql -p 5434 -U woodpecker -d woodpecker -c "SELECT 1;" > /dev/null 2>&1
}

check_woodpecker_server() {
    docker ps --filter name="$WOODPECKER_CONTAINER" --format "{{.Names}}" | grep -q "$WOODPECKER_CONTAINER"
}

check_woodpecker_logs() {
    local errors
    errors=$(docker logs "$WOODPECKER_CONTAINER" --since 5m 2>&1 | grep -i "database connection error\|pq:\|postgres error" | head -3 || true)
    echo "$errors"
}

# Main health check
echo "[$TIMESTAMP] Starting Woodpecker database health check..." >> "$LOG_FILE"

HEALTH_STATUS="OK"
ISSUES=()

# Check 1: PostgreSQL container running
if ! check_postgres_running; then
    HEALTH_STATUS="CRITICAL"
    ISSUES+=("PostgreSQL container '$POSTGRES_CONTAINER' is not running")
fi

# Check 2: PostgreSQL accepting connections
if ! check_postgres_ready; then
    HEALTH_STATUS="CRITICAL"
    ISSUES+=("PostgreSQL is not accepting connections")
fi

# Check 3: Woodpecker user exists
if ! check_woodpecker_user; then
    HEALTH_STATUS="CRITICAL"
    ISSUES+=("Woodpecker database user does not exist")
fi

# Check 4: Woodpecker database exists
if ! check_woodpecker_db; then
    HEALTH_STATUS="CRITICAL"
    ISSUES+=("Woodpecker database does not exist")
fi

# Check 5: Woodpecker can connect
if ! check_woodpecker_connection; then
    HEALTH_STATUS="CRITICAL"
    ISSUES+=("Woodpecker user cannot connect to database")
fi

# Check 6: Woodpecker server running
if ! check_woodpecker_server; then
    HEALTH_STATUS="WARNING"
    ISSUES+=("Woodpecker server container is not running")
fi

# Check 7: Recent errors in Woodpecker logs
LOG_ERRORS=$(check_woodpecker_logs)
if [ -n "$LOG_ERRORS" ]; then
    HEALTH_STATUS="WARNING"
    ISSUES+=("Recent database errors in Woodpecker logs: $LOG_ERRORS")
fi

# Report results
if [ "$HEALTH_STATUS" = "OK" ]; then
    echo "[$TIMESTAMP] OK: Woodpecker database healthy" >> "$LOG_FILE"
    exit 0
else
    for issue in "${ISSUES[@]}"; do
        send_alert "$HEALTH_STATUS" "$issue"
    done
    exit 1
fi
