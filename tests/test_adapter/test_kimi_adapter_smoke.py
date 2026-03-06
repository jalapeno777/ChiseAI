"""Smoke tests for Kimi Adapter.

Basic smoke tests to verify the FastAPI app imports and initializes correctly.

For ST-KIMI-ADAPTER-001: Kimi Adapter Wiring
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


def test_import_app():
    """Test that the FastAPI app can be imported."""
    from src.adapter.kimi.main import app

    assert app is not None


def test_app_instance():
    """Test that app is a FastAPI instance."""
    from fastapi import FastAPI
    from src.adapter.kimi.main import app

    assert isinstance(app, FastAPI)


def test_routes_registered():
    """Test that all expected routes are registered."""
    from src.adapter.kimi.main import app

    routes = [route.path for route in app.routes]

    # Check for expected routes
    assert "/health" in routes
    assert "/v1/models" in routes
    assert "/v1/chat/completions" in routes


def test_app_metadata():
    """Test app metadata is correctly configured."""
    from src.adapter.kimi.main import app

    assert app.title == "Kimi Adapter"
    assert app.description == "OpenAI-compatible adapter for Kimi Coding API"
    assert app.version == "1.0.0"


def test_environment_defaults():
    """Test that environment defaults are set correctly."""
    import importlib
    import os
    from unittest.mock import patch

    # Clear any existing env vars and reload module to test defaults
    with patch.dict(os.environ, {}, clear=True):
        import src.adapter.kimi.main as main_module

        importlib.reload(main_module)

        assert main_module.KIMI_BASE_URL == "https://api.moonshot.cn/v1"
        assert main_module.KIMI_MODEL == "kimi-k2.5"


if __name__ == "__main__":
    print("Running smoke tests...")

    test_import_app()
    print("✓ App imports successfully")

    test_app_instance()
    print("✓ App is FastAPI instance")

    test_routes_registered()
    print("✓ Routes are registered")

    test_app_metadata()
    print("✓ App metadata is correct")

    test_environment_defaults()
    print("✓ Environment defaults are correct")

    print("\nAll smoke tests passed!")
