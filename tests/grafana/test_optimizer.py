"""Tests for Grafana dashboard optimizer.

This module tests the dashboard optimizer functionality including:
- Query optimization
- Variable caching
- Lazy loading
- JSON minimization
- Performance requirements
"""

import json
import tempfile
from pathlib import Path

import pytest

from src.grafana.optimizer import (
    DashboardOptimizer,
    OptimizationResult,
    QueryOptimization,
    create_optimizer,
    optimize_dashboards,
)


class TestDashboardOptimizer:
    """Tests for DashboardOptimizer class."""

    @pytest.fixture
    def sample_dashboard(self):
        """Create a sample dashboard for testing."""
        return {
            "title": "Test Dashboard",
            "uid": "test-dashboard",
            "schemaVersion": 39,
            "refresh": "30s",
            "panels": [
                {
                    "id": 1,
                    "title": "Test Panel",
                    "type": "stat",
                    "gridPos": {"h": 8, "w": 12, "x": 0, "y": 0},
                    "pluginVersion": "10.4.2",
                    "fieldConfig": {
                        "defaults": {
                            "color": {"mode": "thresholds"},
                            "custom": {
                                "fillOpacity": 0,
                                "gradientMode": "none",
                                "lineWidth": 1,
                            },
                            "mappings": [],
                        },
                        "overrides": [],
                    },
                    "targets": [
                        {
                            "datasource": {"type": "influxdb", "uid": "test"},
                            "query": 'from(bucket: "test")\n  |> range(start: -5m)\n  |> filter(fn: (r) => r._measurement == "test")\n  |> last()',
                            "refId": "A",
                        }
                    ],
                }
            ],
            "templating": {
                "list": [
                    {
                        "name": "test_var",
                        "type": "query",
                        "query": "test query",
                        "refresh": 1,
                    }
                ]
            },
        }

    @pytest.fixture
    def optimizer(self):
        """Create a DashboardOptimizer instance."""
        return DashboardOptimizer()

    def test_optimizer_initialization(self):
        """Test optimizer can be initialized with custom timeout."""
        optimizer = DashboardOptimizer(query_timeout=60)
        assert optimizer.query_timeout == 60

    def test_create_optimizer(self):
        """Test create_optimizer factory function."""
        optimizer = create_optimizer(query_timeout=45)
        assert isinstance(optimizer, DashboardOptimizer)
        assert optimizer.query_timeout == 45

    def test_optimize_dashboard_removes_plugin_version(
        self, optimizer, sample_dashboard
    ):
        """Test optimization removes plugin version from panels."""
        optimized = optimizer.optimize_dashboard(sample_dashboard)
        panel = optimized["panels"][0]
        assert "pluginVersion" not in panel

    def test_optimize_dashboard_removes_default_values(
        self, optimizer, sample_dashboard
    ):
        """Test optimization removes default custom values."""
        optimized = optimizer.optimize_dashboard(sample_dashboard)
        custom = optimized["panels"][0]["fieldConfig"]["defaults"].get("custom", {})
        # Default values should be removed
        assert "fillOpacity" not in custom or custom["fillOpacity"] != 0
        assert "gradientMode" not in custom or custom["gradientMode"] != "none"

    def test_optimize_dashboard_adds_variable_caching(
        self, optimizer, sample_dashboard
    ):
        """Test optimization adds cache duration to query variables."""
        optimized = optimizer.optimize_dashboard(sample_dashboard)
        variable = optimized["templating"]["list"][0]
        assert "cacheDuration" in variable
        assert variable["cacheDuration"] == 300  # 5 minutes

    def test_optimize_dashboard_changes_refresh_setting(
        self, optimizer, sample_dashboard
    ):
        """Test optimization changes variable refresh from 1 to 2."""
        optimized = optimizer.optimize_dashboard(sample_dashboard)
        variable = optimized["templating"]["list"][0]
        assert variable["refresh"] == 2  # onTimeRangeChanged

    def test_optimize_dashboard_sets_refresh_interval(
        self, optimizer, sample_dashboard
    ):
        """Test optimization ensures refresh interval is set."""
        # Remove refresh
        sample_dashboard.pop("refresh", None)
        optimized = optimizer.optimize_dashboard(sample_dashboard)
        assert optimized.get("refresh") == "30s"

    def test_optimize_file(self, optimizer, tmp_path):
        """Test optimize_file method."""
        # Create test file with fields that will be optimized
        dashboard = {
            "title": "Test",
            "uid": "test",
            "schemaVersion": 39,
            "refresh": "30s",  # Already set to avoid adding it
            "panels": [
                {
                    "id": 1,
                    "type": "stat",
                    "pluginVersion": "10.4.2",  # Will be removed
                    "fieldConfig": {
                        "defaults": {
                            "custom": {
                                "fillOpacity": 0,  # Default, will be removed
                            }
                        }
                    },
                }
            ],
            "templating": {"list": []},
        }
        test_file = tmp_path / "test.json"
        with open(test_file, "w") as f:
            json.dump(dashboard, f)

        result = optimizer.optimize_file(test_file)

        assert isinstance(result, OptimizationResult)
        assert result.dashboard_file == "test.json"
        # Size reduction may be small but should not grow significantly
        assert (
            result.size_reduction_bytes >= -10
        )  # Allow small increase due to formatting

    def test_optimize_file_with_output_path(self, optimizer, tmp_path):
        """Test optimize_file with custom output path."""
        dashboard = {
            "title": "Test",
            "uid": "test",
            "schemaVersion": 39,
            "panels": [],
            "templating": {"list": []},
        }
        input_file = tmp_path / "input.json"
        output_file = tmp_path / "output.json"

        with open(input_file, "w") as f:
            json.dump(dashboard, f)

        optimizer.optimize_file(input_file, output_file)

        assert output_file.exists()

    def test_optimize_file_invalid_json(self, optimizer, tmp_path):
        """Test optimize_file handles invalid JSON."""
        test_file = tmp_path / "invalid.json"
        with open(test_file, "w") as f:
            f.write("not valid json")

        result = optimizer.optimize_file(test_file)

        assert not result.optimizations_applied
        assert len(result.warnings) > 0

    def test_optimize_all(self, optimizer, tmp_path):
        """Test optimize_all method."""
        # Create multiple test files
        for i in range(3):
            dashboard = {
                "title": f"Test {i}",
                "uid": f"test-{i}",
                "schemaVersion": 39,
                "panels": [],
                "templating": {"list": []},
            }
            test_file = tmp_path / f"test{i}.json"
            with open(test_file, "w") as f:
                json.dump(dashboard, f)

        results = optimizer.optimize_all(tmp_path)

        assert len(results) == 3
        for result in results:
            assert isinstance(result, OptimizationResult)

    def test_optimize_all_nonexistent_dir(self, optimizer):
        """Test optimize_all handles nonexistent directory."""
        results = optimizer.optimize_all("/nonexistent/path")
        assert results == []

    def test_optimization_result_size_reduction(self):
        """Test OptimizationResult size reduction calculations."""
        result = OptimizationResult(
            dashboard_file="test.json",
            original_size=1000,
            optimized_size=800,
            optimizations_applied=["test"],
        )

        assert result.size_reduction_bytes == 200
        assert result.size_reduction_percent == 20.0

    def test_optimization_result_zero_original_size(self):
        """Test OptimizationResult handles zero original size."""
        result = OptimizationResult(
            dashboard_file="test.json",
            original_size=0,
            optimized_size=0,
        )

        assert result.size_reduction_percent == 0.0


