"""Tests for signal list builder."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from dashboard.signal_list import (
    ActiveSignal,
    SignalListBuilder,
    SignalListResult,
)
from signal_generation.models import Signal, SignalDirection, SignalStatus


class TestActiveSignal:
    """Tests for ActiveSignal dataclass."""

    def test_active_signal_creation(self) -> None:
        """Test creating ActiveSignal."""
        signal = ActiveSignal(
            signal_id="test-123",
            token="BTC/USDT",
            direction="long",
            confidence=85.0,
            base_score=80.0,
            timeframe="1h",
            timestamp=datetime.now(UTC),
        )

        assert signal.signal_id == "test-123"
        assert signal.token == "BTC/USDT"
        assert signal.direction == "long"
        assert signal.confidence == 85.0

    def test_active_signal_normalization(self) -> None:
        """Test ActiveSignal value normalization."""
        signal = ActiveSignal(
            signal_id="test-123",
            token="BTC/USDT",
            direction="long",
            confidence=150.0,  # Should be clamped to 100
            base_score=-10.0,  # Should be clamped to 0
            timeframe="1h",
            timestamp=datetime.now(UTC),
        )

        assert signal.confidence == 100.0
        assert signal.base_score == 0.0

    def test_is_high_confidence(self) -> None:
        """Test high confidence check."""
        high = ActiveSignal(
            signal_id="test-1",
            token="BTC/USDT",
            direction="long",
            confidence=80.0,
            base_score=75.0,
            timeframe="1h",
            timestamp=datetime.now(UTC),
        )
        low = ActiveSignal(
            signal_id="test-2",
            token="ETH/USDT",
            direction="short",
            confidence=70.0,
            base_score=65.0,
            timeframe="1h",
            timestamp=datetime.now(UTC),
        )

        assert high.is_high_confidence is True
        assert low.is_high_confidence is False

    def test_emoji(self) -> None:
        """Test emoji property."""
        long_signal = ActiveSignal(
            signal_id="test-1",
            token="BTC/USDT",
            direction="long",
            confidence=80.0,
            base_score=75.0,
            timeframe="1h",
            timestamp=datetime.now(UTC),
        )
        short_signal = ActiveSignal(
            signal_id="test-2",
            token="ETH/USDT",
            direction="short",
            confidence=80.0,
            base_score=75.0,
            timeframe="1h",
            timestamp=datetime.now(UTC),
        )
        neutral_signal = ActiveSignal(
            signal_id="test-3",
            token="SOL/USDT",
            direction="neutral",
            confidence=50.0,
            base_score=50.0,
            timeframe="1h",
            timestamp=datetime.now(UTC),
        )

        assert long_signal.emoji == "🟢"
        assert short_signal.emoji == "🔴"
        assert neutral_signal.emoji == "⚪"

    def test_to_dict(self) -> None:
        """Test ActiveSignal serialization."""
        signal = ActiveSignal(
            signal_id="test-123",
            token="BTC/USDT",
            direction="long",
            confidence=85.0,
            base_score=80.0,
            timeframe="1h",
            timestamp=datetime.now(UTC),
            contributing_factors=[{"type": "rsi", "weight": 0.5}],
        )

        d = signal.to_dict()

        assert d["signal_id"] == "test-123"
        assert d["token"] == "BTC/USDT"
        assert d["confidence"] == 85.0
        assert d["is_high_confidence"] is True
        assert d["emoji"] == "🟢"


class TestSignalListResult:
    """Tests for SignalListResult dataclass."""

    def test_signal_list_result_creation(self) -> None:
        """Test creating SignalListResult."""
        signal = ActiveSignal(
            signal_id="test-123",
            token="BTC/USDT",
            direction="long",
            confidence=85.0,
            base_score=80.0,
            timeframe="1h",
            timestamp=datetime.now(UTC),
        )

        result = SignalListResult(
            timestamp=datetime.now(UTC),
            signals=[signal],
            high_confidence_count=1,
            long_count=1,
            short_count=0,
            tokens_covered=["BTC/USDT"],
        )

        assert len(result.signals) == 1
        assert result.high_confidence_count == 1
        assert result.tokens_covered == ["BTC/USDT"]

    def test_to_dict(self) -> None:
        """Test SignalListResult serialization."""
        signal = ActiveSignal(
            signal_id="test-123",
            token="BTC/USDT",
            direction="long",
            confidence=85.0,
            base_score=80.0,
            timeframe="1h",
            timestamp=datetime.now(UTC),
        )

        result = SignalListResult(
            timestamp=datetime.now(UTC),
            signals=[signal],
            high_confidence_count=1,
            long_count=1,
            short_count=0,
            tokens_covered=["BTC/USDT"],
        )

        d = result.to_dict()

        assert d["total_signals"] == 1
        assert d["high_confidence_count"] == 1
        assert d["long_count"] == 1
        assert d["short_count"] == 0
        assert len(d["signals"]) == 1


class TestSignalListBuilder:
    """Tests for SignalListBuilder."""

    def test_build_empty_signals(self) -> None:
        """Test building with empty signals."""
        builder = SignalListBuilder()

        result = builder.build([])

        assert len(result.signals) == 0
        assert result.high_confidence_count == 0

    def test_build_filters_non_actionable(self) -> None:
        """Test filtering non-actionable signals."""
        builder = SignalListBuilder()

        # Create actionable signal (>= 75%)
        actionable = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.80,
            base_score=80.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
        )

        # Create non-actionable signal (< 75%)
        non_actionable = Signal(
            token="ETH/USDT",
            direction=SignalDirection.SHORT,
            confidence=0.60,
            base_score=60.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.LOGGED_ONLY,
            timeframe="1h",
        )

        result = builder.build([actionable, non_actionable])

        # Should only include actionable signal
        assert len(result.signals) == 1
        assert result.signals[0].token == "BTC/USDT"

    def test_build_sorts_by_confidence(self) -> None:
        """Test sorting by confidence."""
        builder = SignalListBuilder()

        signals = [
            Signal(
                token=f"TOKEN{i}",
                direction=SignalDirection.LONG,
                confidence=0.75 + (i * 0.05),  # Different confidences
                base_score=75.0 + (i * 5),
                timestamp=datetime.now(UTC),
                status=SignalStatus.ACTIONABLE,
                timeframe="1h",
            )
            for i in range(5)
        ]

        result = builder.build(signals)

        # Should be sorted by confidence descending
        confidences = [s.confidence for s in result.signals]
        assert confidences == sorted(confidences, reverse=True)

    def test_build_respects_max_signals(self) -> None:
        """Test max_signals limit."""
        builder = SignalListBuilder()

        signals = [
            Signal(
                token=f"TOKEN{i}",
                direction=SignalDirection.LONG,
                confidence=0.80,
                base_score=80.0,
                timestamp=datetime.now(UTC),
                status=SignalStatus.ACTIONABLE,
                timeframe="1h",
            )
            for i in range(30)
        ]

        result = builder.build(signals, max_signals=10)

        assert len(result.signals) == 10

    def test_build_counts_statistics(self) -> None:
        """Test statistics counting."""
        builder = SignalListBuilder()

        signals = [
            Signal(
                token="BTC/USDT",
                direction=SignalDirection.LONG,
                confidence=0.80,
                base_score=80.0,
                timestamp=datetime.now(UTC),
                status=SignalStatus.ACTIONABLE,
                timeframe="1h",
            ),
            Signal(
                token="ETH/USDT",
                direction=SignalDirection.SHORT,
                confidence=0.85,
                base_score=85.0,
                timestamp=datetime.now(UTC),
                status=SignalStatus.ACTIONABLE,
                timeframe="1h",
            ),
            Signal(
                token="SOL/USDT",
                direction=SignalDirection.LONG,
                confidence=0.70,  # Below threshold
                base_score=70.0,
                timestamp=datetime.now(UTC),
                status=SignalStatus.LOGGED_ONLY,
                timeframe="1h",
            ),
        ]

        result = builder.build(signals)

        assert result.high_confidence_count == 2
        assert result.long_count == 1
        assert result.short_count == 1
        assert len(result.tokens_covered) == 2

    def test_build_from_tokens(self) -> None:
        """Test building from token-signal map."""
        builder = SignalListBuilder()

        token_map = {
            "BTC/USDT": [
                Signal(
                    token="BTC/USDT",
                    direction=SignalDirection.LONG,
                    confidence=0.80,
                    base_score=80.0,
                    timestamp=datetime.now(UTC),
                    status=SignalStatus.ACTIONABLE,
                    timeframe="1h",
                ),
            ],
            "ETH/USDT": [
                Signal(
                    token="ETH/USDT",
                    direction=SignalDirection.SHORT,
                    confidence=0.85,
                    base_score=85.0,
                    timestamp=datetime.now(UTC),
                    status=SignalStatus.ACTIONABLE,
                    timeframe="1h",
                ),
            ],
        }

        result = builder.build_from_tokens(token_map)

        assert len(result.signals) == 2

    def test_filter_by_token(self) -> None:
        """Test filtering by token."""
        builder = SignalListBuilder()

        signals = [
            ActiveSignal(
                signal_id="test-1",
                token="BTC/USDT",
                direction="long",
                confidence=80.0,
                base_score=75.0,
                timeframe="1h",
                timestamp=datetime.now(UTC),
            ),
            ActiveSignal(
                signal_id="test-2",
                token="ETH/USDT",
                direction="short",
                confidence=85.0,
                base_score=80.0,
                timeframe="1h",
                timestamp=datetime.now(UTC),
            ),
        ]

        result = SignalListResult(
            timestamp=datetime.now(UTC),
            signals=signals,
            high_confidence_count=2,
            long_count=1,
            short_count=1,
            tokens_covered=["BTC/USDT", "ETH/USDT"],
        )

        filtered = builder.filter_by_token(result, "BTC/USDT")

        assert len(filtered.signals) == 1
        assert filtered.signals[0].token == "BTC/USDT"
        assert filtered.tokens_covered == ["BTC/USDT"]

    def test_get_summary_text(self) -> None:
        """Test summary text generation."""
        builder = SignalListBuilder()

        signals = [
            ActiveSignal(
                signal_id="test-1",
                token="BTC/USDT",
                direction="long",
                confidence=80.0,
                base_score=75.0,
                timeframe="1h",
                timestamp=datetime.now(UTC),
            ),
            ActiveSignal(
                signal_id="test-2",
                token="ETH/USDT",
                direction="short",
                confidence=85.0,
                base_score=80.0,
                timeframe="1h",
                timestamp=datetime.now(UTC),
            ),
        ]

        result = SignalListResult(
            timestamp=datetime.now(UTC),
            signals=signals,
            high_confidence_count=2,
            long_count=1,
            short_count=1,
            tokens_covered=["BTC/USDT", "ETH/USDT"],
        )

        text = builder.get_summary_text(result)

        assert "Active Signals: 2" in text
        assert "High Confidence" in text
        assert "Long: 1" in text
        assert "Short: 1" in text

    def test_custom_threshold(self) -> None:
        """Test custom confidence threshold."""
        builder = SignalListBuilder(confidence_threshold=80.0)

        signals = [
            Signal(
                token="BTC/USDT",
                direction=SignalDirection.LONG,
                confidence=0.85,  # Above 80%
                base_score=85.0,
                timestamp=datetime.now(UTC),
                status=SignalStatus.ACTIONABLE,
                timeframe="1h",
            ),
            Signal(
                token="ETH/USDT",
                direction=SignalDirection.SHORT,
                confidence=0.78,  # Below 80%
                base_score=78.0,
                timestamp=datetime.now(UTC),
                status=SignalStatus.ACTIONABLE,
                timeframe="1h",
            ),
        ]

        result = builder.build(signals)

        # Should only include signal above 80%
        assert len(result.signals) == 1
        assert result.signals[0].token == "BTC/USDT"
