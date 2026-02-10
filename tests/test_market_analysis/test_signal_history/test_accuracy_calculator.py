"""Tests for accuracy calculator."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from market_analysis.signal_history.accuracy_calculator import (
    DEFAULT_CONFIDENCE_BUCKETS,
    AccuracyMetrics,
    AccuracyReport,
    PredictionAccuracyCalculator,
    get_confidence_bucket,
)
from market_analysis.signal_storage.models import (
    OutcomeRecord,
    SignalDirection,
    SignalRecord,
    SignalWithOutcome,
)


@pytest.fixture
def mock_storage():
    """Create a mock storage backend."""
    storage = MagicMock()
    storage.calculate_prediction_accuracy = AsyncMock(
        return_value={
            "total_signals": 10,
            "resolved_signals": 8,
            "wins": 6,
            "losses": 2,
            "accuracy": 0.75,
            "win_rate": 0.75,
            "avg_pnl": 50.0,
            "total_pnl": 400.0,
            "avg_duration_hours": 2.5,
        }
    )
    storage.query_signals_with_outcomes = AsyncMock(return_value=[])
    return storage


@pytest.fixture
def calculator(mock_storage):
    """Create a PredictionAccuracyCalculator with mock storage."""
    return PredictionAccuracyCalculator(storage=mock_storage)


class TestGetConfidenceBucket:
    """Tests for get_confidence_bucket helper."""

    def test_confidence_bucket_low(self):
        """Test bucket for low confidence."""
        assert get_confidence_bucket(0.05) == "0-10"
        assert get_confidence_bucket(0.09) == "0-10"

    def test_confidence_bucket_mid(self):
        """Test bucket for mid confidence."""
        assert get_confidence_bucket(0.45) == "40-50"
        assert get_confidence_bucket(0.50) == "50-60"

    def test_confidence_bucket_high(self):
        """Test bucket for high confidence."""
        assert get_confidence_bucket(0.75) == "70-80"
        assert get_confidence_bucket(0.95) == "90-100"


class TestAccuracyMetrics:
    """Tests for AccuracyMetrics dataclass."""

    def test_basic_creation(self):
        """Test basic metrics creation."""
        metrics = AccuracyMetrics(
            total_signals=10,
            resolved_signals=8,
            wins=6,
            losses=2,
            total_pnl=400.0,
            avg_duration_hours=2.5,
        )

        assert metrics.total_signals == 10
        assert metrics.resolved_signals == 8
        assert metrics.wins == 6
        assert metrics.losses == 2
        assert metrics.accuracy == 0.75  # 6/8
        assert metrics.win_rate == 0.75
        assert metrics.avg_pnl == 50.0  # 400/8

    def test_zero_resolved(self):
        """Test metrics with zero resolved signals."""
        metrics = AccuracyMetrics(total_signals=0, resolved_signals=0)

        assert metrics.accuracy == 0.0
        assert metrics.avg_pnl == 0.0

    def test_to_dict(self):
        """Test conversion to dictionary."""
        metrics = AccuracyMetrics(
            total_signals=10,
            resolved_signals=8,
            wins=6,
            losses=2,
            total_pnl=400.0,
            signal_type="LONG_rsi",
            confidence_bucket="70-80",
        )

        data = metrics.to_dict()
        assert data["total_signals"] == 10
        assert data["accuracy"] == 0.75
        assert data["signal_type"] == "LONG_rsi"
        assert data["confidence_bucket"] == "70-80"


class TestAccuracyReport:
    """Tests for AccuracyReport dataclass."""

    def test_basic_creation(self):
        """Test basic report creation."""
        overall = AccuracyMetrics(total_signals=100, resolved_signals=80, wins=60)
        by_type = {
            "LONG_rsi": AccuracyMetrics(total_signals=50, resolved_signals=40, wins=30)
        }

        report = AccuracyReport(
            overall=overall,
            by_signal_type=by_type,
            timeframe={"start_time": 1234567890000, "end_time": 1234567950000},
        )

        assert report.overall.total_signals == 100
        assert "LONG_rsi" in report.by_signal_type

    def test_get_best_performing(self):
        """Test getting best performing configurations."""
        by_combo = {
            "LONG_rsi|70-80": AccuracyMetrics(
                total_signals=20, resolved_signals=15, wins=12, accuracy=0.80
            ),
            "SHORT_macd|60-70": AccuracyMetrics(
                total_signals=15, resolved_signals=10, wins=8, accuracy=0.80
            ),
            "LONG_bb|50-60": AccuracyMetrics(
                total_signals=10, resolved_signals=8, wins=4, accuracy=0.50
            ),
        }

        report = AccuracyReport(by_combination=by_combo)
        best = report.get_best_performing(min_signals=10)

        assert len(best) == 3  # All combos have >= 10 signals

    def test_to_dict(self):
        """Test conversion to dictionary."""
        overall = AccuracyMetrics(total_signals=100, resolved_signals=80, wins=60)
        report = AccuracyReport(overall=overall)

        data = report.to_dict()
        assert data["overall"]["total_signals"] == 100


class TestPredictionAccuracyCalculator:
    """Tests for PredictionAccuracyCalculator."""

    @pytest.mark.asyncio
    async def test_calculate_accuracy(self, calculator, mock_storage):
        """Test basic accuracy calculation."""
        metrics = await calculator.calculate_accuracy(
            signal_type="LONG_rsi",
            confidence_bucket="70-80",
            token="BTC",
        )

        assert metrics.total_signals == 10
        assert metrics.wins == 6
        assert metrics.accuracy == 0.75
        mock_storage.calculate_prediction_accuracy.assert_called_once()

    @pytest.mark.asyncio
    async def test_calculate_by_signal_type(self, calculator, mock_storage):
        """Test accuracy grouped by signal type."""
        # Create mock signals with outcomes
        signals = [
            SignalWithOutcome(
                signal=SignalRecord(
                    signal_id="s1",
                    token="BTC",
                    timestamp=1234567890000,
                    direction=SignalDirection.LONG,
                    confidence=0.75,
                    entry_price=50000.0,
                    score=75.0,
                    indicators_used=["rsi"],
                ),
                outcome=OutcomeRecord(
                    signal_id="s1",
                    exit_timestamp=1234567950000,
                    is_win=True,
                    pnl=100.0,
                    exit_price=50100.0,
                    duration_hours=1.0,
                ),
            ),
            SignalWithOutcome(
                signal=SignalRecord(
                    signal_id="s2",
                    token="BTC",
                    timestamp=1234567890000,
                    direction=SignalDirection.LONG,
                    confidence=0.75,
                    entry_price=50000.0,
                    score=75.0,
                    indicators_used=["rsi"],
                ),
                outcome=OutcomeRecord(
                    signal_id="s2",
                    exit_timestamp=1234567950000,
                    is_win=True,
                    pnl=100.0,
                    exit_price=50100.0,
                    duration_hours=1.0,
                ),
            ),
        ]
        mock_storage.query_signals_with_outcomes.return_value = signals

        results = await calculator.calculate_by_signal_type(min_signals=1)

        assert len(results) > 0
        mock_storage.query_signals_with_outcomes.assert_called()

    @pytest.mark.asyncio
    async def test_calculate_by_confidence_bucket(self, calculator, mock_storage):
        """Test accuracy grouped by confidence bucket."""
        results = await calculator.calculate_by_confidence_bucket(min_signals=1)

        # Should have results for each bucket with enough signals
        assert isinstance(results, dict)

    @pytest.mark.asyncio
    async def test_generate_report(self, calculator, mock_storage):
        """Test generating comprehensive report."""
        mock_storage.query_signals_with_outcomes.return_value = []

        report = await calculator.generate_report(min_signals=1)

        assert isinstance(report, AccuracyReport)
        assert report.overall is not None
        assert isinstance(report.by_signal_type, dict)
        assert isinstance(report.by_confidence_bucket, dict)

    @pytest.mark.asyncio
    async def test_compare_configurations(self, calculator, mock_storage):
        """Test comparing different configurations."""
        mock_storage.calculate_prediction_accuracy.return_value = {
            "total_signals": 10,
            "resolved_signals": 8,
            "wins": 6,
            "losses": 2,
            "accuracy": 0.75,
            "win_rate": 0.75,
            "avg_pnl": 50.0,
            "total_pnl": 400.0,
            "avg_duration_hours": 2.5,
        }

        configs = [
            {"name": "RSI only", "indicators": ["rsi"]},
            {"name": "MACD only", "indicators": ["macd"]},
            {"name": "Combined", "indicators": ["rsi", "macd"]},
        ]

        results = await calculator.compare_configurations(configs)

        assert len(results) == 3
        # Results should be sorted by accuracy
        assert results[0][1].accuracy >= results[-1][1].accuracy


class TestDefaultConfidenceBuckets:
    """Tests for default confidence buckets."""

    def test_default_buckets(self):
        """Test default confidence bucket definitions."""
        assert len(DEFAULT_CONFIDENCE_BUCKETS) == 10
        assert "0-10" in DEFAULT_CONFIDENCE_BUCKETS
        assert "90-100" in DEFAULT_CONFIDENCE_BUCKETS
        assert DEFAULT_CONFIDENCE_BUCKETS[0] == "0-10"
        assert DEFAULT_CONFIDENCE_BUCKETS[-1] == "90-100"
