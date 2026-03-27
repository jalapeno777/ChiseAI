"""Tests for CI Metrics Storage."""

from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from src.ci.metrics.models import (
    AggregatedMetricsOutput,
    MetricPoint,
)
from src.ci.metrics.storage import MetricsStorage, load_metrics_history


def create_metric_json(timestamp: str | None = None, **kwargs) -> dict:
    """Helper to create metric JSON data."""
    if timestamp is None:
        timestamp = datetime.now(UTC).isoformat()
    defaults = {
        "timestamp": timestamp,
        "test_count": 100,
        "duration": 45.0,
        "cache_hit_rate": 75.0,
        "parallel_speedup": 2.0,
        "worker_utilization": 0.85,
        "cache": {"hits": 75, "misses": 25, "hit_rate": 75.0},
        "parallel": {"speedup": 2.0, "worker_utilization": 0.85},
        "speedup": {
            "total_duration": 45.0,
            "tests_run": 100,
            "tests_passed": 98,
            "tests_failed": 2,
        },
    }
    defaults.update(kwargs)
    return defaults


class TestMetricsStorage:
    """Tests for MetricsStorage class."""

    def test_create(self) -> None:
        """Test creating storage with default path."""
        storage = MetricsStorage()
        assert storage.base_path == Path("_bmad-output/ci")

    def test_create_custom_path(self) -> None:
        """Test creating storage with custom path."""
        storage = MetricsStorage("/custom/path")
        assert storage.base_path == Path("/custom/path")

    def test_load_metrics_single(self) -> None:
        """Test loading single metric from file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(create_metric_json(), f)
            f.flush()
            path = f.name

        try:
            storage = MetricsStorage()
            metrics = storage.load_metrics(path)
            assert len(metrics) == 1
            assert metrics[0].test_count == 100
        finally:
            Path(path).unlink()

    def test_load_metrics_list(self) -> None:
        """Test loading list of metrics from file."""
        data = [create_metric_json(), create_metric_json()]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            path = f.name

        try:
            storage = MetricsStorage()
            metrics = storage.load_metrics(path)
            assert len(metrics) == 2
        finally:
            Path(path).unlink()

    def test_load_metrics_not_found(self) -> None:
        """Test loading from non-existent file."""
        storage = MetricsStorage()
        with pytest.raises(FileNotFoundError):
            storage.load_metrics("/nonexistent/path.json")

    def test_load_metrics_invalid_json(self) -> None:
        """Test loading invalid JSON file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("not valid json{")
            f.flush()
            path = f.name

        try:
            storage = MetricsStorage()
            with pytest.raises(ValueError):
                storage.load_metrics(path)
        finally:
            Path(path).unlink()

    def test_load_metrics_from_dir(self) -> None:
        """Test loading metrics from directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create metrics.json
            metrics_path = Path(tmpdir) / "metrics.json"
            with open(metrics_path, "w") as f:
                json.dump([create_metric_json()], f)

            storage = MetricsStorage()
            metrics = storage.load_metrics_from_dir(tmpdir)
            assert len(metrics) >= 1

    def test_save_metrics(self) -> None:
        """Test saving metrics to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = MetricsStorage()
            metrics = [
                MetricPoint(timestamp="2026-03-26T10:00:00+00:00", test_count=100)
            ]
            output_path = Path(tmpdir) / "output.json"

            result = storage.save_metrics(metrics, output_path)
            assert result is True
            assert output_path.exists()

            # Verify content
            with open(output_path) as f:
                data = json.load(f)
            assert len(data) == 1
            assert data[0]["test_count"] == 100

    def test_save_aggregated(self) -> None:
        """Test saving aggregated output to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = MetricsStorage()
            output = AggregatedMetricsOutput(
                generated_at="2026-03-26T10:00:00+00:00",
                source_metrics_count=100,
            )
            output.aggregation_windows = {"day": [{"test_count_avg": 100.0}]}
            output_path = Path(tmpdir) / "aggregated.json"

            result = storage.save_aggregated(output, output_path)
            assert result is True
            assert output_path.exists()

    def test_load_aggregated(self) -> None:
        """Test loading aggregated output from file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create file first
            output_path = Path(tmpdir) / "aggregated.json"
            data = {
                "generated_at": "2026-03-26T10:00:00+00:00",
                "source_metrics_count": 100,
                "aggregation_windows": {"day": [{"test_count_avg": 100.0}]},
                "trends": [],
            }
            with open(output_path, "w") as f:
                json.dump(data, f)

            storage = MetricsStorage()
            output = storage.load_aggregated(output_path)
            assert output is not None
            assert output.source_metrics_count == 100
            assert "day" in output.aggregation_windows

    def test_load_aggregated_not_found(self) -> None:
        """Test loading aggregated from non-existent file."""
        storage = MetricsStorage()
        result = storage.load_aggregated("/nonexistent/path.json")
        assert result is None


class TestLoadMetricsHistory:
    """Tests for load_metrics_history function."""

    def test_load_history_empty_dir(self) -> None:
        """Test loading history from empty directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = load_metrics_history(tmpdir)
            assert result == []

    def test_load_history_with_max_days(self) -> None:
        """Test loading history with max_days filter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create metrics file
            metrics_path = Path(tmpdir) / "metrics.json"
            data = [
                create_metric_json(
                    timestamp=(datetime.now(UTC) - timedelta(days=5)).isoformat()
                ),
                create_metric_json(
                    timestamp=(datetime.now(UTC) - timedelta(days=40)).isoformat()
                ),
            ]
            with open(metrics_path, "w") as f:
                json.dump(data, f)

            # Should only include recent metric
            result = load_metrics_history(tmpdir, max_days=30)
            assert len(result) == 1

    def test_load_history_no_filter(self) -> None:
        """Test loading history without max_days filter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            metrics_path = Path(tmpdir) / "metrics.json"
            data = [create_metric_json()]
            with open(metrics_path, "w") as f:
                json.dump(data, f)

            result = load_metrics_history(tmpdir, max_days=0)
            assert len(result) == 1
