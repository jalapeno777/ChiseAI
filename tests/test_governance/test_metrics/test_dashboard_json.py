"""
Tests for Dashboard JSON validation.

Story: ST-GOV-004
"""

import json
from pathlib import Path

import pytest

DASHBOARD_PATH = (
    Path(__file__).parent.parent.parent.parent
    / "infrastructure"
    / "grafana"
    / "dashboards"
    / "governance_metrics.json"
)


class TestDashboardJSON:
    """Test governance metrics dashboard JSON structure."""

    @pytest.fixture
    def dashboard_data(self):
        """Load dashboard JSON."""
        with open(DASHBOARD_PATH) as f:
            return json.load(f)

    def test_dashboard_file_exists(self):
        """Test that dashboard file exists."""
        assert DASHBOARD_PATH.exists(), f"Dashboard not found at {DASHBOARD_PATH}"

    def test_dashboard_valid_json(self):
        """Test that dashboard is valid JSON."""
        with open(DASHBOARD_PATH) as f:
            data = json.load(f)
        assert isinstance(data, dict)

    def test_dashboard_title(self, dashboard_data):
        """Test dashboard has correct title."""
        assert dashboard_data["title"] == "Agent Governance Metrics"

    def test_dashboard_uid(self, dashboard_data):
        """Test dashboard has unique UID."""
        assert "uid" in dashboard_data
        assert "ST-GOV-004" in dashboard_data["uid"]

    def test_dashboard_has_rows(self, dashboard_data):
        """Test dashboard has expected row panels."""
        panels = dashboard_data.get("panels", [])
        row_titles = [p["title"] for p in panels if p.get("type") == "row"]

        expected_rows = [
            "Constitution Health",
            "Task Sentinel",
            "Memory & Retrieval",
            "System Health",
        ]

        for row in expected_rows:
            assert row in row_titles, f"Missing row: {row}"

    def test_dashboard_refresh_interval(self, dashboard_data):
        """Test dashboard has appropriate refresh interval."""
        assert dashboard_data.get("refresh") == "15s"

    def test_dashboard_time_range(self, dashboard_data):
        """Test dashboard has default time range."""
        time_config = dashboard_data.get("time", {})
        assert "from" in time_config
        assert "to" in time_config
        assert time_config["from"] == "now-7d"

    def test_dashboard_has_influxdb_variables(self, dashboard_data):
        """Test dashboard has InfluxDB datasource variable."""
        templating = dashboard_data.get("templating", {})
        variables = templating.get("list", [])

        datasource_vars = [v for v in variables if v.get("type") == "datasource"]
        assert len(datasource_vars) > 0, "No datasource variable found"

        influx_var = next(
            (v for v in datasource_vars if "influxdb" in v.get("query", "").lower()),
            None,
        )
        assert influx_var is not None, "InfluxDB datasource variable not found"

    def test_dashboard_panels_have_datasource(self, dashboard_data):
        """Test that panels reference the datasource variable."""
        panels = dashboard_data.get("panels", [])

        for panel in panels:
            if panel.get("type") not in ["row"]:
                datasource = panel.get("datasource", {})
                if datasource:
                    uid = datasource.get("uid", "")
                    assert "${influxdb_datasource}" in uid or "influx" in uid.lower()

    def test_dashboard_has_required_stat_panels(self, dashboard_data):
        """Test dashboard has required stat panels for key metrics."""
        all_panels = self._flatten_panels(dashboard_data.get("panels", []))
        all_titles = [p.get("title", "").lower() for p in all_panels]

        # Check for key metrics (can be stat or gauge panels)
        required_keywords = [
            "violation",  # Constitution violations
            "validated",  # Tasks validated
            "blocked",  # Tasks blocked
            "hit rate",  # Memory hit rate (gauge panel)
        ]

        for keyword in required_keywords:
            found = any(keyword.lower() in title for title in all_titles)
            assert found, f"No panel found for: {keyword}"

    def test_dashboard_has_gauge_panels(self, dashboard_data):
        """Test dashboard has gauge panels for ratio metrics."""
        all_panels = self._flatten_panels(dashboard_data.get("panels", []))
        gauge_panels = [p for p in all_panels if p.get("type") == "gauge"]

        assert len(gauge_panels) >= 2, "Expected at least 2 gauge panels"

    def test_dashboard_has_timeseries_panels(self, dashboard_data):
        """Test dashboard has timeseries panels for trends."""
        all_panels = self._flatten_panels(dashboard_data.get("panels", []))
        timeseries_panels = [p for p in all_panels if p.get("type") == "timeseries"]

        assert len(timeseries_panels) >= 3, "Expected at least 3 timeseries panels"

    def test_dashboard_tags(self, dashboard_data):
        """Test dashboard has appropriate tags."""
        tags = dashboard_data.get("tags", [])
        assert "governance" in tags
        assert "chiseai" in tags

    def test_dashboard_queries_use_governance_bucket(self, dashboard_data):
        """Test that queries reference the governance bucket."""
        all_panels = self._flatten_panels(dashboard_data.get("panels", []))

        for panel in all_panels:
            targets = panel.get("targets", [])
            for target in targets:
                query = target.get("query", "")
                if query:
                    assert (
                        "governance" in query.lower()
                    ), f"Query in panel '{panel.get('title')}' should reference governance bucket"

    def _flatten_panels(self, panels):
        """Flatten nested panel structure."""
        result = []
        for panel in panels:
            result.append(panel)
            if "panels" in panel:
                result.extend(self._flatten_panels(panel["panels"]))
        return result
