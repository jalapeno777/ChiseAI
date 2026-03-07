"""KIMI API client for LLM integration.

Provides async HTTP client for KIMI K2.5 model API with
retry logic, error handling, and OpenAI-compatible request/response format.

For CH-LLM-KIMI-001: KIMI K2.5 Integration
For CH-KIMI-FIX-001: Model discovery and 403 handling
For CH-LLM-FALLBACK-002: Error classification integration
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any

import aiohttp

from llm.errors import classify_error

logger = logging.getLogger(__name__)


@dataclass
class KimiConfig:
    """Configuration for KIMI API client.

    Attributes:
        api_key: KIMI API key (from KIMI_API_KEY env var)
        base_url: KIMI API endpoint
        model: Model identifier (default: k2p5)
        timeout: Request timeout in seconds
        max_retries: Maximum number of retry attempts
        retry_delay: Initial retry delay in seconds (exponential backoff)
        accessible_models: List of models discovered from /models endpoint
        model_discovery_enabled: Whether to query /models for available models
    """

    api_key: str | None = None
    base_url: str = "https://api.moonshot.cn/v1"
    model: str = "kimi-k2.5"
    timeout: float = 30.0
    max_retries: int = 3
    retry_delay: float = 1.0
    accessible_models: list[str] = field(default_factory=list)
    model_discovery_enabled: bool = True

    def __post_init__(self) -> None:
        """Load API key from environment if not provided."""
        if self.api_key is None:
            self.api_key = os.getenv("KIMI_API_KEY")


@dataclass
class KimiMessage:
    """A message in the KIMI chat format.

    Attributes:
        role: Message role (system, user, assistant)
        content: Message content
    """

    role: str
    content: str


@dataclass
class KimiResponse:
    """Response from KIMI API.

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


