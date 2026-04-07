"""Configure path for signal_generation unit tests."""

from __future__ import annotations

import sys
from pathlib import Path

# Add src directory to path for imports
# Path: tests/unit/signal_generation/conftest.py
#   parent = tests/unit/signal_generation
#   parent.parent = tests/unit
#   parent.parent.parent = tests
#   parent.parent.parent.parent = project root (contains src/)
_src_path = Path(__file__).parent.parent.parent.parent / "src"
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))
