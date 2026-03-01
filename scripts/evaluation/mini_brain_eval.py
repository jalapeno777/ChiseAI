#!/usr/bin/env python3
"""
Mini BrainEval - Real Issue Detection from Iterlogs

SAFETY: No risk cap logic modified
SAFETY: No promotion gate logic modified
SAFETY: No live trading flow modified

This script scans docs/tempmemories/*.md files for real issues and generates
evaluation reports with detected patterns, severity classification, and
suggested mitigations.

Supports both:
- Structured issues from YAML blocks in `## Structured Issues` sections
- Legacy regex-based pattern detection as fallback
"""

import argparse
import hashlib
import json
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict, field


@dataclass
class Issue:
    """Represents a detected issue."""

    issue_type: str
    severity: str  # P0, P1, P2, P3
    description: str
    source_file: str
    timestamp: Optional[str] = None
    line_number: Optional[int] = None
    context: str = ""
    # Fields for structured issues
    root_cause: Optional[str] = None
    fix_applied: Optional[str] = None
    time_lost_minutes: Optional[int] = None
    recurrence_hint: Optional[str] = None
    impact_area: Optional[str] = None
    resolved: Optional[bool] = None
    fingerprint: Optional[str] = None
    is_structured: bool = False


@dataclass
class StructuredIssueEntry:
    """Represents a structured issue from YAML block."""

    issue_type: str
    root_cause: str
    fix_applied: Optional[str] = None
    time_lost_minutes: Optional[int] = None
    recurrence_hint: Optional[str] = None
    impact_area: Optional[str] = None
    resolved: bool = True


@dataclass
class RecurringIssue:
    """Represents a recurring issue pattern."""

    fingerprint: str
    issue_type: str
    root_cause: str
    occurrence_count: int
    total_time_lost_minutes: int
    source_files: List[str]
    resolved: bool


@dataclass
class MiniEvalResult:
    """Result of a mini brain evaluation."""

    eval_id: str
    timestamp: str
    cadence: str
    issues_found: List[Dict[str, Any]]
    mitigations: List[Dict[str, Any]]
    file_stats: Dict[str, Any]
    summary: str
    # New fields for structured issue tracking
    structured_issues_found: int = 0
    recurring_issues: List[Dict[str, Any]] = field(default_factory=list)
    time_lost_total_minutes: int = 0


