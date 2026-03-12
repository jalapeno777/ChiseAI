"""Tests for LLMConfidenceEnhancer with ProviderChain integration.

Tests the refactored LLMConfidenceEnhancer which now uses LLMProviderChain
instead of direct client calls, with:
- KIMI-first priority
- Automatic fallback chain
- Fallback reason capture
- Provider trace logging
"""

from __future__ import annotations

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from signal_generation.llm_enhancer import (
    PROVIDER_CHAIN_AVAILABLE,
    LLMCache,
    LLMConfidenceEnhancer,
    LLMEnhancementResult,
    SignalInput,
)
from signal_generation.models import Signal, SignalDirection


class TestLLMEnhancementResult:
    """Test LLMEnhancementResult dataclass with fallback_reason field."""

    def test_result_with_fallback_reason(self):
        """Test that fallback_reason field is properly handled."""
        result = LLMEnhancementResult(
            enhanced_confidence=85.0,
            base_confidence=82.0,
            rationale="Test rationale",
            market_context="Bullish",
            risk_assessment="Low",
            adjustment_recommendation="Increase",
            latency_ms=150.0,
            llm_provider="GLM-5 (Z.ai)",
            cached=False,
            fallback_reason="KIMI failed (auth error) → falling back to Z.ai",
        )

        assert result.fallback_reason is not None
        assert "KIMI" in result.fallback_reason
        assert "Z.ai" in result.fallback_reason

    def test_result_without_fallback_reason(self):
        """Test that fallback_reason can be None (no fallback occurred)."""
        result = LLMEnhancementResult(
            enhanced_confidence=85.0,
            base_confidence=82.0,
            rationale="Test rationale",
            market_context="Bullish",
            risk_assessment="Low",
            adjustment_recommendation="Increase",
            latency_ms=150.0,
            llm_provider="KIMI K2.5",
            cached=False,
            fallback_reason=None,
        )

        assert result.fallback_reason is None

    def test_result_to_dict_includes_fallback_reason(self):
        """Test that to_dict includes fallback_reason."""
        result = LLMEnhancementResult(
            enhanced_confidence=85.0,
            base_confidence=82.0,
            rationale="Test rationale",
            market_context="Bullish",
            risk_assessment="Low",
            adjustment_recommendation="Increase",
            latency_ms=150.0,
            llm_provider="GLM-5 (Z.ai)",
            cached=False,
            fallback_reason="KIMI unavailable",
        )

        result_dict = result.to_dict()
        assert "fallback_reason" in result_dict
        assert result_dict["fallback_reason"] == "KIMI unavailable"

    def test_result_to_dict_with_none_fallback_reason(self):
        """Test that to_dict handles None fallback_reason."""
        result = LLMEnhancementResult(
            enhanced_confidence=85.0,
            base_confidence=82.0,
            rationale="Test rationale",
            market_context="Bullish",
            risk_assessment="Low",
            adjustment_recommendation="Increase",
            latency_ms=150.0,
            llm_provider="KIMI K2.5",
            cached=False,
            fallback_reason=None,
        )

        result_dict = result.to_dict()
        assert "fallback_reason" in result_dict
        assert result_dict["fallback_reason"] is None


class TestLLMConfidenceEnhancerInitialization:
    """Test LLMConfidenceEnhancer initialization with ProviderChain."""

    def test_init_without_llm(self):
        """Test initialization with LLM disabled."""
        enhancer = LLMConfidenceEnhancer(use_llm=False)

        assert enhancer.use_llm is False
        assert enhancer.is_available() is False
        assert enhancer.get_provider() == "none"
        assert enhancer._provider_chain is None

    def test_init_with_env_var_disabled(self):
        """Test initialization when USE_LLM_ENHANCEMENT is false."""
        with patch.dict(os.environ, {"USE_LLM_ENHANCEMENT": "false"}):
            enhancer = LLMConfidenceEnhancer()

        assert enhancer.use_llm is False
        assert enhancer.is_available() is False

    def test_default_provider_order(self):
        """Test that default provider order is Adapter → KIMI → Z.ai."""
        enhancer = LLMConfidenceEnhancer(use_llm=False)

        expected_order = ["kimi_compat", "kimi", "zai"]
        assert enhancer.get_provider_order() == expected_order
        assert expected_order == enhancer.DEFAULT_PROVIDER_ORDER

    def test_custom_provider_order(self):
        """Test initialization with custom provider order."""
        custom_order = ["zhipu", "kimi"]
        enhancer = LLMConfidenceEnhancer(
            use_llm=False,  # Still disabled to avoid chain init
            provider_order=custom_order,
        )

        assert enhancer.get_provider_order() == custom_order


