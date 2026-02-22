"""Tests for KIMI client.

For CH-LLM-KIMI-001: KIMI K2.5 Integration
"""

import json
import os
from contextlib import asynccontextmanager
from unittest.mock import MagicMock, patch

import aiohttp
import pytest

from llm.kimi_client import (
    KimiClient,
    KimiConfig,
    KimiMessage,
    KimiResponse,
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


class TestKimiConfig:
    """Test KimiConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        with patch.dict(os.environ, {}, clear=True):
            config = KimiConfig()
            assert config.base_url == "https://api.kimi.com/coding/v1"
            assert config.model == "k2p5"
            assert config.timeout == 30.0
            assert config.max_retries == 3
            assert config.retry_delay == 1.0
            assert config.api_key is None
            assert config.accessible_models == []
            assert config.model_discovery_enabled is True

    def test_config_with_api_key(self):
        """Test configuration with explicit API key."""
        config = KimiConfig(api_key="test-key")
        assert config.api_key == "test-key"

    def test_config_from_env(self):
        """Test configuration loads API key from environment."""
        with patch.dict(os.environ, {"KIMI_API_KEY": "env-key"}):
            config = KimiConfig()
            assert config.api_key == "env-key"

    def test_config_explicit_overrides_env(self):
        """Test explicit API key overrides environment."""
        with patch.dict(os.environ, {"KIMI_API_KEY": "env-key"}):
            config = KimiConfig(api_key="explicit-key")
            assert config.api_key == "explicit-key"

    def test_config_with_accessible_models(self):
        """Test configuration with accessible models list."""
        config = KimiConfig(
            api_key="test-key", accessible_models=["kimi-for-coding", "k2p5"]
        )
        assert config.accessible_models == ["kimi-for-coding", "k2p5"]
        assert config.model_discovery_enabled is True

    def test_config_disable_model_discovery(self):
        """Test configuration with model discovery disabled."""
        config = KimiConfig(api_key="test-key", model_discovery_enabled=False)
        assert config.model_discovery_enabled is False


class TestKimiClient:
    """Test KimiClient functionality."""

    @pytest.fixture
    def client(self):
        """Create a KIMI client with test config."""
        config = KimiConfig(api_key="test-api-key")
        return KimiClient(config)

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
        client = KimiClient(KimiConfig(api_key="test-key"))
        assert client.is_configured() is True

    def test_is_configured_false(self):
        """Test is_configured returns False without API key."""
        with patch.dict(os.environ, {}, clear=True):
            client = KimiClient(KimiConfig(api_key=None))
            assert client.is_configured() is False

    def test_build_request_payload(self, client):
        """Test request payload building."""
        messages = [
            KimiMessage(role="system", content="System prompt"),
            KimiMessage(role="user", content="Hello"),
        ]
        payload = client._build_request_payload(
            messages=messages,
            temperature=0.5,
            top_p=0.9,
            max_tokens=100,
            stream=False,
        )

        assert payload["model"] == "k2p5"
        assert payload["temperature"] == 0.5
        assert payload["top_p"] == 0.9
        assert payload["max_tokens"] == 100
        assert payload["stream"] is False
        assert len(payload["messages"]) == 2
        assert payload["messages"][0]["role"] == "system"
        assert payload["messages"][0]["content"] == "System prompt"
        assert payload["messages"][1]["role"] == "user"

    @pytest.mark.asyncio
    async def test_chat_without_api_key(self):
        """Test chat fails gracefully without API key."""
        with patch.dict(os.environ, {}, clear=True):
            client = KimiClient(KimiConfig(api_key=None))
            messages = [KimiMessage(role="user", content="Hello")]

            response = await client.chat(messages)

            assert response.success is False
            assert "KIMI_API_KEY not configured" in response.error

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

        messages = [KimiMessage(role="user", content="Test")]
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

        messages = [KimiMessage(role="user", content="Test")]
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

        messages = [KimiMessage(role="user", content="Test")]
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

        messages = [KimiMessage(role="user", content="Test")]
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

        messages = [KimiMessage(role="user", content="Test")]
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

        messages = [KimiMessage(role="user", content="Test")]
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
                raise TimeoutError()

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

        messages = [KimiMessage(role="user", content="Test")]
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

        messages = [KimiMessage(role="user", content="Test")]
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
        assert health["model"] == "k2p5"
        assert health["error"] is None

    @pytest.mark.asyncio
    async def test_health_check_no_api_key(self):
        """Test health check without API key."""
        with patch.dict(os.environ, {}, clear=True):
            client = KimiClient(KimiConfig(api_key=None))

            health = await client.health_check()

            assert health["healthy"] is False
            assert health["connected"] is False
            assert "KIMI_API_KEY not configured" in health["error"]

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

    @pytest.mark.asyncio
    async def test_discover_models_success(self, client):
        """Test successful model discovery."""
        mock_cm = create_mock_response(
            status=200,
            json_data={
                "data": [
                    {"id": "kimi-for-coding"},
                    {"id": "k2p5"},
                ]
            },
        )

        mock_session = MagicMock()
        mock_session.get = mock_cm
        mock_session.closed = False

        client._session = mock_session

        models = await client.discover_models()

        assert models == ["kimi-for-coding", "k2p5"]
        assert client.config.accessible_models == ["kimi-for-coding", "k2p5"]

    @pytest.mark.asyncio
    async def test_discover_models_no_api_key(self):
        """Test model discovery without API key."""
        with patch.dict(os.environ, {}, clear=True):
            client = KimiClient(KimiConfig(api_key=None))
            models = await client.discover_models()
            assert models == []

    @pytest.mark.asyncio
    async def test_discover_models_http_error(self, client):
        """Test model discovery with HTTP error."""
        mock_cm = create_mock_response(status=403, text_data='{"error": "Forbidden"}')

        mock_session = MagicMock()
        mock_session.get = mock_cm
        mock_session.closed = False

        client._session = mock_session

        models = await client.discover_models()

        assert models == []

    def test_select_model_default(self, client):
        """Test model selection with default."""
        # No accessible models - should return default
        model = client._select_model()
        assert model == "k2p5"

    def test_select_model_with_accessible_models(self, client):
        """Test model selection falls back to accessible model."""
        client.config.accessible_models = ["kimi-for-coding"]
        # Requesting "k2p5" but only "kimi-for-coding" is accessible
        model = client._select_model()
        assert model == "kimi-for-coding"

    def test_select_model_requested_available(self, client):
        """Test model selection when requested model is available."""
        client.config.accessible_models = ["kimi-for-coding", "k2p5"]
        model = client._select_model("k2p5")
        assert model == "k2p5"

    def test_select_model_explicit_override(self, client):
        """Test explicit model selection."""
        client.config.accessible_models = ["kimi-for-coding"]
        model = client._select_model("kimi-for-coding")
        assert model == "kimi-for-coding"

    @pytest.mark.asyncio
    async def test_chat_403_error(self, client):
        """Test handling of 403 permission denied error."""
        mock_cm = create_mock_response(
            status=403,
            json_data={
                "error": {"message": "Access denied", "type": "access_terminated_error"}
            },
        )

        mock_session = MagicMock()
        mock_session.post = mock_cm
        mock_session.closed = False

        client._session = mock_session
        client.config.model_discovery_enabled = False  # Skip discovery

        messages = [KimiMessage(role="user", content="Test")]
        response = await client.chat(messages)

        assert response.success is False
        assert "Permission denied" in response.error
        assert "access_terminated_error" in response.error

    @pytest.mark.asyncio
    async def test_chat_403_error_with_fallback(self, client):
        """Test that chat tries model fallback on 403."""
        call_count = 0

        @asynccontextmanager
        async def mock_cm(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_response = MagicMock()
            # Always return 403 to simulate scope issue
            mock_response.status = 403

            async def mock_text():
                return json.dumps(
                    {
                        "error": {
                            "message": "Model not accessible",
                            "type": "model_access_error",
                        }
                    }
                )

            mock_response.text = mock_text
            yield mock_response

        mock_session = MagicMock()
        mock_session.post = mock_cm
        mock_session.closed = False

        client._session = mock_session
        client.config.model_discovery_enabled = False

        messages = [KimiMessage(role="user", content="Test")]
        response = await client.chat(messages)

        assert response.success is False
        assert "Permission denied" in response.error

    @pytest.mark.asyncio
    async def test_chat_with_model_discovery(self, client):
        """Test that chat triggers model discovery."""
        discovery_called = False

        async def mock_discover():
            nonlocal discovery_called
            discovery_called = True
            client.config.accessible_models = ["kimi-for-coding"]
            return ["kimi-for-coding"]

        client.discover_models = mock_discover

        mock_cm = create_mock_response(
            status=200,
            json_data={
                "choices": [{"message": {"content": "Hello"}, "finish_reason": "stop"}],
                "usage": {},
            },
        )

        mock_session = MagicMock()
        mock_session.post = mock_cm
        mock_session.closed = False

        client._session = mock_session

        messages = [KimiMessage(role="user", content="Test")]
        response = await client.chat(messages)

        assert discovery_called is True
        assert response.success is True


class TestKimiResponse:
    """Test KimiResponse dataclass."""

    def test_success_response(self):
        """Test successful response."""
        response = KimiResponse(
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
        response = KimiResponse(
            success=False,
            error="API key invalid",
        )
        assert response.success is False
        assert response.content is None
        assert response.error == "API key invalid"


class TestKimiMessage:
    """Test KimiMessage dataclass."""

    def test_message_creation(self):
        """Test message creation."""
        msg = KimiMessage(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"

    def test_system_message(self):
        """Test system message."""
        msg = KimiMessage(role="system", content="You are helpful")
        assert msg.role == "system"
        assert msg.content == "You are helpful"

    def test_assistant_message(self):
        """Test assistant message."""
        msg = KimiMessage(role="assistant", content="Hi there")
        assert msg.role == "assistant"
        assert msg.content == "Hi there"
