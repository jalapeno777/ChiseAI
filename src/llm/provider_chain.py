"""LLM Provider Chain with robust fallback handling.

Provides a unified interface for multiple LLM providers with:
- Error classification (auth, scope, quota, rate, network)
- Automatic fallback between providers
- Configurable provider priority
- Proper async/sync handling
- Metrics collection for burn-in observability

Provider Priority (default):
1. KIMI Compat (Adapter) - Primary
2. KIMI (Direct) - Secondary
3. Z.ai (GLM-5) - Tertiary

Deprecated aliases:
- zhipu -> zai

MiniMax remains supported but disabled by default and omitted from default order.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from llm.observability import ChainMetrics, ProviderMetricsExporter

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
    "kimi_compat": ProviderConfig(
        name="KIMI Compat (Adapter)",
        api_key_env="KIMI_API_KEY",  # Reuses existing Kimi API key
        enabled_env="KIMI_COMPAT_ENABLED",
        enabled_default=True,  # ENABLED by default - Kimi MUST route through adapter
        priority=0,  # Highest priority - before direct kimi
    ),
    "kimi": ProviderConfig(
        name="KIMI K2.5",
        api_key_env="KIMI_API_KEY",
        enabled_env="KIMI_ENABLED",
        enabled_default=True,
        priority=1,
    ),
    "zai": ProviderConfig(
        name="GLM-5 (Z.ai)",
        api_key_env="ZAI_API_KEY",  # Also supports Z_AI_API_KEY via _is_provider_available
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

    Provider order: KIMI Compat -> KIMI Direct -> GLM-5 (MiniMax disabled by default)

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
        enable_metrics: bool = True,
        metrics_exporter: ProviderMetricsExporter | None = None,
        circuit_breaker: Any | None = None,
        health_monitor: Any | None = None,
    ):
        """Initialize the provider chain.

        Args:
            provider_order: Ordered list of provider names to try
            max_retries: Maximum retries per provider for retryable errors
            retry_delay: Initial retry delay (exponential backoff)
            enable_metrics: Whether to collect metrics during burn-in
            metrics_exporter: Optional exporter for InfluxDB integration
            circuit_breaker: Optional CircuitBreaker instance for proactive
                failure detection. If None, a default is created.
            health_monitor: Optional HealthMonitor instance for background
                health checking. If provided, it updates the circuit breaker
                based on periodic health checks.
        """
        # Provider Order Enforcement (LLM-PROVIDER-FIX-003):
        # 1. kimi_compat MUST be tried before kimi (adapter preferred over direct)
        # 2. KIMI_COMPAT_ENABLED defaults to true (see PROVIDER_CONFIGS)
        # 3. Adapter container health is checked before use
        #
        # TEMPORARY: MiniMax disabled due to PAPER-LLM-DIAG-001
        # To re-enable: Add "minimax" back to the list
        # Re-enable checklist:
        # 1. Verify MINIMAX_API_KEY is configured
        # 2. Set MINIMAX_ENABLED=true
        # 3. Test with: python -m pytest tests/test_llm/test_provider_chain.py -v -k minimax
        # 4. Monitor burn-in metrics for MiniMax success rate
        self.provider_order = self._normalize_provider_order(
            provider_order
            or [
                "zai",
                "minimax",
            ]
        )
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._provider_stats: dict[str, dict[str, Any]] = {}

        # Metrics collection for burn-in observability
        self._enable_metrics = enable_metrics
        self._metrics_exporter = metrics_exporter
        self._chain_metrics: ChainMetrics | None = None
        if enable_metrics:
            from llm.observability import ChainMetrics

            self._chain_metrics = ChainMetrics()

        # Circuit breaker for proactive failure detection (ST-MVP-007)
        if circuit_breaker is not None:
            self._circuit_breaker = circuit_breaker
        else:
            from llm.circuit_breaker import CircuitBreaker

            self._circuit_breaker = CircuitBreaker()

        # Health monitor for background health checking (ST-MVP-007)
        self._health_monitor = health_monitor

    def _normalize_provider_order(self, provider_order: list[str]) -> list[str]:
        """Normalize provider order with backward-compatible aliases.

        - "zhipu" is treated as a deprecated alias for "zai".
        - Duplicates are removed while preserving order.
        """
        normalized: list[str] = []
        for provider in provider_order:
            canonical = provider
            if provider == "zhipu":
                logger.warning(
                    "Provider 'zhipu' is deprecated and treated as alias for 'zai'"
                )
                canonical = "zai"

            if canonical not in normalized:
                normalized.append(canonical)

        return normalized

    def _resolve_adapter_base_urls(self) -> list[str]:
        """Resolve adapter base URLs for mixed network topologies.

        Priority:
        1. Explicit KIMI_COMPAT_BASE_URL (single source of truth when provided)
        2. Docker service DNS (intra-network)
        3. host.docker.internal (agent/container to host)
        """
        explicit = os.getenv("KIMI_COMPAT_BASE_URL")
        if explicit:
            return [explicit]

        return [
            "http://chiseai-kimi-adapter:8002/v1",
            "http://host.docker.internal:8002/v1",
        ]

    def _resolve_kimi_compat_models(self) -> list[str]:
        """Resolve ordered KIMI models for adapter requests.

        Priority:
        1. KIMI_MODEL (default: kimi-for-coding)
        2. KIMI_FALLBACK_MODEL (default: kimi-k2.5)
        """
        primary = os.getenv("KIMI_MODEL", "kimi-for-coding")
        fallback = os.getenv("KIMI_FALLBACK_MODEL", "kimi-k2.5")

        ordered: list[str] = []
        for model in (primary, fallback):
            if model and model not in ordered:
                ordered.append(model)
        return ordered

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
            # Special case: Zhipu can use ZAI_API_KEY or Z_AI_API_KEY as fallback
            if provider_name == "zhipu":
                zai_key = os.getenv("ZAI_API_KEY") or os.getenv("Z_AI_API_KEY")
                if zai_key:
                    return True, None
            # Special case: ZAI can use Z_AI_API_KEY as fallback
            if provider_name == "zai":
                zai_key = os.getenv("Z_AI_API_KEY")
                if zai_key:
                    return True, None
            return False, f"{config.api_key_env} not set"

        # Special case: Check KIMI adapter container is reachable
        if provider_name == "kimi_compat":
            if not self._is_adapter_container_reachable():
                return False, "KIMI adapter container not reachable"

        return True, None

    def _is_adapter_container_reachable(self) -> bool:
        """Check if KIMI adapter container is reachable.

        Performs a lightweight health check on the adapter container
        to ensure it's available before attempting to use it.

        Returns:
            True if adapter is reachable, False otherwise.
        """
        import socket

        try:
            from urllib.parse import urlparse

            for base_url in self._resolve_adapter_base_urls():
                parsed = urlparse(base_url)
                host = parsed.hostname or "chiseai-kimi-adapter"
                port = parsed.port or 8002

                # Try to connect with a short timeout
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2.0)  # 2 second timeout for health check
                result = sock.connect_ex((host, port))
                sock.close()

                if result == 0:
                    return True
            return False
        except Exception:
            return False

    def _record_attempt(self, provider_name: str, latency_ms: float = 0.0) -> None:
        """Record a provider attempt for metrics.

        Args:
            provider_name: Name of the provider
            latency_ms: Latency in milliseconds
        """
        if not self._enable_metrics or not self._chain_metrics:
            return

        config = PROVIDER_CONFIGS.get(provider_name)
        provider_label = config.name if config else provider_name

        metrics = self._chain_metrics.get_or_create_provider_metrics(
            provider_name, provider_label
        )
        metrics.record_attempt(latency_ms)

        if self._metrics_exporter:
            self._metrics_exporter.log_burn_in_event(
                "attempt", provider_name, {"latency_ms": latency_ms}
            )

    def _record_success(self, provider_name: str, latency_ms: float = 0.0) -> None:
        """Record a successful provider response for metrics.

        Args:
            provider_name: Name of the provider
            latency_ms: Latency in milliseconds
        """
        if not self._enable_metrics or not self._chain_metrics:
            return

        config = PROVIDER_CONFIGS.get(provider_name)
        provider_label = config.name if config else provider_name

        metrics = self._chain_metrics.get_or_create_provider_metrics(
            provider_name, provider_label
        )
        metrics.record_success(latency_ms)
        self._chain_metrics.record_query_success(provider_name)

        if self._metrics_exporter:
            self._metrics_exporter.log_burn_in_event(
                "success", provider_name, {"latency_ms": latency_ms}
            )
            self._metrics_exporter.export_provider_metrics(metrics)

    def _record_failure(
        self,
        provider_name: str,
        error_category: ErrorCategory,
        fallback_reason: str | None = None,
    ) -> None:
        """Record a failed provider response for metrics.

        Args:
            provider_name: Name of the provider
            error_category: Category of the error
            fallback_reason: Optional detailed reason for fallback
        """
        if not self._enable_metrics or not self._chain_metrics:
            return

        config = PROVIDER_CONFIGS.get(provider_name)
        provider_label = config.name if config else provider_name

        metrics = self._chain_metrics.get_or_create_provider_metrics(
            provider_name, provider_label
        )
        metrics.record_failure(error_category, fallback_reason)
        self._chain_metrics.record_fallback()

        if self._metrics_exporter:
            self._metrics_exporter.log_burn_in_event(
                "failure",
                provider_name,
                {
                    "error_category": error_category.name,
                    "fallback_reason": fallback_reason,
                },
            )

    def get_metrics_report(self) -> dict[str, Any]:
        """Get a metrics report for burn-in monitoring.

        Returns:
            Dictionary with chain and provider metrics
        """
        if not self._chain_metrics:
            return {"enabled": False, "message": "Metrics collection is disabled"}

        return {
            "enabled": True,
            "metrics": self._chain_metrics.to_dict(),
        }

    def export_metrics(self) -> dict[str, Any] | None:
        """Export current metrics to InfluxDB if exporter is configured.

        Returns:
            Export result or None if no exporter configured
        """
        if not self._metrics_exporter or not self._chain_metrics:
            return None

        result = self._metrics_exporter.export_chain_metrics(self._chain_metrics)

        # Also export individual provider metrics
        for metrics in self._chain_metrics.provider_metrics.values():
            self._metrics_exporter.export_provider_metrics(metrics)

        return result

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
        start_time = time.time()

        for attempt in range(self.max_retries):
            # Record attempt
            self._record_attempt(provider_name)

            try:
                response = await query_fn(*args, **kwargs)
                latency_ms = (time.time() - start_time) * 1000

                if response.success:
                    # Record success with latency
                    self._record_success(provider_name, latency_ms)
                    return response

                # If response has error but succeeded flag is False, check if retryable
                if response.error and not response.error.retryable:
                    # Record failure
                    self._record_failure(
                        provider_name,
                        response.error.category,
                        response.error.message,
                    )
                    return response

                last_error = Exception(
                    response.error.message if response.error else "Unknown error"
                )
            except Exception as e:
                last_error = e
                error = classify_error(e)

                if not error.retryable or attempt == self.max_retries - 1:
                    # Non-retryable or last attempt - record failure
                    self._record_failure(
                        provider_name,
                        error.category,
                        error.message,
                    )
                    return LLMResponse(
                        success=False,
                        provider=provider_label,
                        error=error,
                    )

                logger.warning(
                    f"{provider_label} attempt {attempt + 1}/{self.max_retries} "
                    f"failed: {error.category.name} - {error.message}. "
                    f"Retrying in {delay:.1f}s..."
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

    async def _query_kimi_compat(
        self, prompt: str, system_prompt: str | None = None
    ) -> LLMResponse:
        """Query KIMI via OpenAI-compatible adapter.

        Makes HTTP requests to KIMI_COMPAT_BASE_URL (default: http://chiseai-kimi-adapter:8002/v1)
        using OpenAI-compatible client pattern.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt

        Returns:
            LLMResponse with result or error
        """
        import os

        import aiohttp

        # For adapter routing, upstream auth is handled by the adapter container itself.
        # Do not require KIMI_API_KEY in this caller container.
        api_key = os.getenv("KIMI_API_KEY", "")

        # Resolve adapter endpoint for this runtime (service DNS or host fallback)
        base_url = None
        for candidate in self._resolve_adapter_base_urls():
            try:
                from urllib.parse import urlparse

                parsed = urlparse(candidate)
                host = parsed.hostname or "chiseai-kimi-adapter"
                port = parsed.port or 8002
                import socket

                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2.0)
                result = sock.connect_ex((host, port))
                sock.close()
                if result == 0:
                    base_url = candidate
                    break
            except Exception:
                continue

        if not base_url:
            return LLMResponse(
                success=False,
                provider="KIMI Compat (Adapter)",
                error=ProviderError(
                    category=ErrorCategory.NETWORK,
                    message=(
                        "KIMI adapter unreachable via configured routes: "
                        + ", ".join(self._resolve_adapter_base_urls())
                    ),
                    retryable=True,
                    should_fallback=True,
                ),
            )

        # Build messages
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "claude-code/0.1.0",
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            model_candidates = self._resolve_kimi_compat_models()
            async with aiohttp.ClientSession() as session:
                for idx, model_name in enumerate(model_candidates):
                    payload = {
                        "model": model_name,
                        "messages": messages,
                        "temperature": 0.3,
                        "max_tokens": 500,
                        # Request direct answer content instead of reasoning-only output.
                        "thinking": {"type": "disabled"},
                    }
                    async with session.post(
                        f"{base_url}/chat/completions",
                        json=payload,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=60),
                    ) as response:
                        response_data = await response.json()

                        if response.status == 200:
                            # Extract content from response
                            choices = response_data.get("choices", [])
                            if choices:
                                message = choices[0].get("message", {})
                                content = message.get("content", "")
                                if not content:
                                    # Some models return reasoning_content when content is empty.
                                    content = message.get("reasoning_content", "")
                                confidence, rationale = self._parse_confidence_response(
                                    content
                                )

                                return LLMResponse(
                                    success=True,
                                    content=content,
                                    confidence_score=confidence,
                                    rationale=rationale,
                                    provider="KIMI Compat (Adapter)",
                                    raw_response=response_data,
                                )
                            return LLMResponse(
                                success=False,
                                provider="KIMI Compat (Adapter)",
                                error=ProviderError(
                                    category=ErrorCategory.UNKNOWN,
                                    message="No choices in response",
                                    retryable=False,
                                    should_fallback=True,
                                ),
                            )

                        # Handle errors
                        error_msg = response_data.get("error", {}).get(
                            "message", f"HTTP {response.status}"
                        )

                        # Retry same provider with next model on model-selection failures.
                        model_related_failure = response.status in (400, 404, 422) or (
                            response.status == 403 and "model" in error_msg.lower()
                        )
                        has_next_model = idx < len(model_candidates) - 1
                        if model_related_failure and has_next_model:
                            logger.warning(
                                "KIMI adapter model '%s' failed (%s); trying fallback model '%s'",
                                model_name,
                                error_msg,
                                model_candidates[idx + 1],
                            )
                            continue

                        if response.status == 401:
                            return LLMResponse(
                                success=False,
                                provider="KIMI Compat (Adapter)",
                                error=ProviderError(
                                    category=ErrorCategory.AUTH,
                                    message=f"Authentication failed: {error_msg}",
                                    status_code=401,
                                    retryable=False,
                                    should_fallback=True,
                                ),
                            )
                        elif response.status == 403:
                            # Telemetry tag for Kimi entitlement block tracking
                            fallback_reason = "kimi-entitlement-block"
                            if "coding agent" in error_msg.lower():
                                fallback_reason = "kimi-entitlement-block"
                            self._record_failure(
                                "kimi_compat",
                                ErrorCategory.SCOPE,
                                fallback_reason=fallback_reason,
                            )
                            return LLMResponse(
                                success=False,
                                provider="KIMI Compat (Adapter)",
                                error=ProviderError(
                                    category=ErrorCategory.SCOPE,
                                    message=f"Permission denied: {error_msg}",
                                    status_code=403,
                                    retryable=False,
                                    should_fallback=True,
                                ),
                            )
                        elif response.status == 429:
                            return LLMResponse(
                                success=False,
                                provider="KIMI Compat (Adapter)",
                                error=ProviderError(
                                    category=ErrorCategory.RATE_LIMIT,
                                    message=f"Rate limit exceeded: {error_msg}",
                                    status_code=429,
                                    retryable=True,
                                    should_fallback=True,
                                ),
                            )
                        elif response.status >= 500:
                            return LLMResponse(
                                success=False,
                                provider="KIMI Compat (Adapter)",
                                error=ProviderError(
                                    category=ErrorCategory.SERVER,
                                    message=f"Server error: {error_msg}",
                                    status_code=response.status,
                                    retryable=True,
                                    should_fallback=True,
                                ),
                            )
                        else:
                            return LLMResponse(
                                success=False,
                                provider="KIMI Compat (Adapter)",
                                error=ProviderError(
                                    category=ErrorCategory.CLIENT,
                                    message=f"Client error: {error_msg}",
                                    status_code=response.status,
                                    retryable=False,
                                    should_fallback=True,
                                ),
                            )

        except aiohttp.ClientError as e:
            return LLMResponse(
                success=False,
                provider="KIMI Compat (Adapter)",
                error=ProviderError(
                    category=ErrorCategory.NETWORK,
                    message=f"Network error: {str(e)}",
                    retryable=True,
                    should_fallback=True,
                ),
            )
        except Exception as e:
            return LLMResponse(
                success=False,
                provider="KIMI Compat (Adapter)",
                error=classify_error(e),
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
                    messages=messages,
                    temperature=0.3,
                    max_tokens=500,
                    thinking=False,
                )

                if not result.success:
                    error = classify_error(
                        Exception(result.error or "Unknown error"),
                        (
                            result.raw_response.get("status")
                            if result.raw_response
                            else None
                        ),
                    )
                    return LLMResponse(
                        success=False,
                        provider="KIMI K2.5",
                        error=error,
                        raw_response=result.raw_response,
                    )

                # Parse response for confidence score
                content = result.content or result.reasoning_content or ""
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
                        (
                            result.raw_response.get("status")
                            if result.raw_response
                            else None
                        ),
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
                        (
                            result.raw_response.get("status")
                            if result.raw_response
                            else None
                        ),
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

        # Record query start
        if self._chain_metrics:
            self._chain_metrics.record_query_start()

        for provider_name in provider_list:
            # Check if provider is available (environment/config check)
            available, reason = self._is_provider_available(provider_name)
            if not available:
                logger.debug(f"Skipping {provider_name}: {reason}")
                continue

            # Check circuit breaker state (ST-MVP-007)
            if not self._circuit_breaker.is_available(provider_name):
                cb_state = self._circuit_breaker.get_state(provider_name)
                logger.info(
                    f"Skipping {provider_name}: circuit breaker is {cb_state.name}"
                )
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

            # Record result to circuit breaker (ST-MVP-007)
            if response.success:
                self._circuit_breaker.record_success(provider_name)
            else:
                self._circuit_breaker.record_failure(provider_name)

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

        # Record query failure
        if self._chain_metrics:
            self._chain_metrics.record_query_failure()

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
            cb_state = self._circuit_breaker.get_state(provider_name)
            status[provider_name] = {
                "available": available,
                "reason": reason,
                "priority": config.priority if config else 0,
                "label": config.name if config else provider_name,
                "circuit_breaker_state": cb_state.name,
            }
        return status

    def get_circuit_breaker_states(self) -> dict[str, dict[str, Any]]:
        """Get circuit breaker states for all providers.

        Returns:
            Dictionary mapping provider names to circuit breaker info
        """
        return self._circuit_breaker.get_all_states()