class KimiClient:
    """Async HTTP client for KIMI API.

    Handles authentication, retry logic with exponential backoff,
    and error handling for KIMI K2.5 model.

    Attributes:
        config: KIMI configuration
        _session: aiohttp ClientSession (created on first use)
    """

    def __init__(self, config: KimiConfig | None = None) -> None:
        """Initialize KIMI client.

        Args:
            config: KIMI configuration (uses defaults if None)
        """
        self.config = config or KimiConfig()
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> KimiClient:
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
                    "User-Agent": "claude-code/0.1.0",
                },
                timeout=aiohttp.ClientTimeout(total=self.config.timeout),
            )

    async def close(self) -> None:
        """Close HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def discover_models(self) -> list[str]:
        """Query the /models endpoint to discover accessible models.

        Returns:
            List of model IDs that are accessible with the current API key.
            Empty list if discovery fails or is disabled.
        """
        if not self.config.api_key:
            logger.warning("Cannot discover models: API key not configured")
            return []

        if not self.config.model_discovery_enabled:
            logger.debug("Model discovery disabled")
            return self.config.accessible_models

        if self._session is None:
            raise RuntimeError(
                "Client not connected. Use 'async with' or call connect()"
            )

        try:
            logger.info("Discovering accessible KIMI models from /models endpoint")
            async with self._session.get(
                f"{self.config.base_url}/models",
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                response_text = await response.text()

                if response.status == 200:
                    try:
                        data = json.loads(response_text)
                        models = data.get("data", [])
                        model_ids = [m.get("id", "unknown") for m in models]
                        self.config.accessible_models = model_ids
                        logger.info(
                            f"Discovered {len(model_ids)} accessible model(s): "
                            f"{model_ids}"
                        )
                        return model_ids
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse /models response: {e}")
                        return []
                else:
                    logger.warning(f"Failed to discover models: HTTP {response.status}")
                    return []

        except Exception as e:
            logger.warning(f"Model discovery failed: {e}")
            return []

    def _select_model(self, requested_model: str | None = None) -> str:
        """Select the model to use for requests.

        Uses the requested model if available, otherwise falls back to
        the first accessible model discovered from /models endpoint.

        Args:
            requested_model: Specific model to use, or None to use config default

        Returns:
            Model ID to use for the request
        """
        target = requested_model or self.config.model

        # If we have accessible models and the target is not in the list,
        # fall back to the first accessible model
        if (
            self.config.accessible_models
            and target not in self.config.accessible_models
        ):
            fallback = self.config.accessible_models[0]
            logger.warning(
                f"Model '{target}' not in accessible models list. "
                f"Falling back to '{fallback}'. "
                f"Available: {self.config.accessible_models}"
            )
            return fallback

        return target

    def _build_request_payload(
        self,
        messages: list[KimiMessage],
        temperature: float = 1.0,
        top_p: float = 0.95,
        max_tokens: int = 2048,
        stream: bool = False,
    ) -> dict[str, Any]:
        """Build the request payload for KIMI API.

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
            formatted_messages.append(msg_dict)

        # Select model (with fallback to accessible models if needed)
        selected_model = self._select_model()
        logger.debug(f"Using model: {selected_model}")

        return {
            "model": selected_model,
            "messages": formatted_messages,
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
            "stream": stream,
        }

    async def _make_request_with_retry(
        self,
        payload: dict[str, Any],
    ) -> KimiResponse:
        """Make request to KIMI API with exponential backoff retry.

        Args:
            payload: Request payload

        Returns:
            KimiResponse with result or error
        """
        if not self.config.api_key:
            return KimiResponse(
                success=False,
                error="KIMI_API_KEY not configured",
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
                    f"{self.config.base_url}/chat/completions",
                    json=payload,
                ) as response:
                    response_text = await response.text()

                    if response.status == 200:
                        data = json.loads(response_text)
                        return self._parse_response(data)

                    # Classify error for deterministic fallback behavior
                    classified_error = classify_error(
                        Exception(f"HTTP {response.status}"),
                        provider="KIMI",
                        status_code=response.status,
                        response_body=response_text,
                    )

                    # Handle specific error codes with classified errors
                    if response.status == 401:
                        return KimiResponse(
                            success=False,
                            error="Authentication failed for KIMI",
                            raw_response={
                                "status": response.status,
                                "body": response_text,
                                "error_type": "AuthError",
                            },
                        )
                    elif response.status == 403:
                        error_message = self._extract_403_error_message(response_text)
                        return KimiResponse(
                            success=False,
                            error=f"Permission denied for KIMI: {error_message}",
                            raw_response={
                                "status": response.status,
                                "body": response_text,
                                "error_type": type(classified_error).__name__,
                            },
                        )
                    elif response.status == 429:
                        # Rate limited - retry with longer delay
                        logger.warning(
                            f"Rate limited (attempt {attempt + 1}/"
                            f"{self.config.max_retries})"
                        )
                        if attempt < self.config.max_retries - 1:
                            await asyncio.sleep(
                                delay * 2
                            )  # Longer delay for rate limits
                            delay *= 2
                            continue
                        return KimiResponse(
                            success=False,
                            error="Rate limit exceeded for KIMI",
                            raw_response={
                                "status": response.status,
                                "body": response_text,
                                "error_type": "RateLimitError",
                            },
                        )
                    elif response.status >= 500:
                        # Server error - retry
                        logger.warning(
                            f"Server error {response.status} (attempt {attempt + 1}/"
                            f"{self.config.max_retries})"
                        )
                        if attempt < self.config.max_retries - 1:
                            await asyncio.sleep(delay)
                            delay *= 2
                            continue
                        return KimiResponse(
                            success=False,
                            error=f"Server error {response.status} from KIMI",
                            raw_response={
                                "status": response.status,
                                "body": response_text,
                                "error_type": "ServerError",
                            },
                        )
                    elif response.status in (400, 422):
                        # Validation error - don't retry
                        return KimiResponse(
                            success=False,
                            error=f"HTTP {response.status}: {response_text[:500]}",
                            raw_response={
                                "status": response.status,
                                "body": response_text,
                                "error_type": "ValidationError",
                            },
                        )
                    else:
                        # Unknown error
                        return KimiResponse(
                            success=False,
                            error=f"HTTP {response.status}: {response_text[:500]}",
                            raw_response={
                                "status": response.status,
                                "body": response_text,
                            },
                        )

            except aiohttp.ClientError as e:
                last_error = e
                logger.warning(
                    f"Request failed (attempt {attempt + 1}/"
                    f"{self.config.max_retries}): {e}"
                )
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(delay)
                    delay *= 2
                else:
                    return KimiResponse(
                        success=False,
                        error=f"Max retries exceeded. Last error: {e}",
                        raw_response={
                            "error_type": "NetworkError",
                        },
                    )
            except TimeoutError as e:
                last_error = e
                logger.warning(
                    f"Request timeout (attempt {attempt + 1}/{self.config.max_retries})"
                )
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(delay)
                    delay *= 2
                else:
                    return KimiResponse(
                        success=False,
                        error=f"Max retries exceeded. Last error: {e}",
                        raw_response={
                            "error_type": "NetworkError",
                        },
                    )
            except Exception as e:
                last_error = e
                logger.error(f"Unexpected error: {e}")
                return KimiResponse(
                    success=False,
                    error=f"Unexpected error: {e}",
                )

        # All retries exhausted
        return KimiResponse(
            success=False,
            error=f"Max retries exceeded. Last error: {last_error}",
        )

    def _extract_403_error_message(self, response_text: str) -> str:
        """Extract a user-friendly error message from 403 response.

        Args:
            response_text: Raw response text from API

        Returns:
            Sanitized error message without sensitive details
        """
        try:
            data = json.loads(response_text)
            error = data.get("error", {})
            message = error.get("message", "")
            error_type = error.get("type", "")

            # Return the API message if available (it's already sanitized)
            if message:
                return f"{message} (type: {error_type})"
        except (json.JSONDecodeError, AttributeError):
            pass

        return "Model not accessible or insufficient API scope"

    def _parse_response(self, data: dict[str, Any]) -> KimiResponse:
        """Parse successful API response.

        Args:
            data: JSON response from API

        Returns:
            KimiResponse with extracted content
        """
        try:
            # Extract usage info
            usage = data.get("usage", {})

            # Extract content from choices
            choices = data.get("choices", [])
            if not choices:
                return KimiResponse(
                    success=False,
                    error="No choices in response",
                    raw_response=data,
                )

            choice = choices[0]
            message = choice.get("message", {})
            content = message.get("content", "")
            finish_reason = choice.get("finish_reason")

            return KimiResponse(
                success=True,
                content=content,
                raw_response=data,
                usage=usage if usage else None,
                finish_reason=finish_reason,
            )
        except Exception as e:
            return KimiResponse(
                success=False,
                error=f"Failed to parse response: {e}",
                raw_response=data,
            )

    async def chat(
        self,
        messages: list[KimiMessage],
        temperature: float = 1.0,
        top_p: float = 0.95,
        max_tokens: int = 2048,
    ) -> KimiResponse:
        """Send a chat completion request to KIMI API.

        Args:
            messages: List of messages for the conversation
            temperature: Sampling temperature (0-2)
            top_p: Nucleus sampling parameter
            max_tokens: Maximum tokens to generate

        Returns:
            KimiResponse with generated content or error
        """
        # Discover accessible models if not already done
        if self.config.model_discovery_enabled and not self.config.accessible_models:
            await self.discover_models()

        payload = self._build_request_payload(
            messages=messages,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            stream=False,
        )

        # Log the model being used
        logger.info(f"KIMI request with model: {payload.get('model', 'unknown')}")

        return await self._make_request_with_retry(payload)

    async def chat_simple(
        self,
        prompt: str,
        system_message: str | None = None,
        temperature: float = 1.0,
        max_tokens: int = 2048,
    ) -> KimiResponse:
        """Simple chat interface with single prompt.

        Args:
            prompt: User prompt
            system_message: Optional system message
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Returns:
            KimiResponse with generated content or error
        """
        messages: list[KimiMessage] = []

        if system_message:
            messages.append(
                KimiMessage(
                    role="system",
                    content=system_message,
                )
            )

        messages.append(
            KimiMessage(
                role="user",
                content=prompt,
            )
        )

        return await self.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def health_check(self) -> dict[str, Any]:
        """Check KIMI API health by making a minimal request.

        Returns:
            Dictionary with health status
        """
        if not self.config.api_key:
            return {
                "healthy": False,
                "connected": False,
                "error": "KIMI_API_KEY not configured",
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
