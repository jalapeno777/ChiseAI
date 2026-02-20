#!/bin/bash
# Weekly automated pre-sprint cleanup for ChiseAI
# Runs every Monday at 6 AM (configurable)
# 
# Add to crontab:
# 0 6 * * 1 /home/tacopants/projects/ChiseAI/scripts/cron/weekly_cleanup.sh

set -euo pipefail

REPO_ROOT="/home/tacopants/projects/ChiseAI"
LOG_DIR="$REPO_ROOT/logs/cleanup"
DISCORD_WEBHOOK="${DISCORD_DEV_WEBHOOK_URL:-}"
DATE=$(date +%Y-%m-%d)
SPRINT_WEEK=$(date +%Y-W%V)

echo "[$(date)] Starting weekly cleanup routine..."

# Create log directory
mkdir -p "$LOG_DIR"

# Change to repo root
cd "$REPO_ROOT"

# Run cleanup with JSON output
JSON_OUTPUT=$(python3 scripts/ops/sprint_cleanup.py --execute --auto-fix-safe --json 2>&1) || EXIT_CODE=$?
EXIT_CODE=${EXIT_CODE:-0}

# Save JSON report
echo "$JSON_OUTPUT" > "$LOG_DIR/cleanup-$DATE.json"

# Generate human-readable report
REPORT=$(python3 scripts/ops/sprint_cleanup.py --execute --auto-fix-safe 2>&1)

# Save text report
echo "$REPORT" > "$LOG_DIR/cleanup-$DATE.txt"

# Determine status for Discord
if [ $EXIT_CODE -eq 0 ]; then
    STATUS="✅ READY"
    COLOR="3066993"  # Green
elif [ $EXIT_CODE -eq 1 ]; then
    STATUS="⚠️ READY WITH WARNINGS"
    COLOR="15158332"  # Orange
else
    STATUS="🔴 BLOCKED"
    COLOR="16711680"  # Red
fi

# Send Discord notification if webhook is configured
if [ -n "$DISCORD_WEBHOOK" ]; then
    # Extract counts from JSON
    CRITICAL=$(echo "$JSON_OUTPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('critical_count',0))" 2>/dev/null || echo "0")
    WARNINGS=$(echo "$JSON_OUTPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('warning_count',0))" 2>/dev/null || echo "0")
    ACTIONS=$(echo "$JSON_OUTPUT" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('actions_taken',[])))" 2>/dev/null || echo "0")
    
    curl -s -X POST "$DISCORD_WEBHOOK" \
        -H "Content-Type: application/json" \
        -d "{
            \"embeds\": [{
                \"title\": \"Weekly Cleanup Report - $SPRINT_WEEK\",
                \"description\": \"Status: $STATUS\",
                \"color\": $COLOR,
                \"fields\": [
                    {\"name\": \"Critical Issues\", \"value\": \"$CRITICAL\", \"inline\": true},
                    {\"name\": \"Warnings\", \"value\": \"$WARNINGS\", \"inline\": true},
                    {\"name\": \"Actions Taken\", \"value\": \"$ACTIONS\", \"inline\": true},
                    {\"name\": \"Log File\", \"value\": \"logs/cleanup/cleanup-$DATE.txt\", \"inline\": false}
                ],
                \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"
            }]
        }" > /dev/null
fi

echo "[$(date)] Cleanup routine completed with exit code: $EXIT_CODE"
echo "[$(date)] Log saved to: $LOG_DIR/cleanup-$DATE.txt"

# Exit with the same code as cleanup script
exit $EXIT_CODE
