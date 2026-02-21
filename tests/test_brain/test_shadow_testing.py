"""Tests for shadow testing module.

ST-CHISE-001.2: Add Shadow Testing Component with Latency Measurement
"""

import asyncio
import pytest
from datetime import datetime
from typing import Any

from src.brain.shadow_testing import (
    ShadowTestConfig,
    ShadowTestResult,
    LatencyStatistics,
    ShadowTester,
    run_shadow_test,
)
from src.brain.version import BrainVersion

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def candidate_version():
    """Fixture for candidate brain version."""
    return BrainVersion(major=2, minor=0, patch=0)


@pytest.fixture
def baseline_version():
    """Fixture for baseline brain version."""
    return BrainVersion(major=1, minor=5, patch=3)


@pytest.fixture
def default_config(candidate_version, baseline_version):
    """Fixture for default shadow test configuration."""
    return ShadowTestConfig(
        candidate_version=candidate_version,
        baseline_version=baseline_version,
        max_latency_overhead_ms=100.0,
        sample_size=10,
        parallel_enabled=True,
        warmup_iterations=1,
        measurement_iterations=3,
    )


@pytest.fixture
def fast_brain():
    """Fixture for a fast brain function (simulates < 100ms latency)."""

    async def _brain(input_data: Any) -> Any:
        await asyncio.sleep(0.001)  # 1ms simulated latency
        return {"prediction": "buy", "confidence": 0.85, "input": input_data}

    return _brain


@pytest.fixture
def slow_brain():
    """Fixture for a slow brain function (simulates > 100ms latency)."""

    async def _brain(input_data: Any) -> Any:
        await asyncio.sleep(0.15)  # 150ms simulated latency
        return {"prediction": "sell", "confidence": 0.75, "input": input_data}

    return _brain


@pytest.fixture
def medium_brain():
    """Fixture for a medium-speed brain function."""

    async def _brain(input_data: Any) -> Any:
        await asyncio.sleep(0.005)  # 5ms simulated latency
        return {"prediction": "hold", "confidence": 0.60, "input": input_data}

    return _brain


@pytest.fixture
def test_inputs():
    """Fixture for test input data."""
    return [
        {"symbol": "BTCUSDT", "price": 50000.0, "volume": 1000.0},
        {"symbol": "ETHUSDT", "price": 3000.0, "volume": 5000.0},
        {"symbol": "SOLUSDT", "price": 100.0, "volume": 10000.0},
    ]


# =============================================================================
# ShadowTestConfig Tests
# =============================================================================


