#!/bin/bash
# Comprehensive CI Check Script for Sprint Q2-3 Branches

BRANCH="$1"
if [ -z "$BRANCH" ]; then
    echo "Usage: $0 <branch-name>"
    exit 1
fi

echo "========================================"
echo "CI CHECKS FOR BRANCH: $BRANCH"
echo "========================================"
echo ""

# Track results
SYNTAX_OK=0
IMPORT_OK=0
BLACK_OK=0
RUFF_OK=0
TESTS_OK=0
ISSUES=""

echo "--- 1. SYNTAX CHECK ---"
if python3 -m compileall src/ 2>&1 | grep -q "Error\|SyntaxError"; then
    echo "❌ SYNTAX ERRORS FOUND"
    python3 -m compileall src/ 2>&1 | grep -E "Error|SyntaxError"
    SYNTAX_OK=1
    ISSUES="${ISSUES}SYNTAX_ERROR;"
else
    echo "✅ Syntax check passed"
fi
echo ""

echo "--- 2. IMPORT CHECKS ---"
IMPORT_ERRORS=""

# Test each import
if ! python3 -c "import sys; sys.path.insert(0, 'src'); import ml.calibration" 2>&1; then
    IMPORT_ERRORS="${IMPORT_ERRORS}ml.calibration "
fi

if ! python3 -c "import sys; sys.path.insert(0, 'src'); import ml.training" 2>&1; then
    IMPORT_ERRORS="${IMPORT_ERRORS}ml.training "
fi

if ! python3 -c "import sys; sys.path.insert(0, 'src'); import api.cache" 2>&1; then
    IMPORT_ERRORS="${IMPORT_ERRORS}api.cache "
fi

if ! python3 -c "import sys; sys.path.insert(0, 'src'); import data.exchange.pooling" 2>&1; then
    IMPORT_ERRORS="${IMPORT_ERRORS}data.exchange.pooling "
fi

if ! python3 -c "import sys; sys.path.insert(0, 'src'); import signal_generation" 2>&1; then
    IMPORT_ERRORS="${IMPORT_ERRORS}signal_generation "
fi

if ! python3 -c "import sys; sys.path.insert(0, 'src'); import discord_alerts" 2>&1; then
    IMPORT_ERRORS="${IMPORT_ERRORS}discord_alerts "
fi

if [ -n "$IMPORT_ERRORS" ]; then
    echo "❌ IMPORT ERRORS: $IMPORT_ERRORS"
    IMPORT_OK=1
    ISSUES="${ISSUES}IMPORT_ERROR:$IMPORT_ERRORS;"
else
    echo "✅ All imports successful"
fi
echo ""

echo "--- 3. BLACK FORMATTING CHECK ---"
BLACK_OUTPUT=$(python3 -m black --check src/ 2>&1)
if echo "$BLACK_OUTPUT" | grep -q "would reformat"; then
    REFORMAT_COUNT=$(echo "$BLACK_OUTPUT" | grep -c "would reformat")
    echo "⚠️  Black would reformat $REFORMAT_COUNT files"
    echo "$BLACK_OUTPUT" | grep "would reformat"
    BLACK_OK=$REFORMAT_COUNT
    ISSUES="${ISSUES}BLACK_REFORMAT:$REFORMAT_COUNT;"
else
    echo "✅ Black formatting passed"
fi
echo ""

echo "--- 4. RUFF LINTING CHECK ---"
RUFF_OUTPUT=$(python3 -m ruff check src/ 2>&1)
RUFF_COUNT=$(echo "$RUFF_OUTPUT" | grep -c "^\[\|F401\|E501\|W" || echo "0")
if [ "$RUFF_COUNT" -gt 0 ]; then
    echo "⚠️  Ruff found $RUFF_COUNT issues"
    echo "$RUFF_OUTPUT" | head -20
    RUFF_OK=$RUFF_COUNT
    ISSUES="${ISSUES}RUFF_ISSUES:$RUFF_COUNT;"
else
    echo "✅ Ruff linting passed"
fi
echo ""

echo "--- 5. TEST EXECUTION ---"
TEST_FAILURES=""

# Calibration tests
if python3 -m pytest tests/test_ml/test_calibration/ -v --tb=short 2>&1 | grep -q "FAILED\|ERROR"; then
    FAIL_COUNT=$(python3 -m pytest tests/test_ml/test_calibration/ --tb=no 2>&1 | grep -oP "\d+ failed" | grep -oP "\d+" || echo "0")
    TEST_FAILURES="${TEST_FAILURES}calibration:$FAIL_COUNT "
fi

# Training tests
if python3 -m pytest tests/test_ml/test_training/ -v --tb=short 2>&1 | grep -q "FAILED\|ERROR"; then
    FAIL_COUNT=$(python3 -m pytest tests/test_ml/test_training/ --tb=no 2>&1 | grep -oP "\d+ failed" | grep -oP "\d+" || echo "0")
    TEST_FAILURES="${TEST_FAILURES}training:$FAIL_COUNT "
fi

# Discord batch tests
if python3 -m pytest tests/test_discord/test_discord_batch.py -v --tb=short 2>&1 | grep -q "FAILED\|ERROR"; then
    FAIL_COUNT=$(python3 -m pytest tests/test_discord/test_discord_batch.py --tb=no 2>&1 | grep -oP "\d+ failed" | grep -oP "\d+" || echo "0")
    TEST_FAILURES="${TEST_FAILURES}discord:$FAIL_COUNT "
fi

# Check for missing test files
if [ ! -f "tests/test_signal_generation/test_async_processor.py" ]; then
    TEST_FAILURES="${TEST_FAILURES}async_processor:MISSING_FILE "
fi

if [ ! -f "tests/test_api/test_pagination.py" ]; then
    TEST_FAILURES="${TEST_FAILURES}pagination:MISSING_FILE "
fi

if [ -n "$TEST_FAILURES" ]; then
    echo "❌ TEST FAILURES: $TEST_FAILURES"
    TEST_OK=1
    ISSUES="${ISSUES}TEST_FAILURE:$TEST_FAILURES;"
else
    echo "✅ All tests passed"
fi
echo ""

echo "========================================"
echo "SUMMARY FOR: $BRANCH"
echo "========================================"
echo "Syntax Issues: $SYNTAX_OK"
echo "Import Issues: $IMPORT_OK"
echo "Black Issues: $BLACK_OK files to reformat"
echo "Ruff Issues: $RUFF_OK"
echo "Test Issues: $TEST_OK"
echo ""
if [ -n "$ISSUES" ]; then
    echo "❌ ISSUES FOUND: $ISSUES"
    exit 1
else
    echo "✅ ALL CHECKS PASSED"
    exit 0
fi
