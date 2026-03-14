"""Coverage analysis and improvement package.

This package provides standalone coverage analysis tools.
"""

from coverage.improvement.analyzer import (
    CoverageAnalyzer,
    CoverageGap,
    CoverageReport,
    ModuleCoverage,
    Priority,
    CRITICAL_MODULES,
)
from coverage.improvement.reporter import (
    CoverageReporter,
    CoverageThresholds,
    ReportFormat,
)

__all__ = [
    # Analyzer
    "CoverageAnalyzer",
    "CoverageGap",
    "CoverageReport",
    "ModuleCoverage",
    "Priority",
    "CRITICAL_MODULES",
    # Reporter
    "CoverageReporter",
    "CoverageThresholds",
    "ReportFormat",
]
