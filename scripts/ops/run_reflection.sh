#!/bin/bash
# Reflection Runner Wrapper Script
# 
# This wrapper sets up the proper Python environment to run the reflection_runner.py
# script, working around circular import issues in the governance package.
#
# Usage:
#   ./scripts/ops/run_reflection.sh --story-id=ST-TEST-001 --type=micro --action="test" --result="success"

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Set PYTHONPATH to include src
export PYTHONPATH="${PROJECT_ROOT}/src:${PYTHONPATH:-}"

# Create a temporary Python script that handles the import issues
python3 << 'PYTHON_SCRIPT'
import sys
import types
from pathlib import Path

# Get project root from command line
project_root = Path(__file__).parent.parent.parent

# Add src to path
sys.path.insert(0, str(project_root / "src"))

# Create mock src module to satisfy 'from src.xxx' imports
if 'src' not in sys.modules:
    src_module = types.ModuleType('src')
    sys.modules['src'] = src_module

# Import and run the actual runner
exec(open(str(project_root / "scripts" / "ops" / "reflection_runner.py")).read())
PYTHON_SCRIPT
