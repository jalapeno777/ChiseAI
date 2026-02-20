#!/bin/bash
# Woodpecker Database Connectivity Test Script
# Usage: ./test_woodpecker_db.sh
# Exit codes: 0 = success, 1 = failure

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "================================================"
echo "   Woodpecker Database Connectivity Test"
echo "================================================"
echo ""

# Track overall success
ALL_PASSED=true

# Test 1: Check PostgreSQL container is running
echo -n "[1/7] Checking PostgreSQL container... "
if docker ps --filter name=chiseai-postgres --format "{{.Names}}" | grep -q "chiseai-postgres"; then
    echo -e "${GREEN}✓ PASS${NC}"
else
    echo -e "${RED}✗ FAIL${NC}"
    echo "    ERROR: PostgreSQL container 'chiseai-postgres' is not running"
    ALL_PASSED=false
fi

# Test 2: Check PostgreSQL is accepting connections
echo -n "[2/7] Checking PostgreSQL accepts connections... "
if docker exec chiseai-postgres pg_isready -p 5434 -U chiseai > /dev/null 2>&1; then
    echo -e "${GREEN}✓ PASS${NC}"
else
    echo -e "${RED}✗ FAIL${NC}"
    echo "    ERROR: PostgreSQL is not accepting connections"
    ALL_PASSED=false
fi

# Test 3: Check woodpecker user exists
echo -n "[3/7] Checking 'woodpecker' database user exists... "
if docker exec chiseai-postgres psql -p 5434 -U chiseai -t -c "SELECT 1 FROM pg_roles WHERE rolname='woodpecker';" 2>/dev/null | grep -q "1"; then
    echo -e "${GREEN}✓ PASS${NC}"
else
    echo -e "${RED}✗ FAIL${NC}"
    echo "    ERROR: 'woodpecker' database user does not exist"
    ALL_PASSED=false
fi

# Test 4: Check woodpecker database exists
echo -n "[4/7] Checking 'woodpecker' database exists... "
if docker exec chiseai-postgres psql -p 5434 -U chiseai -t -c "SELECT 1 FROM pg_database WHERE datname='woodpecker';" 2>/dev/null | grep -q "1"; then
    echo -e "${GREEN}✓ PASS${NC}"
else
    echo -e "${RED}✗ FAIL${NC}"
    echo "    ERROR: 'woodpecker' database does not exist"
    ALL_PASSED=false
fi

# Test 5: Test connection as woodpecker user
echo -n "[5/7] Testing connection as 'woodpecker' user... "
if docker exec chiseai-postgres psql -p 5434 -U woodpecker -d woodpecker -c "SELECT current_user, current_database();" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ PASS${NC}"
else
    echo -e "${RED}✗ FAIL${NC}"
    echo "    ERROR: Cannot connect to database as 'woodpecker' user"
    ALL_PASSED=false
fi

# Test 6: Test write permissions
echo -n "[6/7] Testing write permissions... "
TEST_TABLE="test_$(date +%s)"
if docker exec chiseai-postgres psql -p 5434 -U woodpecker -d woodpecker -c "
    CREATE TABLE ${TEST_TABLE} (id serial PRIMARY KEY, test_data text);
    INSERT INTO ${TEST_TABLE} (test_data) VALUES ('woodpecker_test');
    SELECT test_data FROM ${TEST_TABLE} WHERE id = 1;
    DROP TABLE ${TEST_TABLE};
" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ PASS${NC}"
else
    echo -e "${RED}✗ FAIL${NC}"
    echo "    ERROR: Woodpecker user lacks write permissions"
    ALL_PASSED=false
fi

# Test 7: Verify isolation (woodpecker cannot access chiseai database)
echo -n "[7/7] Testing database isolation... "
if docker exec chiseai-postgres psql -p 5434 -U woodpecker -d chiseai -c "SELECT 1;" 2>&1 | grep -q "permission denied\|database"; then
    echo -e "${GREEN}✓ PASS${NC}"
else
    echo -e "${YELLOW}⚠ WARN${NC}"
    echo "    WARNING: Could not verify isolation (may need manual check)"
fi

# Test 8: Check Woodpecker server container (if running)
echo -n "[BONUS] Checking Woodpecker server container... "
if docker ps --filter name=woodpecker-server --format "{{.Names}}" | grep -q "woodpecker-server"; then
    echo -e "${GREEN}✓ PASS${NC} (running)"
    
    # Check recent logs for database connection
    echo -n "[BONUS] Checking Woodpecker server database connection... "
    if docker logs woodpecker-server --since 2m 2>&1 | grep -i "database\|postgres" | grep -iq "connected\|ready\|migrat"; then
        echo -e "${GREEN}✓ PASS${NC}"
    else
        echo -e "${YELLOW}⚠ WARN${NC} (check logs manually)"
    fi
else
    echo -e "${YELLOW}⚠ SKIP${NC} (not running)"
fi

echo ""
echo "================================================"

if [ "$ALL_PASSED" = true ]; then
    echo -e "${GREEN}All critical tests passed! ✓${NC}"
    echo "Woodpecker database is properly configured."
    echo ""
    echo "Connection string:"
    echo "  postgres://woodpecker:<password>@chiseai-postgres:5434/woodpecker?sslmode=disable"
    exit 0
else
    echo -e "${RED}Some tests failed! ✗${NC}"
    echo "Please review the errors above and check the setup."
    echo ""
    echo "Troubleshooting:"
    echo "  1. Ensure PostgreSQL container is running: docker ps | grep postgres"
    echo "  2. Check logs: docker logs chiseai-postgres"
    echo "  3. Run Terraform apply: terraform apply -target=null_resource.postgres_init_woodpecker"
    exit 1
fi
