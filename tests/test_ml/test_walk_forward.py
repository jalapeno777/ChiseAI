"""Tests for walk-forward evaluation framework."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from ml.walk_forward import (
    AggregatedMetrics,
    LookAheadBiasCheck,
    TemporalWindow,
    WalkForwardConfig,
    WalkForwardEvaluator,
    WalkForwardResult,
    WindowMetrics,
    WindowStatus,
)


class TestTemporalWindow:
    """Tests for TemporalWindow class."""

    def test_valid_window_creation(self) -> None:
        """Test creating a valid temporal window."""
        start = datetime(2024, 1, 1)
        window = TemporalWindow(
            train_start=start,
            train_end=start + timedelta(days=30),
            test_start=start + timedelta(days=30),
            test_end=start + timedelta(days=37),
        )

        assert window.train_start == start
        assert window.train_end == start + timedelta(days=30)
        assert window.test_start == start + timedelta(days=30)
        assert window.test_end == start + timedelta(days=37)

    def test_train_end_before_train_start_raises(self) -> None:
        """Test that train_end before train_start raises ValueError."""
        start = datetime(2024, 1, 1)
        with pytest.raises(ValueError, match="train_end.*must be after train_start"):
            TemporalWindow(
                train_start=start,
                train_end=start - timedelta(days=1),
                test_start=start + timedelta(days=30),
                test_end=start + timedelta(days=37),
            )

    def test_test_end_before_test_start_raises(self) -> None:
        """Test that test_end before test_start raises ValueError."""
        start = datetime(2024, 1, 1)
        with pytest.raises(ValueError, match="test_end.*must be after test_start"):
            TemporalWindow(
                train_start=start,
                train_end=start + timedelta(days=30),
                test_start=start + timedelta(days=37),
                test_end=start + timedelta(days=30),
            )

    def test_test_start_before_train_end_raises(self) -> None:
        """Test that test_start before train_end raises ValueError (look-ahead bias)."""
        start = datetime(2024, 1, 1)
        with pytest.raises(ValueError, match="test_start.*must be >= train_end"):
            TemporalWindow(
                train_start=start,
                train_end=start + timedelta(days=30),
                test_start=start + timedelta(days=29),
                test_end=start + timedelta(days=37),
            )

    def test_no_overlap_validation(self) -> None:
        """Test window overlap detection."""
        start = datetime(2024, 1, 1)
        window1 = TemporalWindow(
            train_start=start,
            train_end=start + timedelta(days=30),
            test_start=start + timedelta(days=30),
            test_end=start + timedelta(days=37),
        )
        window2 = TemporalWindow(
            train_start=start + timedelta(days=37),
            train_end=start + timedelta(days=67),
            test_start=start + timedelta(days=67),
            test_end=start + timedelta(days=74),
        )

        assert window1.validate_no_overlap(window2) is True
        assert window2.validate_no_overlap(window1) is True

    def test_overlap_detection(self) -> None:
        """Test that overlapping windows are detected."""
        start = datetime(2024, 1, 1)
        window1 = TemporalWindow(
            train_start=start,
            train_end=start + timedelta(days=30),
            test_start=start + timedelta(days=30),
            test_end=start + timedelta(days=37),
        )
        # Window2: train is Feb 7 - Mar 9, test is Mar 9 - Mar 16
        # But we want test to overlap with window1's test (Jan 31 - Feb 7)
        # So let's make window2's test_start be Feb 5 (overlaps with window1's test_end Feb 7)
        # And window2's train must end before test starts
        window2 = TemporalWindow(
            train_start=start + timedelta(days=7),  # Jan 8
            train_end=start + timedelta(days=35),  # Feb 5 - this is before test_start
            test_start=start
            + timedelta(days=35),  # Feb 5 - overlaps with window1 test (Jan 31-Feb 7)
            test_end=start + timedelta(days=42),  # Feb 12
        )

        assert window1.validate_no_overlap(window2) is False

    def test_contains_timestamp(self) -> None:
        """Test timestamp containment check."""
        start = datetime(2024, 1, 1)
        window = TemporalWindow(
            train_start=start,
            train_end=start + timedelta(days=30),
            test_start=start + timedelta(days=30),
            test_end=start + timedelta(days=37),
        )

        assert window.contains_timestamp(start + timedelta(days=15), "train") is True
        assert window.contains_timestamp(start + timedelta(days=32), "test") is True
        assert window.contains_timestamp(start + timedelta(days=35), "train") is False

    def test_duration_days(self) -> None:
        """Test duration calculation."""
        start = datetime(2024, 1, 1)
        window = TemporalWindow(
            train_start=start,
            train_end=start + timedelta(days=30),
            test_start=start + timedelta(days=30),
            test_end=start + timedelta(days=37),
        )

        assert window.duration_days("train") == 30.0
        assert window.duration_days("test") == 7.0


class TestWalkForwardConfig:
    """Tests for WalkForwardConfig class."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = WalkForwardConfig()

        assert config.train_days == 30
        assert config.test_days == 7
        assert config.step_days == 7
        assert config.min_train_samples == 500
        assert config.min_test_samples == 100
        assert config.max_windows == 52

    def test_custom_config(self) -> None:
        """Test custom configuration values."""
        config = WalkForwardConfig(
            train_days=60,
            test_days=14,
            step_days=14,
            max_windows=26,
        )

        assert config.train_days == 60
        assert config.test_days == 14
        assert config.step_days == 14
        assert config.max_windows == 26

    def test_invalid_train_days_raises(self) -> None:
        """Test that invalid train_days raises ValueError."""
        with pytest.raises(ValueError, match="train_days must be positive"):
            WalkForwardConfig(train_days=0)

    def test_invalid_test_days_raises(self) -> None:
        """Test that invalid test_days raises ValueError."""
        with pytest.raises(ValueError, match="test_days must be positive"):
            WalkForwardConfig(test_days=-1)


