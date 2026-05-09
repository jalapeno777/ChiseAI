"""Tests for LLM provider health checking.

Tests health status determination, caching, timeout behavior,
and integration with the provider chain.

For ST-MVP-007: LLM Provider Redundancy Enhancement
"""

import os
import time
from unittest.mock import MagicMock, patch

import pytest

from llm.health_check import HealthCheckResult, HealthStatus, ProviderHealthChecker


class TestHealthStatus:
    """Tests for HealthStatus enum."""

    def test_status_values(self):
        """Health status enum has expected values."""
        assert HealthStatus.HEALTHY is not None
        assert HealthStatus.DEGRADED is not None
        assert HealthStatus.UNAVAILABLE is not None
        assert HealthStatus.UNKNOWN is not None


class TestHealthCheckResult:
    """Tests for HealthCheckResult dataclass."""

    def test_result_fields(self):
        """HealthCheckResult has expected fields."""
        result = HealthCheckResult(
            provider="kimi",
            status=HealthStatus.HEALTHY,
            latency_ms=10.5,
            message="API key configured",
        )
        assert result.provider == "kimi"
        assert result.status == HealthStatus.HEALTHY
        assert result.latency_ms == 10.5
        assert result.message == "API key configured"
        assert result.checked_at > 0

    def test_result_default_fields(self):
        """HealthCheckResult has sensible defaults."""
        result = HealthCheckResult(
            provider="test",
            status=HealthStatus.UNKNOWN,
        )
        assert result.latency_ms == 0.0
        assert result.message == ""
        assert result.checked_at > 0


class TestProviderHealthCheckerAPIKeyProviders:
    """Tests for API-key-based provider health checks."""

    def test_api_key_provider_healthy_with_key(self):
        """Provider with API key is HEALTHY."""
        checker = ProviderHealthChecker()
        with patch.dict(os.environ, {"KIMI_API_KEY": "test-key"}):
            result = checker.check_health("kimi")
            assert result.status == HealthStatus.HEALTHY
            assert "KIMI_API_KEY" in result.message

    def test_api_key_provider_unavailable_without_key(self):
        """Provider without API key is UNAVAILABLE."""
        checker = ProviderHealthChecker()
        with patch.dict(os.environ, {}, clear=True):
            # Remove all possible API keys
            for key in [
                "KIMI_API_KEY",
                "ZAI_API_KEY",
                "Z_AI_API_KEY",
                "ZHIPU_API_KEY",
                "MINIMAX_API_KEY",
            ]:
                os.environ.pop(key, None)
            result = checker.check_health("kimi")
            assert result.status == HealthStatus.UNAVAILABLE

    def test_zai_healthy_with_z_ai_api_key(self):
        """Z.ai provider is healthy with Z_AI_API_KEY."""
        checker = ProviderHealthChecker()
        with patch.dict(os.environ, {"Z_AI_API_KEY": "test-key"}, clear=False):
            result = checker.check_health("zai")
            assert result.status == HealthStatus.HEALTHY

    def test_zai_healthy_with_zai_api_key(self):
        """Z.ai provider is healthy with ZAI_API_KEY."""
        checker = ProviderHealthChecker()
        env = {"ZAI_API_KEY": "test-key"}
        with patch.dict(os.environ, env, clear=False):
            result = checker.check_health("zai")
            assert result.status == HealthStatus.HEALTHY

    def test_minimax_unavailable_without_key(self):
        """MiniMax is unavailable without MINIMAX_API_KEY."""
        checker = ProviderHealthChecker()
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("MINIMAX_API_KEY", None)
            result = checker.check_health("minimax")
            assert result.status == HealthStatus.UNAVAILABLE


class TestProviderHealthCheckerCaching:
    """Tests for health check result caching."""

    def test_cached_result_returned_within_ttl(self):
        """Cached result is returned within TTL."""
        checker = ProviderHealthChecker(cache_ttl_seconds=5.0)

        with patch.dict(os.environ, {"KIMI_API_KEY": "test-key"}):
            result1 = checker.check_health("kimi")
            result2 = checker.check_health("kimi")

            # Same timestamp means cached
            assert result1.checked_at == result2.checked_at

    def test_expired_cache_triggers_new_check(self):
        """Expired cache triggers a fresh health check."""
        checker = ProviderHealthChecker(cache_ttl_seconds=0.05)

        with patch.dict(os.environ, {"KIMI_API_KEY": "test-key"}):
            result1 = checker.check_health("kimi")
            time.sleep(0.1)
            result2 = checker.check_health("kimi")

            # Different timestamp means fresh check
            assert result1.checked_at != result2.checked_at

    def test_invalidate_cache_for_provider(self):
        """Invalidating cache for a provider forces fresh check."""
        checker = ProviderHealthChecker(cache_ttl_seconds=60.0)

        with patch.dict(os.environ, {"KIMI_API_KEY": "test-key"}):
            result1 = checker.check_health("kimi")
            checker.invalidate_cache("kimi")
            result2 = checker.check_health("kimi")

            # Different timestamp after invalidation
            assert result1.checked_at != result2.checked_at

    def test_invalidate_all_cache(self):
        """Invalidating all cache clears everything."""
        checker = ProviderHealthChecker(cache_ttl_seconds=60.0)

        with patch.dict(os.environ, {"KIMI_API_KEY": "key1", "ZAI_API_KEY": "key2"}):
            checker.check_health("kimi")
            checker.check_health("zai")

            checker.invalidate_cache()

            # Both should be re-checked
            assert "kimi" not in checker._cache
            assert "zai" not in checker._cache


