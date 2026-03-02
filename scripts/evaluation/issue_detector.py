#!/usr/bin/env python3
"""
Issue Detector - Standalone issue detection from iterlog files

SAFETY: No risk cap logic modified
SAFETY: No promotion gate logic modified
SAFETY: No live trading flow modified

This module provides issue detection capabilities that can be used
independently or as part of the BrainEval system.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class DetectedIssue:
    """Represents a detected issue from iterlog scanning."""

    issue_type: str
    severity: str
    description: str
    source_file: str
    timestamp: str | None = None
    line_number: int | None = None
    context: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "issue_type": self.issue_type,
            "severity": self.severity,
            "description": self.description,
            "source_file": self.source_file,
            "timestamp": self.timestamp,
            "line_number": self.line_number,
            "context": self.context,
        }


class IssuePatterns:
    """Standard issue patterns for detection."""

    PATTERNS = {
        "file_access": {
            "patterns": [
                r"permission denied",
                r"file not found",
                r"cannot read",
                r"no such file",
                r"access denied",
                r"unauthorized access",
            ],
            "severity": "P2",
            "category": "filesystem",
        },
        "db_connectivity": {
            "patterns": [
                r"connection refused",
                r"timeout",
                r"postgresql.*error",
                r"redis.*error",
                r"influxdb.*error",
                r"database.*unavailable",
                r"cannot connect",
                r"connection.*closed",
            ],
            "severity": "P1",
            "category": "database",
        },
        "env_slowdown": {
            "patterns": [
                r"slow",
                r"took \d+s",
                r"high memory",
                r"cpu usage",
                r"performance.*degraded",
                r"lag",
                r"bottleneck",
            ],
            "severity": "P2",
            "category": "performance",
        },
        "tool_error": {
            "patterns": [
                r"failed",
                r"error:",
                r"exception",
                r"crash",
                r"fatal",
                r"panic",
                r"traceback",
            ],
            "severity": "P1",
            "category": "runtime",
        },
        "ci_failure": {
            "patterns": [
                r"ci.*fail",
                r"build.*fail",
                r"test.*fail",
                r"lint.*error",
                r"check.*fail",
                r"pipeline.*fail",
            ],
            "severity": "P2",
            "category": "ci",
        },
        "blocker": {
            "patterns": [
                r"blocker",
                r"blocking",
                r"cannot proceed",
                r"stuck",
                r"deadlock",
            ],
            "severity": "P0",
            "category": "workflow",
        },
        "config_error": {
            "patterns": [
                r"config.*error",
                r"invalid.*config",
                r"missing.*config",
                r"configuration.*fail",
                r"key.*not.*found",
            ],
            "severity": "P1",
            "category": "configuration",
        },
        "api_error": {
            "patterns": [
                r"api.*error",
                r"http.*error",
                r"request.*fail",
                r"response.*error",
                r"status.*\d{3}",
                r"rate.*limit",
            ],
            "severity": "P2",
            "category": "api",
        },
        "security": {
            "patterns": [
                r"security.*issue",
                r"vulnerability",
                r"exploit",
                r"breach",
                r"unauthorized",
                r"injection",
            ],
            "severity": "P0",
            "category": "security",
        },
        "dependency": {
            "patterns": [
                r"dependency.*error",
                r"module.*not.*found",
                r"import.*error",
                r"package.*missing",
                r"version.*conflict",
            ],
            "severity": "P1",
            "category": "dependencies",
        },
    }


class IssueScanner:
    """Scans files for issues based on defined patterns."""

    def __init__(self, patterns: dict[str, dict[str, Any]] | None = None):
        self.patterns = patterns or IssuePatterns.PATTERNS

    def scan_file(self, file_path: Path) -> Iterator[DetectedIssue]:
        """Scan a single file for issues."""
        try:
            with open(file_path, encoding="utf-8", errors="ignore") as f:
                content = f.read()
                lines = content.split("\n")
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
            return

        # Extract timestamp from frontmatter if present
        timestamp = self._extract_timestamp(content)

        for line_num, line in enumerate(lines, 1):
            for issue_type, config in self.patterns.items():
                for pattern in config["patterns"]:
                    if re.search(pattern, line, re.IGNORECASE):
                        # Get context (surrounding lines)
                        context_start = max(0, line_num - 2)
                        context_end = min(len(lines), line_num + 1)
                        context = "\n".join(lines[context_start:context_end])

                        severity = str(config.get("severity", "P3"))
                        yield DetectedIssue(
                            issue_type=issue_type,
                            severity=severity,
                            description=line.strip(),
                            source_file=str(file_path),
                            timestamp=timestamp,
                            line_number=line_num,
                            context=context.strip(),
                        )
                        break  # Avoid duplicate detection for same line

    def scan_directory(
        self, directory: Path, pattern: str = "*.md"
    ) -> Iterator[DetectedIssue]:
        """Scan all files in a directory matching pattern."""
        if not directory.exists():
            return

        for file_path in directory.glob(pattern):
            yield from self.scan_file(file_path)

    def _extract_timestamp(self, content: str) -> str | None:
        """Extract timestamp from file frontmatter."""
        # Look for date: YYYY-MM-DD pattern
        date_match = re.search(r"date:\s*(\d{4}-\d{2}-\d{2})", content)
        if date_match:
            return date_match.group(1)

        # Look for timestamp in filename pattern
        ts_match = re.search(r"(\d{4}-\d{2}-\d{2})", content[:500])
        if ts_match:
            return ts_match.group(1)

        return None


def detect_issues(
    source_path: str,
    file_pattern: str = "*.md",
    patterns: dict[str, dict[str, Any]] | None = None,
) -> list[DetectedIssue]:
    """
    Convenience function to detect issues from a path.

    Args:
        source_path: Path to file or directory to scan
        file_pattern: Glob pattern for files (if directory)
        patterns: Custom patterns (uses defaults if None)

    Returns:
        List of detected issues
    """
    path = Path(source_path)
    scanner = IssueScanner(patterns)

    if path.is_file():
        return list(scanner.scan_file(path))
    else:
        return list(scanner.scan_directory(path, file_pattern))


def get_issue_summary(issues: list[DetectedIssue]) -> dict[str, Any]:
    """Generate summary statistics from issues."""
    severity_counts = {"P0": 0, "P1": 0, "P2": 0, "P3": 0}
    type_counts: dict[str, int] = {}
    category_counts: dict[str, int] = {}

    patterns = IssuePatterns.PATTERNS

    for issue in issues:
        if issue.severity in severity_counts:
            severity_counts[issue.severity] += 1

        type_counts[issue.issue_type] = type_counts.get(issue.issue_type, 0) + 1

        category = str(patterns.get(issue.issue_type, {}).get("category", "unknown"))
        category_counts[category] = category_counts.get(category, 0) + 1

    return {
        "total": len(issues),
        "by_severity": severity_counts,
        "by_type": type_counts,
        "by_category": category_counts,
        "files_affected": len(set(i.source_file for i in issues)),
    }


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Detect issues in iterlog files")
    parser.add_argument("path", help="Path to file or directory to scan")
    parser.add_argument(
        "--pattern", default="*.md", help="File pattern for directories"
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    issues = detect_issues(args.path, args.pattern)
    summary = get_issue_summary(issues)

    if args.json:
        output = {"issues": [i.to_dict() for i in issues], "summary": summary}
        print(json.dumps(output, indent=2))
    else:
        print(f"Found {summary['total']} issues:")
        print(f"\nBy Severity: {summary['by_severity']}")
        print(f"\nBy Type: {summary['by_type']}")

        if issues:
            print("\nTop 10 Issues:")
            for i, issue in enumerate(issues[:10], 1):
                print(
                    f"  {i}. [{issue.severity}] {issue.issue_type}: {issue.description[:60]}..."
                )
