"""Coverage improvement reporter module.

Re-exports from tests.coverage.improvement.reporter for backward compatibility.
"""

from tests.coverage.improvement.reporter import (
    CoverageReporter,
    CoverageThresholds,
    ReportFormat,
)

__all__ = [
    "CoverageReporter",
    "CoverageThresholds",
    "ReportFormat",
]