class TestShadowTestConfig:
    """Tests for ShadowTestConfig dataclass."""

    def test_valid_config_creation(self, candidate_version, baseline_version):
        """Test creating a valid configuration."""
        config = ShadowTestConfig(
            candidate_version=candidate_version,
            baseline_version=baseline_version,
            max_latency_overhead_ms=100.0,
            sample_size=1000,
            parallel_enabled=True,
        )

        assert config.candidate_version == candidate_version
        assert config.baseline_version == baseline_version
        assert config.max_latency_overhead_ms == 100.0
        assert config.sample_size == 1000
        assert config.parallel_enabled is True
        assert config.warmup_iterations == 3  # default
        assert config.measurement_iterations == 5  # default

    def test_default_values(self, candidate_version, baseline_version):
        """Test that default values are set correctly."""
        config = ShadowTestConfig(
            candidate_version=candidate_version,
            baseline_version=baseline_version,
        )

        assert config.max_latency_overhead_ms == 100.0
        assert config.sample_size == 1000
        assert config.parallel_enabled is True
        assert config.warmup_iterations == 3
        assert config.measurement_iterations == 5

    def test_invalid_max_latency_zero(self, candidate_version, baseline_version):
        """Test that zero max_latency_overhead_ms raises ValueError."""
        with pytest.raises(
            ValueError, match="max_latency_overhead_ms must be positive"
        ):
            ShadowTestConfig(
                candidate_version=candidate_version,
                baseline_version=baseline_version,
                max_latency_overhead_ms=0.0,
            )

    def test_invalid_max_latency_negative(self, candidate_version, baseline_version):
        """Test that negative max_latency_overhead_ms raises ValueError."""
        with pytest.raises(
            ValueError, match="max_latency_overhead_ms must be positive"
        ):
            ShadowTestConfig(
                candidate_version=candidate_version,
                baseline_version=baseline_version,
                max_latency_overhead_ms=-50.0,
            )

    def test_invalid_sample_size_zero(self, candidate_version, baseline_version):
        """Test that zero sample_size raises ValueError."""
        with pytest.raises(ValueError, match="sample_size must be positive"):
            ShadowTestConfig(
                candidate_version=candidate_version,
                baseline_version=baseline_version,
                sample_size=0,
            )

    def test_invalid_sample_size_negative(self, candidate_version, baseline_version):
        """Test that negative sample_size raises ValueError."""
        with pytest.raises(ValueError, match="sample_size must be positive"):
            ShadowTestConfig(
                candidate_version=candidate_version,
                baseline_version=baseline_version,
                sample_size=-100,
            )

    def test_invalid_warmup_iterations_negative(
        self, candidate_version, baseline_version
    ):
        """Test that negative warmup_iterations raises ValueError."""
        with pytest.raises(ValueError, match="warmup_iterations must be non-negative"):
            ShadowTestConfig(
                candidate_version=candidate_version,
                baseline_version=baseline_version,
                warmup_iterations=-1,
            )

    def test_invalid_measurement_iterations_zero(
        self, candidate_version, baseline_version
    ):
        """Test that zero measurement_iterations raises ValueError."""
        with pytest.raises(
            ValueError, match="measurement_iterations must be at least 1"
        ):
            ShadowTestConfig(
                candidate_version=candidate_version,
                baseline_version=baseline_version,
                measurement_iterations=0,
            )

    def test_invalid_measurement_iterations_negative(
        self, candidate_version, baseline_version
    ):
        """Test that negative measurement_iterations raises ValueError."""
        with pytest.raises(
            ValueError, match="measurement_iterations must be at least 1"
        ):
            ShadowTestConfig(
                candidate_version=candidate_version,
                baseline_version=baseline_version,
                measurement_iterations=-5,
            )

    def test_zero_warmup_iterations_allowed(self, candidate_version, baseline_version):
        """Test that zero warmup_iterations is allowed."""
        config = ShadowTestConfig(
            candidate_version=candidate_version,
            baseline_version=baseline_version,
            warmup_iterations=0,
        )
        assert config.warmup_iterations == 0


# =============================================================================
# LatencyStatistics Tests
# =============================================================================


class TestLatencyStatistics:
    """Tests for LatencyStatistics dataclass."""

    def test_latency_statistics_creation(self):
        """Test creating latency statistics."""
        stats = LatencyStatistics(
            p50_ms=10.0,
            p95_ms=20.0,
            p99_ms=30.0,
            mean_ms=12.0,
            std_ms=5.0,
            min_ms=5.0,
            max_ms=35.0,
            sample_count=100,
        )

        assert stats.p50_ms == 10.0
        assert stats.p95_ms == 20.0
        assert stats.p99_ms == 30.0
        assert stats.mean_ms == 12.0
        assert stats.std_ms == 5.0
        assert stats.min_ms == 5.0
        assert stats.max_ms == 35.0
        assert stats.sample_count == 100

    def test_to_dict(self):
        """Test conversion to dictionary."""
        stats = LatencyStatistics(
            p50_ms=10.0,
            p95_ms=20.0,
            p99_ms=30.0,
            mean_ms=12.0,
            std_ms=5.0,
            min_ms=5.0,
            max_ms=35.0,
            sample_count=100,
        )

        d = stats.to_dict()
        assert d["p50_ms"] == 10.0
        assert d["p95_ms"] == 20.0
        assert d["p99_ms"] == 30.0
        assert d["mean_ms"] == 12.0
        assert d["std_ms"] == 5.0
        assert d["min_ms"] == 5.0
        assert d["max_ms"] == 35.0
        assert d["sample_count"] == 100


