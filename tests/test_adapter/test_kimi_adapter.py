"""Tests for Kimi Adapter.

Tests the FastAPI adapter that provides OpenAI-compatible API for Kimi Coding.

For ST-KIMI-ADAPTER-001: Kimi Adapter Wiring
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

# Import after path setup
from src.adapter.kimi.main import (
    KIMI_MODEL,
    ChatCompletionRequest,
    ChatMessage,
    app,
)


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


class TestHealthEndpoint:
    """Test suite for /health endpoint."""

    def test_health_returns_200(self, client):
        """Test that /health endpoint returns 200 status."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["version"] == "1.0.0"
        assert "kimi_base_url" in data
        assert "kimi_model" in data


class TestModelsEndpoint:
    """Test suite for /v1/models endpoint."""

    def test_list_models_returns_model_list(self, client):
        """Test that /v1/models returns list of available models."""
        response = client.get("/v1/models")

        assert response.status_code == 200
        data = response.json()
        assert data["object"] == "list"
        assert len(data["data"]) == 1
        assert data["data"][0]["id"] == KIMI_MODEL
        assert data["data"][0]["owned_by"] == "kimi"


class TestRequestResponseMapping:
    """Test request/response mapping correctness."""

    def test_request_model_validation(self):
        """Test that request model validates correctly."""
        # Valid request
        request = ChatCompletionRequest(
            model=KIMI_MODEL,
            messages=[
                ChatMessage(role="system", content="You are helpful."),
                ChatMessage(role="user", content="Hello!"),
            ],
            temperature=0.7,
            max_tokens=500,
        )
        assert request.model == KIMI_MODEL
        assert len(request.messages) == 2
        assert request.temperature == 0.7

    def test_request_temperature_bounds(self):
        """Test temperature validation bounds."""
        # Temperature too high
        with pytest.raises(Exception):  # pydantic.ValidationError
            ChatCompletionRequest(
                model=KIMI_MODEL,
                messages=[ChatMessage(role="user", content="Hello!")],
                temperature=3.0,  # Invalid: > 2.0
            )

    def test_request_max_tokens_bounds(self):
        """Test max_tokens validation bounds."""
        # max_tokens too low
        with pytest.raises(Exception):  # pydantic.ValidationError
            ChatCompletionRequest(
                model=KIMI_MODEL,
                messages=[ChatMessage(role="user", content="Hello!")],
                max_tokens=0,  # Invalid: < 1
            )

    def test_default_values(self):
        """Test default values in request model."""
        request = ChatCompletionRequest(
            model=KIMI_MODEL, messages=[ChatMessage(role="user", content="Hello!")]
        )
        assert request.temperature == 0.7
        assert request.top_p == 0.95
        assert request.max_tokens == 2048
        assert request.stream is False


class TestErrorHandling:
    """Test error handling."""

    def test_error_response_format(self, client):
        """Test that error responses follow OpenAI format."""
        # Test with invalid JSON to trigger validation error
        response = client.post(
            "/v1/chat/completions",
            data="invalid json",
            headers={"Content-Type": "application/json"},
        )

        # Should get a validation error
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
