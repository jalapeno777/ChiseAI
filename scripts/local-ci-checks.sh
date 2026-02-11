#!/usr/bin/env bash
set -euo pipefail

# Write deterministic outputs for CI log scanning and PR comments.
mkdir -p _bmad-output/ci

# Prevent environment contamination (e.g., sibling repos on PYTHONPATH).
export PYTHONPATH="$(pwd)/src"
export PYTHONNOUSERSITE=1

if python3 -c "import pytest_cov" >/dev/null 2>&1; then
  python3 -m pytest \
    --cov=src \
    --cov-report=term-missing \
    --cov-report=xml:_bmad-output/ci/coverage.xml \
    --cov-fail-under=80 \
    --junitxml=_bmad-output/ci/pytest-junit.xml \
    2>&1 | tee _bmad-output/ci/local-ci.log
else
  echo "pytest-cov not installed; running pytest without coverage enforcement" >&2
  python3 -m pytest \
    --junitxml=_bmad-output/ci/pytest-junit.xml \
    2>&1 | tee _bmad-output/ci/local-ci.log
fi
