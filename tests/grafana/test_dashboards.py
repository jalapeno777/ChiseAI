"""Tests for Grafana dashboard JSON validation."""

import json
import os
from pathlib import Path

import pytest


DASHBOARDS_DIR = (
    Path(__file__).parent.parent.parent / "infrastructure" / "grafana" / "dashboards"
)


class TestDashboardSchema:
    """Validate Grafana dashboard JSON schema and structure."""

    @pytest.fixture
    def data_freshness_dashboard(self):
        """Load data-freshness dashboard JSON."""
        dashboard_path = DASHBOARDS_DIR / "data-freshness.json"
        with open(dashboard_path) as f:
            return json.load(f)

    @pytest.fixture
    def backtest_kpis_dashboard(self):
        """Load backtest-kpis dashboard JSON."""
        dashboard_path = DASHBOARDS_DIR / "backtest-kpis.json"
        with open(dashboard_path) as f:
            return json.load(f)

    def test_dashboard_files_exist(self):
        """Verify all required dashboard files exist."""
        required_files = [
            "data-freshness.json",
            "backtest-kpis.json",
            "README.md",
        ]
        for filename in required_files:
            filepath = DASHBOARDS_DIR / filename
            assert filepath.exists(), f"Missing required file: {filename}"

    def test_data_freshness_has_required_schema(self, data_freshness_dashboard):
        """Validate data-freshness dashboard has required schema fields."""
        dashboard = data_freshness_dashboard

        # Required top-level fields
        assert "title" in dashboard, "Dashboard must have title"
        assert "uid" in dashboard, "Dashboard must have uid"
        assert "panels" in dashboard, "Dashboard must have panels"
        assert "schemaVersion" in dashboard, "Dashboard must have schemaVersion"

        # Validate specific fields
        assert dashboard["title"] == "ChiseAI - Data Freshness"
        assert dashboard["uid"] == "chiseai-data-freshness"
        assert dashboard["schemaVersion"] >= 36  # Grafana 10.x
        assert len(dashboard["panels"]) > 0, "Dashboard must have at least one panel"

    def test_backtest_kpis_has_required_schema(self, backtest_kpis_dashboard):
        """Validate backtest-kpis dashboard has required schema fields."""
        dashboard = backtest_kpis_dashboard

        # Required top-level fields
        assert "title" in dashboard, "Dashboard must have title"
        assert "uid" in dashboard, "Dashboard must have uid"
        assert "panels" in dashboard, "Dashboard must have panels"
        assert "schemaVersion" in dashboard, "Dashboard must have schemaVersion"

        # Validate specific fields
        assert dashboard["title"] == "ChiseAI - Backtest KPIs"
        assert dashboard["uid"] == "chiseai-backtest-kpis"
        assert dashboard["schemaVersion"] >= 36  # Grafana 10.x
        assert len(dashboard["panels"]) > 0, "Dashboard must have at least one panel"

    def test_data_freshness_has_freshness_panels(self, data_freshness_dashboard):
        """Verify data-freshness dashboard has required panels."""
        panels = data_freshness_dashboard["panels"]
        panel_titles = [p.get("title", "") for p in panels]

        # Check for required panels
        assert any("Binance" in title for title in panel_titles), (
            "Missing Binance panel"
        )
        assert any("Bybit" in title for title in panel_titles), "Missing Bybit panel"
        assert any("Bitget" in title for title in panel_titles), "Missing Bitget panel"
        assert any("Trend" in title for title in panel_titles), "Missing trend panel"

    def test_backtest_kpis_has_kpi_panels(self, backtest_kpis_dashboard):
        """Verify backtest-kpis dashboard has required KPI panels."""
        panels = backtest_kpis_dashboard["panels"]
        panel_titles = [p.get("title", "") for p in panels]

        # Check for required panels
        assert any("Sharpe" in title for title in panel_titles), (
            "Missing Sharpe ratio panel"
        )
        assert any("Drawdown" in title for title in panel_titles), (
            "Missing max drawdown panel"
        )
        assert any("Win Rate" in title for title in panel_titles), (
            "Missing win rate panel"
        )
        assert any("Trade Count" in title for title in panel_titles), (
            "Missing trade count panel"
        )

    def test_data_freshness_has_variables(self, data_freshness_dashboard):
        """Verify data-freshness dashboard has configurable variables."""
        templating = data_freshness_dashboard.get("templating", {})
        variables = templating.get("list", [])

        var_names = [v.get("name", "") for v in variables]

        # Check for required variables
        assert "influxdb_datasource" in var_names, "Missing datasource variable"
        assert "influxdb_bucket" in var_names, "Missing bucket variable"
        assert "lookback_days" in var_names, "Missing lookback_days variable"
        assert "alert_threshold_seconds" in var_names, (
            "Missing alert threshold variable"
        )

    def test_backtest_kpis_has_strategy_selector(self, backtest_kpis_dashboard):
        """Verify backtest-kpis dashboard has strategy selector."""
        templating = backtest_kpis_dashboard.get("templating", {})
        variables = templating.get("list", [])

        var_names = [v.get("name", "") for v in variables]

        # Check for required variables
        assert "influxdb_datasource" in var_names, "Missing datasource variable"
        assert "influxdb_bucket" in var_names, "Missing bucket variable"
        assert "strategy_id" in var_names, "Missing strategy_id variable"

    def test_data_freshness_has_thresholds(self, data_freshness_dashboard):
        """Verify data-freshness panels have color-coded thresholds."""
        panels = data_freshness_dashboard["panels"]

        # Find stat panels with thresholds (skip table and row panels)
        panels_with_thresholds = [
            p
            for p in panels
            if p.get("type") not in ["row", "table"]
            and "fieldConfig" in p
            and "defaults" in p.get("fieldConfig", {})
            and "thresholds" in p.get("fieldConfig", {}).get("defaults", {})
        ]

        assert len(panels_with_thresholds) > 0, "No panels with thresholds found"

        # Verify at least one panel has all threshold colors (green, yellow, red)
        found_complete_thresholds = False
        for panel in panels_with_thresholds:
            thresholds = panel["fieldConfig"]["defaults"]["thresholds"]
            steps = thresholds.get("steps", [])

            colors = [s.get("color", "") for s in steps]
            if "green" in colors and "yellow" in colors and "red" in colors:
                found_complete_thresholds = True
                break

        assert found_complete_thresholds, (
            "No panel found with green, yellow, and red thresholds"
        )

    def test_backtest_kpis_has_sharpe_thresholds(self, backtest_kpis_dashboard):
        """Verify backtest-kpis Sharpe panel has appropriate thresholds."""
        panels = backtest_kpis_dashboard["panels"]

        # Find Sharpe ratio panel
        sharpe_panel = None
        for panel in panels:
            if "Sharpe" in panel.get("title", ""):
                sharpe_panel = panel
                break

        assert sharpe_panel is not None, "Sharpe ratio panel not found"

        # Check thresholds
        field_config = sharpe_panel.get("fieldConfig", {})
        defaults = field_config.get("defaults", {})
        thresholds = defaults.get("thresholds", {})
        steps = thresholds.get("steps", [])

        # Should have red < 1, yellow 1-2, green > 2
        values = [s.get("value") for s in steps if s.get("value") is not None]
        assert 1 in values or any(v is not None and v <= 1 for v in values), (
            "Missing threshold at 1"
        )
        assert 2 in values or any(v is not None and v >= 2 for v in values), (
            "Missing threshold at 2"
        )

    def test_dashboards_use_influxdb_datasource(
        self, data_freshness_dashboard, backtest_kpis_dashboard
    ):
        """Verify dashboards are configured to use InfluxDB datasource."""
        for dashboard in [data_freshness_dashboard, backtest_kpis_dashboard]:
            panels = dashboard.get("panels", [])

            for panel in panels:
                # Skip row panels
                if panel.get("type") == "row":
                    continue

                targets = panel.get("targets", [])
                for target in targets:
                    datasource = target.get("datasource", {})
                    if isinstance(datasource, dict):
                        assert datasource.get("type") == "influxdb", (
                            f"Panel '{panel.get('title')}' does not use InfluxDB datasource"
                        )

    def test_data_freshness_has_alert_row(self, data_freshness_dashboard):
        """Verify data-freshness dashboard has alerting section."""
        panels = data_freshness_dashboard["panels"]

        # Look for row panel related to alerting
        row_panels = [p for p in panels if p.get("type") == "row"]
        row_titles = [p.get("title", "").lower() for p in row_panels]

        assert any("alert" in title for title in row_titles), "Missing alerting row"

    def test_backtest_kpis_has_timepicker(self, backtest_kpis_dashboard):
        """Verify backtest-kpis dashboard has time range selector configured."""
        timepicker = backtest_kpis_dashboard.get("timepicker", {})
        refresh_intervals = timepicker.get("refresh_intervals", [])

        # Should have refresh intervals including 5s for real-time updates
        assert "5s" in refresh_intervals, "Missing 5s refresh interval"
        assert "30s" in refresh_intervals, "Missing 30s refresh interval"

    def test_dashboards_have_appropriate_refresh_rate(
        self, data_freshness_dashboard, backtest_kpis_dashboard
    ):
        """Verify dashboards have appropriate refresh rates."""
        # Both dashboards should refresh every 30 seconds by default
        assert data_freshness_dashboard.get("refresh") == "30s", (
            "Data freshness dashboard should refresh every 30s"
        )
        assert backtest_kpis_dashboard.get("refresh") == "30s", (
            "Backtest KPIs dashboard should refresh every 30s"
        )

    def test_dashboards_have_chiseai_tags(
        self, data_freshness_dashboard, backtest_kpis_dashboard
    ):
        """Verify dashboards have ChiseAI tags for organization."""
        for dashboard in [data_freshness_dashboard, backtest_kpis_dashboard]:
            tags = dashboard.get("tags", [])
            assert "chiseai" in tags, (
                f"Dashboard '{dashboard.get('title')}' missing 'chiseai' tag"
            )

    def test_data_freshness_queries_use_correct_measurement(
        self, data_freshness_dashboard
    ):
        """Verify data-freshness queries reference correct InfluxDB measurement."""
        panels = data_freshness_dashboard["panels"]

        for panel in panels:
            if panel.get("type") == "row":
                continue

            targets = panel.get("targets", [])
            for target in targets:
                query = target.get("query", "")
                # Check for data_freshness measurement reference
                if "_measurement" in query:
                    assert "data_freshness" in query, (
                        f"Panel '{panel.get('title')}' query should reference data_freshness measurement"
                    )

    def test_backtest_kpis_queries_use_correct_measurement(
        self, backtest_kpis_dashboard
    ):
        """Verify backtest-kpis queries reference correct InfluxDB measurement."""
        panels = backtest_kpis_dashboard["panels"]

        for panel in panels:
            if panel.get("type") == "row":
                continue

            targets = panel.get("targets", [])
            for target in targets:
                query = target.get("query", "")
                # Check for backtest_kpis measurement reference
                if "_measurement" in query:
                    assert "backtest_kpis" in query, (
                        f"Panel '{panel.get('title')}' query should reference backtest_kpis measurement"
                    )

    # =========================================================================
    # HIGH SEVERITY FIXES - ST-OPS-001
    # =========================================================================

    def test_backtest_kpis_handles_all_strategy_selection(
        self, backtest_kpis_dashboard
    ):
        """H1: Verify 'All' strategy selection works with $__all special value.

        All queries that filter by strategy_id must handle the $__all special value
        to show data for all strategies when 'All' is selected.
        """
        panels = backtest_kpis_dashboard["panels"]

        # Panels that intentionally show all strategies (don't need $__all filter)
        all_strategies_panels = ["All Strategies Comparison"]

        for panel in panels:
            if panel.get("type") == "row":
                continue

            # Skip panels that intentionally show all strategies
            if panel.get("title") in all_strategies_panels:
                continue

            targets = panel.get("targets", [])
            for target in targets:
                query = target.get("query", "")
                # Skip panels without strategy_id filtering
                if "strategy_id" not in query:
                    continue

                # All queries filtering by strategy_id must handle $__all
                assert '"${strategy_id}" == "$__all"' in query or "$__all" in query, (
                    f"Panel '{panel.get('title')}' query must handle '$__all' for 'All' strategy selection. "
                    f'Use: filter(fn: (r) => "${{strategy_id}}" == "$__all" or r.strategy_id == "${{strategy_id}}")'
                )

    def test_data_freshness_has_error_handling_panel(self, data_freshness_dashboard):
        """H2: Verify data-freshness dashboard has troubleshooting/error handling panel.

        Dashboard should include a panel with guidance for troubleshooting InfluxDB
        connection issues and common error scenarios.
        """
        panels = data_freshness_dashboard["panels"]
        panel_titles = [p.get("title", "").lower() for p in panels]

        # Check for troubleshooting or error handling panel
        assert any(
            "troubleshoot" in title or "error" in title or "guide" in title
            for title in panel_titles
        ), (
            "Missing troubleshooting/error handling panel. "
            "Add a panel with title containing 'Troubleshooting', 'Error', or 'Guide'"
        )

        # Verify the troubleshooting panel has a description
        troubleshoot_panels = [
            p
            for p in panels
            if "troubleshoot" in p.get("title", "").lower()
            or "error" in p.get("title", "").lower()
            or "guide" in p.get("title", "").lower()
        ]

        for panel in troubleshoot_panels:
            assert panel.get("description") or panel.get("data"), (
                f"Troubleshooting panel '{panel.get('title')}' should have a description or data with guidance"
            )

    def test_data_freshness_lookback_days_has_validation(
        self, data_freshness_dashboard
    ):
        """H3: Verify lookback_days variable has regex validation.

        The lookback_days variable must have a regex pattern to validate
        user input and prevent invalid values.
        """
        templating = data_freshness_dashboard.get("templating", {})
        variables = templating.get("list", [])

        lookback_var = None
        for var in variables:
            if var.get("name") == "lookback_days":
                lookback_var = var
                break

        assert lookback_var is not None, "lookback_days variable not found"

        # Check for regex validation
        regex = lookback_var.get("regex", "")
        assert regex == "^[1-9][0-9]*$", (
            f"lookback_days variable must have regex validation '^[1-9][0-9]*$', got '{regex}'"
        )


