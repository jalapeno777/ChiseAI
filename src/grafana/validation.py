"""Dashboard validation module for Grafana dashboards.

This module provides comprehensive validation for Grafana dashboard JSON files,
ensuring they meet Grafana 10.x schema requirements before provisioning.
"""

import json
import logging
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ValidationError:
    """Represents a single validation error."""

    dashboard_file: str
    field: str
    message: str
    severity: str = "error"  # error, warning


@dataclass
class ValidationResult:
    """Result of dashboard validation."""

    dashboard_file: str
    is_valid: bool
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationError] = field(default_factory=list)
    validated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def all_issues(self) -> list[ValidationError]:
        """Return all issues (errors + warnings)."""
        return self.errors + self.warnings


@dataclass
class HealthStatus:
    """Health check status for dashboards."""

    total_dashboards: int
    valid_dashboards: int
    invalid_dashboards: int
    validation_status: str  # "all", "failed", "mixed"
    last_validation: str | None = None
    malformed_dashboards: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "total_dashboards": self.total_dashboards,
            "valid_dashboards": self.valid_dashboards,
            "invalid_dashboards": self.invalid_dashboards,
            "validation_status": self.validation_status,
            "last_validation": self.last_validation,
            "malformed_dashboards": self.malformed_dashboards,
        }


