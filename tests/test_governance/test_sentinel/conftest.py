"""
Conftest for sentinel tests.

This conftest sets up the import path to avoid triggering
the governance/__init__.py which has dependencies on broken modules.
"""

import sys
from pathlib import Path

# Add the src directory directly to the path
src_path = Path(__file__).parent.parent.parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

# Import sentinel modules directly without triggering governance/__init__.py
# This is done by importing from the full path rather than the package
