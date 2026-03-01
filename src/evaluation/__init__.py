"""Evaluation package.

# SAFETY: No risk cap logic modified
# SAFETY: No promotion gate logic modified
# SAFETY: No live trading flow modified

Provides evaluation tools including Mini BrainEval for lightweight
evaluation runs at various cadences, and repeated issue detection.
"""

from evaluation.fingerprinting import (
    FingerprintCluster,
    FingerprintClusterer,
    IssueFingerprint,
)
from evaluation.mini_brain_eval import MiniBrainEval
from evaluation.repeated_issue_detector import (
    IssueCluster,
    RepeatedIssueDetector,
    RepeatedIssueReport,
    TrendAnalysis,
)
from evaluation.schemas.mini_eval import (
    Issue,
    IssueCategory,
    IssueSeverity,
    MiniEvalResult,
    Mitigation,
    MitigationResult,
)

__all__ = [
    # Mini BrainEval
    "MiniBrainEval",
    # Repeated Issue Detection
    "RepeatedIssueDetector",
    "RepeatedIssueReport",
    "IssueCluster",
    "TrendAnalysis",
    # Fingerprinting
    "IssueFingerprint",
    "FingerprintClusterer",
    "FingerprintCluster",
    # Schemas
    "MiniEvalResult",
    "Issue",
    "IssueCategory",
    "IssueSeverity",
    "Mitigation",
    "MitigationResult",
]
