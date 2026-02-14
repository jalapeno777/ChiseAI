#!/bin/bash
#
# Grafana Persistence Test Script
# Tests that Grafana users persist across container recreation
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
GRAFANA_URL="${GRAFANA_URL:-http://localhost:3001}"
GRAFANA_ADMIN_USER="${GRAFANA_ADMIN_USER:-admin}"
GRAFANA_ADMIN_PASSWORD="${GRAFANA_ADMIN_PASSWORD:-admin}"
TEST_USER="craig-admin"

# Test counters
TESTS_PASSED=0
TESTS_FAILED=0

# Helper functions
log_info() {
    echo -e "${YELLOW}[INFO]${NC} $1"
}

log_pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
    ((TESTS_PASSED++))
}

log_fail() {
    echo -e "${RED}[FAIL]${NC} $1"
    ((TESTS_FAILED++))
}

# Wait for Grafana to be ready
wait_for_grafana() {
    log_info "Waiting for Grafana to be ready..."
    for i in {1..60}; do
        if curl -s "${GRAFANA_URL}/api/health" > /dev/null 2>&1; then
            log_pass "Grafana is ready"
            return 0
        fi
        sleep 1
    done
    log_fail "Grafana did not become ready within 60 seconds"
    return 1
}

# Check if user exists
check_user_exists() {
    local user=$1
    log_info "Checking if user '${user}' exists..."
    
    RESPONSE=$(curl -s -u "${GRAFANA_ADMIN_USER}:${GRAFANA_ADMIN_PASSWORD}" \
        "${GRAFANA_URL}/api/users/search?query=${user}" 2>/dev/null)
    
    if echo "$RESPONSE" | grep -q "\"login\":\"${user}\""; then
        log_pass "User '${user}' exists"
        return 0
    else
        log_fail "User '${user}' does not exist"
        return 1
    fi
}

# Get user count
get_user_count() {
    log_info "Getting user count..."
    
    RESPONSE=$(curl -s -u "${GRAFANA_ADMIN_USER}:${GRAFANA_ADMIN_PASSWORD}" \
        "${GRAFANA_URL}/api/users" 2>/dev/null)
    
    COUNT=$(echo "$RESPONSE" | grep -o '"id":[0-9]*' | wc -l)
    log_info "Current user count: ${COUNT}"
    echo "$COUNT"
}

# Test 1: Initial state - Grafana is running
test_initial_state() {
    echo ""
    echo "=== Test 1: Initial State ==="
    
    if docker ps --filter name=chiseai-grafana --filter status=running | grep -q chiseai-grafana; then
        log_pass "Grafana container is running"
    else
        log_fail "Grafana container is not running"
        return 1
    fi
    
    wait_for_grafana
    check_user_exists "$TEST_USER"
}

# Test 2: Stop and start container
test_stop_start() {
    echo ""
    echo "=== Test 2: Stop and Start Container ==="
    
    # Get initial user count
    INITIAL_COUNT=$(get_user_count)
    log_info "Initial user count: ${INITIAL_COUNT}"
    
    # Stop container
    log_info "Stopping Grafana container..."
    if docker stop chiseai-grafana > /dev/null 2>&1; then
        log_pass "Container stopped successfully"
    else
        log_fail "Failed to stop container"
        return 1
    fi
    
    # Start container
    log_info "Starting Grafana container..."
    if docker start chiseai-grafana > /dev/null 2>&1; then
        log_pass "Container started successfully"
    else
        log_fail "Failed to start container"
        return 1
    fi
    
    # Wait for Grafana
    wait_for_grafana
    
    # Check user still exists
    check_user_exists "$TEST_USER"
    
    # Check user count is the same
    FINAL_COUNT=$(get_user_count)
    log_info "Final user count: ${FINAL_COUNT}"
    
    if [ "$INITIAL_COUNT" -eq "$FINAL_COUNT" ]; then
        log_pass "User count preserved (${INITIAL_COUNT} users)"
    else
        log_fail "User count changed from ${INITIAL_COUNT} to ${FINAL_COUNT}"
    fi
}

