#!/usr/bin/env python3
"""
Conflict Detector for ChiseAI Agent Swarm Parallel Coordination.

Detects file-level conflicts between parallel agent work and determines
if changes are safe to auto-resolve (non-overlapping) or require manual intervention.

Story: ST-AUTO-007
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class ConflictType(Enum):
    """Types of conflicts that can occur."""

    NONE = "none"
    FILE_OVERLAP = "file_overlap"  # Same file modified
    SCOPE_OVERLAP = "scope_overlap"  # Same scope/module modified
    MERGE_CONFLICT = "merge_conflict"  # Git merge conflict would occur
    DEPENDENCY = "dependency"  # One change depends on another
    LOCK_CONTENTION = "lock_contention"  # Redis lock conflict


class ConflictSeverity(Enum):
    """Severity levels for conflicts."""

    NONE = "none"
    LOW = "low"  # Non-overlapping changes, safe to auto-resolve
    MEDIUM = "medium"  # Some overlap but likely resolvable
    HIGH = "high"  # Significant overlap, manual resolution needed
    CRITICAL = "critical"  # Blocking conflict, cannot proceed


@dataclass
class ConflictReport:
    """Report of detected conflicts."""

    conflict_type: ConflictType
    severity: ConflictSeverity
    source_story: str
    target_story: str
    source_agent: str
    target_agent: str
    conflicting_files: list[str] = field(default_factory=list)
    description: str = ""
    resolution_strategy: str = ""
    auto_resolvable: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "conflict_type": self.conflict_type.value,
            "severity": self.severity.value,
            "source_story": self.source_story,
            "target_story": self.target_story,
            "source_agent": self.source_agent,
            "target_agent": self.target_agent,
            "conflicting_files": self.conflicting_files,
            "description": self.description,
            "resolution_strategy": self.resolution_strategy,
            "auto_resolvable": self.auto_resolvable,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConflictReport:
        """Create ConflictReport from dictionary."""
        return cls(
            conflict_type=ConflictType(data.get("conflict_type", "none")),
            severity=ConflictSeverity(data.get("severity", "none")),
            source_story=data["source_story"],
            target_story=data["target_story"],
            source_agent=data["source_agent"],
            target_agent=data["target_agent"],
            conflicting_files=data.get("conflicting_files", []),
            description=data.get("description", ""),
            resolution_strategy=data.get("resolution_strategy", ""),
            auto_resolvable=data.get("auto_resolvable", False),
            metadata=data.get("metadata", {}),
        )


@dataclass
class FileChange:
    """Represents a change to a file."""

    path: str
    change_type: str  # added, modified, deleted, renamed
    additions: int = 0
    deletions: int = 0
    diff_content: str = ""
    scope: str | None = None  # Detected scope/module


@dataclass
class ChangeSet:
    """Set of changes for a story/agent."""

    story_id: str
    agent: str
    branch: str
    base_ref: str = "main"
    files: list[FileChange] = field(default_factory=list)
    scopes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "story_id": self.story_id,
            "agent": self.agent,
            "branch": self.branch,
            "base_ref": self.base_ref,
            "files": [
                {
                    "path": f.path,
                    "change_type": f.change_type,
                    "additions": f.additions,
                    "deletions": f.deletions,
                    "scope": f.scope,
                }
                for f in self.files
            ],
            "scopes": self.scopes,
        }


class ConflictDetector:
    """Detects conflicts between parallel agent work."""

    # File patterns that indicate scope boundaries
    SCOPE_PATTERNS = {
        "scripts:swarm": [r"scripts/swarm/.*"],
        "scripts:pr_lifecycle": [r"scripts/pr_lifecycle/.*"],
        "src:strategy": [r"src/strategy/.*"],
        "src:governance": [r"src/governance/.*"],
        "tests:swarm": [r"tests/test_swarm/.*"],
        "docs": [r"docs/.*"],
    }

    # Files that should never be auto-merged
    PROTECTED_FILES = {
        ".woodpecker.yml",
        "pyproject.toml",
        "AGENTS.md",
        "docs/bmm-workflow-status.yaml",
        "docs/validation/validation-registry.yaml",
    }

    def __init__(self, repo_root: Path | None = None):
        """Initialize conflict detector.

        Args:
            repo_root: Root of the git repository. Auto-detected if not provided.
        """
        self.repo_root = repo_root or self._find_repo_root()

    def _find_repo_root(self) -> Path:
        """Find the git repository root."""
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError("Not in a git repository")
        return Path(result.stdout.strip())

    def get_changed_files(
        self, branch: str, base_ref: str = "main"
    ) -> list[FileChange]:
        """Get list of changed files between branch and base_ref.

        Args:
            branch: Branch to compare
            base_ref: Base reference to compare against

        Returns:
            List of FileChange objects
        """
        # Get diff stats
        result = subprocess.run(
            [
                "git",
                "-C",
                str(self.repo_root),
                "diff",
                "--stat",
                f"{base_ref}...{branch}",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            logger.warning(f"Failed to get diff stats: {result.stderr}")
            return []

        files = []
        for line in result.stdout.split("\n"):
            # Parse lines like: "path/to/file.py | 10 +++---"
            match = re.match(r"^(.+?)\s+\|\s+(\d+)\s+([+-]*)", line)
            if match:
                path = match.group(1).strip()
                changes = match.group(3)
                additions = changes.count("+")
                deletions = changes.count("-")

                # Determine change type
                change_type = "modified"
                if additions > 0 and deletions == 0:
                    change_type = "added"
                elif additions == 0 and deletions > 0:
                    change_type = "deleted"

                files.append(
                    FileChange(
                        path=path,
                        change_type=change_type,
                        additions=additions,
                        deletions=deletions,
                        scope=self._detect_scope(path),
                    )
                )

        return files

    def _detect_scope(self, file_path: str) -> str | None:
        """Detect the scope/module for a file path."""
        for scope, patterns in self.SCOPE_PATTERNS.items():
            for pattern in patterns:
                if re.match(pattern, file_path):
                    return scope
        return None

    def detect_scope_overlap(
        self, change_set1: ChangeSet, change_set2: ChangeSet
    ) -> list[str]:
        """Detect scope overlaps between two change sets.

        Args:
            change_set1: First change set
            change_set2: Second change set

        Returns:
            List of overlapping scope names
        """
        scopes1 = set(change_set1.scopes) or set(
            f.scope for f in change_set1.files if f.scope
        )
        scopes2 = set(change_set2.scopes) or set(
            f.scope for f in change_set2.files if f.scope
        )

        return list(scopes1 & scopes2)

    def detect_file_overlap(
        self,
        change_set1: ChangeSet,
        change_set2: ChangeSet,
    ) -> list[str]:
        """Detect file overlaps between two change sets.

        Args:
            change_set1: First change set
            change_set2: Second change set

        Returns:
            List of overlapping file paths
        """
        files1 = {f.path for f in change_set1.files}
        files2 = {f.path for f in change_set2.files}

        return list(files1 & files2)

    def check_merge_conflict_potential(
        self,
        branch1: str,
        branch2: str,
        base_ref: str = "main",
    ) -> tuple[bool, list[str]]:
        """Check if two branches would have merge conflicts.

        Args:
            branch1: First branch
            branch2: Second branch
            base_ref: Base reference

        Returns:
            Tuple of (would_conflict, conflicting_files)
        """
        # Get changed files for both branches
        files1 = self.get_changed_files(branch1, base_ref)
        files2 = self.get_changed_files(branch2, base_ref)

        paths1 = {f.path for f in files1}
        paths2 = {f.path for f in files2}

        overlapping = paths1 & paths2

        if not overlapping:
            return False, []

        # For overlapping files, check if changes are in different regions
        # This is a simplified check - full merge simulation would be expensive
        conflicting = []
        for path in overlapping:
            if self._is_protected_file(path) or self._would_file_conflict(branch1, branch2, path, base_ref):
                conflicting.append(path)

        return bool(conflicting), list(conflicting)

    def _is_protected_file(self, path: str) -> bool:
        """Check if a file is protected (should never auto-merge)."""
        return any(path.endswith(p) or path == p for p in self.PROTECTED_FILES)

    def _would_file_conflict(
        self,
        branch1: str,
        branch2: str,
        file_path: str,
        base_ref: str,
    ) -> bool:
        """Check if a specific file would have merge conflicts.

        This is a heuristic check - it looks at whether both branches
        modified the same regions of the file.
        """
        # Get the diff for the file from both branches
        result1 = subprocess.run(
            [
                "git",
                "-C",
                str(self.repo_root),
                "diff",
                f"{base_ref}...{branch1}",
                "--",
                file_path,
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        result2 = subprocess.run(
            [
                "git",
                "-C",
                str(self.repo_root),
                "diff",
                f"{base_ref}...{branch2}",
                "--",
                file_path,
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        if result1.returncode != 0 or result2.returncode != 0:
            return True  # Assume conflict if we can't check

        diff1 = result1.stdout
        diff2 = result2.stdout

        # Extract changed line ranges from diffs
        ranges1 = self._extract_changed_ranges(diff1)
        ranges2 = self._extract_changed_ranges(diff2)

        # Check for overlap in changed ranges
        for start1, end1 in ranges1:
            for start2, end2 in ranges2:
                if start1 <= end2 and start2 <= end1:
                    return True

        return False

    def _extract_changed_ranges(self, diff: str) -> list[tuple[int, int]]:
        """Extract changed line ranges from a diff.

        Returns:
            List of (start_line, end_line) tuples
        """
        ranges = []
        for line in diff.split("\n"):
            # Look for hunk headers like @@ -1,5 +1,7 @@
            match = re.match(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
            if match:
                start = int(match.group(3))
                count = int(match.group(4)) if match.group(4) else 1
                ranges.append((start, start + count - 1))
        return ranges

    def analyze_changes(
        self,
        story_id: str,
        agent: str,
        branch: str,
        base_ref: str = "main",
    ) -> ChangeSet:
        """Analyze changes for a story/agent.

        Args:
            story_id: Story ID
            agent: Agent identifier
            branch: Branch name
            base_ref: Base reference

        Returns:
            ChangeSet with detected changes
        """
        files = self.get_changed_files(branch, base_ref)
        scopes = list(set(f.scope for f in files if f.scope))

        return ChangeSet(
            story_id=story_id,
            agent=agent,
            branch=branch,
            base_ref=base_ref,
            files=files,
            scopes=scopes,
        )

    def detect_conflicts(
        self,
        change_set1: ChangeSet,
        change_set2: ChangeSet,
    ) -> ConflictReport:
        """Detect conflicts between two change sets.

        Args:
            change_set1: First change set
            change_set2: Second change set

        Returns:
            ConflictReport with detection results
        """
        # Check for file overlaps
        file_overlaps = self.detect_file_overlap(change_set1, change_set2)

        if not file_overlaps:
            # No file overlap - safe to proceed
            return ConflictReport(
                conflict_type=ConflictType.NONE,
                severity=ConflictSeverity.NONE,
                source_story=change_set1.story_id,
                target_story=change_set2.story_id,
                source_agent=change_set1.agent,
                target_agent=change_set2.agent,
                description="No file overlap detected - changes are independent",
                auto_resolvable=True,
            )

        # Check for protected files
        protected_overlaps = [f for f in file_overlaps if self._is_protected_file(f)]
        if protected_overlaps:
            return ConflictReport(
                conflict_type=ConflictType.FILE_OVERLAP,
                severity=ConflictSeverity.CRITICAL,
                source_story=change_set1.story_id,
                target_story=change_set2.story_id,
                source_agent=change_set1.agent,
                target_agent=change_set2.agent,
                conflicting_files=file_overlaps,
                description=f"Protected files modified: {protected_overlaps}",
                resolution_strategy="Manual resolution required for protected files",
                auto_resolvable=False,
            )

        # Check for merge conflict potential
        would_conflict, conflicting_files = self.check_merge_conflict_potential(
            change_set1.branch,
            change_set2.branch,
            change_set1.base_ref,
        )

        if would_conflict:
            # Determine severity based on number of conflicting files
            if len(conflicting_files) <= 2:
                severity = ConflictSeverity.MEDIUM
                strategy = "Manual merge with careful review recommended"
            else:
                severity = ConflictSeverity.HIGH
                strategy = "Manual resolution required - significant overlap"

            return ConflictReport(
                conflict_type=ConflictType.MERGE_CONFLICT,
                severity=severity,
                source_story=change_set1.story_id,
                target_story=change_set2.story_id,
                source_agent=change_set1.agent,
                target_agent=change_set2.agent,
                conflicting_files=conflicting_files,
                description=f"Merge conflicts detected in {len(conflicting_files)} files",
                resolution_strategy=strategy,
                auto_resolvable=False,
            )

        # Files overlap but no merge conflicts - safe to auto-resolve
        return ConflictReport(
            conflict_type=ConflictType.FILE_OVERLAP,
            severity=ConflictSeverity.LOW,
            source_story=change_set1.story_id,
            target_story=change_set2.story_id,
            source_agent=change_set1.agent,
            target_agent=change_set2.agent,
            conflicting_files=file_overlaps,
            description="File overlap but changes are in non-conflicting regions",
            resolution_strategy="Auto-merge safe - changes are independent",
            auto_resolvable=True,
        )

    def detect_all_conflicts(
        self,
        change_sets: list[ChangeSet],
    ) -> list[ConflictReport]:
        """Detect all conflicts among multiple change sets.

        Args:
            change_sets: List of change sets to compare

        Returns:
            List of ConflictReport objects
        """
        reports = []
        for i, cs1 in enumerate(change_sets):
            for cs2 in change_sets[i + 1 :]:
                report = self.detect_conflicts(cs1, cs2)
                if report.conflict_type != ConflictType.NONE:
                    reports.append(report)
        return reports

    def generate_conflict_matrix(
        self,
        change_sets: list[ChangeSet],
    ) -> dict[str, Any]:
        """Generate a conflict matrix for visualization.

        Args:
            change_sets: List of change sets

        Returns:
            Dictionary with conflict matrix data
        """
        matrix = {}
        for cs in change_sets:
            matrix[f"{cs.story_id}/{cs.agent}"] = {}

        for i, cs1 in enumerate(change_sets):
            for cs2 in change_sets[i + 1 :]:
                report = self.detect_conflicts(cs1, cs2)
                key1 = f"{cs1.story_id}/{cs1.agent}"
                key2 = f"{cs2.story_id}/{cs2.agent}"

                matrix[key1][key2] = {
                    "conflict": report.conflict_type != ConflictType.NONE,
                    "severity": report.severity.value,
                    "auto_resolvable": report.auto_resolvable,
                }
                matrix[key2][key1] = matrix[key1][key2]

        return {
            "agents": list(matrix.keys()),
            "matrix": matrix,
            "total_conflicts": sum(
                1
                for r in self.detect_all_conflicts(change_sets)
                if r.conflict_type != ConflictType.NONE
            ),
            "auto_resolvable": sum(
                1 for r in self.detect_all_conflicts(change_sets) if r.auto_resolvable
            ),
        }


def main():
    """CLI entry point for conflict detector."""
    import argparse

    parser = argparse.ArgumentParser(description="ChiseAI Conflict Detector")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Analyze command
    analyze_parser = subparsers.add_parser(
        "analyze", help="Analyze changes for a branch"
    )
    analyze_parser.add_argument("--story-id", required=True, help="Story ID")
    analyze_parser.add_argument("--agent", required=True, help="Agent identifier")
    analyze_parser.add_argument("--branch", required=True, help="Branch name")
    analyze_parser.add_argument("--base", default="main", help="Base reference")

    # Compare command
    compare_parser = subparsers.add_parser(
        "compare", help="Compare two branches for conflicts"
    )
    compare_parser.add_argument("--story1", required=True, help="First story ID")
    compare_parser.add_argument("--agent1", required=True, help="First agent")
    compare_parser.add_argument("--branch1", required=True, help="First branch")
    compare_parser.add_argument("--story2", required=True, help="Second story ID")
    compare_parser.add_argument("--agent2", required=True, help="Second agent")
    compare_parser.add_argument("--branch2", required=True, help="Second branch")
    compare_parser.add_argument("--base", default="main", help="Base reference")

    # Matrix command
    matrix_parser = subparsers.add_parser(
        "matrix", help="Generate conflict matrix for multiple branches"
    )
    matrix_parser.add_argument(
        "--specs", required=True, help="JSON file with branch specs"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    detector = ConflictDetector()

    try:
        if args.command == "analyze":
            change_set = detector.analyze_changes(
                story_id=args.story_id,
                agent=args.agent,
                branch=args.branch,
                base_ref=args.base,
            )
            print(json.dumps(change_set.to_dict(), indent=2))

        elif args.command == "compare":
            cs1 = detector.analyze_changes(
                story_id=args.story1,
                agent=args.agent1,
                branch=args.branch1,
                base_ref=args.base,
            )
            cs2 = detector.analyze_changes(
                story_id=args.story2,
                agent=args.agent2,
                branch=args.branch2,
                base_ref=args.base,
            )
            report = detector.detect_conflicts(cs1, cs2)
            print(json.dumps(report.to_dict(), indent=2))

        elif args.command == "matrix":
            with open(args.specs) as f:
                specs = json.load(f)

            change_sets = []
            for spec in specs:
                cs = detector.analyze_changes(
                    story_id=spec["story_id"],
                    agent=spec["agent"],
                    branch=spec["branch"],
                    base_ref=spec.get("base", "main"),
                )
                change_sets.append(cs)

            matrix = detector.generate_conflict_matrix(change_sets)
            print(json.dumps(matrix, indent=2))

        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