class TestProviderChainIntegration:
    """Test ProviderChain integration with fallback scenarios."""

    @pytest.fixture
    def mock_signal(self):
        """Create a mock signal for testing."""
        signal = MagicMock(spec=Signal)
        signal.token = "BTC/USDT"
        signal.direction = SignalDirection.LONG
        signal.confidence = 0.82
        signal.base_score = 85.0
        signal.timeframe = "1h"
        signal.contributing_factors = [{"name": "RSI bullish"}]
        return signal

    @pytest.fixture
    def mock_provider_chain(self):
        """Create a mock LLMProviderChain."""
        mock_chain = MagicMock()
        mock_chain.query = AsyncMock()
        return mock_chain

    @pytest.mark.skipif(
        not PROVIDER_CHAIN_AVAILABLE, reason="LLMProviderChain not available"
    )
    def test_kimi_first_priority_attempted(self, mock_signal, mock_provider_chain):
        """Test that KIMI is attempted first in the provider chain."""
        # Mock successful KIMI response
        mock_response = MagicMock()
        mock_response.success = True
        mock_response.content = "MARKET_CONTEXT: Bullish\nRISK_ASSESSMENT: Low\nCONFIDENCE_SCORE: 85\nRATIONALE: Strong signal"
        mock_response.confidence_score = 85.0
        mock_response.rationale = "Strong signal"
        mock_response.provider = "KIMI K2.5"
        mock_response.error = None
        mock_provider_chain.query.return_value = mock_response

        with patch(
            "signal_generation.llm_enhancer.LLMProviderChain",
            return_value=mock_provider_chain,
        ):
            enhancer = LLMConfidenceEnhancer(use_llm=True)
            enhancer._provider_chain = mock_provider_chain

            result = enhancer.enhance(mock_signal)

            # Verify KIMI was attempted first
            mock_provider_chain.query.assert_called_once()
            call_kwargs = mock_provider_chain.query.call_args[1]
            assert call_kwargs.get("providers") == ["kimi_compat", "kimi", "zai"]

            # Verify result shows KIMI as provider (no fallback)
            assert result.llm_provider == "KIMI K2.5"
            assert result.fallback_reason is None

    @pytest.mark.skipif(
        not PROVIDER_CHAIN_AVAILABLE, reason="LLMProviderChain not available"
    )
    def test_fallback_chain_kimi_to_zai(self, mock_signal, mock_provider_chain):
        """Test fallback from KIMI to Z.ai with reason captured."""
        # Mock response indicating KIMI failed, fallback to Z.ai
        mock_response = MagicMock()
        mock_response.success = True
        mock_response.content = "MARKET_CONTEXT: Bullish\nRISK_ASSESSMENT: Medium\nCONFIDENCE_SCORE: 82\nRATIONALE: Good signal"
        mock_response.confidence_score = 82.0
        mock_response.rationale = "Good signal"
        mock_response.provider = "GLM-5 (Z.ai)"

        # Create a mock ProviderError for fallback reason
        mock_error = MagicMock()
        mock_error.category = MagicMock()
        mock_error.category.name = "AUTH"
        mock_error.message = "Authentication failed"
        mock_response.error = mock_error

        mock_provider_chain.query.return_value = mock_response

        with patch(
            "signal_generation.llm_enhancer.LLMProviderChain",
            return_value=mock_provider_chain,
        ):
            enhancer = LLMConfidenceEnhancer(use_llm=True)
            enhancer._provider_chain = mock_provider_chain

            result = enhancer.enhance(mock_signal)

            # Verify result shows Z.ai as provider
            assert result.llm_provider == "GLM-5 (Z.ai)"
            # Verify fallback reason is captured
            assert result.fallback_reason is not None
            assert (
                "Fallback" in result.fallback_reason or "AUTH" in result.fallback_reason
            )

    @pytest.mark.skipif(
        not PROVIDER_CHAIN_AVAILABLE, reason="LLMProviderChain not available"
    )
    def test_fallback_chain_multiple_providers(self, mock_signal, mock_provider_chain):
        """Test full fallback chain: KIMI → Z.ai → Zhipu → MiniMax."""
        # Mock response from final fallback provider (MiniMax)
        mock_response = MagicMock()
        mock_response.success = True
        mock_response.content = "MARKET_CONTEXT: Neutral\nRISK_ASSESSMENT: Medium\nCONFIDENCE_SCORE: 75\nRATIONALE: Okay signal"
        mock_response.confidence_score = 75.0
        mock_response.rationale = "Okay signal"
        mock_response.provider = "MiniMax"
        mock_response.error = None
        mock_provider_chain.query.return_value = mock_response

        with patch(
            "signal_generation.llm_enhancer.LLMProviderChain",
            return_value=mock_provider_chain,
        ):
            enhancer = LLMConfidenceEnhancer(use_llm=True)
            enhancer._provider_chain = mock_provider_chain

            result = enhancer.enhance(mock_signal)

            # Verify MiniMax was the final provider
            assert result.llm_provider == "MiniMax"

    @pytest.mark.skipif(
        not PROVIDER_CHAIN_AVAILABLE, reason="LLMProviderChain not available"
    )
    def test_all_providers_failed(self, mock_signal, mock_provider_chain):
        """Test behavior when all providers fail."""
        # Mock failed response from all providers
        mock_response = MagicMock()
        mock_response.success = False
        mock_response.content = ""
        mock_response.confidence_score = 50.0
        mock_response.rationale = "All LLM providers failed"
        mock_response.provider = "none"

        mock_error = MagicMock()
        mock_error.category = MagicMock()
        mock_error.category.name = "UNKNOWN"
        mock_error.message = "All providers failed: KIMI: AUTH; Z.ai: NETWORK"
        mock_response.error = mock_error

        mock_provider_chain.query.return_value = mock_response

        with patch(
            "signal_generation.llm_enhancer.LLMProviderChain",
            return_value=mock_provider_chain,
        ):
            enhancer = LLMConfidenceEnhancer(use_llm=True)
            enhancer._provider_chain = mock_provider_chain

            result = enhancer.enhance(mock_signal)

            # Should return base confidence on failure
            assert result.enhanced_confidence == mock_signal.confidence * 100
            assert (
                "failed" in result.rationale.lower()
                or "error" in result.rationale.lower()
            )
            assert result.fallback_reason is not None


