"""Comprehensive tests for OrderBookImbalance indicator.

Tests cover bid/ask ratio calculation, depth imbalance at multiple
levels, configurable thresholds for signal generation, FeatureStore
integration, edge cases, and signal conversion.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from market_analysis.indicators.base import SignalDirection
from market_analysis.indicators.feature_store import FeatureStore
from market_analysis.order_flow.order_book_imbalance import (
    ImbalanceLevel,
    OrderBookImbalance,
    OrderBookImbalanceResult,
    OrderBookSnapshot,
    PriceLevel,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_price_levels(
    base_price: float,
    side: str,
    num_levels: int = 15,
    qty: float = 1.0,
) -> list[PriceLevel]:
    """Build a list of PriceLevel objects.

    Args:
        base_price: Starting price (best price for the side).
        side: 'bid' (decreasing prices) or 'ask' (increasing prices).
        num_levels: Number of levels to generate.
        qty: Quantity at each level.

    Returns:
        List of PriceLevel objects.
    """
    levels: list[PriceLevel] = []
    step = 0.5
    for i in range(num_levels):
        if side == "bid":
            price = base_price - i * step
        else:
            price = base_price + i * step
        levels.append(PriceLevel(price=price, quantity=qty))
    return levels


@pytest.fixture
def balanced_snapshot() -> OrderBookSnapshot:
    """Create a perfectly balanced order book snapshot."""
    bids = _make_price_levels(100.0, "bid", num_levels=15, qty=1.0)
    asks = _make_price_levels(100.5, "ask", num_levels=15, qty=1.0)
    return OrderBookSnapshot(
        symbol="BTC/USDT",
        bids=bids,
        asks=asks,
        timestamp=1_700_000_000_000,
    )


@pytest.fixture
def bullish_snapshot() -> OrderBookSnapshot:
    """Create a bullish order book snapshot (2x bid volume)."""
    bids = _make_price_levels(100.0, "bid", num_levels=15, qty=2.0)
    asks = _make_price_levels(100.5, "ask", num_levels=15, qty=1.0)
    return OrderBookSnapshot(
        symbol="BTC/USDT",
        bids=bids,
        asks=asks,
        timestamp=1_700_000_000_000,
    )


@pytest.fixture
def bearish_snapshot() -> OrderBookSnapshot:
    """Create a bearish order book snapshot (2x ask volume)."""
    bids = _make_price_levels(100.0, "bid", num_levels=15, qty=1.0)
    asks = _make_price_levels(100.5, "ask", num_levels=15, qty=2.0)
    return OrderBookSnapshot(
        symbol="BTC/USDT",
        bids=bids,
        asks=asks,
        timestamp=1_700_000_000_000,
    )


@pytest.fixture
def strong_bullish_snapshot() -> OrderBookSnapshot:
    """Create a strongly bullish snapshot (3x bid volume)."""
    bids = _make_price_levels(100.0, "bid", num_levels=15, qty=3.0)
    asks = _make_price_levels(100.5, "ask", num_levels=15, qty=1.0)
    return OrderBookSnapshot(
        symbol="BTC/USDT",
        bids=bids,
        asks=asks,
        timestamp=1_700_000_000_000,
    )


@pytest.fixture
def strong_bearish_snapshot() -> OrderBookSnapshot:
    """Create a strongly bearish snapshot (3x ask volume)."""
    bids = _make_price_levels(100.0, "bid", num_levels=15, qty=1.0)
    asks = _make_price_levels(100.5, "ask", num_levels=15, qty=3.0)
    return OrderBookSnapshot(
        symbol="BTC/USDT",
        bids=bids,
        asks=asks,
        timestamp=1_700_000_000_000,
    )


@pytest.fixture
def empty_ask_snapshot() -> OrderBookSnapshot:
    """Create a snapshot with zero ask volume (edge case)."""
    bids = _make_price_levels(100.0, "bid", num_levels=15, qty=1.0)
    asks = [PriceLevel(price=100.5 + i * 0.5, quantity=0.0) for i in range(15)]
    return OrderBookSnapshot(
        symbol="BTC/USDT",
        bids=bids,
        asks=asks,
        timestamp=1_700_000_000_000,
    )


@pytest.fixture
def empty_bid_snapshot() -> OrderBookSnapshot:
    """Create a snapshot with zero bid volume (edge case)."""
    bids = [PriceLevel(price=100.0 - i * 0.5, quantity=0.0) for i in range(15)]
    asks = _make_price_levels(100.5, "ask", num_levels=15, qty=1.0)
    return OrderBookSnapshot(
        symbol="BTC/USDT",
        bids=bids,
        asks=asks,
        timestamp=1_700_000_000_000,
    )


@pytest.fixture
def indicator() -> OrderBookImbalance:
    """Create default OrderBookImbalance indicator."""
    return OrderBookImbalance(num_levels=10)


@pytest.fixture
def mock_feature_store() -> MagicMock:
    """Create a mock FeatureStore."""
    store = MagicMock(spec=FeatureStore)
    store.get.return_value = None
    store.set.return_value = True
    return store


# ---------------------------------------------------------------------------
# PriceLevel Tests
# ---------------------------------------------------------------------------


class TestPriceLevel:
    """Tests for PriceLevel dataclass."""

    def test_creation(self) -> None:
        level = PriceLevel(price=50000.0, quantity=1.5)
        assert level.price == 50000.0
        assert level.quantity == 1.5


# ---------------------------------------------------------------------------
# OrderBookSnapshot Tests
# ---------------------------------------------------------------------------


class TestOrderBookSnapshot:
    """Tests for OrderBookSnapshot dataclass."""

    def test_creation(self) -> None:
        bids = [PriceLevel(price=100.0, quantity=1.0)]
        asks = [PriceLevel(price=101.0, quantity=1.0)]
        snap = OrderBookSnapshot(
            symbol="BTC/USDT",
            bids=bids,
            asks=asks,
            timestamp=1_700_000_000_000,
        )
        assert snap.symbol == "BTC/USDT"
        assert len(snap.bids) == 1
        assert len(snap.asks) == 1


# ---------------------------------------------------------------------------
# OrderBookImbalanceResult Tests
# ---------------------------------------------------------------------------


class TestOrderBookImbalanceResult:
    """Tests for OrderBookImbalanceResult dataclass."""

    @pytest.fixture
    def bullish_result(self) -> OrderBookImbalanceResult:
        return OrderBookImbalanceResult(
            bid_ask_ratio=1.5,
            depth_imbalance=0.2,
            bid_volume=15.0,
            ask_volume=10.0,
            level_imbalances={1: 0.2, 2: 0.15},
            imbalance_level=ImbalanceLevel.BUY,
            spread=0.5,
            mid_price=100.25,
            num_levels=10,
            timestamp=datetime.now(UTC),
        )

    def test_is_bullish(self, bullish_result: OrderBookImbalanceResult) -> None:
        assert bullish_result.is_bullish is True
        assert bullish_result.is_bearish is False

    def test_is_bearish(self) -> None:
        result = OrderBookImbalanceResult(
            bid_ask_ratio=0.5,
            depth_imbalance=-0.3,
            bid_volume=10.0,
            ask_volume=20.0,
            level_imbalances={},
            imbalance_level=ImbalanceLevel.STRONG_SELL,
            spread=0.5,
            mid_price=100.25,
            num_levels=10,
            timestamp=datetime.now(UTC),
        )
        assert result.is_bearish is True
        assert result.is_bullish is False

    def test_neutral(self) -> None:
        result = OrderBookImbalanceResult(
            bid_ask_ratio=1.0,
            depth_imbalance=0.0,
            bid_volume=10.0,
            ask_volume=10.0,
            level_imbalances={},
            imbalance_level=ImbalanceLevel.NEUTRAL,
            spread=0.5,
            mid_price=100.25,
            num_levels=10,
            timestamp=datetime.now(UTC),
        )
        assert result.is_bullish is False
        assert result.is_bearish is False


# ---------------------------------------------------------------------------
# ImbalanceLevel Tests
# ---------------------------------------------------------------------------


class TestImbalanceLevel:
    """Tests for ImbalanceLevel enum."""

    def test_values(self) -> None:
        assert ImbalanceLevel.STRONG_BUY.value == "strong_buy"
        assert ImbalanceLevel.BUY.value == "buy"
        assert ImbalanceLevel.NEUTRAL.value == "neutral"
        assert ImbalanceLevel.SELL.value == "sell"
        assert ImbalanceLevel.STRONG_SELL.value == "strong_sell"


# ---------------------------------------------------------------------------
# OrderBookImbalance Initialization Tests
# ---------------------------------------------------------------------------


class TestOrderBookImbalanceInit:
    """Tests for OrderBookImbalance initialization and validation."""

    def test_default_initialization(self) -> None:
        ob = OrderBookImbalance()
        assert ob.num_levels == 10
        assert ob.strong_buy_threshold == 1.5
        assert ob.buy_threshold == 1.2
        assert ob.sell_threshold == 0.8
        assert ob.strong_sell_threshold == 0.5
        assert ob._feature_store is None

    def test_custom_initialization(self, mock_feature_store: MagicMock) -> None:
        ob = OrderBookImbalance(
            num_levels=5,
            strong_buy_threshold=2.0,
            buy_threshold=1.5,
            sell_threshold=0.7,
            strong_sell_threshold=0.3,
            feature_store=mock_feature_store,
            cache_ttl=120,
        )
        assert ob.num_levels == 5
        assert ob.strong_buy_threshold == 2.0
        assert ob.buy_threshold == 1.5
        assert ob.sell_threshold == 0.7
        assert ob.strong_sell_threshold == 0.3
        assert ob._cache_ttl == 120

    def test_custom_name(self) -> None:
        ob = OrderBookImbalance(name="CustomOB")
        assert ob.name == "CustomOB"

    def test_default_name(self) -> None:
        ob = OrderBookImbalance()
        assert ob.name == "OrderBookImbalance"

    def test_invalid_num_levels_zero(self) -> None:
        with pytest.raises(ValueError, match="num_levels must be >= 1"):
            OrderBookImbalance(num_levels=0)

    def test_invalid_num_levels_negative(self) -> None:
        with pytest.raises(ValueError, match="num_levels must be >= 1"):
            OrderBookImbalance(num_levels=-1)

    def test_invalid_thresholds_strong_buy_le_buy(self) -> None:
        with pytest.raises(ValueError, match="strong_buy_threshold"):
            OrderBookImbalance(strong_buy_threshold=1.0, buy_threshold=1.2)

    def test_invalid_thresholds_sell_le_strong_sell(self) -> None:
        with pytest.raises(ValueError, match="sell_threshold"):
            OrderBookImbalance(sell_threshold=0.4, strong_sell_threshold=0.5)

    def test_invalid_thresholds_buy_le_sell(self) -> None:
        with pytest.raises(ValueError, match="buy_threshold"):
            OrderBookImbalance(buy_threshold=0.8, sell_threshold=0.9)


# ---------------------------------------------------------------------------
# BaseIndicator Interface Tests
# ---------------------------------------------------------------------------


class TestBaseIndicatorInterface:
    """Tests for BaseIndicator abstract interface compliance."""

    def test_description(self, indicator: OrderBookImbalance) -> None:
        assert isinstance(indicator.description, str)
        assert len(indicator.description) > 0

    def test_parameters(self, indicator: OrderBookImbalance) -> None:
        params = indicator.parameters
        assert isinstance(params, dict)
        assert "num_levels" in params
        assert "strong_buy_threshold" in params
        assert "buy_threshold" in params
        assert "sell_threshold" in params
        assert "strong_sell_threshold" in params

    def test_get_metadata(self, indicator: OrderBookImbalance) -> None:
        meta = indicator.get_metadata()
        assert meta["name"] == "OrderBookImbalance"
        assert "description" in meta
        assert "parameters" in meta


# ---------------------------------------------------------------------------
# Static Method Tests
# ---------------------------------------------------------------------------


class TestStaticMethods:
    """Tests for static helper methods."""

    def test_total_volume(self) -> None:
        levels = [PriceLevel(price=100.0, quantity=1.0) for _ in range(5)]
        assert OrderBookImbalance._total_volume(levels) == 5.0

    def test_total_volume_empty(self) -> None:
        assert OrderBookImbalance._total_volume([]) == 0.0

    def test_bid_ask_ratio_normal(self) -> None:
        assert OrderBookImbalance._bid_ask_ratio(15.0, 10.0) == 1.5

    def test_bid_ask_ratio_equal(self) -> None:
        assert OrderBookImbalance._bid_ask_ratio(10.0, 10.0) == 1.0

    def test_bid_ask_ratio_zero_ask(self) -> None:
        assert (
            OrderBookImbalance._bid_ask_ratio(10.0, 0.0) == OrderBookImbalance.MAX_RATIO
        )

    def test_bid_ask_ratio_zero_both(self) -> None:
        assert OrderBookImbalance._bid_ask_ratio(0.0, 0.0) == 1.0

    def test_bid_ask_ratio_zero_bid(self) -> None:
        assert OrderBookImbalance._bid_ask_ratio(0.0, 10.0) == 0.0

    def test_depth_imbalance_positive(self) -> None:
        # More bids than asks
        imb = OrderBookImbalance._depth_imbalance(15.0, 5.0)
        assert imb == pytest.approx(0.5)

    def test_depth_imbalance_negative(self) -> None:
        # More asks than bids
        imb = OrderBookImbalance._depth_imbalance(5.0, 15.0)
        assert imb == pytest.approx(-0.5)

    def test_depth_imbalance_zero(self) -> None:
        imb = OrderBookImbalance._depth_imbalance(10.0, 10.0)
        assert imb == pytest.approx(0.0)

    def test_depth_imbalance_all_bids(self) -> None:
        imb = OrderBookImbalance._depth_imbalance(10.0, 0.0)
        assert imb == pytest.approx(1.0)

    def test_depth_imbalance_all_asks(self) -> None:
        imb = OrderBookImbalance._depth_imbalance(0.0, 10.0)
        assert imb == pytest.approx(-1.0)

    def test_depth_imbalance_zero_total(self) -> None:
        imb = OrderBookImbalance._depth_imbalance(0.0, 0.0)
        assert imb == 0.0

    def test_classify_imbalance_strong_buy(self) -> None:
        assert (
            OrderBookImbalance._classify_imbalance(2.0, 1.5, 1.2, 0.8, 0.5)
            == ImbalanceLevel.STRONG_BUY
        )

    def test_classify_imbalance_buy(self) -> None:
        assert (
            OrderBookImbalance._classify_imbalance(1.3, 1.5, 1.2, 0.8, 0.5)
            == ImbalanceLevel.BUY
        )

    def test_classify_imbalance_neutral(self) -> None:
        assert (
            OrderBookImbalance._classify_imbalance(1.0, 1.5, 1.2, 0.8, 0.5)
            == ImbalanceLevel.NEUTRAL
        )

    def test_classify_imbalance_sell(self) -> None:
        assert (
            OrderBookImbalance._classify_imbalance(0.7, 1.5, 1.2, 0.8, 0.5)
            == ImbalanceLevel.SELL
        )

    def test_classify_imbalance_strong_sell(self) -> None:
        assert (
            OrderBookImbalance._classify_imbalance(0.3, 1.5, 1.2, 0.8, 0.5)
            == ImbalanceLevel.STRONG_SELL
        )

    def test_classify_imbalance_boundary_strong_buy(self) -> None:
        assert (
            OrderBookImbalance._classify_imbalance(1.5, 1.5, 1.2, 0.8, 0.5)
            == ImbalanceLevel.STRONG_BUY
        )

    def test_classify_imbalance_boundary_buy(self) -> None:
        assert (
            OrderBookImbalance._classify_imbalance(1.2, 1.5, 1.2, 0.8, 0.5)
            == ImbalanceLevel.BUY
        )

    def test_classify_imbalance_boundary_sell(self) -> None:
        assert (
            OrderBookImbalance._classify_imbalance(0.8, 1.5, 1.2, 0.8, 0.5)
            == ImbalanceLevel.SELL
        )

    def test_classify_imbalance_boundary_strong_sell(self) -> None:
        assert (
            OrderBookImbalance._classify_imbalance(0.5, 1.5, 1.2, 0.8, 0.5)
            == ImbalanceLevel.STRONG_SELL
        )


# ---------------------------------------------------------------------------
# Per-Level Imbalance Tests
# ---------------------------------------------------------------------------


class TestPerLevelImbalances:
    """Tests for per-level cumulative imbalance computation."""

    def test_single_level_balanced(self) -> None:
        bids = [PriceLevel(price=100.0, quantity=1.0)]
        asks = [PriceLevel(price=101.0, quantity=1.0)]
        result = OrderBookImbalance._per_level_imbalances(bids, asks, 1)
        assert result[1] == pytest.approx(0.0)

    def test_multiple_levels(self) -> None:
        bids = _make_price_levels(100.0, "bid", 5, 2.0)
        asks = _make_price_levels(101.0, "ask", 5, 1.0)
        result = OrderBookImbalance._per_level_imbalances(bids, asks, 5)
        assert len(result) == 5
        # Each level should have same imbalance (uniform qty)
        for level_val in result.values():
            assert level_val == pytest.approx(1.0 / 3.0)

    def test_num_levels_exceeds_available(self) -> None:
        bids = [PriceLevel(price=100.0, quantity=1.0)]
        asks = [PriceLevel(price=101.0, quantity=1.0)]
        result = OrderBookImbalance._per_level_imbalances(bids, asks, 3)
        # Returns entries for all requested levels; exhausted levels yield 0.0
        assert len(result) == 3
        assert result[1] == pytest.approx(0.0)  # 1 bid, 1 ask → balanced
        assert result[2] == pytest.approx(0.0)  # empty slices → 0/0 → 0.0
        assert result[3] == pytest.approx(0.0)  # empty slices → 0/0 → 0.0


# ---------------------------------------------------------------------------
# Validate Tests
# ---------------------------------------------------------------------------


class TestValidate:
    """Tests for data validation."""

    def test_validate_sufficient_data(
        self, indicator: OrderBookImbalance, balanced_snapshot: OrderBookSnapshot
    ) -> None:
        assert indicator.validate([balanced_snapshot]) is True

    def test_validate_empty_list(self, indicator: OrderBookImbalance) -> None:
        assert indicator.validate([]) is False

    def test_validate_insufficient_bids(self, indicator: OrderBookImbalance) -> None:
        snap = OrderBookSnapshot(
            symbol="BTC/USDT",
            bids=[PriceLevel(price=100.0, quantity=1.0)] * 5,  # Only 5
            asks=[PriceLevel(price=101.0, quantity=1.0)] * 15,
            timestamp=1_700_000_000_000,
        )
        assert indicator.validate([snap]) is False

    def test_validate_insufficient_asks(self, indicator: OrderBookImbalance) -> None:
        snap = OrderBookSnapshot(
            symbol="BTC/USDT",
            bids=[PriceLevel(price=100.0, quantity=1.0)] * 15,
            asks=[PriceLevel(price=101.0, quantity=1.0)] * 5,  # Only 5
            timestamp=1_700_000_000_000,
        )
        assert indicator.validate([snap]) is False


# ---------------------------------------------------------------------------
# Compute Tests
# ---------------------------------------------------------------------------


class TestCompute:
    """Tests for the compute() method (BaseIndicator interface)."""

    def test_compute_balanced(
        self, indicator: OrderBookImbalance, balanced_snapshot: OrderBookSnapshot
    ) -> None:
        result = indicator.compute([balanced_snapshot])
        assert result.bid_ask_ratio == pytest.approx(1.0)
        assert result.depth_imbalance == pytest.approx(0.0)
        assert result.imbalance_level == ImbalanceLevel.NEUTRAL

    def test_compute_bullish(
        self, indicator: OrderBookImbalance, bullish_snapshot: OrderBookSnapshot
    ) -> None:
        result = indicator.compute([bullish_snapshot])
        assert result.bid_ask_ratio == pytest.approx(2.0)
        assert result.depth_imbalance == pytest.approx(1.0 / 3.0)
        assert result.imbalance_level == ImbalanceLevel.STRONG_BUY

    def test_compute_bearish(
        self, indicator: OrderBookImbalance, bearish_snapshot: OrderBookSnapshot
    ) -> None:
        result = indicator.compute([bearish_snapshot])
        assert result.bid_ask_ratio == pytest.approx(0.5)
        assert result.depth_imbalance == pytest.approx(-1.0 / 3.0)
        assert result.imbalance_level == ImbalanceLevel.STRONG_SELL

    def test_compute_uses_latest_snapshot(self, indicator: OrderBookImbalance) -> None:
        """Verify compute uses the last snapshot in the list."""
        snap1 = OrderBookSnapshot(
            symbol="BTC/USDT",
            bids=_make_price_levels(100.0, "bid", 15, 1.0),
            asks=_make_price_levels(100.5, "ask", 15, 1.0),
            timestamp=1_700_000_000_000,
        )
        snap2 = OrderBookSnapshot(
            symbol="BTC/USDT",
            bids=_make_price_levels(100.0, "bid", 15, 3.0),
            asks=_make_price_levels(100.5, "ask", 15, 1.0),
            timestamp=1_700_000_001_000,
        )
        result = indicator.compute([snap1, snap2])
        assert result.bid_ask_ratio == pytest.approx(3.0)

    def test_compute_empty_data_raises(self, indicator: OrderBookImbalance) -> None:
        with pytest.raises(ValueError, match="No order book snapshots"):
            indicator.compute([])


# ---------------------------------------------------------------------------
# Analyze Tests
# ---------------------------------------------------------------------------


class TestAnalyze:
    """Tests for the analyze() method."""

    def test_analyze_balanced(
        self, indicator: OrderBookImbalance, balanced_snapshot: OrderBookSnapshot
    ) -> None:
        result = indicator.analyze(balanced_snapshot)
        assert result.bid_ask_ratio == pytest.approx(1.0)
        assert result.depth_imbalance == pytest.approx(0.0)
        assert result.spread == pytest.approx(0.5)
        assert result.mid_price == pytest.approx(100.25)
        assert result.num_levels == 10

    def test_analyze_bullish(
        self, indicator: OrderBookImbalance, bullish_snapshot: OrderBookSnapshot
    ) -> None:
        result = indicator.analyze(bullish_snapshot)
        assert result.bid_ask_ratio > 1.0
        assert result.depth_imbalance > 0.0
        assert result.is_bullish is True

    def test_analyze_bearish(
        self, indicator: OrderBookImbalance, bearish_snapshot: OrderBookSnapshot
    ) -> None:
        result = indicator.analyze(bearish_snapshot)
        assert result.bid_ask_ratio < 1.0
        assert result.depth_imbalance < 0.0
        assert result.is_bearish is True

    def test_analyze_level_imbalances(
        self, indicator: OrderBookImbalance, bullish_snapshot: OrderBookSnapshot
    ) -> None:
        result = indicator.analyze(bullish_snapshot)
        assert len(result.level_imbalances) == 10
        for lvl in range(1, 11):
            assert lvl in result.level_imbalances

    def test_analyze_num_levels_truncation(self) -> None:
        """Verify that only num_levels are used."""
        ob = OrderBookImbalance(num_levels=3)
        snap = OrderBookSnapshot(
            symbol="BTC/USDT",
            bids=_make_price_levels(100.0, "bid", 15, 2.0),
            asks=_make_price_levels(100.5, "ask", 15, 1.0),
            timestamp=1_700_000_000_000,
        )
        result = ob.analyze(snap)
        assert result.num_levels == 3
        assert len(result.level_imbalances) == 3

    def test_analyze_insufficient_bids_raises(self) -> None:
        ob = OrderBookImbalance(num_levels=10)
        snap = OrderBookSnapshot(
            symbol="BTC/USDT",
            bids=[PriceLevel(price=100.0, quantity=1.0)] * 5,
            asks=[PriceLevel(price=101.0, quantity=1.0)] * 15,
            timestamp=1_700_000_000_000,
        )
        with pytest.raises(ValueError, match="bid levels"):
            ob.analyze(snap)

    def test_analyze_insufficient_asks_raises(self) -> None:
        ob = OrderBookImbalance(num_levels=10)
        snap = OrderBookSnapshot(
            symbol="BTC/USDT",
            bids=[PriceLevel(price=100.0, quantity=1.0)] * 15,
            asks=[PriceLevel(price=101.0, quantity=1.0)] * 5,
            timestamp=1_700_000_000_000,
        )
        with pytest.raises(ValueError, match="ask levels"):
            ob.analyze(snap)

    def test_analyze_empty_asks_infinite_ratio(
        self, indicator: OrderBookImbalance, empty_ask_snapshot: OrderBookSnapshot
    ) -> None:
        result = indicator.analyze(empty_ask_snapshot)
        assert result.bid_ask_ratio == OrderBookImbalance.MAX_RATIO
        assert result.depth_imbalance == pytest.approx(1.0)
        assert result.imbalance_level == ImbalanceLevel.STRONG_BUY

    def test_analyze_empty_bids_zero_ratio(
        self, indicator: OrderBookImbalance, empty_bid_snapshot: OrderBookSnapshot
    ) -> None:
        result = indicator.analyze(empty_bid_snapshot)
        assert result.bid_ask_ratio == 0.0
        assert result.depth_imbalance == pytest.approx(-1.0)
        assert result.imbalance_level == ImbalanceLevel.STRONG_SELL


# ---------------------------------------------------------------------------
# Configurable Threshold Tests
# ---------------------------------------------------------------------------


class TestConfigurableThresholds:
    """Tests for configurable imbalance thresholds."""

    def test_custom_thresholds_classify_correctly(self) -> None:
        ob = OrderBookImbalance(
            num_levels=5,
            strong_buy_threshold=3.0,
            buy_threshold=2.0,
            sell_threshold=0.5,
            strong_sell_threshold=0.3,
        )
        # ratio=2.5 should be BUY (between 2.0 and 3.0)
        snap = OrderBookSnapshot(
            symbol="BTC/USDT",
            bids=_make_price_levels(100.0, "bid", 10, 2.5),
            asks=_make_price_levels(100.5, "ask", 10, 1.0),
            timestamp=1_700_000_000_000,
        )
        result = ob.analyze(snap)
        assert result.imbalance_level == ImbalanceLevel.BUY

    def test_tight_thresholds(self) -> None:
        ob = OrderBookImbalance(
            num_levels=5,
            strong_buy_threshold=1.1,
            buy_threshold=1.05,
            sell_threshold=0.95,
            strong_sell_threshold=0.9,
        )
        # ratio=1.08 -> BUY
        snap = OrderBookSnapshot(
            symbol="BTC/USDT",
            bids=_make_price_levels(100.0, "bid", 10, 1.08),
            asks=_make_price_levels(100.5, "ask", 10, 1.0),
            timestamp=1_700_000_000_000,
        )
        result = ob.analyze(snap)
        assert result.imbalance_level == ImbalanceLevel.BUY


# ---------------------------------------------------------------------------
# FeatureStore Integration Tests
# ---------------------------------------------------------------------------


class TestFeatureStoreIntegration:
    """Tests for FeatureStore caching integration."""

    def test_cache_hit_returns_cached_data(self, mock_feature_store: MagicMock) -> None:
        cached_data = {
            "bid_ask_ratio": 1.5,
            "depth_imbalance": 0.2,
            "bid_volume": 15.0,
            "ask_volume": 10.0,
            "imbalance_level": "buy",
            "spread": 0.5,
            "mid_price": 100.25,
            "num_levels": 5,
            "level_imbalances": {1: 0.2},
            "timestamp": "2026-01-01T00:00:00",
        }
        mock_feature_store.get.return_value = cached_data

        ob = OrderBookImbalance(num_levels=5, feature_store=mock_feature_store)
        snap = OrderBookSnapshot(
            symbol="BTC/USDT",
            bids=_make_price_levels(100.0, "bid", 10, 1.0),
            asks=_make_price_levels(100.5, "ask", 10, 1.0),
            timestamp=1_700_000_000_000,
        )
        result = ob.analyze(snap)

        assert result.bid_ask_ratio == 1.5
        assert result.depth_imbalance == 0.2
        assert result.imbalance_level == ImbalanceLevel.BUY
        mock_feature_store.get.assert_called_once()

    def test_cache_miss_computes_and_stores(
        self, mock_feature_store: MagicMock
    ) -> None:
        mock_feature_store.get.return_value = None

        ob = OrderBookImbalance(num_levels=5, feature_store=mock_feature_store)
        snap = OrderBookSnapshot(
            symbol="BTC/USDT",
            bids=_make_price_levels(100.0, "bid", 10, 2.0),
            asks=_make_price_levels(100.5, "ask", 10, 1.0),
            timestamp=1_700_000_000_000,
        )
        result = ob.analyze(snap)

        assert result.bid_ask_ratio == pytest.approx(2.0)
        mock_feature_store.set.assert_called_once()

    def test_no_feature_store_skips_cache(self) -> None:
        ob = OrderBookImbalance(num_levels=5)
        snap = OrderBookSnapshot(
            symbol="BTC/USDT",
            bids=_make_price_levels(100.0, "bid", 10, 1.0),
            asks=_make_price_levels(100.5, "ask", 10, 1.0),
            timestamp=1_700_000_000_000,
        )
        result = ob.analyze(snap)
        assert result is not None

    def test_cache_key_format(self, mock_feature_store: MagicMock) -> None:
        mock_feature_store.get.return_value = None
        ob = OrderBookImbalance(num_levels=7, feature_store=mock_feature_store)
        snap = OrderBookSnapshot(
            symbol="ETH/USDT",
            bids=_make_price_levels(100.0, "bid", 10, 1.0),
            asks=_make_price_levels(100.5, "ask", 10, 1.0),
            timestamp=1_700_000_000_000,
        )
        ob.analyze(snap)
        called_key = mock_feature_store.get.call_args[0][0]
        assert "ETH/USDT" in called_key
        assert "7" in called_key

    def test_cached_data_set_contains_all_fields(
        self, mock_feature_store: MagicMock
    ) -> None:
        mock_feature_store.get.return_value = None
        ob = OrderBookImbalance(num_levels=3, feature_store=mock_feature_store)
        snap = OrderBookSnapshot(
            symbol="BTC/USDT",
            bids=_make_price_levels(100.0, "bid", 10, 1.0),
            asks=_make_price_levels(100.5, "ask", 10, 1.0),
            timestamp=1_700_000_000_000,
        )
        ob.analyze(snap)
        call_args = mock_feature_store.set.call_args
        cached_data = call_args[0][1]
        required_fields = [
            "bid_ask_ratio",
            "depth_imbalance",
            "bid_volume",
            "ask_volume",
            "imbalance_level",
            "spread",
            "mid_price",
            "num_levels",
            "level_imbalances",
            "timestamp",
        ]
        for field in required_fields:
            assert field in cached_data, f"Missing field: {field}"


# ---------------------------------------------------------------------------
# Signal Conversion Tests
# ---------------------------------------------------------------------------


class TestToSignal:
    """Tests for signal conversion from imbalance results."""

    def test_strong_buy_signal(self) -> None:
        ob = OrderBookImbalance()
        result = OrderBookImbalanceResult(
            bid_ask_ratio=2.0,
            depth_imbalance=0.33,
            bid_volume=20.0,
            ask_volume=10.0,
            level_imbalances={},
            imbalance_level=ImbalanceLevel.STRONG_BUY,
            spread=0.5,
            mid_price=100.25,
            num_levels=10,
            timestamp=datetime.now(UTC),
        )
        signal = ob.to_signal(result)
        assert signal.direction == SignalDirection.BUY
        assert signal.confidence >= 0.6

    def test_buy_signal(self) -> None:
        ob = OrderBookImbalance()
        result = OrderBookImbalanceResult(
            bid_ask_ratio=1.3,
            depth_imbalance=0.13,
            bid_volume=11.3,
            ask_volume=8.7,
            level_imbalances={},
            imbalance_level=ImbalanceLevel.BUY,
            spread=0.5,
            mid_price=100.25,
            num_levels=10,
            timestamp=datetime.now(UTC),
        )
        signal = ob.to_signal(result)
        assert signal.direction == SignalDirection.BUY
        assert 0.5 <= signal.confidence <= 0.8

    def test_neutral_signal(self) -> None:
        ob = OrderBookImbalance()
        result = OrderBookImbalanceResult(
            bid_ask_ratio=1.0,
            depth_imbalance=0.0,
            bid_volume=10.0,
            ask_volume=10.0,
            level_imbalances={},
            imbalance_level=ImbalanceLevel.NEUTRAL,
            spread=0.5,
            mid_price=100.25,
            num_levels=10,
            timestamp=datetime.now(UTC),
        )
        signal = ob.to_signal(result)
        assert signal.direction == SignalDirection.HOLD
        assert signal.confidence == 0.5

    def test_sell_signal(self) -> None:
        ob = OrderBookImbalance()
        result = OrderBookImbalanceResult(
            bid_ask_ratio=0.7,
            depth_imbalance=-0.18,
            bid_volume=7.0,
            ask_volume=10.0,
            level_imbalances={},
            imbalance_level=ImbalanceLevel.SELL,
            spread=0.5,
            mid_price=100.25,
            num_levels=10,
            timestamp=datetime.now(UTC),
        )
        signal = ob.to_signal(result)
        assert signal.direction == SignalDirection.SELL
        assert 0.5 <= signal.confidence <= 0.8

    def test_strong_sell_signal(self) -> None:
        ob = OrderBookImbalance()
        result = OrderBookImbalanceResult(
            bid_ask_ratio=0.3,
            depth_imbalance=-0.54,
            bid_volume=3.0,
            ask_volume=10.0,
            level_imbalances={},
            imbalance_level=ImbalanceLevel.STRONG_SELL,
            spread=0.5,
            mid_price=100.25,
            num_levels=10,
            timestamp=datetime.now(UTC),
        )
        signal = ob.to_signal(result)
        assert signal.direction == SignalDirection.SELL
        assert signal.confidence >= 0.6

    def test_signal_confidence_capped_at_095(self) -> None:
        ob = OrderBookImbalance()
        result = OrderBookImbalanceResult(
            bid_ask_ratio=100.0,
            depth_imbalance=0.98,
            bid_volume=1000.0,
            ask_volume=1.0,
            level_imbalances={},
            imbalance_level=ImbalanceLevel.STRONG_BUY,
            spread=0.5,
            mid_price=100.25,
            num_levels=10,
            timestamp=datetime.now(UTC),
        )
        signal = ob.to_signal(result)
        assert signal.confidence <= 0.95

    def test_signal_metadata(self) -> None:
        ob = OrderBookImbalance()
        result = OrderBookImbalanceResult(
            bid_ask_ratio=1.5,
            depth_imbalance=0.2,
            bid_volume=15.0,
            ask_volume=10.0,
            level_imbalances={1: 0.2},
            imbalance_level=ImbalanceLevel.BUY,
            spread=0.5,
            mid_price=100.25,
            num_levels=5,
            timestamp=datetime.now(UTC),
        )
        signal = ob.to_signal(result)
        assert signal.metadata["indicator"] == "OrderBookImbalance"
        assert signal.metadata["bid_ask_ratio"] == 1.5
        assert signal.metadata["depth_imbalance"] == 0.2
        assert signal.metadata["imbalance_level"] == "buy"
        assert signal.metadata["spread"] == 0.5
        assert signal.metadata["mid_price"] == 100.25
        assert signal.metadata["num_levels"] == 5


# ---------------------------------------------------------------------------
# Multi-Level Depth Tests
# ---------------------------------------------------------------------------


class TestMultiLevelDepth:
    """Tests for L2 order book multi-level depth analysis."""

    def test_level1_imbalance_only_best(self) -> None:
        ob = OrderBookImbalance(num_levels=1)
        snap = OrderBookSnapshot(
            symbol="BTC/USDT",
            bids=_make_price_levels(100.0, "bid", 15, 2.0),
            asks=_make_price_levels(100.5, "ask", 15, 1.0),
            timestamp=1_700_000_000_000,
        )
        result = ob.analyze(snap)
        assert result.num_levels == 1
        assert result.bid_ask_ratio == pytest.approx(2.0)
        assert len(result.level_imbalances) == 1

    def test_deep_levels_aggregate_correctly(self) -> None:
        ob = OrderBookImbalance(num_levels=15)
        snap = OrderBookSnapshot(
            symbol="BTC/USDT",
            bids=_make_price_levels(100.0, "bid", 15, 2.0),
            asks=_make_price_levels(100.5, "ask", 15, 1.0),
            timestamp=1_700_000_000_000,
        )
        result = ob.analyze(snap)
        assert result.num_levels == 15
        assert result.bid_volume == pytest.approx(30.0)
        assert result.ask_volume == pytest.approx(15.0)
        assert result.bid_ask_ratio == pytest.approx(2.0)

    def test_varying_depth_per_level(self) -> None:
        """Test with different quantities at each level."""
        bids = [PriceLevel(price=100.0 - i * 0.5, quantity=10.0 - i) for i in range(15)]
        asks = [
            PriceLevel(price=100.5 + i * 0.5, quantity=5.0 + i * 0.5) for i in range(15)
        ]
        snap = OrderBookSnapshot(
            symbol="BTC/USDT",
            bids=bids,
            asks=asks,
            timestamp=1_700_000_000_000,
        )
        ob = OrderBookImbalance(num_levels=15)
        result = ob.analyze(snap)
        assert result.bid_volume > 0
        assert result.ask_volume > 0
        assert len(result.level_imbalances) == 15


# ---------------------------------------------------------------------------
# Spread and Mid-Price Tests
# ---------------------------------------------------------------------------


class TestSpreadAndMidPrice:
    """Tests for spread and mid-price computation."""

    def test_spread_calculation(
        self, indicator: OrderBookImbalance, balanced_snapshot: OrderBookSnapshot
    ) -> None:
        result = indicator.analyze(balanced_snapshot)
        # Best ask (100.5) - Best bid (100.0) = 0.5
        assert result.spread == pytest.approx(0.5)

    def test_mid_price_calculation(
        self, indicator: OrderBookImbalance, balanced_snapshot: OrderBookSnapshot
    ) -> None:
        result = indicator.analyze(balanced_snapshot)
        # (100.0 + 100.5) / 2 = 100.25
        assert result.mid_price == pytest.approx(100.25)

    def test_wider_spread(self) -> None:
        ob = OrderBookImbalance(num_levels=5)
        snap = OrderBookSnapshot(
            symbol="BTC/USDT",
            bids=[PriceLevel(price=99.0, quantity=1.0) for _ in range(10)],
            asks=[PriceLevel(price=101.0, quantity=1.0) for _ in range(10)],
            timestamp=1_700_000_000_000,
        )
        result = ob.analyze(snap)
        assert result.spread == pytest.approx(2.0)
        assert result.mid_price == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# Timestamp Tests
# ---------------------------------------------------------------------------


class TestTimestamps:
    """Tests for timestamp handling in results."""

    def test_result_has_timestamp(
        self, indicator: OrderBookImbalance, balanced_snapshot: OrderBookSnapshot
    ) -> None:
        result = indicator.analyze(balanced_snapshot)
        assert isinstance(result.timestamp, datetime)

    def test_signal_uses_result_timestamp(self) -> None:
        ob = OrderBookImbalance()
        ts = datetime(2026, 1, 15, 12, 0, 0)
        result = OrderBookImbalanceResult(
            bid_ask_ratio=1.0,
            depth_imbalance=0.0,
            bid_volume=10.0,
            ask_volume=10.0,
            level_imbalances={},
            imbalance_level=ImbalanceLevel.NEUTRAL,
            spread=0.5,
            mid_price=100.25,
            num_levels=10,
            timestamp=ts,
        )
        signal = ob.to_signal(result)
        assert signal.timestamp == ts
