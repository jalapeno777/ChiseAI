"""Coverage analysis for identifying gaps and generating reports.

Provides comprehensive coverage analysis including:
- Module-level coverage tracking
- Gap identification
- Critical path coverage
- Trend analysis
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class Priority(Enum):
    """Priority levels for coverage gaps."""

    CRITICAL = "critical"  # Core business logic
    HIGH = "high"  # Important functionality
    MEDIUM = "medium"  # Standard functionality
    LOW = "low"  # Utility functions


@dataclass
class CoverageGap:
    """Represents a gap in test coverage.

    Attributes:
        file_path: Path to file with gap
        line_start: Start line of gap
        line_end: End line of gap
        function_name: Function with gap
        priority: Priority level
        description: Description of what's not covered
    """

    file_path: str
    line_start: int
    line_end: int
    function_name: str | None = None
    priority: Priority = Priority.MEDIUM
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "file_path": self.file_path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "function_name": self.function_name,
            "priority": self.priority.value,
            "description": self.description,
        }


@dataclass
class ModuleCoverage:
    """Coverage statistics for a module.

    Attributes:
        module_path: Path to module
        total_lines: Total executable lines
        covered_lines: Lines covered by tests
        coverage_percent: Coverage percentage
        gaps: List of coverage gaps
        critical_path: Whether module is on critical path
    """

    module_path: str
    total_lines: int
    covered_lines: int
    coverage_percent: float
    gaps: list[CoverageGap] = field(default_factory=list)
    critical_path: bool = False

    @property
    def uncovered_lines(self) -> int:
        """Get number of uncovered lines."""
        return self.total_lines - self.covered_lines

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "module_path": self.module_path,
            "total_lines": self.total_lines,
            "covered_lines": self.covered_lines,
            "uncovered_lines": self.uncovered_lines,
            "coverage_percent": round(self.coverage_percent, 2),
            "critical_path": self.critical_path,
            "gap_count": len(self.gaps),
        }


@dataclass
class CoverageReport:
    """Complete coverage report.

    Attributes:
        timestamp: Report generation timestamp
        overall_coverage: Overall coverage percentage
        module_coverage: Coverage by module
        total_gaps: Total coverage gaps
        critical_gaps: Gaps in critical paths
        recommendations: Improvement recommendations
    """

    timestamp: datetime
    overall_coverage: float
    module_coverage: list[ModuleCoverage] = field(default_factory=list)
    total_gaps: int = 0
    critical_gaps: int = 0
    recommendations: list[str] = field(default_factory=list)

    @property
    def is_compliant(self, threshold: float = 80.0) -> bool:
        """Check if coverage meets threshold.

        Args:
            threshold: Minimum coverage threshold

        Returns:
            True if coverage meets threshold
        """
        return self.overall_coverage >= threshold

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "overall_coverage": round(self.overall_coverage, 2),
            "total_gaps": self.total_gaps,
            "critical_gaps": self.critical_gaps,
            "is_compliant": self.is_compliant(),
            "modules": [m.to_dict() for m in self.module_coverage],
            "recommendations": self.recommendations,
        }


# Critical path modules that require high coverage
CRITICAL_MODULES = [
    "src/execution/",
    "src/ml/",
    "src/strategy/",
    "src/risk/",
    "src/portfolio/",
]


class CoverageAnalyzer:
    """Analyzer for test coverage.

    Analyzes coverage data to identify gaps, track trends,
    and generate comprehensive reports.

    Example:
        analyzer = CoverageAnalyzer("src/")
        report = analyzer.analyze()
        print(f"Overall coverage: {report.overall_coverage}%")
        for gap in analyzer.get_critical_gaps():
            print(f"Critical gap: {gap.file_path}")
    """

    def __init__(
        self,
        source_path: str = "src/",
        critical_modules: list[str] | None = None,
    ):
        """Initialize coverage analyzer.

        Args:
            source_path: Path to source code
            critical_modules: List of critical module prefixes
        """
        self.source_path = Path(source_path)
        self.critical_modules = critical_modules or CRITICAL_MODULES

    def run_coverage(self) -> dict[str, Any]:
        """Run pytest with coverage.

        Returns:
            Raw coverage data
        """
        try:
            result = subprocess.run(
                [
                    "python",
                    "-m",
                    "pytest",
                    "--cov=src/",
                    "--cov-report=json",
                    "--cov-report=term-missing",
                    "-q",
                ],
                capture_output=True,
                text=True,
                cwd="/home/tacopants/projects/ChiseAI",
            )

            # Load coverage.json
            coverage_file = Path("coverage.json")
            if coverage_file.exists():
                with open(coverage_file) as f:
                    return json.load(f)

        except Exception as e:
            logger.warning(f"Failed to run coverage: {e}")

        return {"files": {}}

    def analyze(self) -> CoverageReport:
        """Analyze coverage and generate report.

        Returns:
            CoverageReport with analysis results
        """
        # Run coverage
        coverage_data = self.run_coverage()

        # Parse coverage data
        modules: list[ModuleCoverage] = []
        total_lines = 0
        total_covered = 0
        total_gaps = 0
        critical_gaps = 0

        for file_path, file_data in coverage_data.get("files", {}).items():
            summary = file_data.get("summary", {})

            total = summary.get("num_statements", 0)
            covered = summary.get("covered_lines", 0)
            percent = summary.get("percent_covered", 0.0)

            # Check if critical
            is_critical = any(file_path.startswith(cm) for cm in self.critical_modules)

            # Identify gaps
            gaps = self._identify_gaps(file_path, file_data, is_critical)

            module = ModuleCoverage(
                module_path=file_path,
                total_lines=total,
                covered_lines=covered,
                coverage_percent=percent,
                gaps=gaps,
                critical_path=is_critical,
            )

            modules.append(module)
            total_lines += total
            total_covered += covered
            total_gaps += len(gaps)

            if is_critical:
                critical_gaps += len(gaps)

        # Calculate overall coverage
        overall = (total_covered / total_lines * 100) if total_lines > 0 else 0.0

        # Generate recommendations
        recommendations = self._generate_recommendations(modules, overall)

        return CoverageReport(
            timestamp=datetime.now(UTC),
            overall_coverage=overall,
            module_coverage=modules,
            total_gaps=total_gaps,
            critical_gaps=critical_gaps,
            recommendations=recommendations,
        )

    def _identify_gaps(
        self,
        file_path: str,
        file_data: dict[str, Any],
        is_critical: bool,
    ) -> list[CoverageGap]:
        """Identify coverage gaps in a file.

        Args:
            file_path: Path to file
            file_data: Coverage data for file
            is_critical: Whether file is on critical path

        Returns:
            List of CoverageGap
        """
        gaps: list[CoverageGap] = []

        executed_lines = set(file_data.get("executed_lines", []))
        missing_lines = file_data.get("missing_lines", [])

        # Group consecutive missing lines
        if missing_lines:
            missing_lines = sorted(missing_lines)

            # Simple gap detection
            for line in missing_lines:
                priority = Priority.CRITICAL if is_critical else Priority.MEDIUM

                gaps.append(
                    CoverageGap(
                        file_path=file_path,
                        line_start=line,
                        line_end=line,
                        priority=priority,
                        description=f"Line {line} not covered",
                    )
                )

        return gaps

    def _generate_recommendations(
        self,
        modules: list[ModuleCoverage],
        overall: float,
    ) -> list[str]:
        """Generate coverage improvement recommendations.

        Args:
            modules: Module coverage data
            overall: Overall coverage percentage

        Returns:
            List of recommendations
        """
        recommendations = []

        # Overall coverage recommendation
        if overall < 80:
            recommendations.append(
                f"Overall coverage ({overall:.1f}%) is below 80% threshold. "
                "Prioritize adding tests for uncovered modules."
            )
        elif overall < 90:
            recommendations.append(
                f"Coverage at {overall:.1f}%. Focus on critical path modules "
                "to reach 90% target."
            )

        # Critical module recommendations
        critical_low = [
            m for m in modules if m.critical_path and m.coverage_percent < 90
        ]

        if critical_low:
            recommendations.append(
                f"{len(critical_low)} critical modules have coverage below 90%. "
                "These should be prioritized."
            )

        # Specific module recommendations
        for module in sorted(modules, key=lambda x: x.coverage_percent)[:5]:
            if module.coverage_percent < 50:
                recommendations.append(
                    f"Module '{module.module_path}' has only "
                    f"{module.coverage_percent:.1f}% coverage. "
                    "Consider adding comprehensive tests."
                )

        return recommendations

    def get_critical_gaps(self) -> list[CoverageGap]:
        """Get all gaps in critical path modules.

        Returns:
            List of critical CoverageGap
        """
        report = self.analyze()
        critical_gaps: list[CoverageGap] = []

        for module in report.module_coverage:
            if module.critical_path:
                critical_gaps.extend(module.gaps)

        # Sort by priority
        priority_order = {
            Priority.CRITICAL: 0,
            Priority.HIGH: 1,
            Priority.MEDIUM: 2,
            Priority.LOW: 3,
        }
        critical_gaps.sort(key=lambda g: priority_order.get(g.priority, 3))

        return critical_gaps

    def get_modules_below_threshold(
        self,
        threshold: float = 80.0,
    ) -> list[ModuleCoverage]:
        """Get modules below coverage threshold.

        Args:
            threshold: Minimum coverage threshold

        Returns:
            List of modules below threshold
        """
        report = self.analyze()
        return [m for m in report.module_coverage if m.coverage_percent < threshold]

    def get_coverage_trend(self, days: int = 7) -> dict[str, Any]:
        """Get coverage trend over time.

        Args:
            days: Number of days to analyze

        Returns:
            Trend data
        """
        # This would integrate with historical coverage data
        # For now, return current snapshot
        report = self.analyze()

        return {
            "current_coverage": report.overall_coverage,
            "trend": "stable",
            "days_analyzed": days,
        }
