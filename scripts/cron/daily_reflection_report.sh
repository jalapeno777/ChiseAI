#!/bin/bash
# Daily Reflection Report Cron Wrapper
# Story: ST-DAILY-REFLECTION-001
#
# This script is called by cron at 09:00 UTC daily
# It generates the daily reflection report and posts to Discord

set -euo pipefail

# Configuration
SCRIPT_DIR="/home/tacopants/projects/ChiseAI"
SCRIPT_PATH="$SCRIPT_DIR/scripts/standup/generate_daily_reflection_report.py"
LOG_DIR="$SCRIPT_DIR/logs/daily-reflection"
DATE_STAMP=$(date +%Y%m%d)
LOG_FILE="$LOG_DIR/daily_$DATE_STAMP.log"

# Ensure log directory exists
mkdir -p "$LOG_DIR"

# Log start
echo "========================================" >> "$LOG_FILE"
echo "Daily Reflection Report - $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"

# Run the report
cd "$SCRIPT_DIR"
/usr/bin/python3 "$SCRIPT_PATH" --post-discord --verbose >> "$LOG_FILE" 2>&1

# Check exit status
EXIT_CODE=$?
if [ $EXIT_CODE -eq 0 ]; then
    echo "✓ Report completed successfully" >> "$LOG_FILE"
else
    echo "❌ Report failed with exit code $EXIT_CODE" >> "$LOG_FILE"
fi

echo "" >> "$LOG_FILE"

exit $EXIT_CODE
