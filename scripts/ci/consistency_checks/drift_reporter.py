"""Drift reporter for local CI consistency validation.

Generates comprehensive drift reports combining version and configuration drift.
"""

import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


@dataclass
class DriftEntry:
    """Single drift entry."""

    category: str
    drift_type: str  # "version" or "config"
    item: str
    local_value: Any
    ci_value: Any
    severity: str
    description: str


@dataclass
class DriftReport:
    """Comprehensive drift report."""

    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    version_drifts: list[DriftEntry] = field(default_factory=list)
    config_drifts: list[DriftEntry] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)
    passed: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Convert report to dictionary."""
        return {
            "timestamp": self.timestamp,
            "version_drifts": [asdict(d) for d in self.version_drifts],
            "config_drifts": [asdict(d) for d in self.config_drifts],
            "summary": self.summary,
            "passed": self.passed,
        }

    def to_json(self, indent: int = 2) -> str:
        """Format report as JSON."""
        return json.dumps(self.to_dict(), indent=indent)

    def to_text(self) -> str:
        """Format report as human-readable text."""
        lines = [
            "=" * 70,
            "LOCAL CI CONSISTENCY DRIFT REPORT",
            "=" * 70,
            f"Generated: {self.timestamp}",
            "",
        ]

        total_drifts = len(self.version_drifts) + len(self.config_drifts)

        if total_drifts == 0:
            lines.extend(
                [
                    "✓ NO DRIFT DETECTED",
                    "",
                    "Local environment is consistent with CI configuration.",
                    "",
                ]
            )
        else:
            lines.extend(
                [
                    f"✗ DRIFT DETECTED: {total_drifts} issue(s)",
                    "",
                ]
            )

            # Summary by severity
            if self.summary:
                lines.append("SUMMARY:")
                for severity in ["high", "medium", "low"]:
                    count = self.summary.get(severity, 0)
                    if count > 0:
                        symbol = (
                            "✗"
                            if severity == "high"
                            else "⚠" if severity == "medium" else "○"
                        )
                        lines.append(f"  {symbol} {severity.upper()}: {count}")
                lines.append("")

            # Version drifts
            if self.version_drifts:
                lines.append("-" * 70)
                lines.append("VERSION DRIFTS:")
                lines.append("-" * 70)
                for drift in self.version_drifts:
                    lines.append(
                        f"  [{drift.severity.upper()}] {drift.category}: {drift.item}"
                    )
                    lines.append(f"    Local: {drift.local_value}")
                    lines.append(f"    CI:    {drift.ci_value}")
                    if drift.description:
                        lines.append(f"    Note:  {drift.description}")
                    lines.append("")

            # Config drifts
            if self.config_drifts:
                lines.append("-" * 70)
                lines.append("CONFIGURATION DRIFTS:")
                lines.append("-" * 70)
                for drift in self.config_drifts:
                    lines.append(
                        f"  [{drift.severity.upper()}] {drift.category}.{drift.item}"
                    )
                    lines.append(f"    Local: {drift.local_value}")
                    lines.append(f"    CI:    {drift.ci_value}")
                    if drift.description:
                        lines.append(f"    Note:  {drift.description}")
                    lines.append("")

        lines.extend(
            [
                "=" * 70,
                f"STATUS: {'PASS' if self.passed else 'FAIL'}",
                "=" * 70,
            ]
        )

        return "\n".join(lines)


def create_drift_entry(
    category: str,
    drift_type: str,
    item: str,
    local_value: Any,
    ci_value: Any,
    severity: str,
    description: str = "",
) -> DriftEntry:
    """Create a drift entry with defaults."""
    return DriftEntry(
        category=category,
        drift_type=drift_type,
        item=item,
        local_value=str(local_value) if local_value is not None else "NOT INSTALLED",
        ci_value=str(ci_value) if ci_value is not None else "UNKNOWN",
        severity=severity,
        description=description,
    )


def build_report(
    version_drifts: list[Any],
    config_drifts: list[Any],
) -> DriftReport:
    """Build a comprehensive drift report.

    Args:
        version_drifts: List of ToolVersion objects with drift
        config_drifts: List of ConfigDrift objects

    Returns:
        DriftReport with all drift information
    """
    report = DriftReport()

    # Process version drifts
    for vdrift in version_drifts:
        entry = create_drift_entry(
            category="tool",
            drift_type="version",
            item=vdrift.name,
            local_value=vdrift.local_version,
            ci_value=vdrift.ci_version,
            severity="high" if vdrift.name == "python" else "medium",
            description=f"Version mismatch in {vdrift.ci_docker_image}",
        )
        report.version_drifts.append(entry)

    # Process config drifts
    severity_map = {"high": "high", "medium": "medium", "low": "low"}
    for cdrift in config_drifts:
        entry = create_drift_entry(
            category=cdrift.category,
            drift_type="config",
            item=cdrift.setting,
            local_value=cdrift.local_value,
            ci_value=cdrift.ci_value,
            severity=severity_map.get(cdrift.severity, "medium"),
            description="Configuration value differs from CI",
        )
        report.config_drifts.append(entry)

    # Calculate summary
    all_drifts = report.version_drifts + report.config_drifts
    report.summary = {
        "total": len(all_drifts),
        "high": len([d for d in all_drifts if d.severity == "high"]),
        "medium": len([d for d in all_drifts if d.severity == "medium"]),
        "low": len([d for d in all_drifts if d.severity == "low"]),
    }

    # Passed only if no high severity drifts
    report.passed = report.summary["high"] == 0

    return report


def write_report(
    report: DriftReport, output_path: str | None = None, format: str = "text"
) -> str:
    """Write drift report to file or stdout.

    Args:
        report: The DriftReport to write
        output_path: Optional file path to write to
        format: "text" or "json"

    Returns:
        The formatted report string
    """
    if format == "json":
        content = report.to_json()
    else:
        content = report.to_text()

    if output_path:
        Path(output_path).write_text(content)
    else:
        print(content)

    return content


def remediation_steps(report: DriftReport) -> list[str]:
    """Generate remediation steps based on detected drifts."""
    steps = []

    for drift in report.version_drifts:
        if drift.item == "python":
            steps.append(
                f"Python version drift: Install Python {drift.ci_value} to match CI"
            )
        elif drift.item in ("black", "ruff", "mypy", "bandit", "pytest"):
            steps.append(
                f"{drift.item} version drift: Run `pip install --upgrade {drift.item}` to match CI version"
            )

    for drift in report.config_drifts:
        if drift.category == "black" and drift.item == "line-length":
            steps.append(
                "Black line-length: Update pyproject.toml to use line-length=88"
            )
        elif drift.category == "ruff":
            if "select" in drift.item:
                steps.append(
                    "Ruff lint rules: Sync select list with CI configuration in pyproject.toml"
                )
            elif drift.item == "line-length":
                steps.append(
                    "Ruff line-length: Update pyproject.toml to use line-length=88"
                )
        elif drift.category == "mypy" and drift.item == "python_version":
            steps.append(
                "Mypy python_version: Update to python_version = '3.11' in pyproject.toml"
            )

    return steps


def format_remediation(report: DriftReport) -> str:
    """Format remediation steps as text."""
    steps = remediation_steps(report)

    if not steps:
        return ""

    lines = [
        "",
        "=" * 70,
        "REMEDIATION STEPS",
        "=" * 70,
        "",
    ]

    for i, step in enumerate(steps, 1):
        lines.append(f"  {i}. {step}")

    lines.extend(
        [
            "",
            "After applying fixes, re-run:",
            "  python scripts/validate_local_ci_consistency.py",
            "",
        ]
    )

    return "\n".join(lines)


if __name__ == "__main__":
    # Demo/test with sample data
    from scripts.ci.consistency_checks.config_comparator import compare_configurations
    from scripts.ci.consistency_checks.version_checker import (
        check_tool_versions,
        detect_version_drift,
    )

    version_results = check_tool_versions()
    version_drifts = detect_version_drift(version_results)
    config_comparison = compare_configurations()

    report = build_report(version_drifts, config_comparison.drifts)

    print(report.to_text())
    print(format_remediation(report))

    sys.exit(0 if report.passed else 1)