class IssueDetector:
    """Detects issues from iterlog files."""

    # Issue patterns to search for (fallback for legacy files)
    PATTERNS = {
        "file_access": {
            "patterns": [
                r"permission denied",
                r"file not found",
                r"cannot read",
                r"no such file",
                r"access denied",
            ],
            "severity": "P2",
            "mitigation": "Check file permissions and paths. Ensure proper access rights.",
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
            ],
            "severity": "P1",
            "mitigation": "Verify database services are running. Check network connectivity and credentials.",
        },
        "env_slowdown": {
            "patterns": [
                r"slow",
                r"took \d+s",
                r"high memory",
                r"cpu usage",
                r"performance.*degraded",
                r"lag",
            ],
            "severity": "P2",
            "mitigation": "Monitor resource usage. Consider scaling or optimization.",
        },
        "tool_error": {
            "patterns": [
                r"failed",
                r"error:",
                r"exception",
                r"crash",
                r"fatal",
                r"panic",
            ],
            "severity": "P1",
            "mitigation": "Review error logs. Check tool configuration and dependencies.",
        },
        "ci_failure": {
            "patterns": [
                r"ci.*fail",
                r"build.*fail",
                r"test.*fail",
                r"lint.*error",
                r"check.*fail",
            ],
            "severity": "P2",
            "mitigation": "Review CI logs. Fix failing tests or linting issues.",
        },
        "blocker": {
            "patterns": [
                r"blocker",
                r"blocking",
                r"cannot proceed",
                r"stuck",
            ],
            "severity": "P0",
            "mitigation": "Escalate to team lead. Identify dependency or external blocker.",
        },
        "config_error": {
            "patterns": [
                r"config.*error",
                r"invalid.*config",
                r"missing.*config",
                r"configuration.*fail",
            ],
            "severity": "P1",
            "mitigation": "Verify configuration files. Check for missing or invalid settings.",
        },
        "api_error": {
            "patterns": [
                r"api.*error",
                r"http.*error",
                r"request.*fail",
                r"response.*error",
                r"status.*\d{3}",
            ],
            "severity": "P2",
            "mitigation": "Check API status and rate limits. Verify request format.",
        },
    }

    def __init__(self, tempmemories_path: str = "docs/tempmemories"):
        self.tempmemories_path = Path(tempmemories_path)
        self.issues: List[Issue] = []
        self.structured_issues: List[Issue] = []
        self.fingerprint_registry: Dict[str, List[Issue]] = {}

    def _generate_fingerprint(self, issue_type: str, root_cause: str) -> str:
        """Generate a fingerprint for issue deduplication."""
        content = f"{issue_type}|{root_cause}"
        return hashlib.md5(content.encode(), usedforsecurity=False).hexdigest()[:12]

    def _parse_yaml_value(self, line: str) -> Tuple[Optional[str], Any]:
        """Parse a simple YAML key: value line."""
        match = re.match(r"^\s+(\w+):\s*(.*)?$", line)
        if match:
            key = match.group(1)
            value = match.group(2)
            # Handle quoted strings
            if value and value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            elif value and value.startswith("'") and value.endswith("'"):
                value = value[1:-1]
            # Handle boolean
            elif value and value.lower() in ("true", "false"):
                value = value.lower() == "true"
            # Handle integer
            elif value and value.lstrip("-").isdigit():
                value = int(value)
            return key, value
        return None, None

    def _parse_structured_issues_section(
        self, content: str
    ) -> List[StructuredIssueEntry]:
        """
        Parse structured issues from YAML block in `## Structured Issues` section.

        Expected format:
        ## Structured Issues

        issues:
          - issue_type: "ci_failure"
            root_cause: "missing dependency"
            fix_applied: "added package to requirements"
            time_lost_minutes: 30
            recurrence_hint: "check deps before commit"
            impact_area: "efficiency"
            resolved: true
        """
        issues = []

        # Find the Structured Issues section
        section_match = re.search(
            r"^##\s+Structured\s+Issues\s*\n(.*?)(?=^##\s|\Z)",
            content,
            re.MULTILINE | re.DOTALL,
        )

        if not section_match:
            return issues

        section_content = section_match.group(1)

        # Check for empty issues list sentinel
        if re.search(r"^issues:\s*\[\s*\]\s*$", section_content, re.MULTILINE):
            return issues

        # Find the issues: block
        issues_match = re.search(r"^issues:\s*\n(.*)", section_content, re.DOTALL)
        if not issues_match:
            return issues

        issues_block = issues_match.group(1)
        lines = issues_block.split("\n")

        current_issue: Dict[str, Any] = {}

        for line in lines:
            # Check for new issue entry (starts with -)
            if re.match(r"^\s+-\s*$", line) or re.match(r"^\s+-\s+issue_type:", line):
                # Save previous issue if exists
                if (
                    current_issue
                    and "issue_type" in current_issue
                    and "root_cause" in current_issue
                ):
                    issues.append(
                        StructuredIssueEntry(
                            issue_type=current_issue.get("issue_type", ""),
                            root_cause=current_issue.get("root_cause", ""),
                            fix_applied=current_issue.get("fix_applied"),
                            time_lost_minutes=current_issue.get("time_lost_minutes"),
                            recurrence_hint=current_issue.get("recurrence_hint"),
                            impact_area=current_issue.get("impact_area"),
                            resolved=current_issue.get("resolved", True),
                        )
                    )
                current_issue = {}

                # Parse inline issue_type if present
                inline_match = re.match(r"^\s+-\s+issue_type:\s*(.+)$", line)
                if inline_match:
                    value = inline_match.group(1).strip()
                    if value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    current_issue["issue_type"] = value
                continue

            # Parse key: value pairs
            key, value = self._parse_yaml_value(line)
            if key and value is not None:
                current_issue[key] = value

        # Don't forget the last issue
        if (
            current_issue
            and "issue_type" in current_issue
            and "root_cause" in current_issue
        ):
            issues.append(
                StructuredIssueEntry(
                    issue_type=current_issue.get("issue_type", ""),
                    root_cause=current_issue.get("root_cause", ""),
                    fix_applied=current_issue.get("fix_applied"),
                    time_lost_minutes=current_issue.get("time_lost_minutes"),
                    recurrence_hint=current_issue.get("recurrence_hint"),
                    impact_area=current_issue.get("impact_area"),
                    resolved=current_issue.get("resolved", True),
                )
            )

        return issues

    def _severity_from_issue_type(self, issue_type: str) -> str:
        """Map issue_type to severity."""
        severity_map = {
            "blocker": "P0",
            "ci_failure": "P2",
            "db_connectivity": "P1",
            "config_error": "P1",
            "api_error": "P2",
            "tool_error": "P1",
            "file_access": "P2",
            "env_slowdown": "P2",
        }
        return severity_map.get(issue_type, "P3")

    def scan_files(self) -> List[Issue]:
        """Scan all markdown files in tempmemories for issues."""
        self.issues = []
        self.structured_issues = []
        self.fingerprint_registry = {}

        if not self.tempmemories_path.exists():
            print(f"Warning: Path {self.tempmemories_path} does not exist")
            return self.issues

        md_files = list(self.tempmemories_path.glob("*.md"))

        for file_path in md_files:
            self._scan_file(file_path)

        # Merge issues: structured issues take precedence
        # Remove regex-detected issues that match structured issue fingerprints
        structured_fingerprints = {
            i.fingerprint for i in self.structured_issues if i.fingerprint
        }

        filtered_regex_issues = [
            i
            for i in self.issues
            if not i.is_structured and i.fingerprint not in structured_fingerprints
        ]

        # Combine: structured first, then filtered regex
        self.issues = self.structured_issues + filtered_regex_issues

        return self.issues

    def _scan_file(self, file_path: Path) -> None:
        """Scan a single file for issues."""
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                lines = content.split("\n")
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
            return

        # Extract timestamp from frontmatter if present
        timestamp = self._extract_timestamp(content)

        # PRIORITY: Try to parse structured issues first
        structured_entries = self._parse_structured_issues_section(content)

        if structured_entries:
            # Process structured issues
            for entry in structured_entries:
                fingerprint = self._generate_fingerprint(
                    entry.issue_type, entry.root_cause
                )

                issue = Issue(
                    issue_type=entry.issue_type,
                    severity=self._severity_from_issue_type(entry.issue_type),
                    description=f"{entry.issue_type}: {entry.root_cause}",
                    source_file=str(file_path),
                    timestamp=timestamp,
                    root_cause=entry.root_cause,
                    fix_applied=entry.fix_applied,
                    time_lost_minutes=entry.time_lost_minutes,
                    recurrence_hint=entry.recurrence_hint,
                    impact_area=entry.impact_area,
                    resolved=entry.resolved,
                    fingerprint=fingerprint,
                    is_structured=True,
                )
                self.structured_issues.append(issue)

                # Track in fingerprint registry
                if fingerprint not in self.fingerprint_registry:
                    self.fingerprint_registry[fingerprint] = []
                self.fingerprint_registry[fingerprint].append(issue)
        else:
            # FALLBACK: Use regex pattern detection for legacy files
            for line_num, line in enumerate(lines, 1):
                for issue_type, config in self.PATTERNS.items():
                    for pattern in config["patterns"]:
                        if re.search(pattern, line, re.IGNORECASE):
                            # Get context (surrounding lines)
                            context_start = max(0, line_num - 2)
                            context_end = min(len(lines), line_num + 1)
                            context = "\n".join(lines[context_start:context_end])

                            # Generate fingerprint from issue type and description
                            fingerprint = self._generate_fingerprint(
                                issue_type, line.strip()
                            )

                            issue = Issue(
                                issue_type=issue_type,
                                severity=config["severity"],
                                description=line.strip(),
                                source_file=str(file_path),
                                timestamp=timestamp,
                                line_number=line_num,
                                context=context.strip(),
                                fingerprint=fingerprint,
                                is_structured=False,
                            )
                            self.issues.append(issue)

                            # Track in fingerprint registry
                            if fingerprint not in self.fingerprint_registry:
                                self.fingerprint_registry[fingerprint] = []
                            self.fingerprint_registry[fingerprint].append(issue)
                            break  # Avoid duplicate detection for same line

    def _extract_timestamp(self, content: str) -> Optional[str]:
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

    def get_recurring_issues(self) -> List[RecurringIssue]:
        """Identify recurring issues based on fingerprint grouping."""
        recurring = []

        for fingerprint, issues in self.fingerprint_registry.items():
            if len(issues) > 1:
                # This is a recurring issue
                total_time = sum(i.time_lost_minutes or 0 for i in issues)
                recurring.append(
                    RecurringIssue(
                        fingerprint=fingerprint,
                        issue_type=issues[0].issue_type,
                        root_cause=issues[0].root_cause or issues[0].description,
                        occurrence_count=len(issues),
                        total_time_lost_minutes=total_time,
                        source_files=list(set(i.source_file for i in issues)),
                        resolved=all(
                            i.resolved for i in issues if i.resolved is not None
                        ),
                    )
                )

        return recurring

    def get_time_lost_total(self) -> int:
        """Calculate total time lost across all issues."""
        return sum(i.time_lost_minutes or 0 for i in self.issues)

    def get_mitigations(self) -> List[Dict[str, Any]]:
        """Generate mitigation suggestions based on detected issues."""
        mitigations = []

        # Group issues by type
        issues_by_type: Dict[str, List[Issue]] = {}
        for issue in self.issues:
            if issue.issue_type not in issues_by_type:
                issues_by_type[issue.issue_type] = []
            issues_by_type[issue.issue_type].append(issue)

        for issue_type, issues in issues_by_type.items():
            config = self.PATTERNS.get(issue_type, {})

            # Use recurrence_hint from structured issues if available
            structured_hints = [i.recurrence_hint for i in issues if i.recurrence_hint]
            suggestion = (
                structured_hints[0]
                if structured_hints
                else config.get("mitigation", "Review and address the issue.")
            )

            mitigation = {
                "issue_type": issue_type,
                "count": len(issues),
                "severity": config.get(
                    "severity", self._severity_from_issue_type(issue_type)
                ),
                "suggestion": suggestion,
                "affected_files": list(set(i.source_file for i in issues)),
            }
            mitigations.append(mitigation)

        return mitigations

    def get_file_stats(self) -> Dict[str, Any]:
        """Generate statistics about scanned files."""
        md_files = (
            list(self.tempmemories_path.glob("*.md"))
            if self.tempmemories_path.exists()
            else []
        )

        # Count issues by severity
        severity_counts = {"P0": 0, "P1": 0, "P2": 0, "P3": 0}
        for issue in self.issues:
            if issue.severity in severity_counts:
                severity_counts[issue.severity] += 1

        # Count issues by type
        type_counts: Dict[str, int] = {}
        for issue in self.issues:
            type_counts[issue.issue_type] = type_counts.get(issue.issue_type, 0) + 1

        return {
            "files_scanned": len(md_files),
            "total_issues": len(self.issues),
            "issues_by_severity": severity_counts,
            "issues_by_type": type_counts,
            "files_with_issues": len(set(i.source_file for i in self.issues)),
            "structured_issues_count": len(self.structured_issues),
        }


