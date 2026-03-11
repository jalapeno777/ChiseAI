"""Coverage analysis and improvement package.

This package re-exports from tests.coverage for backward compatibility.
"""

# Re-export from tests.coverage
from tests.coverage.improvement.analyzer import (
    CoverageAnalyzer,
    CoverageGap,
    CoverageReport,
    ModuleCoverage,
    Priority,
    CRITICAL_MODULES,
)
from tests.coverage.improvement.reporter import (
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
