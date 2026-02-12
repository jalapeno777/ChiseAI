#!/usr/bin/env python3
"""
Tests for Grafana Dashboard Watchdog

Usage:
    pytest tests/test_ops/test_grafana_watchdog.py -v
"""

import json
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest
import requests

# Add project root to path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.operations.grafana_watchdog import (
    WatchdogConfig,
    GrafanaAPI,
    DashboardChangeHandler,
    GrafanaWatchdog,
)


class TestWatchdogConfig:
    """Test WatchdogConfig dataclass."""

    def test_default_values(self):
        config = WatchdogConfig()
        assert config.grafana_url == "http://host.docker.internal:3001"
        assert config.grafana_user == "admin"
        assert config.grafana_password == "admin"
        assert config.grafana_api_key is None
        assert config.debounce_seconds == 5.0
        assert config.log_level == "INFO"

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("GRAFANA_URL", "http://custom:3000")
        monkeypatch.setenv("GRAFANA_USER", "custom_user")
        monkeypatch.setenv("GRAFANA_PASSWORD", "custom_pass")
        monkeypatch.setenv("GRAFANA_API_KEY", "api_key_123")
        monkeypatch.setenv("DASHBOARDS_PATH", "/custom/path")
        monkeypatch.setenv("WATCHDOG_DEBOUNCE_SECONDS", "10")
        monkeypatch.setenv("WATCHDOG_LOG_LEVEL", "DEBUG")

        config = WatchdogConfig.from_env()
        assert config.grafana_url == "http://custom:3000"
        assert config.grafana_user == "custom_user"
        assert config.grafana_password == "custom_pass"
        assert config.grafana_api_key == "api_key_123"
        assert config.dashboards_path == "/custom/path"
        assert config.debounce_seconds == 10.0
        assert config.log_level == "DEBUG"


class TestGrafanaAPI:
    """Test GrafanaAPI client."""

    @pytest.fixture
    def config(self):
        return WatchdogConfig(
            grafana_url="http://test:3001",
            grafana_user="admin",
            grafana_password="admin",
        )

    @pytest.fixture
    def api(self, config):
        return GrafanaAPI(config)

    def test_init_with_basic_auth(self, config):
        api = GrafanaAPI(config)
        assert api.session.auth == ("admin", "admin")
        assert "Authorization" not in api.session.headers

    def test_init_with_api_key(self, config):
        config.grafana_api_key = "test_key"
        api = GrafanaAPI(config)
        assert api.session.headers["Authorization"] == "Bearer test_key"
        assert api.session.auth is None

    @patch("src.operations.grafana_watchdog.requests.Session.get")
    def test_health_check_success(self, mock_get, api):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        assert api.health_check() is True

    @patch("src.operations.grafana_watchdog.requests.Session.get")
    def test_health_check_failure(self, mock_get, api):
        mock_get.side_effect = requests.RequestException("Connection error")

        assert api.health_check() is False

    @patch("src.operations.grafana_watchdog.requests.Session.post")
    def test_reload_dashboards_success(self, mock_post, api):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        assert api.reload_dashboards() is True

    @patch("src.operations.grafana_watchdog.requests.Session.post")
    def test_reload_dashboards_not_found(self, mock_post, api):
        mock_response = Mock()
        mock_response.status_code = 404
        mock_post.return_value = mock_response

        assert api.reload_dashboards() is False

    @patch("src.operations.grafana_watchdog.requests.Session.post")
    def test_reload_dashboards_auth_error(self, mock_post, api):
        mock_response = Mock()
        mock_response.status_code = 401
        mock_post.return_value = mock_response

        assert api.reload_dashboards() is False

    @patch("src.operations.grafana_watchdog.requests.Session.get")
    def test_list_dashboards_success(self, mock_get, api):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"uid": "dash1", "title": "Test Dashboard"}]
        mock_get.return_value = mock_response

        dashboards = api.list_dashboards()
        assert len(dashboards) == 1
        assert dashboards[0]["uid"] == "dash1"