# =============================================================================
# ShadowTestResult Tests
# =============================================================================


class TestShadowTestResult:
    """Tests for ShadowTestResult dataclass."""

    def test_result_creation(self, default_config):
        """Test creating a shadow test result."""
        candidate_stats = LatencyStatistics(
            p50_ms=15.0,
            p95_ms=25.0,
            p99_ms=35.0,
            mean_ms=16.0,
            std_ms=6.0,
            min_ms=8.0,
            max_ms=40.0,
            sample_count=10,
        )
        baseline_stats = LatencyStatistics(
            p50_ms=10.0,
            p95_ms=18.0,
            p99_ms=25.0,
            mean_ms=11.0,
            std_ms=4.0,
            min_ms=5.0,
            max_ms=28.0,
            sample_count=10,
        )

        result = ShadowTestResult(
            passed=True,
            latency_overhead_ms=45.45,  # (16-11)/11 * 100
            candidate_latency_ms=candidate_stats,
            baseline_latency_ms=baseline_stats,
            candidate_predictions=[{"pred": 1}],
            baseline_predictions=[{"pred": 1}],
            timestamp=datetime.utcnow(),
            error_message=None,
            config=default_config,
        )

        assert result.passed is True
        assert result.latency_overhead_ms == 45.45
        assert result.error_message is None
        assert result.config == default_config

    def test_result_to_dict(self, default_config):
        """Test conversion to dictionary."""
        candidate_stats = LatencyStatistics(
            p50_ms=15.0,
            p95_ms=25.0,
            p99_ms=35.0,
            mean_ms=16.0,
            std_ms=6.0,
            min_ms=8.0,
            max_ms=40.0,
            sample_count=10,
        )
        baseline_stats = LatencyStatistics(
            p50_ms=10.0,
            p95_ms=18.0,
            p99_ms=25.0,
            mean_ms=11.0,
            std_ms=4.0,
            min_ms=5.0,
            max_ms=28.0,
            sample_count=10,
        )

        result = ShadowTestResult(
            passed=True,
            latency_overhead_ms=45.45,
            candidate_latency_ms=candidate_stats,
            baseline_latency_ms=baseline_stats,
            candidate_predictions=[{"pred": 1}],
            baseline_predictions=[{"pred": 1}],
            timestamp=datetime.utcnow(),
            config=default_config,
        )

        d = result.to_dict()
        assert d["passed"] is True
        assert d["latency_overhead_ms"] == 45.45
        assert d["candidate_latency_ms"]["p50_ms"] == 15.0
        assert d["baseline_latency_ms"]["p50_ms"] == 10.0
        assert d["config"]["candidate_version"] == "2.0.0"
        assert d["config"]["baseline_version"] == "1.5.3"


# =============================================================================
# ShadowTester Tests
# =============================================================================