class TestProviderHealthCheckerKimiCompat:
    """Tests for KIMI compat (adapter) health check."""

    def test_kimi_compat_unreachable(self):
        """KIMI compat is UNAVAILABLE when adapter is unreachable."""
        checker = ProviderHealthChecker(timeout_seconds=0.1)

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("KIMI_COMPAT_BASE_URL", None)
            result = checker.check_health("kimi_compat")
            assert result.status == HealthStatus.UNAVAILABLE

    def test_kimi_compat_healthy_when_reachable(self):
        """KIMI compat is HEALTHY when adapter is reachable."""
        checker = ProviderHealthChecker(timeout_seconds=2.0)

        # Mock socket to simulate reachable adapter
        with patch("llm.health_check.socket.socket") as mock_socket_cls:
            mock_sock = MagicMock()
            mock_sock.connect_ex.return_value = 0  # Success
            mock_socket_cls.return_value = mock_sock

            result = checker.check_health("kimi_compat")
            assert result.status == HealthStatus.HEALTHY

    def test_kimi_compat_unreachable_on_connection_failure(self):
        """KIMI compat is UNAVAILABLE on connection failure."""
        checker = ProviderHealthChecker(timeout_seconds=2.0)

        with patch("llm.health_check.socket.socket") as mock_socket_cls:
            mock_sock = MagicMock()
            mock_sock.connect_ex.return_value = 1  # Connection refused
            mock_socket_cls.return_value = mock_sock

            result = checker.check_health("kimi_compat")
            assert result.status == HealthStatus.UNAVAILABLE


class TestProviderHealthCheckerGeneric:
    """Tests for generic/unknown provider health check."""

    def test_unknown_provider_returns_unknown(self):
        """Unknown providers return UNKNOWN status."""
        checker = ProviderHealthChecker()
        result = checker.check_health("unknown_provider")
        assert result.status == HealthStatus.UNKNOWN


class TestProviderHealthCheckerCheckAll:
    """Tests for check_all_health."""

    def test_check_all_returns_all_providers(self):
        """check_all_health returns results for all providers."""
        checker = ProviderHealthChecker()
        with patch.dict(os.environ, {}, clear=True):
            for key in [
                "KIMI_API_KEY",
                "ZAI_API_KEY",
                "Z_AI_API_KEY",
                "ZHIPU_API_KEY",
                "MINIMAX_API_KEY",
                "KIMI_COMPAT_BASE_URL",
            ]:
                os.environ.pop(key, None)

            results = checker.check_all_health(["kimi", "zai"])
            assert "kimi" in results
            assert "zai" in results

    def test_check_all_default_providers(self):
        """check_all_health uses all known providers by default."""
        checker = ProviderHealthChecker()
        with patch.dict(os.environ, {}, clear=True):
            for key in [
                "KIMI_API_KEY",
                "ZAI_API_KEY",
                "Z_AI_API_KEY",
                "ZHIPU_API_KEY",
                "MINIMAX_API_KEY",
                "KIMI_COMPAT_BASE_URL",
            ]:
                os.environ.pop(key, None)

            results = checker.check_all_health()
            assert set(results.keys()) == {
                "kimi_compat",
                "kimi",
                "zai",
                "zhipu",
                "minimax",
            }


class TestProviderHealthCheckerTimeout:
    """Tests for health check timeout behavior."""

    def test_timeout_configured(self):
        """Timeout is properly configured."""
        checker = ProviderHealthChecker(timeout_seconds=3.0)
        assert checker._timeout == 3.0

    def test_default_timeout(self):
        """Default timeout is 5.0 seconds."""
        checker = ProviderHealthChecker()
        assert checker._timeout == 5.0