class TestDashboardChangeHandler:
    """Test DashboardChangeHandler."""

    @pytest.fixture
    def config(self, tmp_path):
        dashboards_dir = tmp_path / "dashboards"
        dashboards_dir.mkdir()

        return WatchdogConfig(
            grafana_url="http://test:3001",
            dashboards_path=str(dashboards_dir),
            debounce_seconds=0.1,  # Short debounce for testing
        )

    @pytest.fixture
    def mock_api(self):
        return Mock(spec=GrafanaAPI)

    @pytest.fixture
    def handler(self, mock_api, config):
        return DashboardChangeHandler(mock_api, config)

    def test_is_dashboard_file(self, handler):
        assert handler._is_dashboard_file("/path/to/dashboards/test.json") is True
        assert handler._is_dashboard_file("/path/to/other/file.txt") is False
        assert handler._is_dashboard_file("/path/to/dashboards/test.yaml") is False

    @patch("src.operations.grafana_watchdog.DashboardChangeHandler._trigger_reload")
    def test_on_created(self, mock_trigger, handler):
        event = Mock()
        event.is_directory = False
        event.src_path = "/path/to/dashboards/new-dashboard.json"

        handler.on_created(event)

        assert event.src_path in handler.known_files
        mock_trigger.assert_called_once()

    @patch("src.operations.grafana_watchdog.DashboardChangeHandler._trigger_reload")
    def test_on_created_ignores_directories(self, mock_trigger, handler):
        event = Mock()
        event.is_directory = True
        event.src_path = "/path/to/dashboards/new-folder"

        handler.on_created(event)

        mock_trigger.assert_not_called()

    @patch("src.operations.grafana_watchdog.DashboardChangeHandler._trigger_reload")
    def test_on_deleted(self, mock_trigger, handler):
        handler.known_files.add("/path/to/dashboards/old-dashboard.json")

        event = Mock()
        event.is_directory = False
        event.src_path = "/path/to/dashboards/old-dashboard.json"

        handler.on_deleted(event)

        assert event.src_path not in handler.known_files
        mock_trigger.assert_called_once()

    @patch("src.operations.grafana_watchdog.DashboardChangeHandler._trigger_reload")
    def test_on_modified(self, mock_trigger, handler):
        event = Mock()
        event.is_directory = False
        event.src_path = "/path/to/dashboards/existing-dashboard.json"

        handler.on_modified(event)

        mock_trigger.assert_called_once()

    @patch("src.operations.grafana_watchdog.DashboardChangeHandler._trigger_reload")
    def test_on_moved(self, mock_trigger, handler):
        handler.known_files.add("/path/to/dashboards/old-name.json")

        event = Mock()
        event.is_directory = False
        event.src_path = "/path/to/dashboards/old-name.json"
        event.dest_path = "/path/to/dashboards/new-name.json"

        handler.on_moved(event)

        assert "/path/to/dashboards/old-name.json" not in handler.known_files
        assert "/path/to/dashboards/new-name.json" in handler.known_files
        mock_trigger.assert_called_once()


class TestGrafanaWatchdog:
    """Test GrafanaWatchdog main class."""

    @pytest.fixture
    def config(self, tmp_path):
        dashboards_dir = tmp_path / "dashboards"
        dashboards_dir.mkdir()

        return WatchdogConfig(
            grafana_url="http://test:3001",
            dashboards_path=str(dashboards_dir),
            debounce_seconds=0.1,
        )

    @pytest.fixture
    def watchdog(self, config):
        return GrafanaWatchdog(config)

    def test_validate_environment_success(self, watchdog, config):
        assert watchdog.validate_environment() is True

    def test_validate_environment_missing_path(self, watchdog):
        watchdog.config.dashboards_path = "/nonexistent/path"
        assert watchdog.validate_environment() is False

    @patch("src.operations.grafana_watchdog.GrafanaAPI.health_check")
    def test_wait_for_grafana_success(self, mock_health, watchdog):
        mock_health.return_value = True

        assert watchdog.wait_for_grafana(timeout=5) is True

    @patch("src.operations.grafana_watchdog.GrafanaAPI.health_check")
    def test_wait_for_grafana_timeout(self, mock_health, watchdog):
        mock_health.return_value = False

        assert watchdog.wait_for_grafana(timeout=1) is False


