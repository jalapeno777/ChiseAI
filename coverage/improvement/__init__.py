"""Coverage improvement package.

Re-exports from tests.coverage.improvement for backward compatibility.
"""

# Import submodules to make them accessible
from coverage.improvement import analyzer
from coverage.improvement import reporter

# Re-export main classes for convenience
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
    # Submodules
    "analyzer",
    "reporter",
    # Analyzer exports
    "CoverageAnalyzer",
    "CoverageGap",
    "CoverageReport",
    "ModuleCoverage",
    "Priority",
    "CRITICAL_MODULES",
    # Reporter exports
    "CoverageReporter",
    "CoverageThresholds",
    "ReportFormat",
]