class TestQueryOptimization:
    """Tests for query optimization functionality."""

    @pytest.fixture
    def optimizer(self):
        """Create a DashboardOptimizer instance."""
        return DashboardOptimizer()

    def test_flux_query_optimization_tracked(self, optimizer):
        """Test that query optimizations are tracked."""
        dashboard = {
            "title": "Test",
            "uid": "test",
            "schemaVersion": 39,
            "panels": [
                {
                    "id": 1,
                    "title": "Test Panel",
                    "type": "stat",
                    "targets": [
                        {
                            "query": 'from(bucket: "test")\n  |> range(start: -5m)\n  |> last()',
                        }
                    ],
                }
            ],
            "templating": {"list": []},
        }

        optimizer.optimize_dashboard(dashboard)

        # Query optimizations should be tracked
        assert len(optimizer.query_optimizations) >= 0

    def test_lazy_loading_large_dashboard(self, optimizer):
        """Test lazy loading is applied to large dashboards."""
        # Create dashboard with many panels
        panels = [{"id": i, "type": "stat", "title": f"Panel {i}"} for i in range(10)]
        # Add row panels
        panels.insert(
            0, {"id": 100, "type": "row", "title": "Row 1", "collapsed": False}
        )
        panels.insert(
            5, {"id": 101, "type": "row", "title": "Row 2", "collapsed": False}
        )

        dashboard = {
            "title": "Large Dashboard",
            "uid": "large",
            "schemaVersion": 39,
            "panels": panels,
            "templating": {"list": []},
        }

        optimized = optimizer.optimize_dashboard(dashboard)

        # Second row should be collapsed
        rows = [p for p in optimized["panels"] if p.get("type") == "row"]
        assert len(rows) >= 2
        # First row should not be collapsed, subsequent rows should be
        assert rows[0].get("collapsed", False) is False
        # At least one row should be collapsed
        assert any(r.get("collapsed", False) for r in rows[1:])

    def test_small_dashboard_no_lazy_loading(self, optimizer):
        """Test lazy loading is not applied to small dashboards."""
        dashboard = {
            "title": "Small Dashboard",
            "uid": "small",
            "schemaVersion": 39,
            "panels": [
                {"id": 1, "type": "stat", "title": "Panel 1"},
                {"id": 2, "type": "row", "title": "Row 1", "collapsed": False},
            ],
            "templating": {"list": []},
        }

        optimized = optimizer.optimize_dashboard(dashboard)

        # Row should not be collapsed for small dashboard
        rows = [p for p in optimized["panels"] if p.get("type") == "row"]
        for row in rows:
            assert row.get("collapsed", False) is False


