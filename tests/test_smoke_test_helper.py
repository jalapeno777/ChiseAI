"""Tests for smoke test helper - validates CI pipeline end-to-end."""

import pytest

from src.utils.smoke_test_helper import ci_pipeline_greeting


def test_greeting_with_name():
    """Test greeting with a valid name."""
    result = ci_pipeline_greeting("GitHub Actions")
    assert result == "Hello, GitHub Actions! CI pipeline is working."


def test_greeting_with_empty_name_raises():
    """Test that empty name raises ValueError."""
    with pytest.raises(ValueError, match="Name cannot be empty"):
        ci_pipeline_greeting("")
