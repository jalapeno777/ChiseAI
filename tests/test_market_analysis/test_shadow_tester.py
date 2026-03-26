"""Tests for BOS/CHoCH Shadow Tester (ST-ICT-032).

Tests verify:
- Shadow test initialization and lifecycle
- Signal recording and outcome tracking
- Accuracy calculation
- Feature flag integration (BOS/CHoCH safety check)
"""

from __future__ import annotations

from datetime import UTC
from unittest.mock import MagicMock, patch

import pytest
from src.market_analysis.ict_signals.shadow_tester import (
    BOSCHoCHShadowTester,
    PredictionResult,
    ShadowSignal,
    SignalType,
)


class TestBOSCHoCHShadowTesterInit:
    """Test shadow tester initialization."""

    def test_init_with_defaults(self) -> None:
        """Test initialization with default values."""
        tester = BOSCHoCHShadowTester()

        assert tester.redis_host == "host.docker.internal"
        assert tester.redis_port == 6380
        assert tester.redis_db == 1
        assert tester._active_signals == {}
        assert tester._outcomes == {}
        assert tester._test_start_time is None
        assert tester._test_end_time is None
        assert tester._duration_days == 7

    def test_init_with_custom_redis(self) -> None:
        """Test initialization with custom Redis params."""
        tester = BOSCHoCHShadowTester(
            redis_host="custom.host",
            redis_port=6381,
            redis_db=2,
        )

        assert tester.redis_host == "custom.host"
        assert tester.redis_port == 6381
        assert tester.redis_db == 2


class TestShadowTestLifecycle:
    """Test shadow test start/stop lifecycle."""

    def test_start_shadow_test(self) -> None:
        """Test starting a shadow test."""
        tester = BOSCHoCHShadowTester()
        tester._feature_flags = MagicMock()
        tester._feature_flags.is_bos_choch_enabled.return_value = True

        result = tester.start_shadow_test(duration_days=14)

        assert result["status"] == "started"
        assert result["duration_days"] == 14
        assert tester._test_start_time is not None
        assert tester._test_end_time is not None
        assert tester._duration_days == 14
        assert tester._active_signals == {}
        assert tester._outcomes == {}

    def test_start_shadow_test_feature_flag_disabled(self) -> None:
        """Test that starting shadow test raises when feature flag is disabled."""
        tester = BOSCHoCHShadowTester()
        tester._feature_flags = MagicMock()
        tester._feature_flags.is_bos_choch_enabled.return_value = False

        with pytest.raises(
            RuntimeError, match="BOS/CHoCH shadow testing disabled by feature flag"
        ):
            tester.start_shadow_test()

    def test_stop_shadow_test(self) -> None:
        """Test stopping a shadow test."""
        tester = BOSCHoCHShadowTester()
        tester._feature_flags = MagicMock()
        tester._feature_flags.is_bos_choch_enabled.return_value = True

        tester.start_shadow_test()
        result = tester.stop_shadow_test()

        assert result["status"] == "stopped"
        assert result["start_time"] is not None
        assert result["end_time"] is not None
        assert "final_accuracy" in result


class TestSignalRecording:
    """Test signal prediction recording."""

    def test_record_signal_prediction(self) -> None:
        """Test recording a signal prediction."""
        tester = BOSCHoCHShadowTester()
        tester._feature_flags = MagicMock()
        tester._feature_flags.is_bos_choch_enabled.return_value = True

        tester.start_shadow_test()

        signal = tester.record_signal_prediction(
            signal_type=SignalType.BOS_BULL,
            token="BTC/USD",
            predicted_direction="long",
            predicted_target=50000.0,
            predicted_stop=49000.0,
            confidence=0.85,
            timeframe="1H",
            current_price=49500.0,
        )

        assert signal.signal_id is not None
        assert signal.signal_type == SignalType.BOS_BULL
        assert signal.token == "BTC/USD"
        assert signal.predicted_direction == "long"
        assert signal.confidence == 0.85
        assert len(tester._active_signals) == 1


class TestOutcomeRecording:
    """Test actual outcome recording."""

    def test_record_actual_outcome_correct_long(self) -> None:
        """Test recording outcome for correct long prediction."""
        tester = BOSCHoCHShadowTester()
        tester._feature_flags = MagicMock()
        tester._feature_flags.is_bos_choch_enabled.return_value = True

        tester.start_shadow_test()

        signal = tester.record_signal_prediction(
            signal_type=SignalType.BOS_BULL,
            token="BTC/USD",
            predicted_direction="long",
            predicted_target=50000.0,
            predicted_stop=49000.0,
            confidence=0.85,
            timeframe="1H",
            current_price=49500.0,
        )

        outcome = tester.record_actual_outcome(
            signal_id=signal.signal_id,
            actual_high=51000.0,
            actual_low=49000.0,
            outcome_price=50500.0,
            holding_period_hours=4.0,
        )

        assert outcome is not None
        assert outcome.result == PredictionResult.CORRECT
        assert outcome.signal_id == signal.signal_id

    def test_record_actual_outcome_incorrect_short(self) -> None:
        """Test recording outcome for incorrect short prediction."""
        tester = BOSCHoCHShadowTester()
        tester._feature_flags = MagicMock()
        tester._feature_flags.is_bos_choch_enabled.return_value = True

        tester.start_shadow_test()

        signal = tester.record_signal_prediction(
            signal_type=SignalType.BOS_BEAR,
            token="BTC/USD",
            predicted_direction="short",
            predicted_target=49000.0,
            predicted_stop=50000.0,
            confidence=0.80,
            timeframe="1H",
            current_price=49500.0,
        )

        outcome = tester.record_actual_outcome(
            signal_id=signal.signal_id,
            actual_high=51000.0,
            actual_low=49000.0,
            outcome_price=50500.0,
            holding_period_hours=4.0,
        )

        assert outcome is not None
        assert outcome.result == PredictionResult.INCORRECT


