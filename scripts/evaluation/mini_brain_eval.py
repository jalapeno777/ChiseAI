#!/usr/bin/env python3
"""
Mini BrainEval - Real Issue Detection from Iterlogs

SAFETY: No risk cap logic modified
SAFETY: No promotion gate logic modified
SAFETY: No live trading flow modified

This script scans docs/tempmemories/*.md files for real issues and generates
evaluation reports with detected patterns, severity classification, and
suggested mitigations.
"""

import argparse
import json
import os
import re
import uuid
import yaml
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
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
    # Structured issue fields
    root_cause: Optional[str] = None
    fix_applied: Optional[str] = None
    time_lost_minutes: Optional[int] = None
    recurrence_hint: Optional[str] = None
    impact_area: Optional[str] = None
    resolved: Optional[bool] = None
    is_structured: bool = False  # Flag to indicate structured vs regex


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


class IssueDetector:
    """Detects issues from iterlog files."""

    # Issue patterns to search for
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

    def scan_files(self) -> List[Issue]:
        """Scan all markdown files in tempmemories for issues."""
        self.issues = []

        if not self.tempmemories_path.exists():
            print(f"Warning: Path {self.tempmemories_path} does not exist")
            return self.issues

        md_files = list(self.tempmemories_path.glob("*.md"))

        for file_path in md_files:
            self._scan_file(file_path)

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

        # FIRST: Try to parse structured issues
        structured_issues = self._scan_structured_issues(content, file_path, timestamp)
        if structured_issues:
            self.issues.extend(structured_issues)
            return  # Use structured issues only, skip regex

        # FALLBACK: Use regex patterns if no structured section found
        for line_num, line in enumerate(lines, 1):
            for issue_type, config in self.PATTERNS.items():
                for pattern in config["patterns"]:
                    if re.search(pattern, line, re.IGNORECASE):
                        # Get context (surrounding lines)
                        context_start = max(0, line_num - 2)
                        context_end = min(len(lines), line_num + 1)
                        context = "\n".join(lines[context_start:context_end])

                        issue = Issue(
                            issue_type=issue_type,
                            severity=config["severity"],
                            description=line.strip(),
                            source_file=str(file_path),
                            timestamp=timestamp,
                            line_number=line_num,
                            context=context.strip(),
                            is_structured=False,
                        )
                        self.issues.append(issue)
                        break  # Avoid duplicate detection for same line

    def _scan_structured_issues(
        self, content: str, file_path: Path, timestamp: Optional[str]
    ) -> List[Issue]:
        """Parse structured issues from markdown YAML section.

        Returns empty list if no structured section or parsing fails.
        """
        issues: List[Issue] = []

        # Find ## Structured Issues section
        structured_match = re.search(
            r"^##\s+Structured\s+Issues\s*\n(.*?)(?=^##\s|\Z)",
            content,
            re.MULTILINE | re.DOTALL,
        )

        if not structured_match:
            return issues  # No structured section found

        yaml_content = structured_match.group(1).strip()

        try:
            parsed = yaml.safe_load(yaml_content)
            if not parsed or not isinstance(parsed, dict):
                return issues

            issues_list = parsed.get("issues", [])
            if not issues_list:
                return issues  # Empty issues list

            for item in issues_list:
                if not isinstance(item, dict):
                    continue

                # Map severity from structured fields or infer from issue_type
                issue_type = item.get("issue_type", "unknown")
                severity = self._infer_severity(issue_type, item.get("resolved", False))

                # Build description from structured fields
                description_parts = []
                if item.get("root_cause"):
                    description_parts.append(f"Root cause: {item['root_cause']}")
                if item.get("fix_applied"):
                    description_parts.append(f"Fix: {item['fix_applied']}")
                description = "; ".join(description_parts) or issue_type

                issue = Issue(
                    issue_type=issue_type,
                    severity=severity,
                    description=description,
                    source_file=str(file_path),
                    timestamp=timestamp,
                    line_number=None,  # Structured issues don't have line numbers
                    context="",  # Structured issues don't have surrounding context
                    root_cause=item.get("root_cause"),
                    fix_applied=item.get("fix_applied"),
                    time_lost_minutes=item.get("time_lost_minutes"),
                    recurrence_hint=item.get("recurrence_hint"),
                    impact_area=item.get("impact_area"),
                    resolved=item.get("resolved"),
                    is_structured=True,
                )
                issues.append(issue)

        except yaml.YAMLError as e:
            print(f"Warning: Failed to parse structured issues in {file_path}: {e}")
            return []  # Return empty on parse error, will fallback to regex

        return issues

    def _infer_severity(self, issue_type: str, resolved: bool) -> str:
        """Infer severity from issue_type and resolved status."""
        # Check if issue_type matches known patterns
        for pattern_type, config in self.PATTERNS.items():
            if pattern_type == issue_type:
                # Reduce severity if resolved
                if resolved:
                    severity_order = ["P0", "P1", "P2", "P3"]
                    idx = severity_order.index(config["severity"])
                    return severity_order[min(idx + 1, 3)]
                return config["severity"]

        # Default severity based on common patterns
        if "blocker" in issue_type.lower():
            return "P0"
        if "failure" in issue_type.lower() or "error" in issue_type.lower():
            return "P1"
        if "warning" in issue_type.lower() or "slow" in issue_type.lower():
            return "P2"
        return "P3"

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
            mitigation = {
                "issue_type": issue_type,
                "count": len(issues),
                "severity": config.get("severity", "P3"),
                "suggestion": config.get("mitigation", "Review and address the issue."),
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
        }


def run_evaluation(
    cadence: str, output_dir: str = "_bmad-output/brain-eval"
) -> MiniEvalResult:
    """Run a complete evaluation for the specified cadence."""

    detector = IssueDetector()
    issues = detector.scan_files()
    mitigations = detector.get_mitigations()
    file_stats = detector.get_file_stats()

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

    result = MiniEvalResult(
        eval_id=str(uuid.uuid4()),
        timestamp=datetime.utcnow().isoformat() + "Z",
        cadence=cadence,
        issues_found=[asdict(issue) for issue in issues],
        mitigations=mitigations,
        file_stats=file_stats,
        summary="; ".join(summary_parts),
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


if __name__ == "__main__":
    main()