class DashboardValidator:
    """Validator for Grafana dashboard JSON files.

    Validates dashboards against Grafana 10.x schema requirements:
    - Required fields: title, uid, panels, schemaVersion
    - Panel configuration validity
    - Datasource references
    - Tags and metadata

    Example:
        >>> validator = DashboardValidator()
        >>> result = validator.validate_file("dashboard.json")
        >>> if result.is_valid:
        ...     print("Dashboard is valid")
        ... else:
        ...     for error in result.errors:
        ...         print(f"Error: {error.message}")
    """

    # Grafana 10.x minimum schema version
    MIN_SCHEMA_VERSION = 36
    MAX_SCHEMA_VERSION = 40  # Grafana 10.4.x

    # Required top-level fields
    REQUIRED_FIELDS = ["title", "uid", "panels", "schemaVersion"]

    # Valid panel types in Grafana 10.x
    VALID_PANEL_TYPES = {
        "stat",
        "graph",
        "table",
        "timeseries",
        "gauge",
        "bargauge",
        "heatmap",
        "logs",
        "news",
        "nodeGraph",
        "piechart",
        "row",
        "text",
        "traces",
        "trend",
        "xychart",
        "flamegraph",
        "canvas",
        "geomap",
    }

    # Valid datasource types
    VALID_DATASOURCE_TYPES = {
        "influxdb",
        "prometheus",
        "grafana",
        "mysql",
        "postgres",
        "elasticsearch",
        "loki",
        "tempo",
        "jaeger",
        "zipkin",
        "cloudwatch",
        "azuremonitor",
        "stackdriver",
        " graphite",
    }

    def __init__(
        self,
        provisioning_dir: str | None = None,
        active_dir: str | None = None,
        failed_dir: str | None = None,
    ):
        """Initialize the validator.

        Args:
            provisioning_dir: Directory containing dashboard JSON files to validate
            active_dir: Directory to move valid dashboards to
            failed_dir: Directory to move invalid dashboards to
        """
        self.provisioning_dir = Path(provisioning_dir) if provisioning_dir else None
        self.active_dir = Path(active_dir) if active_dir else None
        self.failed_dir = Path(failed_dir) if failed_dir else None
        self.validation_results: list[ValidationResult] = []

    def validate_file(self, file_path: str | Path) -> ValidationResult:
        """Validate a single dashboard JSON file.

        Args:
            file_path: Path to the dashboard JSON file

        Returns:
            ValidationResult with validation status and any errors
        """
        file_path = Path(file_path)
        dashboard_file = file_path.name

        # Check file exists
        if not file_path.exists():
            error = ValidationError(
                dashboard_file=dashboard_file,
                field="file",
                message=f"File not found: {file_path}",
                severity="error",
            )
            return ValidationResult(
                dashboard_file=dashboard_file,
                is_valid=False,
                errors=[error],
            )

        # Try to parse JSON
        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()
            dashboard = json.loads(content)
        except json.JSONDecodeError as e:
            error = ValidationError(
                dashboard_file=dashboard_file,
                field="json",
                message=f"Invalid JSON: {e}",
                severity="error",
            )
            return ValidationResult(
                dashboard_file=dashboard_file,
                is_valid=False,
                errors=[error],
            )
        except Exception as e:
            error = ValidationError(
                dashboard_file=dashboard_file,
                field="file",
                message=f"Error reading file: {e}",
                severity="error",
            )
            return ValidationResult(
                dashboard_file=dashboard_file,
                is_valid=False,
                errors=[error],
            )

        # Validate dashboard structure
        return self.validate_dashboard(dashboard, dashboard_file)

    def validate_dashboard(
        self, dashboard: dict, dashboard_file: str = "unknown"
    ) -> ValidationResult:
        """Validate a dashboard dictionary.

        Args:
            dashboard: Parsed dashboard JSON as dictionary
            dashboard_file: Name of the dashboard file for error reporting

        Returns:
            ValidationResult with validation status and any errors
        """
        errors = []
        warnings = []

        # Check required fields
        for field in self.REQUIRED_FIELDS:
            if field not in dashboard:
                errors.append(
                    ValidationError(
                        dashboard_file=dashboard_file,
                        field=field,
                        message=f"Missing required field: {field}",
                        severity="error",
                    )
                )

        # Validate schema version
        if "schemaVersion" in dashboard:
            schema_version = dashboard["schemaVersion"]
            if not isinstance(schema_version, int):
                errors.append(
                    ValidationError(
                        dashboard_file=dashboard_file,
                        field="schemaVersion",
                        message=f"schemaVersion must be an integer, got {type(schema_version).__name__}",
                        severity="error",
                    )
                )
            elif schema_version < self.MIN_SCHEMA_VERSION:
                errors.append(
                    ValidationError(
                        dashboard_file=dashboard_file,
                        field="schemaVersion",
                        message=f"schemaVersion {schema_version} is below minimum {self.MIN_SCHEMA_VERSION} for Grafana 10.x",
                        severity="error",
                    )
                )
            elif schema_version > self.MAX_SCHEMA_VERSION:
                warnings.append(
                    ValidationError(
                        dashboard_file=dashboard_file,
                        field="schemaVersion",
                        message=f"schemaVersion {schema_version} is newer than tested maximum {self.MAX_SCHEMA_VERSION}",
                        severity="warning",
                    )
                )

        # Validate title
        if "title" in dashboard:
            title = dashboard["title"]
            if not isinstance(title, str):
                errors.append(
                    ValidationError(
                        dashboard_file=dashboard_file,
                        field="title",
                        message=f"title must be a string, got {type(title).__name__}",
                        severity="error",
                    )
                )
            elif not title.strip():
                errors.append(
                    ValidationError(
                        dashboard_file=dashboard_file,
                        field="title",
                        message="title cannot be empty",
                        severity="error",
                    )
                )

        # Validate uid
        if "uid" in dashboard:
            uid = dashboard["uid"]
            if not isinstance(uid, str):
                errors.append(
                    ValidationError(
                        dashboard_file=dashboard_file,
                        field="uid",
                        message=f"uid must be a string, got {type(uid).__name__}",
                        severity="error",
                    )
                )
            elif not uid.strip():
                errors.append(
                    ValidationError(
                        dashboard_file=dashboard_file,
                        field="uid",
                        message="uid cannot be empty",
                        severity="error",
                    )
                )
            elif not self._is_valid_uid(uid):
                warnings.append(
                    ValidationError(
                        dashboard_file=dashboard_file,
                        field="uid",
                        message=f"uid '{uid}' contains characters that may cause issues",
                        severity="warning",
                    )
                )

        # Validate panels
        if "panels" in dashboard:
            panels = dashboard["panels"]
            if not isinstance(panels, list):
                errors.append(
                    ValidationError(
                        dashboard_file=dashboard_file,
                        field="panels",
                        message=f"panels must be an array, got {type(panels).__name__}",
                        severity="error",
                    )
                )
            elif len(panels) == 0:
                errors.append(
                    ValidationError(
                        dashboard_file=dashboard_file,
                        field="panels",
                        message="panels array cannot be empty",
                        severity="error",
                    )
                )
            else:
                # Validate each panel
                for i, panel in enumerate(panels):
                    panel_errors, panel_warnings = self._validate_panel(
                        panel, i, dashboard_file
                    )
                    errors.extend(panel_errors)
                    warnings.extend(panel_warnings)

        # Validate tags
        if "tags" in dashboard:
            tags = dashboard["tags"]
            if not isinstance(tags, list):
                errors.append(
                    ValidationError(
                        dashboard_file=dashboard_file,
                        field="tags",
                        message=f"tags must be an array, got {type(tags).__name__}",
                        severity="error",
                    )
                )
            else:
                for i, tag in enumerate(tags):
                    if not isinstance(tag, str):
                        errors.append(
                            ValidationError(
                                dashboard_file=dashboard_file,
                                field=f"tags[{i}]",
                                message=f"tag must be a string, got {type(tag).__name__}",
                                severity="error",
                            )
                        )

        # Validate refresh interval
        if "refresh" in dashboard:
            refresh = dashboard["refresh"]
            if not isinstance(refresh, (str, bool)):
                errors.append(
                    ValidationError(
                        dashboard_file=dashboard_file,
                        field="refresh",
                        message=f"refresh must be a string or false, got {type(refresh).__name__}",
                        severity="error",
                    )
                )

        is_valid = len(errors) == 0

        return ValidationResult(
            dashboard_file=dashboard_file,
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
        )

    def _validate_panel(
        self, panel: dict, index: int, dashboard_file: str
    ) -> tuple[list[ValidationError], list[ValidationError]]:
        """Validate a single panel configuration.

        Args:
            panel: Panel configuration dictionary
            index: Panel index in the panels array
            dashboard_file: Name of the dashboard file for error reporting

        Returns:
            Tuple of (errors, warnings) lists for the panel
        """
        errors = []
        warnings = []

        if not isinstance(panel, dict):
            errors.append(
                ValidationError(
                    dashboard_file=dashboard_file,
                    field=f"panels[{index}]",
                    message=f"panel must be an object, got {type(panel).__name__}",
                    severity="error",
                )
            )
            return errors, warnings

        # Check required panel fields
        if "type" not in panel:
            errors.append(
                ValidationError(
                    dashboard_file=dashboard_file,
                    field=f"panels[{index}].type",
                    message=f"panel {index} missing required field: type",
                    severity="error",
                )
            )
        else:
            panel_type = panel["type"]
            if panel_type not in self.VALID_PANEL_TYPES:
                errors.append(
                    ValidationError(
                        dashboard_file=dashboard_file,
                        field=f"panels[{index}].type",
                        message=f"panel {index} has invalid type: {panel_type}",
                        severity="error",
                    )
                )

        # Check for title (optional but recommended)
        if "title" not in panel:
            # Row panels don't strictly need titles, but it's good practice
            pass

        # Validate datasource references in targets
        if "targets" in panel:
            targets = panel["targets"]
            if not isinstance(targets, list):
                errors.append(
                    ValidationError(
                        dashboard_file=dashboard_file,
                        field=f"panels[{index}].targets",
                        message=f"panel {index} targets must be an array",
                        severity="error",
                    )
                )
            else:
                for target_idx, target in enumerate(targets):
                    if isinstance(target, dict) and "datasource" in target:
                        ds = target["datasource"]
                        if isinstance(ds, dict):
                            ds_type = ds.get("type", "")
                            if ds_type and ds_type not in self.VALID_DATASOURCE_TYPES:
                                warnings.append(
                                    ValidationError(
                                        dashboard_file=dashboard_file,
                                        field=f"panels[{index}].targets[{target_idx}].datasource",
                                        message=f"panel {index} target {target_idx} has unknown datasource type: {ds_type}",
                                        severity="warning",
                                    )
                                )

        # Validate gridPos (positioning)
        if "gridPos" in panel:
            grid_pos = panel["gridPos"]
            if not isinstance(grid_pos, dict):
                errors.append(
                    ValidationError(
                        dashboard_file=dashboard_file,
                        field=f"panels[{index}].gridPos",
                        message=f"panel {index} gridPos must be an object",
                        severity="error",
                    )
                )
            else:
                # Check required gridPos fields
                for field in ["h", "w", "x", "y"]:
                    if field in grid_pos and not isinstance(grid_pos[field], int):
                        errors.append(
                            ValidationError(
                                dashboard_file=dashboard_file,
                                field=f"panels[{index}].gridPos.{field}",
                                message=f"panel {index} gridPos.{field} must be an integer",
                                severity="error",
                            )
                        )

        return errors, warnings

    def _is_valid_uid(self, uid: str) -> bool:
        """Check if a UID contains only valid characters.

        Grafana UIDs should be alphanumeric with hyphens and underscores.

        Args:
            uid: The UID to validate

        Returns:
            True if the UID is valid, False otherwise
        """
        valid_chars = set(
            "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
        )
        return all(c in valid_chars for c in uid)

    def validate_all(self) -> list[ValidationResult]:
        """Validate all dashboard files in the provisioning directory.

        Returns:
            List of ValidationResult for each dashboard file
        """
        if not self.provisioning_dir:
            raise ValueError("provisioning_dir must be set to validate all dashboards")

        results = []

        if not self.provisioning_dir.exists():
            logger.warning(
                f"Provisioning directory does not exist: {self.provisioning_dir}"
            )
            return results

        # Find all JSON files
        json_files = list(self.provisioning_dir.glob("*.json"))

        for json_file in json_files:
            result = self.validate_file(json_file)
            results.append(result)
            self.validation_results.append(result)

            # Log results
            if result.is_valid:
                logger.info(f"✓ Valid dashboard: {result.dashboard_file}")
                for warning in result.warnings:
                    logger.warning(f"  ⚠ {warning.field}: {warning.message}")
            else:
                logger.error(f"✗ Invalid dashboard: {result.dashboard_file}")
                for error in result.errors:
                    logger.error(f"  ✗ {error.field}: {error.message}")

        return results

    def process_dashboards(self) -> HealthStatus:
        """Validate all dashboards and move them to appropriate directories.

        Valid dashboards are moved to active_dir, invalid to failed_dir.

        Returns:
            HealthStatus summarizing the validation results
        """
        if not self.provisioning_dir:
            raise ValueError("provisioning_dir must be set")

        # Ensure output directories exist
        if self.active_dir:
            self.active_dir.mkdir(parents=True, exist_ok=True)
        if self.failed_dir:
            self.failed_dir.mkdir(parents=True, exist_ok=True)

        # Validate all dashboards
        results = self.validate_all()

        # Move files based on validation results
        malformed_dashboards = []
        valid_count = 0
        invalid_count = 0

        for result in results:
            source_file = self.provisioning_dir / result.dashboard_file

            if result.is_valid:
                valid_count += 1
                if self.active_dir:
                    dest_file = self.active_dir / result.dashboard_file
                    shutil.copy2(source_file, dest_file)
                    logger.info(
                        f"Moved valid dashboard to active: {result.dashboard_file}"
                    )
            else:
                invalid_count += 1
                malformed_dashboards.append(
                    {
                        "file": result.dashboard_file,
                        "errors": [e.message for e in result.errors],
                    }
                )
                if self.failed_dir:
                    dest_file = self.failed_dir / result.dashboard_file
                    shutil.copy2(source_file, dest_file)
                    logger.info(
                        f"Moved invalid dashboard to failed: {result.dashboard_file}"
                    )

        # Determine validation status
        if invalid_count == 0:
            validation_status = "all"
        elif valid_count == 0:
            validation_status = "failed"
        else:
            validation_status = "mixed"

        return HealthStatus(
            total_dashboards=len(results),
            valid_dashboards=valid_count,
            invalid_dashboards=invalid_count,
            validation_status=validation_status,
            last_validation=datetime.now(UTC).isoformat(),
            malformed_dashboards=malformed_dashboards,
        )

    def get_health_status(self) -> HealthStatus:
        """Get current health status without re-validating.

        Returns:
            HealthStatus based on the last validation run
        """
        if not self.validation_results:
            # Run validation if not already done
            return self.process_dashboards()

        valid_count = sum(1 for r in self.validation_results if r.is_valid)
        invalid_count = len(self.validation_results) - valid_count

        malformed_dashboards = [
            {"file": r.dashboard_file, "errors": [e.message for e in r.errors]}
            for r in self.validation_results
            if not r.is_valid
        ]

        if invalid_count == 0:
            validation_status = "all"
        elif valid_count == 0:
            validation_status = "failed"
        else:
            validation_status = "mixed"

        last_validation = None
        if self.validation_results:
            last_validation = self.validation_results[0].validated_at.isoformat()

        return HealthStatus(
            total_dashboards=len(self.validation_results),
            valid_dashboards=valid_count,
            invalid_dashboards=invalid_count,
            validation_status=validation_status,
            last_validation=last_validation,
            malformed_dashboards=malformed_dashboards,
        )
