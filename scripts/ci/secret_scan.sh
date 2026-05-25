#!/usr/bin/env bash
# Secret scanning CI gate for ChiseAI
# Runs gitleaks on the current tree and fails if secrets are detected.
# Usage: bash scripts/ci/secret_scan.sh [--strict]
# --strict: Also fail on warnings (not just confirmed secrets)

set -euo pipefail

STRICT_MODE=false
if [[ "${1:-}" == "--strict" ]]; then
    STRICT_MODE=true
fi

echo "=== ChiseAI Secret Scan ==="
echo "Date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "Directory: $(pwd)"
echo ""

# Check if gitleaks is available
if ! command -v gitleaks &>/dev/null; then
    echo "ERROR: gitleaks not found. Install: https://github.com/gitleaks/gitleaks"
    exit 1
fi

echo "Gitleaks version: $(gitleaks version)"
echo ""

# Run gitleaks detect on current tree
echo "Scanning current tree for secrets..."
RESULT=$(gitleaks detect --source . --no-git --verbose 2>&1) || true

# Count findings
# gitleaks exits with code 1 if leaks found
FINDINGS=$(echo "$RESULT" | grep -c "Finding:" || true)

if [[ "$FINDINGS" -gt 0 ]]; then
    echo ""
    echo "=========================================="
    echo "SECRET SCAN FAILED: $FINDINGS finding(s) detected"
    echo "=========================================="
    echo ""
    echo "$RESULT"
    echo ""
    echo "If these are false positives, add them to .gitleaks.toml allowlist."
    exit 1
fi

# Also check for any git history leaks if in strict mode
if [[ "$STRICT_MODE" == "true" ]]; then
    echo "Strict mode: Scanning git history..."
    HISTORY_RESULT=$(gitleaks detect --source . --verbose 2>&1) || true
    HISTORY_FINDINGS=$(echo "$HISTORY_RESULT" | grep -c "Finding:" || true)

    if [[ "$HISTORY_FINDINGS" -gt 0 ]]; then
        echo ""
        echo "=========================================="
        echo "STRICT MODE: $HISTORY_FINDINGS finding(s) in git history"
        echo "=========================================="
        echo "$HISTORY_RESULT"
        exit 1
    fi
fi

echo ""
echo "=== Secret scan PASSED: No secrets detected ==="
exit 0
