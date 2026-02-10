"""Tests for market summary calculator."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from dashboard.market_summary import (
    MarketSummary,
    MarketSummaryCalculator,
    TokenMetrics,
)


@dataclass
class MockOHLCVData:
    """Mock OHLCV data for testing."""

    timestamp: int
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: float


def create_mock_data(
    count: int,
    start_price: float = 50000.0,
    price_change: float = 0.0,
    volume: float = 1000.0,
) -> list[MockOHLCVData]:
    """Create mock OHLCV data."""
    data = []
    price = start_price

    for i in range(count):
        # Apply price change gradually
        price = start_price + (price_change * i / count)

        data.append(
            MockOHLCVData(
                timestamp=i * 3600,  # Hourly data
                open_price=price * 0.99,
                high_price=price * 1.02,
                low_price=price * 0.98,
                close_price=price,
                volume=volume,
            )
        )

    return data


class TestTokenMetrics:
    """Tests for TokenMetrics dataclass."""

    def test_token_metrics_creation(self) -> None:
        """Test creating TokenMetrics."""
        metrics = TokenMetrics(
            token="BTC/USDT",
            current_price=50000.0,
            price_change_24h=5.0,
            price_change_7d=10.0,
            volume_24h=1000000.0,
            volume_change=20.0,
            volatility_24h=2.5,
            price_range_24h=1000.0,
            high_24h=51000.0,
            low_24h=49000.0,
        )

        assert metrics.token == "BTC/USDT"
        assert metrics.current_price == 50000.0
        assert metrics.price_change_24h == 5.0

    def test_token_metrics_to_dict(self) -> None:
        """Test TokenMetrics serialization."""
        metrics = TokenMetrics(
            token="BTC/USDT",
            current_price=50000.0,
            price_change_24h=5.0,
            price_change_7d=10.0,
            volume_24h=1000000.0,
            volume_change=20.0,
            volatility_24h=2.5,
            price_range_24h=1000.0,
            high_24h=51000.0,
            low_24h=49000.0,
        )

        d = metrics.to_dict()

        assert d["token"] == "BTC/USDT"
        assert d["current_price"] == 50000.0
        assert d["price_change_24h"] == 5.0


class TestMarketSummaryCalculator:
    """Tests for MarketSummaryCalculator."""

    def test_calculate_summary_empty_data(self) -> None:
        """Test summary with empty data."""
        calculator = MarketSummaryCalculator()
        summary = calculator.calculate_summary({})

        assert summary.tokens == []
        assert summary.avg_price_change_24h == 0.0
        assert summary.total_volume_24h == 0.0

    def test_calculate_summary_single_token(self) -> None:
        """Test summary with single token."""
        calculator = MarketSummaryCalculator()

        # Create 48 hours of data with 5% increase (last 24 candles show ~5% change)
        data = create_mock_data(48, start_price=50000.0, price_change=2500.0)

        summary = calculator.calculate_summary({"BTC/USDT": data})

        assert len(summary.tokens) == 1
        assert summary.tokens[0].token == "BTC/USDT"
        # Price change should be positive (uptrend)
        assert summary.tokens[0].price_change_24h > 0

    def test_calculate_summary_multiple_tokens(self) -> None:
        """Test summary with multiple tokens."""
        calculator = MarketSummaryCalculator()

        btc_data = create_mock_data(48, start_price=50000.0, price_change=2500.0)
        eth_data = create_mock_data(48, start_price=3000.0, price_change=-150.0)

        summary = calculator.calculate_summary(
            {
                "BTC/USDT": btc_data,
                "ETH/USDT": eth_data,
            }
        )

        assert len(summary.tokens) == 2

        # Check top gainers/losers
        assert len(summary.top_gainers) > 0
        assert len(summary.top_losers) > 0

    def test_calculate_summary_sentiment_bullish(self) -> None:
        """Test bullish sentiment detection."""
        calculator = MarketSummaryCalculator()

        # Create data with strong upward movement
        data = create_mock_data(48, start_price=50000.0, price_change=5000.0)

        summary = calculator.calculate_summary({"BTC/USDT": data})

        assert summary.overall_sentiment == "bullish"

    def test_calculate_summary_sentiment_bearish(self) -> None:
        """Test bearish sentiment detection."""
        calculator = MarketSummaryCalculator()

        # Create data with strong downward movement
        data = create_mock_data(48, start_price=50000.0, price_change=-5000.0)

        summary = calculator.calculate_summary({"BTC/USDT": data})

        assert summary.overall_sentiment == "bearish"

    def test_calculate_atr(self) -> None:
        """Test ATR calculation."""
        calculator = MarketSummaryCalculator()

        # Create data with known volatility
        data = []
        for i in range(20):
            data.append(
                MockOHLCVData(
                    timestamp=i * 3600,
                    open_price=50000.0,
                    high_price=50500.0,
                    low_price=49500.0,
                    close_price=50000.0,
                    volume=1000.0,
                )
            )

        atr = calculator._calculate_atr(data)

        # ATR should be around 1000 (high - low)
        assert atr > 0

    def test_calculate_overnight_summary(self) -> None:
        """Test overnight summary calculation."""
        calculator = MarketSummaryCalculator()

        # Create 24 hours of data
        data = create_mock_data(24, start_price=50000.0, price_change=1000.0)

        overnight = calculator.calculate_overnight_summary(
            {"BTC/USDT": data},
            hours_ago=8,
        )

        assert overnight["period_hours"] == 8
        assert "avg_change_pct" in overnight
        assert "top_movers" in overnight
        assert overnight["token_count"] == 1


class TestMarketSummary:
    """Tests for MarketSummary dataclass."""

    def test_market_summary_to_dict(self) -> None:
        """Test MarketSummary serialization."""
        token = TokenMetrics(
            token="BTC/USDT",
            current_price=50000.0,
            price_change_24h=5.0,
            price_change_7d=10.0,
            volume_24h=1000000.0,
            volume_change=20.0,
            volatility_24h=2.5,
            price_range_24h=1000.0,
            high_24h=51000.0,
            low_24h=49000.0,
        )

        summary = MarketSummary(
            timestamp=datetime.now(UTC),
            tokens=[token],
            top_gainers=[token],
            overall_sentiment="bullish",
            avg_price_change_24h=5.0,
            total_volume_24h=1000000.0,
        )

        d = summary.to_dict()

        assert d["overall_sentiment"] == "bullish"
        assert d["avg_price_change_24h"] == 5.0
        assert d["token_count"] == 1
        assert len(d["top_gainers"]) == 1
