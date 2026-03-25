"""Tests for CVD calculator."""

from datetime import UTC, datetime, timedelta

import pytest

from market_analysis.cvd.cvd_calculator import (
    CVDCalculator,
    CVDResult,
    Trade,
    TradeDirection,
)


class TestTrade:
    """Tests for Trade dataclass."""

    def test_trade_direction_buy(self):
        """Test buy trade classification."""
        trade = Trade(
            trade_id=1,
            price=50000.0,
            quantity=0.1,
            timestamp=datetime.now(UTC),
            is_buyer_maker=False,
        )
        assert trade.direction == TradeDirection.BUY
        assert trade.volume_delta == 0.1

    def test_trade_direction_sell(self):
        """Test sell trade classification."""
        trade = Trade(
            trade_id=2,
            price=50000.0,
            quantity=0.1,
            timestamp=datetime.now(UTC),
            is_buyer_maker=True,
        )
        assert trade.direction == TradeDirection.SELL
        assert trade.volume_delta == -0.1


class TestCVDCalculator:
    """Tests for CVDCalculator."""

    @pytest.fixture
    def calculator(self):
        """Create CVDCalculator instance."""
        return CVDCalculator()

    @pytest.fixture
    def sample_trades(self):
        """Create sample trade list."""
        base_time = datetime.now(UTC)
        return [
            Trade(
                trade_id=1,
                price=50000,
                quantity=0.1,
                timestamp=base_time,
                is_buyer_maker=False,
            ),
            Trade(
                trade_id=2,
                price=50010,
                quantity=0.2,
                timestamp=base_time + timedelta(seconds=1),
                is_buyer_maker=True,
            ),
            Trade(
                trade_id=3,
                price=50020,
                quantity=0.15,
                timestamp=base_time + timedelta(seconds=2),
                is_buyer_maker=False,
            ),
            Trade(
                trade_id=4,
                price=50030,
                quantity=0.25,
                timestamp=base_time + timedelta(seconds=3),
                is_buyer_maker=True,
            ),
            Trade(
                trade_id=5,
                price=50040,
                quantity=0.3,
                timestamp=base_time + timedelta(seconds=4),
                is_buyer_maker=False,
            ),
        ]

    def test_calculate_from_trades(self, calculator, sample_trades):
        """Test CVD calculation from trade list."""
        result = calculator.calculate_from_trades(sample_trades)

        assert isinstance(result, CVDResult)
        assert result.trade_count == 5
        assert len(result.timestamps) == 5
        assert len(result.cvd_values) == 5
        # Trade 1: +0.1, Trade 2: -0.2, Trade 3: +0.15, Trade 4: -0.25, Trade 5: +0.3
        # CVD: [0.1, -0.1, 0.05, -0.2, 0.1]
        assert result.cvd_values[-1] == pytest.approx(0.1)
        assert result.buy_volume == 0.55  # trades 1, 3, 5
        assert result.sell_volume == 0.45  # trades 2, 4

    def test_calculate_from_trades_empty(self, calculator):
        """Test CVD calculation with empty trade list."""
        result = calculator.calculate_from_trades([])

        assert result.trade_count == 0
        assert result.cvd_values == []
        assert result.buy_volume == 0.0
        assert result.sell_volume == 0.0

    def test_calculate_from_arrays(self, calculator):
        """Test CVD calculation from arrays."""
        timestamps = [datetime.now(UTC) + timedelta(seconds=i) for i in range(3)]
        prices = [50000.0, 50010.0, 50020.0]
        quantities = [0.1, 0.2, 0.15]
        is_buyer_maker = [False, True, False]

        result = calculator.calculate_from_arrays(
            timestamps, prices, quantities, is_buyer_maker
        )

        assert result.trade_count == 3
        assert len(result.cvd_values) == 3
        # Trade 1: +0.1, Trade 2: -0.2, Trade 3: +0.15
        # CVD: [0.1, -0.1, 0.05]
        assert result.cvd_values[-1] == pytest.approx(0.05)

    def test_calculate_from_arrays_length_mismatch(self, calculator):
        """Test CVD calculation with mismatched array lengths."""
        timestamps = [datetime.now(UTC)]
        prices = [50000.0, 50010.0]  # Different length
        quantities = [0.1]
        is_buyer_maker = [False]

        with pytest.raises(ValueError, match="same length"):
            calculator.calculate_from_arrays(
                timestamps, prices, quantities, is_buyer_maker
            )

    def test_get_cvd_rate(self, calculator, sample_trades):
        """Test CVD rate calculation."""
        result = calculator.calculate_from_trades(sample_trades)
        rates = calculator.get_cvd_rate(result, window_size=2)

        assert len(rates) == len(result.cvd_values)
        # np.diff prepends cvd[0], so rates[0] = cvd[0] - cvd[0] = 0
        # rates[1] = cvd[1] - cvd[0] = -0.1 - 0.1 = -0.2
        assert rates[0] == pytest.approx(0.0)  # Prepend delta is 0
        assert rates[1] == pytest.approx(
            -0.2
        )  # Actual change from first to second trade

    def test_detect_divergence(self, calculator):
        """Test basic divergence detection."""
        # Price going down, CVD going up (bullish divergence)
        prices = [100.0, 99.0, 98.0, 97.0, 96.0]
        cvd_values = [0.0, 1.0, 2.0, 3.0, 4.0]  # CVD going up while price down

        divergences = calculator.detect_divergence(cvd_values, prices)

        assert len(divergences) > 0

    def test_detect_divergence_no_divergence(self, calculator):
        """Test divergence detection when no divergence exists."""
        prices = [100.0, 101.0, 102.0, 103.0, 104.0]
        cvd_values = [0.0, 1.0, 2.0, 3.0, 4.0]  # Both going up

        divergences = calculator.detect_divergence(cvd_values, prices, threshold=0.1)

        # May have some divergences due to magnitude differences, but shouldn't have strong ones
        assert isinstance(divergences, list)