class TestAccuracyCalculation:
    """Test accuracy calculation."""

    def test_calculate_accuracy_empty(self) -> None:
        """Test accuracy calculation with no signals."""
        tester = BOSCHoCHShadowTester()
        tester._feature_flags = MagicMock()
        tester._feature_flags.is_bos_choch_enabled.return_value = True

        tester.start_shadow_test()
        accuracy = tester.calculate_accuracy()

        assert accuracy["total_signals"] == 0
        assert accuracy["resolved_signals"] == 0
        assert accuracy["directional_accuracy"] == 0.0

    def test_calculate_accuracy_with_signals(self) -> None:
        """Test accuracy calculation with resolved signals."""
        tester = BOSCHoCHShadowTester()
        tester._feature_flags = MagicMock()
        tester._feature_flags.is_bos_choch_enabled.return_value = True

        tester.start_shadow_test()

        # Add correct long signal
        signal1 = tester.record_signal_prediction(
            signal_type=SignalType.BOS_BULL,
            token="BTC/USD",
            predicted_direction="long",
            predicted_target=50000.0,
            predicted_stop=49000.0,
            confidence=0.85,
            timeframe="1H",
            current_price=49500.0,
        )
        tester.record_actual_outcome(
            signal_id=signal1.signal_id,
            actual_high=51000.0,
            actual_low=49000.0,
            outcome_price=50500.0,
            holding_period_hours=4.0,
        )

        # Add incorrect short signal
        signal2 = tester.record_signal_prediction(
            signal_type=SignalType.BOS_BEAR,
            token="ETH/USD",
            predicted_direction="short",
            predicted_target=3000.0,
            predicted_stop=3100.0,
            confidence=0.75,
            timeframe="1H",
            current_price=3050.0,
        )
        tester.record_actual_outcome(
            signal_id=signal2.signal_id,
            actual_high=3150.0,
            actual_low=2950.0,
            outcome_price=3050.0,
            holding_period_hours=2.0,
        )

        accuracy = tester.calculate_accuracy()

        assert accuracy["total_signals"] == 2
        assert accuracy["resolved_signals"] == 2
        assert accuracy["correct"] == 1
        assert accuracy["incorrect"] == 1
        assert accuracy["directional_accuracy"] == 50.0


class TestFeatureFlagCheck:
    """Test feature flag integration for BOS/CHoCH safety."""

    def test_feature_flag_check_blocks_shadow_test(self) -> None:
        """Test that shadow test is blocked when BOS/CHoCH feature flag is disabled."""
        tester = BOSCHoCHShadowTester()

        # Simulate feature flag being disabled
        with patch.object(
            tester,
            "_feature_flags",
            MagicMock(is_bos_choch_enabled=MagicMock(return_value=False)),
        ):
            with pytest.raises(
                RuntimeError, match="BOS/CHoCH shadow testing disabled by feature flag"
            ):
                tester.start_shadow_test()

    def test_feature_flag_check_allows_shadow_test(self) -> None:
        """Test that shadow test proceeds when BOS/CHoCH feature flag is enabled."""
        tester = BOSCHoCHShadowTester()

        # Simulate feature flag being enabled
        with patch.object(
            tester,
            "_feature_flags",
            MagicMock(is_bos_choch_enabled=MagicMock(return_value=True)),
        ):
            result = tester.start_shadow_test()
            assert result["status"] == "started"


class TestShadowSignal:
    """Test ShadowSignal dataclass."""

    def test_shadow_signal_creation(self) -> None:
        """Test creating a ShadowSignal."""
        from datetime import datetime

        signal = ShadowSignal(
            signal_id="test-123",
            signal_type=SignalType.BOS_BULL,
            token="BTC/USD",
            timestamp=datetime.now(UTC),
            predicted_direction="long",
            predicted_target=50000.0,
            predicted_stop=49000.0,
            confidence=0.85,
            timeframe="1H",
            metadata={"extra": "data"},
        )

        assert signal.signal_id == "test-123"
        assert signal.signal_type == SignalType.BOS_BULL
        assert signal.token == "BTC/USD"
        assert signal.confidence == 0.85
        assert signal.metadata["extra"] == "data"


class TestSignalTypes:
    """Test SignalType and PredictionResult enums."""

    def test_signal_types(self) -> None:
        """Test SignalType enum values."""
        assert SignalType.BOS_BULL.value == "bos_bull"
        assert SignalType.BOS_BEAR.value == "bos_bear"
        assert SignalType.CHOCH_BULL.value == "choch_bull"
        assert SignalType.CHOCH_BEAR.value == "choch_bear"

    def test_prediction_results(self) -> None:
        """Test PredictionResult enum values."""
        assert PredictionResult.CORRECT.value == "correct"
        assert PredictionResult.INCORRECT.value == "incorrect"
        assert PredictionResult.PENDING.value == "pending"
