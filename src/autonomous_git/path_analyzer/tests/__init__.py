"""Tests for the path analyzer module."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))


# Empty init file for tests package
