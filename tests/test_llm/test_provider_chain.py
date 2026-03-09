"""Tests for LLM provider chain with robust fallback handling.

Tests the LLMProviderChain class which provides:
- Error classification (auth, scope, quota, rate, network)
- Automatic fallback between providers
- Proper async/sync handling

Provider Priority: KIMI → GLM-5 → GLM-4.7 → MiniMax (disabled by default)
"""

import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from llm.provider_chain import (
    PROVIDER_CONFIGS,
    ErrorCategory,
    LLMProviderChain,
    LLMResponse,
    ProviderError,
    classify_error,
)


class TestErrorClassification:
    """Test suite for error classification functionality."""

    def test_classify_auth_error_401(self):
        """Test classification of 401 authentication errors."""
        error = Exception("Authentication failed: Invalid API key")
        result = classify_error(error, status_code=401)

        assert result.category == ErrorCategory.AUTH
        assert result.retryable is False
        assert result.should_fallback is True
        assert "Authentication failed" in result.message

    def test_classify_auth_error_keywords(self):
        """Test classification of auth errors by keywords."""
        test_cases = [
            Exception("Unauthorized access"),
            Exception("Invalid API key provided"),
            Exception("Authentication required"),
        ]

        for error in test_cases:
            result = classify_error(error)
            assert result.category == ErrorCategory.AUTH
            assert result.retryable is False

    def test_classify_scope_error_403(self):
        """Test classification of 403 permission errors."""
        error = Exception("Permission denied: insufficient scope")
        result = classify_error(error, status_code=403)

        assert result.category == ErrorCategory.SCOPE
        assert result.retryable is False
        assert result.should_fallback is True

    def test_classify_quota_error(self):
        """Test classification of quota exceeded errors."""
        error = Exception("Quota exceeded: daily limit reached")
        result = classify_error(error, status_code=403)

        assert result.category == ErrorCategory.QUOTA
        assert result.retryable is False
        assert result.should_fallback is True
        assert "quota" in result.message.lower()

    def test_classify_rate_limit_429(self):
        """Test classification of 429 rate limit errors."""
        error = Exception("Rate limit exceeded")
        result = classify_error(error, status_code=429)

        assert result.category == ErrorCategory.RATE_LIMIT
        assert result.retryable is True
        assert result.should_fallback is True

    def test_classify_rate_limit_keywords(self):
        """Test classification of rate limit by keywords."""
        error = Exception("Too many requests, please slow down")
        result = classify_error(error)

        assert result.category == ErrorCategory.RATE_LIMIT
        assert result.retryable is True

    def test_classify_network_error(self):
        """Test classification of network errors."""
        test_cases = [
            (Exception("Connection timeout"), "timeout"),
            (Exception("DNS resolution failed"), "dns"),
            (Exception("Network unreachable"), "network"),
            (Exception("Connection refused"), "connection"),
        ]

        for error, _ in test_cases:
            result = classify_error(error)
            assert result.category == ErrorCategory.NETWORK
            assert result.retryable is True
            assert result.should_fallback is True

    def test_classify_server_error_5xx(self):
        """Test classification of 5xx server errors."""
        error = Exception("Internal server error")
        result = classify_error(error, status_code=500)

        assert result.category == ErrorCategory.SERVER
        assert result.retryable is True
        assert result.should_fallback is True

    def test_classify_server_error_502(self):
        """Test classification of 502 bad gateway."""
        error = Exception("Bad gateway")
        result = classify_error(error, status_code=502)

        assert result.category == ErrorCategory.SERVER
        assert result.retryable is True

    def test_classify_client_error_4xx(self):
        """Test classification of 4xx client errors."""
        error = Exception("Bad request")
        result = classify_error(error, status_code=400)

        assert result.category == ErrorCategory.CLIENT
        assert result.retryable is False

    def test_classify_unknown_error(self):
        """Test classification of unknown errors."""
        error = Exception("Something went wrong")
        result = classify_error(error)

        assert result.category == ErrorCategory.UNKNOWN
        assert result.retryable is False
        assert result.should_fallback is True


