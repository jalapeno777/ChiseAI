"""Tests for repainting and lookahead guard safety module."""

import numpy as np
import pytest

from market_analysis.safety import (
    CheckpointedData,
    GuardResult,
    LookaheadAccessError,
    LookaheadGuard,
    RepaintingDetector,
    RepaintingError,
    RepaintingViolation,
    RepaintingViolationType,
    check_indicator,
    lookahead_guard,
)


class TestRepaintingDetector:
    """Test cases for RepaintingDetector."""

    @pytest.fixture
    def detector(self):
        """Create a repainting detector with 0% tolerance."""
        return RepaintingDetector(tolerance=0.0)

    def test_initialization(self):
        """Test detector initialization."""
        detector = RepaintingDetector(tolerance=0.0)
        assert detector.tolerance == 0.0
        assert detector.store_snapshots is False

        detector_with_snapshots = RepaintingDetector(
            tolerance=0.0, store_snapshots=True
        )
        assert detector_with_snapshots.store_snapshots is True

    def test_invalid_tolerance(self):
        """Test that invalid tolerance raises error."""
        with pytest.raises(ValueError, match="Tolerance must be in"):
            RepaintingDetector(tolerance=-0.1)
        with pytest.raises(ValueError, match="Tolerance must be in"):
            RepaintingDetector(tolerance=1.5)

    def test_snapshot_storage(self, detector):
        """Test snapshot storage and retrieval."""
        detector.store_snapshots = True
        test_values = np.array([1.0, 2.0, 3.0])
        detector.store_snapshot("RSI", 5, test_values)

        retrieved = detector.get_snapshot("RSI", 5)
        assert retrieved is not None
        np.testing.assert_array_equal(retrieved, test_values)

    def test_snapshot_not_found(self, detector):
        """Test retrieval of non-existent snapshot."""
        detector.store_snapshots = True
        result = detector.get_snapshot("NONEXISTENT", 0)
        assert result is None

    def test_check_lookahead_valid(self, detector):
        """Test lookahead check with valid calculation."""

        def calculator(data):
            return np.array([d for d in data])

        data = [1, 2, 3, 4, 5]
        result = detector.check_lookahead(data, calculator, "test")

        assert result.passed is True
        assert result.violation_count == 0

    def test_check_lookahead_result_length_exceeds_data(self, detector):
        """Test detection when result length exceeds data length."""

        # A calculation that returns more values than data points
        def calculator(data):
            return np.array([1, 2, 3, 4, 5, 6, 7])  # 7 values from 5 data points

        data = [1, 2, 3, 4, 5]
        result = detector.check_lookahead(data, calculator, "test")

        assert result.passed is False
        assert result.violation_count == 1
        assert (
            result.violations[0].violation_type
            == RepaintingViolationType.LOOKAHEAD_ACCESS
        )

    def test_check_repainting_insufficient_data(self, detector):
        """Test repainting check with insufficient data."""

        class MockIndicator:
            def calculate(self, data):
                return np.array([1, 2, 3])

        indicator = MockIndicator()
        result = detector.check_repainting(indicator, [1, 2])

        # Should pass with fewer than 2 data points (no comparison possible)
        assert result.passed is True

    def test_check_repainting_no_method(self, detector):
        """Test repainting check with indicator lacking compute/calculate."""

        class BadIndicator:
            pass

        indicator = BadIndicator()
        result = detector.check_repainting(indicator, [1, 2, 3, 4, 5])

        assert result.passed is False
        assert "no compute" in result.violations[0].details.lower()

    def test_values_equal_nan(self, detector):
        """Test NaN equality handling."""
        assert detector._values_equal(np.nan, np.nan) is True
        assert detector._values_equal(1.0, 1.0) is True
        assert detector._values_equal(1.0, 1.0 + 1e-12) is True
        assert detector._values_equal(1.0, 2.0) is False

    def test_check_repainting_detects_actual_repainting(self, detector):
        """Test that check_repainting catches an indicator that changes historical values.

        This test creates a deliberately repainting indicator that returns different
        values for the same bar index when calculated with more data.
        """

        class RepaintingIndicator:
            """Indicator that changes historical values based on data length."""

            def compute(self, data):
                # Simulate repainting: when we have 5 bars, we "adjust" bar 0's value
                # based on the latest bar (a classic repainting pattern)
                values = np.array([10.0, 20.0, 30.0, 40.0, 50.0])
                if len(data) == 5:
                    # Pretend bar 0 changed when new data arrived
                    values[0] = 99.0
                return values[: len(data)]

        indicator = RepaintingIndicator()
        # Data with 4 elements: compute returns [10, 20, 30, 40]
        data_4 = [1, 2, 3, 4]
        result_4 = detector.check_repainting(indicator, data_4)
        # With 4 bars, no comparison possible (only len-1 comparisons)
        assert result_4.passed is True

        # Data with 5 elements: compute returns [99, 20, 30, 40, 50]
        # The first value changed from 10 to 99, indicating repainting
        data_5 = [1, 2, 3, 4, 5]
        result_5 = detector.check_repainting(indicator, data_5)

        assert result_5.passed is False
        assert result_5.violation_count >= 1
        # Bar 0's value changed
        assert any(
            v.index == 0 and v.violation_type == RepaintingViolationType.VALUE_CHANGE
            for v in result_5.violations
        )
        assert any(
            "changed from" in v.details and "to" in v.details
            for v in result_5.violations
        )


