"""Test coverage analysis and improvement package.

Provides tools for analyzing coverage gaps, generating coverage reports,
and identifying untested critical paths.
"""

# Use relative imports to avoid circular dependency with root coverage package
from .improvement.analyzer import (
    CRITICAL_MODULES,
    CoverageAnalyzer,
    CoverageGap,
    CoverageReport,
    ModuleCoverage,
    Priority,
)
from .improvement.reporter import (
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