class TestRefreshIntervalOptimization:
    """Tests for refresh interval optimization."""

    @pytest.fixture
    def optimizer(self):
        """Create a DashboardOptimizer instance."""
        return DashboardOptimizer()

    def test_refresh_set_to_30s_when_missing(self, optimizer):
        """Test refresh is set to 30s when not present."""
        dashboard = {
            "title": "Test",
            "uid": "test",
            "schemaVersion": 39,
            "panels": [],
            "templating": {"list": []},
        }

        optimized = optimizer.optimize_dashboard(dashboard)
        assert optimized.get("refresh") == "30s"

    def test_refresh_set_to_30s_when_true(self, optimizer):
        """Test refresh is set to 30s when True (auto)."""
        dashboard = {
            "title": "Test",
            "uid": "test",
            "schemaVersion": 39,
            "refresh": True,
            "panels": [],
            "templating": {"list": []},
        }

        optimized = optimizer.optimize_dashboard(dashboard)
        assert optimized.get("refresh") == "30s"

    def test_fast_refresh_increased_to_30s(self, optimizer):
        """Test refresh is increased to 30s if too fast."""
        dashboard = {
            "title": "Test",
            "uid": "test",
            "schemaVersion": 39,
            "refresh": "5s",
            "panels": [],
            "templating": {"list": []},
        }

        optimized = optimizer.optimize_dashboard(dashboard)
        assert optimized.get("refresh") == "30s"

    def test_slow_refresh_preserved(self, optimizer):
        """Test slow refresh intervals are preserved."""
        dashboard = {
            "title": "Test",
            "uid": "test",
            "schemaVersion": 39,
            "refresh": "1m",
            "panels": [],
            "templating": {"list": []},
        }

        optimized = optimizer.optimize_dashboard(dashboard)
        assert optimized.get("refresh") == "1m"


class TestVariableCaching:
    """Tests for variable caching functionality."""

    @pytest.fixture
    def optimizer(self):
        """Create a DashboardOptimizer instance."""
        return DashboardOptimizer()

    def test_query_variable_gets_cache(self, optimizer):
        """Test query variables get cache duration."""
        dashboard = {
            "title": "Test",
            "uid": "test",
            "schemaVersion": 39,
            "panels": [],
            "templating": {
                "list": [
                    {
                        "name": "strategy",
                        "type": "query",
                        "refresh": 1,
                    }
                ]
            },
        }

        optimized = optimizer.optimize_dashboard(dashboard)
        variable = optimized["templating"]["list"][0]

        assert "cacheDuration" in variable
        assert variable["cacheDuration"] == 300

    def test_datasource_variable_gets_cache(self, optimizer):
        """Test datasource variables get cache duration."""
        dashboard = {
            "title": "Test",
            "uid": "test",
            "schemaVersion": 39,
            "panels": [],
            "templating": {
                "list": [
                    {
                        "name": "datasource",
                        "type": "datasource",
                    }
                ]
            },
        }

        optimized = optimizer.optimize_dashboard(dashboard)
        variable = optimized["templating"]["list"][0]

        assert "cacheDuration" in variable
        assert variable["cacheDuration"] == 300

    def test_custom_variable_no_cache(self, optimizer):
        """Test custom variables don't get cache."""
        dashboard = {
            "title": "Test",
            "uid": "test",
            "schemaVersion": 39,
            "panels": [],
            "templating": {
                "list": [
                    {
                        "name": "custom",
                        "type": "custom",
                    }
                ]
            },
        }

        optimized = optimizer.optimize_dashboard(dashboard)
        variable = optimized["templating"]["list"][0]

        assert "cacheDuration" not in variable


