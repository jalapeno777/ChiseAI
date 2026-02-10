"""Tests for stop-loss integration with signal generation.

Tests the integration of stop-loss calculation into signal generation,
Discord alerts, and outcome tracking.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from portfolio_risk.stop_loss import (
    StopLossTracker,
    StopLossOutcome,
    SignalResult,
    TradeDirection,
)
from signal_generation.models import Signal, SignalDirection, SignalStatus
from signal_generation.signal_generator import (
    SignalGenerationConfig,
    SignalGenerator,
)


class MockOHLCV:
    """Mock OHLCV data point."""

    def __init__(
        self,
        open_price: float,
        high_price: float,
        low_price: float,
        close_price: float,
        volume: float = 1000.0,
        timestamp: int = 0,
    ):
        self.open_price = open_price
        self.high_price = high_price
        self.low_price = low_price
        self.close_price = close_price
        self.volume = volume
        self.timestamp = timestamp


class MockKeyLevel:
    """Mock KeyLevel for testing."""

    def __init__(
        self,
        price: float,
        level_type: str,
        strength: float = 50.0,
        confluence_score: float = 0.0,
        description: str = "",
    ):
        self.price = price
        self.level_type = level_type
        self.strength = strength
        self.confluence_score = confluence_score
        self.description = description


class MockKeyLevelsResult:
    """Mock KeyLevelsResult for testing."""

    def __init__(
        self,
        nearest_support: MockKeyLevel | None = None,
        nearest_resistance: MockKeyLevel | None = None,
    ):
        self.nearest_support = nearest_support
        self.nearest_resistance = nearest_resistance


class TestSignalWithStopLoss:
    """Tests for signals with stop-loss integration."""

    def create_mock_ohlcv(self, n: int = 30) -> list[MockOHLCV]:
        """Create mock OHLCV data."""
        import numpy as np

        np.random.seed(42)
        data = []
        price = 50000.0

        for i in range(n):
            change = np.random.randn() * 200
            close = price + change
            high = max(price, close) + abs(np.random.randn()) * 150
            low = min(price, close) - abs(np.random.randn()) * 100

            data.append(MockOHLCV(price, high, low, close, timestamp=i))
            price = close

        return data

    def test_signal_model_has_stop_loss_fields(self):
        """Test that Signal model has stop-loss fields."""
        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=80.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
            stop_loss=49000.0,
            stop_loss_method="technical_level",
            stop_loss_rationale="Support at 49000",
            trailing_stop=49500.0,
            trailing_stop_enabled=True,
            risk_reward_ratio=2.0,
        )

        assert signal.stop_loss == 49000.0
        assert signal.stop_loss_method == "technical_level"
        assert signal.stop_loss_rationale == "Support at 49000"
        assert signal.trailing_stop == 49500.0
        assert signal.trailing_stop_enabled is True
        assert signal.risk_reward_ratio == 2.0

    def test_signal_to_dict_includes_stop_loss(self):
        """Test that to_dict includes stop-loss information."""
        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=80.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
            stop_loss=49000.0,
            stop_loss_method="atr",
            stop_loss_rationale="ATR-based stop",
            risk_reward_ratio=2.5,
        )

        data = signal.to_dict()

        assert data["stop_loss"] == 49000.0
        assert data["stop_loss_method"] == "atr"
        assert data["stop_loss_rationale"] == "ATR-based stop"
        assert data["risk_reward_ratio"] == 2.5

    def test_signal_to_discord_message_includes_stop_loss(self):
        """Test that Discord message includes stop-loss."""
        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=80.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
            stop_loss=49000.0,
            stop_loss_method="technical_level",
            risk_reward_ratio=2.0,
        )

        message = signal.to_discord_message()

        assert "Stop-Loss" in message
        assert "$49,000.00" in message or "49000" in message
        assert "technical_level" in message
        assert "R:R" in message

    def test_signal_to_discord_message_with_trailing_stop(self):
        """Test Discord message with trailing stop."""
        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.90,
            base_score=85.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
            stop_loss=49000.0,
            stop_loss_method="atr",
            trailing_stop=49500.0,
            trailing_stop_enabled=True,
            risk_reward_ratio=2.0,
        )

        message = signal.to_discord_message()

        assert "Trailing Stop" in message
        assert "49500" in message or "$49,500.00" in message

    def test_signal_to_dashboard_payload_includes_stop_loss(self):
        """Test that dashboard payload includes stop-loss."""
        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=80.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
            stop_loss=49000.0,
            stop_loss_method="atr",
            stop_loss_rationale="ATR-based",
            trailing_stop=49500.0,
            trailing_stop_enabled=True,
            risk_reward_ratio=2.0,
        )

        payload = signal.to_dashboard_payload()

        assert payload["stop_loss"] == 49000.0
        assert payload["stop_loss_method"] == "atr"
        assert payload["stop_loss_rationale"] == "ATR-based"
        assert payload["trailing_stop"] == 49500.0
        assert payload["trailing_stop_enabled"] is True
        assert payload["risk_reward_ratio"] == 2.0


class TestSignalGeneratorStopLoss:
    """Tests for SignalGenerator stop-loss integration."""

    def test_config_has_stop_loss_options(self):
        """Test that config includes stop-loss options."""
        config = SignalGenerationConfig(
            enable_stop_loss_calculation=True,
            enable_trailing_stop=True,
            trailing_stop_threshold=0.85,
        )

        assert config.enable_stop_loss_calculation is True
        assert config.enable_trailing_stop is True
        assert config.trailing_stop_threshold == 0.85

    @patch("signal_generation.signal_generator.SignalGenerator._get_freshness_checker")
    @patch("signal_generation.signal_generator.SignalGenerator._get_scorer")
    def test_generate_signal_with_stop_loss(self, mock_get_scorer, mock_get_checker):
        """Test signal generation with stop-loss calculation."""
        # Mock freshness checker
        mock_checker = MagicMock()
        mock_checker.check_freshness.return_value = MagicMock(
            is_fresh=True,
            errors=[],
            data_age_seconds=0.0,
        )
        mock_get_checker.return_value = mock_checker

        # Mock confluence scorer
        mock_scorer = MagicMock()
        mock_score = MagicMock()
        mock_score.confidence = 0.85
        mock_score.score = 80.0
        mock_score.direction_str = "LONG"
        mock_score.contributing_factors = []
        mock_score.signal_breakdown = {}
        mock_score.metadata = {}
        mock_score.multiplier_applied = 1.0
        mock_score.multiplier_rationale = ""
        mock_scorer.calculate_score.return_value = mock_score
        mock_get_scorer.return_value = mock_scorer

        config = SignalGenerationConfig(
            enable_freshness_checks=True,
            enable_stop_loss_calculation=True,
            enable_caching=False,
        )
        generator = SignalGenerator(config=config)

        # Create mock OHLCV data
        import numpy as np

        np.random.seed(42)
        mock_ohlcv = []
        price = 50000.0
        for i in range(30):
            change = np.random.randn() * 200
            close = price + change
            high = max(price, close) + abs(np.random.randn()) * 150
            low = min(price, close) - abs(np.random.randn()) * 100
            mock_ohlcv.append(MockOHLCV(price, high, low, close, timestamp=i))
            price = close

        # Create mock key levels
        support = MockKeyLevel(
            price=49000.0,
            level_type="support",
            strength=80.0,
            description="Swing low",
        )
        key_levels = MockKeyLevelsResult(nearest_support=support)

        from data_ingestion.timeframe_config import Timeframe

        signal = generator.generate_signal(
            token="BTC/USDT",
            timeframe=Timeframe.HOUR_1,
            ohlcv_data=mock_ohlcv,
            aggregated_signals=MagicMock(),
            key_levels=key_levels,
            current_price=50000.0,
        )

        # Signal should have stop-loss calculated
        assert signal.stop_loss is not None
        assert signal.stop_loss_method is not None
        assert signal.stop_loss_rationale is not None
        assert signal.risk_reward_ratio >= 0

    def test_generate_signal_without_stop_loss_when_disabled(self):
        """Test that stop-loss is not calculated when disabled."""
        config = SignalGenerationConfig(enable_stop_loss_calculation=False)
        generator = SignalGenerator(config=config)

        # Create a mock signal manually
        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=80.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
        )

        # Stop-loss should be None when not calculated
        assert signal.stop_loss is None
        assert signal.stop_loss_method is None


class TestStopLossTracker:
    """Tests for StopLossTracker."""

    def test_tracker_initialization(self):
        """Test tracker initialization."""
        tracker = StopLossTracker()

        assert tracker._signals == {}
        assert tracker._stop_hits == []
        assert tracker._outcomes == []

    def test_record_signal(self):
        """Test recording a signal for tracking."""
        tracker = StopLossTracker()

        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=80.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
            stop_loss=49000.0,
            stop_loss_method="atr",
        )

        tracker.record_signal(signal, entry_price=50000.0, target_price=52000.0)

        assert signal.signal_id in tracker._signals
        assert tracker._signals[signal.signal_id]["entry_price"] == 50000.0
        assert tracker._signals[signal.signal_id]["target_price"] == 52000.0

    def test_record_stop_hit(self):
        """Test recording a stop-loss hit."""
        tracker = StopLossTracker()

        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=80.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
            stop_loss=49000.0,
            stop_loss_method="atr",
        )

        tracker.record_signal(signal, entry_price=50000.0)

        event = tracker.record_stop_hit(
            signal_id=signal.signal_id,
            hit_price=48950.0,
            outcome=StopLossOutcome.HIT,
            price_action="Sharp decline through support",
        )

        assert event is not None
        assert event.signal_id == signal.signal_id
        assert event.hit_price == 48950.0
        assert event.outcome == StopLossOutcome.HIT
        assert len(tracker._stop_hits) == 1

    def test_record_stop_hit_unknown_signal(self):
        """Test recording stop hit for unknown signal."""
        tracker = StopLossTracker()

        event = tracker.record_stop_hit(
            signal_id="unknown-id",
            hit_price=49000.0,
            outcome=StopLossOutcome.HIT,
        )

        assert event is None

    def test_record_outcome(self):
        """Test recording signal outcome."""
        tracker = StopLossTracker()

        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=80.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
            stop_loss=49000.0,
        )

        tracker.record_signal(signal, entry_price=50000.0, target_price=52000.0)

        outcome = tracker.record_outcome(
            signal_id=signal.signal_id,
            exit_price=52000.0,
            result=SignalResult.WIN,
            pnl_percent=0.04,
            duration_hours=4.5,
        )

        assert outcome is not None
        assert outcome.result == SignalResult.WIN
        assert outcome.pnl_percent == 0.04
        assert outcome.stop_hit is False

    def test_check_stop_hit_long(self):
        """Test checking stop hit for long position."""
        tracker = StopLossTracker()

        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=80.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
            stop_loss=49000.0,
        )

        tracker.record_signal(signal, entry_price=50000.0)

        # Price above stop - not hit
        assert tracker.check_stop_hit(signal.signal_id, current_price=49500.0) is False

        # Price at stop - hit
        assert tracker.check_stop_hit(signal.signal_id, current_price=49000.0) is True

        # Price below stop - hit
        assert tracker.check_stop_hit(signal.signal_id, current_price=48900.0) is True

    def test_check_stop_hit_short(self):
        """Test checking stop hit for short position."""
        tracker = StopLossTracker()

        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.SHORT,
            confidence=0.85,
            base_score=80.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
            stop_loss=51000.0,
        )

        tracker.record_signal(signal, entry_price=50000.0)

        # Price below stop - not hit
        assert tracker.check_stop_hit(signal.signal_id, current_price=50500.0) is False

        # Price at stop - hit
        assert tracker.check_stop_hit(signal.signal_id, current_price=51000.0) is True

        # Price above stop - hit
        assert tracker.check_stop_hit(signal.signal_id, current_price=51100.0) is True

    def test_get_correlation_stats(self):
        """Test getting correlation statistics."""
        tracker = StopLossTracker()

        # Create and record multiple signals with outcomes
        for i in range(5):
            signal = Signal(
                token="BTC/USDT",
                direction=SignalDirection.LONG,
                confidence=0.80 + (i * 0.03),
                base_score=80.0,
                timestamp=datetime.now(UTC),
                status=SignalStatus.ACTIONABLE,
                timeframe="1h",
                stop_loss=49000.0,
                stop_loss_method="atr" if i % 2 == 0 else "technical_level",
            )

            tracker.record_signal(signal, entry_price=50000.0)

            # Mix of wins and losses
            if i < 3:
                result = SignalResult.WIN
                pnl = 0.03
            else:
                result = SignalResult.LOSS
                pnl = -0.02

            tracker.record_outcome(
                signal_id=signal.signal_id,
                exit_price=51500.0 if result == SignalResult.WIN else 49000.0,
                result=result,
                pnl_percent=pnl,
                duration_hours=2.0 + i,
            )

        stats = tracker.get_correlation_stats()

        assert stats.total_signals == 5
        assert stats.stop_hits == 2  # 2 losses
        assert stats.wins_before_stop == 3
        assert "atr" in stats.correlation_by_method
        assert "technical_level" in stats.correlation_by_method

    def test_get_signal_history(self):
        """Test getting complete history for a signal."""
        tracker = StopLossTracker()

        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=80.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
            stop_loss=49000.0,
        )

        tracker.record_signal(signal, entry_price=50000.0, target_price=52000.0)
        tracker.record_stop_hit(
            signal_id=signal.signal_id,
            hit_price=48950.0,
            outcome=StopLossOutcome.HIT,
        )
        tracker.record_outcome(
            signal_id=signal.signal_id,
            exit_price=48950.0,
            result=SignalResult.LOSS,
            pnl_percent=-0.021,
            duration_hours=3.0,
        )

        history = tracker.get_signal_history(signal.signal_id)

        assert history is not None
        assert history["entry_price"] == 50000.0
        assert history["target_price"] == 52000.0
        assert history["stop_hit"] is not None
        assert history["outcome"] is not None
        assert history["outcome"]["result"] == "loss"

    def test_get_signal_history_unknown(self):
        """Test getting history for unknown signal."""
        tracker = StopLossTracker()

        history = tracker.get_signal_history("unknown-id")

        assert history is None

    def test_clear_old_records(self):
        """Test clearing old records."""
        tracker = StopLossTracker()

        # Add a signal
        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=80.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
            stop_loss=49000.0,
        )

        tracker.record_signal(signal, entry_price=50000.0)

        # Clear records older than 0 hours (should clear everything)
        cleared = tracker.clear_old_records(max_age_hours=0)

        assert cleared > 0
        assert signal.signal_id not in tracker._signals


class TestStopLossDiscordIntegration:
    """Tests for Discord alert integration with stop-loss."""

    def test_discord_message_formatting(self):
        """Test Discord message formatting with stop-loss."""
        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=80.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
            stop_loss=48500.0,
            stop_loss_method="technical_level",
            risk_reward_ratio=2.5,
        )

        message = signal.to_discord_message()

        # Verify all key elements are present
        assert "LONG Signal: BTC/USDT" in message
        assert "Confidence: **85.0%**" in message
        assert "Stop-Loss:" in message
        assert "technical_level" in message
        assert "R:R **2.50**" in message

    def test_discord_message_without_stop_loss(self):
        """Test Discord message when no stop-loss is set."""
        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=80.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
        )

        message = signal.to_discord_message()

        # Should not include stop-loss section
        assert "Stop-Loss" not in message
        assert "R:R" not in message

    def test_short_signal_discord_message(self):
        """Test Discord message for short signal."""
        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.SHORT,
            confidence=0.80,
            base_score=75.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
            stop_loss=52000.0,
            stop_loss_method="atr",
            risk_reward_ratio=1.8,
        )

        message = signal.to_discord_message()

        assert "🔴 **SHORT Signal: BTC/USDT**" in message
        assert "Stop-Loss:" in message
        assert "$52,000.00" in message or "52000" in message


class TestTrailingStop:
    """Tests for trailing stop functionality."""

    def test_trailing_stop_calculated_for_high_confidence(self):
        """Test that trailing stop is calculated for high confidence signals."""
        # This tests the config threshold
        config = SignalGenerationConfig(
            enable_trailing_stop=True,
            trailing_stop_threshold=0.85,
        )

        # Signal at threshold should get trailing stop
        assert config.trailing_stop_threshold == 0.85

    def test_signal_with_trailing_stop(self):
        """Test signal with trailing stop fields."""
        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.90,
            base_score=85.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
            stop_loss=49000.0,
            trailing_stop=49500.0,
            trailing_stop_enabled=True,
        )

        assert signal.trailing_stop == 49500.0
        assert signal.trailing_stop_enabled is True

        # Check Discord message
        message = signal.to_discord_message()
        assert "Trailing Stop" in message

        # Check dashboard payload
        payload = signal.to_dashboard_payload()
        assert payload["trailing_stop"] == 49500.0
        assert payload["trailing_stop_enabled"] is True
