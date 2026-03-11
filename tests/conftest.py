from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

# Add src and project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Skip Streamlit dashboard tests unless explicitly enabled.

    Streamlit is deprecated for ChiseAI in the short term, and CI does not install it.
    Enable locally by setting CHISE_ENABLE_STREAMLIT_TESTS=1 and ensuring streamlit
    is installed.
    """

    enable = os.environ.get("CHISE_ENABLE_STREAMLIT_TESTS", "").strip() == "1"
    if enable:
        if importlib.util.find_spec("streamlit") is None:
            raise pytest.UsageError(
                "CHISE_ENABLE_STREAMLIT_TESTS=1 but streamlit is not installed."
            )
        return

    skip = pytest.mark.skip(
        reason=(
            "Streamlit tests disabled by default; set CHISE_ENABLE_STREAMLIT_TESTS=1 "
            "to run."
        )
    )

    for item in items:
        # Only skip tests that are known to require Streamlit.
        path = str(item.fspath)
        if path.endswith("test_risk_exposure_panel.py"):
            item.add_marker(skip)
