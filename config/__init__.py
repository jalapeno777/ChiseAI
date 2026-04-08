"""Configuration package for ChiseAI.

This package provides configuration management for the trading system.
Submodules (bootstrap.py, trading_mode.py, etc.) are symlinks to src.config.*
and must be importable via `from config.bootstrap import bootstrap`.

This __init__ adds src/ to sys.path so that symlinked submodules can resolve
their transitive imports, but does NOT re-export names that would shadow
the submodule import paths.
"""

import sys
from pathlib import Path

# Add src to path so symlinked submodules (e.g. config/bootstrap.py -> src/config/bootstrap.py)
# can resolve their own imports (e.g. from config.env_loader import ...).
_src_path = Path(__file__).parent.parent / "src"
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))
