#!/usr/bin/env bash
set -euo pipefail

export PYTHONPATH="${PYTHONPATH:-}:src"
# Tooling/integration modules can be high-IO and are better covered by
# explicit integration tests. Keep unit-test coverage focused on core library.
python3 -m pytest \
  --cov=chiseai \
  --cov-omit=src/chiseai/taiga_sync.py \
  --cov-report=term-missing \
  --cov-fail-under=80
