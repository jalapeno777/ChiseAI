"""Tests for BOS/CHoCH Shadow Tester.

For ST-ICT-032: BOS/CHoCH Live Shadow Testing
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from market_analysis.ict_signals.shadow_tester import (
    BOSCHoCHShadowTester,
    DailyAccuracyReport,
    PredictionResult,
    ShadowSignal,
    SignalType,
)


@pytest.fixture
def mock_redis_client():
    """Mock Redis client for testing."""
    mock_client = MagicMock()
    mock_client.ping.return_value = True
    mock_client.get.return_value = None
    mock_client.setex.return_value = True
    return mock_client


@pytest.fixture
def shadow_tester(mock_redis_client):
    """Create shadow tester instance with mocked Redis."""
    tester = BOSCHoCHShadowTester(
        redis_host="localhost",
        redis_port=6379,
        redis_db=0,
    )
    tester._redis_client = mock_redis_client
    return tester


class TestBOSCHoCHShadowTester:
    """Tests for BOSCHoCHShadowTester class."""

    def test_start_shadow_test(self, shadow_tester):
        """Test starting a shadow test."""
        result = shadow_tester.start_shadow_test(duration_days=7)

        assert result["status"] == "started"
        assert result["duration_days"] == 7
        assert shadow_tester._test_start_time is not None
        assert shadow_tester._test_end_time is not None
        assert (shadow_tester._test_end_time - shadow_tester._test_start_time).days == 7

    def test_record_signal_prediction(self, shadow_tester):
        """Test recording a signal prediction."""
        shadow_tester.start_shadow_test()

        signal = shadow_tester.record_signal_prediction(
            signal_type=SignalType.BOS_BULL,
            token="BTCUSDT",
            predicted_direction="long",
            predicted_target=52000.0,
            predicted_stop=50000.0,
            confidence=0.75,
            timeframe="1h",
            current_price=51000.0,
        )

        assert signal.signal_id is not None
        assert signal.signal_type == SignalType.BOS_BULL
        assert signal.token == "BTCUSDT"
        assert signal.predicted_direction == "long"
        assert signal.predicted_target == 52000.0
        assert signal.confidence == 0.75
        assert signal.signal_id in shadow_tester._active_signals

    def test_record_actual_outcome_correct(self, shadow_tester):
        """Test recording a correct prediction outcome."""
        shadow_tester.start_shadow_test()

        signal = shadow_tester.record_signal_prediction(
            signal_type=SignalType.BOS_BULL,
            token="BTCUSDT",
            predicted_direction="long",
            predicted_target=52000.0,
            predicted_stop=50000.0,
            confidence=0.75,
            timeframe="1h",
            current_price=51000.0,
        )

        outcome = shadow_tester.record_actual_outcome(
            signal_id=signal.signal_id,
            actual_high=52500.0,  # Price went up - correct prediction
            actual_low=50500.0,
            outcome_price=52000.0,
            holding_period_hours=4.0,
        )

        assert outcome is not None
        assert outcome.result == PredictionResult.CORRECT
        assert outcome.signal_id == signal.signal_id

    def test_record_actual_outcome_incorrect(self, shadow_tester):
        """Test recording an incorrect prediction outcome."""
        shadow_tester.start_shadow_test()

        signal = shadow_tester.record_signal_prediction(
            signal_type=SignalType.BOS_BEAR,
            token="ETHUSDT",
            predicted_direction="short",
            predicted_target=3000.0,
            predicted_stop=3200.0,
            confidence=0.70,
            timeframe="4h",
            current_price=3100.0,
        )

        outcome = shadow_tester.record_actual_outcome(
            signal_id=signal.signal_id,
            actual_high=3300.0,  # Price went up - incorrect for short
            actual_low=3050.0,
            outcome_price=3150.0,
            holding_period_hours=2.0,
        )

        assert outcome is not None
        assert outcome.result == PredictionResult.INCORRECT

    def test_record_actual_outcome_signal_not_found(self, shadow_tester):
        """Test recording outcome for non-existent signal."""
        shadow_tester.start_shadow_test()

        outcome = shadow_tester.record_actual_outcome(
            signal_id="non-existent-id",
            actual_high=52500.0,
            actual_low=50500.0,
            outcome_price=51000.0,
            holding_period_hours=4.0,
        )

        assert outcome is None

    def test_calculate_accuracy_no_signals(self, shadow_tester):
        """Test accuracy calculation with no signals."""
        shadow_tester.start_shadow_test()

        accuracy = shadow_tester.calculate_accuracy()

        assert accuracy["total_signals"] == 0
        assert accuracy["resolved_signals"] == 0
        assert accuracy["correct"] == 0
        assert accuracy["incorrect"] == 0
        assert accuracy["pending"] == 0
        assert accuracy["directional_accuracy"] == 0.0

    def test_calculate_accuracy_with_signals(self, shadow_tester):
        """Test accuracy calculation with signals and outcomes."""
        shadow_tester.start_shadow_test()

        # Record correct prediction
        signal1 = shadow_tester.record_signal_prediction(
            signal_type=SignalType.BOS_BULL,
            token="BTCUSDT",
            predicted_direction="long",
            predicted_target=52000.0,
            predicted_stop=50000.0,
            confidence=0.75,
            timeframe="1h",
            current_price=51000.0,
        )
        shadow_tester.record_actual_outcome(
            signal_id=signal1.signal_id,
            actual_high=52500.0,
            actual_low=50500.0,
            outcome_price=52000.0,
            holding_period_hours=4.0,
        )

        # Record incorrect prediction
        signal2 = shadow_tester.record_signal_prediction(
            signal_type=SignalType.CHOCH_BULL,
            token="ETHUSDT",
            predicted_direction="long",
            predicted_target=3200.0,
            predicted_stop=2900.0,
            confidence=0.65,
            timeframe="1h",
            current_price=3000.0,
        )
        shadow_tester.record_actual_outcome(
            signal_id=signal2.signal_id,
            actual_high=2950.0,  # Price went down
            actual_low=2850.0,
            outcome_price=2900.0,
            holding_period_hours=2.0,
        )

        accuracy = shadow_tester.calculate_accuracy()

        assert accuracy["total_signals"] == 2
        assert accuracy["resolved_signals"] == 2
        assert accuracy["correct"] == 1
        assert accuracy["incorrect"] == 1
        assert accuracy["pending"] == 0
        assert accuracy["directional_accuracy"] == 50.0

    def test_generate_daily_report(self, shadow_tester, mock_redis_client):
        """Test daily report generation."""
        shadow_tester.start_shadow_test()

        # Record signals
        signal = shadow_tester.record_signal_prediction(
            signal_type=SignalType.BOS_BULL,
            token="BTCUSDT",
            predicted_direction="long",
            predicted_target=52000.0,
            predicted_stop=50000.0,
            confidence=0.75,
            timeframe="1h",
            current_price=51000.0,
        )

        shadow_tester.record_actual_outcome(
            signal_id=signal.signal_id,
            actual_high=52500.0,
            actual_low=50500.0,
            outcome_price=52000.0,
            holding_period_hours=4.0,
        )

        today = datetime.now(UTC).strftime("%Y-%m-%d")
        report = shadow_tester.generate_daily_report(today)

        assert report.date == today
        assert report.total_signals == 1
        assert report.resolved_signals == 1
        assert report.correct_predictions == 1
        assert report.directional_accuracy == 100.0
        assert "bos_bull" in report.signals_by_type

    def test_stop_shadow_test(self, shadow_tester):
        """Test stopping a shadow test."""
        shadow_tester.start_shadow_test(duration_days=7)

        result = shadow_tester.stop_shadow_test()

        assert result["status"] == "stopped"
        assert result["duration_days"] == 7
        assert result["end_time"] is not None
        assert "final_accuracy" in result

    def test_get_pending_signals(self, shadow_tester):
        """Test getting pending signals without outcomes."""
        shadow_tester.start_shadow_test()

        signal1 = shadow_tester.record_signal_prediction(
            signal_type=SignalType.BOS_BULL,
            token="BTCUSDT",
            predicted_direction="long",
            predicted_target=52000.0,
            predicted_stop=50000.0,
            confidence=0.75,
            timeframe="1h",
            current_price=51000.0,
        )

        signal2 = shadow_tester.record_signal_prediction(
            signal_type=SignalType.BOS_BEAR,
            token="ETHUSDT",
            predicted_direction="short",
            predicted_target=3000.0,
            predicted_stop=3200.0,
            confidence=0.70,
            timeframe="4h",
            current_price=3100.0,
        )

        # Record outcome for only one signal
        shadow_tester.record_actual_outcome(
            signal_id=signal1.signal_id,
            actual_high=52500.0,
            actual_low=50500.0,
            outcome_price=52000.0,
            holding_period_hours=4.0,
        )

        pending = shadow_tester.get_pending_signals()

        assert len(pending) == 1
        assert pending[0].signal_id == signal2.signal_id


class TestShadowSignal:
    """Tests for ShadowSignal dataclass."""

    def test_shadow_signal_creation(self):
        """Test ShadowSignal creation."""
        signal = ShadowSignal(
            signal_id="test-id",
            signal_type=SignalType.CHOCH_BEAR,
            token="BTCUSDT",
            timestamp=datetime.now(UTC),
            predicted_direction="short",
            predicted_target=48000.0,
            predicted_stop=50000.0,
            confidence=0.68,
            timeframe="15m",
        )

        assert signal.signal_id == "test-id"
        assert signal.signal_type == SignalType.CHOCH_BEAR
        assert signal.confidence == 0.68


class TestSignalType:
    """Tests for SignalType enum."""

    def test_signal_type_values(self):
        """Test all signal type values exist."""
        assert SignalType.BOS_BULL.value == "bos_bull"
        assert SignalType.BOS_BEAR.value == "bos_bear"
        assert SignalType.CHOCH_BULL.value == "choch_bull"
        assert SignalType.CHOCH_BEAR.value == "choch_bear"


class TestDailyAccuracyReport:
    """Tests for DailyAccuracyReport dataclass."""

    def test_daily_report_creation(self):
        """Test DailyAccuracyReport creation."""
        report = DailyAccuracyReport(
            date="2026-03-26",
            total_signals=10,
            resolved_signals=8,
            correct_predictions=6,
            incorrect_predictions=2,
            pending_predictions=2,
            directional_accuracy=75.0,
            avg_confidence=0.72,
            signals_by_type={"bos_bull": 5, "bos_bear": 5},
        )

        assert report.date == "2026-03-26"
        assert report.total_signals == 10
        assert report.directional_accuracy == 75.0
        assert report.signals_by_type["bos_bull"] == 5


class TestPredictionResult:
    """Tests for PredictionResult enum."""

    def test_prediction_result_values(self):
        """Test prediction result values."""
        assert PredictionResult.CORRECT.value == "correct"
        assert PredictionResult.INCORRECT.value == "incorrect"
        assert PredictionResult.PENDING.value == "pending"
