"""LLM Provider Chain with robust fallback handling.

Provides a unified interface for multiple LLM providers with:
- Error classification (auth, scope, quota, rate, network)
- Automatic fallback between providers
- Configurable provider priority
- Proper async/sync handling

Provider Priority (default):
1. KIMI (K2.5) - Primary
2. Z.ai (GLM-5) - Secondary
3. Zhipu (GLM-4.7) - Tertiary
4. MiniMax - Quaternary (disabled by default)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, Callable, Coroutine

if TYPE_CHECKING:
    from signal_generation.models import Signal

logger = logging.getLogger(__name__)


class ErrorCategory(Enum):
    """Categories of LLM provider errors for fallback decisions."""

    AUTH = auto()  # 401 - Authentication failed
    SCOPE = auto()  # 403 - Permission/scope denied
    QUOTA = auto()  # 429 with quota message or 403 quota exceeded
    RATE_LIMIT = auto()  # 429 - Rate limit (retryable with backoff)
    NETWORK = auto()  # Connection errors, timeouts, DNS failures
    SERVER = auto()  # 5xx errors (retryable)
    CLIENT = auto()  # 4xx errors (non-retryable)
    UNKNOWN = auto()  # Unclassified errors
    NOT_CONFIGURED = auto()  # API key missing or disabled


@dataclass
class ProviderError:
    """Structured error information from a provider call."""

    category: ErrorCategory
    message: str
    original_error: Exception | None = None
    status_code: int | None = None
    retryable: bool = False
    should_fallback: bool = True


@dataclass
class LLMResponse:
    """Unified response from any LLM provider."""

    success: bool
    content: str = ""
    confidence_score: float = 50.0
    rationale: str = ""
    provider: str = "unknown"
    latency_ms: float = 0.0
    error: ProviderError | None = None
    raw_response: dict[str, Any] | None = None


@dataclass
class ProviderConfig:
    """Configuration for an LLM provider."""

    name: str
    api_key_env: str
    enabled_env: str | None = None
    enabled_default: bool = True
    priority: int = 0


# Provider configurations
PROVIDER_CONFIGS = {
    "kimi": ProviderConfig(
        name="KIMI K2.5",
        api_key_env="KIMI_API_KEY",
        enabled_env="KIMI_ENABLED",
        enabled_default=True,
        priority=1,
    ),
    "zai": ProviderConfig(
        name="GLM-5 (Z.ai)",
        api_key_env="ZAI_API_KEY",
        enabled_env=None,  # Always enabled if key present
        enabled_default=True,
        priority=2,
    ),
    "zhipu": ProviderConfig(
        name="GLM-4.7 (Zhipu)",
        api_key_env="ZHIPU_API_KEY",
        enabled_env=None,
        enabled_default=True,
        priority=3,
    ),
    "minimax": ProviderConfig(
        name="MiniMax",
        api_key_env="MINIMAX_API_KEY",
        enabled_env="MINIMAX_ENABLED",
        enabled_default=False,  # Disabled by default
        priority=4,
    ),
}


def classify_error(error: Exception, status_code: int | None = None) -> ProviderError:
    """Classify an error into a category for fallback decisions.

    Args:
        error: The exception that occurred
        status_code: HTTP status code if available

    Returns:
        ProviderError with classification and fallback decision
    """
    error_str = str(error).lower()
    error_type = type(error).__name__.lower()

    # Check for authentication errors
    if status_code == 401 or any(
        kw in error_str for kw in ["auth", "unauthorized", "invalid key", "api key"]
    ):
        return ProviderError(
            category=ErrorCategory.AUTH,
            message="Authentication failed - check API key",
            original_error=error,
            status_code=status_code,
            retryable=False,
            should_fallback=True,
        )

    # Check for permission/scope errors
    if status_code == 403 or any(
        kw in error_str for kw in ["forbidden", "permission", "scope"]
    ):
        # Check if it's a quota error disguised as 403
        if any(
            kw in error_str for kw in ["quota", "limit exceeded", "insufficient quota"]
        ):
            return ProviderError(
                category=ErrorCategory.QUOTA,
                message="API quota exceeded",
                original_error=error,
                status_code=status_code,
                retryable=False,
                should_fallback=True,
            )
        return ProviderError(
            category=ErrorCategory.SCOPE,
            message="Permission denied - check API scope",
            original_error=error,
            status_code=status_code,
            retryable=False,
            should_fallback=True,
        )

    # Check for rate limiting
    if status_code == 429 or any(
        kw in error_str for kw in ["rate limit", "too many requests"]
    ):
        return ProviderError(
            category=ErrorCategory.RATE_LIMIT,
            message="Rate limit exceeded - retry with backoff",
            original_error=error,
            status_code=status_code,
            retryable=True,
            should_fallback=True,  # Still fallback if retries exhausted
        )

    # Check for server errors (5xx)
    if status_code and status_code >= 500:
        return ProviderError(
            category=ErrorCategory.SERVER,
            message=f"Server error {status_code}",
            original_error=error,
            status_code=status_code,
            retryable=True,
            should_fallback=True,
        )

    # Check for network errors
    if any(
        kw in error_str
        for kw in ["connection", "timeout", "dns", "network", "unreachable", "refused"]
    ) or any(kw in error_type for kw in ["timeout", "connection", "network"]):
        return ProviderError(
            category=ErrorCategory.NETWORK,
            message="Network error - check connectivity",
            original_error=error,
            status_code=status_code,
            retryable=True,
            should_fallback=True,
        )

    # Check for client errors (4xx)
    if status_code and status_code >= 400:
        return ProviderError(
            category=ErrorCategory.CLIENT,
            message=f"Client error {status_code}: {error}",
            original_error=error,
            status_code=status_code,
            retryable=False,
            should_fallback=True,
        )

    # Unknown errors - assume non-retryable but fallback
    return ProviderError(
        category=ErrorCategory.UNKNOWN,
        message=f"Unknown error: {error}",
        original_error=error,
        status_code=status_code,
        retryable=False,
        should_fallback=True,
    )


class LLMProviderChain:
    """Manages LLM provider fallback chain with error classification.

    Provider order: KIMI → GLM-5 → GLM-4.7 → MiniMax (disabled by default)

    Usage:
        chain = LLMProviderChain()
        response = await chain.query("Your prompt here")
        if response.success:
            print(response.content)
        else:
            print(f"All providers failed: {response.error}")
    """

    def __init__(
        self,
        provider_order: list[str] | None = None,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ):
        """Initialize the provider chain.

        Args:
            provider_order: Ordered list of provider names to try
            max_retries: Maximum retries per provider for retryable errors
            retry_delay: Initial retry delay (exponential backoff)
        """
        self.provider_order = provider_order or ["kimi", "zai", "zhipu", "minimax"]
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._provider_stats: dict[str, dict[str, Any]] = {}

    def _is_provider_available(self, provider_name: str) -> tuple[bool, str | None]:
        """Check if a provider is available based on environment.

        Args:
            provider_name: Name of the provider

        Returns:
            Tuple of (available, reason_if_not)
        """
        config = PROVIDER_CONFIGS.get(provider_name)
        if not config:
            return False, f"Unknown provider: {provider_name}"

        # Check if explicitly disabled
        if config.enabled_env:
            enabled = os.getenv(config.enabled_env, str(config.enabled_default)).lower()
            if enabled in ("false", "0", "no", "off"):
                return False, f"{config.enabled_env}=false"

        # Check for API key
        api_key = os.getenv(config.api_key_env)
        if not api_key:
            # Special case: Zhipu can use ZAI_API_KEY as fallback
            if provider_name == "zhipu":
                zai_key = os.getenv("ZAI_API_KEY")
                if zai_key:
                    return True, None
            return False, f"{config.api_key_env} not set"

        return True, None

    async def _query_with_retry(
        self,
        provider_name: str,
        query_fn: Callable[..., Coroutine[Any, Any, LLMResponse]],
        *args: Any,
        **kwargs: Any,
    ) -> LLMResponse:
        """Query a provider with retry logic for retryable errors.

        Args:
            provider_name: Name of the provider
            query_fn: Async function to call
            *args: Positional arguments for query_fn
            **kwargs: Keyword arguments for query_fn

        Returns:
            LLMResponse from the provider
        """
        config = PROVIDER_CONFIGS.get(provider_name)
        provider_label = config.name if config else provider_name

        last_error: Exception | None = None
        delay = self.retry_delay

        for attempt in range(self.max_retries):
            try:
                response = await query_fn(*args, **kwargs)
                if response.success:
                    return response
                # If response has error but succeeded flag is False, check if retryable
                if response.error and not response.error.retryable:
                    return response
                last_error = Exception(
                    response.error.message if response.error else "Unknown error"
                )
            except Exception as e:
                last_error = e
                error = classify_error(e)

                if not error.retryable or attempt == self.max_retries - 1:
                    # Non-retryable or last attempt
                    return LLMResponse(
                        success=False,
                        provider=provider_label,
                        error=error,
                    )

                logger.warning(
                    f"{provider_label} attempt {attempt + 1}/{self.max_retries} failed: "
                    f"{error.category.name} - {error.message}. Retrying in {delay:.1f}s..."
                )
                await asyncio.sleep(delay)
                delay *= 2  # Exponential backoff

        # All retries exhausted
        final_error = classify_error(
            last_error or Exception("All retries exhausted"),
        )
        return LLMResponse(
            success=False,
            provider=provider_label,
            error=final_error,
        )

    async def _query_kimi(
        self, prompt: str, system_prompt: str | None = None
    ) -> LLMResponse:
        """Query KIMI K2.5 API.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt

        Returns:
            LLMResponse with result or error
        """
        try:
            from llm.kimi_client import KimiClient, KimiConfig, KimiMessage

            config = KimiConfig()
            if not config.api_key:
                return LLMResponse(
                    success=False,
                    provider="KIMI K2.5",
                    error=ProviderError(
                        category=ErrorCategory.NOT_CONFIGURED,
                        message="KIMI_API_KEY not configured",
                        retryable=False,
                        should_fallback=True,
                    ),
                )

            async with KimiClient(config) as client:
                messages = []
                if system_prompt:
                    messages.append(KimiMessage(role="system", content=system_prompt))
                messages.append(KimiMessage(role="user", content=prompt))

                result = await client.chat(
                    messages=messages, temperature=0.3, max_tokens=500
                )

                if not result.success:
                    error = classify_error(
                        Exception(result.error or "Unknown error"),
                        result.raw_response.get("status")
                        if result.raw_response
                        else None,
                    )
                    return LLMResponse(
                        success=False,
                        provider="KIMI K2.5",
                        error=error,
                        raw_response=result.raw_response,
                    )

                # Parse response for confidence score
                content = result.content or ""
                confidence, rationale = self._parse_confidence_response(content)

                return LLMResponse(
                    success=True,
                    content=content,
                    confidence_score=confidence,
                    rationale=rationale,
                    provider="KIMI K2.5",
                    raw_response=result.raw_response,
                )

        except ImportError:
            return LLMResponse(
                success=False,
                provider="KIMI K2.5",
                error=ProviderError(
                    category=ErrorCategory.NOT_CONFIGURED,
                    message="KimiClient not available",
                    retryable=False,
                    should_fallback=True,
                ),
            )
        except Exception as e:
            return LLMResponse(
                success=False,
                provider="KIMI K2.5",
                error=classify_error(e),
            )

    async def _query_zai(
        self, prompt: str, system_prompt: str | None = None
    ) -> LLMResponse:
        """Query Z.ai GLM-5 API.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt

        Returns:
            LLMResponse with result or error
        """
        try:
            from llm.zai_client import ZaiClient, ZaiConfig, ZaiMessage

            config = ZaiConfig()
            if not config.api_key:
                return LLMResponse(
                    success=False,
                    provider="GLM-5 (Z.ai)",
                    error=ProviderError(
                        category=ErrorCategory.NOT_CONFIGURED,
                        message="ZAI_API_KEY not configured",
                        retryable=False,
                        should_fallback=True,
                    ),
                )

            async with ZaiClient(config) as client:
                messages = []
                if system_prompt:
                    messages.append(ZaiMessage(role="system", content=system_prompt))
                messages.append(ZaiMessage(role="user", content=prompt))

                result = await client.chat(
                    messages=messages, temperature=0.3, max_tokens=500
                )

                if not result.success:
                    error = classify_error(
                        Exception(result.error or "Unknown error"),
                        result.raw_response.get("status")
                        if result.raw_response
                        else None,
                    )
                    return LLMResponse(
                        success=False,
                        provider="GLM-5 (Z.ai)",
                        error=error,
                        raw_response=result.raw_response,
                    )

                content = result.content or ""
                confidence, rationale = self._parse_confidence_response(content)

                return LLMResponse(
                    success=True,
                    content=content,
                    confidence_score=confidence,
                    rationale=rationale,
                    provider="GLM-5 (Z.ai)",
                    raw_response=result.raw_response,
                )

        except ImportError:
            return LLMResponse(
                success=False,
                provider="GLM-5 (Z.ai)",
                error=ProviderError(
                    category=ErrorCategory.NOT_CONFIGURED,
                    message="ZaiClient not available",
                    retryable=False,
                    should_fallback=True,
                ),
            )
        except Exception as e:
            return LLMResponse(
                success=False,
                provider="GLM-5 (Z.ai)",
                error=classify_error(e),
            )

    async def _query_zhipu(
        self, prompt: str, system_prompt: str | None = None
    ) -> LLMResponse:
        """Query Zhipu GLM-4.7 API.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt

        Returns:
            LLMResponse with result or error
        """
        try:
            from llm.zhipu_client import ZaiError, ZaiMessage, ZhipuClient

            # Try ZHIPU_API_KEY first, fall back to ZAI_API_KEY
            api_key = os.getenv("ZHIPU_API_KEY") or os.getenv("ZAI_API_KEY")
            if not api_key:
                return LLMResponse(
                    success=False,
                    provider="GLM-4.7 (Zhipu)",
                    error=ProviderError(
                        category=ErrorCategory.NOT_CONFIGURED,
                        message="Neither ZHIPU_API_KEY nor ZAI_API_KEY configured",
                        retryable=False,
                        should_fallback=True,
                    ),
                )

            # ZhipuClient uses synchronous requests with proper error handling
            client = ZhipuClient(api_key=api_key)
            messages = []
            if system_prompt:
                messages.append(ZaiMessage(role="system", content=system_prompt))
            messages.append(ZaiMessage(role="user", content=prompt))

            response = client.chat(messages=messages, temperature=0.3, max_tokens=500)

            content = response.content or ""
            confidence, rationale = self._parse_confidence_response(content)

            return LLMResponse(
                success=True,
                content=content,
                confidence_score=confidence,
                rationale=rationale,
                provider="GLM-4.7 (Zhipu)",
                raw_response=response.raw_response,
            )

        except ZaiError as e:
            # Extract status code if available
            status_code = None
            if hasattr(e, "response") and hasattr(e.response, "status_code"):
                status_code = e.response.status_code
            return LLMResponse(
                success=False,
                provider="GLM-4.7 (Zhipu)",
                error=classify_error(e, status_code),
            )
        except ImportError:
            return LLMResponse(
                success=False,
                provider="GLM-4.7 (Zhipu)",
                error=ProviderError(
                    category=ErrorCategory.NOT_CONFIGURED,
                    message="ZhipuClient not available",
                    retryable=False,
                    should_fallback=True,
                ),
            )
        except Exception as e:
            return LLMResponse(
                success=False,
                provider="GLM-4.7 (Zhipu)",
                error=classify_error(e),
            )

    async def _query_minimax(
        self, prompt: str, system_prompt: str | None = None
    ) -> LLMResponse:
        """Query MiniMax API.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt

        Returns:
            LLMResponse with result or error
        """
        try:
            from llm.minimax_client import MiniMaxClient, MiniMaxConfig, MiniMaxMessage

            config = MiniMaxConfig()
            if not config.api_key:
                return LLMResponse(
                    success=False,
                    provider="MiniMax",
                    error=ProviderError(
                        category=ErrorCategory.NOT_CONFIGURED,
                        message="MINIMAX_API_KEY not configured",
                        retryable=False,
                        should_fallback=True,
                    ),
                )

            async with MiniMaxClient(config) as client:
                messages = []
                if system_prompt:
                    messages.append(
                        MiniMaxMessage(role="system", content=system_prompt)
                    )
                messages.append(MiniMaxMessage(role="user", content=prompt))

                result = await client.chat(
                    messages=messages, temperature=0.3, max_tokens=500
                )

                if not result.success:
                    error = classify_error(
                        Exception(result.error or "Unknown error"),
                        result.raw_response.get("status")
                        if result.raw_response
                        else None,
                    )
                    return LLMResponse(
                        success=False,
                        provider="MiniMax",
                        error=error,
                        raw_response=result.raw_response,
                    )

                content = result.content or ""
                confidence, rationale = self._parse_confidence_response(content)

                return LLMResponse(
                    success=True,
                    content=content,
                    confidence_score=confidence,
                    rationale=rationale,
                    provider="MiniMax",
                    raw_response=result.raw_response,
                )

        except ImportError:
            return LLMResponse(
                success=False,
                provider="MiniMax",
                error=ProviderError(
                    category=ErrorCategory.NOT_CONFIGURED,
                    message="MiniMaxClient not available",
                    retryable=False,
                    should_fallback=True,
                ),
            )
        except Exception as e:
            return LLMResponse(
                success=False,
                provider="MiniMax",
                error=classify_error(e),
            )

    def _parse_confidence_response(self, content: str) -> tuple[float, str]:
        """Parse confidence score and rationale from LLM response.

        Args:
            content: Raw LLM response content

        Returns:
            Tuple of (confidence_score, rationale)
        """
        confidence = 50.0  # Default neutral
        rationale = "No rationale provided"

        lines = content.split("\n")
        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Match CONFIDENCE: [number]
            if re.match(r"^CONFIDENCE\s*:", line, re.IGNORECASE):
                match = re.search(r"(-?\d+(?:\.\d+)?)", line)
                if match:
                    confidence = float(match.group(1))
                    confidence = max(0.0, min(100.0, confidence))

            # Match RATIONALE: [text]
            elif re.match(r"^RATIONALE\s*:", line, re.IGNORECASE):
                rationale = re.sub(
                    r"^RATIONALE\s*:", "", line, flags=re.IGNORECASE
                ).strip()

        return confidence, rationale

    async def query(
        self,
        prompt: str,
        system_prompt: str | None = None,
        providers: list[str] | None = None,
    ) -> LLMResponse:
        """Query LLM providers in order until one succeeds.

        Args:
            prompt: User prompt to send to LLM
            system_prompt: Optional system prompt
            providers: Optional list of provider names to try (overrides default order)

        Returns:
            LLMResponse from the first successful provider, or error response
        """
        provider_list = providers or self.provider_order
        errors: list[tuple[str, ProviderError]] = []

        for provider_name in provider_list:
            # Check if provider is available
            available, reason = self._is_provider_available(provider_name)
            if not available:
                logger.debug(f"Skipping {provider_name}: {reason}")
                continue

            logger.info(f"Trying LLM provider: {provider_name}")

            # Get the query function for this provider
            query_fn = getattr(self, f"_query_{provider_name}", None)
            if not query_fn:
                logger.warning(f"Unknown provider: {provider_name}")
                continue

            # Query with retry
            response = await self._query_with_retry(
                provider_name, query_fn, prompt, system_prompt
            )

            if response.success:
                logger.info(
                    f"Successfully got response from {response.provider} "
                    f"(confidence: {response.confidence_score:.1f})"
                )
                return response

            # Log error and continue to next provider
            if response.error:
                errors.append((provider_name, response.error))
                if response.error.should_fallback:
                    logger.warning(
                        f"{provider_name} failed ({response.error.category.name}): "
                        f"{response.error.message}. Falling back..."
                    )
                else:
                    logger.error(
                        f"{provider_name} failed ({response.error.category.name}): "
                        f"{response.error.message}. Not retryable."
                    )
                    break

        # All providers failed
        error_summary = "; ".join(
            f"{name}: {err.category.name}" for name, err in errors
        )
        logger.error(f"All LLM providers failed: {error_summary}")

        return LLMResponse(
            success=False,
            content="",
            confidence_score=50.0,
            rationale="All LLM providers failed",
            provider="none",
            error=ProviderError(
                category=ErrorCategory.UNKNOWN,
                message=f"All providers failed: {error_summary}",
                retryable=False,
                should_fallback=False,
            ),
        )

    def get_provider_status(self) -> dict[str, dict[str, Any]]:
        """Get status of all providers.

        Returns:
            Dictionary with provider availability status
        """
        status = {}
        for provider_name in self.provider_order:
            available, reason = self._is_provider_available(provider_name)
            config = PROVIDER_CONFIGS.get(provider_name)
            status[provider_name] = {
                "available": available,
                "reason": reason,
                "priority": config.priority if config else 0,
                "label": config.name if config else provider_name,
            }
        return status
