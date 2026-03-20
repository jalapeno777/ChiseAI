"""Tests for open interest aggregation."""

from datetime import UTC, datetime, timedelta

from exchange_data.binance.open_interest import (
    OIAggregation,
    OpenInterestAggregator,
    OpenInterestData,
)


class TestOpenInterestData:
    """Test OpenInterestData dataclass."""

    def test_creation(self) -> None:
        """Test creating open interest data."""
        oi = OpenInterestData(
            symbol="BTCUSDT",
            timestamp=datetime.now(UTC),
            open_interest=1000000.0,
            open_interest_usd=50000000000.0,
            price=50000.0,
        )

        assert oi.symbol == "BTCUSDT"
        assert oi.open_interest == 1000000.0
        assert oi.open_interest_usd == 50000000000.0

    def test_to_dict(self) -> None:
        """Test dictionary conversion."""
        timestamp = datetime(2024, 1, 1, 12, 0, 0)
        oi = OpenInterestData(
            symbol="BTCUSDT",
            timestamp=timestamp,
            open_interest=1000000.0,
            open_interest_usd=50000000000.0,
            price=50000.0,
        )

        data = oi.to_dict()
        assert data["symbol"] == "BTCUSDT"
        assert data["open_interest"] == 1000000.0
        assert data["timestamp"] == timestamp.isoformat()


class TestOIAggregation:
    """Test OIAggregation dataclass."""

    def test_creation(self) -> None:
        """Test creating aggregation."""
        agg = OIAggregation(
            symbol="BTCUSDT",
            window_start=datetime.now(UTC),
            window_end=datetime.now(UTC),
            avg_oi=1000000.0,
            min_oi=900000.0,
            max_oi=1100000.0,
            change_pct=5.0,
            data_points=10,
        )

        assert agg.symbol == "BTCUSDT"
        assert agg.avg_oi == 1000000.0
        assert agg.change_pct == 5.0

    def test_to_dict(self) -> None:
        """Test dictionary conversion."""
        start = datetime(2024, 1, 1, 12, 0, 0)
        end = datetime(2024, 1, 1, 13, 0, 0)
        agg = OIAggregation(
            symbol="BTCUSDT",
            window_start=start,
            window_end=end,
            avg_oi=1000000.0,
            min_oi=900000.0,
            max_oi=1100000.0,
            change_pct=5.0,
            data_points=10,
        )

        data = agg.to_dict()
        assert data["symbol"] == "BTCUSDT"
        assert data["avg_oi"] == 1000000.0
        assert data["window_start"] == start.isoformat()


class TestOpenInterestAggregator:
    """Test OpenInterestAggregator functionality."""

    def test_add(self) -> None:
        """Test adding data points."""
        aggregator = OpenInterestAggregator()
        oi = OpenInterestData(
            symbol="BTCUSDT",
            timestamp=datetime.now(UTC),
            open_interest=1000000.0,
        )

        aggregator.add(oi)

        assert "BTCUSDT" in aggregator.get_all_symbols()

    def test_get_aggregation(self) -> None:
        """Test getting aggregation."""
        aggregator = OpenInterestAggregator(window_minutes=60)
        now = datetime.now(UTC)

        # Add data points
        for i in range(5):
            oi = OpenInterestData(
                symbol="BTCUSDT",
                timestamp=now - timedelta(minutes=i * 10),
                open_interest=1000000.0 + i * 10000,
            )
            aggregator.add(oi)

        agg = aggregator.get_aggregation("BTCUSDT")

        assert agg is not None
        assert agg.symbol == "BTCUSDT"
        assert agg.data_points == 5
        assert agg.min_oi == 1000000.0
        assert agg.max_oi == 1040000.0

    def test_get_aggregation_insufficient_data(self) -> None:
        """Test aggregation with insufficient data."""
        aggregator = OpenInterestAggregator()

        agg = aggregator.get_aggregation("BTCUSDT")

        assert agg is None

    def test_get_latest(self) -> None:
        """Test getting latest data point."""
        aggregator = OpenInterestAggregator()
        now = datetime.now(UTC)

        oi1 = OpenInterestData(
            symbol="BTCUSDT",
            timestamp=now - timedelta(minutes=5),
            open_interest=1000000.0,
        )
        oi2 = OpenInterestData(
            symbol="BTCUSDT",
            timestamp=now,
            open_interest=1100000.0,
        )

        aggregator.add(oi1)
        aggregator.add(oi2)

        latest = aggregator.get_latest("BTCUSDT")

        assert latest is not None
        assert latest.open_interest == 1100000.0

    def test_get_latest_no_data(self) -> None:
        """Test getting latest when no data exists."""
        aggregator = OpenInterestAggregator()

        latest = aggregator.get_latest("BTCUSDT")

        assert latest is None

    def test_change_pct_calculation(self) -> None:
        """Test change percentage calculation."""
        aggregator = OpenInterestAggregator(window_minutes=60)
        now = datetime.now(UTC)

        oi1 = OpenInterestData(
            symbol="BTCUSDT",
            timestamp=now - timedelta(minutes=30),
            open_interest=1000000.0,
        )
        oi2 = OpenInterestData(
            symbol="BTCUSDT",
            timestamp=now,
            open_interest=1100000.0,
        )

        aggregator.add(oi1)
        aggregator.add(oi2)

        agg = aggregator.get_aggregation("BTCUSDT")

        assert agg is not None
        assert agg.change_pct == 10.0  # (1100000 - 1000000) / 1000000 * 100

    def test_multiple_symbols(self) -> None:
        """Test handling multiple symbols."""
        aggregator = OpenInterestAggregator()
        now = datetime.now(UTC)

        oi_btc = OpenInterestData(
            symbol="BTCUSDT",
            timestamp=now,
            open_interest=1000000.0,
        )
        oi_eth = OpenInterestData(
            symbol="ETHUSDT",
            timestamp=now,
            open_interest=5000000.0,
        )

        aggregator.add(oi_btc)
        aggregator.add(oi_eth)

        symbols = aggregator.get_all_symbols()
        assert len(symbols) == 2
        assert "BTCUSDT" in symbols
        assert "ETHUSDT" in symbols

    def test_data_cleanup(self) -> None:
        """Test old data cleanup."""
        aggregator = OpenInterestAggregator(window_minutes=10)
        now = datetime.now(UTC)

        # Add old data
        old_oi = OpenInterestData(
            symbol="BTCUSDT",
            timestamp=now - timedelta(minutes=30),  # Outside 2x window
            open_interest=1000000.0,
        )
        aggregator.add(old_oi)

        # Add new data
        new_oi = OpenInterestData(
            symbol="BTCUSDT",
            timestamp=now,
            open_interest=1100000.0,
        )
        aggregator.add(new_oi)

        # Old data should be cleaned up
        agg = aggregator.get_aggregation("BTCUSDT", window_minutes=60)
        assert agg is None  # Not enough data in 60 min window