class TestProviderTraceLogging:
    """Test provider trace logging with fallback reasons."""

    @pytest.fixture
    def mock_signal(self):
        """Create a mock signal for testing."""
        signal = MagicMock(spec=Signal)
        signal.token = "BTC/USDT"
        signal.direction = SignalDirection.LONG
        signal.confidence = 0.82
        signal.base_score = 85.0
        signal.timeframe = "1h"
        signal.contributing_factors = []
        return signal

    @pytest.mark.skipif(
        not PROVIDER_CHAIN_AVAILABLE, reason="LLMProviderChain not available"
    )
    def test_fallback_reason_logged(self, mock_signal):
        """Test that fallback reason is logged in interaction log."""
        mock_chain = MagicMock()

        mock_response = MagicMock()
        mock_response.success = True
        mock_response.content = "CONFIDENCE_SCORE: 80"
        mock_response.confidence_score = 80.0
        mock_response.rationale = "Test"
        mock_response.provider = "GLM-5 (Z.ai)"

        mock_error = MagicMock()
        mock_error.category.name = "QUOTA"
        mock_error.message = "Quota exceeded"
        mock_response.error = mock_error

        mock_chain.query = AsyncMock(return_value=mock_response)

        with patch(
            "signal_generation.llm_enhancer.LLMProviderChain", return_value=mock_chain
        ):
            enhancer = LLMConfidenceEnhancer(use_llm=True)
            enhancer._provider_chain = mock_chain

            enhancer.enhance(mock_signal)

            # Check interaction log includes fallback reason
            interaction_log = enhancer.get_interaction_log()
            assert len(interaction_log) > 0
            last_entry = interaction_log[-1]
            assert "fallback_reason" in last_entry
            assert "Fallback" in last_entry["fallback_reason"]

    @pytest.mark.skipif(
        not PROVIDER_CHAIN_AVAILABLE, reason="LLMProviderChain not available"
    )
    def test_no_fallback_reason_when_primary_succeeds(self, mock_signal):
        """Test that no fallback reason when primary provider succeeds."""
        mock_chain = MagicMock()

        mock_response = MagicMock()
        mock_response.success = True
        mock_response.content = "CONFIDENCE_SCORE: 90"
        mock_response.confidence_score = 90.0
        mock_response.rationale = "Excellent signal"
        mock_response.provider = "KIMI K2.5"
        mock_response.error = None

        mock_chain.query = AsyncMock(return_value=mock_response)

        with patch(
            "signal_generation.llm_enhancer.LLMProviderChain", return_value=mock_chain
        ):
            enhancer = LLMConfidenceEnhancer(use_llm=True)
            enhancer._provider_chain = mock_chain

            result = enhancer.enhance(mock_signal)

            # Check no fallback reason in result
            assert result.fallback_reason is None

            # Check interaction log doesn't include fallback_reason or it's None
            interaction_log = enhancer.get_interaction_log()
            last_entry = interaction_log[-1]
            if "fallback_reason" in last_entry:
                assert last_entry["fallback_reason"] is None