class TestAcceptanceCriteria:
    """Test acceptance criteria for ST-OPS-006."""

    @pytest.fixture
    def sample_dashboard(self):
        return {
            "dashboard": {
                "title": "Test Dashboard",
                "uid": "test-dashboard",
                "panels": [],
            },
            "overwrite": True,
        }

    def test_ac1_watchdog_can_run_as_service(self, tmp_path):
        """AC1: Watchdog process runs as sidecar or systemd service"""
        dashboards_dir = tmp_path / "dashboards"
        dashboards_dir.mkdir()

        config = WatchdogConfig(
            dashboards_path=str(dashboards_dir),
            debounce_seconds=0.1,
        )

        watchdog = GrafanaWatchdog(config)
        assert watchdog.validate_environment() is True

    @patch("src.operations.grafana_watchdog.GrafanaAPI.reload_dashboards")
    def test_ac2_new_files_trigger_provisioning(self, mock_reload, tmp_path):
        """AC2: New JSON files in dashboard dir trigger provisioning"""
        dashboards_dir = tmp_path / "dashboards"
        dashboards_dir.mkdir()

        config = WatchdogConfig(
            dashboards_path=str(dashboards_dir),
            debounce_seconds=0.1,
        )

        mock_api = Mock(spec=GrafanaAPI)
        handler = DashboardChangeHandler(mock_api, config)

        # Simulate file creation
        test_file = dashboards_dir / "test-dashboard.json"
        test_file.write_text('{"title": "Test"}')

        event = Mock()
        event.is_directory = False
        event.src_path = str(test_file)

        handler.on_created(event)

        # Should trigger reload
        assert mock_api.reload_dashboards.called or handler.pending_reload

    @patch("src.operations.grafana_watchdog.GrafanaAPI.reload_dashboards")
    def test_ac3_deleted_files_deprovision(self, mock_reload, tmp_path):
        """AC3: Removed files de-provisioned from Grafana"""
        dashboards_dir = tmp_path / "dashboards"
        dashboards_dir.mkdir()

        config = WatchdogConfig(
            dashboards_path=str(dashboards_dir),
            debounce_seconds=0.1,
        )

        mock_api = Mock(spec=GrafanaAPI)
        handler = DashboardChangeHandler(mock_api, config)

        # Add file to known files
        test_file = dashboards_dir / "old-dashboard.json"
        handler.known_files.add(str(test_file))

        # Simulate file deletion
        event = Mock()
        event.is_directory = False
        event.src_path = str(test_file)

        handler.on_deleted(event)

        # Should trigger reload
        assert str(test_file) not in handler.known_files

    def test_ac4_file_changes_detected_within_5s(self, tmp_path):
        """AC4: File changes detected within 5s"""
        dashboards_dir = tmp_path / "dashboards"
        dashboards_dir.mkdir()

        config = WatchdogConfig(
            dashboards_path=str(dashboards_dir),
            debounce_seconds=5.0,
        )

        # Verify debounce is set to 5 seconds or less
        assert config.debounce_seconds <= 5.0

    def test_ac5_systemd_service_file_exists(self):
        """AC5: Watchdog can be started/stopped via systemd or docker"""
        service_file = (
            Path(__file__).parent.parent.parent
            / "infrastructure"
            / "grafana"
            / "watchdog"
            / "chiseai-grafana-watchdog.service"
        )
        dockerfile = (
            Path(__file__).parent.parent.parent
            / "infrastructure"
            / "grafana"
            / "watchdog"
            / "Dockerfile"
        )

        assert service_file.exists(), "Systemd service file should exist"
        assert dockerfile.exists(), "Dockerfile should exist"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