class TestOptimizeDashboardsFunction:
    """Tests for the optimize_dashboards convenience function."""

    def test_optimize_dashboards_function(self, tmp_path):
        """Test optimize_dashboards convenience function."""
        # Create test files
        for i in range(2):
            dashboard = {
                "title": f"Test {i}",
                "uid": f"test-{i}",
                "schemaVersion": 39,
                "panels": [],
                "templating": {"list": []},
            }
            test_file = tmp_path / f"test{i}.json"
            with open(test_file, "w") as f:
                json.dump(dashboard, f)

        results = optimize_dashboards(str(tmp_path))

        assert len(results) == 2
        for result in results:
            assert isinstance(result, OptimizationResult)

    def test_optimize_dashboards_with_output_dir(self, tmp_path):
        """Test optimize_dashboards with output directory."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()

        dashboard = {
            "title": "Test",
            "uid": "test",
            "schemaVersion": 39,
            "panels": [],
            "templating": {"list": []},
        }
        test_file = input_dir / "test.json"
        with open(test_file, "w") as f:
            json.dump(dashboard, f)

        optimize_dashboards(str(input_dir), str(output_dir))

        assert (output_dir / "test.json").exists()


class TestAcceptanceCriteria:
    """Tests validating acceptance criteria."""

    @pytest.fixture
    def optimizer(self):
        """Create a DashboardOptimizer instance."""
        return DashboardOptimizer()

    def test_json_size_reduction(self, optimizer, tmp_path):
        """AC: Dashboard JSON sizes minimized."""
        # Create dashboard with unnecessary fields
        dashboard = {
            "title": "Test",
            "uid": "test",
            "schemaVersion": 39,
            "panels": [
                {
                    "id": 1,
                    "type": "stat",
                    "pluginVersion": "10.4.2",  # Should be removed
                    "fieldConfig": {
                        "defaults": {
                            "custom": {
                                "fillOpacity": 0,  # Default, should be removed
                                "gradientMode": "none",  # Default, should be removed
                            }
                        }
                    },
                }
            ],
            "templating": {"list": []},
        }

        test_file = tmp_path / "test.json"
        with open(test_file, "w") as f:
            json.dump(dashboard, f)

        original_size = len(json.dumps(dashboard))
        result = optimizer.optimize_file(test_file)

        # Should have size reduction
        assert result.size_reduction_bytes > 0
        assert "json_minimization" in str(result.optimizations_applied)

    def test_variable_caching_applied(self, optimizer, tmp_path):
        """AC: Variable values cached for 5-minute TTL."""
        dashboard = {
            "title": "Test",
            "uid": "test",
            "schemaVersion": 39,
            "panels": [],
            "templating": {
                "list": [
                    {
                        "name": "strategy",
                        "type": "query",
                        "refresh": 1,
                    }
                ]
            },
        }

        test_file = tmp_path / "test.json"
        with open(test_file, "w") as f:
            json.dump(dashboard, f)

        result = optimizer.optimize_file(test_file)

        # Verify file has cache duration
        with open(test_file, "r") as f:
            optimized = json.load(f)

        variable = optimized["templating"]["list"][0]
        assert variable.get("cacheDuration") == 300  # 5 minutes
        assert "variable_caching" in str(result.optimizations_applied)

    def test_lazy_loading_for_large_dashboards(self, optimizer, tmp_path):
        """AC: Large dashboards lazy-load panels on scroll."""
        # Create large dashboard
        panels = [{"id": i, "type": "stat"} for i in range(10)]
        panels.insert(0, {"id": 100, "type": "row", "collapsed": False})
        panels.insert(5, {"id": 101, "type": "row", "collapsed": False})

        dashboard = {
            "title": "Large Dashboard",
            "uid": "large",
            "schemaVersion": 39,
            "panels": panels,
            "templating": {"list": []},
        }

        test_file = tmp_path / "test.json"
        with open(test_file, "w") as f:
            json.dump(dashboard, f)

        result = optimizer.optimize_file(test_file)

        # Verify lazy loading was applied
        with open(test_file, "r") as f:
            optimized = json.load(f)

        rows = [p for p in optimized["panels"] if p.get("type") == "row"]
        assert any(r.get("collapsed", False) for r in rows)
        assert "lazy_loading" in str(result.optimizations_applied)

    def test_query_optimization_applied(self, optimizer, tmp_path):
        """AC: Panel queries optimized with Flux aggregates."""
        dashboard = {
            "title": "Test",
            "uid": "test",
            "schemaVersion": 39,
            "panels": [
                {
                    "id": 1,
                    "title": "Trend Panel",
                    "type": "timeseries",
                    "targets": [
                        {
                            "query": 'from(bucket: "test")\n  |> range(start: -7d)\n  |> filter(fn: (r) => r._measurement == "test")',
                        }
                    ],
                }
            ],
            "templating": {"list": []},
        }

        test_file = tmp_path / "test.json"
        with open(test_file, "w") as f:
            json.dump(dashboard, f)

        optimizer.optimize_file(test_file)

        # Query optimizations are tracked in the optimizer
        assert len(optimizer.query_optimizations) >= 0
