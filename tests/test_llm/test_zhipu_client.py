"""
Unit tests for Z.ai (Zhipu AI) GLM-5 client.
"""

import json
import os
from unittest.mock import Mock, patch

import pytest
from src.llm.zhipu_client import (
    ZaiAuthError,
    ZaiError,
    ZaiMessage,
    ZaiRateLimitError,
    ZaiResponse,
    ZaiServerError,
    ZhipuClient,
)


class TestZaiMessage:
    """Tests for ZaiMessage dataclass."""

    def test_message_creation(self):
        """Test creating a message."""
        msg = ZaiMessage(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"

    def test_message_to_dict(self):
        """Test converting message to dict."""
        msg = ZaiMessage(role="system", content="You are helpful")
        result = msg.to_dict()
        assert result == {"role": "system", "content": "You are helpful"}


class TestZhipuClientInitialization:
    """Tests for ZhipuClient initialization."""

    def test_init_with_api_key(self):
        """Test initialization with explicit API key."""
        client = ZhipuClient(api_key="test-key")
        assert client.api_key == "test-key"
        assert client.endpoint == ZhipuClient.DEFAULT_ENDPOINT
        assert client.model == ZhipuClient.DEFAULT_MODEL

    def test_init_with_env_var_zhipu(self):
        """Test initialization with ZHIPU_API_KEY env var."""
        with patch.dict(os.environ, {"ZHIPU_API_KEY": "env-zhipu-key"}):
            client = ZhipuClient()
            assert client.api_key == "env-zhipu-key"

    def test_init_with_env_var_zai(self):
        """Test initialization with ZAI_API_KEY env var."""
        with patch.dict(os.environ, {"ZAI_API_KEY": "env-zai-key"}, clear=True):
            client = ZhipuClient()
            assert client.api_key == "env-zai-key"

    def test_init_zhipu_takes_precedence(self):
        """Test ZHIPU_API_KEY takes precedence over ZAI_API_KEY."""
        with patch.dict(
            os.environ, {"ZHIPU_API_KEY": "zhipu-key", "ZAI_API_KEY": "zai-key"}
        ):
            client = ZhipuClient()
            assert client.api_key == "zhipu-key"

    def test_init_without_api_key_raises(self):
        """Test initialization without API key raises error."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ZaiAuthError) as exc_info:
                ZhipuClient()
            assert "API key required" in str(exc_info.value)

    def test_init_with_custom_endpoint(self):
        """Test initialization with custom endpoint."""
        client = ZhipuClient(
            api_key="test-key", endpoint="https://custom.api.com/v1/chat"
        )
        assert client.endpoint == "https://custom.api.com/v1/chat"

    def test_init_with_custom_model(self):
        """Test initialization with custom model."""
        client = ZhipuClient(api_key="test-key", model="glm-4")
        assert client.model == "glm-4"

    def test_init_with_custom_timeout(self):
        """Test initialization with custom timeout."""
        client = ZhipuClient(api_key="test-key", timeout=120)
        assert client.timeout == 120

    def test_init_with_custom_retries(self):
        """Test initialization with custom retry settings."""
        client = ZhipuClient(api_key="test-key", max_retries=5, backoff_factor=1.5)
        assert client.max_retries == 5
        assert client.backoff_factor == 1.5


class TestZhipuClientChat:
    """Tests for ZhipuClient.chat method."""

    @pytest.fixture
    def client(self):
        """Create a client fixture."""
        return ZhipuClient(api_key="test-key")

    @pytest.fixture
    def mock_success_response(self):
        """Create a mock successful API response."""
        mock = Mock()
        mock.status_code = 200
        mock.json.return_value = {
            "id": "chat-123",
            "model": "glm-5",
            "choices": [
                {
                    "message": {"role": "assistant", "content": "Hello!"},
                    "finish_reason": "stop",
                    "index": 0,
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
        return mock

    def test_chat_with_message_objects(self, client, mock_success_response):
        """Test chat with ZaiMessage objects."""
        with patch.object(client._session, "post", return_value=mock_success_response):
            messages = [
                ZaiMessage(role="system", content="You are helpful"),
                ZaiMessage(role="user", content="Hello"),
            ]
            response = client.chat(messages)

            assert isinstance(response, ZaiResponse)
            assert response.content == "Hello!"
            assert response.model == "glm-5"
            assert response.finish_reason == "stop"

    def test_chat_with_dict_messages(self, client, mock_success_response):
        """Test chat with dict messages."""
        with patch.object(client._session, "post", return_value=mock_success_response):
            messages = [
                {"role": "system", "content": "You are helpful"},
                {"role": "user", "content": "Hello"},
            ]
            response = client.chat(messages)

            assert response.content == "Hello!"

    def test_chat_with_mixed_messages(self, client, mock_success_response):
        """Test chat with mixed message types."""
        with patch.object(client._session, "post", return_value=mock_success_response):
            messages = [
                ZaiMessage(role="system", content="You are helpful"),
                {"role": "user", "content": "Hello"},
            ]
            response = client.chat(messages)

            assert response.content == "Hello!"

    def test_chat_invalid_message_type(self, client):
        """Test chat with invalid message type raises error."""
        with pytest.raises(ValueError) as exc_info:
            client.chat(["invalid message"])
        assert "Invalid message type" in str(exc_info.value)

    def test_chat_invalid_message_dict(self, client):
        """Test chat with invalid message dict raises error."""
        with pytest.raises(ValueError) as exc_info:
            client.chat([{"role": "user"}])  # Missing content
        assert "must have 'role' and 'content' keys" in str(exc_info.value)

    def test_chat_request_payload(self, client, mock_success_response):
        """Test that correct payload is sent."""
        with patch.object(
            client._session, "post", return_value=mock_success_response
        ) as mock_post:
            messages = [ZaiMessage(role="user", content="Hello")]
            client.chat(messages, temperature=0.5, max_tokens=100, top_p=0.9)

            call_args = mock_post.call_args
            payload = call_args.kwargs["json"]

            assert payload["model"] == "glm-5"
            assert payload["messages"] == [{"role": "user", "content": "Hello"}]
            assert payload["temperature"] == 0.5
            assert payload["max_tokens"] == 100
            assert payload["top_p"] == 0.9

    def test_chat_headers(self, client, mock_success_response):
        """Test that correct headers are sent."""
        with patch.object(
            client._session, "post", return_value=mock_success_response
        ) as mock_post:
            client.chat([ZaiMessage(role="user", content="Hello")])

            call_args = mock_post.call_args
            headers = call_args.kwargs["headers"]

            assert headers["Authorization"] == "Bearer test-key"
            assert headers["Content-Type"] == "application/json"
            assert headers["Accept"] == "application/json"

    def test_chat_response_parsing(self, client, mock_success_response):
        """Test response parsing."""
        with patch.object(client._session, "post", return_value=mock_success_response):
            response = client.chat([ZaiMessage(role="user", content="Hello")])

            assert response.id == "chat-123"
            assert response.model == "glm-5"
            assert response.content == "Hello!"
            assert response.finish_reason == "stop"
            assert response.usage == {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            }
            assert response.raw_response is not None

    def test_chat_no_choices_raises(self, client):
        """Test response with no choices raises error."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "chat-123", "choices": []}

        with patch.object(client._session, "post", return_value=mock_response):
            with pytest.raises(ZaiError) as exc_info:
                client.chat([ZaiMessage(role="user", content="Hello")])
            assert "No choices in response" in str(exc_info.value)

    def test_stream_not_implemented(self, client):
        """Test that streaming raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            client.chat([ZaiMessage(role="user", content="Hello")], stream=True)


class TestZhipuClientErrors:
    """Tests for error handling."""

    @pytest.fixture
    def client(self):
        """Create a client fixture."""
        return ZhipuClient(api_key="test-key")

    def test_auth_error_401(self, client):
        """Test 401 raises ZaiAuthError."""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"error": {"message": "Invalid API key"}}
        mock_response.text = '{"error": {"message": "Invalid API key"}}'

        with patch.object(client._session, "post", return_value=mock_response):
            with pytest.raises(ZaiAuthError) as exc_info:
                client.chat([ZaiMessage(role="user", content="Hello")])
            assert "Authentication failed" in str(exc_info.value)

    def test_rate_limit_error_429(self, client):
        """Test 429 raises ZaiRateLimitError."""
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.json.return_value = {"error": {"message": "Rate limit exceeded"}}
        mock_response.text = '{"error": {"message": "Rate limit exceeded"}}'

        with patch.object(client._session, "post", return_value=mock_response):
            with pytest.raises(ZaiRateLimitError) as exc_info:
                client.chat([ZaiMessage(role="user", content="Hello")])
            assert "Rate limit exceeded" in str(exc_info.value)

    def test_server_error_500(self, client):
        """Test 500 raises ZaiServerError."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.json.return_value = {
            "error": {"message": "Internal server error"}
        }
        mock_response.text = '{"error": {"message": "Internal server error"}}'

        with patch.object(client._session, "post", return_value=mock_response):
            with pytest.raises(ZaiServerError) as exc_info:
                client.chat([ZaiMessage(role="user", content="Hello")])
            assert "Server error" in str(exc_info.value)

    def test_other_error_400(self, client):
        """Test 400 raises ZaiError."""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"error": {"message": "Bad request"}}
        mock_response.text = '{"error": {"message": "Bad request"}}'

        with patch.object(client._session, "post", return_value=mock_response):
            with pytest.raises(ZaiError) as exc_info:
                client.chat([ZaiMessage(role="user", content="Hello")])
            assert "API error" in str(exc_info.value)

    def test_error_non_json_response(self, client):
        """Test error with non-JSON response."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.json.side_effect = json.JSONDecodeError("test", "", 0)
        mock_response.text = "Internal Server Error"

        with patch.object(client._session, "post", return_value=mock_response):
            with pytest.raises(ZaiServerError) as exc_info:
                client.chat([ZaiMessage(role="user", content="Hello")])
            assert "Internal Server Error" in str(exc_info.value)


class TestZhipuClientSimpleChat:
    """Tests for simple_chat method."""

    @pytest.fixture
    def client(self):
        """Create a client fixture."""
        return ZhipuClient(api_key="test-key")

    def test_simple_chat_without_system(self, client):
        """Test simple chat without system prompt."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "chat-123",
            "model": "glm-5",
            "choices": [
                {
                    "message": {"role": "assistant", "content": "Response"},
                    "finish_reason": "stop",
                    "index": 0,
                }
            ],
            "usage": {},
        }

        with patch.object(
            client._session, "post", return_value=mock_response
        ) as mock_post:
            result = client.simple_chat("Hello")

            assert result == "Response"
            call_args = mock_post.call_args
            payload = call_args.kwargs["json"]
            assert len(payload["messages"]) == 1
            assert payload["messages"][0]["role"] == "user"
            assert payload["messages"][0]["content"] == "Hello"

    def test_simple_chat_with_system(self, client):
        """Test simple chat with system prompt."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "chat-123",
            "model": "glm-5",
            "choices": [
                {
                    "message": {"role": "assistant", "content": "Response"},
                    "finish_reason": "stop",
                    "index": 0,
                }
            ],
            "usage": {},
        }

        with patch.object(
            client._session, "post", return_value=mock_response
        ) as mock_post:
            result = client.simple_chat("Hello", system_prompt="You are helpful")

            assert result == "Response"
            call_args = mock_post.call_args
            payload = call_args.kwargs["json"]
            assert len(payload["messages"]) == 2
            assert payload["messages"][0]["role"] == "system"
            assert payload["messages"][0]["content"] == "You are helpful"
            assert payload["messages"][1]["role"] == "user"
            assert payload["messages"][1]["content"] == "Hello"


class TestZhipuClientHealthCheck:
    """Tests for health_check method."""

    @pytest.fixture
    def client(self):
        """Create a client fixture."""
        return ZhipuClient(api_key="test-key")

    def test_health_check_success(self, client):
        """Test health check returns True on success."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "chat-123",
            "model": "glm-5",
            "choices": [
                {
                    "message": {"role": "assistant", "content": "Hi"},
                    "finish_reason": "stop",
                    "index": 0,
                }
            ],
            "usage": {},
        }

        with patch.object(client._session, "post", return_value=mock_response):
            assert client.health_check() is True

    def test_health_check_failure(self, client):
        """Test health check returns False on failure."""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"error": {"message": "Invalid key"}}
        mock_response.text = '{"error": {"message": "Invalid key"}}'

        with patch.object(client._session, "post", return_value=mock_response):
            assert client.health_check() is False


class TestZhipuClientContextManager:
    """Tests for context manager usage."""

    def test_context_manager(self):
        """Test client works as context manager."""
        with ZhipuClient(api_key="test-key") as client:
            assert isinstance(client, ZhipuClient)
            assert client._session is not None

    def test_context_manager_closes_session(self):
        """Test session is closed on exit."""
        with ZhipuClient(api_key="test-key") as client:
            pass
        # Session should be closed after exit


class TestZhipuClientClose:
    """Tests for close method."""

    def test_close(self):
        """Test close method."""
        client = ZhipuClient(api_key="test-key")
        client.close()
        # Should not raise
