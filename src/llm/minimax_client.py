"""MiniMax API client for LLM integration.

Provides async HTTP client for MiniMax 2.5 (M2-her) model API with
retry logic, error handling, and OpenAI-compatible request/response format.

For CH-LLM-MINIMAX-001: MiniMax 2.5 Integration
For CH-LLM-FALLBACK-002: Error classification integration
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from typing import Any, AsyncIterator, cast

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
class MiniMaxConfig:
    """Configuration for MiniMax API client.

    Attributes:
        api_key: MiniMax API key (from MINIMAX_API_KEY env var)
        base_url: MiniMax API endpoint
        model: Model identifier (default: M2-her)
        timeout: Request timeout in seconds
        max_retries: Maximum number of retry attempts
        retry_delay: Initial retry delay in seconds (exponential backoff)
    """

    api_key: str | None = None
    base_url: str = "https://api.minimax.io/v1/text/chatcompletion_v2"
    model: str = "MiniMax-M2.5"
    timeout: float = 30.0
    max_retries: int = 3
    retry_delay: float = 1.0

    def __post_init__(self) -> None:
        """Load API key from environment if not provided."""
        if self.api_key is None:
            self.api_key = os.getenv("MINIMAX_API_KEY")


@dataclass
class MiniMaxMessage:
    """A message in the MiniMax chat format.

    Attributes:
        role: Message role (system, user, assistant)
        content: Message content
        name: Optional name for the message sender
    """

    role: str
    content: str
    name: str | None = None


@dataclass
class MiniMaxResponse:
    """Response from MiniMax API.

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