class TestSignalInput:
    """Test SignalInput dataclass functionality."""

    def test_signal_input_creation(self):
        """Test creating SignalInput from signal data."""
        signal_input = SignalInput(
            token="BTC/USDT",
            direction="long",
            confidence=0.82,
            base_score=85.0,
            indicators={"rsi": 65.5, "macd": 0.5},
            timeframe="1h",
            contributing_factors=["RSI bullish", "MACD crossover"],
        )

        assert signal_input.token == "BTC/USDT"
        assert signal_input.direction == "long"
        assert signal_input.confidence == 0.82
        assert signal_input.base_score == 85.0

    def test_to_prompt_context(self):
        """Test conversion to prompt context string."""
        signal_input = SignalInput(
            token="ETH/USDT",
            direction="short",
            confidence=0.75,
            base_score=78.0,
            indicators={"rsi": 72.0},
            timeframe="4h",
            contributing_factors=["Overbought RSI"],
        )

        context = signal_input.to_prompt_context()

        assert "ETH/USDT" in context
        assert "SHORT" in context
        assert "75.0%" in context
        assert "78.0/100" in context
        assert "4h" in context
        assert "rsi: 72.0" in context
        assert "Overbought RSI" in context

    def test_to_cache_key_consistency(self):
        """Test that cache keys are consistent for similar inputs."""
        input1 = SignalInput(
            token="BTC/USDT",
            direction="long",
            confidence=0.82,
            base_score=85.0,
            timeframe="1h",
        )
        input2 = SignalInput(
            token="BTC/USDT",
            direction="long",
            confidence=0.82,
            base_score=85.0,
            timeframe="1h",
        )

        assert input1.to_cache_key() == input2.to_cache_key()

    def test_to_cache_key_differentiation(self):
        """Test that different inputs produce different cache keys."""
        input1 = SignalInput(
            token="BTC/USDT",
            direction="long",
            confidence=0.82,
            base_score=85.0,
        )
        input2 = SignalInput(
            token="ETH/USDT",
            direction="long",
            confidence=0.82,
            base_score=85.0,
        )

        assert input1.to_cache_key() != input2.to_cache_key()


class TestLLMCache:
    """Test LLM result caching functionality."""

    def test_cache_set_and_get(self):
        """Test basic cache set and get operations."""
        cache = LLMCache(max_size=10, ttl_seconds=3600)

        result = LLMEnhancementResult(
            enhanced_confidence=85.0,
            base_confidence=82.0,
            rationale="Test rationale",
            market_context="Bullish",
            risk_assessment="Low",
            adjustment_recommendation="Increase",
            latency_ms=150.0,
            llm_provider="zhipu",
        )

        cache.set("key1", result)
        cached = cache.get("key1")

        assert cached is not None
        assert cached.enhanced_confidence == 85.0
        assert cached.cached is True  # Should be marked as cached

    def test_cache_ttl_expiration(self):
        """Test that cache entries expire after TTL."""
        cache = LLMCache(max_size=10, ttl_seconds=0)  # Immediate expiration

        result = LLMEnhancementResult(
            enhanced_confidence=85.0,
            base_confidence=82.0,
            rationale="Test rationale",
            market_context="Bullish",
            risk_assessment="Low",
            adjustment_recommendation="Increase",
            latency_ms=150.0,
            llm_provider="zhipu",
        )

        cache.set("key1", result)
        cached = cache.get("key1")

        assert cached is None  # Should be expired


