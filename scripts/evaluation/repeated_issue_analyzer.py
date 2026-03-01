#!/usr/bin/env python3
"""
Repeated Issue Analyzer - Cluster recurring issues across evaluations

SAFETY: No risk cap logic modified
SAFETY: No promotion gate logic modified
SAFETY: No live trading flow modified

This script reads all BrainEval JSON results and groups issues by normalized
descriptions to identify recurring patterns.
"""

import json
import hashlib
import re
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class IssueCluster:
    """A cluster of similar issues."""

    cluster_id: str
    normalized_description: str
    issue_type: str
    severity: str
    count: int
    first_seen: str
    last_seen: str
    occurrences: List[Dict[str, Any]]
    source_files: List[str]
    trend: str  # increasing, decreasing, stable


class RepeatedIssueAnalyzer:
    """Analyzes BrainEval results to find repeated issues."""

    def __init__(self, eval_dir: str = "_bmad-output/brain-eval"):
        self.eval_dir = Path(eval_dir)
        self.clusters: Dict[str, IssueCluster] = {}

    def normalize_description(self, description: str) -> str:
        """Normalize an issue description for clustering."""
        # Convert to lowercase
        normalized = description.lower()

        # Remove timestamps (YYYY-MM-DD, HH:MM:SS, etc.)
        normalized = re.sub(r"\d{4}-\d{2}-\d{2}", "[DATE]", normalized)
        normalized = re.sub(r"\d{2}:\d{2}:\d{2}", "[TIME]", normalized)

        # Remove line numbers
        normalized = re.sub(r"line \d+", "line [N]", normalized)
        normalized = re.sub(r":\d+:", ":[N]:", normalized)

        # Remove specific file paths (keep filename)
        normalized = re.sub(r"[\w\-/]+/([\w\-]+\.\w+)", r"[PATH]/\1", normalized)

        # Remove UUIDs
        normalized = re.sub(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            "[UUID]",
            normalized,
        )

        # Remove specific numbers (keep context)
        normalized = re.sub(r"\b\d+\b", "[N]", normalized)

        # Remove extra whitespace
        normalized = " ".join(normalized.split())

        return normalized

    def generate_cluster_id(self, normalized_desc: str, issue_type: str) -> str:
        """Generate a unique ID for a cluster."""
        content = f"{issue_type}:{normalized_desc}"
        return hashlib.md5(content.encode()).hexdigest()[:12]

    def load_all_evaluations(self) -> List[Dict[str, Any]]:
        """Load all evaluation JSON files."""
        evaluations = []

        if not self.eval_dir.exists():
            print(f"Warning: Directory {self.eval_dir} does not exist")
            return evaluations

        # Look for JSON files in all cadence subdirectories
        for json_file in self.eval_dir.rglob("*.json"):
            if json_file.name == "repeated_issues_report.json":
                continue  # Skip our own output

            try:
                with open(json_file, "r") as f:
                    data = json.load(f)
                    data["_source_file"] = str(json_file)
                    evaluations.append(data)
            except Exception as e:
                print(f"Error loading {json_file}: {e}")

        return evaluations

    def cluster_issues(
        self, evaluations: List[Dict[str, Any]]
    ) -> Dict[str, IssueCluster]:
        """Group issues into clusters."""
        self.clusters = {}

        for eval_data in evaluations:
            eval_timestamp = eval_data.get("timestamp", "")
            eval_cadence = eval_data.get("cadence", "unknown")

            for issue in eval_data.get("issues_found", []):
                description = issue.get("description", "")
                normalized = self.normalize_description(description)
                issue_type = issue.get("issue_type", "unknown")
                severity = issue.get("severity", "P3")

                cluster_id = self.generate_cluster_id(normalized, issue_type)

                if cluster_id not in self.clusters:
                    self.clusters[cluster_id] = IssueCluster(
                        cluster_id=cluster_id,
                        normalized_description=normalized,
                        issue_type=issue_type,
                        severity=severity,
                        count=0,
                        first_seen=eval_timestamp,
                        last_seen=eval_timestamp,
                        occurrences=[],
                        source_files=[],
                        trend="stable",
                    )

                cluster = self.clusters[cluster_id]
                cluster.count += 1
                cluster.occurrences.append(
                    {
                        "timestamp": eval_timestamp,
                        "cadence": eval_cadence,
                        "original_description": description,
                        "source_file": issue.get("source_file", ""),
                        "line_number": issue.get("line_number"),
                    }
                )

                # Update source files
                source = issue.get("source_file", "")
                if source and source not in cluster.source_files:
                    cluster.source_files.append(source)

                # Update timestamps
                if eval_timestamp:
                    if eval_timestamp < cluster.first_seen:
                        cluster.first_seen = eval_timestamp
                    if eval_timestamp > cluster.last_seen:
                        cluster.last_seen = eval_timestamp

        # Calculate trends
        self._calculate_trends()

        return self.clusters

    def _calculate_trends(self) -> None:
        """Calculate trend (increasing/decreasing/stable) for each cluster."""
        for cluster in self.clusters.values():
            if len(cluster.occurrences) < 2:
                cluster.trend = "stable"
                continue

            # Sort by timestamp
            sorted_occurrences = sorted(
                cluster.occurrences, key=lambda x: x.get("timestamp", "")
            )

            # Simple trend: compare first half vs second half
            mid = len(sorted_occurrences) // 2
            first_half = len(sorted_occurrences[:mid])
            second_half = len(sorted_occurrences[mid:])

            if second_half > first_half * 1.5:
                cluster.trend = "increasing"
            elif second_half < first_half * 0.5:
                cluster.trend = "decreasing"
            else:
                cluster.trend = "stable"

    def generate_report(self) -> Dict[str, Any]:
        """Generate the repeated issues report."""
        evaluations = self.load_all_evaluations()

        if not evaluations:
            return {
                "report_id": "empty",
                "generated_at": datetime.utcnow().isoformat() + "Z",
                "total_evaluations": 0,
                "total_clusters": 0,
                "clusters": [],
                "summary": "No evaluation data found",
            }

        clusters = self.cluster_issues(evaluations)

        # Sort clusters by count (most frequent first)
        sorted_clusters = sorted(clusters.values(), key=lambda x: x.count, reverse=True)

        # Build report
        report = {
            "report_id": f"rir-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}",
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "total_evaluations": len(evaluations),
            "total_clusters": len(clusters),
            "total_issues": sum(c.count for c in clusters.values()),
            "clusters": [asdict(c) for c in sorted_clusters],
            "summary": self._generate_summary(sorted_clusters),
        }

        return report

    def _generate_summary(self, clusters: List[IssueCluster]) -> str:
        """Generate a human-readable summary."""
        if not clusters:
            return "No repeated issues found"

        total_issues = sum(c.count for c in clusters)
        top_issues = clusters[:5]

        parts = [
            f"Found {len(clusters)} unique issue patterns from {total_issues} total occurrences"
        ]

        # Count by trend
        increasing = sum(1 for c in clusters if c.trend == "increasing")
        decreasing = sum(1 for c in clusters if c.trend == "decreasing")

        if increasing > 0:
            parts.append(f"{increasing} issues are increasing in frequency")
        if decreasing > 0:
            parts.append(f"{decreasing} issues are decreasing in frequency")

        parts.append(
            f"Top issue: '{clusters[0].normalized_description[:50]}...' ({clusters[0].count} occurrences)"
        )

        return "; ".join(parts)

    def save_report(
        self, report: Dict[str, Any], output_path: Optional[str] = None
    ) -> str:
        """Save the report to a file."""
        if output_path is None:
            output_path = self.eval_dir / "repeated_issues_report.json"

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)

        return str(output_path)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Analyze BrainEval results for repeated issues"
    )
    parser.add_argument(
        "--eval-dir",
        default="_bmad-output/brain-eval",
        help="Directory containing BrainEval JSON files",
    )
    parser.add_argument(
        "--output",
        default="_bmad-output/brain-eval/repeated_issues_report.json",
        help="Output file path",
    )

    args = parser.parse_args()

    analyzer = RepeatedIssueAnalyzer(args.eval_dir)
    report = analyzer.generate_report()
    output_path = analyzer.save_report(report, args.output)

    print(f"Report saved to: {output_path}")
    print(f"\n{'=' * 60}")
    print("Repeated Issues Analysis")
    print(f"{'=' * 60}")
    print(f"Total Evaluations: {report['total_evaluations']}")
    print(f"Total Clusters: {report['total_clusters']}")
    print(f"Total Issues: {report['total_issues']}")
    print(f"\nSummary: {report['summary']}")

    if report["clusters"]:
        print(f"\nTop 5 Repeated Issues:")
        for i, cluster in enumerate(report["clusters"][:5], 1):
            print(
                f"  {i}. [{cluster['severity']}] {cluster['issue_type']}: "
                f"{cluster['normalized_description'][:50]}... "
                f"({cluster['count']}x, {cluster['trend']})"
            )


if __name__ == "__main__":
    main()
