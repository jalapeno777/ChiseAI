"""Tests for Signal Outcome Matcher.

Tests the signal-to-outcome matching service including:
- Match outcomes to signals
- Confidence calculation
- Time window handling
- Database updates
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from src.ml.feedback.signal_outcome_matcher import (
    DEFAULT_MATCH_WINDOWS,
    MatcherMetrics,
    MatchMetadata,
    SignalMatcherConfig,
    SignalOutcomeMatcher,
)
from src.ml.models.signal_outcome import (
    OutcomeType,
    SignalOutcome,
)


class TestSignalMatcherConfig:
    """Tests for SignalMatcherConfig."""

    def test_default_creation(self):
        """Test creating config with defaults."""
        config = SignalMatcherConfig()

        assert config.default_match_window_hours == 24.0
        assert config.min_confidence_threshold == 0.95
        assert config.symbol_match_weight == 0.3
        assert config.direction_match_weight == 0.3
        assert config.time_proximity_weight == 0.4
        assert config.enable_influxdb_export is True

    def test_timeframe_windows_merged(self):
        """Test that custom windows are merged with defaults."""
        config = SignalMatcherConfig(
            timeframe_windows={"1h": 48.0}  # Override 1h window
        )

        # Should have default windows
        assert "1m" in config.timeframe_windows
        assert "5m" in config.timeframe_windows

        # Should have overridden value
        assert config.timeframe_windows["1h"] == 48.0

        # Should have other defaults
        assert config.timeframe_windows["4h"] == 72.0

    def test_get_window_for_timeframe(self):
        """Test getting window for specific timeframe."""
        config = SignalMatcherConfig()

        assert config.get_window_for_timeframe("1m") == 0.5
        assert config.get_window_for_timeframe("5m") == 2.0
        assert config.get_window_for_timeframe("15m") == 6.0
        assert config.get_window_for_timeframe("1h") == 24.0
        assert config.get_window_for_timeframe("4h") == 72.0
        assert config.get_window_for_timeframe("1d") == 168.0

    def test_get_window_default(self):
        """Test default window for unknown timeframe."""
        config = SignalMatcherConfig(default_match_window_hours=12.0)

        assert config.get_window_for_timeframe("unknown") == 12.0
        assert config.get_window_for_timeframe(None) == 12.0


class TestMatchMetadata:
    """Tests for MatchMetadata."""

    def test_default_creation(self):
        """Test creating metadata with defaults."""
        metadata = MatchMetadata()

        assert metadata.matched_signal_id is None
        assert metadata.match_confidence == 0.0
        assert metadata.match_method == ""
        assert metadata.symbol_match is False
        assert metadata.direction_match is False

    def test_to_dict(self):
        """Test conversion to dictionary."""
        signal_id = uuid4()
        metadata = MatchMetadata(
            matched_signal_id=signal_id,
            match_confidence=0.95,
            match_method="fuzzy",
            timeframe="1h",
            window_hours=24.0,
            symbol_match=True,
            direction_match=True,
            time_diff_seconds=300.0,
        )

        data = metadata.to_dict()

        assert data["matched_signal_id"] == str(signal_id)
        assert data["match_confidence"] == 0.95
        assert data["match_method"] == "fuzzy"
        assert data["timeframe"] == "1h"
        assert data["symbol_match"] is True
        assert data["direction_match"] is True


class TestMatcherMetrics:
    """Tests for MatcherMetrics."""

    def test_default_creation(self):
        """Test creating metrics with defaults."""
        metrics = MatcherMetrics()

        assert metrics.outcomes_processed == 0
        assert metrics.outcomes_matched == 0
        assert metrics.outcomes_unmatched == 0
        assert metrics.high_confidence_matches == 0
        assert metrics.avg_confidence == 0.0

    def test_record_match(self):
        """Test recording a match."""
        metrics = MatcherMetrics()

        metrics.record_match(confidence=0.97, latency_seconds=0.5)

        assert metrics.outcomes_matched == 1
        assert metrics.avg_confidence == 0.97
        assert metrics.avg_match_latency_seconds == 0.5
        assert metrics.high_confidence_matches == 1

    def test_record_multiple_matches(self):
        """Test recording multiple matches."""
        metrics = MatcherMetrics()

        metrics.record_match(confidence=0.90, latency_seconds=0.5)
        metrics.record_match(confidence=0.98, latency_seconds=0.3)
        metrics.record_match(confidence=0.96, latency_seconds=0.4)

        assert metrics.outcomes_matched == 3
        assert metrics.avg_confidence == pytest.approx(0.947, rel=1e-2)
        assert metrics.avg_match_latency_seconds == pytest.approx(0.4, rel=1e-2)
        assert metrics.high_confidence_matches == 2  # 0.98 and 0.96

    def test_record_unmatched(self):
        """Test recording unmatched outcome."""
        metrics = MatcherMetrics()

        metrics.record_unmatched()

        assert metrics.outcomes_unmatched == 1

    def test_record_error(self):
        """Test recording an error."""
        metrics = MatcherMetrics()

        metrics.record_error()

        assert metrics.errors_encountered == 1

    def test_to_dict(self):
        """Test conversion to dictionary."""
        metrics = MatcherMetrics()
        metrics.outcomes_processed = 100
        metrics.outcomes_matched = 95
        metrics.avg_confidence = 0.96

        data = metrics.to_dict()

        assert data["outcomes_processed"] == 100
        assert data["outcomes_matched"] == 95
        assert data["avg_confidence"] == 0.96


class TestSignalOutcomeMatcher:
    """Tests for SignalOutcomeMatcher."""

    @pytest.fixture
    def config(self):
        """Create test config."""
        return SignalMatcherConfig(
            min_confidence_threshold=0.95,
            batch_size=10,
            enable_influxdb_export=False,
        )

    @pytest.fixture
    def mock_db_pool(self):
        """Create mock database pool."""
        pool = AsyncMock()
        conn = AsyncMock()
        pool.acquire.return_value.__aenter__.return_value = conn
        return pool

    @pytest.fixture
    def mock_signal_tracker(self):
        """Create mock signal tracker."""
        tracker = AsyncMock()
        tracker.get_signal_history.return_value = []
        return tracker

    def test_initialization(self, config):
        """Test matcher initialization."""
        matcher = SignalOutcomeMatcher(config=config)

        assert matcher.config == config
        assert matcher.db_pool is None
        assert matcher.influxdb is None
        assert matcher.signal_tracker is None

    def test_initialization_with_deps(self, config, mock_db_pool, mock_signal_tracker):
        """Test initialization with dependencies."""
        matcher = SignalOutcomeMatcher(
            config=config,
            db_pool=mock_db_pool,
            signal_tracker=mock_signal_tracker,
        )

        assert matcher.db_pool == mock_db_pool
        assert matcher.signal_tracker == mock_signal_tracker

    @pytest.mark.asyncio
    async def test_match_outcome_no_tracker(self, config):
        """Test matching without signal tracker."""
        matcher = SignalOutcomeMatcher(config=config)

        outcome = SignalOutcome(
            order_id="test-123",
            symbol="BTCUSDT",
            fill_price=Decimal("50000"),
        )

        result = await matcher.match_outcome(outcome)

        assert result.matched is False
        # Without tracker, it tries order_id matching first which returns "no_order_id"
        assert result.match_method in ["no_tracker", "no_order_id"]
        assert matcher.metrics.outcomes_processed == 1
        assert matcher.metrics.outcomes_unmatched == 1

    @pytest.mark.asyncio
    async def test_match_outcome_no_signals(self, config, mock_signal_tracker):
        """Test matching when no signals found."""
        mock_signal_tracker.get_signal_history.return_value = []

        matcher = SignalOutcomeMatcher(
            config=config,
            signal_tracker=mock_signal_tracker,
        )

        outcome = SignalOutcome(
            order_id="test-123",
            symbol="BTCUSDT",
            side="Buy",
            fill_price=Decimal("50000"),
            fill_timestamp=datetime.now(UTC),
        )

        result = await matcher.match_outcome(outcome)

        assert result.matched is False
        assert result.match_method == "no_signals"
        assert matcher.metrics.outcomes_unmatched == 1

    @pytest.mark.asyncio
    async def test_match_confidence_calculation(self, config, mock_signal_tracker):
        """Test confidence calculation."""
        # Create mock signal
        mock_signal = MagicMock()
        mock_signal.signal_id = str(uuid4())
        mock_signal.token = "BTC"
        mock_signal.direction.value = "LONG"
        mock_signal.timestamp = int(
            (datetime.now(UTC) - timedelta(minutes=30)).timestamp() * 1000
        )

        mock_signal_tracker.get_signal_history.return_value = [
            MagicMock(signal=mock_signal, outcome=None)
        ]

        matcher = SignalOutcomeMatcher(
            config=config,
            signal_tracker=mock_signal_tracker,
        )

        outcome = SignalOutcome(
            symbol="BTCUSDT",
            side="Buy",
            fill_timestamp=datetime.now(UTC),
        )

        result = await matcher.match_outcome(outcome)

        # Should have high confidence (symbol match + direction match + time proximity)
        assert result.confidence > 0.0
        assert result.confidence <= 1.0

    @pytest.mark.asyncio
    async def test_match_high_confidence(self, config, mock_signal_tracker):
        """Test high confidence match (>= 0.95)."""
        # Create mock signal with perfect match
        mock_signal = MagicMock()
        mock_signal.signal_id = str(uuid4())
        mock_signal.token = "BTC"
        mock_signal.direction.value = "LONG"
        mock_signal.timestamp = int(
            (datetime.now(UTC) - timedelta(minutes=5)).timestamp() * 1000
        )

        mock_signal_tracker.get_signal_history.return_value = [
            MagicMock(signal=mock_signal, outcome=None)
        ]

        # Use lower threshold for this test
        config.min_confidence_threshold = 0.5
        matcher = SignalOutcomeMatcher(
            config=config,
            signal_tracker=mock_signal_tracker,
        )

        outcome = SignalOutcome(
            symbol="BTCUSDT",
            side="Buy",
            fill_timestamp=datetime.now(UTC),
        )

        result = await matcher.match_outcome(outcome)

        assert result.matched is True
        assert result.signal_id == UUID(mock_signal.signal_id)
        assert matcher.metrics.outcomes_matched == 1

    @pytest.mark.asyncio
    async def test_match_below_threshold(self, config, mock_signal_tracker):
        """Test match below confidence threshold."""
        # Create mock signal with poor match (wrong symbol)
        mock_signal = MagicMock()
        mock_signal.signal_id = str(uuid4())
        mock_signal.token = "ETH"  # Different from outcome
        mock_signal.direction.value = "LONG"
        mock_signal.timestamp = int(
            (datetime.now(UTC) - timedelta(hours=2)).timestamp() * 1000
        )

        mock_signal_tracker.get_signal_history.return_value = [
            MagicMock(signal=mock_signal, outcome=None)
        ]

        matcher = SignalOutcomeMatcher(
            config=config,
            signal_tracker=mock_signal_tracker,
        )

        outcome = SignalOutcome(
            symbol="BTCUSDT",
            side="Buy",
            fill_timestamp=datetime.now(UTC),
        )

        result = await matcher.match_outcome(outcome)

        assert result.matched is False
        assert result.match_method == "below_threshold"
        assert matcher.metrics.outcomes_unmatched == 1

    @pytest.mark.asyncio
    async def test_process_pending_outcomes_no_db(self, config):
        """Test processing pending outcomes without database."""
        matcher = SignalOutcomeMatcher(config=config)

        results = await matcher.process_pending_outcomes()

        assert results == []

    @pytest.mark.asyncio
    async def test_get_match_statistics_no_db(self, config):
        """Test getting statistics without database."""
        matcher = SignalOutcomeMatcher(config=config)

        stats = await matcher.get_match_statistics()

        assert stats == {}


class TestConfidenceCalculation:
    """Tests for confidence calculation logic."""

    @pytest.fixture
    def matcher(self):
        """Create matcher for testing."""
        config = SignalMatcherConfig(
            symbol_match_weight=0.3,
            direction_match_weight=0.3,
            time_proximity_weight=0.4,
        )
        return SignalOutcomeMatcher(config=config)

    def test_perfect_match(self, matcher):
        """Test confidence with perfect match."""
        outcome = SignalOutcome(
            symbol="BTCUSDT",
            side="Buy",
            fill_timestamp=datetime.now(UTC),
        )

        mock_signal = MagicMock()
        mock_signal.token = "BTC"
        mock_signal.direction.value = "LONG"
        mock_signal.timestamp = int(
            (datetime.now(UTC) - timedelta(minutes=5)).timestamp() * 1000
        )

        confidence, metadata = matcher._calculate_match_confidence(
            outcome, mock_signal, window_hours=24.0
        )

        assert confidence == 1.0
        assert metadata.symbol_match is True
        assert metadata.direction_match is True

    def test_symbol_mismatch(self, matcher):
        """Test confidence with symbol mismatch."""
        outcome = SignalOutcome(
            symbol="BTCUSDT",
            side="Buy",
            fill_timestamp=datetime.now(UTC),
        )

        mock_signal = MagicMock()
        mock_signal.token = "ETH"  # Wrong symbol
        mock_signal.direction.value = "LONG"
        mock_signal.timestamp = int(
            (datetime.now(UTC) - timedelta(minutes=5)).timestamp() * 1000
        )

        confidence, metadata = matcher._calculate_match_confidence(
            outcome, mock_signal, window_hours=24.0
        )

        # Should only have direction + time (0.3 + 0.4 = 0.7)
        assert confidence == pytest.approx(0.7, rel=1e-2)
        assert metadata.symbol_match is False
        assert metadata.direction_match is True

    def test_direction_mismatch(self, matcher):
        """Test confidence with direction mismatch."""
        outcome = SignalOutcome(
            symbol="BTCUSDT",
            side="Sell",  # Selling (SHORT)
            fill_timestamp=datetime.now(UTC),
        )

        mock_signal = MagicMock()
        mock_signal.token = "BTC"
        mock_signal.direction.value = "LONG"  # But signal is LONG
        mock_signal.timestamp = int(
            (datetime.now(UTC) - timedelta(minutes=5)).timestamp() * 1000
        )

        confidence, metadata = matcher._calculate_match_confidence(
            outcome, mock_signal, window_hours=24.0
        )

        # Should only have symbol + time (0.3 + 0.4 = 0.7)
        assert confidence == pytest.approx(0.7, rel=1e-2)
        assert metadata.symbol_match is True
        assert metadata.direction_match is False

    def test_time_decay(self, matcher):
        """Test confidence with time decay."""
        outcome = SignalOutcome(
            symbol="BTCUSDT",
            side="Buy",
            fill_timestamp=datetime.now(UTC),
        )

        mock_signal = MagicMock()
        mock_signal.token = "BTC"
        mock_signal.direction.value = "LONG"
        # Signal is 50% through the window
        mock_signal.timestamp = int(
            (datetime.now(UTC) - timedelta(hours=12)).timestamp() * 1000
        )

        confidence, metadata = matcher._calculate_match_confidence(
            outcome, mock_signal, window_hours=24.0
        )

        # Should have symbol (0.3) + direction (0.3) + partial time
        # Time score = 1 - 0.5 = 0.5, so 0.4 * 0.5 = 0.2
        # Total = 0.3 + 0.3 + 0.2 = 0.8
        assert confidence == pytest.approx(0.8, rel=1e-2)


class TestTimeWindowHandling:
    """Tests for time window handling per timeframe."""

    @pytest.fixture
    def mock_signal_tracker(self):
        """Create mock signal tracker."""
        tracker = AsyncMock()
        tracker.get_signal_history.return_value = []
        return tracker

    def test_default_windows(self):
        """Test default timeframe windows."""
        assert DEFAULT_MATCH_WINDOWS["1m"] == 0.5  # 30min
        assert DEFAULT_MATCH_WINDOWS["5m"] == 2.0  # 2h
        assert DEFAULT_MATCH_WINDOWS["15m"] == 6.0  # 6h
        assert DEFAULT_MATCH_WINDOWS["1h"] == 24.0  # 24h
        assert DEFAULT_MATCH_WINDOWS["4h"] == 72.0  # 3d
        assert DEFAULT_MATCH_WINDOWS["1d"] == 168.0  # 7d

    @pytest.mark.asyncio
    async def test_timeframe_specific_window(self, mock_signal_tracker):
        """Test using timeframe-specific window."""
        config = SignalMatcherConfig()
        matcher = SignalOutcomeMatcher(
            config=config,
            signal_tracker=mock_signal_tracker,
        )

        outcome = SignalOutcome(
            symbol="BTCUSDT",
            side="Buy",
            fill_timestamp=datetime.now(UTC),
        )

        # Match with 1m timeframe
        await matcher.match_outcome(outcome, timeframe="1m")

        # Should use 0.5h window
        call_args = mock_signal_tracker.get_signal_history.call_args
        start_time = call_args.kwargs["start_time"]
        end_time = call_args.kwargs["end_time"]

        window_hours = (end_time - start_time) / (3600 * 1000)
        assert window_hours == pytest.approx(0.5, rel=1e-2)


class TestDatabaseOperations:
    """Tests for database operations."""

    @pytest.fixture
    def mock_db_pool(self):
        """Create mock database pool."""
        pool = AsyncMock()
        conn = AsyncMock()
        pool.acquire.return_value.__aenter__.return_value = conn
        return pool

    @pytest.mark.asyncio
    async def test_row_to_outcome(self, mock_db_pool):
        """Test converting database row to outcome."""
        matcher = SignalOutcomeMatcher(db_pool=mock_db_pool)

        # Create mock row
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda self, key: {
            "outcome_id": str(uuid4()),
            "order_id": "test-order",
            "symbol": "BTCUSDT",
            "side": "Buy",
            "fill_price": "50000.50",
            "fill_quantity": "0.1",
            "fill_timestamp": datetime.now(UTC),
            "outcome_type": "tp_hit",
            "metadata": {"key": "value"},
        }.get(key)

        # Patch the row to work with attribute access
        mock_row = {
            "outcome_id": str(uuid4()),
            "order_id": "test-order",
            "symbol": "BTCUSDT",
            "side": "Buy",
            "fill_price": "50000.50",
            "fill_quantity": "0.1",
            "fill_timestamp": datetime.now(UTC),
            "outcome_type": "tp_hit",
            "metadata": {"key": "value"},
        }

        outcome = matcher._row_to_outcome(mock_row)

        assert outcome.order_id == "test-order"
        assert outcome.symbol == "BTCUSDT"
        assert outcome.side == "Buy"
        assert outcome.fill_price == Decimal("50000.50")
        assert outcome.outcome_type == OutcomeType.TP_HIT


class TestOutcomeTypes:
    """Tests for different outcome types."""

    @pytest.mark.parametrize(
        "outcome_type",
        [
            OutcomeType.TP_HIT,
            OutcomeType.SL_HIT,
            OutcomeType.MANUAL_CLOSE,
            OutcomeType.EXPIRED,
        ],
    )
    def test_outcome_type_values(self, outcome_type):
        """Test outcome type enum values."""
        assert isinstance(outcome_type.value, str)

    def test_all_outcome_types(self):
        """Test all required outcome types exist."""
        assert OutcomeType.TP_HIT.value == "tp_hit"
        assert OutcomeType.SL_HIT.value == "sl_hit"
        assert OutcomeType.MANUAL_CLOSE.value == "manual_close"
        assert OutcomeType.EXPIRED.value == "expired"


class TestIntegration:
    """Integration-style tests."""

    @pytest.mark.asyncio
    async def test_full_match_flow(self):
        """Test full matching flow with mocked dependencies."""
        # Create mock signal
        signal_id = str(uuid4())
        mock_signal = MagicMock()
        mock_signal.signal_id = signal_id
        mock_signal.token = "BTC"
        mock_signal.direction.value = "LONG"
        mock_signal.timestamp = int(
            (datetime.now(UTC) - timedelta(minutes=10)).timestamp() * 1000
        )

        mock_signal_tracker = AsyncMock()
        mock_signal_tracker.get_signal_history.return_value = [
            MagicMock(signal=mock_signal, outcome=None)
        ]

        config = SignalMatcherConfig(
            min_confidence_threshold=0.5,  # Lower for test
            enable_influxdb_export=False,
        )

        matcher = SignalOutcomeMatcher(
            config=config,
            signal_tracker=mock_signal_tracker,
        )

        outcome = SignalOutcome(
            order_id="test-order-123",
            symbol="BTCUSDT",
            side="Buy",
            fill_price=Decimal("50000"),
            fill_quantity=Decimal("0.1"),
            fill_timestamp=datetime.now(UTC),
            outcome_type=OutcomeType.TP_HIT,
        )

        result = await matcher.match_outcome(outcome)

        assert result.matched is True
        assert result.signal_id == UUID(signal_id)
        assert result.confidence > 0.5
        assert matcher.metrics.outcomes_matched == 1

    @pytest.mark.asyncio
    async def test_batch_processing(self):
        """Test batch processing of multiple outcomes."""
        signal_id = str(uuid4())
        mock_signal = MagicMock()
        mock_signal.signal_id = signal_id
        mock_signal.token = "BTC"
        mock_signal.direction.value = "LONG"
        mock_signal.timestamp = int(
            (datetime.now(UTC) - timedelta(minutes=10)).timestamp() * 1000
        )

        mock_signal_tracker = AsyncMock()
        mock_signal_tracker.get_signal_history.return_value = [
            MagicMock(signal=mock_signal, outcome=None)
        ]

        # Create mock database with pending outcomes
        mock_rows = []
        for i in range(5):
            mock_rows.append(
                {
                    "outcome_id": str(uuid4()),
                    "order_id": f"order-{i}",
                    "symbol": "BTCUSDT",
                    "side": "Buy",
                    "fill_price": "50000",
                    "fill_quantity": "0.1",
                    "fill_timestamp": datetime.now(UTC) - timedelta(minutes=10),
                    "outcome_type": "tp_hit",
                    "metadata": {},
                }
            )

        # Create proper async context manager mock for connection
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=mock_rows)
        mock_conn.execute = AsyncMock(return_value=None)

        # Create proper async context manager for pool.acquire()
        mock_acquire_cm = AsyncMock()
        mock_acquire_cm.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_acquire_cm.__aexit__ = AsyncMock(return_value=None)

        mock_db_pool = AsyncMock()
        mock_db_pool.acquire = MagicMock(return_value=mock_acquire_cm)

        config = SignalMatcherConfig(
            min_confidence_threshold=0.5,
            batch_size=10,
            enable_influxdb_export=False,
        )

        matcher = SignalOutcomeMatcher(
            config=config,
            db_pool=mock_db_pool,
            signal_tracker=mock_signal_tracker,
        )

        results = await matcher.process_pending_outcomes(limit=5)

        assert len(results) == 5
        assert matcher.metrics.outcomes_processed == 5