class TestProviderChainInitialization:
    """Test provider chain initialization."""

    def test_default_provider_order(self):
        """Test default provider order."""
        chain = LLMProviderChain()

        # MiniMax temporarily disabled per PAPER-LLM-DIAG-001
        assert chain.provider_order == [
            "kimi_compat",
            "kimi",
            "zai",
            "zhipu",
            # "minimax",  # Disabled per PAPER-LLM-DIAG-001
        ]
        assert chain.max_retries == 3
        assert chain.retry_delay == 1.0

    def test_custom_provider_order(self):
        """Test custom provider order."""
        chain = LLMProviderChain(
            provider_order=["zai", "kimi"],
            max_retries=5,
            retry_delay=2.0,
        )

        assert chain.provider_order == ["zai", "kimi"]
        assert chain.max_retries == 5
        assert chain.retry_delay == 2.0

    def test_provider_configs_exist(self):
        """Test that all provider configs are defined."""
        expected_providers = ["kimi_compat", "kimi", "zai", "zhipu", "minimax"]

        for provider in expected_providers:
            assert provider in PROVIDER_CONFIGS
            config = PROVIDER_CONFIGS[provider]
            assert config.name
            assert config.api_key_env
            assert config.priority >= 0  # 0 is valid (highest priority)


class TestProviderAvailability:
    """Test provider availability checking."""

    def test_kimi_available_with_key(self):
        """Test KIMI is available when API key is set."""
        with patch.dict(os.environ, {"KIMI_API_KEY": "test-key"}, clear=True):
            chain = LLMProviderChain()
            available, reason = chain._is_provider_available("kimi")

            assert available is True
            assert reason is None

    def test_kimi_unavailable_without_key(self):
        """Test KIMI is unavailable without API key."""
        with patch.dict(os.environ, {}, clear=True):
            chain = LLMProviderChain()
            available, reason = chain._is_provider_available("kimi")

            assert available is False
            assert "KIMI_API_KEY" in reason

    def test_kimi_disabled_when_kimi_enabled_false(self):
        """Test KIMI is disabled when KIMI_ENABLED=false."""
        with patch.dict(
            os.environ,
            {"KIMI_API_KEY": "test-key", "KIMI_ENABLED": "false"},
            clear=True,
        ):
            chain = LLMProviderChain()
            available, reason = chain._is_provider_available("kimi")

            assert available is False
            assert "KIMI_ENABLED=false" in reason

    def test_zai_available_with_key(self):
        """Test Z.ai is available when API key is set."""
        with patch.dict(os.environ, {"ZAI_API_KEY": "test-key"}, clear=True):
            chain = LLMProviderChain()
            available, reason = chain._is_provider_available("zai")

            assert available is True
            assert reason is None

    def test_zhipu_available_with_zhipu_key(self):
        """Test Zhipu is available with ZHIPU_API_KEY."""
        with patch.dict(os.environ, {"ZHIPU_API_KEY": "test-key"}, clear=True):
            chain = LLMProviderChain()
            available, reason = chain._is_provider_available("zhipu")

            assert available is True
            assert reason is None

    def test_zhipu_available_with_zai_key_fallback(self):
        """Test Zhipu can use ZAI_API_KEY as fallback."""
        with patch.dict(os.environ, {"ZAI_API_KEY": "test-key"}, clear=True):
            chain = LLMProviderChain()
            available, reason = chain._is_provider_available("zhipu")

            assert available is True
            assert reason is None

    def test_zhipu_unavailable_without_any_key(self):
        """Test Zhipu is unavailable without any API key."""
        with patch.dict(os.environ, {}, clear=True):
            chain = LLMProviderChain()
            available, reason = chain._is_provider_available("zhipu")

            assert available is False
            assert "ZHIPU_API_KEY" in reason

    def test_minimax_disabled_by_default(self):
        """Test MiniMax is disabled by default."""
        with patch.dict(os.environ, {"MINIMAX_API_KEY": "test-key"}, clear=True):
            chain = LLMProviderChain()
            available, reason = chain._is_provider_available("minimax")

            assert available is False
            assert "MINIMAX_ENABLED" in reason

    def test_minimax_enabled_with_explicit_flag(self):
        """Test MiniMax is enabled when MINIMAX_ENABLED=true."""
        with patch.dict(
            os.environ,
            {"MINIMAX_API_KEY": "test-key", "MINIMAX_ENABLED": "true"},
            clear=True,
        ):
            chain = LLMProviderChain()
            available, reason = chain._is_provider_available("minimax")

            assert available is True
            assert reason is None


