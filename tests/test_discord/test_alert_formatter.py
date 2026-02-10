"""Tests for alert formatter.

Tests for ST-NS-009: Discord Alert Integration
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from discord_alerts.alert_formatter import AlertFormatter, AlertType
from signal_generation.models import Signal, SignalDirection, SignalStatus


class TestAlertType:
    """Test cases for AlertType enum."""

    def test_alert_type_values(self) -> None:
        """Test alert type enum values."""
        assert AlertType.ACTIONABLE.value == "actionable"
        assert AlertType.WATCHLIST.value == "watchlist"
        assert AlertType.INFO.value == "info"


class TestAlertFormatter:
    """Test cases for AlertFormatter."""

    @pytest.fixture
    def formatter(self) -> AlertFormatter:
        """Create alert formatter fixture."""
        return AlertFormatter()

    @pytest.fixture
    def actionable_signal(self) -> Signal:
        """Create actionable signal fixture (75%+ confidence)."""
        return Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=82.5,
            timestamp=datetime(2024, 1, 15, 12, 30, 0, tzinfo=UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
            signal_id="test-signal-123",
            generation_latency_ms=150.5,
            contributing_factors=[
                {"name": "RSI Oversold", "value": "32.5", "weight": 0.3},
                {"name": "MACD Bullish", "value": "Crossover", "weight": 0.25},
            ],
            signal_breakdown={
                "1h": {"score": 85.0, "direction": "LONG"},
                "4h": {"score": 80.0, "direction": "LONG"},
            },
        )

    @pytest.fixture
    def watchlist_signal(self) -> Signal:
        """Create watchlist signal fixture (40-74% confidence)."""
        return Signal(
            token="ETH/USDT",
            direction=SignalDirection.SHORT,
            confidence=0.55,
            base_score=52.0,
            timestamp=datetime(2024, 1, 15, 12, 30, 0, tzinfo=UTC),
            status=SignalStatus.LOGGED_ONLY,
            timeframe="4h",
            signal_id="test-signal-456",
            generation_latency_ms=200.0,
        )

    @pytest.fixture
    def low_confidence_signal(self) -> Signal:
        """Create low confidence signal fixture (<40% confidence)."""
        return Signal(
            token="SOL/USDT",
            direction=SignalDirection.NEUTRAL,
            confidence=0.25,
            base_score=30.0,
            timestamp=datetime(2024, 1, 15, 12, 30, 0, tzinfo=UTC),
            status=SignalStatus.LOGGED_ONLY,
            timeframe="15m",
            signal_id="test-signal-789",
            generation_latency_ms=100.0,
        )

    def test_format_signal_actionable(self, formatter, actionable_signal) -> None:
        """Test formatting actionable signal."""
        result = formatter.format_signal(actionable_signal)

        assert "content" in result
        assert "embeds" in result
        assert len(result["embeds"]) == 1

        # Check content has actionable indicator
        assert "ACTIONABLE" in result["content"]
        assert "BTC/USDT" in result["content"]

        # Check embed
        embed = result["embeds"][0]
        assert "LONG Signal: BTC/USDT" in embed["title"]
        assert embed["color"] == 0x00FF00  # Bright green for long high

    def test_format_signal_watchlist(self, formatter, watchlist_signal) -> None:
        """Test formatting watchlist signal."""
        result = formatter.format_signal(watchlist_signal)

        # Check content has watchlist indicator
        assert "Watchlist" in result["content"]
        assert "ETH/USDT" in result["content"]

        # Check embed
        embed = result["embeds"][0]
        assert "SHORT Signal: ETH/USDT" in embed["title"]
        assert embed["color"] == 0xFF6B6B  # Light red for short medium

    def test_format_signal_low_confidence(
        self, formatter, low_confidence_signal
    ) -> None:
        """Test formatting low confidence signal."""
        result = formatter.format_signal(low_confidence_signal)

        # Check content
        assert "SOL/USDT" in result["content"]

        # Check embed
        embed = result["embeds"][0]
        assert embed["color"] == 0x808080  # Gray for neutral

    def test_detect_alert_type_actionable(self, formatter, actionable_signal) -> None:
        """Test detecting actionable alert type."""
        alert_type = formatter._detect_alert_type(actionable_signal)

        assert alert_type == AlertType.ACTIONABLE

    def test_detect_alert_type_watchlist(self, formatter, watchlist_signal) -> None:
        """Test detecting watchlist alert type."""
        alert_type = formatter._detect_alert_type(watchlist_signal)

        assert alert_type == AlertType.WATCHLIST

    def test_detect_alert_type_info(self, formatter, low_confidence_signal) -> None:
        """Test detecting info alert type."""
        alert_type = formatter._detect_alert_type(low_confidence_signal)

        assert alert_type == AlertType.INFO

    def test_get_embed_color_long_high(self, formatter) -> None:
        """Test embed color for long high confidence."""
        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=80.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
        )

        color = formatter._get_embed_color(signal)

        assert color == 0x00FF00  # Bright green

    def test_get_embed_color_long_medium(self, formatter) -> None:
        """Test embed color for long medium confidence."""
        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.60,
            base_score=60.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.LOGGED_ONLY,
            timeframe="1h",
        )

        color = formatter._get_embed_color(signal)

        assert color == 0x90EE90  # Light green

    def test_get_embed_color_short_high(self, formatter) -> None:
        """Test embed color for short high confidence."""
        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.SHORT,
            confidence=0.85,
            base_score=80.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
        )

        color = formatter._get_embed_color(signal)

        assert color == 0xFF0000  # Bright red

    def test_get_embed_color_short_medium(self, formatter) -> None:
        """Test embed color for short medium confidence."""
        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.SHORT,
            confidence=0.60,
            base_score=60.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.LOGGED_ONLY,
            timeframe="1h",
        )

        color = formatter._get_embed_color(signal)

        assert color == 0xFF6B6B  # Light red

    def test_get_confidence_emoji_high(self, formatter) -> None:
        """Test confidence emoji for high confidence."""
        emoji = formatter._get_confidence_emoji(0.85)

        assert emoji == "🔥"

    def test_get_confidence_emoji_medium(self, formatter) -> None:
        """Test confidence emoji for medium confidence."""
        emoji = formatter._get_confidence_emoji(0.55)

        assert emoji == "⚡"

    def test_get_confidence_emoji_low(self, formatter) -> None:
        """Test confidence emoji for low confidence."""
        emoji = formatter._get_confidence_emoji(0.25)

        assert emoji == "💤"

    def test_format_contributing_factors(self, formatter) -> None:
        """Test formatting contributing factors."""
        factors = [
            {"name": "RSI", "value": "30", "weight": 0.3},
            {"name": "MACD", "value": "Bullish", "weight": 0.25},
        ]

        result = formatter._format_contributing_factors(factors)

        assert "RSI" in result
        assert "MACD" in result
        assert "30" in result
        assert "Bullish" in result

    def test_format_contributing_factors_empty(self, formatter) -> None:
        """Test formatting empty contributing factors."""
        result = formatter._format_contributing_factors([])

        assert result == ""

    def test_format_signal_breakdown(self, formatter) -> None:
        """Test formatting signal breakdown."""
        breakdown = {
            "1h": {"score": 85.0, "direction": "LONG"},
            "4h": {"score": 80.0, "direction": "LONG"},
        }

        result = formatter._format_signal_breakdown(breakdown)

        assert "1h" in result
        assert "4h" in result
        assert "85.0" in result
        assert "LONG" in result

    def test_format_signal_breakdown_empty(self, formatter) -> None:
        """Test formatting empty signal breakdown."""
        result = formatter._format_signal_breakdown({})

        assert result == ""

    def test_extract_key_levels_empty(self, formatter) -> None:
        """Test extracting key levels when none available."""
        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=80.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
        )

        result = formatter._extract_key_levels(signal)

        assert result == "N/A"

    def test_extract_key_levels_with_metadata(self, formatter) -> None:
        """Test extracting key levels from metadata."""
        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=80.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
            metadata={"entry_price": 45000.50},
        )

        result = formatter._extract_key_levels(signal)

        assert "Entry" in result
        assert "45,000.50" in result

    def test_format_simple_message(self, formatter) -> None:
        """Test formatting simple message."""
        result = formatter.format_simple_message(
            token="BTC/USDT",
            direction="LONG",
            confidence=0.85,
            timestamp=datetime(2024, 1, 15, 12, 30, 0, tzinfo=UTC),
        )

        assert "BTC/USDT" in result
        assert "LONG" in result
        assert "85.0%" in result
        assert "12:30:00" in result

    def test_format_simple_message_no_timestamp(self, formatter) -> None:
        """Test formatting simple message without timestamp."""
        result = formatter.format_simple_message(
            token="BTC/USDT",
            direction="SHORT",
            confidence=0.65,
        )

        assert "BTC/USDT" in result
        assert "SHORT" in result
        assert "65.0%" in result
        # Should not have timestamp
        assert "|" not in result

    def test_embed_contains_required_fields(self, formatter, actionable_signal) -> None:
        """Test embed contains all required fields per requirements."""
        result = formatter.format_signal(actionable_signal)
        embed = result["embeds"][0]

        # Required fields: token, direction, confidence, timestamp
        assert "title" in embed
        assert "description" in embed
        assert "color" in embed
        assert "footer" in embed
        assert "timestamp" in embed

        # Check content
        assert "BTC/USDT" in embed["title"]
        assert "85.0" in embed["description"] or "85" in embed["description"]
        assert "footer" in embed
        assert "timestamp" in embed

    def test_embed_footer_contains_signal_id(
        self, formatter, actionable_signal
    ) -> None:
        """Test embed footer contains signal ID."""
        result = formatter.format_signal(actionable_signal)
        embed = result["embeds"][0]

        assert "footer" in embed
        assert "text" in embed["footer"]
        # Signal ID should be truncated in footer
        assert (
            "test-sig" in embed["footer"]["text"]
            or "Signal ID" in embed["footer"]["text"]
        )
