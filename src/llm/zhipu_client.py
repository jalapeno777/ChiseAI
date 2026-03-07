"""
Z.ai (Zhipu AI) GLM-5 Integration Client

Provides OpenAI-compatible interface for Z.ai's GLM-5 model.
Uses coding endpoint: https://api.z.ai/api/coding/paas/v4/chat/completions

For CH-LLM-FALLBACK-002: Error classification integration
For LLM-PROVIDER-FIX-002: Updated endpoint to api.z.ai/api/coding/paas/v4
"""

import json
import os
import time
from dataclasses import dataclass
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from llm.errors import (
    NetworkError,
    QuotaError,
    ScopeError,
    classify_error,
)


class ZaiError(Exception):
    """Base exception for Z.ai client errors."""

    pass


class ZaiAuthError(ZaiError):
    """Authentication error (401)."""

    pass


class ZaiRateLimitError(ZaiError):
    """Rate limit exceeded (429)."""

    pass


class ZaiServerError(ZaiError):
    """Server error (5xx)."""

    pass


class ZaiTimeoutError(ZaiError):
    """Request timeout."""

    pass


@dataclass
class ZaiMessage:
    """Represents a message in the conversation."""

    role: str  # "system", "user", "assistant"
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass
class ZaiResponse:
    """Parsed response from Z.ai API."""

    id: str
    model: str
    content: str
    finish_reason: str
    usage: dict[str, int] | None = None
    raw_response: dict[str, Any] | None = None


