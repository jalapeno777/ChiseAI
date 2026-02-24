"""Coverage reporting with multiple output formats.

Provides reporting functionality for coverage analysis including
console, JSON, HTML, and Markdown formats.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from coverage.improvement.analyzer import CoverageReport

logger = logging.getLogger(__name__)


class ReportFormat(Enum):
    """Available report formats."""

    CONSOLE = "console"
    JSON = "json"
    MARKDOWN = "markdown"
    HTML = "html"


@dataclass
class CoverageThresholds:
    """Coverage thresholds for compliance.

    Attributes:
        minimum_coverage: Minimum overall coverage (%)
        critical_path_minimum: Minimum coverage for critical paths (%)
        fail_on_violation: Whether to fail on threshold violation
    """

    minimum_coverage: float = 80.0
    critical_path_minimum: float = 90.0
    fail_on_violation: bool = True

    @classmethod
    def default(cls) -> CoverageThresholds:
        """Get default thresholds."""
        return cls()

    @classmethod
    def strict(cls) -> CoverageThresholds:
        """Get strict thresholds."""
        return cls(
            minimum_coverage=85.0,
            critical_path_minimum=95.0,
        )

    @classmethod
    def ci(cls) -> CoverageThresholds:
        """Get CI thresholds."""
        return cls(
            minimum_coverage=80.0,
            critical_path_minimum=90.0,
            fail_on_violation=True,
        )


class CoverageReporter:
    """Reporter for coverage analysis results.

    Generates reports in multiple formats and checks compliance
    with coverage thresholds.

    Example:
        reporter = CoverageReporter()
        report = analyzer.analyze()
        reporter.generate(report, ReportFormat.MARKDOWN, "coverage.md")
        if reporter.check_compliance(report):
            print("Coverage compliant")
    """

    def __init__(
        self,
        thresholds: CoverageThresholds | None = None,
        output_dir: str = "reports/coverage",
    ):
        """Initialize coverage reporter.

        Args:
            thresholds: Coverage thresholds
            output_dir: Directory for output files
        """
        self.thresholds = thresholds or CoverageThresholds.default()
        self.output_dir = Path(output_dir)

    def generate(
        self,
        report: CoverageReport,
        format: ReportFormat,
        output_path: str | None = None,
    ) -> str:
        """Generate coverage report in specified format.

        Args:
            report: Coverage report to format
            format: Output format
            output_path: Optional output file path

        Returns:
            Report content as string
        """
        if format == ReportFormat.CONSOLE:
            content = self._format_console(report)
        elif format == ReportFormat.JSON:
            content = self._format_json(report)
        elif format == ReportFormat.MARKDOWN:
            content = self._format_markdown(report)
        elif format == ReportFormat.HTML:
            content = self._format_html(report)
        else:
            raise ValueError(f"Unknown format: {format}")

        if output_path:
            self._write_file(output_path, content)

        return content

    def _format_console(self, report: CoverageReport) -> str:
        """Format report for console output.

        Args:
            report: Coverage report

        Returns:
            Console-formatted string
        """
        lines = [
            "=" * 60,
            "COVERAGE REPORT",
            "=" * 60,
            f"Timestamp: {report.timestamp.isoformat()}",
            f"Overall Coverage: {report.overall_coverage:.2f}%",
            f"Total Gaps: {report.total_gaps}",
            f"Critical Gaps: {report.critical_gaps}",
            f"Compliant: {'Yes' if report.is_compliant(self.thresholds.minimum_coverage) else 'No'}",
            "",
            "MODULE COVERAGE",
            "-" * 60,
        ]

        # Sort modules by coverage (lowest first)
        sorted_modules = sorted(
            report.module_coverage,
            key=lambda m: m.coverage_percent,
        )

        for module in sorted_modules[:20]:  # Top 20 lowest
            status = (
                "🔴"
                if module.coverage_percent < 50
                else "🟡" if module.coverage_percent < 80 else "🟢"
            )
            critical = " [CRITICAL]" if module.critical_path else ""
            lines.append(
                f"{status} {module.coverage_percent:6.2f}% | {module.module_path}{critical}"
            )

        if report.recommendations:
            lines.extend(
                [
                    "",
                    "RECOMMENDATIONS",
                    "-" * 60,
                ]
            )
            for i, rec in enumerate(report.recommendations, 1):
                lines.append(f"{i}. {rec}")

        lines.append("=" * 60)

        return "\n".join(lines)

    def _format_json(self, report: CoverageReport) -> str:
        """Format report as JSON.

        Args:
            report: Coverage report

        Returns:
            JSON string
        """
        data = report.to_dict()
        data["thresholds"] = {
            "minimum_coverage": self.thresholds.minimum_coverage,
            "critical_path_minimum": self.thresholds.critical_path_minimum,
        }
        return json.dumps(data, indent=2)

    def _format_markdown(self, report: CoverageReport) -> str:
        """Format report as Markdown.

        Args:
            report: Coverage report

        Returns:
            Markdown string
        """
        lines = [
            "# Coverage Report",
            "",
            f"**Generated:** {report.timestamp.isoformat()}",
            "",
            "## Summary",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Overall Coverage | {report.overall_coverage:.2f}% |",
            f"| Total Gaps | {report.total_gaps} |",
            f"| Critical Gaps | {report.critical_gaps} |",
            f"| Compliant | {'✅ Yes' if report.is_compliant(self.thresholds.minimum_coverage) else '❌ No'} |",
            "",
            "## Module Coverage",
            "",
            "| Module | Coverage | Lines | Critical |",
            "|--------|----------|-------|----------|",
        ]

        # Sort by coverage (lowest first)
        sorted_modules = sorted(
            report.module_coverage,
            key=lambda m: m.coverage_percent,
        )

        for module in sorted_modules:
            status = (
                "🔴"
                if module.coverage_percent < 50
                else "🟡" if module.coverage_percent < 80 else "🟢"
            )
            critical = "Yes" if module.critical_path else "No"
            lines.append(
                f"| {module.module_path} | {status} {module.coverage_percent:.1f}% | "
                f"{module.covered_lines}/{module.total_lines} | {critical} |"
            )

        if report.recommendations:
            lines.extend(
                [
                    "",
                    "## Recommendations",
                    "",
                ]
            )
            for i, rec in enumerate(report.recommendations, 1):
                lines.append(f"{i}. {rec}")

        return "\n".join(lines)

    def _format_html(self, report: CoverageReport) -> str:
        """Format report as HTML.

        Args:
            report: Coverage report

        Returns:
            HTML string
        """
        coverage_color = (
            "#28a745"
            if report.overall_coverage >= 80
            else "#ffc107" if report.overall_coverage >= 50 else "#dc3545"
        )

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Coverage Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .summary {{ background: #f5f5f5; padding: 15px; border-radius: 5px; }}
        .coverage-bar {{ height: 20px; background: #e0e0e0; border-radius: 3px; }}
        .coverage-fill {{ height: 100%; border-radius: 3px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background: #f5f5f5; }}
        .critical {{ background: #fff3cd; }}
    </style>
</head>
<body>
    <h1>Coverage Report</h1>
    <p><strong>Generated:</strong> {report.timestamp.isoformat()}</p>

    <div class="summary">
        <h2>Summary</h2>
        <div class="coverage-bar">
            <div class="coverage-fill" style="width: {report.overall_coverage}%; background: {coverage_color};"></div>
        </div>
        <p><strong>Overall Coverage:</strong> {report.overall_coverage:.2f}%</p>
        <p><strong>Total Gaps:</strong> {report.total_gaps}</p>
        <p><strong>Critical Gaps:</strong> {report.critical_gaps}</p>
    </div>

    <h2>Module Coverage</h2>
    <table>
        <tr>
            <th>Module</th>
            <th>Coverage</th>
            <th>Lines</th>
            <th>Critical</th>
        </tr>
"""

        for module in sorted(report.module_coverage, key=lambda m: m.coverage_percent):
            row_class = "critical" if module.critical_path else ""
            html += f"""
        <tr class="{row_class}">
            <td>{module.module_path}</td>
            <td>{module.coverage_percent:.1f}%</td>
            <td>{module.covered_lines}/{module.total_lines}</td>
            <td>{"Yes" if module.critical_path else "No"}</td>
        </tr>
"""

        html += """
    </table>
</body>
</html>
"""
        return html

    def _write_file(self, path: str, content: str) -> None:
        """Write content to file.

        Args:
            path: File path
            content: File content
        """
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(file_path, "w") as f:
            f.write(content)

        logger.info(f"Wrote report to {path}")

    def check_compliance(self, report: CoverageReport) -> bool:
        """Check if coverage meets thresholds.

        Args:
            report: Coverage report

        Returns:
            True if compliant
        """
        # Check overall coverage
        if report.overall_coverage < self.thresholds.minimum_coverage:
            logger.warning(
                f"Overall coverage {report.overall_coverage:.1f}% below "
                f"minimum {self.thresholds.minimum_coverage}%"
            )
            return False

        # Check critical path coverage
        for module in report.module_coverage:
            if (
                module.critical_path
                and module.coverage_percent < self.thresholds.critical_path_minimum
            ):
                logger.warning(
                    f"Critical module {module.module_path} has coverage "
                    f"{module.coverage_percent:.1f}% below minimum "
                    f"{self.thresholds.critical_path_minimum}%"
                )
                if self.thresholds.fail_on_violation:
                    return False

        return True

    def get_summary_for_ci(self, report: CoverageReport) -> dict[str, Any]:
        """Get summary suitable for CI output.

        Args:
            report: Coverage report

        Returns:
            CI-friendly summary
        """
        return {
            "coverage": round(report.overall_coverage, 2),
            "threshold": self.thresholds.minimum_coverage,
            "compliant": self.check_compliance(report),
            "gaps": report.total_gaps,
            "critical_gaps": report.critical_gaps,
            "modules_analyzed": len(report.module_coverage),
        }
