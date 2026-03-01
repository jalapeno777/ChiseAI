"""
Issue ingestion and parsing system for brain evaluation.

# SAFETY: No risk cap logic modified
# SAFETY: No promotion gate logic modified
# SAFETY: No live trading flow modified
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class IssueCategory(Enum):
    """Categories of issues that can be detected."""

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
    """
    Represents a detected issue from various sources.

    # SAFETY: No risk cap logic modified
    # SAFETY: No promotion gate logic modified
    # SAFETY: No live trading flow modified
    """

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
        """Generate fingerprint after initialization."""
        self.fingerprint = self._generate_fingerprint()

    def _generate_fingerprint(self) -> str:
        """
        Generate a unique fingerprint for deduplication.

        Pattern: hash(category + normalized_description)
        """
        normalized_desc = self._normalize_description(self.description)
        fingerprint_input = f"{self.category.value}:{normalized_desc}"
        return hashlib.sha256(fingerprint_input.encode()).hexdigest()[:16]

    @staticmethod
    def _normalize_description(description: str) -> str:
        """
        Normalize description for consistent fingerprinting.

        - Lowercase
        - Remove timestamps (before numbers to preserve pattern)
        - Remove specific paths/numbers
        """
        import re

        normalized = description.lower()
        # Remove file paths
        normalized = re.sub(r"/[\w/.-]+", "<PATH>", normalized)
        # Remove timestamps BEFORE numbers (timestamps contain numbers)
        # Note: lowercase "t" because we already lowercased the string
        normalized = re.sub(
            r"\d{4}-\d{2}-\d{2}[t ]\d{2}:\d{2}:\d{2}", "<TIMESTAMP>", normalized
        )
        # Remove numbers (line numbers, ports, etc.)
        normalized = re.sub(r"\b\d+\b", "<NUM>", normalized)
        # Collapse whitespace
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized


__all__ = ["Issue", "IssueCategory", "IssueSource"]
