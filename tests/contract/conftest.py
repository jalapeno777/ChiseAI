"""Pytest configuration for contract tests."""

from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers for contract tests."""
    config.addinivalue_line(
        "markers",
        "contract: marks tests as contract tests (validate external service contracts)",
    )