# Test 3: Recreate container (simulates terraform apply)
test_recreate_container() {
    echo ""
    echo "=== Test 3: Recreate Container (Terraform Apply Simulation) ==="
    
    # Get initial user count
    INITIAL_COUNT=$(get_user_count)
    log_info "Initial user count: ${INITIAL_COUNT}"
    
    # Get volume name
    VOLUME_NAME=$(docker inspect chiseai-grafana --format='{{range .Mounts}}{{if eq .Destination "/var/lib/grafana"}}{{.Name}}{{end}}{{end}}')
    log_info "Grafana volume: ${VOLUME_NAME}"
    
    # Stop and remove container
    log_info "Stopping and removing container..."
    docker stop chiseai-grafana > /dev/null 2>&1 || true
    docker rm chiseai-grafana > /dev/null 2>&1 || true
    log_pass "Container removed"
    
    # Recreate container (simulating terraform apply)
    log_info "Recreating container..."
    docker run -d \
        --name chiseai-grafana \
        --network chiseai \
        -p 3001:3001 \
        -v "${VOLUME_NAME}:/var/lib/grafana" \
        -v "$(pwd)/infrastructure/grafana/provisioning:/etc/grafana/provisioning:ro" \
        -v "$(pwd)/infrastructure/grafana/scripts/bootstrap_admin.sh:/usr/local/bin/bootstrap_admin.sh:ro" \
        -e "GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_ADMIN_PASSWORD}" \
        -e "GF_SERVER_HTTP_PORT=3001" \
        -e "ADMIN_USER=craig-admin" \
        -e "ADMIN_PASSWORD=${GRAFANA_ADMIN_PASSWORD}" \
        -e "ADMIN_EMAIL=craig@chiseai.local" \
        -e "ADMIN_NAME=Craig Admin" \
        --label "project=chiseai" \
        --entrypoint '["/bin/sh", "-c", "chmod +x /usr/local/bin/bootstrap_admin.sh \u0026\u0026 /usr/local/bin/bootstrap_admin.sh \u0026 /run.sh"]' \
        grafana/grafana:10.4.2 > /dev/null 2>&1
    
    log_pass "Container recreated"
    
    # Wait for Grafana
    wait_for_grafana
    
    # Check user still exists
    check_user_exists "$TEST_USER"
    
    # Check user count is the same
    FINAL_COUNT=$(get_user_count)
    log_info "Final user count: ${FINAL_COUNT}"
    
    if [ "$INITIAL_COUNT" -eq "$FINAL_COUNT" ]; then
        log_pass "User count preserved (${INITIAL_COUNT} users)"
    else
        log_fail "User count changed from ${INITIAL_COUNT} to ${FINAL_COUNT}"
    fi
}

# Test 4: Bootstrap idempotency
test_bootstrap_idempotency() {
    echo ""
    echo "=== Test 4: Bootstrap Script Idempotency ==="
    
    # Run bootstrap script multiple times
    log_info "Running bootstrap script 3 times..."
    
    for i in {1..3}; do
        log_info "Run ${i}/3..."
        docker exec chiseai-grafana /usr/local/bin/bootstrap_admin.sh > /dev/null 2>&1 || true
    done
    
    # Check user still exists and only one instance
    RESPONSE=$(curl -s -u "${GRAFANA_ADMIN_USER}:${GRAFANA_ADMIN_PASSWORD}" \
        "${GRAFANA_URL}/api/users/search?query=${TEST_USER}" 2>/dev/null)
    
    TOTAL_COUNT=$(echo "$RESPONSE" | grep -o '"totalCount":[0-9]*' | head -1 | cut -d: -f2 || echo "0")
    
    if [ "$TOTAL_COUNT" -eq 1 ]; then
        log_pass "Idempotency verified - exactly one '${TEST_USER}' user exists"
    else
        log_fail "Idempotency failed - found ${TOTAL_COUNT} '${TEST_USER}' users"
    fi
}

# Main test execution
main() {
    echo "========================================"
    echo "Grafana Persistence Test Suite"
    echo "========================================"
    echo ""
    echo "Configuration:"
    echo "  Grafana URL: ${GRAFANA_URL}"
    echo "  Test User: ${TEST_USER}"
    echo ""
    
    # Check prerequisites
    if ! docker ps > /dev/null 2>&1; then
        echo "ERROR: Docker is not running or not accessible"
        exit 1
    fi
    
    if ! docker ps --filter name=chiseai-grafana | grep -q chiseai-grafana; then
        echo "WARNING: Grafana container not found. Some tests may fail."
        echo "Expected container name: chiseai-grafana"
    fi
    
    # Run tests
    test_initial_state
    test_stop_start
    test_recreate_container
    test_bootstrap_idempotency
    
    # Summary
    echo ""
    echo "========================================"
    echo "Test Summary"
    echo "========================================"
    echo -e "Tests Passed: ${GREEN}${TESTS_PASSED}${NC}"
    echo -e "Tests Failed: ${RED}${TESTS_FAILED}${NC}"
    echo ""
    
    if [ $TESTS_FAILED -eq 0 ]; then
        echo -e "${GREEN}All tests passed!${NC}"
        exit 0
    else
        echo -e "${RED}Some tests failed!${NC}"
        exit 1
    fi
}

# Show usage
usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Test Grafana persistence across container recreation.

OPTIONS:
    -h, --help          Show this help message
    --skip-recreate     Skip the container recreate test (destructive)
    --url URL           Grafana URL (default: http://localhost:3001)
    --user USER         Admin username (default: admin)
    --password PASS     Admin password (default: admin)

ENVIRONMENT VARIABLES:
    GRAFANA_URL         Grafana URL
    GRAFANA_ADMIN_USER  Admin username
    GRAFANA_ADMIN_PASSWORD  Admin password

EXAMPLES:
    # Run all tests
    $0

    # Run with custom credentials
    $0 --url http://grafana:3000 --user admin --password secret

    # Skip destructive recreate test
    $0 --skip-recreate

EOF
}

# Parse arguments
SKIP_RECREATE=false
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            usage
            exit 0
            ;;
        --skip-recreate)
            SKIP_RECREATE=true
            shift
            ;;
        --url)
            GRAFANA_URL="$2"
            shift 2
            ;;
        --user)
            GRAFANA_ADMIN_USER="$2"
            shift 2
            ;;
        --password)
            GRAFANA_ADMIN_PASSWORD="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# Run main
main