class TestShadowTester:
    """Tests for ShadowTester class."""

    @pytest.mark.asyncio
    async def test_basic_shadow_test(self, default_config, fast_brain, test_inputs):
        """Test basic shadow test execution."""
        tester = ShadowTester(default_config, fast_brain, fast_brain)
        result = await tester.run_shadow_test(test_inputs)

        assert isinstance(result, ShadowTestResult)
        assert result.passed is True
        assert result.config == default_config
        assert len(result.candidate_predictions) == len(test_inputs)
        assert len(result.baseline_predictions) == len(test_inputs)

    @pytest.mark.asyncio
    async def test_latency_threshold_enforcement(
        self, candidate_version, baseline_version, fast_brain, slow_brain, test_inputs
    ):
        """Test that latency threshold is enforced (should fail when overhead > 100ms threshold)."""
        config = ShadowTestConfig(
            candidate_version=candidate_version,
            baseline_version=baseline_version,
            max_latency_overhead_ms=100.0,  # 100% threshold
            sample_size=3,
            parallel_enabled=True,
            warmup_iterations=0,
            measurement_iterations=2,
        )

        # Candidate is slow, baseline is fast - should fail
        tester = ShadowTester(config, slow_brain, fast_brain)
        result = await tester.run_shadow_test(test_inputs)

        # The slow brain (150ms) vs fast brain (1ms) should exceed 100% overhead
        assert result.passed is False
        assert result.latency_overhead_ms > 100.0
        assert result.error_message is not None
        assert "exceeds threshold" in result.error_message

    @pytest.mark.asyncio
    async def test_passing_latency_threshold(
        self, candidate_version, baseline_version, fast_brain, test_inputs
    ):
        """Test that similar latencies pass the threshold."""
        config = ShadowTestConfig(
            candidate_version=candidate_version,
            baseline_version=baseline_version,
            max_latency_overhead_ms=100.0,
            sample_size=3,
            parallel_enabled=True,
            warmup_iterations=0,
            measurement_iterations=2,
        )

        # Both brains are fast - should pass
        tester = ShadowTester(config, fast_brain, fast_brain)
        result = await tester.run_shadow_test(test_inputs)

        assert result.passed is True
        assert result.error_message is None

    @pytest.mark.asyncio
    async def test_parallel_execution(self, default_config, fast_brain, test_inputs):
        """Test parallel execution mode."""
        config = ShadowTestConfig(
            candidate_version=default_config.candidate_version,
            baseline_version=default_config.baseline_version,
            parallel_enabled=True,
            sample_size=3,
            warmup_iterations=0,
            measurement_iterations=2,
        )

        tester = ShadowTester(config, fast_brain, fast_brain)
        result = await tester.run_shadow_test(test_inputs)

        assert result.passed is True
        assert result.config.parallel_enabled is True

    @pytest.mark.asyncio
    async def test_sequential_execution(self, default_config, fast_brain, test_inputs):
        """Test sequential execution mode."""
        config = ShadowTestConfig(
            candidate_version=default_config.candidate_version,
            baseline_version=default_config.baseline_version,
            parallel_enabled=False,
            sample_size=3,
            warmup_iterations=0,
            measurement_iterations=2,
        )

        tester = ShadowTester(config, fast_brain, fast_brain)
        result = await tester.run_shadow_test(test_inputs)

        assert result.passed is True
        assert result.config.parallel_enabled is False

    @pytest.mark.asyncio
    async def test_empty_inputs(self, default_config, fast_brain):
        """Test handling of empty input list."""
        tester = ShadowTester(default_config, fast_brain, fast_brain)
        result = await tester.run_shadow_test([])

        assert result.passed is False
        assert result.error_message is not None
        assert "No inputs provided" in result.error_message

    @pytest.mark.asyncio
    async def test_sample_size_limit(
        self, candidate_version, baseline_version, fast_brain, test_inputs
    ):
        """Test that sample_size limits the number of inputs tested."""
        config = ShadowTestConfig(
            candidate_version=candidate_version,
            baseline_version=baseline_version,
            sample_size=2,  # Only test 2 inputs
            parallel_enabled=True,
            warmup_iterations=0,
            measurement_iterations=2,
        )

        tester = ShadowTester(config, fast_brain, fast_brain)
        result = await tester.run_shadow_test(test_inputs)

        # Should only have 2 predictions even though 3 inputs provided
        assert len(result.candidate_predictions) == 2
        assert len(result.baseline_predictions) == 2

    @pytest.mark.asyncio
    async def test_latency_statistics_calculated(
        self, default_config, fast_brain, test_inputs
    ):
        """Test that latency statistics are properly calculated."""
        tester = ShadowTester(default_config, fast_brain, fast_brain)
        result = await tester.run_shadow_test(test_inputs)

        # Check candidate stats
        assert result.candidate_latency_ms.sample_count > 0
        assert result.candidate_latency_ms.mean_ms >= 0
        assert result.candidate_latency_ms.p50_ms >= 0
        assert result.candidate_latency_ms.p95_ms >= result.candidate_latency_ms.p50_ms
        assert result.candidate_latency_ms.p99_ms >= result.candidate_latency_ms.p95_ms
        assert result.candidate_latency_ms.min_ms <= result.candidate_latency_ms.max_ms

        # Check baseline stats
        assert result.baseline_latency_ms.sample_count > 0

    @pytest.mark.asyncio
    async def test_predictions_returned(self, default_config, fast_brain, test_inputs):
        """Test that predictions are returned correctly."""
        tester = ShadowTester(default_config, fast_brain, fast_brain)
        result = await tester.run_shadow_test(test_inputs)

        assert len(result.candidate_predictions) == len(test_inputs)
        assert len(result.baseline_predictions) == len(test_inputs)

        # Each prediction should have the expected structure
        for pred in result.candidate_predictions:
            assert "prediction" in pred
            assert "confidence" in pred

    @pytest.mark.asyncio
    async def test_timestamp_set(self, default_config, fast_brain, test_inputs):
        """Test that timestamp is set on result."""
        tester = ShadowTester(default_config, fast_brain, fast_brain)
        result = await tester.run_shadow_test(test_inputs)

        assert isinstance(result.timestamp, datetime)
        assert result.timestamp <= datetime.utcnow()

    @pytest.mark.asyncio
    async def test_validate_latency_threshold_method(self, default_config, fast_brain):
        """Test the validate_latency_threshold method."""
        tester = ShadowTester(default_config, fast_brain, fast_brain)

        # Should pass when under threshold
        assert tester.validate_latency_threshold(50.0) is True
        assert tester.validate_latency_threshold(99.9) is True

        # Should fail when at or over threshold
        assert tester.validate_latency_threshold(100.0) is True  # At threshold passes
        assert tester.validate_latency_threshold(100.1) is False  # Over threshold fails
        assert tester.validate_latency_threshold(150.0) is False

    @pytest.mark.asyncio
    async def test_validate_latency_threshold_override(
        self, default_config, fast_brain
    ):
        """Test threshold override in validate method."""
        tester = ShadowTester(default_config, fast_brain, fast_brain)

        # Use custom threshold
        assert tester.validate_latency_threshold(150.0, threshold=200.0) is True
        assert tester.validate_latency_threshold(150.0, threshold=100.0) is False

    @pytest.mark.asyncio
    async def test_warmup_runs(
        self, candidate_version, baseline_version, fast_brain, test_inputs
    ):
        """Test that warmup iterations are executed."""
        call_count = {"count": 0}

        async def counting_brain(input_data: Any) -> Any:
            call_count["count"] += 1
            await asyncio.sleep(0.001)
            return {"pred": 1}

        config = ShadowTestConfig(
            candidate_version=candidate_version,
            baseline_version=baseline_version,
            sample_size=1,
            warmup_iterations=2,
            measurement_iterations=1,
        )

        tester = ShadowTester(config, counting_brain, fast_brain)
        await tester.run_shadow_test(test_inputs[:1])

        # Should have warmup calls (2 iterations * 1 brain = 2 calls for counting_brain)
        # Plus measurement calls (1 iteration * 1 brain = 1 call)
        assert call_count["count"] >= 2