def run_evaluation(
    cadence: str, output_dir: str = "_bmad-output/brain-eval"
) -> MiniEvalResult:
    """Run a complete evaluation for the specified cadence."""

    detector = IssueDetector()
    issues = detector.scan_files()
    mitigations = detector.get_mitigations()
    file_stats = detector.get_file_stats()
    recurring_issues = detector.get_recurring_issues()
    time_lost_total = detector.get_time_lost_total()

    # Generate summary
    summary_parts = [
        f"Scanned {file_stats['files_scanned']} files",
        f"Found {file_stats['total_issues']} issues",
    ]

    if file_stats["total_issues"] > 0:
        summary_parts.append(
            f"P0: {file_stats['issues_by_severity']['P0']}, "
            f"P1: {file_stats['issues_by_severity']['P1']}, "
            f"P2: {file_stats['issues_by_severity']['P2']}, "
            f"P3: {file_stats['issues_by_severity']['P3']}"
        )

    if file_stats["structured_issues_count"] > 0:
        summary_parts.append(f"Structured: {file_stats['structured_issues_count']}")

    if time_lost_total > 0:
        summary_parts.append(f"Time lost: {time_lost_total}min")

    if recurring_issues:
        summary_parts.append(f"Recurring: {len(recurring_issues)} patterns")

    result = MiniEvalResult(
        eval_id=str(uuid.uuid4()),
        timestamp=datetime.utcnow().isoformat() + "Z",
        cadence=cadence,
        issues_found=[asdict(issue) for issue in issues],
        mitigations=mitigations,
        file_stats=file_stats,
        summary="; ".join(summary_parts),
        structured_issues_found=file_stats["structured_issues_count"],
        recurring_issues=[asdict(r) for r in recurring_issues],
        time_lost_total_minutes=time_lost_total,
    )

    # Save to file
    output_path = Path(output_dir) / cadence
    output_path.mkdir(parents=True, exist_ok=True)

    timestamp_str = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    output_file = output_path / f"{timestamp_str}.json"

    with open(output_file, "w") as f:
        json.dump(asdict(result), f, indent=2)

    print(f"Evaluation complete. Results saved to: {output_file}")
    print(f"Summary: {result.summary}")

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Mini BrainEval - Detect issues from iterlog files"
    )
    parser.add_argument(
        "--cadence",
        choices=["6h", "daily", "weekly"],
        required=True,
        help="Evaluation cadence",
    )
    parser.add_argument(
        "--output-dir",
        default="_bmad-output/brain-eval",
        help="Output directory for results",
    )
    parser.add_argument(
        "--tempmemories",
        default="docs/tempmemories",
        help="Path to tempmemories directory",
    )

    args = parser.parse_args()

    # Override tempmemories path if provided
    if args.tempmemories != "docs/tempmemories":
        global IssueDetector
        original_init = IssueDetector.__init__
        IssueDetector.__init__ = (
            lambda self, tempmemories_path=args.tempmemories: original_init(
                self, tempmemories_path
            )
        )

    result = run_evaluation(args.cadence, args.output_dir)

    # Print summary
    print(f"\n{'=' * 60}")
    print(f"Mini BrainEval - {args.cadence.upper()} Evaluation")
    print(f"{'=' * 60}")
    print(f"Eval ID: {result.eval_id}")
    print(f"Timestamp: {result.timestamp}")
    print(f"Files Scanned: {result.file_stats['files_scanned']}")
    print(f"Total Issues: {result.file_stats['total_issues']}")
    print(f"Structured Issues: {result.structured_issues_found}")
    print(f"Time Lost: {result.time_lost_total_minutes} minutes")

    if result.file_stats["total_issues"] > 0:
        print(f"\nIssues by Severity:")
        for sev, count in result.file_stats["issues_by_severity"].items():
            if count > 0:
                print(f"  {sev}: {count}")

        print(f"\nIssues by Type:")
        for issue_type, count in result.file_stats["issues_by_type"].items():
            print(f"  {issue_type}: {count}")

        print(f"\nTop Mitigations:")
        for mit in sorted(result.mitigations, key=lambda x: x["count"], reverse=True)[
            :5
        ]:
            print(
                f"  - {mit['issue_type']} ({mit['count']}): {mit['suggestion'][:60]}..."
            )

    if result.recurring_issues:
        print(f"\nRecurring Issue Patterns:")
        for rec in result.recurring_issues:
            print(
                f"  - [{rec['fingerprint']}] {rec['issue_type']}: {rec['root_cause'][:50]}..."
            )
            print(
                f"    Occurrences: {rec['occurrence_count']}, Time lost: {rec['total_time_lost_minutes']}min"
            )


if __name__ == "__main__":
    main()
