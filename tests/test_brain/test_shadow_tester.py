"""Tests for brain shadow testing module."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from brain.shadow_tester import (
    LatencyMetrics,
    OutputComparison,
    ShadowTester,
    ShadowTestResult,
    ShadowTestStatus,
)


class TestLatencyMetrics:
    """Tests for LatencyMetrics class."""

    def test_creation(self) -> None:
        """Test basic creation."""
        metrics = LatencyMetrics(
            live_latency_ms=50.0,
            shadow_latency_ms=100.0,
        )
        assert metrics.live_latency_ms == 50.0
        assert metrics.shadow_latency_ms == 100.0
        assert metrics.overhead_ms == 50.0
        assert metrics.overhead_percentage == 100.0

    def test_zero_live_latency(self) -> None:
        """Test with zero live latency."""
        metrics = LatencyMetrics(
            live_latency_ms=0.0,
            shadow_latency_ms=100.0,
        )
        assert metrics.overhead_ms == 100.0
        assert metrics.overhead_percentage == 0.0  # Avoid division by zero

    def test_negative_overhead(self) -> None:
        """Test when shadow is faster than live."""
        metrics = LatencyMetrics(
            live_latency_ms=100.0,
            shadow_latency_ms=50.0,
        )
        assert metrics.overhead_ms == 0.0  # Clamped to zero
        assert metrics.overhead_percentage == 0.0

    def test_to_dict(self) -> None:
        """Test serialization."""
        metrics = LatencyMetrics(live_latency_ms=50.0, shadow_latency_ms=75.0)
        data = metrics.to_dict()
        assert data["live_latency_ms"] == 50.0
        assert data["shadow_latency_ms"] == 75.0
        assert data["overhead_ms"] == 25.0

    def test_from_dict(self) -> None:
        """Test deserialization."""
        data = {
            "live_latency_ms": 50.0,
            "shadow_latency_ms": 75.0,
            "overhead_ms": 25.0,
            "overhead_percentage": 50.0,
        }
        metrics = LatencyMetrics.from_dict(data)
        assert metrics.live_latency_ms == 50.0
        assert metrics.overhead_percentage == 50.0


class TestOutputComparison:
    """Tests for OutputComparison class."""

    def test_creation(self) -> None:
        """Test basic creation."""
        comp = OutputComparison(
            input_id="test_1",
            live_output={"prediction": "buy"},
            shadow_output={"prediction": "buy"},
            match=True,
            similarity_score=1.0,
        )
        assert comp.input_id == "test_1"
        assert comp.match is True
        assert comp.similarity_score == 1.0

    def test_to_dict(self) -> None:
        """Test serialization."""
        comp = OutputComparison(
            input_id="test_1",
            live_output={"prediction": "buy"},
            shadow_output={"prediction": "sell"},
            match=False,
            similarity_score=0.5,
            differences=["prediction differs"],
        )
        data = comp.to_dict()
        assert data["input_id"] == "test_1"
        assert data["match"] is False
        assert data["differences"] == ["prediction differs"]

    def test_from_dict(self) -> None:
        """Test deserialization."""
        data = {
            "input_id": "test_1",
            "live_output": {"prediction": "buy"},
            "shadow_output": {"prediction": "sell"},
            "match": False,
            "similarity_score": 0.5,
            "differences": ["prediction differs"],
        }
        comp = OutputComparison.from_dict(data)
        assert comp.input_id == "test_1"
        assert comp.match is False


class TestShadowTester:
    """Tests for ShadowTester class."""

    def test_creation(self) -> None:
        """Test basic creation."""
        tester = ShadowTester()
        assert tester.max_overhead_ms == 100.0
        assert tester.similarity_threshold == 0.95

    def test_custom_params(self) -> None:
        """Test custom parameters."""
        tester = ShadowTester(
            max_overhead_ms=50.0,
            similarity_threshold=0.99,
            timeout_seconds=60.0,
        )
        assert tester.max_overhead_ms == 50.0
        assert tester.similarity_threshold == 0.99
        assert tester.timeout_seconds == 60.0

    def test_run_shadow_test(self) -> None:
        """Test running a shadow test."""
        tester = ShadowTester()
        test_inputs = [
            {"input": "test1"},
            {"input": "test2"},
            {"input": "test3"},
        ]

        result = tester.run_shadow_test(
            shadow_version="1.1.0",
            live_version="1.0.0",
            test_inputs=test_inputs,
        )

        assert result.shadow_version == "1.1.0"
        assert result.live_version == "1.0.0"
        assert result.status == ShadowTestStatus.COMPLETED
        assert result.total_requests == 3
        assert len(result.comparisons) == 3
        assert result.latency.live_latency_ms > 0
        assert result.latency.shadow_latency_ms > 0

    def test_is_latency_acceptable(self) -> None:
        """Test checking if latency is acceptable."""
        mock_redis = MagicMock()
        result = ShadowTestResult(
            shadow_version="1.1.0",
            live_version="1.0.0",
            status=ShadowTestStatus.COMPLETED,
            started_at="2024-01-01T00:00:00Z",
            latency=LatencyMetrics(live_latency_ms=50.0, shadow_latency_ms=100.0),
        )
        mock_redis.get.return_value = json.dumps(result.to_dict())

        tester = ShadowTester(redis_client=mock_redis, max_overhead_ms=100.0)
        assert tester.is_latency_acceptable("1.1.0") is True

        # Test with excessive overhead
        result.latency = LatencyMetrics(live_latency_ms=50.0, shadow_latency_ms=200.0)
        mock_redis.get.return_value = json.dumps(result.to_dict())
        assert tester.is_latency_acceptable("1.1.0") is False

    def test_is_output_compatible(self) -> None:
        """Test checking output compatibility."""
        mock_redis = MagicMock()
        result = ShadowTestResult(
            shadow_version="1.1.0",
            live_version="1.0.0",
            status=ShadowTestStatus.COMPLETED,
            started_at="2024-01-01T00:00:00Z",
            match_rate=0.98,
        )
        mock_redis.get.return_value = json.dumps(result.to_dict())

        tester = ShadowTester(redis_client=mock_redis)
        assert tester.is_output_compatible("1.1.0") is True

        # Test with low match rate
        result.match_rate = 0.90
        mock_redis.get.return_value = json.dumps(result.to_dict())
        assert tester.is_output_compatible("1.1.0") is False

    def test_list_shadow_tests(self) -> None:
        """Test listing shadow tests."""
        mock_redis = MagicMock()

        result1 = ShadowTestResult(
            shadow_version="1.1.0",
            live_version="1.0.0",
            status=ShadowTestStatus.COMPLETED,
            started_at="2024-01-01T00:00:00Z",
        )
        result2 = ShadowTestResult(
            shadow_version="1.2.0",
            live_version="1.1.0",
            status=ShadowTestStatus.COMPLETED,
            started_at="2024-01-02T00:00:00Z",
        )

        mock_redis.scan.side_effect = [
            (0, ["brain:shadow_test:1.1.0", "brain:shadow_test:1.2.0"]),
        ]
        mock_redis.get.side_effect = [
            json.dumps(result1.to_dict()),
            json.dumps(result2.to_dict()),
        ]

        tester = ShadowTester(redis_client=mock_redis)
        results = tester.list_shadow_tests()

        assert len(results) == 2
        # Should be sorted by started_at descending
        assert results[0].shadow_version == "1.2.0"
        assert results[1].shadow_version == "1.1.0"

    def test_empty_test_inputs(self) -> None:
        """Test with empty test inputs."""
        tester = ShadowTester()
        result = tester.run_shadow_test(
            shadow_version="1.1.0",
            live_version="1.0.0",
            test_inputs=[],
        )

        assert result.total_requests == 0
        assert result.match_rate == 0.0
        assert result.avg_similarity == 0.0
