"""Tests for RealDataValidator module."""

from datetime import UTC, datetime, timedelta

import pytest

from market_analysis.indicators.real_data_validator import (
    DriftStatus,
    EdgeCaseResult,
    EdgeCaseType,
    FeatureValidationResult,
    RealDataValidator,
)


class TestRealDataValidator:
    """Test suite for RealDataValidator class."""

    @pytest.fixture
    def validator(self):
        """Create RealDataValidator instance."""
        return RealDataValidator(
            drift_threshold=0.15,
            volatility_threshold=2.0,
            gap_tolerance_seconds=60,
        )

    @pytest.fixture
    def sample_snapshot(self):
        """Create sample market data snapshot."""
        from execution.paper.real_data_ingestion import (
            DataFreshness,
            DataSource,
            MarketDataSnapshot,
            OrderBookEntry,
            OrderBookSnapshot,
            TradeEntry,
        )

        return MarketDataSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime.now(UTC),
            order_book=OrderBookSnapshot(
                symbol="BTCUSDT",
                timestamp=datetime.now(UTC),
                bids=[
                    OrderBookEntry(price=50000, quantity=1.5, side="bid"),
                    OrderBookEntry(price=49999, quantity=2.0, side="bid"),
                ],
                asks=[
                    OrderBookEntry(price=50001, quantity=1.0, side="ask"),
                    OrderBookEntry(price=50002, quantity=2.5, side="ask"),
                ],
                source=DataSource.LIVE_BYBIT,
            ),
            recent_trades=[
                TradeEntry(
                    trade_id="1",
                    symbol="BTCUSDT",
                    side="buy",
                    price=50000.0,
                    quantity=1.0,
                    timestamp=datetime.now(UTC),
                ),
                TradeEntry(
                    trade_id="2",
                    symbol="BTCUSDT",
                    side="sell",
                    price=50001.0,
                    quantity=0.8,
                    timestamp=datetime.now(UTC) - timedelta(seconds=10),
                ),
                TradeEntry(
                    trade_id="3",
                    symbol="BTCUSDT",
                    side="buy",
                    price=49999.0,
                    quantity=1.2,
                    timestamp=datetime.now(UTC) - timedelta(seconds=20),
                ),
            ],
            source=DataSource.LIVE_BYBIT,
            freshness=DataFreshness.FRESH,
        )

    def test_validate_features_valid(self, validator, sample_snapshot):
        """Test feature validation with valid data."""
        result = validator.validate_features(sample_snapshot)

        assert result.is_valid is True
        assert len(result.features) > 0
        assert "bid_ask_spread" in result.features
        assert "order_book_imbalance" in result.features

    def test_validate_features_missing_orderbook(self, validator):
        """Test validation with missing order book."""
        from execution.paper.real_data_ingestion import (
            DataFreshness,
            DataSource,
            MarketDataSnapshot,
            TradeEntry,
        )

        snapshot = MarketDataSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime.now(UTC),
            recent_trades=[
                TradeEntry(
                    trade_id="1",
                    symbol="BTCUSDT",
                    side="buy",
                    price=50000.0,
                    quantity=1.0,
                    timestamp=datetime.now(UTC),
                )
            ],
            source=DataSource.LIVE_BYBIT,
            freshness=DataFreshness.FRESH,
        )

        result = validator.validate_features(snapshot)
        assert result.is_valid is False
        assert len(result.validation_errors) > 0

    def test_detect_feature_drift_stable(self, validator):
        """Test drift detection with stable features."""
        baseline = {"feature1": 0.5, "feature2": 0.3}
        current = {"feature1": 0.52, "feature2": 0.31}

        result = validator.detect_feature_drift(baseline, current)

        assert result.status == DriftStatus.STABLE
        assert result.drift_score < 0.15

    def test_detect_feature_drift_detected(self, validator):
        """Test drift detection with drifted features."""
        baseline = {"feature1": 0.5, "feature2": 0.3}
        current = {"feature1": 0.7, "feature2": 0.4}

        result = validator.detect_feature_drift(baseline, current)

        assert result.status == DriftStatus.DRIFT_DETECTED
        assert result.drift_score > 0.15

    def test_detect_feature_drift_unknown_baseline(self, validator):
        """Test drift detection without baseline."""
        result = validator.detect_feature_drift()

        assert result.status == DriftStatus.UNKNOWN

    def test_set_baseline(self, validator):
        """Test setting baseline features."""
        features = {"feature1": 0.5, "feature2": 0.3}
        validator.set_baseline(features)

        baseline = validator.get_baseline_features()
        assert baseline == features

    def test_clear_baseline(self, validator):
        """Test clearing baseline features."""
        validator.set_baseline({"feature1": 0.5})
        validator.clear_baseline()

        baseline = validator.get_baseline_features()
        assert len(baseline) == 0

    def test_normalize_data(self, validator, sample_snapshot):
        """Test data normalization."""
        normalized, status = validator.normalize_data(sample_snapshot)

        assert status.value == "normalized"
        assert normalized.order_book is not None

    def test_handle_edge_cases_none(self, validator):
        """Test edge case handling with normal data."""
        from execution.paper.real_data_ingestion import (
            DataFreshness,
            DataSource,
            MarketDataSnapshot,
            OrderBookEntry,
            OrderBookSnapshot,
            TradeEntry,
        )

        # Create snapshot with stable prices (small variation, no high volatility)
        trades = [
            TradeEntry(
                trade_id="1",
                symbol="BTCUSDT",
                side="buy",
                price=50000.0,
                quantity=1.0,
                timestamp=datetime.now(UTC),
            ),
            TradeEntry(
                trade_id="2",
                symbol="BTCUSDT",
                side="sell",
                price=50000.5,
                quantity=0.8,
                timestamp=datetime.now(UTC) - timedelta(seconds=10),
            ),
            TradeEntry(
                trade_id="3",
                symbol="BTCUSDT",
                side="buy",
                price=50000.3,
                quantity=1.2,
                timestamp=datetime.now(UTC) - timedelta(seconds=20),
            ),
        ]

        snapshot = MarketDataSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime.now(UTC),
            order_book=OrderBookSnapshot(
                symbol="BTCUSDT",
                timestamp=datetime.now(UTC),
                bids=[
                    OrderBookEntry(price=50000, quantity=1.5, side="bid"),
                    OrderBookEntry(price=49999, quantity=2.0, side="bid"),
                ],
                asks=[
                    OrderBookEntry(price=50001, quantity=1.0, side="ask"),
                    OrderBookEntry(price=50002, quantity=2.5, side="ask"),
                ],
            ),
            recent_trades=trades,
            source=DataSource.LIVE_BYBIT,
            freshness=DataFreshness.FRESH,
        )

        result = validator.handle_edge_cases(snapshot)

        assert result.edge_case_type == EdgeCaseType.NONE
        assert result.severity == "low"

    def test_handle_edge_cases_high_volatility(self, validator):
        """Test high volatility detection."""
        from execution.paper.real_data_ingestion import (
            DataFreshness,
            DataSource,
            MarketDataSnapshot,
            OrderBookEntry,
            OrderBookSnapshot,
            TradeEntry,
        )

        # Create trades with extreme price variation (erratic movement)
        trades = [
            TradeEntry(
                trade_id="0",
                symbol="BTCUSDT",
                side="buy",
                price=50000.0,
                quantity=1.0,
                timestamp=datetime.now(UTC),
            ),
            TradeEntry(
                trade_id="1",
                symbol="BTCUSDT",
                side="sell",
                price=48000.0,  # Big drop
                quantity=1.0,
                timestamp=datetime.now(UTC) - timedelta(seconds=5),
            ),
            TradeEntry(
                trade_id="2",
                symbol="BTCUSDT",
                side="buy",
                price=52000.0,  # Big rise
                quantity=1.0,
                timestamp=datetime.now(UTC) - timedelta(seconds=10),
            ),
            TradeEntry(
                trade_id="3",
                symbol="BTCUSDT",
                side="sell",
                price=49000.0,  # Another drop
                quantity=1.0,
                timestamp=datetime.now(UTC) - timedelta(seconds=15),
            ),
            TradeEntry(
                trade_id="4",
                symbol="BTCUSDT",
                side="buy",
                price=51000.0,
                quantity=1.0,
                timestamp=datetime.now(UTC) - timedelta(seconds=20),
            ),
        ]

        snapshot = MarketDataSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime.now(UTC),
            order_book=OrderBookSnapshot(
                symbol="BTCUSDT",
                timestamp=datetime.now(UTC),
                bids=[OrderBookEntry(price=50000, quantity=1.0, side="bid")],
                asks=[OrderBookEntry(price=55000, quantity=1.0, side="ask")],
            ),
            recent_trades=trades,
            source=DataSource.LIVE_BYBIT,
            freshness=DataFreshness.FRESH,
        )

        result = validator.handle_edge_cases(snapshot)

        assert result.edge_case_type == EdgeCaseType.HIGH_VOLATILITY
        assert result.severity in ["medium", "high"]

    def test_handle_edge_cases_stale_data(self, validator):
        """Test stale data detection."""
        from execution.paper.real_data_ingestion import (
            DataFreshness,
            DataSource,
            MarketDataSnapshot,
            OrderBookEntry,
            OrderBookSnapshot,
            TradeEntry,
        )

        snapshot = MarketDataSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime.now(UTC) - timedelta(seconds=120),
            order_book=OrderBookSnapshot(
                symbol="BTCUSDT",
                timestamp=datetime.now(UTC) - timedelta(seconds=120),
                bids=[OrderBookEntry(price=50000, quantity=1.0, side="bid")],
                asks=[OrderBookEntry(price=50001, quantity=1.0, side="ask")],
            ),
            recent_trades=[
                TradeEntry(
                    trade_id="1",
                    symbol="BTCUSDT",
                    side="buy",
                    price=50000.0,
                    quantity=1.0,
                    timestamp=datetime.now(UTC) - timedelta(seconds=120),
                )
            ],
            source=DataSource.LIVE_BYBIT,
            freshness=DataFreshness.STALE,
        )

        result = validator.handle_edge_cases(snapshot)

        assert result.edge_case_type == EdgeCaseType.STALE_DATA

    def test_extract_order_book_features(self, validator):
        """Test order book feature extraction."""
        from execution.paper.real_data_ingestion import (
            OrderBookEntry,
            OrderBookSnapshot,
        )

        order_book = OrderBookSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime.now(UTC),
            bids=[
                OrderBookEntry(price=50000, quantity=1.5, side="bid"),
                OrderBookEntry(price=49999, quantity=2.0, side="bid"),
            ],
            asks=[
                OrderBookEntry(price=50001, quantity=1.0, side="ask"),
                OrderBookEntry(price=50002, quantity=2.5, side="ask"),
            ],
        )

        features = validator._extract_order_book_features(order_book)

        assert "bid_ask_spread" in features
        assert "order_book_imbalance" in features
        assert "mid_price" in features
        assert features["bid_ask_spread"] > 0

    def test_extract_trade_features(self, validator):
        """Test trade feature extraction."""
        from execution.paper.real_data_ingestion import TradeEntry

        trades = [
            TradeEntry(
                trade_id="1",
                symbol="BTCUSDT",
                side="buy",
                price=50000.0,
                quantity=1.0,
                timestamp=datetime.now(UTC),
            ),
            TradeEntry(
                trade_id="2",
                symbol="BTCUSDT",
                side="sell",
                price=50001.0,
                quantity=0.8,
                timestamp=datetime.now(UTC) - timedelta(seconds=10),
            ),
            TradeEntry(
                trade_id="3",
                symbol="BTCUSDT",
                side="buy",
                price=49999.0,
                quantity=1.2,
                timestamp=datetime.now(UTC) - timedelta(seconds=20),
            ),
        ]

        features = validator._extract_trade_features(trades)

        assert "trade_rate" in features
        assert "buy_sell_ratio" in features
        assert "avg_trade_size" in features
        assert features["buy_sell_ratio"] != 0

    def test_is_feature_valid(self, validator):
        """Test feature validity checking."""
        assert validator._is_feature_valid("bid_ask_spread", 0.001) is True
        assert validator._is_feature_valid("bid_ask_spread", 0.5) is False
        assert validator._is_feature_valid("order_book_imbalance", 0.0) is True
        assert validator._is_feature_valid("order_book_imbalance", 2.0) is False
        assert validator._is_feature_valid("unknown_feature", 1000.0) is True

    def test_detect_data_gaps(self, validator, sample_snapshot):
        """Test data gap detection."""
        gap = validator._detect_data_gaps(sample_snapshot)
        # Sample snapshot has recent trades, should have minimal or no gap
        assert gap is None or gap <= 60

    def test_detect_low_liquidity(self, validator):
        """Test low liquidity detection."""
        from execution.paper.real_data_ingestion import (
            MarketDataSnapshot,
            OrderBookEntry,
            OrderBookSnapshot,
        )

        snapshot = MarketDataSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime.now(UTC),
            order_book=OrderBookSnapshot(
                symbol="BTCUSDT",
                timestamp=datetime.now(UTC),
                bids=[OrderBookEntry(price=50000, quantity=0.001, side="bid")],
                asks=[OrderBookEntry(price=50001, quantity=0.001, side="ask")],
            ),
            recent_trades=[],
        )

        result = validator._detect_low_liquidity(snapshot)
        assert result is not None
        assert result < 1.0

    def test_detect_price_spikes(self, validator):
        """Test price spike detection."""
        from execution.paper.real_data_ingestion import (
            MarketDataSnapshot,
            OrderBookEntry,
            OrderBookSnapshot,
            TradeEntry,
        )

        trades = [
            TradeEntry(
                trade_id=f"{i}",
                symbol="BTCUSDT",
                side="buy",
                price=50000.0,
                quantity=1.0,
                timestamp=datetime.now(UTC) - timedelta(seconds=i * 5),
            )
            for i in range(5)
        ]
        # Add a spike
        trades.append(
            TradeEntry(
                trade_id="spike",
                symbol="BTCUSDT",
                side="buy",
                price=60000.0,  # 20% spike
                quantity=1.0,
                timestamp=datetime.now(UTC),
            )
        )

        snapshot = MarketDataSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime.now(UTC),
            order_book=OrderBookSnapshot(
                symbol="BTCUSDT",
                timestamp=datetime.now(UTC),
                bids=[OrderBookEntry(price=50000, quantity=1.0, side="bid")],
                asks=[OrderBookEntry(price=50001, quantity=1.0, side="ask")],
            ),
            recent_trades=trades,
        )

        spike = validator._detect_price_spikes(snapshot)
        assert spike is not None
        assert spike > 0.05


class TestEdgeCaseResult:
    """Test suite for EdgeCaseResult dataclass."""

    def test_edge_case_result_creation(self):
        """Test creating EdgeCaseResult."""
        result = EdgeCaseResult(
            edge_case_type=EdgeCaseType.DATA_GAP,
            severity="medium",
            details={"gap_seconds": 120},
            affected_features=["price", "momentum"],
        )

        assert result.edge_case_type == EdgeCaseType.DATA_GAP
        assert result.severity == "medium"
        assert result.details["gap_seconds"] == 120
        assert len(result.affected_features) == 2


class TestFeatureValidationResult:
    """Test suite for FeatureValidationResult dataclass."""

    def test_feature_validation_result_creation(self):
        """Test creating FeatureValidationResult."""
        result = FeatureValidationResult(
            is_valid=True,
            features={"feature1": 0.5, "feature2": 0.3},
            validation_errors=[],
            warnings=["Minor volatility detected"],
        )

        assert result.is_valid is True
        assert len(result.features) == 2
        assert len(result.warnings) == 1
        assert len(result.validation_errors) == 0