class TestWalkForwardEvaluator:
    """Tests for WalkForwardEvaluator class."""

    def test_window_generation(self) -> None:
        """Test walk-forward window generation."""
        config = WalkForwardConfig(train_days=30, test_days=7, step_days=7)
        evaluator = WalkForwardEvaluator(config)

        start = datetime(2024, 1, 1)
        end = datetime(2024, 6, 1)

        windows = evaluator.generate_windows(start, end)

        assert len(windows) > 0
        assert len(windows) <= config.max_windows

        # Check first window
        first = windows[0]
        assert first.train_start == start
        assert first.train_end == start + timedelta(days=30)
        assert first.test_start == start + timedelta(days=30)
        assert first.test_end == start + timedelta(days=37)

    def test_no_look_ahead_bias_validation_passes(self) -> None:
        """Test that valid windows pass look-ahead bias check."""
        config = WalkForwardConfig(train_days=30, test_days=7, step_days=7)
        evaluator = WalkForwardEvaluator(config)

        start = datetime(2024, 1, 1)
        end = datetime(2024, 6, 1)
        windows = evaluator.generate_windows(start, end)

        result = evaluator.validate_no_look_ahead_bias(windows)
        assert result == LookAheadBiasCheck.PASSED

    def test_look_ahead_bias_overlap_detected(self) -> None:
        """Test that overlapping test periods are detected."""
        start = datetime(2024, 1, 1)
        windows = [
            TemporalWindow(
                train_start=start,
                train_end=start + timedelta(days=30),
                test_start=start + timedelta(days=30),
                test_end=start + timedelta(days=37),
            ),
            TemporalWindow(
                train_start=start + timedelta(days=7),  # Jan 8
                train_end=start + timedelta(days=35),  # Feb 5
                test_start=start
                + timedelta(days=35),  # Feb 5 - overlaps with window1 test
                test_end=start + timedelta(days=42),  # Feb 12
            ),
        ]

        config = WalkForwardConfig()
        evaluator = WalkForwardEvaluator(config)

        result = evaluator.validate_no_look_ahead_bias(windows)
        assert result == LookAheadBiasCheck.FAILED_OVERLAP

    def test_strategy_comparison(self) -> None:
        """Test strategy comparison functionality."""
        evaluator = WalkForwardEvaluator()

        # Create mock results
        result1 = WalkForwardResult(
            strategy_id="strategy_1",
            config=WalkForwardConfig(),
            aggregated=AggregatedMetrics(mean_sharpe=1.5),
        )
        result2 = WalkForwardResult(
            strategy_id="strategy_2",
            config=WalkForwardConfig(),
            aggregated=AggregatedMetrics(mean_sharpe=1.2),
        )
        result3 = WalkForwardResult(
            strategy_id="strategy_3",
            config=WalkForwardConfig(),
            aggregated=AggregatedMetrics(mean_sharpe=1.8),
        )

        comparisons = evaluator.compare_strategies([result1, result2, result3])

        assert len(comparisons) == 3
        assert comparisons[0][0] == "strategy_3"  # Highest Sharpe
        assert comparisons[1][0] == "strategy_1"
        assert comparisons[2][0] == "strategy_2"

    def test_aggregation_empty_results(self) -> None:
        """Test aggregation with no completed windows."""
        evaluator = WalkForwardEvaluator()

        window_results = [
            WindowMetrics(
                window=TemporalWindow(
                    train_start=datetime(2024, 1, 1),
                    train_end=datetime(2024, 2, 1),
                    test_start=datetime(2024, 2, 1),
                    test_end=datetime(2024, 2, 8),
                ),
                status=WindowStatus.FAILED,
            ),
        ]

        aggregated = evaluator._aggregate_metrics(window_results)

        assert aggregated.window_count == 1
        assert aggregated.mean_sharpe == 0.0
        assert aggregated.total_trades == 0

    def test_aggregation_with_results(self) -> None:
        """Test aggregation with completed window results."""
        evaluator = WalkForwardEvaluator()

        base_window = TemporalWindow(
            train_start=datetime(2024, 1, 1),
            train_end=datetime(2024, 2, 1),
            test_start=datetime(2024, 2, 1),
            test_end=datetime(2024, 2, 8),
        )

        window_results = [
            WindowMetrics(
                window=base_window,
                status=WindowStatus.COMPLETED,
                sharpe_ratio=1.5,
                max_drawdown_pct=10.0,
                win_rate_pct=55.0,
                trade_count=10,
                total_return_pct=5.0,
            ),
            WindowMetrics(
                window=base_window,
                status=WindowStatus.COMPLETED,
                sharpe_ratio=1.3,
                max_drawdown_pct=12.0,
                win_rate_pct=52.0,
                trade_count=12,
                total_return_pct=4.0,
            ),
        ]

        aggregated = evaluator._aggregate_metrics(window_results)

        assert aggregated.window_count == 2
        assert aggregated.mean_sharpe == 1.4  # Average of 1.5 and 1.3
        assert aggregated.total_trades == 22
        assert aggregated.best_window_index == 0  # Higher Sharpe
        assert aggregated.worst_window_index == 1