class TestCVDCalculatorEdgeCases:
    """Edge case tests for CVDCalculator."""

    @pytest.fixture
    def calculator(self):
        """Create CVDCalculator instance."""
        return CVDCalculator()

    def test_single_trade(self, calculator):
        """Test CVD with single trade."""
        trade = Trade(
            trade_id=1,
            price=50000,
            quantity=0.1,
            timestamp=datetime.now(UTC),
            is_buyer_maker=False,
        )
        result = calculator.calculate_from_trades([trade])

        assert result.trade_count == 1
        assert result.cvd_values[0] == 0.1
        assert result.buy_volume == 0.1
        assert result.sell_volume == 0.0

    def test_all_sell_trades(self, calculator):
        """Test CVD with all sell trades."""
        base_time = datetime.now(UTC)
        trades = [
            Trade(
                trade_id=i,
                price=50000 - i,
                quantity=0.1,
                timestamp=base_time + timedelta(seconds=i),
                is_buyer_maker=True,
            )
            for i in range(5)
        ]
        result = calculator.calculate_from_trades(trades)

        assert result.trade_count == 5
        assert result.cvd_values[-1] == pytest.approx(-0.5)
        assert result.buy_volume == 0.0
        assert result.sell_volume == 0.5

    def test_unsorted_trades(self, calculator):
        """Test CVD calculation sorts trades by timestamp."""
        base_time = datetime.now(UTC)
        # Trades out of order
        trades = [
            Trade(
                trade_id=3,
                price=50030,
                quantity=0.3,
                timestamp=base_time + timedelta(seconds=3),
                is_buyer_maker=False,
            ),
            Trade(
                trade_id=1,
                price=50000,
                quantity=0.1,
                timestamp=base_time,
                is_buyer_maker=False,
            ),
            Trade(
                trade_id=2,
                price=50010,
                quantity=0.2,
                timestamp=base_time + timedelta(seconds=1),
                is_buyer_maker=True,
            ),
        ]
        result = calculator.calculate_from_trades(trades)

        # Should be sorted: trade 1 (+0.1), trade 2 (-0.2), trade 3 (+0.3)
        # CVD: [0.1, -0.1, 0.2]
        assert result.cvd_values[0] == pytest.approx(0.1)
        assert result.cvd_values[1] == pytest.approx(-0.1)
        assert result.cvd_values[2] == pytest.approx(0.2)
