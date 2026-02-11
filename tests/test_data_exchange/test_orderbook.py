"""Tests for order book functionality."""

from datetime import datetime

import pytest

from exchange_data.binance.orderbook import (
    OrderBookLevel,
    OrderBookSnapshot,
    OrderBookTracker,
)


class TestOrderBookLevel:
    """Test OrderBookLevel dataclass."""

    def test_creation(self) -> None:
        """Test creating an order book level."""
        level = OrderBookLevel(price=50000.0, quantity=1.5)

        assert level.price == 50000.0
        assert level.quantity == 1.5


class TestOrderBookSnapshot:
    """Test OrderBookSnapshot functionality."""

    def test_creation(self) -> None:
        """Test creating a snapshot."""
        snapshot = OrderBookSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            last_update_id=12345,
            bids=[OrderBookLevel(price=50000.0, quantity=1.0)],
            asks=[OrderBookLevel(price=50001.0, quantity=0.5)],
        )

        assert snapshot.symbol == "BTCUSDT"
        assert snapshot.last_update_id == 12345
        assert len(snapshot.bids) == 1
        assert len(snapshot.asks) == 1

    def test_best_bid(self) -> None:
        """Test best bid calculation."""
        snapshot = OrderBookSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            last_update_id=1,
            bids=[
                OrderBookLevel(price=50000.0, quantity=1.0),
                OrderBookLevel(price=49999.0, quantity=2.0),
            ],
            asks=[OrderBookLevel(price=50001.0, quantity=0.5)],
        )

        assert snapshot.best_bid == 50000.0

    def test_best_ask(self) -> None:
        """Test best ask calculation."""
        snapshot = OrderBookSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            last_update_id=1,
            bids=[OrderBookLevel(price=50000.0, quantity=1.0)],
            asks=[
                OrderBookLevel(price=50001.0, quantity=0.5),
                OrderBookLevel(price=50002.0, quantity=1.0),
            ],
        )

        assert snapshot.best_ask == 50001.0

    def test_mid_price(self) -> None:
        """Test mid price calculation."""
        snapshot = OrderBookSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            last_update_id=1,
            bids=[OrderBookLevel(price=50000.0, quantity=1.0)],
            asks=[OrderBookLevel(price=50002.0, quantity=0.5)],
        )

        assert snapshot.mid_price == 50001.0

    def test_spread(self) -> None:
        """Test spread calculation."""
        snapshot = OrderBookSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            last_update_id=1,
            bids=[OrderBookLevel(price=50000.0, quantity=1.0)],
            asks=[OrderBookLevel(price=50002.0, quantity=0.5)],
        )

        assert snapshot.spread == 2.0

    def test_spread_pct(self) -> None:
        """Test spread percentage calculation."""
        snapshot = OrderBookSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            last_update_id=1,
            bids=[OrderBookLevel(price=50000.0, quantity=1.0)],
            asks=[OrderBookLevel(price=50100.0, quantity=0.5)],
        )

        assert snapshot.spread_pct == pytest.approx(0.1996, rel=0.01)

    def test_empty_book(self) -> None:
        """Test empty order book handling."""
        snapshot = OrderBookSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            last_update_id=1,
            bids=[],
            asks=[],
        )

        assert snapshot.best_bid is None
        assert snapshot.best_ask is None
        assert snapshot.mid_price is None
        assert snapshot.spread is None

    def test_get_bid_depth(self) -> None:
        """Test bid depth calculation."""
        snapshot = OrderBookSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            last_update_id=1,
            bids=[
                OrderBookLevel(price=50000.0, quantity=1.0),
                OrderBookLevel(price=49900.0, quantity=2.0),
                OrderBookLevel(price=49800.0, quantity=3.0),
            ],
            asks=[],
        )

        depth = snapshot.get_bid_depth(49900.0)
        assert depth == 3.0  # 1.0 + 2.0

    def test_get_ask_depth(self) -> None:
        """Test ask depth calculation."""
        snapshot = OrderBookSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            last_update_id=1,
            bids=[],
            asks=[
                OrderBookLevel(price=50100.0, quantity=0.5),
                OrderBookLevel(price=50200.0, quantity=1.0),
                OrderBookLevel(price=50300.0, quantity=1.5),
            ],
        )

        depth = snapshot.get_ask_depth(50200.0)
        assert depth == 1.5  # 0.5 + 1.0

    def test_to_dict(self) -> None:
        """Test dictionary conversion."""
        snapshot = OrderBookSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
            last_update_id=12345,
            bids=[OrderBookLevel(price=50000.0, quantity=1.0)],
            asks=[OrderBookLevel(price=50001.0, quantity=0.5)],
            latency_ms=50.0,
        )

        data = snapshot.to_dict()

        assert data["symbol"] == "BTCUSDT"
        assert data["last_update_id"] == 12345
        assert data["latency_ms"] == 50.0
        assert data["best_bid"] == 50000.0
        assert data["best_ask"] == 50001.0


