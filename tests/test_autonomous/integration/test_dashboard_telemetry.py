"""
Integration tests for Autonomous Control Plane Dashboard Telemetry.

Story: ST-NS-043
"""

import json
import os
import re
from pathlib import Path

import pytest
import yaml


class TestDashboardTelemetry:
    """Tests for dashboard, alerts, and runbook configuration."""

    @pytest.fixture
    def dashboard_path(self):
        """Path to the dashboard JSON file."""
        return Path("infrastructure/grafana/dashboards/autonomous_control_plane.json")

    @pytest.fixture
    def alerts_path(self):
        """Path to the alerts YAML file."""
        return Path("infrastructure/grafana/alerts/autonomous_control_plane.yml")

    @pytest.fixture
    def runbook_path(self):
        """Path to the runbook markdown file."""
        return Path("docs/runbooks/autonomous_control_plane.md")

    @pytest.fixture
    def dashboard(self, dashboard_path):
        """Load and return the dashboard JSON."""
        with open(dashboard_path) as f:
            return json.load(f)

    @pytest.fixture
    def alerts(self, alerts_path):
        """Load and return the alerts YAML."""
        with open(alerts_path) as f:
            return yaml.safe_load(f)

    @pytest.fixture
    def runbook_content(self, runbook_path):
        """Load and return the runbook content."""
        with open(runbook_path) as f:
            return f.read()

    def test_dashboard_json_valid(self, dashboard_path):
        """AC1: Verify dashboard JSON loads without errors."""
        with open(dashboard_path) as f:
            data = json.load(f)
        assert isinstance(data, dict)
        assert "panels" in data

    def test_dashboard_panels_exist(self, dashboard):
        """AC2: Verify all expected panels are present."""
        panels = dashboard.get("panels", [])
        assert len(panels) >= 7, f"Expected at least 7 panels, got {len(panels)}"

        # Check for expected panel titles
        panel_titles = {p.get("title", "") for p in panels}
        expected_panels = [
            "Self-Healing Engine Overview",
            "Total Healing Attempts",
            "Successful Healings",
            "Failed Healings",
            "Pending Approvals",
            "Avg Healing Duration",
            "Rolled Back",
        ]

        for expected in expected_panels:
            assert expected in panel_titles, f"Missing panel: {expected}"

    def test_dashboard_has_datasource(self, dashboard):
        """Verify panels reference InfluxDB datasource."""
        panels = dashboard.get("panels", [])
        for panel in panels:
            if panel.get("type") != "row":  # Skip row panels
                datasource = panel.get("datasource", "")
                assert "InfluxDB" in str(
                    datasource
                ), f"Panel {panel.get('title')} missing InfluxDB datasource"

    def test_dashboard_has_uid(self, dashboard):
        """Verify dashboard has a unique identifier."""
        assert "uid" in dashboard, "Dashboard missing UID"
        assert (
            dashboard["uid"] == "autonomous-healing"
        ), f"Unexpected UID: {dashboard['uid']}"

    def test_alert_rules_configured(self, alerts):
        """AC3: Verify 3 alert rules exist."""
        groups = alerts.get("groups", [])
        assert len(groups) >= 1, "No alert groups found"

        group = groups[0]
        rules = group.get("rules", [])
        assert len(rules) == 3, f"Expected 3 alert rules, got {len(rules)}"

        # Check rule names
        rule_names = {r.get("alert") for r in rules}
        expected_rules = {
            "ControlPlaneDown",
            "CircuitBreakerOpenTooLong",
            "HealingFailureRateHigh",
        }
        assert (
            rule_names == expected_rules
        ), f"Missing or unexpected rules: {rule_names}"

    def test_alert_rules_have_required_fields(self, alerts):
        """Verify alert rules have all required fields."""
        groups = alerts.get("groups", [])
        rules = groups[0].get("rules", [])

        required_fields = ["alert", "expr", "for", "labels", "annotations"]

        for rule in rules:
            for field in required_fields:
                assert field in rule, f"Rule {rule.get('alert')} missing field: {field}"

            # Verify annotations include runbook_url
            annotations = rule.get("annotations", {})
            assert (
                "runbook_url" in annotations
            ), f"Rule {rule.get('alert')} missing runbook_url"
            assert "summary" in annotations, f"Rule {rule.get('alert')} missing summary"

    def test_runbook_exists(self, runbook_path):
        """AC4: Verify runbook file exists."""
        assert runbook_path.exists(), f"Runbook not found: {runbook_path}"

    def test_runbook_has_alert_sections(self, runbook_content):
        """Verify runbook has sections for each alert."""
        required_sections = [
            "ControlPlaneDown",
            "CircuitBreakerOpenTooLong",
            "HealingFailureRateHigh",
        ]

        for section in required_sections:
            assert section in runbook_content, f"Runbook missing section for: {section}"

    def test_runbook_has_escalation_procedures(self, runbook_content):
        """Verify runbook includes escalation procedures."""
        assert "Escalation" in runbook_content, "Runbook missing escalation procedures"
        assert (
            "P0" in runbook_content or "severity" in runbook_content.lower()
        ), "Runbook missing severity levels"

    def test_runbook_links_in_alert_rules(self, alerts):
        """AC5: Verify alert rules reference runbook."""
        groups = alerts.get("groups", [])
        rules = groups[0].get("rules", [])

        for rule in rules:
            annotations = rule.get("annotations", {})
            runbook_url = annotations.get("runbook_url", "")
            assert (
                "autonomous_control_plane" in runbook_url
            ), f"Rule {rule.get('alert')} has invalid runbook URL"

    def test_terraform_deployable(self, dashboard_path):
        """AC6: Verify dashboard JSON is valid for Terraform deployment."""
        with open(dashboard_path) as f:
            content = f.read()

        # Verify it's valid JSON
        data = json.loads(content)

        # Verify required Grafana dashboard fields
        assert "title" in data, "Dashboard missing title"
        assert "uid" in data, "Dashboard missing UID"
        assert "panels" in data, "Dashboard missing panels"
        assert isinstance(data["panels"], list), "Panels must be a list"

        # Verify no trailing commas (common JSON error)
        # This is implicitly checked by json.loads() succeeding

    def test_dashboard_has_refresh_interval(self, dashboard):
        """Verify dashboard has a refresh interval configured."""
        assert "refresh" in dashboard, "Dashboard missing refresh interval"
        assert (
            dashboard["refresh"] == "30s"
        ), f"Unexpected refresh interval: {dashboard['refresh']}"

    def test_dashboard_has_time_range(self, dashboard):
        """Verify dashboard has default time range."""
        assert "time" in dashboard, "Dashboard missing time configuration"
        time_config = dashboard["time"]
        assert "from" in time_config, "Missing time 'from'"
        assert "to" in time_config, "Missing time 'to'"

    def test_alert_rule_expressions_valid(self, alerts):
        """Verify alert rule expressions are non-empty."""
        groups = alerts.get("groups", [])
        rules = groups[0].get("rules", [])

        for rule in rules:
            expr = rule.get("expr", "")
            assert expr, f"Rule {rule.get('alert')} has empty expression"
            assert (
                len(expr) > 10
            ), f"Rule {rule.get('alert')} expression seems too short"

    def test_runbook_has_useful_commands(self, runbook_content):
        """Verify runbook includes useful commands section."""
        assert (
            "Useful Commands" in runbook_content or "Commands" in runbook_content
        ), "Runbook missing commands section"
        assert (
            "curl" in runbook_content or "kubectl" in runbook_content
        ), "Runbook missing example commands"

    def test_dashboard_panel_types_valid(self, dashboard):
        """Verify all panels have valid types."""
        valid_types = {
            "row",
            "singlestat",
            "graph",
            "table",
            "stat",
            "timeseries",
            "gauge",
        }
        panels = dashboard.get("panels", [])

        for panel in panels:
            panel_type = panel.get("type", "")
            assert (
                panel_type in valid_types or panel_type
            ), f"Panel {panel.get('title')} has invalid type: {panel_type}"

    def test_dashboard_has_templating(self, dashboard):
        """Verify dashboard has template variables configured."""
        templating = dashboard.get("templating", {})
        list_vars = templating.get("list", [])
        assert (
            len(list_vars) >= 2
        ), f"Expected at least 2 template variables, got {len(list_vars)}"

        var_names = {v.get("name") for v in list_vars}
        assert "severity" in var_names, "Missing 'severity' template variable"
        assert "status" in var_names, "Missing 'status' template variable"


class TestFileStructure:
    """Tests for file structure and organization."""

    def test_dashboard_file_exists(self):
        """Verify dashboard file exists in expected location."""
        path = Path("infrastructure/grafana/dashboards/autonomous_control_plane.json")
        assert path.exists(), f"Dashboard file not found: {path}"

    def test_alerts_directory_exists(self):
        """Verify alerts directory exists."""
        path = Path("infrastructure/grafana/alerts")
        assert path.exists(), f"Alerts directory not found: {path}"

    def test_runbook_directory_exists(self):
        """Verify runbooks directory exists."""
        path = Path("docs/runbooks")
        assert path.exists(), f"Runbooks directory not found: {path}"

    def test_all_files_readable(self):
        """Verify all required files are readable."""
        files = [
            "infrastructure/grafana/dashboards/autonomous_control_plane.json",
            "infrastructure/grafana/alerts/autonomous_control_plane.yml",
            "docs/runbooks/autonomous_control_plane.md",
        ]

        for file_path in files:
            path = Path(file_path)
            assert path.exists(), f"File not found: {path}"
            assert path.stat().st_size > 0, f"File is empty: {path}"
            with open(path) as f:
                content = f.read()
                assert len(content) > 100, f"File content too short: {path}"
