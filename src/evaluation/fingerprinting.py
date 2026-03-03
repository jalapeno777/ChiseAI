"""Issue fingerprinting module for repeated issue detection.

# SAFETY: No risk cap logic modified
# SAFETY: No promotion gate logic modified
# SAFETY: No live trading flow modified

Provides fingerprinting capabilities to normalize and cluster issues
for detecting repeated problems across evaluation runs.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evaluation.schemas.mini_eval import Issue


class IssueFingerprint:
    """Generates and manages fingerprints for issues.

        Fingerprints are used to identify repeated issues by normalizing
    their descriptions and creating consistent hash-based identifiers.

        Example:
            >>> from evaluation.schemas.mini_eval import Issue, IssueCategory, IssueSeverity
            >>> issue = Issue.create(
            ...     category=IssueCategory.DB_CONNECTIVITY,
            ...     severity=IssueSeverity.P1,
            ...     description="Redis connection timeout at 2026-03-01T12:00:00Z",
            ...     source="test"
            ... )
            >>> fingerprint = IssueFingerprint.generate(issue)
            >>> print(fingerprint)
            'db_connectivity:a1b2c3d4...'
    """

    # Regex patterns for normalization
    TIMESTAMP_PATTERN = re.compile(
        r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?"
    )
    UUID_PATTERN = re.compile(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
    )
    GUID_PATTERN = re.compile(
        r"\{?[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\}?"
    )
    FILE_PATH_PATTERN = re.compile(r"(?:/[^/\s]+)+|(?:[a-zA-Z]:\\[^\\\s]+)+")
    LINE_NUMBER_PATTERN = re.compile(r":\d+")
    PID_PATTERN = re.compile(r"\b(?:pid|PID)\s*[=:]?\s*\d+\b")
    MEMORY_ADDRESS_PATTERN = re.compile(r"0x[0-9a-fA-F]+")
    HEX_NUMBER_PATTERN = re.compile(r"\b0x[0-9a-fA-F]+\b")
    IP_ADDRESS_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b|\[[0-9a-fA-F:]+\]")
    PORT_NUMBER_PATTERN = re.compile(r":\d{2,5}\b")
    SESSION_ID_PATTERN = re.compile(r"\b(?:session|sess)_?[0-9a-fA-F]{8,}\b")
    REQUEST_ID_PATTERN = re.compile(r"\b(?:req|request)_?[0-9a-fA-F]{8,}\b")

    @classmethod
    def generate(cls, issue: Issue) -> str:
        """Generate a fingerprint for an issue.

        Creates a hash-based fingerprint from the issue category and
        normalized description. This allows detection of the same
        underlying issue even with different variable parts.

        Args:
            issue: The Issue to fingerprint

        Returns:
            A string fingerprint in the format "category:hash"
        """
        normalized_desc = cls.normalize_description(issue.description)
        fingerprint_data = f"{issue.category}:{normalized_desc}"
        hash_value = hashlib.sha256(fingerprint_data.encode()).hexdigest()[:16]
        return f"{issue.category}:{hash_value}"

    @classmethod
    def normalize_description(cls, description: str) -> str:
        """Normalize an issue description by removing variable parts.

        Removes timestamps, UUIDs, file paths, line numbers, PIDs,
        memory addresses, and other variable content that would
        prevent matching of similar issues.

        Args:
            description: The original issue description

        Returns:
            Normalized description with variable parts replaced
        """
        if not description:
            return ""

        normalized = description

        # Replace timestamps with placeholder
        normalized = cls.TIMESTAMP_PATTERN.sub("<TIMESTAMP>", normalized)

        # Replace UUIDs with placeholder
        normalized = cls.UUID_PATTERN.sub("<UUID>", normalized)
        normalized = cls.GUID_PATTERN.sub("<UUID>", normalized)

        # Replace file paths, keeping only filename
        def replace_path(match: re.Match) -> str:
            """Replace file path with filename only.

            Args:
                match: Regex match object containing the file path

            Returns:
                Filename extracted from the path, or "<PATH>" placeholder
            """
            path = match.group()
            # Extract just the filename
            filename = path.split("/")[-1].split("\\")[-1]
            return filename if filename else "<PATH>"

        normalized = cls.FILE_PATH_PATTERN.sub(replace_path, normalized)

        # Replace line numbers with placeholder
        normalized = cls.LINE_NUMBER_PATTERN.sub(":<LINE>", normalized)

        # Replace PIDs with placeholder
        normalized = cls.PID_PATTERN.sub("<PID>", normalized)

        # Replace memory addresses with placeholder
        normalized = cls.MEMORY_ADDRESS_PATTERN.sub("<ADDR>", normalized)

        # Replace IP addresses with placeholder
        normalized = cls.IP_ADDRESS_PATTERN.sub("<IP>", normalized)

        # Replace port numbers (but not in URLs that already have <IP>)
        # Use a simpler approach - just replace standalone port patterns
        normalized = cls.PORT_NUMBER_PATTERN.sub(":<PORT>", normalized)

        # Replace session IDs with placeholder
        normalized = cls.SESSION_ID_PATTERN.sub("<SESSION>", normalized)

        # Replace request IDs with placeholder
        normalized = cls.REQUEST_ID_PATTERN.sub("<REQUEST>", normalized)

        # Replace standalone hex numbers (not part of words)
        normalized = cls.HEX_NUMBER_PATTERN.sub("<HEX>", normalized)

        # Normalize whitespace
        normalized = " ".join(normalized.split())

        return normalized.lower().strip()

    @classmethod
    def cluster(cls, fingerprints: list[str]) -> dict[str, list[str]]:
        """Cluster fingerprints by similarity.

        Groups identical fingerprints together, returning a mapping
        from unique fingerprint to all occurrences.

        Args:
            fingerprints: List of fingerprint strings

        Returns:
            Dictionary mapping unique fingerprint to list of occurrences
        """
        clusters: dict[str, list[str]] = {}

        for fingerprint in fingerprints:
            if fingerprint not in clusters:
                clusters[fingerprint] = []
            clusters[fingerprint].append(fingerprint)

        return clusters

    @classmethod
    def are_similar(cls, fingerprint1: str, fingerprint2: str) -> bool:
        """Check if two fingerprints represent similar issues.

                Compares fingerprints to determine if they likely represent
        the same underlying issue type.

                Args:
                    fingerprint1: First fingerprint to compare
                    fingerprint2: Second fingerprint to compare

                Returns:
                    True if fingerprints are similar, False otherwise
        """
        # For now, exact match is sufficient
        # Future enhancement: fuzzy matching based on description similarity
        return fingerprint1 == fingerprint2

    @classmethod
    def extract_category(cls, fingerprint: str) -> str:
        """Extract the category from a fingerprint.

        Args:
            fingerprint: Fingerprint string in format "category:hash"

        Returns:
            The category portion of the fingerprint
        """
        return fingerprint.split(":")[0] if ":" in fingerprint else "unknown"


@dataclass
class FingerprintCluster:
    """Represents a cluster of similar fingerprints.

    Attributes:
        fingerprint: The representative fingerprint for this cluster
        category: Issue category
        count: Number of occurrences
        descriptions: Set of unique normalized descriptions
    """

    fingerprint: str
    category: str
    count: int = 0
    descriptions: set[str] = field(default_factory=set)

    def add_occurrence(self, description: str) -> None:
        """Add an occurrence to this cluster."""
        self.count += 1
        self.descriptions.add(description)

    def get_variants(self) -> list[str]:
        """Get list of unique description variants in this cluster."""
        return list(self.descriptions)


class FingerprintClusterer:
    """Clusters issues by their fingerprints.

    Provides advanced clustering capabilities for grouping
    similar issues across multiple evaluation runs.
    """

    def __init__(self) -> None:
        """Initialize the clusterer."""
        self.clusters: dict[str, FingerprintCluster] = {}

    def add_issue(self, issue: Issue) -> str:
        """Add an issue to the clustering.

        Args:
            issue: Issue to add

        Returns:
            The fingerprint assigned to this issue
        """
        fingerprint = IssueFingerprint.generate(issue)
        normalized_desc = IssueFingerprint.normalize_description(issue.description)

        if fingerprint not in self.clusters:
            category = IssueFingerprint.extract_category(fingerprint)
            self.clusters[fingerprint] = FingerprintCluster(
                fingerprint=fingerprint, category=category
            )

        self.clusters[fingerprint].add_occurrence(normalized_desc)
        return fingerprint

    def get_clusters(self) -> list[FingerprintCluster]:
        """Get all clusters sorted by count (descending).

        Returns:
            List of FingerprintCluster objects
        """
        return sorted(self.clusters.values(), key=lambda c: c.count, reverse=True)

    def get_repeated_clusters(self, min_count: int = 2) -> list[FingerprintCluster]:
        """Get clusters with at least min_count occurrences.

        Args:
            min_count: Minimum number of occurrences (default: 2)

        Returns:
            List of FingerprintCluster objects with count >= min_count
        """
        return [c for c in self.get_clusters() if c.count >= min_count]

    def get_cluster_for_fingerprint(
        self, fingerprint: str
    ) -> FingerprintCluster | None:
        """Get the cluster for a specific fingerprint.

        Args:
            fingerprint: Fingerprint to look up

        Returns:
            FingerprintCluster if found, None otherwise
        """
        return self.clusters.get(fingerprint)

    def clear(self) -> None:
        """Clear all clusters."""
        self.clusters.clear()

    def get_stats(self) -> dict:
        """Get clustering statistics.

        Returns:
            Dictionary with clustering statistics
        """
        total_issues = sum(c.count for c in self.clusters.values())
        unique_fingerprints = len(self.clusters)
        repeated_clusters = len(self.get_repeated_clusters())

        return {
            "total_issues": total_issues,
            "unique_fingerprints": unique_fingerprints,
            "repeated_clusters": repeated_clusters,
            "single_occurrences": unique_fingerprints - repeated_clusters,
        }
