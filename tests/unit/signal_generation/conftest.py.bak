"""Configure path for signal_generation unit tests."""

from __future__ import annotations

import sys
from pathlib import Path

# Add src directory to path for imports
_src_path = Path(__file__).parent.parent.parent / "src"
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))
