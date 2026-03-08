"""Evaluation package.

# SAFETY: No risk cap logic modified
# SAFETY: No promotion gate logic modified
# SAFETY: No live trading flow modified

Combines issue ingestion primitives with mini BrainEval/repeated-issue tooling.
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class IssueCategory(Enum):
    """Categories of issues that can be detected for ingestion."""

    FILE_ACCESS = "file_access"
    DB_CONNECTIVITY = "db_connectivity"
    ENV_SLOWDOWN = "env_slowdown"
    TOOL_ERROR = "tool_error"
    OTHER = "other"


class IssueSource(Enum):
    """Sources where issues can be detected."""

    ITERLOG = "iterlog"
    CI_LOG = "ci_log"
    WORKER_REPORT = "worker_report"
    REDIS = "redis"


@dataclass
class Issue:
    """Issue model used by ingestion/parsing paths."""

    category: IssueCategory
    description: str
    source: IssueSource
    timestamp: datetime
    raw_text: str
    story_id: str | None = None
    file_path: str | None = None
    line_number: int | None = None
    fingerprint: str = field(default="", init=False)
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        self.fingerprint = self._generate_fingerprint()

    def _generate_fingerprint(self) -> str:
        normalized_desc = self._normalize_description(self.description)
        fingerprint_input = f"{self.category.value}:{normalized_desc}"
        return hashlib.sha256(fingerprint_input.encode()).hexdigest()[:16]

    @staticmethod
    def _normalize_description(description: str) -> str:
        import re

        normalized = description.lower()
        normalized = re.sub(r"/[\w/.-]+", "<PATH>", normalized)
        normalized = re.sub(
            r"\d{4}-\d{2}-\d{2}[t ]\d{2}:\d{2}:\d{2}", "<TIMESTAMP>", normalized
        )
        normalized = re.sub(r"\b\d+\b", "<NUM>", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized


from .fingerprinting import FingerprintCluster, FingerprintClusterer, IssueFingerprint
from .kpi_persistence import KPIPersistence, KPIPersistenceError, KPISnapshot
from .mini_brain_eval import MiniBrainEval
from .repeated_issue_detector import (
    IssueCluster,
    RepeatedIssueDetector,
    RepeatedIssueReport,
    TrendAnalysis,
)
from .schemas.mini_eval import (
    Issue as MiniEvalIssue,
)
from .schemas.mini_eval import (
    IssueCategory as MiniEvalIssueCategory,
)
from .schemas.mini_eval import (
    IssueSeverity,
    MiniEvalResult,
    Mitigation,
    MitigationResult,
)
from .trend_rollups import (
    TrendRollup,
    TrendRollupEngine,
    calculate_kpis,
    get_redis_client,
)

__all__ = [
    "Issue",
    "IssueCategory",
    "IssueSource",
    "MiniBrainEval",
    "RepeatedIssueDetector",
    "RepeatedIssueReport",
    "IssueCluster",
    "TrendAnalysis",
    "IssueFingerprint",
    "FingerprintClusterer",
    "FingerprintCluster",
    "TrendRollup",
    "TrendRollupEngine",
    "calculate_kpis",
    "get_redis_client",
    "MiniEvalResult",
    "MiniEvalIssue",
    "MiniEvalIssueCategory",
    "IssueSeverity",
    "Mitigation",
    "MitigationResult",
    "KPIPersistence",
    "KPIPersistenceError",
    "KPISnapshot",
]
