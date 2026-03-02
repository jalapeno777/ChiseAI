#!/bin/bash
# PAPER-RECOVERY-001: Redis Environment Fix Wrapper
# This script ensures correct Redis environment variables are set
# before running any Python scripts.
#
# Usage: source scripts/redis_env_fix.sh && python3 your_script.py
# Or: scripts/redis_env_fix.sh python3 your_script.py

export REDIS_HOST=host.docker.internal
export REDIS_PORT=6380

# Also set common aliases used by the codebase
export DB_HOST="${DB_HOST:-host.docker.internal}"
export DB_PORT="${DB_PORT:-5434}"
export INFLUXDB_URL="${INFLUXDB_URL:-http://host.docker.internal:18087}"
export INFLUXDB_ORG="${INFLUXDB_ORG:-chiseai}"
export INFLUXDB_BUCKET="${INFLUXDB_BUCKET:-chiseai}"
# Validate INFLUXDB_TOKEN is set (no default - security fix)
if [ -z "$INFLUXDB_TOKEN" ]; then
    echo "ERROR: INFLUXDB_TOKEN environment variable is not set"
    echo "Please set INFLUXDB_TOKEN before running this script"
    echo "Example: export INFLUXDB_TOKEN=your-token-here"
    exit 1
fi

echo "Redis environment fixed:"
echo "  REDIS_HOST=$REDIS_HOST"
echo "  REDIS_PORT=$REDIS_PORT"
echo "  INFLUXDB_URL=$INFLUXDB_URL"
echo "  INFLUXDB_ORG=$INFLUXDB_ORG"

# If arguments provided, execute them with the fixed environment
if [ $# -gt 0 ]; then
    exec "$@"
fi
