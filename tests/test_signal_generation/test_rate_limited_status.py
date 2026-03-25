"""Tests for RATE_LIMITED signal status handling.

Verifies AC1-AC7 from ST-ICT-002:
- RATE_LIMITED exists in SignalStatus enum
- signal_generator sets RATE_LIMITED when rate-limited
- signal_emitter skips RATE_LIMITED signals gracefully
- scorer handles RATE_LIMITED signals gracefully
- Existing tests pass (no regression)
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from signal_generation.models import Signal, SignalDirection, SignalStatus
from signal_generation.signal_emitter import (
    DashboardEmitter,
    DiscordEmitter,
)


# ---------------------------------------------------------------------------
# AC1: RATE_LIMITED enum value
# ---------------------------------------------------------------------------
class TestRateLimitedEnum:
    """Verify RATE_LIMITED exists in SignalStatus enum (AC1)."""

    def test_rate_limited_exists(self):
        """RATE_LIMITED must be a member of SignalStatus."""
        assert hasattr(SignalStatus, "RATE_LIMITED")

    def test_rate_limited_value(self):
        """RATE_LIMITED value should be 'rate_limited'."""
        assert SignalStatus.RATE_LIMITED.value == "rate_limited"

    def test_rate_limited_is_not_actionable(self):
        """RATE_LIMITED should be distinct from ACTIONABLE."""
        assert SignalStatus.RATE_LIMITED != SignalStatus.ACTIONABLE

    def test_rate_limited_signal_is_not_actionable(self):
        """A RATE_LIMITED signal should not pass is_actionable check."""
        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=80.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.RATE_LIMITED,
            timeframe="1h",
        )
        assert signal.is_actionable is False


# ---------------------------------------------------------------------------
# AC2: signal_generator sets RATE_LIMITED when rate-limited
# ---------------------------------------------------------------------------
class TestGeneratorRateLimited:
    """Verify signal_generator sets RATE_LIMITED when rate-limited (AC2)."""

    @patch("signal_generation.signal_generator.SignalGenerator._get_scorer")
    @patch("signal_generation.signal_generator.SignalGenerator._get_freshness_checker")
    @patch("signal_generation.signal_generator.SignalGenerator._get_confidence_filter")
    def test_rate_limited_status_when_throttled(
        self, mock_get_filter, mock_get_checker, mock_get_scorer
    ):
        """When rate limit is hit, status should be RATE_LIMITED (not ACTIONABLE)."""
        from data_ingestion.timeframe_config import Timeframe
        from signal_generation.signal_generator import (
            SignalGenerationConfig,
            SignalGenerator,
        )

        config = SignalGenerationConfig(max_signals_per_token_per_hour=1)
        generator = SignalGenerator(config=config)

        # Fill rate limit
        generator._record_signal("BTC/USDT")

        # Setup mocks
        mock_checker = MagicMock()
        mock_checker.check_freshness.return_value = MagicMock(
            is_fresh=True, staleness_seconds=0
        )
        mock_get_checker.return_value = mock_checker

        mock_scorer = MagicMock()
        mock_scorer.calculate_score.return_value = MagicMock(
            score=85.0,
            direction=SignalDirection.LONG,
            confidence=0.85,
            contributing_factors=[],
            signal_breakdown={},
            metadata={},
            multiplier_applied=1.0,
            multiplier_rationale="",
        )
        mock_get_scorer.return_value = mock_scorer

        mock_filter = MagicMock()
        mock_filter.filter.return_value = MagicMock(is_actionable=True)
        mock_get_filter.return_value = mock_filter

        mock_ohlcv = [MagicMock(timestamp=1000, datetime_utc=datetime.now(UTC))]

        result = generator.generate_signal(
            token="BTC/USDT",
            timeframe=Timeframe.HOUR_1,
            ohlcv_data=mock_ohlcv,
        )

        assert result.status == SignalStatus.RATE_LIMITED
        assert result.metadata.get("rate_limited") is True


# ---------------------------------------------------------------------------
# AC3: ACTIONABLE still set when not rate-limited (no regression)
# ---------------------------------------------------------------------------
class TestGeneratorActionableNoRegression:
    """Verify ACTIONABLE is still set when not rate-limited (AC3)."""

    @patch("signal_generation.signal_generator.SignalGenerator._get_scorer")
    @patch("signal_generation.signal_generator.SignalGenerator._get_freshness_checker")
    @patch("signal_generation.signal_generator.SignalGenerator._get_confidence_filter")
    def test_actionable_status_when_not_rate_limited(
        self, mock_get_filter, mock_get_checker, mock_get_scorer
    ):
        """When rate limit is NOT hit, status should remain ACTIONABLE."""
        from data_ingestion.timeframe_config import Timeframe
        from signal_generation.signal_generator import (
            SignalGenerationConfig,
            SignalGenerator,
        )

        config = SignalGenerationConfig(max_signals_per_token_per_hour=10)
        generator = SignalGenerator(config=config)

        # Setup mocks
        mock_checker = MagicMock()
        mock_checker.check_freshness.return_value = MagicMock(
            is_fresh=True, staleness_seconds=0
        )
        mock_get_checker.return_value = mock_checker

        mock_scorer = MagicMock()
        mock_scorer.calculate_score.return_value = MagicMock(
            score=85.0,
            direction=SignalDirection.LONG,
            confidence=0.85,
            contributing_factors=[],
            signal_breakdown={},
            metadata={},
            multiplier_applied=1.0,
            multiplier_rationale="",
        )
        mock_get_scorer.return_value = mock_scorer

        mock_filter = MagicMock()
        mock_filter.filter.return_value = MagicMock(is_actionable=True)
        mock_get_filter.return_value = mock_filter

        mock_ohlcv = [MagicMock(timestamp=1000, datetime_utc=datetime.now(UTC))]

        result = generator.generate_signal(
            token="BTC/USDT",
            timeframe=Timeframe.HOUR_1,
            ohlcv_data=mock_ohlcv,
        )

        assert result.status == SignalStatus.ACTIONABLE
        assert result.metadata.get("rate_limited") is None


# ---------------------------------------------------------------------------
# AC4: signal_emitter handles RATE_LIMITED gracefully
# ---------------------------------------------------------------------------
class TestEmitterRateLimited:
    """Verify emitters skip RATE_LIMITED signals (AC4)."""

    def _make_rate_limited_signal(self):
        """Create a RATE_LIMITED signal for testing."""
        return Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=80.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.RATE_LIMITED,
            timeframe="1h",
        )

    def test_discord_emitter_skips_rate_limited(self):
        """DiscordEmitter should skip RATE_LIMITED signals."""
        emitter = DiscordEmitter(webhook_url="https://example.com/webhook")
        signal = self._make_rate_limited_signal()

        result = asyncio.get_event_loop().run_until_complete(emitter.emit(signal))

        assert result.success is False
        assert "rate-limited" in result.error.lower()

    def test_dashboard_emitter_skips_rate_limited(self):
        """DashboardEmitter should skip RATE_LIMITED signals."""
        emitter = DashboardEmitter()
        signal = self._make_rate_limited_signal()

        result = asyncio.get_event_loop().run_until_complete(emitter.emit(signal))

        assert result.success is False
        assert "rate-limited" in result.error.lower()

    def test_discord_emitter_emits_actionable(self):
        """DiscordEmitter should still emit ACTIONABLE signals (no regression)."""
        emitter = DiscordEmitter(webhook_url="https://example.com/webhook")
        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=80.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
        )

        # Mock aiohttp to avoid real HTTP call
        with patch("aiohttp.ClientSession") as mock_session:
            mock_post = AsyncMock()
            mock_post.status = 204
            mock_post.text = AsyncMock(return_value="")
            mock_post.__aenter__ = AsyncMock(return_value=mock_post)
            mock_post.__aexit__ = AsyncMock(return_value=False)
            mock_session.return_value.__aenter__ = AsyncMock(
                return_value=MagicMock(post=MagicMock(return_value=mock_post))
            )
            mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

            result = asyncio.get_event_loop().run_until_complete(emitter.emit(signal))

            # Should not be blocked by rate-limited check
            assert "rate-limited" not in (result.error or "").lower()


# ---------------------------------------------------------------------------
# AC5: scorer handles RATE_LIMITED gracefully
# ---------------------------------------------------------------------------
class TestScorerRateLimited:
    """Verify scorer handles RATE_LIMITED signals gracefully (AC5)."""

    def test_scorer_skips_rate_limited_signals(self):
        """Scorer should skip signals with rate_limited status."""
        from market_analysis.confluence.scorer import ConfluenceScorer
        from market_analysis.confluence.signal_aggregator import (
            AggregatedSignals,
            SignalDirection,
        )

        scorer = ConfluenceScorer()

        # Create a mock signal with rate_limited status
        mock_signal = MagicMock()
        mock_signal.status = SignalStatus.RATE_LIMITED

        mock_agg = MagicMock(spec=AggregatedSignals)
        mock_agg.signals = [mock_signal]

        result = scorer.calculate_score(mock_agg)

        # Should return neutral score, not crash
        assert result.score == 50.0
        assert result.direction == SignalDirection.NEUTRAL
        assert result.metadata.get("reason") == "all_signals_rate_limited"

    def test_scorer_handles_mixed_signals(self):
        """Scorer should process non-rate-limited signals when mixed."""
        from market_analysis.confluence.scorer import ConfluenceScorer
        from market_analysis.confluence.signal_aggregator import (
            AggregatedSignals,
        )

        scorer = ConfluenceScorer()

        # Create mixed signals: one rate-limited, one normal
        rate_limited_signal = MagicMock()
        rate_limited_signal.status = SignalStatus.RATE_LIMITED

        normal_signal = MagicMock()
        normal_signal.indicator_type = "rsi"
        normal_signal.timeframe = "1h"
        normal_signal.direction = MagicMock()
        normal_signal.weighted_score = 0.8
        normal_signal.strength = 0.9
        normal_signal.confidence = 0.8
        normal_signal.raw_value = 65.0
        # No status attribute (normal signal)

        mock_agg = MagicMock(spec=AggregatedSignals)
        mock_agg.signals = [rate_limited_signal, normal_signal]

        # Should not crash
        result = scorer.calculate_score(mock_agg)
        assert result.is_valid
