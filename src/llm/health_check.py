"""Pre-call health checking for LLM providers.

Provides lightweight health checks per provider type to detect issues
before attempting actual API calls. Health results are cached with
configurable TTL to avoid excessive checking.

For ST-MVP-007: LLM Provider Redundancy Enhancement
"""

from __future__ import annotations

import logging
import os
import socket
import threading
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Provider health status levels."""

    HEALTHY = auto()  # Provider is responding normally
    DEGRADED = auto()  # Provider is slow or partially available
    UNAVAILABLE = auto()  # Provider is not reachable
    UNKNOWN = auto()  # Health status not yet determined


@dataclass
class HealthCheckResult:
    """Result of a provider health check."""

    provider: str
    status: HealthStatus
    latency_ms: float = 0.0
    message: str = ""
    checked_at: float = field(default_factory=time.monotonic)


class ProviderHealthChecker:
    """Performs lightweight health checks on LLM providers.

    Each provider type has a specific check strategy:
    - kimi_compat: TCP socket check to adapter container
    - kimi: Validate API key exists
    - zai: Validate API key exists
    - zhipu: Validate API key exists
    - minimax: Validate API key exists

    Results are cached with configurable TTL.

    Usage:
        checker = ProviderHealthChecker()
        result = checker.check_health("kimi")
        if result.status == HealthStatus.HEALTHY:
            # Provider is available
    """

    def __init__(
        self,
        timeout_seconds: float = 5.0,
        cache_ttl_seconds: float = 60.0,
    ):
        """Initialize the health checker.

        Args:
            timeout_seconds: Timeout for health check connections
            cache_ttl_seconds: Time-to-live for cached health results
        """
        self._timeout = timeout_seconds
        self._cache_ttl = cache_ttl_seconds
        self._cache: dict[str, HealthCheckResult] = {}
        self._cache_lock = threading.Lock()

    def check_health(self, provider: str) -> HealthCheckResult:
        """Check the health of a provider.

        Returns cached result if still valid, otherwise performs a fresh check.

        Args:
            provider: Provider name

        Returns:
            HealthCheckResult with status
        """
        # Check cache first
        with self._cache_lock:
            cached = self._cache.get(provider)
            if cached is not None:
                age = time.monotonic() - cached.checked_at
                if age < self._cache_ttl:
                    logger.debug(
                        "Health check for %s: using cached result (%s, age=%.1fs)",
                        provider,
                        cached.status.name,
                        age,
                    )
                    return cached

        # Perform fresh check
        check_fn = {
            "kimi_compat": self._check_kimi_compat,
            "kimi": self._check_api_key_provider,
            "zai": self._check_api_key_provider,
            "zhipu": self._check_api_key_provider,
            "minimax": self._check_api_key_provider,
        }.get(provider, self._check_generic)

        try:
            result = check_fn(provider)
        except Exception as e:
            result = HealthCheckResult(
                provider=provider,
                status=HealthStatus.UNAVAILABLE,
                message=f"Health check error: {e}",
            )

        # Cache the result
        with self._cache_lock:
            self._cache[provider] = result
        logger.info(
            "Health check for %s: %s (%s)",
            provider,
            result.status.name,
            result.message,
        )
        return result

    def check_all_health(
        self, providers: list[str] | None = None
    ) -> dict[str, HealthCheckResult]:
        """Check health of all or specified providers.

        Args:
            providers: List of provider names to check, or None for all known

        Returns:
            Dictionary mapping provider names to HealthCheckResult
        """
        if providers is None:
            providers = ["kimi_compat", "kimi", "zai", "zhipu", "minimax"]

        return {p: self.check_health(p) for p in providers}

    def invalidate_cache(self, provider: str | None = None) -> None:
        """Invalidate cached health check results.

        Args:
            provider: Provider to invalidate, or None for all
        """
        with self._cache_lock:
            if provider is None:
                self._cache.clear()
            else:
                self._cache.pop(provider, None)

    def _check_kimi_compat(self, provider: str) -> HealthCheckResult:
        """Check health of KIMI adapter container via TCP socket.

        Args:
            provider: Provider name (unused, for interface consistency)

        Returns:
            HealthCheckResult
        """
        base_urls = [
            os.getenv("KIMI_COMPAT_BASE_URL"),
            "http://chiseai-kimi-adapter:8002/v1",
            "http://host.docker.internal:8002/v1",
        ]
        # Filter None
        base_urls = [u for u in base_urls if u]

        start = time.monotonic()
        for base_url in base_urls:
            try:
                parsed = urlparse(base_url)
                host = parsed.hostname or "chiseai-kimi-adapter"
                port = parsed.port or 8002

                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(self._timeout)
                try:
                    result = sock.connect_ex((host, port))
                finally:
                    sock.close()

                latency_ms = (time.monotonic() - start) * 1000

                if result == 0:
                    return HealthCheckResult(
                        provider="kimi_compat",
                        status=HealthStatus.HEALTHY,
                        latency_ms=latency_ms,
                        message=f"Adapter reachable at {host}:{port}",
                    )
            except Exception:
                continue

        latency_ms = (time.monotonic() - start) * 1000
        return HealthCheckResult(
            provider="kimi_compat",
            status=HealthStatus.UNAVAILABLE,
            latency_ms=latency_ms,
            message="Adapter unreachable via all configured routes",
        )

    def _check_api_key_provider(self, provider: str) -> HealthCheckResult:
        """Check health of an API-key-based provider.

        Validates that the API key is configured. This is a lightweight check
        that doesn't make network calls.

        Args:
            provider: Provider name

        Returns:
            HealthCheckResult
        """
        key_env_map = {
            "kimi": ["KIMI_API_KEY"],
            "zai": ["ZAI_API_KEY", "Z_AI_API_KEY"],
            "zhipu": ["ZHIPU_API_KEY", "ZAI_API_KEY", "Z_AI_API_KEY"],
            "minimax": ["MINIMAX_API_KEY"],
        }

        key_envs = key_env_map.get(provider, [])
        for key_env in key_envs:
            if os.getenv(key_env):
                return HealthCheckResult(
                    provider=provider,
                    status=HealthStatus.HEALTHY,
                    message=f"API key configured ({key_env})",
                )

        return HealthCheckResult(
            provider=provider,
            status=HealthStatus.UNAVAILABLE,
            message=f"No API key found (checked: {', '.join(key_envs)})",
        )

    def _check_generic(self, provider: str) -> HealthCheckResult:
        """Generic health check for unknown providers.

        Args:
            provider: Provider name

        Returns:
            HealthCheckResult with UNKNOWN status
        """
        return HealthCheckResult(
            provider=provider,
            status=HealthStatus.UNKNOWN,
            message=f"No health check strategy for provider '{provider}'",
        )


__all__ = [
    "HealthCheckResult",
    "HealthStatus",
    "ProviderHealthChecker",
]