class TestProviderFallbackChain:
    """Test provider fallback chain behavior."""

    @pytest.mark.asyncio
    async def test_kimi_first_success_no_fallback(self):
        """Test that if KIMI succeeds, no fallback occurs."""
        with patch.dict(
            os.environ,
            {"KIMI_API_KEY": "test-key", "ZAI_API_KEY": "test-key"},
            clear=True,
        ):
            chain = LLMProviderChain()

            # Mock KIMI to succeed
            mock_response = LLMResponse(
                success=True,
                content="Test response",
                confidence_score=75.0,
                rationale="Test rationale",
                provider="KIMI K2.5",
            )
            chain._query_kimi = AsyncMock(return_value=mock_response)
            chain._query_zai = AsyncMock(side_effect=Exception("Should not be called"))

            result = await chain.query("Test prompt")

            assert result.success is True
            assert result.provider == "KIMI K2.5"
            chain._query_kimi.assert_called_once()
            chain._query_zai.assert_not_called()

    @pytest.mark.asyncio
    async def test_fallback_to_zai_when_kimi_fails(self):
        """Test fallback to Z.ai when KIMI fails."""
        with patch.dict(
            os.environ,
            {"KIMI_API_KEY": "test-key", "ZAI_API_KEY": "test-key"},
            clear=True,
        ):
            chain = LLMProviderChain()

            # Mock KIMI to fail with auth error
            kimi_response = LLMResponse(
                success=False,
                provider="KIMI K2.5",
                error=ProviderError(
                    category=ErrorCategory.AUTH,
                    message="Invalid API key",
                    should_fallback=True,
                ),
            )
            chain._query_kimi = AsyncMock(return_value=kimi_response)

            # Mock Z.ai to succeed
            zai_response = LLMResponse(
                success=True,
                content="Z.ai response",
                confidence_score=70.0,
                rationale="Z.ai rationale",
                provider="GLM-5 (Z.ai)",
            )
            chain._query_zai = AsyncMock(return_value=zai_response)

            result = await chain.query("Test prompt")

            assert result.success is True
            assert result.provider == "GLM-5 (Z.ai)"
            chain._query_kimi.assert_called_once()
            chain._query_zai.assert_called_once()

    @pytest.mark.asyncio
    async def test_fallback_chain_multiple_failures(self):
        """Test fallback through multiple providers."""
        with patch.dict(
            os.environ,
            {
                "KIMI_API_KEY": "test-key",
                "ZAI_API_KEY": "test-key",
                "ZHIPU_API_KEY": "test-key",
            },
            clear=True,
        ):
            chain = LLMProviderChain()

            # Mock KIMI and Z.ai to fail
            kimi_response = LLMResponse(
                success=False,
                provider="KIMI K2.5",
                error=ProviderError(
                    category=ErrorCategory.AUTH,
                    message="Auth failed",
                    should_fallback=True,
                ),
            )
            zai_response = LLMResponse(
                success=False,
                provider="GLM-5 (Z.ai)",
                error=ProviderError(
                    category=ErrorCategory.RATE_LIMIT,
                    message="Rate limited",
                    should_fallback=True,
                ),
            )
            zhipu_response = LLMResponse(
                success=True,
                content="Zhipu response",
                confidence_score=65.0,
                rationale="Zhipu rationale",
                provider="GLM-4.7 (Zhipu)",
            )

            chain._query_kimi = AsyncMock(return_value=kimi_response)
            chain._query_zai = AsyncMock(return_value=zai_response)
            chain._query_zhipu = AsyncMock(return_value=zhipu_response)

            result = await chain.query("Test prompt")

            assert result.success is True
            assert result.provider == "GLM-4.7 (Zhipu)"
            chain._query_kimi.assert_called_once()
            chain._query_zai.assert_called_once()
            chain._query_zhipu.assert_called_once()

    @pytest.mark.asyncio
    async def test_all_providers_fail(self):
        """Test when all providers fail."""
        with patch.dict(
            os.environ,
            {"KIMI_API_KEY": "test-key", "ZAI_API_KEY": "test-key"},
            clear=True,
        ):
            chain = LLMProviderChain()

            # Mock all providers to fail
            kimi_response = LLMResponse(
                success=False,
                provider="KIMI K2.5",
                error=ProviderError(
                    category=ErrorCategory.AUTH,
                    message="Auth failed",
                    should_fallback=True,
                ),
            )
            zai_response = LLMResponse(
                success=False,
                provider="GLM-5 (Z.ai)",
                error=ProviderError(
                    category=ErrorCategory.NETWORK,
                    message="Network error",
                    should_fallback=True,
                ),
            )

            chain._query_kimi = AsyncMock(return_value=kimi_response)
            chain._query_zai = AsyncMock(return_value=zai_response)
            chain._query_zhipu = AsyncMock(
                return_value=LLMResponse(
                    success=False,
                    provider="GLM-4.7 (Zhipu)",
                    error=ProviderError(
                        category=ErrorCategory.NOT_CONFIGURED,
                        message="No API key",
                        should_fallback=True,
                    ),
                )
            )

            result = await chain.query("Test prompt")

            assert result.success is False
            assert result.provider == "none"
            assert result.error is not None
            assert "All providers failed" in result.error.message

    @pytest.mark.asyncio
    async def test_skip_unavailable_providers(self):
        """Test that unavailable providers are skipped."""
        with patch.dict(
            os.environ,
            {"ZAI_API_KEY": "test-key"},  # Only Z.ai available
            clear=True,
        ):
            chain = LLMProviderChain()

            # Mock Z.ai to succeed
            zai_response = LLMResponse(
                success=True,
                content="Z.ai response",
                confidence_score=70.0,
                rationale="Z.ai rationale",
                provider="GLM-5 (Z.ai)",
            )
            chain._query_kimi = AsyncMock(side_effect=Exception("Should not be called"))
            chain._query_zai = AsyncMock(return_value=zai_response)

            result = await chain.query("Test prompt")

            assert result.success is True
            assert result.provider == "GLM-5 (Z.ai)"
            # KIMI should not be called since it's not available
            chain._query_kimi.assert_not_called()


