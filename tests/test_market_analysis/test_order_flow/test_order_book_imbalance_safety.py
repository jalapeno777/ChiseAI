"""Tests for Order Book Imbalance indicator safety (repainting guard)."""

import pytest

from market_analysis.safety import RepaintingDetector, check_indicator


class TestOrderBookImbalanceSafety:
    """Safety tests for Order Book Imbalance indicator."""

    @pytest.fixture
    def obi_indicator(self):
        """Create Order Book Imbalance indicator instance."""
        from market_analysis.order_flow import OrderBookImbalance
        from market_analysis.order_flow.order_book_imbalance import (
            OrderBookSnapshot,
            PriceLevel,
        )

        return OrderBookImbalance()

    @pytest.fixture
    def sample_order_book_data(self):
        """Create sample order book data for testing."""
        from market_analysis.order_flow.order_book_imbalance import (
            OrderBookSnapshot,
            PriceLevel,
        )

        base_ts = 1609459200000.0

        def make_snapshot(ts, bid_price, ask_price):
            return OrderBookSnapshot(
                symbol="BTC/USDT",
                bids=[
                    PriceLevel(price=bid_price, quantity=100.0),
                    PriceLevel(price=bid_price - 1, quantity=200.0),
                    PriceLevel(price=bid_price - 2, quantity=300.0),
                    PriceLevel(price=bid_price - 3, quantity=400.0),
                    PriceLevel(price=bid_price - 4, quantity=500.0),
                    PriceLevel(price=bid_price - 5, quantity=600.0),
                    PriceLevel(price=bid_price - 6, quantity=700.0),
                    PriceLevel(price=bid_price - 7, quantity=800.0),
                    PriceLevel(price=bid_price - 8, quantity=900.0),
                    PriceLevel(price=bid_price - 9, quantity=1000.0),
                ],
                asks=[
                    PriceLevel(price=ask_price, quantity=100.0),
                    PriceLevel(price=ask_price + 1, quantity=200.0),
                    PriceLevel(price=ask_price + 2, quantity=300.0),
                    PriceLevel(price=ask_price + 3, quantity=400.0),
                    PriceLevel(price=ask_price + 4, quantity=500.0),
                    PriceLevel(price=ask_price + 5, quantity=600.0),
                    PriceLevel(price=ask_price + 6, quantity=700.0),
                    PriceLevel(price=ask_price + 7, quantity=800.0),
                    PriceLevel(price=ask_price + 8, quantity=900.0),
                    PriceLevel(price=ask_price + 9, quantity=1000.0),
                ],
                timestamp=ts,
            )

        # Create snapshots with slight price variations
        snapshots = []
        for i in range(30):
            ts = base_ts + i * 1000
            bid = 50000.0 + i * 10  # Slight upward drift
            ask = 50001.0 + i * 10  # Slight upward drift
            snapshots.append(make_snapshot(ts, bid, ask))

        return snapshots

    def test_order_book_imbalance_no_repainting(
        self, obi_indicator, sample_order_book_data
    ):
        """Test that Order Book Imbalance does not repaint.

        Order Book Imbalance should be point-in-time only - it uses
        the latest snapshot and should not look ahead.
        """
        detector = RepaintingDetector(tolerance=0.0)
        result = detector.check_repainting(obi_indicator, sample_order_book_data)

        assert result.passed is True, (
            f"Order Book Imbalance repainting detected: {result.violations}"
        )

    def test_order_book_imbalance_uses_latest_only(
        self, obi_indicator, sample_order_book_data
    ):
        """Test that Order Book Imbalance computes from latest snapshot only.

        The indicator should use data[-1] (latest snapshot) and not
        be affected by historical snapshots.
        """
        # Calculate with all data
        result_all = obi_indicator.compute(sample_order_book_data)
        bid_ask_all = result_all.bid_ask_ratio

        # Calculate with just the last 5 snapshots
        result_slice = obi_indicator.compute(sample_order_book_data[-5:])
        bid_ask_slice = result_slice.bid_ask_ratio

        # Should produce same result since it uses latest snapshot
        assert abs(bid_ask_all - bid_ask_slice) < 1e-10, (
            "Order Book Imbalance should use only latest snapshot"
        )

    def test_order_book_imbalance_check_indicator_convenience(
        self, obi_indicator, sample_order_book_data
    ):
        """Test the check_indicator convenience function for OBI."""
        result = check_indicator(obi_indicator, sample_order_book_data)

        assert result.passed is True
        assert result.violation_count == 0
        assert "OrderBookImbalance" in result.guard_name
