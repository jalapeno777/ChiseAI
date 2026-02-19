"""Z.ai (Zhipu AI) API client for LLM integration.

Provides async HTTP client for GLM-5 model API with
retry logic, error handling, and OpenAI-compatible request/response format.

For CH-LLM-ZAI-001: Z.ai GLM-5 Integration
For CH-LLM-FALLBACK-002: Error classification integration
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from typing import Any, cast

import aiohttp

from llm.errors import (
    AuthError,
    NetworkError,
    QuotaError,
    RateLimitError,
    ScopeError,
    ServerError,
    ValidationError,
    classify_error,
)

logger = logging.getLogger(__name__)


@dataclass
class ZaiConfig:
    """Configuration for Z.ai API client.

    Attributes:
        api_key: Z.ai API key (from Z_AI_API_KEY or ZHIPU_API_KEY env var)
        base_url: Z.ai API endpoint
        model: Model identifier (default: glm-5)
        timeout: Request timeout in seconds
        max_retries: Maximum number of retry attempts
        retry_delay: Initial retry delay in seconds (exponential backoff)
    """

    api_key: str | None = None
    base_url: str = "https://api.z.ai/api/paas/v4/chat/completions"
    model: str = "glm-5"
    timeout: float = 30.0
    max_retries: int = 3
    retry_delay: float = 1.0

    def __post_init__(self) -> None:
        """Load API key from environment if not provided."""
        if self.api_key is None:
            # Try Z_AI_API_KEY first, then fall back to ZHIPU_API_KEY
            self.api_key = os.getenv("Z_AI_API_KEY") or os.getenv("ZHIPU_API_KEY")


@dataclass
class ZaiMessage:
    """A message in the Z.ai chat format.

    Attributes:
        role: Message role (system, user, assistant)
        content: Message content
    """

    role: str
    content: str


@dataclass
class ZaiResponse:
    """Response from Z.ai API.

    Attributes:
        success: Whether the request was successful
        content: Generated text content (if successful)
        error: Error message (if failed)
        raw_response: Full JSON response from API
        usage: Token usage information
        finish_reason: Reason for completion
    """

    success: bool
    content: str | None = None
    error: str | None = None
    raw_response: dict[str, Any] | None = None
    usage: dict[str, int] | None = None
    finish_reason: str | None = None


class ZaiClient:
    """Async HTTP client for Z.ai API.

    Handles authentication, retry logic with exponential backoff,
    and error handling for GLM-5 model.

    Attributes:
        config: Z.ai configuration
        _session: aiohttp ClientSession (created on first use)
    """

    def __init__(self, config: ZaiConfig | None = None) -> None:
        """Initialize Z.ai client.

        Args:
            config: Z.ai configuration (uses defaults if None)
        """
        self.config = config or ZaiConfig()
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> "ZaiClient":
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.close()

    async def connect(self) -> None:
        """Initialize HTTP session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.config.api_key or ''}",
                },
                timeout=aiohttp.ClientTimeout(total=self.config.timeout),
            )

    async def close(self) -> None:
        """Close HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    def _build_request_payload(
        self,
        messages: list[ZaiMessage],
        temperature: float = 1.0,
        top_p: float = 0.95,
        max_tokens: int = 2048,
        stream: bool = False,
        thinking: bool = True,
    ) -> dict[str, Any]:
        """Build the request payload for Z.ai API.

        Args:
            messages: List of messages for the conversation
            temperature: Sampling temperature (0-2)
            top_p: Nucleus sampling parameter
            max_tokens: Maximum tokens to generate
            stream: Whether to stream the response
            thinking: Whether to enable thinking mode

        Returns:
            JSON payload dictionary
        """
        formatted_messages = []
        for msg in messages:
            msg_dict: dict[str, Any] = {
                "role": msg.role,
                "content": msg.content,
            }
            formatted_messages.append(msg_dict)

        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": formatted_messages,
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
            "stream": stream,
        }

        # Add thinking mode if enabled (GLM-5 feature)
        if thinking:
            payload["thinking"] = {"type": "enabled"}

        return payload

    async def _make_request_with_retry(
        self,
        payload: dict[str, Any],
    ) -> ZaiResponse:
        """Make request to Z.ai API with exponential backoff retry.

        Args:
            payload: Request payload

        Returns:
            ZaiResponse with result or error
        """
        if not self.config.api_key:
            return ZaiResponse(
                success=False,
                error="Z_AI_API_KEY or ZHIPU_API_KEY not configured",
            )

        if self._session is None:
            raise RuntimeError(
                "Client not connected. Use 'async with' or call connect()"
            )

        last_error: Exception | None = None
        delay = self.config.retry_delay

        for attempt in range(self.config.max_retries):
            try:
                async with self._session.post(
                    self.config.base_url,
                    json=payload,
                ) as response:
                    response_text = await response.text()

                    if response.status == 200:
                        data = json.loads(response_text)
                        return self._parse_response(data)

                    # Classify error for deterministic fallback behavior
                    error = classify_error(
                        Exception(f"HTTP {response.status}"),
                        provider="ZAI",
                        status_code=response.status,
                        response_body=response_text,
                    )

                    # Handle specific error codes with classified errors
                    if response.status == 401:
                        raise AuthError(
                            f"Authentication failed for ZAI", provider="ZAI"
                        )
                    elif response.status == 403:
                        # Check for quota vs scope error
                        if isinstance(error, QuotaError):
                            raise error
                        elif isinstance(error, ScopeError):
                            raise error
                        else:
                            raise ScopeError(
                                f"Permission denied for ZAI: {response_text[:200]}",
                                provider="ZAI",
                            )
                    elif response.status == 429:
                        # Rate limited - retry with longer delay
                        logger.warning(
                            f"Rate limited (attempt {attempt + 1}/{self.config.max_retries})"
                        )
                        if attempt < self.config.max_retries - 1:
                            await asyncio.sleep(
                                delay * 2
                            )  # Longer delay for rate limits
                            delay *= 2
                            continue
                        raise RateLimitError(
                            f"Rate limit exceeded for ZAI", provider="ZAI"
                        )
                    elif response.status >= 500:
                        # Server error - retry
                        logger.warning(
                            f"Server error {response.status} (attempt {attempt + 1}/{self.config.max_retries})"
                        )
                        if attempt < self.config.max_retries - 1:
                            await asyncio.sleep(delay)
                            delay *= 2
                            continue
                        raise ServerError(
                            f"Server error {response.status} from ZAI",
                            provider="ZAI",
                            status_code=response.status,
                        )
                    elif response.status in (400, 422):
                        # Validation error - don't retry
                        raise ValidationError(
                            f"Request validation failed for ZAI: {response_text[:200]}",
                            provider="ZAI",
                            status_code=response.status,
                        )
                    else:
                        # Unknown error
                        return ZaiResponse(
                            success=False,
                            error=f"HTTP {response.status}: {response_text[:500]}",
                            raw_response={
                                "status": response.status,
                                "body": response_text,
                            },
                        )

            except AuthError:
                raise  # Re-raise auth errors for immediate fallback
            except QuotaError:
                raise  # Re-raise quota errors for immediate fallback
            except ScopeError:
                raise  # Re-raise scope errors for immediate fallback
            except RateLimitError:
                raise  # Re-raise rate limit errors for handler decision
            except ValidationError:
                raise  # Re-raise validation errors (don't retry)
            except ServerError:
                raise  # Re-raise server errors for handler decision
            except aiohttp.ClientError as e:
                last_error = e
                logger.warning(
                    f"Request failed (attempt {attempt + 1}/{self.config.max_retries}): {e}"
                )
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(delay)
                    delay *= 2
                else:
                    raise NetworkError(f"Network error with ZAI: {e}", provider="ZAI")
            except asyncio.TimeoutError as e:
                last_error = e
                logger.warning(
                    f"Request timeout (attempt {attempt + 1}/{self.config.max_retries})"
                )
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(delay)
                    delay *= 2
                else:
                    raise NetworkError(f"Timeout error with ZAI: {e}", provider="ZAI")
            except Exception as e:
                last_error = e
                logger.error(f"Unexpected error: {e}")
                return ZaiResponse(
                    success=False,
                    error=f"Unexpected error: {e}",
                )

        # All retries exhausted
        return ZaiResponse(
            success=False,
            error=f"Max retries exceeded. Last error: {last_error}",
        )

    def _parse_response(self, data: dict[str, Any]) -> ZaiResponse:
        """Parse successful API response.

        Args:
            data: JSON response from API

        Returns:
            ZaiResponse with extracted content
        """
        try:
            # Extract usage info
            usage = data.get("usage", {})

            # Extract content from choices
            choices = data.get("choices", [])
            if not choices:
                return ZaiResponse(
                    success=False,
                    error="No choices in response",
                    raw_response=data,
                )

            choice = choices[0]
            message = choice.get("message", {})
            content = message.get("content", "")
            finish_reason = choice.get("finish_reason")

            return ZaiResponse(
                success=True,
                content=content,
                raw_response=data,
                usage=usage if usage else None,
                finish_reason=finish_reason,
            )
        except Exception as e:
            return ZaiResponse(
                success=False,
                error=f"Failed to parse response: {e}",
                raw_response=data,
            )

    async def chat(
        self,
        messages: list[ZaiMessage],
        temperature: float = 1.0,
        top_p: float = 0.95,
        max_tokens: int = 2048,
        thinking: bool = True,
    ) -> ZaiResponse:
        """Send a chat completion request to Z.ai API.

        Args:
            messages: List of messages for the conversation
            temperature: Sampling temperature (0-2)
            top_p: Nucleus sampling parameter
            max_tokens: Maximum tokens to generate
            thinking: Whether to enable thinking mode

        Returns:
            ZaiResponse with generated content or error
        """
        payload = self._build_request_payload(
            messages=messages,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            stream=False,
            thinking=thinking,
        )

        return await self._make_request_with_retry(payload)

    async def chat_simple(
        self,
        prompt: str,
        system_message: str | None = None,
        temperature: float = 1.0,
        max_tokens: int = 2048,
        thinking: bool = True,
    ) -> ZaiResponse:
        """Simple chat interface with single prompt.

        Args:
            prompt: User prompt
            system_message: Optional system message
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            thinking: Whether to enable thinking mode

        Returns:
            ZaiResponse with generated content or error
        """
        messages: list[ZaiMessage] = []

        if system_message:
            messages.append(
                ZaiMessage(
                    role="system",
                    content=system_message,
                )
            )

        messages.append(
            ZaiMessage(
                role="user",
                content=prompt,
            )
        )

        return await self.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            thinking=thinking,
        )

    async def health_check(self) -> dict[str, Any]:
        """Check Z.ai API health by making a minimal request.

        Returns:
            Dictionary with health status
        """
        if not self.config.api_key:
            return {
                "healthy": False,
                "connected": False,
                "error": "Z_AI_API_KEY or ZHIPU_API_KEY not configured",
            }

        try:
            # Make a minimal request to check connectivity
            response = await self.chat_simple(
                prompt="Hello",
                max_tokens=5,
            )

            if response.success:
                return {
                    "healthy": True,
                    "connected": True,
                    "model": self.config.model,
                    "error": None,
                }
            else:
                return {
                    "healthy": False,
                    "connected": True,
                    "model": self.config.model,
                    "error": response.error,
                }
        except Exception as e:
            return {
                "healthy": False,
                "connected": False,
                "error": str(e),
            }

    def is_configured(self) -> bool:
        """Check if client has valid configuration.

        Returns:
            True if API key is configured
        """
        return bool(self.config.api_key)
