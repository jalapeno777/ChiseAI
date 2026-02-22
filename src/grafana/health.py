"""Health check endpoints for Grafana dashboards.

This module provides health check functionality for monitoring
dashboard validation status and system health.
"""

import json
import logging
from pathlib import Path
from typing import Any

from src.grafana.validation import DashboardValidator, HealthStatus

logger = logging.getLogger(__name__)


class DashboardHealthEndpoint:
    """Health endpoint for dashboard validation status.

    Provides an HTTP-like interface for checking dashboard health status
    that can be integrated with monitoring systems or called directly.

    Example:
        >>> endpoint = DashboardHealthEndpoint("/path/to/dashboards")
        >>> status = endpoint.check_health()
        >>> print(status.to_dict())
        {
            "total_dashboards": 5,
            "valid_dashboards": 4,
            "invalid_dashboards": 1,
            "validation_status": "mixed",
            "last_validation": "2026-02-11T12:00:00",
            "malformed_dashboards": [...]
        }
    """

    def __init__(
        self,
        provisioning_dir: str,
        active_dir: str | None = None,
        failed_dir: str | None = None,
    ):
        """Initialize the health endpoint.

        Args:
            provisioning_dir: Directory containing dashboard JSON files
            active_dir: Directory for valid dashboards (optional)
            failed_dir: Directory for invalid dashboards (optional)
        """
        self.provisioning_dir = Path(provisioning_dir)
        self.active_dir = Path(active_dir) if active_dir else None
        self.failed_dir = Path(failed_dir) if failed_dir else None
        self._validator: DashboardValidator | None = None
        self._last_status: HealthStatus | None = None

    def _get_validator(self) -> DashboardValidator:
        """Get or create the dashboard validator."""
        if self._validator is None:
            self._validator = DashboardValidator(
                provisioning_dir=str(self.provisioning_dir),
                active_dir=str(self.active_dir) if self.active_dir else None,
                failed_dir=str(self.failed_dir) if self.failed_dir else None,
            )
        return self._validator

    def check_health(self, force_refresh: bool = False) -> HealthStatus:
        """Check the health status of all dashboards.

        Args:
            force_refresh: If True, re-validate all dashboards even if
                          cached results exist

        Returns:
            HealthStatus with current validation results
        """
        validator = self._get_validator()

        if force_refresh or self._last_status is None:
            self._last_status = validator.process_dashboards()
        else:
            self._last_status = validator.get_health_status()

        return self._last_status

    def get_health_json(self, force_refresh: bool = False) -> str:
        """Get health status as a JSON string.

        Args:
            force_refresh: If True, re-validate all dashboards

        Returns:
            JSON string with health status
        """
        status = self.check_health(force_refresh)
        return json.dumps(status.to_dict(), indent=2)

    def get_health_dict(self, force_refresh: bool = False) -> dict[str, Any]:
        """Get health status as a dictionary.

        Args:
            force_refresh: If True, re-validate all dashboards

        Returns:
            Dictionary with health status
        """
        status = self.check_health(force_refresh)
        return status.to_dict()

    def is_healthy(self) -> bool:
        """Quick check if all dashboards are valid.

        Returns:
            True if all dashboards passed validation, False otherwise
        """
        status = self.check_health()
        return status.validation_status == "all"

    def get_malformed_dashboards(self) -> list[dict[str, Any]]:
        """Get list of malformed dashboards with error details.

        Returns:
            List of dictionaries with file names and error messages
        """
        status = self.check_health()
        return status.malformed_dashboards

    def format_health_report(self) -> str:
        """Format a human-readable health report.

        Returns:
            Formatted string with health status details
        """
        status = self.check_health()

        lines = [
            "=" * 60,
            "Grafana Dashboard Health Report",
            "=" * 60,
            f"Timestamp: {status.last_validation or 'N/A'}",
            f"Total Dashboards: {status.total_dashboards}",
            f"Valid: {status.valid_dashboards}",
            f"Invalid: {status.invalid_dashboards}",
            f"Status: {status.validation_status.upper()}",
            "-" * 60,
        ]

        if status.malformed_dashboards:
            lines.append("Malformed Dashboards:")
            for dashboard in status.malformed_dashboards:
                lines.append(f"  - {dashboard['file']}")
                for error in dashboard["errors"]:
                    lines.append(f"    * {error}")
        else:
            lines.append("All dashboards are valid!")

        lines.append("=" * 60)

        return "\n".join(lines)


def create_health_endpoint(
    provisioning_dir: str | None = None,
    active_dir: str | None = None,
    failed_dir: str | None = None,
) -> DashboardHealthEndpoint:
    """Create a health endpoint with default paths.

    Uses environment variables or default paths if not specified.

    Args:
        provisioning_dir: Directory with dashboard JSON files
        active_dir: Directory for valid dashboards
        failed_dir: Directory for invalid dashboards

    Returns:
        Configured DashboardHealthEndpoint
    """
    # Use environment variables or defaults
    if provisioning_dir is None:
        provisioning_dir = (
            Path(__file__).parent.parent.parent
            / "infrastructure"
            / "grafana"
            / "provisioning"
            / "dashboards"
        )

    if active_dir is None:
        active_dir = str(Path(provisioning_dir) / "active")

    if failed_dir is None:
        failed_dir = str(Path(provisioning_dir) / "failed")

    return DashboardHealthEndpoint(
        provisioning_dir=str(provisioning_dir),
        active_dir=str(active_dir),
        failed_dir=str(failed_dir),
    )


# Simulated HTTP endpoint handler for integration
def handle_health_request(
    provisioning_dir: str,
    active_dir: str | None = None,
    failed_dir: str | None = None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Handle a health check request.

    This function simulates an HTTP endpoint handler that can be
    integrated with Flask, FastAPI, or other web frameworks.

    Args:
        provisioning_dir: Directory with dashboard JSON files
        active_dir: Directory for valid dashboards
        failed_dir: Directory for invalid dashboards
        force_refresh: Force re-validation

    Returns:
        Dictionary with health status (suitable for JSON response)
    """
    endpoint = DashboardHealthEndpoint(
        provisioning_dir=provisioning_dir,
        active_dir=active_dir,
        failed_dir=failed_dir,
    )

    status = endpoint.check_health(force_refresh)

    # Add HTTP-like status code
    response = status.to_dict()
    response["status_code"] = 200 if status.validation_status == "all" else 503
    response["status_text"] = (
        "healthy" if status.validation_status == "all" else "degraded"
    )

    return response
