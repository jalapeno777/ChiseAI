"""Coverage improvement analyzer module.

Re-exports from tests.coverage.improvement.analyzer for backward compatibility.
"""

from tests.coverage.improvement.analyzer import (
    CoverageAnalyzer,
    CoverageGap,
    CoverageReport,
    ModuleCoverage,
    Priority,
    CRITICAL_MODULES,
)

__all__ = [
    "CoverageAnalyzer",
    "CoverageGap",
    "CoverageReport",
    "ModuleCoverage",
    "Priority",
    "CRITICAL_MODULES",
]