class TestResponseParsing:
    """Test response parsing functionality."""

    def test_parse_confidence_with_confidence_line(self):
        """Test parsing confidence from response with CONFIDENCE line."""
        chain = LLMProviderChain()
        content = "CONFIDENCE: 85\nRATIONALE: Strong signal"

        confidence, rationale = chain._parse_confidence_response(content)

        assert confidence == 85.0
        assert rationale == "Strong signal"

    def test_parse_confidence_with_percentage(self):
        """Test parsing confidence with percentage sign."""
        chain = LLMProviderChain()
        content = "CONFIDENCE: 92%\nRATIONALE: Good trend"

        confidence, _ = chain._parse_confidence_response(content)

        assert confidence == 92.0

    def test_parse_confidence_with_decimal(self):
        """Test parsing confidence with decimal value."""
        chain = LLMProviderChain()
        content = "CONFIDENCE: 87.5\nRATIONALE: Moderate signal"

        confidence, _ = chain._parse_confidence_response(content)

        assert confidence == 87.5

    def test_parse_confidence_bounds_clamping(self):
        """Test that confidence is clamped to 0-100 range."""
        chain = LLMProviderChain()

        # Test upper bound
        content = "CONFIDENCE: 150"
        confidence, _ = chain._parse_confidence_response(content)
        assert confidence == 100.0

        # Test lower bound
        content = "CONFIDENCE: -20"
        confidence, _ = chain._parse_confidence_response(content)
        assert confidence == 0.0

    def test_parse_confidence_default_values(self):
        """Test default values when no confidence/rationale found."""
        chain = LLMProviderChain()
        content = "Some random response without structured data"

        confidence, rationale = chain._parse_confidence_response(content)

        assert confidence == 50.0  # Default neutral
        assert rationale == "No rationale provided"


