#!/usr/bin/env bash
set -euo pipefail

export PYTHONPATH="${PYTHONPATH:-}:src"
python3 -m pytest --cov=src --cov-report=term-missing --cov-fail-under=80