class TestLLMResponseParsing:
    """Test LLM response parsing functionality."""

    def test_parse_llm_response(self):
        """Test parsing of LLM response content."""
        enhancer = LLMConfidenceEnhancer(use_llm=False)

        content = """MARKET_CONTEXT: Bullish trend continuation expected
RISK_ASSESSMENT: Low volatility, strong support
CONFIDENCE_SCORE: 85
RATIONALE: Multiple indicators align with uptrend momentum"""

        parsed = enhancer._parse_llm_response(content)

        assert parsed["market_context"] == "Bullish trend continuation expected"
        assert parsed["risk_assessment"] == "Low volatility, strong support"
        assert parsed["confidence_score"] == 85.0
        assert parsed["rationale"] == "Multiple indicators align with uptrend momentum"

    def test_parse_llm_response_with_percentage(self):
        """Test parsing confidence score with percentage sign."""
        enhancer = LLMConfidenceEnhancer(use_llm=False)

        content = "CONFIDENCE_SCORE: 82.5%"

        parsed = enhancer._parse_llm_response(content)

        assert parsed["confidence_score"] == 82.5

    def test_parse_llm_response_bounds_checking(self):
        """Test that confidence score is bounded to 0-100."""
        enhancer = LLMConfidenceEnhancer(use_llm=False)

        content_high = "CONFIDENCE_SCORE: 150"
        content_zero = "CONFIDENCE_SCORE: 0"

        parsed_high = enhancer._parse_llm_response(content_high)
        parsed_zero = enhancer._parse_llm_response(content_zero)

        assert parsed_high["confidence_score"] == 100.0
        assert parsed_zero["confidence_score"] == 0.0


class TestBlendedConfidence:
    """Test blended confidence calculation."""

    def test_calculate_blended_confidence(self):
        """Test blended confidence calculation."""
        enhancer = LLMConfidenceEnhancer(use_llm=False)

        # Formula: final = (base * 0.7) + (llm * 0.3)
        # base=0.8, llm=80 -> (0.8*0.7) + (0.8*0.3) = 0.56 + 0.24 = 0.8
        result = enhancer.calculate_blended_confidence(0.8, 80.0)
        assert pytest.approx(result, 0.001) == 0.8

    def test_calculated_blended_bounds(self):
        """Test that blended confidence is bounded to 0-1."""
        enhancer = LLMConfidenceEnhancer(use_llm=False)

        # Test upper bound
        result_high = enhancer.calculate_blended_confidence(1.0, 150.0)
        assert result_high == 1.0

        # Test lower bound
        result_low = enhancer.calculate_blended_confidence(0.0, -20.0)
        assert result_low == 0.0


class TestFallbackReasonFormatting:
    """Test fallback reason formatting."""

    def test_format_fallback_reason_with_error(self):
        """Test formatting fallback reason from ProviderError."""
        enhancer = LLMConfidenceEnhancer(use_llm=False)

        mock_response = MagicMock()
        mock_error = MagicMock()
        mock_error.category.name = "AUTH"
        mock_error.message = "Authentication failed"
        mock_response.error = mock_error

        reason = enhancer._format_fallback_reason(mock_response)
        assert "AUTH" in reason
        assert "Authentication failed" in reason

    def test_extract_fallback_reason_with_error(self):
        """Test extracting fallback reason when response has error."""
        enhancer = LLMConfidenceEnhancer(use_llm=False)

        mock_response = MagicMock()
        mock_error = MagicMock()
        mock_error.category.name = "QUOTA"
        mock_error.message = "API quota exceeded"
        mock_response.error = mock_error

        reason = enhancer._extract_fallback_reason(mock_response)
        assert reason is not None
        assert "Fallback" in reason

    def test_extract_fallback_reason_without_error(self):
        """Test extracting fallback reason when no error (no fallback)."""
        enhancer = LLMConfidenceEnhancer(use_llm=False)

        mock_response = MagicMock()
        mock_response.error = None

        reason = enhancer._extract_fallback_reason(mock_response)
        assert reason is None
