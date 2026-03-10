"""Smoke tests for brain shadow testing module.

Verifies basic functionality and imports for the shadow testing framework.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from brain.shadow_testing import (
    BrainFunction,
    LatencyStatistics,
    ShadowTester,
    ShadowTestConfig,
    ShadowTestResult,
    run_shadow_test,
)
from brain.version import BrainVersion


class TestShadowTestConfigSmoke:
    """Smoke tests for ShadowTestConfig class."""

    def test_config_creation(self) -> None:
        """Test creating shadow test config."""
        candidate = BrainVersion(1, 1, 0)
        baseline = BrainVersion(1, 0, 0)

        config = ShadowTestConfig(
            candidate_version=candidate,
            baseline_version=baseline,
            max_latency_overhead_ms=50.0,
            sample_size=100,
        )

        assert config.candidate_version == candidate
        assert config.baseline_version == baseline
        assert config.max_latency_overhead_ms == 50.0
        assert config.sample_size == 100

    def test_config_defaults(self) -> None:
        """Test config default values."""
        candidate = BrainVersion(1, 1, 0)
        baseline = BrainVersion(1, 0, 0)

        config = ShadowTestConfig(
            candidate_version=candidate,
            baseline_version=baseline,
        )

        assert config.max_latency_overhead_ms == 100.0
        assert config.sample_size == 1000
        assert config.parallel_enabled is True
        assert config.warmup_iterations == 3
        assert config.measurement_iterations == 5

    def test_config_validation_latency(self) -> None:
        """Test config validation for latency."""
        candidate = BrainVersion(1, 1, 0)
        baseline = BrainVersion(1, 0, 0)

        with pytest.raises(ValueError, match="max_latency_overhead_ms"):
            ShadowTestConfig(
                candidate_version=candidate,
                baseline_version=baseline,
                max_latency_overhead_ms=0,
            )

    def test_config_validation_sample_size(self) -> None:
        """Test config validation for sample size."""
        candidate = BrainVersion(1, 1, 0)
        baseline = BrainVersion(1, 0, 0)

        with pytest.raises(ValueError, match="sample_size"):
            ShadowTestConfig(
                candidate_version=candidate,
                baseline_version=baseline,
                sample_size=-1,
            )


class TestLatencyStatisticsSmoke:
    """Smoke tests for LatencyStatistics class."""

    def test_statistics_creation(self) -> None:
        """Test creating latency statistics."""
        stats = LatencyStatistics(
            p50_ms=10.0,
            p95_ms=20.0,
            p99_ms=30.0,
            mean_ms=12.0,
            std_ms=5.0,
            min_ms=8.0,
            max_ms=35.0,
            sample_count=100,
        )

        assert stats.p50_ms == 10.0
        assert stats.p95_ms == 20.0
        assert stats.p99_ms == 30.0
        assert stats.mean_ms == 12.0
        assert stats.sample_count == 100

    def test_statistics_to_dict(self) -> None:
        """Test converting statistics to dict."""
        stats = LatencyStatistics(
            p50_ms=10.0,
            p95_ms=20.0,
            p99_ms=30.0,
            mean_ms=12.0,
            std_ms=5.0,
            min_ms=8.0,
            max_ms=35.0,
            sample_count=100,
        )

        data = stats.to_dict()
        assert data["p50_ms"] == 10.0
        assert data["p95_ms"] == 20.0
        assert data["sample_count"] == 100


class TestShadowTestResultSmoke:
    """Smoke tests for ShadowTestResult class."""

    def test_result_creation(self) -> None:
        """Test creating shadow test result."""
        candidate_stats = LatencyStatistics(
            p50_ms=10.0,
            p95_ms=20.0,
            p99_ms=30.0,
            mean_ms=12.0,
            std_ms=5.0,
            min_ms=8.0,
            max_ms=35.0,
            sample_count=100,
        )
        baseline_stats = LatencyStatistics(
            p50_ms=8.0,
            p95_ms=15.0,
            p99_ms=25.0,
            mean_ms=10.0,
            std_ms=4.0,
            min_ms=6.0,
            max_ms=30.0,
            sample_count=100,
        )

        result = ShadowTestResult(
            passed=True,
            latency_overhead_ms=20.0,
            candidate_latency_ms=candidate_stats,
            baseline_latency_ms=baseline_stats,
            candidate_predictions=[1, 2, 3],
            baseline_predictions=[1, 2, 3],
            timestamp=datetime.utcnow(),
        )

        assert result.passed is True
        assert result.latency_overhead_ms == 20.0
        assert len(result.candidate_predictions) == 3

    def test_result_to_dict(self) -> None:
        """Test converting result to dict."""
        candidate_stats = LatencyStatistics(
            p50_ms=10.0,
            p95_ms=20.0,
            p99_ms=30.0,
            mean_ms=12.0,
            std_ms=5.0,
            min_ms=8.0,
            max_ms=35.0,
            sample_count=100,
        )
        baseline_stats = LatencyStatistics(
            p50_ms=8.0,
            p95_ms=15.0,
            p99_ms=25.0,
            mean_ms=10.0,
            std_ms=4.0,
            min_ms=6.0,
            max_ms=30.0,
            sample_count=100,
        )

        result = ShadowTestResult(
            passed=True,
            latency_overhead_ms=20.0,
            candidate_latency_ms=candidate_stats,
            baseline_latency_ms=baseline_stats,
            candidate_predictions=[1, 2],
            baseline_predictions=[1, 2],
            timestamp=datetime.utcnow(),
            error_message=None,
        )

        data = result.to_dict()
        assert data["passed"] is True
        assert data["latency_overhead_ms"] == 20.0
        assert "candidate_latency_ms" in data
        assert "baseline_latency_ms" in data


class TestShadowTesterSmoke:
    """Smoke tests for ShadowTester class."""

    def test_tester_creation(self) -> None:
        """Test creating shadow tester."""
        candidate = BrainVersion(1, 1, 0)
        baseline = BrainVersion(1, 0, 0)
        config = ShadowTestConfig(
            candidate_version=candidate,
            baseline_version=baseline,
        )

        async def mock_brain(x):
            return x

        tester = ShadowTester(config, mock_brain, mock_brain)

        assert tester.config == config
        assert tester.candidate_brain == mock_brain
        assert tester.baseline_brain == mock_brain

    @pytest.mark.asyncio
    async def test_run_shadow_test_empty_inputs(self) -> None:
        """Test shadow test with empty inputs."""
        candidate = BrainVersion(1, 1, 0)
        baseline = BrainVersion(1, 0, 0)
        config = ShadowTestConfig(
            candidate_version=candidate,
            baseline_version=baseline,
        )

        async def mock_brain(x):
            return x

        tester = ShadowTester(config, mock_brain, mock_brain)
        result = await tester.run_shadow_test([])

        assert result.passed is False
        assert "No inputs" in result.error_message

    @pytest.mark.asyncio
    async def test_run_shadow_test_with_inputs(self) -> None:
        """Test shadow test with valid inputs."""
        candidate = BrainVersion(1, 1, 0)
        baseline = BrainVersion(1, 0, 0)
        config = ShadowTestConfig(
            candidate_version=candidate,
            baseline_version=baseline,
            sample_size=5,
            warmup_iterations=0,
            measurement_iterations=1,
        )

        async def mock_brain(x):
            return x

        tester = ShadowTester(config, mock_brain, mock_brain)
        inputs = [{"data": i} for i in range(5)]
        result = await tester.run_shadow_test(inputs)

        assert result.timestamp is not None
        assert result.candidate_latency_ms is not None
        assert result.baseline_latency_ms is not None

    @pytest.mark.asyncio
    async def test_run_shadow_test_sequential(self) -> None:
        """Test shadow test in sequential mode."""
        candidate = BrainVersion(1, 1, 0)
        baseline = BrainVersion(1, 0, 0)
        config = ShadowTestConfig(
            candidate_version=candidate,
            baseline_version=baseline,
            sample_size=3,
            parallel_enabled=False,
            warmup_iterations=0,
            measurement_iterations=1,
        )

        async def mock_brain(x):
            return x

        tester = ShadowTester(config, mock_brain, mock_brain)
        inputs = [{"data": i} for i in range(3)]
        result = await tester.run_shadow_test(inputs)

        assert result.candidate_latency_ms.sample_count == 3
        assert result.baseline_latency_ms.sample_count == 3

    def test_validate_latency_threshold(self) -> None:
        """Test latency threshold validation."""
        candidate = BrainVersion(1, 1, 0)
        baseline = BrainVersion(1, 0, 0)
        config = ShadowTestConfig(
            candidate_version=candidate,
            baseline_version=baseline,
            max_latency_overhead_ms=50.0,
        )

        async def mock_brain(x):
            return x

        tester = ShadowTester(config, mock_brain, mock_brain)

        assert tester.validate_latency_threshold(40.0) is True
        assert tester.validate_latency_threshold(60.0) is False

    def test_validate_latency_threshold_custom(self) -> None:
        """Test latency threshold validation with custom value."""
        candidate = BrainVersion(1, 1, 0)
        baseline = BrainVersion(1, 0, 0)
        config = ShadowTestConfig(
            candidate_version=candidate,
            baseline_version=baseline,
            max_latency_overhead_ms=100.0,
        )

        async def mock_brain(x):
            return x

        tester = ShadowTester(config, mock_brain, mock_brain)

        assert tester.validate_latency_threshold(50.0, threshold=75.0) is True
        assert tester.validate_latency_threshold(80.0, threshold=75.0) is False


class TestRunShadowTestSmoke:
    """Smoke tests for run_shadow_test convenience function."""

    @pytest.mark.asyncio
    async def test_run_shadow_test_function(self) -> None:
        """Test the convenience function."""
        candidate = BrainVersion(1, 1, 0)
        baseline = BrainVersion(1, 0, 0)

        async def mock_brain(x):
            return x

        inputs = [{"data": i} for i in range(3)]

        result = await run_shadow_test(
            candidate_version=candidate,
            baseline_version=baseline,
            candidate_brain=mock_brain,
            baseline_brain=mock_brain,
            inputs=inputs,
            sample_size=3,
        )

        assert result.candidate_latency_ms is not None
        assert result.baseline_latency_ms is not None

    @pytest.mark.asyncio
    async def test_run_shadow_test_with_options(self) -> None:
        """Test the convenience function with options."""
        candidate = BrainVersion(1, 1, 0)
        baseline = BrainVersion(1, 0, 0)

        async def mock_brain(x):
            return x

        inputs = [{"data": i} for i in range(5)]

        result = await run_shadow_test(
            candidate_version=candidate,
            baseline_version=baseline,
            candidate_brain=mock_brain,
            baseline_brain=mock_brain,
            inputs=inputs,
            max_latency_overhead_ms=200.0,
            sample_size=5,
            parallel_enabled=False,
        )

        assert result.config is not None
        assert result.config.max_latency_overhead_ms == 200.0
        assert result.config.parallel_enabled is False


class TestBrainFunctionSmoke:
    """Smoke tests for BrainFunction type."""

    @pytest.mark.asyncio
    async def test_brain_function_type(self) -> None:
        """Test that async functions work as BrainFunction."""

        async def sample_brain(data: dict) -> dict:
            return {"result": data}

        result = await sample_brain({"input": "test"})
        assert result["result"]["input"] == "test"


class TestShadowTestEdgeCasesSmoke:
    """Smoke tests for edge cases."""

    @pytest.mark.asyncio
    async def test_shadow_test_exception_handling(self) -> None:
        """Test handling of exceptions during shadow test."""
        candidate = BrainVersion(1, 1, 0)
        baseline = BrainVersion(1, 0, 0)
        config = ShadowTestConfig(
            candidate_version=candidate,
            baseline_version=baseline,
            sample_size=3,
            warmup_iterations=0,
        )

        async def failing_brain(x):
            raise ValueError("Test error")

        async def working_brain(x):
            return x

        tester = ShadowTester(config, failing_brain, working_brain)
        inputs = [{"data": i} for i in range(3)]

        result = await tester.run_shadow_test(inputs)

        assert result.passed is False
        assert result.error_message is not None
        assert "failed" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_shadow_test_latency_calculation(self) -> None:
        """Test that latency calculations are correct."""
        candidate = BrainVersion(1, 1, 0)
        baseline = BrainVersion(1, 0, 0)
        config = ShadowTestConfig(
            candidate_version=candidate,
            baseline_version=baseline,
            sample_size=5,
            warmup_iterations=0,
            measurement_iterations=3,
        )

        async def fast_brain(x):
            return x

        tester = ShadowTester(config, fast_brain, fast_brain)
        inputs = [{"data": i} for i in range(5)]

        result = await tester.run_shadow_test(inputs)

        # Both brains are the same, so overhead should be near 0
        assert result.candidate_latency_ms is not None
        assert result.baseline_latency_ms is not None
        assert result.candidate_latency_ms.sample_count == 5
        assert result.baseline_latency_ms.sample_count == 5
