"""Tests for MiniMax client.

For CH-LLM-MINIMAX-001: MiniMax 2.5 Integration
"""

import asyncio
import json
import os
from contextlib import asynccontextmanager
from unittest.mock import MagicMock, patch

import aiohttp
import pytest

from llm.minimax_client import (
    MiniMaxClient,
    MiniMaxConfig,
    MiniMaxMessage,
    MiniMaxResponse,
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


class TestMiniMaxConfig:
    """Test MiniMaxConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        with patch.dict(os.environ, {}, clear=True):
            config = MiniMaxConfig()
            assert config.base_url == "https://api.minimax.io/v1/text/chatcompletion_v2"
            assert config.model == "MiniMax-M2.5"
            assert config.timeout == 30.0
            assert config.max_retries == 3
            assert config.retry_delay == 1.0
            assert config.api_key is None

    def test_config_with_api_key(self):
        """Test configuration with explicit API key."""
        config = MiniMaxConfig(api_key="test-key")
        assert config.api_key == "test-key"

    def test_config_from_env(self):
        """Test configuration loads API key from environment."""
        with patch.dict(os.environ, {"MINIMAX_API_KEY": "env-key"}):
            config = MiniMaxConfig()
            assert config.api_key == "env-key"

    def test_config_explicit_overrides_env(self):
        """Test explicit API key overrides environment."""
        with patch.dict(os.environ, {"MINIMAX_API_KEY": "env-key"}):
            config = MiniMaxConfig(api_key="explicit-key")
            assert config.api_key == "explicit-key"


class TestMiniMaxClient:
    """Test MiniMaxClient functionality."""

    @pytest.fixture
    def client(self):
        """Create a MiniMax client with test config."""
        config = MiniMaxConfig(api_key="test-api-key")
        return MiniMaxClient(config)

    @pytest.mark.asyncio
    async def test_client_context_manager(self, client):
        """Test async context manager."""
        async with client as c:
            assert c._session is not None
        assert client._session is None or client._session.closed

    @pytest.mark.asyncio
    async def test_connect_creates_session(self, client):
        """Test connect creates aiohttp session."""
        await client.connect()
        assert client._session is not None
        await client.close()

    @pytest.mark.asyncio
    async def test_close_session(self, client):
        """Test close properly closes session."""
        await client.connect()
        await client.close()
        assert client._session is None

    def test_is_configured_true(self):
        """Test is_configured returns True with API key."""
        client = MiniMaxClient(MiniMaxConfig(api_key="test-key"))
        assert client.is_configured() is True

    def test_is_configured_false(self):
        """Test is_configured returns False without API key."""
        with patch.dict(os.environ, {}, clear=True):
            client = MiniMaxClient(MiniMaxConfig(api_key=None))
            assert client.is_configured() is False

    def test_build_request_payload(self, client):
        """Test request payload building."""
        messages = [
            MiniMaxMessage(role="system", content="System prompt", name="MiniMax AI"),
            MiniMaxMessage(role="user", content="Hello", name="User"),
        ]
        payload = client._build_request_payload(
            messages=messages,
            temperature=0.5,
            top_p=0.9,
            max_tokens=100,
            stream=False,
        )

        assert payload["model"] == "MiniMax-M2.5"
        assert payload["temperature"] == 0.5
        assert payload["top_p"] == 0.9
        assert payload["max_completion_tokens"] == 100
        assert payload["stream"] is False
        assert len(payload["messages"]) == 2
        assert payload["messages"][0]["role"] == "system"
        assert payload["messages"][0]["name"] == "MiniMax AI"
        assert payload["messages"][1]["role"] == "user"

    @pytest.mark.asyncio
    async def test_chat_without_api_key(self):
        """Test chat fails gracefully without API key."""
        with patch.dict(os.environ, {}, clear=True):
            client = MiniMaxClient(MiniMaxConfig(api_key=None))
            messages = [MiniMaxMessage(role="user", content="Hello")]

            response = await client.chat(messages)

            assert response.success is False
            assert "MINIMAX_API_KEY not configured" in response.error

    @pytest.mark.asyncio
    async def test_chat_simple(self, client):
        """Test simple chat interface."""
        mock_cm = create_mock_response(
            status=200,
            json_data={
                "choices": [
                    {"message": {"content": "Hello!"}, "finish_reason": "stop"}
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )

        mock_session = MagicMock()
        mock_session.post = mock_cm
        mock_session.closed = False

        client._session = mock_session

        response = await client.chat_simple(
            prompt="Hello",
            system_message="You are helpful",
        )

        assert response.success is True
        assert response.content == "Hello!"

    @pytest.mark.asyncio
    async def test_chat_success(self, client):
        """Test successful chat completion."""
        mock_cm = create_mock_response(
            status=200,
            json_data={
                "id": "test-id",
                "choices": [
                    {
                        "message": {"content": "Test response"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                },
            },
        )

        mock_session = MagicMock()
        mock_session.post = mock_cm
        mock_session.closed = False

        client._session = mock_session

        messages = [MiniMaxMessage(role="user", content="Test")]
        response = await client.chat(messages)

        assert response.success is True
        assert response.content == "Test response"
        assert response.finish_reason == "stop"
        assert response.usage == {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
        }
        assert response.raw_response is not None

    @pytest.mark.asyncio
    async def test_chat_authentication_error(self, client):
        """Test handling of 401 authentication error."""
        mock_cm = create_mock_response(
            status=401, text_data='{"error": "Unauthorized"}'
        )

        mock_session = MagicMock()
        mock_session.post = mock_cm
        mock_session.closed = False

        client._session = mock_session

        messages = [MiniMaxMessage(role="user", content="Test")]
        response = await client.chat(messages)

        assert response.success is False
        assert "Authentication failed" in response.error

    @pytest.mark.asyncio
    async def test_chat_rate_limit_error(self, client):
        """Test handling of 429 rate limit error."""
        mock_cm = create_mock_response(
            status=429, text_data='{"error": "Rate limited"}'
        )

        mock_session = MagicMock()
        mock_session.post = mock_cm
        mock_session.closed = False

        client._session = mock_session

        messages = [MiniMaxMessage(role="user", content="Test")]
        response = await client.chat(messages)

        assert response.success is False
        assert "Rate limit exceeded" in response.error

    @pytest.mark.asyncio
    async def test_chat_server_error_with_retry(self, client):
        """Test retry on server error."""
        # First call returns 500, second returns 200
        call_count = 0

        @asynccontextmanager
        async def mock_cm(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_response = MagicMock()
            if call_count == 1:
                mock_response.status = 500

                async def mock_text():
                    return '{"error": "Server error"}'

                mock_response.text = mock_text
            else:
                mock_response.status = 200

                async def mock_text():
                    return json.dumps(
                        {
                            "choices": [
                                {
                                    "message": {"content": "Success after retry"},
                                    "finish_reason": "stop",
                                }
                            ],
                            "usage": {},
                        }
                    )

                mock_response.text = mock_text
            yield mock_response

        mock_session = MagicMock()
        mock_session.post = mock_cm
        mock_session.closed = False

        client._session = mock_session
        client.config.retry_delay = 0.001  # Fast retry for testing

        messages = [MiniMaxMessage(role="user", content="Test")]
        response = await client.chat(messages)

        assert response.success is True
        assert response.content == "Success after retry"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_chat_client_error_no_retry(self, client):
        """Test no retry on client error (4xx except 429)."""
        call_count = 0

        @asynccontextmanager
        async def mock_cm(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_response = MagicMock()
            mock_response.status = 400

            async def mock_text():
                return '{"error": "Bad request"}'

            mock_response.text = mock_text
            yield mock_response

        mock_session = MagicMock()
        mock_session.post = mock_cm
        mock_session.closed = False

        client._session = mock_session

        messages = [MiniMaxMessage(role="user", content="Test")]
        response = await client.chat(messages)

        assert response.success is False
        assert "HTTP 400" in response.error
        assert call_count == 1  # No retry

    @pytest.mark.asyncio
    async def test_chat_network_error_with_retry(self, client):
        """Test retry on network error."""
        call_count = 0

        class FailingCM:
            async def __aenter__(self):
                nonlocal call_count
                call_count += 1
                raise aiohttp.ClientError("Connection failed")

            async def __aexit__(self, *args):
                return False

        def mock_cm(*args, **kwargs):
            return FailingCM()

        mock_session = MagicMock()
        mock_session.post = mock_cm
        mock_session.closed = False

        client._session = mock_session
        client.config.retry_delay = 0.001  # Fast retry for testing
        client.config.max_retries = 2

        messages = [MiniMaxMessage(role="user", content="Test")]
        response = await client.chat(messages)

        assert response.success is False
        assert "Max retries exceeded" in response.error
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_chat_timeout_with_retry(self, client):
        """Test retry on timeout."""
        call_count = 0

        class TimeoutCM:
            async def __aenter__(self):
                nonlocal call_count
                call_count += 1
                raise asyncio.TimeoutError()

            async def __aexit__(self, *args):
                return False

        def mock_cm(*args, **kwargs):
            return TimeoutCM()

        mock_session = MagicMock()
        mock_session.post = mock_cm
        mock_session.closed = False

        client._session = mock_session
        client.config.retry_delay = 0.001  # Fast retry for testing
        client.config.max_retries = 2

        messages = [MiniMaxMessage(role="user", content="Test")]
        response = await client.chat(messages)

        assert response.success is False
        assert "Max retries exceeded" in response.error

    @pytest.mark.asyncio
    async def test_chat_no_choices_in_response(self, client):
        """Test handling of response without choices."""
        mock_cm = create_mock_response(
            status=200,
            json_data={
                "id": "test-id",
                "usage": {},
            },
        )

        mock_session = MagicMock()
        mock_session.post = mock_cm
        mock_session.closed = False

        client._session = mock_session

        messages = [MiniMaxMessage(role="user", content="Test")]
        response = await client.chat(messages)

        assert response.success is False
        assert "No choices in response" in response.error

    @pytest.mark.asyncio
    async def test_health_check_success(self, client):
        """Test health check with successful response."""
        mock_cm = create_mock_response(
            status=200,
            json_data={
                "choices": [{"message": {"content": "Hi"}, "finish_reason": "stop"}],
                "usage": {},
            },
        )

        mock_session = MagicMock()
        mock_session.post = mock_cm
        mock_session.closed = False

        client._session = mock_session

        health = await client.health_check()

        assert health["healthy"] is True
        assert health["connected"] is True
        assert health["model"] == "MiniMax-M2.5"
        assert health["error"] is None

    @pytest.mark.asyncio
    async def test_health_check_no_api_key(self):
        """Test health check without API key."""
        with patch.dict(os.environ, {}, clear=True):
            client = MiniMaxClient(MiniMaxConfig(api_key=None))

            health = await client.health_check()

            assert health["healthy"] is False
            assert health["connected"] is False
            assert "MINIMAX_API_KEY not configured" in health["error"]

    @pytest.mark.asyncio
    async def test_health_check_api_error(self, client):
        """Test health check with API error."""
        mock_cm = create_mock_response(
            status=500, text_data='{"error": "Server error"}'
        )

        mock_session = MagicMock()
        mock_session.post = mock_cm
        mock_session.closed = False

        client._session = mock_session

        health = await client.health_check()

        assert health["healthy"] is False
        assert health["connected"] is True
        assert health["error"] is not None


class TestMiniMaxResponse:
    """Test MiniMaxResponse dataclass."""

    def test_success_response(self):
        """Test successful response."""
        response = MiniMaxResponse(
            success=True,
            content="Hello",
            usage={"prompt_tokens": 10, "completion_tokens": 5},
            finish_reason="stop",
        )
        assert response.success is True
        assert response.content == "Hello"
        assert response.error is None

    def test_error_response(self):
        """Test error response."""
        response = MiniMaxResponse(
            success=False,
            error="API key invalid",
        )
        assert response.success is False
        assert response.content is None
        assert response.error == "API key invalid"


class TestMiniMaxMessage:
    """Test MiniMaxMessage dataclass."""

    def test_message_with_name(self):
        """Test message with name."""
        msg = MiniMaxMessage(role="user", content="Hello", name="User")
        assert msg.role == "user"
        assert msg.content == "Hello"
        assert msg.name == "User"

    def test_message_without_name(self):
        """Test message without name."""
        msg = MiniMaxMessage(role="assistant", content="Hi there")
        assert msg.role == "assistant"
        assert msg.content == "Hi there"
        assert msg.name is None