class ZhipuClient:
    """
    Client for Z.ai GLM-5 API.

    Features:
    - OpenAI-compatible chat completions
    - Exponential backoff retry
    - Configurable timeout
    - Proper error handling
    """

    DEFAULT_ENDPOINT = "https://api.z.ai/api/coding/paas/v4/chat/completions"
    DEFAULT_MODEL = "glm-5"
    DEFAULT_TIMEOUT = 60
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_BACKOFF_FACTOR = 2.0

    def __init__(
        self,
        api_key: str | None = None,
        endpoint: str | None = None,
        model: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
    ):
        """
        Initialize Z.ai client.

        Args:
            api_key: Z.ai API key. Defaults to ZHIPU_API_KEY or ZAI_API_KEY env var.
            endpoint: API endpoint URL. Defaults to global endpoint.
            model: Model name. Defaults to "glm-5".
            timeout: Request timeout in seconds.
            max_retries: Maximum number of retries for failed requests.
            backoff_factor: Exponential backoff multiplier.
        """
        self.api_key = api_key or self._get_api_key_from_env()
        if not self.api_key:
            raise ZaiAuthError(
                "API key required. Set ZHIPU_API_KEY or ZAI_API_KEY "
                "environment variable."
            )

        self.endpoint = endpoint or self.DEFAULT_ENDPOINT
        self.model = model or self.DEFAULT_MODEL
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor

        self._session = self._create_session()

    def _get_api_key_from_env(self) -> str | None:
        """Get API key from environment variables.

        Checks in order: ZHIPU_API_KEY, Z_AI_API_KEY, ZAI_API_KEY
        """
        return (
            os.getenv("ZHIPU_API_KEY")
            or os.getenv("Z_AI_API_KEY")
            or os.getenv("ZAI_API_KEY")
        )

    def _create_session(self) -> requests.Session:
        """Create requests session with retry strategy."""
        session = requests.Session()

        # Configure retry strategy
        retry_strategy = Retry(
            total=self.max_retries,
            backoff_factor=self.backoff_factor,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["POST", "GET"],
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        return session

    def _get_headers(self) -> dict[str, str]:
        """Get request headers with authorization."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _handle_error(self, response: requests.Response) -> None:
        """Handle HTTP error responses using classified errors."""
        status_code = response.status_code

        try:
            error_data = response.json()
            error_msg = error_data.get("error", {}).get("message", str(error_data))
        except (json.JSONDecodeError, ValueError):
            error_msg = response.text or f"HTTP {status_code}"

        # Classify error for deterministic fallback behavior
        error = classify_error(
            Exception(f"HTTP {status_code}"),
            provider="ZHIPU",
            status_code=status_code,
            response_body=response.text,
        )

        if status_code == 401:
            raise ZaiAuthError(f"Authentication failed for ZHIPU: {error_msg}")
        elif status_code == 429:
            raise ZaiRateLimitError(f"Rate limit exceeded for ZHIPU: {error_msg}")
        elif status_code == 403:
            # Check for quota vs scope error
            if isinstance(error, (QuotaError, ScopeError)):
                raise error
            else:
                raise ScopeError(
                    f"Permission denied for ZHIPU: {error_msg}", provider="ZHIPU"
                )
        elif status_code in (400, 422):
            raise ZaiError(f"API error {status_code}: {error_msg}")
        elif status_code >= 500:
            raise ZaiServerError(f"Server error {status_code} from ZHIPU: {error_msg}")

    def _parse_response(self, data: dict[str, Any]) -> ZaiResponse:
        """Parse API response into ZaiResponse object.

        Args:
            data: JSON response data from API.

        Returns:
            Parsed ZaiResponse object.

        Raises:
            ZaiError: If response format is invalid.
        """
        choices = data.get("choices", [])
        if not choices:
            raise ZaiError("No choices in response")

        choice = choices[0]
        message = choice.get("message", {})

        return ZaiResponse(
            id=data.get("id", ""),
            model=data.get("model", self.model),
            content=message.get("content", ""),
            finish_reason=choice.get("finish_reason", ""),
            usage=data.get("usage"),
            raw_response=data,
        )

    def chat(
        self,
        messages: list[ZaiMessage | dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        top_p: float | None = None,
        stream: bool = False,
    ) -> ZaiResponse:
        """
        Send chat completion request to Z.ai API.

        Args:
            messages: List of messages (ZaiMessage or dict with role/content).
            temperature: Sampling temperature (0-2).
            max_tokens: Maximum tokens to generate.
            top_p: Nucleus sampling parameter.
            stream: Whether to stream response (not implemented).

        Returns:
            ZaiResponse with generated content.

        Raises:
            ZaiAuthError: If authentication fails.
            ZaiRateLimitError: If rate limit is exceeded.
            ZaiServerError: If server error occurs.
            ZaiTimeoutError: If request times out.
            ZaiError: For other API errors.
        """
        if stream:
            raise NotImplementedError("Streaming not yet implemented")

        # Convert messages to dict format
        formatted_messages = []
        for msg in messages:
            if isinstance(msg, ZaiMessage):
                formatted_messages.append(msg.to_dict())
            elif isinstance(msg, dict):
                if "role" not in msg or "content" not in msg:
                    raise ValueError("Message dict must have 'role' and 'content' keys")
                formatted_messages.append(msg)
            else:
                raise ValueError(f"Invalid message type: {type(msg)}")

        payload = {
            "model": self.model,
            "messages": formatted_messages,
            "temperature": temperature,
        }

        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if top_p is not None:
            payload["top_p"] = top_p

        last_exception: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                response = self._session.post(
                    self.endpoint,
                    headers=self._get_headers(),
                    json=payload,
                    timeout=self.timeout,
                )

                if response.status_code == 200:
                    return self._parse_response(response.json())
                else:
                    self._handle_error(response)

            except requests.exceptions.Timeout:
                last_exception = NetworkError(
                    f"Request timed out after {self.timeout}s", provider="ZHIPU"
                )
            except (ZaiRateLimitError, ZaiServerError) as e:
                # These are retryable, continue to next attempt
                if attempt < self.max_retries:
                    wait_time = self.backoff_factor * (2**attempt)
                    time.sleep(wait_time)
                else:
                    raise e  # Re-raise after exhausting retries
            except (ZaiAuthError, QuotaError, ScopeError):
                raise  # Non-retryable errors - re-raise for immediate fallback
            except ZaiError:
                raise  # Other ZaiError types - re-raise immediately
            except requests.exceptions.RequestException as e:
                last_exception = NetworkError(f"Request failed: {e}", provider="ZHIPU")
                if attempt < self.max_retries:
                    wait_time = self.backoff_factor * (2**attempt)
                    time.sleep(wait_time)

        # All retries exhausted
        if last_exception:
            raise last_exception
        raise ZaiError("All retry attempts failed")

    def simple_chat(self, prompt: str, system_prompt: str | None = None) -> str:
        """
        Simple one-turn chat interface.

        Args:
            prompt: User prompt.
            system_prompt: Optional system prompt.

        Returns:
            Generated response content.
        """
        messages = []
        if system_prompt:
            messages.append(ZaiMessage(role="system", content=system_prompt))
        messages.append(ZaiMessage(role="user", content=prompt))

        response = self.chat(messages)
        return response.content

    def health_check(self) -> bool:
        """
        Check if API is accessible with current credentials.

        Returns:
            True if healthy, False otherwise.
        """
        try:
            # Simple test request with minimal tokens
            self.chat(
                messages=[ZaiMessage(role="user", content="Hi")],
                max_tokens=5,
            )
            return True
        except ZaiError:
            return False

    def close(self) -> None:
        """Close the session and release resources."""
        if self._session:
            self._session.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False