class TestOrderBookTracker:
    """Test OrderBookTracker functionality."""

    def test_add_snapshot(self) -> None:
        """Test adding snapshots."""
        tracker = OrderBookTracker()
        snapshot = OrderBookSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            last_update_id=1,
            bids=[],
            asks=[],
        )

        tracker.add_snapshot(snapshot)

        assert "BTCUSDT" in tracker.get_all_symbols()

    def test_get_latest(self) -> None:
        """Test getting latest snapshot."""
        tracker = OrderBookTracker()

        snapshot1 = OrderBookSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            last_update_id=1,
            bids=[],
            asks=[],
        )
        snapshot2 = OrderBookSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            last_update_id=2,
            bids=[],
            asks=[],
        )

        tracker.add_snapshot(snapshot1)
        tracker.add_snapshot(snapshot2)

        latest = tracker.get_latest("BTCUSDT")
        assert latest is not None
        assert latest.last_update_id == 2

    def test_get_history(self) -> None:
        """Test getting snapshot history."""
        tracker = OrderBookTracker()

        for i in range(5):
            snapshot = OrderBookSnapshot(
                symbol="BTCUSDT",
                timestamp=datetime.utcnow(),
                last_update_id=i,
                bids=[],
                asks=[],
            )
            tracker.add_snapshot(snapshot)

        history = tracker.get_history("BTCUSDT", count=3)
        assert len(history) == 3

    def test_detect_gaps(self) -> None:
        """Test gap detection."""
        tracker = OrderBookTracker()

        # Add snapshots with a gap
        snapshot1 = OrderBookSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
            last_update_id=1,
            bids=[],
            asks=[],
        )
        snapshot2 = OrderBookSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime(2024, 1, 1, 12, 0, 10),  # 10 second gap
            last_update_id=2,
            bids=[],
            asks=[],
        )

        tracker.add_snapshot(snapshot1)
        tracker.add_snapshot(snapshot2)

        gaps = tracker.detect_gaps("BTCUSDT", max_gap_sec=5.0)
        assert len(gaps) == 1
        assert gaps[0]["duration_sec"] == 10.0

    def test_no_gaps(self) -> None:
        """Test when no gaps exist."""
        tracker = OrderBookTracker()

        snapshot1 = OrderBookSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
            last_update_id=1,
            bids=[],
            asks=[],
        )
        snapshot2 = OrderBookSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime(2024, 1, 1, 12, 0, 1),  # 1 second gap
            last_update_id=2,
            bids=[],
            asks=[],
        )

        tracker.add_snapshot(snapshot1)
        tracker.add_snapshot(snapshot2)

        gaps = tracker.detect_gaps("BTCUSDT", max_gap_sec=5.0)
        assert len(gaps) == 0

    def test_has_duplicates(self) -> None:
        """Test duplicate detection."""
        tracker = OrderBookTracker()

        snapshot1 = OrderBookSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            last_update_id=1,
            bids=[],
            asks=[],
        )
        snapshot2 = OrderBookSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            last_update_id=1,  # Duplicate ID
            bids=[],
            asks=[],
        )

        tracker.add_snapshot(snapshot1)
        tracker.add_snapshot(snapshot2)

        assert tracker.has_duplicates("BTCUSDT") is True

    def test_no_duplicates(self) -> None:
        """Test when no duplicates exist."""
        tracker = OrderBookTracker()

        snapshot1 = OrderBookSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            last_update_id=1,
            bids=[],
            asks=[],
        )
        snapshot2 = OrderBookSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            last_update_id=2,
            bids=[],
            asks=[],
        )

        tracker.add_snapshot(snapshot1)
        tracker.add_snapshot(snapshot2)

        assert tracker.has_duplicates("BTCUSDT") is False

    def test_max_history(self) -> None:
        """Test history limit enforcement."""
        tracker = OrderBookTracker(max_history=5)

        for i in range(10):
            snapshot = OrderBookSnapshot(
                symbol="BTCUSDT",
                timestamp=datetime.utcnow(),
                last_update_id=i,
                bids=[],
                asks=[],
            )
            tracker.add_snapshot(snapshot)

        history = tracker.get_history("BTCUSDT", count=100)
        assert len(history) == 5
