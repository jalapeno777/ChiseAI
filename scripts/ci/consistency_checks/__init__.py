"""Consistency checks for local CI validation.

This package provides tools to validate that the local development environment
matches the CI configuration, detecting drift early to prevent "works on my machine" issues.
"""

from scripts.ci.consistency_checks.config_comparator import (
    ConfigComparison,
    ConfigDrift,
    compare_configurations,
    extract_ci_config_from_yaml,
    format_config_report,
    parse_pyproject_toml,
)
from scripts.ci.consistency_checks.drift_reporter import (
    DriftEntry,
    DriftReport,
    build_report,
    format_remediation,
    write_report,
)
from scripts.ci.consistency_checks.version_checker import (
    ToolVersion,
    check_tool_versions,
    detect_version_drift,
    format_version_report,
    get_ci_tool_version,
    get_local_tool_version,
)

__all__ = [
    # Version checker
    "check_tool_versions",
    "detect_version_drift",
    "get_local_tool_version",
    "get_ci_tool_version",
    "format_version_report",
    "ToolVersion",
    # Config comparator
    "compare_configurations",
    "parse_pyproject_toml",
    "extract_ci_config_from_yaml",
    "format_config_report",
    "ConfigDrift",
    "ConfigComparison",
    # Drift reporter
    "build_report",
    "write_report",
    "format_remediation",
    "DriftReport",
    "DriftEntry",
]
