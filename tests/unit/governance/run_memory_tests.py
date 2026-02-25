#!/usr/bin/env python3
"""
Test runner for memory stewardship tests that bypasses circular imports.
"""

import sys
import types
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

# Create mock modules to prevent circular imports
sys.modules["governance"] = types.ModuleType("governance")
sys.modules["governance.memory"] = types.ModuleType("governance.memory")

# Now run pytest
if __name__ == "__main__":
    import pytest

    sys.exit(
        pytest.main(
            [str(Path(__file__).parent / "test_memory_stewardship.py"), "-v"]
            + sys.argv[1:]
        )
    )
