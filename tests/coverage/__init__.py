"""Test coverage analysis and improvement package.

Provides tools for analyzing coverage gaps, generating coverage reports,
and identifying untested critical paths.
"""

from coverage.improvement.analyzer import (
    CoverageAnalyzer,
    CoverageGap,
    CoverageReport,
    ModuleCoverage,
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
    # Reporter
    "CoverageReporter",
    "CoverageThresholds",
    "ReportFormat",
]
