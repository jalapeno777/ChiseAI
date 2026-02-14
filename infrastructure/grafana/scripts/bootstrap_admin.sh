#!/bin/bash
#
# Grafana Admin Bootstrap Script
# Ensures the craig-admin user exists in Grafana
# This script is idempotent - safe to run multiple times
#

set -e

# Configuration from environment variables (passed via Terraform)
GRAFANA_URL="${GRAFANA_URL:-http://localhost:3001}"
GRAFANA_ADMIN_USER="${GRAFANA_ADMIN_USER:-admin}"
GRAFANA_ADMIN_PASSWORD="${GRAFANA_ADMIN_PASSWORD:-admin}"

# User to bootstrap
ADMIN_USER="${ADMIN_USER:-craig-admin}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-}"  # Must be provided via env var
ADMIN_EMAIL="${ADMIN_EMAIL:-craig@chiseai.local}"
ADMIN_NAME="${ADMIN_NAME:-Craig Admin}"

# Wait for Grafana to be ready
echo "[bootstrap] Waiting for Grafana to be ready at ${GRAFANA_URL}..."
for i in {1..30}; do
    if curl -s "${GRAFANA_URL}/api/health" > /dev/null 2>&1; then
        echo "[bootstrap] Grafana is ready"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "[bootstrap] ERROR: Grafana did not become ready within 30 seconds"
        exit 1
    fi
    sleep 1
done

# Check if admin user already exists
echo "[bootstrap] Checking if user '${ADMIN_USER}' exists..."
USER_CHECK=$(curl -s -w "%{http_code}" -o /tmp/user_check.json \
    -u "${GRAFANA_ADMIN_USER}:${GRAFANA_ADMIN_PASSWORD}" \
    "${GRAFANA_URL}/api/users/search?query=${ADMIN_USER}" 2>/dev/null || echo "000")

if [ "$USER_CHECK" = "200" ]; then
    # Check if user was found
    USER_COUNT=$(cat /tmp/user_check.json | grep -o '"totalCount":[0-9]*' | cut -d: -f2 || echo "0")
    if [ "$USER_COUNT" -gt 0 ]; then
        echo "[bootstrap] User '${ADMIN_USER}' already exists (totalCount: ${USER_COUNT})"
        echo "[bootstrap] Bootstrap complete - no action needed"
        exit 0
    fi
fi

# User doesn't exist, create it
if [ -z "$ADMIN_PASSWORD" ]; then
    echo "[bootstrap] ERROR: ADMIN_PASSWORD environment variable must be set"
    exit 1
fi

echo "[bootstrap] Creating user '${ADMIN_USER}'..."
CREATE_RESULT=$(curl -s -w "%{http_code}" -o /tmp/create_result.json \
    -X POST \
    -u "${GRAFANA_ADMIN_USER}:${GRAFANA_ADMIN_PASSWORD}" \
    -H "Content-Type: application/json" \
    -d "{
        \"name\": \"${ADMIN_NAME}\",
        \"email\": \"${ADMIN_EMAIL}\",
        \"login\": \"${ADMIN_USER}\",
        \"password\": \"${ADMIN_PASSWORD}\",
        \"OrgId\": 1
    }" \
    "${GRAFANA_URL}/api/admin/users" 2>/dev/null || echo "000")

if [ "$CREATE_RESULT" = "200" ] || [ "$CREATE_RESULT" = "201" ]; then
    echo "[bootstrap] User '${ADMIN_USER}' created successfully"
    
    # Get the user ID
    USER_ID=$(cat /tmp/create_result.json | grep -o '"id":[0-9]*' | head -1 | cut -d: -f2 || echo "")
    
    if [ -n "$USER_ID" ]; then
        echo "[bootstrap] User ID: ${USER_ID}"
        
        # Update user to Admin role
        echo "[bootstrap] Setting Admin role for user '${ADMIN_USER}'..."
        ROLE_RESULT=$(curl -s -w "%{http_code}" -o /tmp/role_result.json \
            -X PUT \
            -u "${GRAFANA_ADMIN_USER}:${GRAFANA_ADMIN_PASSWORD}" \
            -H "Content-Type: application/json" \
            -d '{
                "role": "Admin"
            }' \
            "${GRAFANA_URL}/api/org/users/${USER_ID}" 2>/dev/null || echo "000")
        
        if [ "$ROLE_RESULT" = "200" ]; then
            echo "[bootstrap] Admin role assigned successfully"
        else
            echo "[bootstrap] WARNING: Failed to set Admin role (HTTP ${ROLE_RESULT})"
            cat /tmp/role_result.json 2>/dev/null || true
        fi
    fi
    
    echo "[bootstrap] Bootstrap complete - user created and configured"
    exit 0
else
    echo "[bootstrap] ERROR: Failed to create user (HTTP ${CREATE_RESULT})"
    cat /tmp/create_result.json 2>/dev/null || true
    exit 1
fi