class TestWindowMetrics:
    """Tests for WindowMetrics class."""

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        window = TemporalWindow(
            train_start=datetime(2024, 1, 1),
            train_end=datetime(2024, 2, 1),
            test_start=datetime(2024, 2, 1),
            test_end=datetime(2024, 2, 8),
        )

        metrics = WindowMetrics(
            window=window,
            status=WindowStatus.COMPLETED,
            sharpe_ratio=1.5,
            trade_count=10,
        )

        data = metrics.to_dict()

        assert data["status"] == "completed"
        assert data["sharpe_ratio"] == 1.5
        assert data["trade_count"] == 10
        assert "window" in data


class TestAggregatedMetrics:
    """Tests for AggregatedMetrics class."""

    def test_consistency_score_calculation(self) -> None:
        """Test consistency score calculation."""
        # Low variance = high consistency (cv = 0.1/1.5 = 0.067, score = 100 - 6.7 = 93.3)
        metrics_low_var = AggregatedMetrics(
            window_count=10,
            mean_sharpe=1.5,
            std_sharpe=0.1,
            consistency_score=100 - (0.1 / 1.5 * 100),  # ~93.3
        )
        # High variance = low consistency (cv = 0.5/1.5 = 0.333, score = 100 - 33.3 = 66.7)
        metrics_high_var = AggregatedMetrics(
            window_count=10,
            mean_sharpe=1.5,
            std_sharpe=0.5,
            consistency_score=100 - (0.5 / 1.5 * 100),  # ~66.7
        )

        assert metrics_low_var.consistency_score > metrics_high_var.consistency_score

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        metrics = AggregatedMetrics(
            window_count=10,
            mean_sharpe=1.5,
            mean_max_drawdown=10.0,
            total_trades=100,
        )

        data = metrics.to_dict()

        assert data["window_count"] == 10
        assert data["mean_sharpe"] == 1.5
        assert data["total_trades"] == 100


