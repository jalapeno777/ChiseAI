"""Tests for Z.AI (Zhipu AI) client.

For CH-LLM-ZAI-001: Z.ai GLM-5 Integration
For LLM-VALIDATE-001: Thinking mode reasoning_content extraction
"""

import json
import os
from contextlib import asynccontextmanager
from unittest.mock import MagicMock, patch

import aiohttp
import pytest

from llm.zai_client import (
    ZaiClient,
    ZaiConfig,
    ZaiMessage,
    ZaiResponse,
)


def create_mock_response(status=200, json_data=None, text_data=None):
    """Create a mock response that works as an async context manager."""
    mock_response = MagicMock()
    mock_response.status = status

    if json_data is not None:
        text_data = json.dumps(json_data)

    async def mock_text():
        return text_data or ""

    mock_response.text = mock_text

    @asynccontextmanager
    async def mock_cm(*args, **kwargs):
        yield mock_response

    return mock_cm


class TestZaiConfig:
    """Test ZaiConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        with patch.dict(os.environ, {}, clear=True):
            config = ZaiConfig()
            assert (
                config.base_url
                == "https://api.z.ai/api/coding/paas/v4/chat/completions"
            )
            assert config.model == "glm-5"
            assert config.timeout == 30.0
            assert config.max_retries == 3
            assert config.retry_delay == 1.0
            assert config.api_key is None

    def test_config_with_api_key(self):
        """Test configuration with explicit API key."""
        config = ZaiConfig(api_key="test-key")
        assert config.api_key == "test-key"

    def test_config_from_env_z_ai_api_key(self):
        """Test configuration loads API key from Z_AI_API_KEY environment."""
        with patch.dict(os.environ, {"Z_AI_API_KEY": "env-key"}):
            config = ZaiConfig()
            assert config.api_key == "env-key"

    def test_config_from_env_zhipu_api_key(self):
        """Test configuration loads API key from ZHIPU_API_KEY environment."""
        with patch.dict(os.environ, {"ZHIPU_API_KEY": "zhipu-key"}, clear=True):
            config = ZaiConfig()
            assert config.api_key == "zhipu-key"

    def test_config_z_ai_api_key_takes_precedence(self):
        """Test Z_AI_API_KEY takes precedence over ZHIPU_API_KEY."""
        with patch.dict(
            os.environ, {"Z_AI_API_KEY": "zai-key", "ZHIPU_API_KEY": "zhipu-key"}
        ):
            config = ZaiConfig()
            assert config.api_key == "zai-key"

    def test_config_explicit_overrides_env(self):
        """Test explicit API key overrides environment."""
        with patch.dict(os.environ, {"Z_AI_API_KEY": "env-key"}):
            config = ZaiConfig(api_key="explicit-key")
            assert config.api_key == "explicit-key"


class TestZaiResponse:
    """Test ZaiResponse dataclass."""

    def test_response_with_reasoning_content(self):
        """Test response includes reasoning_content field."""
        response = ZaiResponse(
            success=True,
            content="Final answer",
            reasoning_content="Step-by-step thinking",
            finish_reason="stop",
        )
        assert response.success is True
        assert response.content == "Final answer"
        assert response.reasoning_content == "Step-by-step thinking"
        assert response.finish_reason == "stop"

    def test_response_without_reasoning_content(self):
        """Test response with reasoning_content as None."""
        response = ZaiResponse(
            success=True,
            content="Final answer",
            reasoning_content=None,
            finish_reason="stop",
        )
        assert response.success is True
        assert response.content == "Final answer"
        assert response.reasoning_content is None

    def test_response_default_reasoning_content(self):
        """Test response defaults reasoning_content to None."""
        response = ZaiResponse(success=True)
        assert response.reasoning_content is None


class TestZaiClient:
    """Test ZaiClient functionality."""

    @pytest.fixture
    def client(self):
        """Create a Z.AI client with test config."""
        config = ZaiConfig(api_key="test-api-key")
        return ZaiClient(config)

    @pytest.mark.asyncio
    async def test_client_context_manager(self, client):
        """Test async context manager."""
        async with client as c:
            assert c._session is not None
            assert not c._session.closed
        assert client._session is None

    @pytest.mark.asyncio
    async def test_parse_response_with_thinking_mode(self, client):
        """Test parsing response with thinking mode enabled.

        When thinking=True, API returns reasoning_content field.
        """
        mock_data = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "The answer is 42.",
                        "reasoning_content": "Let me think step by step:\\n1. First, I need to understand the problem\\n2. Then calculate",
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        }

        response = client._parse_response(mock_data)

        assert response.success is True
        assert response.content == "The answer is 42."
        assert (
            response.reasoning_content
            == "Let me think step by step:\\n1. First, I need to understand the problem\\n2. Then calculate"
        )
        assert response.finish_reason == "stop"
        assert response.usage == {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
        }

    @pytest.mark.asyncio
    async def test_parse_response_without_thinking_mode(self, client):
        """Test parsing response without thinking mode.

        When thinking=False, API does not return reasoning_content field.
        reasoning_content should be None.
        """
        mock_data = {
            "choices": [
                {
                    "message": {"role": "assistant", "content": "The answer is 42."},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 15, "total_tokens": 25},
        }

        response = client._parse_response(mock_data)

        assert response.success is True
        assert response.content == "The answer is 42."
        assert response.reasoning_content is None
        assert response.finish_reason == "stop"

    @pytest.mark.asyncio
    async def test_parse_response_empty_reasoning_content(self, client):
        """Test parsing response with empty reasoning_content."""
        mock_data = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "Simple answer.",
                        "reasoning_content": "",
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {},
        }

        response = client._parse_response(mock_data)

        assert response.success is True
        assert response.content == "Simple answer."
        # Empty string is still a valid value, should be preserved
        assert response.reasoning_content == ""

    @pytest.mark.asyncio
    async def test_parse_response_no_choices(self, client):
        """Test parsing response with no choices."""
        mock_data = {"choices": [], "usage": {}}

        response = client._parse_response(mock_data)

        assert response.success is False
        assert response.error == "No choices in response"
        assert response.reasoning_content is None

    @pytest.mark.asyncio
    async def test_parse_response_missing_message(self, client):
        """Test parsing response with missing message."""
        mock_data = {"choices": [{"finish_reason": "stop"}], "usage": {}}

        response = client._parse_response(mock_data)

        assert response.success is True
        assert response.content == ""  # Default value
        assert response.reasoning_content is None

    @pytest.mark.asyncio
    async def test_chat_without_thinking_mode(self, client):
        """Test chat method with thinking mode disabled."""
        mock_data = {
            "choices": [
                {
                    "message": {"role": "assistant", "content": "Final response"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"total_tokens": 40},
        }

        mock_cm = create_mock_response(status=200, json_data=mock_data)

        async with client:
            with patch.object(client._session, "post", return_value=mock_cm()):
                messages = [ZaiMessage(role="user", content="Hello")]
                response = await client.chat(messages, thinking=False)

                assert response.success is True
                assert response.content == "Final response"
                assert response.reasoning_content is None

    @pytest.mark.asyncio
    async def test_chat_simple_with_thinking(self, client):
        """Test simple chat interface with thinking enabled."""
        mock_data = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "Simple answer",
                        "reasoning_content": "I thought about this carefully",
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {"total_tokens": 25},
        }

        mock_cm = create_mock_response(status=200, json_data=mock_data)

        async with client:
            with patch.object(client._session, "post", return_value=mock_cm()):
                response = await client.chat_simple(
                    prompt="What is 2+2?", thinking=True
                )

                assert response.success is True
                assert response.content == "Simple answer"
                assert response.reasoning_content == "I thought about this carefully"

    def test_build_request_payload_with_thinking(self, client):
        """Test request payload includes thinking parameter."""
        messages = [ZaiMessage(role="user", content="Hello")]
        payload = client._build_request_payload(messages, thinking=True)

        assert payload["thinking"] == {"type": "enabled"}

    def test_build_request_payload_without_thinking(self, client):
        """Test request payload excludes thinking when disabled."""
        messages = [ZaiMessage(role="user", content="Hello")]
        payload = client._build_request_payload(messages, thinking=False)

        assert "thinking" not in payload

    def test_is_configured_true(self):
        """Test is_configured returns True when API key is set."""
        config = ZaiConfig(api_key="test-key")
        client = ZaiClient(config)
        assert client.is_configured() is True

    def test_is_configured_false(self):
        """Test is_configured returns False when API key is not set."""
        with patch.dict(os.environ, {}, clear=True):
            config = ZaiConfig()
            client = ZaiClient(config)
            assert client.is_configured() is False


class TestZaiMessage:
    """Test ZaiMessage dataclass."""

    def test_message_creation(self):
        """Test creating a message."""
        msg = ZaiMessage(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"

    def test_system_message(self):
        """Test creating a system message."""
        msg = ZaiMessage(role="system", content="You are helpful")
        assert msg.role == "system"
        assert msg.content == "You are helpful"

    def test_assistant_message(self):
        """Test creating an assistant message."""
        msg = ZaiMessage(role="assistant", content="Hi there")
        assert msg.role == "assistant"
        assert msg.content == "Hi there"