class TestProviderStatus:
    """Test provider status reporting."""

    def test_get_provider_status_all_available(self):
        """Test status when all providers are available."""
        with patch.dict(
            os.environ,
            {
                "KIMI_API_KEY": "test-key",
                "ZAI_API_KEY": "test-key",
                "ZHIPU_API_KEY": "test-key",
                "MINIMAX_API_KEY": "test-key",
                "MINIMAX_ENABLED": "true",
            },
            clear=True,
        ):
            chain = LLMProviderChain()
            status = chain.get_provider_status()

            assert status["kimi"]["available"] is True
            assert status["zai"]["available"] is True
            assert status["zhipu"]["available"] is True
            # MiniMax disabled per PAPER-LLM-DIAG-001 - not in provider_order
            # Can still be checked via explicit provider list
            assert "minimax" not in chain.provider_order

    def test_get_provider_status_with_reasons(self):
        """Test status includes reasons for unavailable providers."""
        with patch.dict(os.environ, {}, clear=True):
            chain = LLMProviderChain()
            status = chain.get_provider_status()

            assert status["kimi"]["available"] is False
            assert status["kimi"]["reason"] is not None
            assert status["zai"]["available"] is False
            # MiniMax not in provider_order per PAPER-LLM-DIAG-001
            # So it won't be in status dict
            assert "minimax" not in status