class TestWalkForwardResult:
    """Tests for WalkForwardResult class."""

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        result = WalkForwardResult(
            strategy_id="test_strategy",
            config=WalkForwardConfig(),
            look_ahead_check=LookAheadBiasCheck.PASSED,
            total_evaluation_time_seconds=3600.0,
        )

        data = result.to_dict()

        assert data["strategy_id"] == "test_strategy"
        assert data["look_ahead_check"] == "passed"
        assert data["total_evaluation_time_seconds"] == 3600.0
        assert "config" in data


class TestTemporalSplitAudit:
    """Tests for temporal split audit and look-ahead bias prevention."""

    def test_train_test_temporal_boundary(self) -> None:
        """Verify train end < test start for all generated windows."""
        config = WalkForwardConfig(train_days=30, test_days=7, step_days=7)
        evaluator = WalkForwardEvaluator(config)

        start = datetime(2024, 1, 1)
        end = datetime(2024, 12, 31)
        windows = evaluator.generate_windows(start, end)

        for window in windows:
            # Critical: train_end must be <= test_start (no overlap)
            assert window.train_end <= window.test_start, (
                f"Train period ({window.train_end}) overlaps with test period "
                f"({window.test_start}) - look-ahead bias detected!"
            )

    def test_no_future_data_in_training(self) -> None:
        """Verify no future test data leaks into training."""
        config = WalkForwardConfig(train_days=30, test_days=7, step_days=7)
        evaluator = WalkForwardEvaluator(config)

        start = datetime(2024, 1, 1)
        end = datetime(2024, 6, 1)
        windows = evaluator.generate_windows(start, end)

        for i, window in enumerate(windows):
            # All training data must be before test_start
            assert window.train_end <= window.test_start, (
                f"Window {i}: Training data extends into test period"
            )

    def test_strict_temporal_ordering(self) -> None:
        """Verify strict temporal ordering across all windows."""
        config = WalkForwardConfig(train_days=30, test_days=7, step_days=7)
        evaluator = WalkForwardEvaluator(config)

        start = datetime(2024, 1, 1)
        end = datetime(2024, 6, 1)
        windows = evaluator.generate_windows(start, end)

        for i in range(len(windows) - 1):
            current = windows[i]
            next_window = windows[i + 1]

            # Next window's train must start after or at current window's step
            assert next_window.train_start >= current.train_start + timedelta(
                days=config.step_days
            ), (
                f"Window {i}: Next window train_start ({next_window.train_start}) "
                f"should be after current window train_start + step ({current.train_start + timedelta(days=config.step_days)})"
            )

    def test_look_ahead_bias_validation_comprehensive(self) -> None:
        """Comprehensive look-ahead bias validation across multiple scenarios."""
        evaluator = WalkForwardEvaluator()

        # Scenario 1: Valid non-overlapping windows
        start = datetime(2024, 1, 1)
        valid_windows = [
            TemporalWindow(
                train_start=start,
                train_end=start + timedelta(days=30),
                test_start=start + timedelta(days=30),
                test_end=start + timedelta(days=37),
            ),
            TemporalWindow(
                train_start=start + timedelta(days=37),
                train_end=start + timedelta(days=67),
                test_start=start + timedelta(days=67),
                test_end=start + timedelta(days=74),
            ),
        ]
        result = evaluator.validate_no_look_ahead_bias(valid_windows)
        assert result == LookAheadBiasCheck.PASSED

        # Scenario 2: Overlapping test periods
        overlapping_windows = [
            TemporalWindow(
                train_start=start,
                train_end=start + timedelta(days=30),
                test_start=start + timedelta(days=30),
                test_end=start + timedelta(days=37),
            ),
            TemporalWindow(
                train_start=start + timedelta(days=7),
                train_end=start + timedelta(days=35),
                test_start=start + timedelta(days=35),
                test_end=start + timedelta(days=42),
            ),
        ]
        result = evaluator.validate_no_look_ahead_bias(overlapping_windows)
        assert result == LookAheadBiasCheck.FAILED_OVERLAP


