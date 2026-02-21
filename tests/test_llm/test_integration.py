"""
Integration tests for Z.ai (Zhipu AI) GLM-5 client.

These tests require a valid ZHIPU_API_KEY or ZAI_API_KEY environment variable.
Use --run-integration flag to run these tests.
"""

import json
import os
import pytest

from src.llm.zhipu_client import (
    ZhipuClient,
    ZaiMessage,
    ZaiAuthError,
)


# Check if integration tests should run
def should_run_integration():
    """Check if integration tests should run."""
    import sys

    return "--run-integration" in sys.argv


def get_api_key():
    """Get API key from environment."""
    return os.getenv("ZHIPU_API_KEY") or os.getenv("ZAI_API_KEY")


@pytest.fixture
def api_key():
    """Get API key or skip test."""
    if not should_run_integration():
        pytest.skip("Integration tests require --run-integration flag")
    key = get_api_key()
    if not key:
        pytest.skip("ZHIPU_API_KEY or ZAI_API_KEY environment variable required")
    return key


@pytest.fixture
def client(api_key):
    """Create a real client fixture."""
    return ZhipuClient(api_key=api_key)


class TestZaiIntegration:
    """Integration tests against live Z.ai API."""

    def test_simple_chat(self, client):
        """Test simple chat with live API."""
        response = client.simple_chat(
            "What is 2+2? Answer with just the number.",
            system_prompt="You are a helpful assistant.",
        )

        # Verify we got a non-empty response
        assert response
        assert isinstance(response, str)
        assert len(response) > 0
        print(f"\nResponse: {response}")

    def test_chat_with_messages(self, client):
        """Test chat with message objects."""
        messages = [
            ZaiMessage(role="system", content="You are a helpful math tutor."),
            ZaiMessage(role="user", content="What is the square root of 16?"),
        ]

        response = client.chat(messages, temperature=0.1)

        assert response.content
        assert response.id
        assert response.model == "glm-5"
        assert response.finish_reason
        assert response.usage is not None
        assert "prompt_tokens" in response.usage
        assert "completion_tokens" in response.usage

        print(f"\nResponse ID: {response.id}")
        print(f"Content: {response.content}")
        print(f"Usage: {response.usage}")

    def test_chat_response_structure(self, client):
        """Test that response structure is correct."""
        messages = [ZaiMessage(role="user", content="Say 'hello' and nothing else.")]

        response = client.chat(messages, max_tokens=10)

        # Verify response structure
        assert hasattr(response, "id")
        assert hasattr(response, "model")
        assert hasattr(response, "content")
        assert hasattr(response, "finish_reason")
        assert hasattr(response, "usage")
        assert hasattr(response, "raw_response")

        # Verify raw response is complete JSON
        assert isinstance(response.raw_response, dict)
        assert "choices" in response.raw_response
        assert len(response.raw_response["choices"]) > 0

        print(f"\nRaw Response:\n{json.dumps(response.raw_response, indent=2)}")

    def test_health_check(self, client):
        """Test health check with live API."""
        is_healthy = client.health_check()
        assert is_healthy is True

    def test_chat_with_temperature(self, client):
        """Test chat with different temperature settings."""
        messages = [
            ZaiMessage(role="user", content="Generate a random number between 1-100.")
        ]

        # Test with temperature 0 (more deterministic)
        response1 = client.chat(messages, temperature=0.0)

        # Test with temperature 1 (more random)
        response2 = client.chat(messages, temperature=1.0)

        # Both should return valid responses
        assert response1.content
        assert response2.content

        print(f"\nTemperature 0: {response1.content}")
        print(f"Temperature 1: {response2.content}")

    def test_chat_with_max_tokens(self, client):
        """Test chat with max_tokens limit."""
        messages = [ZaiMessage(role="user", content="Write a long story about a cat.")]

        response = client.chat(messages, max_tokens=20)

        # Response should be truncated due to max_tokens
        assert response.content
        assert response.finish_reason == "length"

        print(f"\nTruncated response: {response.content}")

    def test_invalid_api_key(self):
        """Test that invalid API key raises auth error."""
        if not should_run_integration():
            pytest.skip("Integration tests require --run-integration flag")
        client = ZhipuClient(api_key="invalid-key")

        with pytest.raises(ZaiAuthError) as exc_info:
            client.chat([ZaiMessage(role="user", content="Hello")])

        assert "Authentication failed" in str(exc_info.value)