class TestTerraformConfiguration:
    """Validate Terraform dashboard configuration."""

    @pytest.fixture
    def terraform_dir(self):
        """Get Terraform directory path."""
        return Path(__file__).parent.parent.parent / "infrastructure" / "terraform"

    def test_dashboards_tf_exists(self, terraform_dir):
        """Verify dashboards.tf file exists."""
        dashboards_tf = terraform_dir / "dashboards.tf"
        assert dashboards_tf.exists(), "dashboards.tf must exist"

    def test_dashboards_tf_has_required_resources(self, terraform_dir):
        """Verify dashboards.tf defines required resources."""
        dashboards_tf = terraform_dir / "dashboards.tf"

        with open(dashboards_tf) as f:
            content = f.read()

        # Check for required resource types
        assert 'resource "grafana_dashboard"' in content, (
            "Missing grafana_dashboard resource"
        )
        assert 'resource "grafana_folder"' in content, "Missing grafana_folder resource"
        assert "grafana_data_source" in content, "Missing grafana_data_source resource"

        # Check for dashboard references
        assert "data-freshness.json" in content, "Missing data-freshness.json reference"
        assert "backtest-kpis.json" in content, "Missing backtest-kpis.json reference"

    def test_dashboards_tf_uses_variables(self, terraform_dir):
        """Verify dashboards.tf uses variables for configuration."""
        dashboards_tf = terraform_dir / "dashboards.tf"

        with open(dashboards_tf) as f:
            content = f.read()

        # Check for variable references
        assert "var.influxdb_org" in content, "Missing influxdb_org variable reference"
        assert "var.influxdb_bucket" in content, (
            "Missing influxdb_bucket variable reference"
        )
        assert "var.influxdb_token" in content, (
            "Missing influxdb_token variable reference"
        )