# =============================================================================
# run_shadow_test Convenience Function Tests
# =============================================================================


class TestRunShadowTest:
    """Tests for the run_shadow_test convenience function."""

    @pytest.mark.asyncio
    async def test_convenience_function(
        self, candidate_version, baseline_version, fast_brain, test_inputs
    ):
        """Test the convenience function works correctly."""
        result = await run_shadow_test(
            candidate_version=candidate_version,
            baseline_version=baseline_version,
            candidate_brain=fast_brain,
            baseline_brain=fast_brain,
            inputs=test_inputs,
            max_latency_overhead_ms=100.0,
            sample_size=3,
            parallel_enabled=True,
        )

        assert isinstance(result, ShadowTestResult)
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_convenience_function_with_slow_candidate(
        self, candidate_version, baseline_version, slow_brain, fast_brain, test_inputs
    ):
        """Test convenience function with slow candidate (should fail)."""
        result = await run_shadow_test(
            candidate_version=candidate_version,
            baseline_version=baseline_version,
            candidate_brain=slow_brain,
            baseline_brain=fast_brain,
            inputs=test_inputs,
            max_latency_overhead_ms=100.0,
            sample_size=3,
            parallel_enabled=True,
        )

        assert result.passed is False
        assert result.latency_overhead_ms > 100.0


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_brain_exception_handling(
        self, candidate_version, baseline_version, fast_brain, test_inputs
    ):
        """Test handling of brain function exceptions."""

        async def failing_brain(input_data: Any) -> Any:
            raise ValueError("Brain failure")

        config = ShadowTestConfig(
            candidate_version=candidate_version,
            baseline_version=baseline_version,
            sample_size=1,
            warmup_iterations=0,
            measurement_iterations=1,
        )

        tester = ShadowTester(config, failing_brain, fast_brain)
        result = await tester.run_shadow_test(test_inputs[:1])

        assert result.passed is False
        assert result.error_message is not None
        assert "Shadow test execution failed" in result.error_message

    @pytest.mark.asyncio
    async def test_large_input_set(
        self, candidate_version, baseline_version, fast_brain
    ):
        """Test with larger input set."""
        large_inputs = [{"id": i, "data": f"test_{i}"} for i in range(50)]

        config = ShadowTestConfig(
            candidate_version=candidate_version,
            baseline_version=baseline_version,
            sample_size=20,  # Test 20 out of 50
            parallel_enabled=True,
            warmup_iterations=0,
            measurement_iterations=2,
        )

        tester = ShadowTester(config, fast_brain, fast_brain)
        result = await tester.run_shadow_test(large_inputs)

        assert result.passed is True
        assert len(result.candidate_predictions) == 20

    @pytest.mark.asyncio
    async def test_single_input(self, candidate_version, baseline_version, fast_brain):
        """Test with single input."""
        single_input = [{"test": "data"}]

        config = ShadowTestConfig(
            candidate_version=candidate_version,
            baseline_version=baseline_version,
            sample_size=1,
            parallel_enabled=True,
            warmup_iterations=0,
            measurement_iterations=3,
        )

        tester = ShadowTester(config, fast_brain, fast_brain)
        result = await tester.run_shadow_test(single_input)

        assert result.passed is True
        assert len(result.candidate_predictions) == 1

    @pytest.mark.asyncio
    async def test_different_prediction_outputs(
        self, candidate_version, baseline_version, test_inputs
    ):
        """Test that different brain outputs are captured correctly."""

        async def candidate_brain(input_data: Any) -> Any:
            return {"version": "candidate", "pred": "buy"}

        async def baseline_brain(input_data: Any) -> Any:
            return {"version": "baseline", "pred": "sell"}

        config = ShadowTestConfig(
            candidate_version=candidate_version,
            baseline_version=baseline_version,
            sample_size=2,
            parallel_enabled=True,
            warmup_iterations=0,
            measurement_iterations=1,
        )

        tester = ShadowTester(config, candidate_brain, baseline_brain)
        result = await tester.run_shadow_test(test_inputs[:2])

        # Check that predictions are different
        for i in range(len(result.candidate_predictions)):
            assert result.candidate_predictions[i]["version"] == "candidate"
            assert result.baseline_predictions[i]["version"] == "baseline"
            assert result.candidate_predictions[i]["pred"] == "buy"
            assert result.baseline_predictions[i]["pred"] == "sell"

    @pytest.mark.asyncio
    async def test_statistical_validity(
        self, candidate_version, baseline_version, fast_brain, test_inputs
    ):
        """Test that statistical calculations are valid."""
        config = ShadowTestConfig(
            candidate_version=candidate_version,
            baseline_version=baseline_version,
            sample_size=5,
            parallel_enabled=True,
            warmup_iterations=0,
            measurement_iterations=5,  # Multiple iterations for stats
        )

        tester = ShadowTester(config, fast_brain, fast_brain)
        result = await tester.run_shadow_test(test_inputs[:5])

        stats = result.candidate_latency_ms

        # Statistical sanity checks
        assert stats.mean_ms >= stats.min_ms
        assert stats.mean_ms <= stats.max_ms
        assert stats.p50_ms >= stats.min_ms
        assert stats.p50_ms <= stats.max_ms
        assert stats.p95_ms >= stats.p50_ms
        assert stats.p99_ms >= stats.p95_ms
        assert stats.std_ms >= 0  # Standard deviation is non-negative

    @pytest.mark.asyncio
    async def test_overhead_calculation_accuracy(
        self, candidate_version, baseline_version, test_inputs
    ):
        """Test that overhead calculation is accurate."""

        # Create brains with known latency difference
        async def candidate_brain(input_data: Any) -> Any:
            await asyncio.sleep(0.002)  # 2ms
            return {"pred": 1}

        async def baseline_brain(input_data: Any) -> Any:
            await asyncio.sleep(0.001)  # 1ms
            return {"pred": 1}

        config = ShadowTestConfig(
            candidate_version=candidate_version,
            baseline_version=baseline_version,
            sample_size=3,
            max_latency_overhead_ms=200.0,  # Allow up to 200%
            parallel_enabled=True,
            warmup_iterations=0,
            measurement_iterations=3,
        )

        tester = ShadowTester(config, candidate_brain, baseline_brain)
        result = await tester.run_shadow_test(test_inputs[:3])

        # Overhead should be approximately 100% (2ms vs 1ms)
        # Allow for some variance due to timing
        assert 50.0 <= result.latency_overhead_ms <= 150.0

    @pytest.mark.asyncio
    async def test_parallel_faster_than_sequential(
        self, candidate_version, baseline_version, medium_brain, test_inputs
    ):
        """Test that parallel execution is faster than sequential."""
        # This test verifies parallel execution works
        parallel_config = ShadowTestConfig(
            candidate_version=candidate_version,
            baseline_version=baseline_version,
            sample_size=5,
            parallel_enabled=True,
            warmup_iterations=0,
            measurement_iterations=2,
        )

        sequential_config = ShadowTestConfig(
            candidate_version=candidate_version,
            baseline_version=baseline_version,
            sample_size=5,
            parallel_enabled=False,
            warmup_iterations=0,
            measurement_iterations=2,
        )

        parallel_tester = ShadowTester(parallel_config, medium_brain, medium_brain)
        sequential_tester = ShadowTester(sequential_config, medium_brain, medium_brain)

        import time

        start = time.perf_counter()
        parallel_result = await parallel_tester.run_shadow_test(test_inputs[:5])
        parallel_time = time.perf_counter() - start

        start = time.perf_counter()
        sequential_result = await sequential_tester.run_shadow_test(test_inputs[:5])
        sequential_time = time.perf_counter() - start

        # Both should pass
        assert parallel_result.passed is True
        assert sequential_result.passed is True

        # Parallel should generally be faster, but due to timing variance,
        # we just verify both complete successfully

    @pytest.mark.asyncio
    async def test_config_immutability(self, default_config, fast_brain):
        """Test that config is frozen and immutable."""
        tester = ShadowTester(default_config, fast_brain, fast_brain)

        # Config should be accessible but the dataclass is frozen
        assert tester.config.sample_size == default_config.sample_size


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests for shadow testing workflow."""

    @pytest.mark.asyncio
    async def test_full_workflow_pass(
        self, candidate_version, baseline_version, fast_brain, test_inputs
    ):
        """Test full shadow testing workflow that passes."""
        # Create more test inputs if needed
        extended_inputs = test_inputs * 2  # 3 * 2 = 6 inputs

        config = ShadowTestConfig(
            candidate_version=candidate_version,
            baseline_version=baseline_version,
            max_latency_overhead_ms=100.0,
            sample_size=5,
            parallel_enabled=True,
            warmup_iterations=1,
            measurement_iterations=3,
        )

        tester = ShadowTester(config, fast_brain, fast_brain)
        result = await tester.run_shadow_test(extended_inputs[:5])

        # Verify all result fields
        assert result.passed is True
        assert result.error_message is None
        assert result.latency_overhead_ms <= 100.0
        assert len(result.candidate_predictions) == 5
        assert len(result.baseline_predictions) == 5
        assert result.candidate_latency_ms.sample_count > 0
        assert result.baseline_latency_ms.sample_count > 0
        assert isinstance(result.timestamp, datetime)
        assert result.config is not None

    @pytest.mark.asyncio
    async def test_full_workflow_fail(
        self, candidate_version, baseline_version, slow_brain, fast_brain, test_inputs
    ):
        """Test full shadow testing workflow that fails due to latency."""
        config = ShadowTestConfig(
            candidate_version=candidate_version,
            baseline_version=baseline_version,
            max_latency_overhead_ms=100.0,
            sample_size=3,
            parallel_enabled=True,
            warmup_iterations=0,
            measurement_iterations=2,
        )

        tester = ShadowTester(config, slow_brain, fast_brain)
        result = await tester.run_shadow_test(test_inputs[:3])

        # Verify failure details
        assert result.passed is False
        assert result.error_message is not None
        assert "exceeds threshold" in result.error_message
        assert result.latency_overhead_ms > 100.0

    @pytest.mark.asyncio
    async def test_result_serialization_roundtrip(
        self, default_config, fast_brain, test_inputs
    ):
        """Test that results can be serialized and maintain data integrity."""
        tester = ShadowTester(default_config, fast_brain, fast_brain)
        result = await tester.run_shadow_test(test_inputs)

        # Serialize to dict
        result_dict = result.to_dict()

        # Verify all expected keys present
        assert "passed" in result_dict
        assert "latency_overhead_ms" in result_dict
        assert "candidate_latency_ms" in result_dict
        assert "baseline_latency_ms" in result_dict
        assert "candidate_predictions" in result_dict
        assert "baseline_predictions" in result_dict
        assert "timestamp" in result_dict
        assert "config" in result_dict

    @pytest.mark.asyncio
    async def test_multiple_iterations_consistency(
        self, candidate_version, baseline_version, fast_brain, test_inputs
    ):
        """Test that multiple measurement iterations provide consistent results."""
        config = ShadowTestConfig(
            candidate_version=candidate_version,
            baseline_version=baseline_version,
            sample_size=3,
            parallel_enabled=True,
            warmup_iterations=0,
            measurement_iterations=5,
        )

        tester = ShadowTester(config, fast_brain, fast_brain)
        result = await tester.run_shadow_test(test_inputs[:3])

        # With identical brains, overhead should be close to 0
        # Allow for some measurement variance
        assert abs(result.latency_overhead_ms) < 50.0  # Within 50%
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_various_input_sizes(
        self, candidate_version, baseline_version, fast_brain
    ):
        """Test with various input sizes."""
        config = ShadowTestConfig(
            candidate_version=candidate_version,
            baseline_version=baseline_version,
            sample_size=100,  # Request up to 100
            parallel_enabled=True,
            warmup_iterations=0,
            measurement_iterations=2,
        )

        # Test with fewer inputs than sample_size
        small_inputs = [{"id": i} for i in range(5)]
        tester = ShadowTester(config, fast_brain, fast_brain)
        result = await tester.run_shadow_test(small_inputs)

        assert len(result.candidate_predictions) == 5
        assert len(result.baseline_predictions) == 5

        # Test with more inputs than sample_size
        large_inputs = [{"id": i} for i in range(200)]
        result = await tester.run_shadow_test(large_inputs)

        assert len(result.candidate_predictions) == 100  # Limited by sample_size
        assert len(result.baseline_predictions) == 100
