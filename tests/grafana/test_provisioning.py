"""Tests for Grafana dashboard provisioning validation and health checks."""

import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest

from src.grafana.health import (
    DashboardHealthEndpoint,
    create_health_endpoint,
    handle_health_request,
)
from src.grafana.validation import (
    DashboardValidator,
    HealthStatus,
    ValidationError,
    ValidationResult,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    tmpdir = tempfile.mkdtemp()
    yield Path(tmpdir)
    shutil.rmtree(tmpdir)


@pytest.fixture
def valid_dashboard():
    """Return a valid Grafana 10.x dashboard."""
    return {
        "title": "Test Dashboard",
        "uid": "test-dashboard-001",
        "schemaVersion": 39,
        "panels": [
            {
                "id": 1,
                "title": "Test Panel",
                "type": "stat",
                "gridPos": {"h": 6, "w": 6, "x": 0, "y": 0},
                "targets": [
                    {
                        "datasource": {"type": "influxdb", "uid": "test-ds"},
                        "query": 'from(bucket: "test")',
                    }
                ],
            }
        ],
        "tags": ["test", "chiseai"],
        "refresh": "30s",
    }


@pytest.fixture
def dashboard_with_warnings():
    """Return a valid dashboard with warnings."""
    return {
        "title": "Test Dashboard With Warnings",
        "uid": "test-dashboard-warn",
        "schemaVersion": 41,  # Newer than tested maximum
        "panels": [
            {
                "id": 1,
                "title": "Test Panel",
                "type": "stat",
                "gridPos": {"h": 6, "w": 6, "x": 0, "y": 0},
                "targets": [],
            }
        ],
        "tags": ["test"],
    }


@pytest.fixture
def dashboard_missing_title():
    """Return a dashboard missing the title field."""
    return {
        "uid": "test-no-title",
        "schemaVersion": 39,
        "panels": [{"id": 1, "type": "stat"}],
    }


@pytest.fixture
def dashboard_missing_uid():
    """Return a dashboard missing the uid field."""
    return {
        "title": "No UID Dashboard",
        "schemaVersion": 39,
        "panels": [{"id": 1, "type": "stat"}],
    }


@pytest.fixture
def dashboard_missing_panels():
    """Return a dashboard missing the panels field."""
    return {
        "title": "No Panels Dashboard",
        "uid": "test-no-panels",
        "schemaVersion": 39,
    }


@pytest.fixture
def dashboard_empty_panels():
    """Return a dashboard with empty panels array."""
    return {
        "title": "Empty Panels Dashboard",
        "uid": "test-empty-panels",
        "schemaVersion": 39,
        "panels": [],
    }


@pytest.fixture
def dashboard_invalid_schema_version():
    """Return a dashboard with invalid schema version."""
    return {
        "title": "Old Schema Dashboard",
        "uid": "test-old-schema",
        "schemaVersion": 30,  # Below minimum for Grafana 10.x
        "panels": [{"id": 1, "type": "stat"}],
    }


@pytest.fixture
def dashboard_invalid_panel_type():
    """Return a dashboard with invalid panel type."""
    return {
        "title": "Invalid Panel Type Dashboard",
        "uid": "test-invalid-panel",
        "schemaVersion": 39,
        "panels": [
            {
                "id": 1,
                "title": "Bad Panel",
                "type": "invalid_type_xyz",
                "gridPos": {"h": 6, "w": 6, "x": 0, "y": 0},
            }
        ],
    }


@pytest.fixture
def dashboard_missing_panel_type():
    """Return a dashboard with panel missing type field."""
    return {
        "title": "Missing Panel Type Dashboard",
        "uid": "test-missing-panel-type",
        "schemaVersion": 39,
        "panels": [{"id": 1, "title": "No Type Panel"}],
    }


@pytest.fixture
def dashboard_invalid_json():
    """Return invalid JSON string."""
    return '{"title": "Broken", "uid": "test", "panels": [}'


@pytest.fixture
def dashboard_empty_title():
    """Return a dashboard with empty title."""
    return {
        "title": "",
        "uid": "test-empty-title",
        "schemaVersion": 39,
        "panels": [{"id": 1, "type": "stat"}],
    }


@pytest.fixture
def dashboard_invalid_uid_chars():
    """Return a dashboard with potentially problematic UID characters."""
    return {
        "title": "Weird UID Dashboard",
        "uid": "test@uid#with$pecial%chars",
        "schemaVersion": 39,
        "panels": [{"id": 1, "type": "stat"}],
    }


@pytest.fixture
def dashboard_invalid_gridpos():
    """Return a dashboard with invalid gridPos types."""
    return {
        "title": "Bad GridPos Dashboard",
        "uid": "test-bad-gridpos",
        "schemaVersion": 39,
        "panels": [
            {
                "id": 1,
                "type": "stat",
                "gridPos": {"h": "six", "w": 6, "x": 0, "y": 0},
            }
        ],
    }


@pytest.fixture
def dashboard_invalid_tags():
    """Return a dashboard with invalid tags."""
    return {
        "title": "Bad Tags Dashboard",
        "uid": "test-bad-tags",
        "schemaVersion": 39,
        "panels": [{"id": 1, "type": "stat"}],
        "tags": ["valid", 123, None],
    }


@pytest.fixture
def dashboard_unknown_datasource():
    """Return a dashboard with unknown datasource type (warning only)."""
    return {
        "title": "Unknown Datasource Dashboard",
        "uid": "test-unknown-ds",
        "schemaVersion": 39,
        "panels": [
            {
                "id": 1,
                "type": "stat",
                "gridPos": {"h": 6, "w": 6, "x": 0, "y": 0},
                "targets": [
                    {
                        "datasource": {"type": "custom_datasource_xyz", "uid": "test"},
                        "query": "test",
                    }
                ],
            }
        ],
    }


# =============================================================================
# Test DashboardValidator
# =============================================================================


class TestDashboardValidator:
    """Tests for the DashboardValidator class."""

    def test_validator_initialization(self, temp_dir):
        """Test validator can be initialized with paths."""
        validator = DashboardValidator(
            provisioning_dir=str(temp_dir),
            active_dir=str(temp_dir / "active"),
            failed_dir=str(temp_dir / "failed"),
        )
        assert validator.provisioning_dir == temp_dir
        assert validator.active_dir == temp_dir / "active"
        assert validator.failed_dir == temp_dir / "failed"

    def test_validate_valid_dashboard(self, valid_dashboard):
        """Test validation passes for a valid dashboard."""
        validator = DashboardValidator()
        result = validator.validate_dashboard(valid_dashboard, "test.json")

        assert result.is_valid is True
        assert len(result.errors) == 0
        assert result.dashboard_file == "test.json"

    def test_validate_dashboard_missing_title(self, dashboard_missing_title):
        """Test validation fails for dashboard missing title."""
        validator = DashboardValidator()
        result = validator.validate_dashboard(dashboard_missing_title, "test.json")

        assert result.is_valid is False
        assert any(e.field == "title" for e in result.errors)

    def test_validate_dashboard_missing_uid(self, dashboard_missing_uid):
        """Test validation fails for dashboard missing uid."""
        validator = DashboardValidator()
        result = validator.validate_dashboard(dashboard_missing_uid, "test.json")

        assert result.is_valid is False
        assert any(e.field == "uid" for e in result.errors)

    def test_validate_dashboard_missing_panels(self, dashboard_missing_panels):
        """Test validation fails for dashboard missing panels."""
        validator = DashboardValidator()
        result = validator.validate_dashboard(dashboard_missing_panels, "test.json")

        assert result.is_valid is False
        assert any(e.field == "panels" for e in result.errors)

    def test_validate_dashboard_empty_panels(self, dashboard_empty_panels):
        """Test validation fails for dashboard with empty panels."""
        validator = DashboardValidator()
        result = validator.validate_dashboard(dashboard_empty_panels, "test.json")

        assert result.is_valid is False
        assert any("empty" in e.message.lower() for e in result.errors)

    def test_validate_dashboard_invalid_schema_version(
        self, dashboard_invalid_schema_version
    ):
        """Test validation fails for old schema version."""
        validator = DashboardValidator()
        result = validator.validate_dashboard(
            dashboard_invalid_schema_version, "test.json"
        )

        assert result.is_valid is False
        assert any(e.field == "schemaVersion" for e in result.errors)

    def test_validate_dashboard_invalid_panel_type(self, dashboard_invalid_panel_type):
        """Test validation fails for invalid panel type."""
        validator = DashboardValidator()
        result = validator.validate_dashboard(dashboard_invalid_panel_type, "test.json")

        assert result.is_valid is False
        assert any("invalid type" in e.message.lower() for e in result.errors)

    def test_validate_dashboard_missing_panel_type(self, dashboard_missing_panel_type):
        """Test validation fails for panel missing type field."""
        validator = DashboardValidator()
        result = validator.validate_dashboard(dashboard_missing_panel_type, "test.json")

        assert result.is_valid is False
        assert any(e.field.endswith(".type") for e in result.errors)

    def test_validate_dashboard_empty_title(self, dashboard_empty_title):
        """Test validation fails for empty title."""
        validator = DashboardValidator()
        result = validator.validate_dashboard(dashboard_empty_title, "test.json")

        assert result.is_valid is False
        assert any("empty" in e.message.lower() for e in result.errors)

    def test_validate_dashboard_with_warnings(self, dashboard_with_warnings):
        """Test validation passes but includes warnings."""
        validator = DashboardValidator()
        result = validator.validate_dashboard(dashboard_with_warnings, "test.json")

        assert result.is_valid is True
        assert len(result.warnings) > 0
        assert any("schemaVersion" in w.field for w in result.warnings)

    def test_validate_dashboard_invalid_uid_chars(self, dashboard_invalid_uid_chars):
        """Test validation warns for problematic UID characters."""
        validator = DashboardValidator()
        result = validator.validate_dashboard(dashboard_invalid_uid_chars, "test.json")

        assert result.is_valid is True  # Still valid, just warning
        assert len(result.warnings) > 0
        assert any("uid" in w.field for w in result.warnings)

    def test_validate_dashboard_invalid_gridpos(self, dashboard_invalid_gridpos):
        """Test validation fails for invalid gridPos types."""
        validator = DashboardValidator()
        result = validator.validate_dashboard(dashboard_invalid_gridpos, "test.json")

        assert result.is_valid is False
        assert any("gridPos" in e.field for e in result.errors)

    def test_validate_dashboard_invalid_tags(self, dashboard_invalid_tags):
        """Test validation fails for invalid tags."""
        validator = DashboardValidator()
        result = validator.validate_dashboard(dashboard_invalid_tags, "test.json")

        assert result.is_valid is False
        assert any("tags" in e.field for e in result.errors)

    def test_validate_dashboard_unknown_datasource(self, dashboard_unknown_datasource):
        """Test validation warns for unknown datasource."""
        validator = DashboardValidator()
        result = validator.validate_dashboard(dashboard_unknown_datasource, "test.json")

        assert result.is_valid is True  # Still valid, just warning
        assert len(result.warnings) > 0
        assert any("datasource" in w.field for w in result.warnings)

    def test_validate_file_not_found(self, temp_dir):
        """Test validation handles missing file."""
        validator = DashboardValidator()
        result = validator.validate_file(temp_dir / "nonexistent.json")

        assert result.is_valid is False
        assert any("not found" in e.message.lower() for e in result.errors)

    def test_validate_invalid_json(self, temp_dir, dashboard_invalid_json):
        """Test validation handles invalid JSON."""
        json_file = temp_dir / "invalid.json"
        with open(json_file, "w") as f:
            f.write(dashboard_invalid_json)

        validator = DashboardValidator()
        result = validator.validate_file(json_file)

        assert result.is_valid is False
        assert any("json" in e.field.lower() for e in result.errors)

    def test_validate_file_success(self, temp_dir, valid_dashboard):
        """Test validation from file succeeds."""
        json_file = temp_dir / "valid.json"
        with open(json_file, "w") as f:
            json.dump(valid_dashboard, f)

        validator = DashboardValidator()
        result = validator.validate_file(json_file)

        assert result.is_valid is True

    def test_validate_all_empty_dir(self, temp_dir):
        """Test validate_all with empty directory."""
        validator = DashboardValidator(provisioning_dir=str(temp_dir))
        results = validator.validate_all()

        assert len(results) == 0

    def test_validate_all_multiple_files(
        self, temp_dir, valid_dashboard, dashboard_missing_title
    ):
        """Test validate_all with multiple files."""
        # Create valid dashboard
        with open(temp_dir / "valid.json", "w") as f:
            json.dump(valid_dashboard, f)

        # Create invalid dashboard
        with open(temp_dir / "invalid.json", "w") as f:
            json.dump(dashboard_missing_title, f)

        validator = DashboardValidator(provisioning_dir=str(temp_dir))
        results = validator.validate_all()

        assert len(results) == 2
        assert any(r.is_valid for r in results)
        assert any(not r.is_valid for r in results)

    def test_process_dashboards(
        self, temp_dir, valid_dashboard, dashboard_missing_title
    ):
        """Test process_dashboards moves files correctly."""
        # Create dashboards
        with open(temp_dir / "valid.json", "w") as f:
            json.dump(valid_dashboard, f)
        with open(temp_dir / "invalid.json", "w") as f:
            json.dump(dashboard_missing_title, f)

        active_dir = temp_dir / "active"
        failed_dir = temp_dir / "failed"

        validator = DashboardValidator(
            provisioning_dir=str(temp_dir),
            active_dir=str(active_dir),
            failed_dir=str(failed_dir),
        )
        status = validator.process_dashboards()

        assert status.total_dashboards == 2
        assert status.valid_dashboards == 1
        assert status.invalid_dashboards == 1
        assert status.validation_status == "mixed"
        assert (active_dir / "valid.json").exists()
        assert (failed_dir / "invalid.json").exists()

    def test_get_health_status(self, temp_dir, valid_dashboard):
        """Test get_health_status returns cached results."""
        with open(temp_dir / "valid.json", "w") as f:
            json.dump(valid_dashboard, f)

        validator = DashboardValidator(provisioning_dir=str(temp_dir))
        validator.validate_all()

        status = validator.get_health_status()

        assert status.total_dashboards == 1
        assert status.valid_dashboards == 1
        assert status.validation_status == "all"

    def test_get_health_status_no_validation(self, temp_dir, valid_dashboard):
        """Test get_health_status runs validation if not cached."""
        with open(temp_dir / "valid.json", "w") as f:
            json.dump(valid_dashboard, f)

        validator = DashboardValidator(provisioning_dir=str(temp_dir))
        status = validator.get_health_status()

        assert status.total_dashboards == 1


# =============================================================================
# Test HealthStatus
# =============================================================================


class TestHealthStatus:
    """Tests for the HealthStatus dataclass."""

    def test_health_status_creation(self):
        """Test HealthStatus can be created."""
        status = HealthStatus(
            total_dashboards=5,
            valid_dashboards=4,
            invalid_dashboards=1,
            validation_status="mixed",
        )

        assert status.total_dashboards == 5
        assert status.valid_dashboards == 4
        assert status.invalid_dashboards == 1
        assert status.validation_status == "mixed"

    def test_health_status_to_dict(self):
        """Test HealthStatus converts to dict correctly."""
        malformed = [{"file": "bad.json", "errors": ["Missing title"]}]
        status = HealthStatus(
            total_dashboards=3,
            valid_dashboards=2,
            invalid_dashboards=1,
            validation_status="mixed",
            last_validation="2026-02-11T12:00:00",
            malformed_dashboards=malformed,
        )

        d = status.to_dict()

        assert d["total_dashboards"] == 3
        assert d["valid_dashboards"] == 2
        assert d["invalid_dashboards"] == 1
        assert d["validation_status"] == "mixed"
        assert d["last_validation"] == "2026-02-11T12:00:00"
        assert d["malformed_dashboards"] == malformed


# =============================================================================
# Test DashboardHealthEndpoint
# =============================================================================


class TestDashboardHealthEndpoint:
    """Tests for the DashboardHealthEndpoint class."""

    def test_endpoint_initialization(self, temp_dir):
        """Test endpoint can be initialized."""
        endpoint = DashboardHealthEndpoint(
            provisioning_dir=str(temp_dir),
            active_dir=str(temp_dir / "active"),
            failed_dir=str(temp_dir / "failed"),
        )
        assert endpoint.provisioning_dir == temp_dir

    def test_check_health(self, temp_dir, valid_dashboard):
        """Test health check returns status."""
        with open(temp_dir / "valid.json", "w") as f:
            json.dump(valid_dashboard, f)

        endpoint = DashboardHealthEndpoint(provisioning_dir=str(temp_dir))
        status = endpoint.check_health()

        assert status.total_dashboards == 1
        assert status.valid_dashboards == 1
        assert status.validation_status == "all"

    def test_check_health_force_refresh(self, temp_dir, valid_dashboard):
        """Test force refresh re-validates dashboards."""
        with open(temp_dir / "valid.json", "w") as f:
            json.dump(valid_dashboard, f)

        endpoint = DashboardHealthEndpoint(provisioning_dir=str(temp_dir))
        status1 = endpoint.check_health()

        # Add another dashboard
        with open(temp_dir / "valid2.json", "w") as f:
            json.dump(valid_dashboard, f)

        status2 = endpoint.check_health(force_refresh=True)

        assert status2.total_dashboards == 2

    def test_get_health_json(self, temp_dir, valid_dashboard):
        """Test health status returned as JSON."""
        with open(temp_dir / "valid.json", "w") as f:
            json.dump(valid_dashboard, f)

        endpoint = DashboardHealthEndpoint(provisioning_dir=str(temp_dir))
        json_str = endpoint.get_health_json()

        data = json.loads(json_str)
        assert data["total_dashboards"] == 1
        assert data["validation_status"] == "all"

    def test_get_health_dict(self, temp_dir, valid_dashboard):
        """Test health status returned as dict."""
        with open(temp_dir / "valid.json", "w") as f:
            json.dump(valid_dashboard, f)

        endpoint = DashboardHealthEndpoint(provisioning_dir=str(temp_dir))
        data = endpoint.get_health_dict()

        assert data["total_dashboards"] == 1
        assert data["validation_status"] == "all"

    def test_is_healthy_all_valid(self, temp_dir, valid_dashboard):
        """Test is_healthy returns True when all valid."""
        with open(temp_dir / "valid.json", "w") as f:
            json.dump(valid_dashboard, f)

        endpoint = DashboardHealthEndpoint(provisioning_dir=str(temp_dir))
        assert endpoint.is_healthy() is True

    def test_is_healthy_with_invalid(
        self, temp_dir, valid_dashboard, dashboard_missing_title
    ):
        """Test is_healthy returns False when invalid exists."""
        with open(temp_dir / "valid.json", "w") as f:
            json.dump(valid_dashboard, f)
        with open(temp_dir / "invalid.json", "w") as f:
            json.dump(dashboard_missing_title, f)

        endpoint = DashboardHealthEndpoint(provisioning_dir=str(temp_dir))
        assert endpoint.is_healthy() is False

    def test_get_malformed_dashboards(
        self, temp_dir, valid_dashboard, dashboard_missing_title
    ):
        """Test getting list of malformed dashboards."""
        with open(temp_dir / "valid.json", "w") as f:
            json.dump(valid_dashboard, f)
        with open(temp_dir / "invalid.json", "w") as f:
            json.dump(dashboard_missing_title, f)

        endpoint = DashboardHealthEndpoint(provisioning_dir=str(temp_dir))
        malformed = endpoint.get_malformed_dashboards()

        assert len(malformed) == 1
        assert malformed[0]["file"] == "invalid.json"

    def test_format_health_report(self, temp_dir, valid_dashboard):
        """Test health report formatting."""
        with open(temp_dir / "valid.json", "w") as f:
            json.dump(valid_dashboard, f)

        endpoint = DashboardHealthEndpoint(provisioning_dir=str(temp_dir))
        report = endpoint.format_health_report()

        assert "Grafana Dashboard Health Report" in report
        assert "Total Dashboards: 1" in report
        assert "Status: ALL" in report


# =============================================================================
# Test Helper Functions
# =============================================================================


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_create_health_endpoint(self, temp_dir):
        """Test create_health_endpoint factory function."""
        endpoint = create_health_endpoint(
            provisioning_dir=str(temp_dir),
            active_dir=str(temp_dir / "active"),
            failed_dir=str(temp_dir / "failed"),
        )

        assert isinstance(endpoint, DashboardHealthEndpoint)
        assert endpoint.provisioning_dir == temp_dir

    def test_handle_health_request(self, temp_dir, valid_dashboard):
        """Test handle_health_request function."""
        with open(temp_dir / "valid.json", "w") as f:
            json.dump(valid_dashboard, f)

        response = handle_health_request(provisioning_dir=str(temp_dir))

        assert response["status_code"] == 200
        assert response["status_text"] == "healthy"
        assert response["total_dashboards"] == 1

    def test_handle_health_request_degraded(self, temp_dir, dashboard_missing_title):
        """Test handle_health_request returns degraded status."""
        with open(temp_dir / "invalid.json", "w") as f:
            json.dump(dashboard_missing_title, f)

        response = handle_health_request(provisioning_dir=str(temp_dir))

        assert response["status_code"] == 503
        assert response["status_text"] == "degraded"


# =============================================================================
# Test ValidationError and ValidationResult
# =============================================================================


class TestValidationDataClasses:
    """Tests for ValidationError and ValidationResult dataclasses."""

    def test_validation_error_creation(self):
        """Test ValidationError can be created."""
        error = ValidationError(
            dashboard_file="test.json",
            field="title",
            message="Title is missing",
            severity="error",
        )

        assert error.dashboard_file == "test.json"
        assert error.field == "title"
        assert error.message == "Title is missing"
        assert error.severity == "error"

    def test_validation_result_creation(self):
        """Test ValidationResult can be created."""
        error = ValidationError(
            dashboard_file="test.json",
            field="title",
            message="Title is missing",
        )
        result = ValidationResult(
            dashboard_file="test.json",
            is_valid=False,
            errors=[error],
        )

        assert result.dashboard_file == "test.json"
        assert result.is_valid is False
        assert len(result.errors) == 1

    def test_validation_result_all_issues(self):
        """Test all_issues combines errors and warnings."""
        error = ValidationError(
            dashboard_file="test.json",
            field="title",
            message="Title is missing",
        )
        warning = ValidationError(
            dashboard_file="test.json",
            field="uid",
            message="UID has unusual characters",
            severity="warning",
        )
        result = ValidationResult(
            dashboard_file="test.json",
            is_valid=False,
            errors=[error],
            warnings=[warning],
        )

        assert len(result.all_issues) == 2


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests for the complete validation pipeline."""

    def test_full_validation_pipeline(
        self, temp_dir, valid_dashboard, dashboard_missing_title
    ):
        """Test complete validation and processing pipeline."""
        # Setup directories
        active_dir = temp_dir / "active"
        failed_dir = temp_dir / "failed"

        # Create dashboards
        with open(temp_dir / "good.json", "w") as f:
            json.dump(valid_dashboard, f)
        with open(temp_dir / "bad.json", "w") as f:
            json.dump(dashboard_missing_title, f)
        with open(temp_dir / "another_good.json", "w") as f:
            json.dump({**valid_dashboard, "uid": "another-good"}, f)

        # Run validation pipeline
        endpoint = DashboardHealthEndpoint(
            provisioning_dir=str(temp_dir),
            active_dir=str(active_dir),
            failed_dir=str(failed_dir),
        )
        status = endpoint.check_health()

        # Verify results
        assert status.total_dashboards == 3
        assert status.valid_dashboards == 2
        assert status.invalid_dashboards == 1
        assert status.validation_status == "mixed"
        assert len(status.malformed_dashboards) == 1

        # Verify files were copied
        assert (active_dir / "good.json").exists()
        assert (active_dir / "another_good.json").exists()
        assert (failed_dir / "bad.json").exists()

    def test_health_endpoint_json_response(
        self, temp_dir, valid_dashboard, dashboard_missing_title
    ):
        """Test JSON response format matches expected API structure."""
        with open(temp_dir / "valid.json", "w") as f:
            json.dump(valid_dashboard, f)
        with open(temp_dir / "invalid.json", "w") as f:
            json.dump(dashboard_missing_title, f)

        response = handle_health_request(provisioning_dir=str(temp_dir))

        # Verify response structure
        assert "total_dashboards" in response
        assert "valid_dashboards" in response
        assert "invalid_dashboards" in response
        assert "validation_status" in response
        assert "last_validation" in response
        assert "malformed_dashboards" in response
        assert "status_code" in response
        assert "status_text" in response

        # Verify types
        assert isinstance(response["total_dashboards"], int)
        assert isinstance(response["validation_status"], str)
        assert isinstance(response["malformed_dashboards"], list)

    def test_empty_provisioning_directory(self, temp_dir):
        """Test handling of empty provisioning directory."""
        endpoint = DashboardHealthEndpoint(provisioning_dir=str(temp_dir))
        status = endpoint.check_health()

        assert status.total_dashboards == 0
        assert status.valid_dashboards == 0
        assert status.invalid_dashboards == 0
        assert status.validation_status == "all"  # No failures

    def test_nonexistent_provisioning_directory(self, temp_dir):
        """Test handling of non-existent provisioning directory."""
        nonexistent = temp_dir / "does_not_exist"
        endpoint = DashboardHealthEndpoint(provisioning_dir=str(nonexistent))
        status = endpoint.check_health()

        assert status.total_dashboards == 0

    def test_multiple_validation_runs(self, temp_dir, valid_dashboard):
        """Test that multiple validation runs work correctly."""
        with open(temp_dir / "valid.json", "w") as f:
            json.dump(valid_dashboard, f)

        endpoint = DashboardHealthEndpoint(provisioning_dir=str(temp_dir))

        # First run
        status1 = endpoint.check_health()
        assert status1.total_dashboards == 1

        # Second run (cached)
        status2 = endpoint.check_health()
        assert status2.total_dashboards == 1

        # Third run (forced refresh)
        status3 = endpoint.check_health(force_refresh=True)
        assert status3.total_dashboards == 1

    def test_complex_dashboard_validation(self, temp_dir):
        """Test validation of a complex real-world dashboard structure."""
        complex_dashboard = {
            "annotations": {
                "list": [
                    {
                        "builtIn": 1,
                        "datasource": {"type": "grafana", "uid": "-- Grafana --"},
                        "enable": True,
                        "hide": True,
                        "iconColor": "rgba(0, 211, 255, 1)",
                        "name": "Annotations & Alerts",
                        "type": "dashboard",
                    }
                ]
            },
            "description": "Complex test dashboard",
            "editable": True,
            "fiscalYearStartMonth": 0,
            "graphTooltip": 0,
            "id": None,
            "links": [],
            "liveNow": False,
            "panels": [
                {
                    "collapsed": False,
                    "gridPos": {"h": 1, "w": 24, "x": 0, "y": 0},
                    "id": 1,
                    "panels": [],
                    "title": "Overview",
                    "type": "row",
                },
                {
                    "datasource": {"type": "influxdb", "uid": "test-ds"},
                    "fieldConfig": {
                        "defaults": {
                            "color": {"mode": "thresholds"},
                            "mappings": [],
                            "thresholds": {
                                "mode": "absolute",
                                "steps": [
                                    {"color": "red", "value": None},
                                    {"color": "yellow", "value": 1},
                                    {"color": "green", "value": 2},
                                ],
                            },
                            "unit": "none",
                        },
                        "overrides": [],
                    },
                    "gridPos": {"h": 6, "w": 6, "x": 0, "y": 1},
                    "id": 2,
                    "options": {
                        "colorMode": "value",
                        "graphMode": "area",
                        "justifyMode": "auto",
                        "orientation": "auto",
                        "reduceOptions": {
                            "calcs": ["lastNotNull"],
                            "fields": "",
                            "values": False,
                        },
                        "showPercentChange": False,
                        "textMode": "auto",
                        "wideLayout": True,
                    },
                    "pluginVersion": "10.4.2",
                    "targets": [
                        {
                            "datasource": {"type": "influxdb", "uid": "test-ds"},
                            "query": 'from(bucket: "test")',
                            "refId": "A",
                        }
                    ],
                    "title": "Test Metric",
                    "type": "stat",
                },
            ],
            "refresh": "30s",
            "schemaVersion": 39,
            "tags": ["test", "chiseai", "complex"],
            "templating": {
                "list": [
                    {
                        "current": {"selected": False, "text": "Test", "value": "test"},
                        "hide": 0,
                        "label": "Bucket",
                        "name": "bucket",
                        "options": [],
                        "query": "test",
                        "skipUrlSync": False,
                        "type": "textbox",
                    }
                ]
            },
            "time": {"from": "now-7d", "to": "now"},
            "timepicker": {
                "refresh_intervals": [
                    "5s",
                    "10s",
                    "30s",
                    "1m",
                    "5m",
                    "15m",
                    "30m",
                    "1h",
                ]
            },
            "timezone": "UTC",
            "title": "Complex Test Dashboard",
            "uid": "complex-test-dashboard",
            "version": 1,
            "weekStart": "",
        }

        with open(temp_dir / "complex.json", "w") as f:
            json.dump(complex_dashboard, f)

        validator = DashboardValidator(provisioning_dir=str(temp_dir))
        result = validator.validate_file(temp_dir / "complex.json")

        assert result.is_valid is True
        assert len(result.errors) == 0
