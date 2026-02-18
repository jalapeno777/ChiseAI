"""Tests for provider fallback behavior and priority.

This module tests the LLM provider fallback chain in LLMConfidenceEnhancer:
KIMI → GLM-5 (Z.ai) → GLM-4.7 (Zhipu) → MiniMax (disabled by default)

CH-LLM-KIMI-001: KIMI Primary LLM Provider Tests
"""

import os
import sys
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from scripts.live_pipeline_proof import (
    AnalysisResult,
    LLMConfidenceEnhancer,
    LLMEnhancement,
    MarketData,
    SignalDirection,
)


class TestProviderFallbackChain:
    """Test suite for LLM provider fallback chain behavior."""

    @pytest.fixture
    def sample_market_data(self):
        """Create sample market data for testing."""
        return MarketData(
            symbol="BTCUSDT",
            price=50000.0,
            volume_24h=1000000000.0,
            price_change_24h=1000.0,
            price_change_percent_24h=2.0,
            high_24h=51000.0,
            low_24h=49000.0,
            timestamp=datetime.now(UTC),
            latency_ms=50.0,
        )

    @pytest.fixture
    def sample_analysis(self):
        """Create sample analysis result for testing."""
        return AnalysisResult(
            indicators={"rsi": 55.0, "macd": 1.0, "macd_signal": "bullish"},
            confluence_score=65.0,
            direction=SignalDirection.LONG,
            rationale="Bullish momentum detected",
        )

    @pytest.fixture
    def sample_llm_enhancement(self):
        """Create sample LLM enhancement for testing."""
        return LLMEnhancement(
            provider="test",
            base_confidence=65.0,
            llm_confidence=75.0,
            final_confidence=68.0,
            rationale="Test rationale",
            latency_ms=100.0,
        )

    @pytest.mark.asyncio
    async def test_kimi_is_primary_provider(
        self, sample_market_data, sample_analysis, sample_llm_enhancement
    ):
        """Test that KIMI is tried first when KIMI_API_KEY is set.

        When KIMI_API_KEY is set and KIMI_ENABLED is true (default),
        KIMI should be the first provider attempted.
        """
        with patch.dict(
            "os.environ",
            {"KIMI_API_KEY": "test-kimi-key", "KIMI_ENABLED": "true"},
            clear=True,
        ):
            enhancer = LLMConfidenceEnhancer()

            # Mock KIMI to return success
            mock_result = LLMEnhancement(
                provider="KIMI K2.5",
                base_confidence=65.0,
                llm_confidence=75.0,
                final_confidence=68.0,
                rationale="KIMI analysis",
                latency_ms=100.0,
            )
            enhancer._query_kimi = AsyncMock(return_value=mock_result)

            result = await enhancer.enhance(sample_analysis, sample_market_data)

            assert result.provider == "KIMI K2.5"
            enhancer._query_kimi.assert_called_once()

    @pytest.mark.asyncio
    async def test_fallback_to_zai_when_kimi_fails(
        self, sample_market_data, sample_analysis
    ):
        """Test fallback to Z.ai (GLM-5) when KIMI fails.

        When KIMI_API_KEY is set but KIMI fails, and ZAI_API_KEY is set,
        should fall back to GLM-5 via Z.ai.
        """
        with patch.dict(
            "os.environ",
            {
                "KIMI_API_KEY": "test-kimi-key",
                "KIMI_ENABLED": "true",
                "ZAI_API_KEY": "test-zai-key",
            },
            clear=True,
        ):
            enhancer = LLMConfidenceEnhancer()

            # Mock KIMI to fail
            enhancer._query_kimi = AsyncMock(side_effect=RuntimeError("KIMI failed"))

            # Mock Z.ai to succeed
            mock_result = LLMEnhancement(
                provider="GLM-5 (Z.ai)",
                base_confidence=65.0,
                llm_confidence=70.0,
                final_confidence=66.5,
                rationale="Z.ai analysis",
                latency_ms=150.0,
            )
            enhancer._query_zai = AsyncMock(return_value=mock_result)

            result = await enhancer.enhance(sample_analysis, sample_market_data)

            assert result.provider == "GLM-5 (Z.ai)"
            enhancer._query_kimi.assert_called_once()
            enhancer._query_zai.assert_called_once()

    @pytest.mark.asyncio
    async def test_fallback_to_zhipu_when_zai_fails(
        self, sample_market_data, sample_analysis
    ):
        """Test fallback to Zhipu (GLM-4.7) when both KIMI and Z.ai fail.

        When KIMI fails and Z.ai fails, should try Zhipu GLM-4.7.
        """
        with patch.dict(
            "os.environ",
            {
                "KIMI_API_KEY": "test-kimi-key",
                "KIMI_ENABLED": "true",
                "ZAI_API_KEY": "test-zai-key",
            },
            clear=True,
        ):
            enhancer = LLMConfidenceEnhancer()

            # Mock KIMI to fail
            enhancer._query_kimi = AsyncMock(side_effect=RuntimeError("KIMI failed"))

            # Mock Z.ai to fail
            enhancer._query_zai = AsyncMock(side_effect=RuntimeError("Z.ai failed"))

            # Mock Zhipu to succeed
            mock_result = LLMEnhancement(
                provider="GLM-4.7 (Zhipu)",
                base_confidence=65.0,
                llm_confidence=68.0,
                final_confidence=65.9,
                rationale="Zhipu analysis",
                latency_ms=200.0,
            )
            enhancer._query_zhipu = AsyncMock(return_value=mock_result)

            result = await enhancer.enhance(sample_analysis, sample_market_data)

            assert result.provider == "GLM-4.7 (Zhipu)"
            enhancer._query_kimi.assert_called_once()
            enhancer._query_zai.assert_called_once()
            enhancer._query_zhipu.assert_called_once()

    @pytest.mark.asyncio
    async def test_minimax_disabled_by_default(
        self, sample_market_data, sample_analysis
    ):
        """Test that MiniMax is disabled by default.

        When all previous providers fail and MINIMAX_API_KEY is set,
        but MINIMAX_ENABLED is not set (defaults to false),
        should NOT try MiniMax and return fallback.
        """
        with patch.dict(
            "os.environ",
            {
                "KIMI_API_KEY": "test-kimi-key",
                "KIMI_ENABLED": "true",
                "ZAI_API_KEY": "test-zai-key",
                "MINIMAX_API_KEY": "test-minimax-key",
                # MINIMAX_ENABLED not set - defaults to false
            },
            clear=True,
        ):
            enhancer = LLMConfidenceEnhancer()

            # Mock all providers to fail
            enhancer._query_kimi = AsyncMock(side_effect=RuntimeError("KIMI failed"))
            enhancer._query_zai = AsyncMock(side_effect=RuntimeError("Z.ai failed"))
            enhancer._query_zhipu = AsyncMock(side_effect=RuntimeError("Zhipu failed"))
            enhancer._query_minimax = AsyncMock(
                side_effect=RuntimeError("Should not be called")
            )

            result = await enhancer.enhance(sample_analysis, sample_market_data)

            assert result.provider == "none (fallback)"
            assert result.final_confidence == sample_analysis.confluence_score
            enhancer._query_kimi.assert_called_once()
            enhancer._query_zai.assert_called_once()
            enhancer._query_zhipu.assert_called_once()
            # MiniMax should NOT be called when disabled
            enhancer._query_minimax.assert_not_called()

    @pytest.mark.asyncio
    async def test_minimax_enabled_with_explicit_flag(
        self, sample_market_data, sample_analysis
    ):
        """Test that MiniMax is tried when explicitly enabled.

        When all previous providers fail and MINIMAX_API_KEY is set
        with MINIMAX_ENABLED=true, should try MiniMax.
        """
        with patch.dict(
            "os.environ",
            {
                "KIMI_API_KEY": "test-kimi-key",
                "KIMI_ENABLED": "true",
                "ZAI_API_KEY": "test-zai-key",
                "MINIMAX_API_KEY": "test-minimax-key",
                "MINIMAX_ENABLED": "true",
            },
            clear=True,
        ):
            enhancer = LLMConfidenceEnhancer()

            # Mock KIMI, Z.ai, Zhipu to fail
            enhancer._query_kimi = AsyncMock(side_effect=RuntimeError("KIMI failed"))
            enhancer._query_zai = AsyncMock(side_effect=RuntimeError("Z.ai failed"))
            enhancer._query_zhipu = AsyncMock(side_effect=RuntimeError("Zhipu failed"))

            # Mock MiniMax to succeed
            mock_result = LLMEnhancement(
                provider="MiniMax",
                base_confidence=65.0,
                llm_confidence=72.0,
                final_confidence=67.1,
                rationale="MiniMax analysis",
                latency_ms=180.0,
            )
            enhancer._query_minimax = AsyncMock(return_value=mock_result)

            result = await enhancer.enhance(sample_analysis, sample_market_data)

            assert result.provider == "MiniMax"
            enhancer._query_kimi.assert_called_once()
            enhancer._query_zai.assert_called_once()
            enhancer._query_zhipu.assert_called_once()
            enhancer._query_minimax.assert_called_once()

    @pytest.mark.asyncio
    async def test_kimi_disabled_when_kimi_enabled_false(
        self, sample_market_data, sample_analysis
    ):
        """Test that KIMI is skipped when KIMI_ENABLED=false.

        When KIMI_API_KEY is set but KIMI_ENABLED=false,
        should skip KIMI and try Z.ai first.
        """
        with patch.dict(
            "os.environ",
            {
                "KIMI_API_KEY": "test-kimi-key",
                "KIMI_ENABLED": "false",
                "ZAI_API_KEY": "test-zai-key",
            },
            clear=True,
        ):
            enhancer = LLMConfidenceEnhancer()

            # Mock KIMI - should not be called
            enhancer._query_kimi = AsyncMock(
                side_effect=RuntimeError("Should not be called")
            )

            # Mock Z.ai to succeed
            mock_result = LLMEnhancement(
                provider="GLM-5 (Z.ai)",
                base_confidence=65.0,
                llm_confidence=70.0,
                final_confidence=66.5,
                rationale="Z.ai analysis",
                latency_ms=150.0,
            )
            enhancer._query_zai = AsyncMock(return_value=mock_result)

            result = await enhancer.enhance(sample_analysis, sample_market_data)

            assert result.provider == "GLM-5 (Z.ai)"
            # KIMI should NOT be called when disabled
            enhancer._query_kimi.assert_not_called()
            enhancer._query_zai.assert_called_once()

    @pytest.mark.asyncio
    async def test_complete_fallback_chain_order(
        self, sample_market_data, sample_analysis
    ):
        """Test that all providers are tried in the correct order.

        Set up scenario where all providers fail except the last one (MiniMax),
        and verify the chain order: KIMI → Z.ai → Zhipu → MiniMax.
        """
        with patch.dict(
            "os.environ",
            {
                "KIMI_API_KEY": "test-kimi-key",
                "KIMI_ENABLED": "true",
                "ZAI_API_KEY": "test-zai-key",
                "MINIMAX_API_KEY": "test-minimax-key",
                "MINIMAX_ENABLED": "true",
            },
            clear=True,
        ):
            enhancer = LLMConfidenceEnhancer()

            # Track call order
            call_order = []

            async def mock_kimi(*args, **kwargs):
                call_order.append("KIMI")
                raise RuntimeError("KIMI failed")

            async def mock_zai(*args, **kwargs):
                call_order.append("Z.ai")
                raise RuntimeError("Z.ai failed")

            async def mock_zhipu(*args, **kwargs):
                call_order.append("Zhipu")
                raise RuntimeError("Zhipu failed")

            async def mock_minimax(*args, **kwargs):
                call_order.append("MiniMax")
                return LLMEnhancement(
                    provider="MiniMax",
                    base_confidence=65.0,
                    llm_confidence=72.0,
                    final_confidence=67.1,
                    rationale="MiniMax analysis",
                    latency_ms=180.0,
                )

            enhancer._query_kimi = mock_kimi
            enhancer._query_zai = mock_zai
            enhancer._query_zhipu = mock_zhipu
            enhancer._query_minimax = mock_minimax

            result = await enhancer.enhance(sample_analysis, sample_market_data)

            assert result.provider == "MiniMax"
            assert call_order == ["KIMI", "Z.ai", "Zhipu", "MiniMax"]

    @pytest.mark.asyncio
    async def test_no_providers_configured(self, sample_market_data, sample_analysis):
        """Test behavior when no API keys are set.

        When no API keys are configured, should try Zhipu (no key check),
        then return fallback when all fail.
        """
        with patch.dict("os.environ", {}, clear=True):
            enhancer = LLMConfidenceEnhancer()

            # Mock providers that require API keys - should not be called
            enhancer._query_kimi = AsyncMock(
                side_effect=RuntimeError("Should not be called")
            )
            enhancer._query_zai = AsyncMock(
                side_effect=RuntimeError("Should not be called")
            )
            enhancer._query_minimax = AsyncMock(
                side_effect=RuntimeError("Should not be called")
            )

            # Mock Zhipu to fail (Zhipu is always tried - no API key check in enhance)
            enhancer._query_zhipu = AsyncMock(side_effect=RuntimeError("Zhipu failed"))

            result = await enhancer.enhance(sample_analysis, sample_market_data)

            assert result.provider == "none (fallback)"
            assert result.final_confidence == sample_analysis.confluence_score
            assert result.llm_confidence == sample_analysis.confluence_score
            # KIMI and Z.ai should NOT be called (no API keys)
            enhancer._query_kimi.assert_not_called()
            enhancer._query_zai.assert_not_called()
            # Zhipu IS called (no API key check, always tried)
            enhancer._query_zhipu.assert_called_once()
            # MiniMax should NOT be called (no API key / disabled)
            enhancer._query_minimax.assert_not_called()
