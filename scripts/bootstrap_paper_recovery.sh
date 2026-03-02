#!/bin/bash
# PAPER-RECOVERY-001: Bootstrap script for paper recovery environment
# Sources .env file if it exists and validates all required environment variables
#
# Usage: source scripts/bootstrap_paper_recovery.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env"

# Source .env file if it exists
if [ -f "$ENV_FILE" ]; then
    echo "Loading environment from ${ENV_FILE}..."
    source "$ENV_FILE"
else
    echo "WARNING: ${ENV_FILE} not found. Using environment variables only."
    echo "Create ${ENV_FILE} from scripts/.env.example for easier configuration."
fi

# Set defaults for optional variables
export REDIS_HOST="${REDIS_HOST:-host.docker.internal}"
export REDIS_PORT="${REDIS_PORT:-6380}"
export DB_HOST="${DB_HOST:-host.docker.internal}"
export DB_PORT="${DB_PORT:-5434}"
export INFLUXDB_URL="${INFLUXDB_URL:-http://host.docker.internal:18087}"
export INFLUXDB_ORG="${INFLUXDB_ORG:-chiseai}"
export INFLUXDB_BUCKET="${INFLUXDB_BUCKET:-chiseai}"

# Validate required variables
MISSING_VARS=()

if [ -z "$INFLUXDB_TOKEN" ]; then
    MISSING_VARS+=("INFLUXDB_TOKEN")
fi

# Report validation results
if [ ${#MISSING_VARS[@]} -ne 0 ]; then
    echo ""
    echo "ERROR: The following required environment variables are not set:"
    for var in "${MISSING_VARS[@]}"; do
        echo "  - $var"
    done
    echo ""
    echo "To fix this:"
    echo "  1. Copy scripts/.env.example to scripts/.env"
    echo "  2. Edit scripts/.env and set the required values"
    echo "  3. Run: source scripts/bootstrap_paper_recovery.sh"
    echo ""
    echo "Or set them directly:"
    echo "  export INFLUXDB_TOKEN=your-token-here"
    echo ""
    return 1 2>/dev/null || exit 1
fi

# Success - show configuration
echo ""
echo "✓ Environment validated successfully"
echo ""
echo "Configuration:"
echo "  REDIS_HOST=${REDIS_HOST}"
echo "  REDIS_PORT=${REDIS_PORT}"
echo "  INFLUXDB_URL=${INFLUXDB_URL}"
echo "  INFLUXDB_ORG=${INFLUXDB_ORG}"
echo "  INFLUXDB_BUCKET=${INFLUXDB_BUCKET}"
echo "  INFLUXDB_TOKEN=************ (set)"
echo ""
echo "You can now run paper recovery scripts:"
echo "  python3 scripts/create_evidence_bundle.py"
echo "  ./scripts/redis_env_fix.sh python3 your_script.py"
echo ""