class MiniMaxClient:
    """Async HTTP client for MiniMax API.

    Handles authentication, retry logic with exponential backoff,
    and error handling for MiniMax 2.5 (M2-her) model.

    Attributes:
        config: MiniMax configuration
        _session: aiohttp ClientSession (created on first use)
    """

    def __init__(self, config: MiniMaxConfig | None = None) -> None:
        """Initialize MiniMax client.

        Args:
            config: MiniMax configuration (uses defaults if None)
        """
        self.config = config or MiniMaxConfig()
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> "MiniMaxClient":
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
        messages: list[MiniMaxMessage],
        temperature: float = 1.0,
        top_p: float = 0.95,
        max_tokens: int = 2048,
        stream: bool = False,
    ) -> dict[str, Any]:
        """Build the request payload for MiniMax API.

        Args:
            messages: List of messages for the conversation
            temperature: Sampling temperature (0-2)
            top_p: Nucleus sampling parameter
            max_tokens: Maximum tokens to generate
            stream: Whether to stream the response

        Returns:
            JSON payload dictionary
        """
        formatted_messages = []
        for msg in messages:
            msg_dict: dict[str, Any] = {
                "role": msg.role,
                "content": msg.content,
            }
            if msg.name:
                msg_dict["name"] = msg.name
            formatted_messages.append(msg_dict)

        return {
            "model": self.config.model,
            "messages": formatted_messages,
            "temperature": temperature,
            "top_p": top_p,
            "max_completion_tokens": max_tokens,
            "stream": stream,
        }

    async def _make_request_with_retry(
        self,
        payload: dict[str, Any],
    ) -> MiniMaxResponse:
        """Make request to MiniMax API with exponential backoff retry.

        Args:
            payload: Request payload

        Returns:
            MiniMaxResponse with result or error
        """
        if not self.config.api_key:
            return MiniMaxResponse(
                success=False,
                error="MINIMAX_API_KEY not configured",
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
                        provider="MINIMAX",
                        status_code=response.status,
                        response_body=response_text,
                    )

                    # Handle specific error codes with classified errors
                    if response.status == 401:
                        raise AuthError(
                            f"Authentication failed for MINIMAX", provider="MINIMAX"
                        )
                    elif response.status == 403:
                        # Check for quota vs scope error
                        if isinstance(error, QuotaError):
                            raise error
                        elif isinstance(error, ScopeError):
                            raise error
                        else:
                            raise ScopeError(
                                f"Permission denied for MINIMAX: {response_text[:200]}",
                                provider="MINIMAX",
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
                            f"Rate limit exceeded for MINIMAX", provider="MINIMAX"
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
                            f"Server error {response.status} from MINIMAX",
                            provider="MINIMAX",
                            status_code=response.status,
                        )
                    elif response.status in (400, 422):
                        # Validation error - don't retry
                        raise ValidationError(
                            f"Request validation failed for MINIMAX: {response_text[:200]}",
                            provider="MINIMAX",
                            status_code=response.status,
                        )
                    else:
                        # Unknown error
                        return MiniMaxResponse(
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
                    raise NetworkError(
                        f"Network error with MINIMAX: {e}", provider="MINIMAX"
                    )
            except asyncio.TimeoutError as e:
                last_error = e
                logger.warning(
                    f"Request timeout (attempt {attempt + 1}/{self.config.max_retries})"
                )
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(delay)
                    delay *= 2
                else:
                    raise NetworkError(
                        f"Timeout error with MINIMAX: {e}", provider="MINIMAX"
                    )
            except Exception as e:
                last_error = e
                logger.error(f"Unexpected error: {e}")
                return MiniMaxResponse(
                    success=False,
                    error=f"Unexpected error: {e}",
                )

        # All retries exhausted
        return MiniMaxResponse(
            success=False,
            error=f"Max retries exceeded. Last error: {last_error}",
        )

    def _parse_response(self, data: dict[str, Any]) -> MiniMaxResponse:
        """Parse successful API response.

        Args:
            data: JSON response from API

        Returns:
            MiniMaxResponse with extracted content
        """
        try:
            # Extract usage info
            usage = data.get("usage", {})

            # Extract content from choices
            choices = data.get("choices", [])
            if not choices:
                return MiniMaxResponse(
                    success=False,
                    error="No choices in response",
                    raw_response=data,
                )

            choice = choices[0]
            message = choice.get("message", {})
            content = message.get("content", "")
            finish_reason = choice.get("finish_reason")

            return MiniMaxResponse(
                success=True,
                content=content,
                raw_response=data,
                usage=usage if usage else None,
                finish_reason=finish_reason,
            )
        except Exception as e:
            return MiniMaxResponse(
                success=False,
                error=f"Failed to parse response: {e}",
                raw_response=data,
            )

    async def chat(
        self,
        messages: list[MiniMaxMessage],
        temperature: float = 1.0,
        top_p: float = 0.95,
        max_tokens: int = 2048,
    ) -> MiniMaxResponse:
        """Send a chat completion request to MiniMax API.

        Args:
            messages: List of messages for the conversation
            temperature: Sampling temperature (0-2)
            top_p: Nucleus sampling parameter
            max_tokens: Maximum tokens to generate

        Returns:
            MiniMaxResponse with generated content or error
        """
        payload = self._build_request_payload(
            messages=messages,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            stream=False,
        )

        return await self._make_request_with_retry(payload)

    async def chat_simple(
        self,
        prompt: str,
        system_message: str | None = None,
        temperature: float = 1.0,
        max_tokens: int = 2048,
    ) -> MiniMaxResponse:
        """Simple chat interface with single prompt.

        Args:
            prompt: User prompt
            system_message: Optional system message
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Returns:
            MiniMaxResponse with generated content or error
        """
        messages: list[MiniMaxMessage] = []

        if system_message:
            messages.append(
                MiniMaxMessage(
                    role="system",
                    content=system_message,
                    name="MiniMax AI",
                )
            )

        messages.append(
            MiniMaxMessage(
                role="user",
                content=prompt,
                name="User",
            )
        )

        return await self.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def health_check(self) -> dict[str, Any]:
        """Check MiniMax API health by making a minimal request.

        Returns:
            Dictionary with health status
        """
        if not self.config.api_key:
            return {
                "healthy": False,
                "connected": False,
                "error": "MINIMAX_API_KEY not configured",
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