class TestCheckpointedData:
    """Test cases for CheckpointedData."""

    def test_basic_access(self):
        """Test basic data access without checkpoint."""
        data = [1, 2, 3, 4, 5]
        checkpointed = CheckpointedData(data)

        assert len(checkpointed) == 5
        assert checkpointed[0] == 1
        assert checkpointed[4] == 5

    def test_checkpoint_access_allowed(self):
        """Test that access within checkpoint is allowed."""
        data = [1, 2, 3, 4, 5]
        checkpointed = CheckpointedData(data)

        with checkpointed.access_checkpoint(current_bar=2) as cp:
            assert cp[0] == 1
            assert cp[2] == 3
            # cp[3] would raise if accessed within block

    def test_checkpoint_access_blocked(self):
        """Test that access beyond checkpoint raises error."""
        data = [1, 2, 3, 4, 5]
        checkpointed = CheckpointedData(data)

        with pytest.raises(LookaheadAccessError):
            with checkpointed.access_checkpoint(current_bar=2) as cp:
                _ = cp[3]  # Should raise - beyond checkpoint

    def test_checkpoint_restored_after_exit(self):
        """Test that checkpoint is restored after context exit."""
        data = [1, 2, 3, 4, 5]
        checkpointed = CheckpointedData(data)

        with checkpointed.access_checkpoint(current_bar=2):
            pass  # Checkpoint active

        # After exit, should have no checkpoint
        assert checkpointed[3] == 4  # Should not raise


class TestLookaheadGuard:
    """Test cases for LookaheadGuard context manager."""

    def test_context_manager_pass(self):
        """Test context manager with no violations."""
        guard = LookaheadGuard(name="test", strict=False)

        with guard:
            pass  # No violations

        assert len(guard.violations) == 0

    def test_decorator_no_violation(self):
        """Test decorator with compliant function."""

        @lookahead_guard
        def calculate(data):
            return sum(data)

        result = calculate([1, 2, 3])
        assert result == 6


class TestLookaheadGuardIntegration:
    """Integration tests for lookahead guard with indicators."""

    @pytest.fixture
    def sample_ohlcv_data(self):
        """Create sample OHLCV data for testing.

        Provides 50 bars to satisfy MACD's requirement (26 fast + 26 slow + 9 signal = 35 min).
        """
        from data_ingestion.ohlcv_fetcher import OHLCVData

        base_ts = 1609459200000
        data = []
        price = 100.0

        for i in range(50):
            price += 2.0 if i % 2 == 0 else -1.0
            data.append(
                OHLCVData(
                    timestamp=base_ts + i * 60000,
                    open_price=price - 1.0,
                    high_price=price + 1.0,
                    low_price=price - 2.0,
                    close_price=price,
                    volume=1000.0,
                )
            )

        return data

    def test_rsi_no_repainting(self, sample_ohlcv_data):
        """Test RSI indicator passes repainting check."""
        from market_analysis.indicators.rsi import RSI

        rsi = RSI(period=14)
        detector = RepaintingDetector(tolerance=0.0)

        result = detector.check_repainting(rsi, sample_ohlcv_data)

        assert result.passed is True, f"Violations: {result.violations}"
        assert result.guard_name == "RSI_repainting_check"

    def test_macd_no_repainting(self, sample_ohlcv_data):
        """Test MACD indicator passes repainting check."""
        from market_analysis.indicators.macd import MACD

        macd = MACD()
        detector = RepaintingDetector(tolerance=0.0)

        result = detector.check_repainting(macd, sample_ohlcv_data)

        assert result.passed is True, f"Violations: {result.violations}"
        assert result.guard_name == "MACD_repainting_check"

    def test_bollinger_bands_no_repainting(self, sample_ohlcv_data):
        """Test Bollinger Bands indicator passes repainting check."""
        from market_analysis.indicators.bollinger_bands import BollingerBands

        bb = BollingerBands()
        detector = RepaintingDetector(tolerance=0.0)

        result = detector.check_repainting(bb, sample_ohlcv_data)

        assert result.passed is True, f"Violations: {result.violations}"
        assert result.guard_name == "BollingerBands_repainting_check"

    def test_check_indicator_convenience_function(self, sample_ohlcv_data):
        """Test check_indicator convenience function."""
        from market_analysis.indicators.rsi import RSI

        rsi = RSI(period=14)
        result = check_indicator(rsi, sample_ohlcv_data)

        assert isinstance(result, GuardResult)
        assert result.passed is True


class TestRepaintingError:
    """Test cases for RepaintingError."""

    def test_error_creation(self):
        """Test RepaintingError creation."""
        error = RepaintingError("Test violation")
        assert str(error) == "Test violation"

    def test_error_raised_by_strict_guard(self):
        """Test that strict guard raises RepaintingError."""
        guard = LookaheadGuard(name="test", strict=True)

        with pytest.raises(RepaintingError):
            with guard:
                guard._violations.append(
                    RepaintingViolation(
                        violation_type=RepaintingViolationType.LOOKAHEAD_ACCESS,
                        index=0,
                        timestamp=None,
                        details="Test violation",
                    )
                )


class TestGlobalDetector:
    """Test cases for global detector functions."""

    def test_get_detector_singleton(self):
        """Test that get_detector returns singleton."""
        from market_analysis.safety import get_detector

        detector1 = get_detector()
        detector2 = get_detector()

        assert detector1 is detector2
        assert detector1.tolerance == 0.0