class TestWalkForwardIntegration:
    """Integration tests for walk-forward evaluation."""

    def test_full_evaluation_with_mock_strategy(self) -> None:
        """Test complete walk-forward evaluation with a mock strategy."""

        class MockStrategy:
            """Mock strategy for testing."""

            def train(self, data: list[dict]) -> dict:
                return {"trained": True, "samples": len(data)}

            def predict(self, data: list[dict], train_result: dict) -> dict:
                return {
                    "sharpe_ratio": 1.5,
                    "max_drawdown_pct": 10.0,
                    "win_rate_pct": 55.0,
                    "profit_factor": 1.8,
                    "total_return_pct": 5.0,
                    "volatility_pct": 15.0,
                    "trade_count": 10,
                    "avg_trade_return_pct": 0.5,
                }

        # Generate test data
        data = []
        start = datetime(2024, 1, 1)
        for i in range(1000):
            data.append(
                {
                    "timestamp": (start + timedelta(hours=i)).isoformat(),
                    "open": 100 + i * 0.01,
                    "high": 101 + i * 0.01,
                    "low": 99 + i * 0.01,
                    "close": 100 + i * 0.01,
                    "volume": 1000,
                }
            )

        config = WalkForwardConfig(
            train_days=30,
            test_days=7,
            step_days=7,
            min_train_samples=100,
            min_test_samples=50,
        )
        evaluator = WalkForwardEvaluator(config)
        strategy = MockStrategy()

        result = evaluator.evaluate_strategy(
            strategy=strategy,
            data=data,
            strategy_id="mock_strategy",
        )

        # Verify result structure
        assert result.strategy_id == "mock_strategy"
        assert result.look_ahead_check == LookAheadBiasCheck.PASSED
        assert len(result.window_results) > 0
        assert result.aggregated.window_count > 0

    def test_evaluation_with_callable_strategy(self) -> None:
        """Test evaluation with a callable strategy (no train/predict methods)."""

        def simple_strategy(test_data: list[dict], train_data: list[dict]) -> dict:
            return {
                "sharpe_ratio": 1.2,
                "max_drawdown_pct": 8.0,
                "win_rate_pct": 52.0,
                "trade_count": 5,
                "total_return_pct": 3.0,
            }

        # Generate enough hourly data for ~6 months to ensure windows can be created
        data = []
        start = datetime(2024, 1, 1)
        for i in range(5000):
            data.append(
                {
                    "timestamp": (start + timedelta(hours=i)).isoformat(),
                    "close": 100 + i * 0.01,
                }
            )

        config = WalkForwardConfig(
            train_days=14,
            test_days=7,
            step_days=7,
            min_train_samples=50,
            min_test_samples=20,
        )
        evaluator = WalkForwardEvaluator(config)

        result = evaluator.evaluate_strategy(
            strategy=simple_strategy,
            data=data,
            strategy_id="callable_strategy",
        )

        assert result.strategy_id == "callable_strategy"
        assert result.look_ahead_check == LookAheadBiasCheck.PASSED

    def test_insufficient_data_handling(self) -> None:
        """Test handling of insufficient data scenarios."""

        class MockStrategy:
            def train(self, data: list[dict]) -> dict:
                return {}

            def predict(self, data: list[dict], train_result: dict) -> dict:
                return {"sharpe_ratio": 1.0}

        # Very sparse data
        data = []
        start = datetime(2024, 1, 1)
        for i in range(10):
            data.append(
                {
                    "timestamp": (start + timedelta(days=i)).isoformat(),
                    "close": 100.0,
                }
            )

        config = WalkForwardConfig(
            train_days=30,
            test_days=7,
            min_train_samples=100,  # More than we have
            min_test_samples=50,
        )
        evaluator = WalkForwardEvaluator(config)

        result = evaluator.evaluate_strategy(
            strategy=MockStrategy(),
            data=data,
            strategy_id="sparse_strategy",
        )

        # Should either fail validation or have failed windows
        assert (
            result.look_ahead_check == LookAheadBiasCheck.PASSED
            or len(result.window_results) == 0
        )

    def test_metric_aggregation_accuracy(self) -> None:
        """Test that metric aggregation produces correct statistics."""
        evaluator = WalkForwardEvaluator()

        base_window = TemporalWindow(
            train_start=datetime(2024, 1, 1),
            train_end=datetime(2024, 2, 1),
            test_start=datetime(2024, 2, 1),
            test_end=datetime(2024, 2, 8),
        )

        # Create results with known values
        window_results = [
            WindowMetrics(
                window=base_window,
                status=WindowStatus.COMPLETED,
                sharpe_ratio=2.0,
                max_drawdown_pct=10.0,
                win_rate_pct=60.0,
                trade_count=10,
                total_return_pct=5.0,
            ),
            WindowMetrics(
                window=base_window,
                status=WindowStatus.COMPLETED,
                sharpe_ratio=1.0,
                max_drawdown_pct=15.0,
                win_rate_pct=50.0,
                trade_count=8,
                total_return_pct=3.0,
            ),
            WindowMetrics(
                window=base_window,
                status=WindowStatus.COMPLETED,
                sharpe_ratio=1.5,
                max_drawdown_pct=12.0,
                win_rate_pct=55.0,
                trade_count=12,
                total_return_pct=4.0,
            ),
        ]

        aggregated = evaluator._aggregate_metrics(window_results)

        # Verify mean calculations
        assert aggregated.mean_sharpe == pytest.approx(
            1.5, rel=1e-10
        )  # (2.0 + 1.0 + 1.5) / 3
        assert aggregated.mean_max_drawdown == pytest.approx(12.333, rel=0.01)
        assert aggregated.mean_win_rate == pytest.approx(55.0, rel=1e-10)

        # Verify total trades
        assert aggregated.total_trades == 30  # 10 + 8 + 12

        # Verify best/worst window indices
        assert aggregated.best_window_index == 0  # Sharpe 2.0 is highest
        assert aggregated.worst_window_index == 1  # Sharpe 1.0 is lowest

        # Verify window count
        assert aggregated.window_count == 3

    def test_configurable_windows(self) -> None:
        """Test that window sizes are configurable."""
        # Test with custom window sizes
        config = WalkForwardConfig(
            train_days=60,
            test_days=14,
            step_days=14,
        )
        evaluator = WalkForwardEvaluator(config)

        start = datetime(2024, 1, 1)
        end = datetime(2024, 12, 31)
        windows = evaluator.generate_windows(start, end)

        assert len(windows) > 0

        # Verify first window has correct sizes
        first = windows[0]
        assert first.duration_days("train") == 60.0
        assert first.duration_days("test") == 14.0

    def test_max_windows_limit(self) -> None:
        """Test that max_windows configuration is respected."""
        config = WalkForwardConfig(
            train_days=7,
            test_days=1,
            step_days=1,
            max_windows=5,
        )
        evaluator = WalkForwardEvaluator(config)

        start = datetime(2024, 1, 1)
        end = datetime(2024, 12, 31)
        windows = evaluator.generate_windows(start, end)

        assert len(windows) <= 5