class TestRetryLogic:
    """Test retry logic for retryable errors."""

    @pytest.mark.asyncio
    async def test_retry_on_rate_limit(self):
        """Test retry on rate limit errors."""
        with patch.dict(os.environ, {"KIMI_API_KEY": "test-key"}, clear=True):
            chain = LLMProviderChain(max_retries=3, retry_delay=0.1)

            # Mock to fail twice with rate limit, then succeed
            call_count = 0

            async def mock_query(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count < 3:
                    return LLMResponse(
                        success=False,
                        provider="KIMI K2.5",
                        error=ProviderError(
                            category=ErrorCategory.RATE_LIMIT,
                            message="Rate limited",
                            retryable=True,
                            should_fallback=True,
                        ),
                    )
                return LLMResponse(
                    success=True,
                    content="Success",
                    confidence_score=75.0,
                    rationale="Good",
                    provider="KIMI K2.5",
                )

            chain._query_kimi = mock_query

            result = await chain._query_with_retry("kimi", chain._query_kimi, "prompt")

            assert result.success is True
            assert call_count == 3  # 2 failures + 1 success

    @pytest.mark.asyncio
    async def test_no_retry_on_auth_error(self):
        """Test no retry on auth errors (non-retryable)."""
        with patch.dict(os.environ, {"KIMI_API_KEY": "test-key"}, clear=True):
            chain = LLMProviderChain(max_retries=3)

            async def mock_query(*args, **kwargs):
                return LLMResponse(
                    success=False,
                    provider="KIMI K2.5",
                    error=ProviderError(
                        category=ErrorCategory.AUTH,
                        message="Invalid key",
                        retryable=False,
                        should_fallback=True,
                    ),
                )

            chain._query_kimi = mock_query

            result = await chain._query_with_retry("kimi", chain._query_kimi, "prompt")

            assert result.success is False
            assert result.error.category == ErrorCategory.AUTH


class TestIntegrationWithPrompts:
    """Test integration with actual prompt structure."""

    @pytest.mark.asyncio
    async def test_query_with_system_prompt(self):
        """Test query with system prompt."""
        with patch.dict(os.environ, {"KIMI_API_KEY": "test-key"}, clear=True):
            chain = LLMProviderChain()

            mock_response = LLMResponse(
                success=True,
                content="Response",
                confidence_score=80.0,
                rationale="Rationale",
                provider="KIMI K2.5",
            )
            chain._query_kimi = AsyncMock(return_value=mock_response)

            result = await chain.query(
                prompt="Analyze this signal",
                system_prompt="You are a trading analyst",
            )

            assert result.success is True
            # Verify the mock was called with correct arguments
            chain._query_kimi.assert_called_once_with(
                "Analyze this signal", "You are a trading analyst"
            )


class TestKimiCompatProvider:
    """Test suite for kimi_compat provider."""

    def test_kimi_compat_config_exists(self):
        """Test that kimi_compat provider config exists."""
        assert "kimi_compat" in PROVIDER_CONFIGS
        config = PROVIDER_CONFIGS["kimi_compat"]
        assert config.name == "KIMI Compat (Adapter)"
        assert config.api_key_env == "KIMI_API_KEY"
        assert config.enabled_env == "KIMI_COMPAT_ENABLED"
        assert config.enabled_default is True  # ENABLED by default
        assert config.priority == 0  # Highest priority

    def test_kimi_compat_enabled_by_default(self):
        """Test that kimi_compat is enabled by default when key is present."""
        with patch.dict(
            os.environ,
            {"KIMI_API_KEY": "test-key"},  # Key present, compat enabled by default
            clear=True,
        ):
            chain = LLMProviderChain()
            # Mock adapter container as reachable
            chain._is_adapter_container_reachable = lambda: True
            available, reason = chain._is_provider_available("kimi_compat")

            assert available is True
            assert reason is None

    def test_kimi_compat_enabled_with_flag(self):
        """Test that kimi_compat is enabled when KIMI_COMPAT_ENABLED=true."""
        with patch.dict(
            os.environ,
            {"KIMI_API_KEY": "test-key", "KIMI_COMPAT_ENABLED": "true"},
            clear=True,
        ):
            chain = LLMProviderChain()
            # Mock adapter container as reachable
            chain._is_adapter_container_reachable = lambda: True
            available, reason = chain._is_provider_available("kimi_compat")

            assert available is True
            assert reason is None

    def test_kimi_compat_unavailable_without_key(self):
        """Test that kimi_compat is unavailable without API key."""
        with patch.dict(
            os.environ,
            {"KIMI_COMPAT_ENABLED": "true"},  # Enabled but no key
            clear=True,
        ):
            chain = LLMProviderChain()
            available, reason = chain._is_provider_available("kimi_compat")

            assert available is False
            assert "KIMI_API_KEY" in reason

    @pytest.mark.asyncio
    async def test_kimi_compat_first_in_default_order(self):
        """Test that kimi_compat is first in default provider order."""
        chain = LLMProviderChain()
        assert chain.provider_order[0] == "kimi_compat"

    @pytest.mark.asyncio
    async def test_fallback_from_kimi_compat_to_kimi(self):
        """Test fallback from kimi_compat to direct kimi when compat fails."""
        with patch.dict(
            os.environ,
            {
                "KIMI_API_KEY": "test-key",
                "KIMI_COMPAT_ENABLED": "true",
            },
            clear=True,
        ):
            chain = LLMProviderChain()
            # Mock adapter container as reachable
            chain._is_adapter_container_reachable = lambda: True

            # Mock kimi_compat to fail with network error (fallbackable)
            compat_response = LLMResponse(
                success=False,
                provider="KIMI Compat (Adapter)",
                error=ProviderError(
                    category=ErrorCategory.NETWORK,
                    message="Adapter unavailable",
                    should_fallback=True,
                ),
            )
            chain._query_kimi_compat = AsyncMock(return_value=compat_response)

            # Mock direct kimi to succeed
            kimi_response = LLMResponse(
                success=True,
                content="Direct KIMI response",
                confidence_score=75.0,
                rationale="Direct response",
                provider="KIMI K2.5",
            )
            chain._query_kimi = AsyncMock(return_value=kimi_response)

            result = await chain.query("Test prompt")

            assert result.success is True
            assert result.provider == "KIMI K2.5"
            chain._query_kimi_compat.assert_called_once()
            chain._query_kimi.assert_called_once()

    @pytest.mark.asyncio
    async def test_kimi_compat_skipped_when_disabled(self):
        """Test that kimi_compat is skipped when explicitly disabled."""
        with patch.dict(
            os.environ,
            {
                "KIMI_API_KEY": "test-key",
                "KIMI_COMPAT_ENABLED": "false",  # Explicitly disable compat
            },
            clear=True,
        ):
            chain = LLMProviderChain()

            # Mock kimi_compat - should not be called when disabled
            chain._query_kimi_compat = AsyncMock(
                side_effect=Exception("Should not be called")
            )

            # Mock direct kimi to succeed
            kimi_response = LLMResponse(
                success=True,
                content="Direct KIMI response",
                confidence_score=75.0,
                rationale="Direct response",
                provider="KIMI K2.5",
            )
            chain._query_kimi = AsyncMock(return_value=kimi_response)

            result = await chain.query("Test prompt")

            assert result.success is True
            assert result.provider == "KIMI K2.5"
            chain._query_kimi_compat.assert_not_called()
            chain._query_kimi.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
