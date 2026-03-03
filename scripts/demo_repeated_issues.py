#!/usr/bin/env python3
"""Demo script for repeated issue detection system.

# SAFETY: No risk cap logic modified
# SAFETY: No promotion gate logic modified
# SAFETY: No live trading flow modified

This script demonstrates the repeated issue detection and aggregation
system with sample data similar to Batch 1 evaluation results.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.evaluation.fingerprinting import FingerprintClusterer, IssueFingerprint
from src.evaluation.repeated_issue_detector import RepeatedIssueDetector
from src.evaluation.schemas.mini_eval import Issue, IssueCategory, IssueSeverity


def create_sample_issues():
    """Create sample issues similar to Batch 1 data."""
    now = datetime.now(UTC)

    issues = (
        [
            # Repeated DB connectivity issues (15 occurrences)
            Issue.create(
                category=IssueCategory.DB_CONNECTIVITY,
                severity=IssueSeverity.P1,
                description=f"Redis connection timeout at {(now - timedelta(hours=i * 2)).isoformat()}",
                source="MiniBrainEval.run_6h_eval",
            )
            for i in range(15)
        ]
        + [
            # Repeated env slowdown issues (8 occurrences)
            Issue.create(
                category=IssueCategory.ENV_SLOWDOWN,
                severity=IssueSeverity.P2,
                description=f"High memory usage during evaluation at pid {10000 + i}",
                source="MiniBrainEval._collect_proxy_metrics",
            )
            for i in range(8)
        ]
        + [
            # Single file access issue
            Issue.create(
                category=IssueCategory.FILE_ACCESS,
                severity=IssueSeverity.P2,
                description="File not found: /tmp/test_file.txt",
                source="MiniBrainEval.run_6h_eval",
            ),
            # Single tool error
            Issue.create(
                category=IssueCategory.TOOL_ERROR,
                severity=IssueSeverity.P1,
                description="MCP tool execution failed: timeout after 30s",
                source="MiniBrainEval.run_6h_eval",
            ),
        ]
    )

    return issues


def demo_fingerprinting():
    """Demonstrate fingerprinting capabilities."""
    print("=" * 60)
    print("FINGERPRINTING DEMO")
    print("=" * 60)

    # Create sample issues
    issues = create_sample_issues()

    # Show fingerprint generation
    print("\n1. Fingerprint Generation:")
    print("-" * 40)

    sample_issue = issues[0]
    fingerprint = IssueFingerprint.generate(sample_issue)
    print(f"Issue: {sample_issue.description}")
    print(f"Category: {sample_issue.category}")
    print(f"Fingerprint: {fingerprint}")

    # Show normalization
    print("\n2. Description Normalization:")
    print("-" * 40)

    test_descriptions = [
        "Error at 2026-03-01T12:00:00Z in /path/to/file.py:123",
        "Session a1b2c3d4-e5f6-7890-abcd-ef1234567890 failed",
        "Memory access violation at 0x7fff12345678",
        "Connection to 192.168.1.1:8080 refused",
    ]

    for desc in test_descriptions:
        normalized = IssueFingerprint.normalize_description(desc)
        print(f"Original:     {desc}")
        print(f"Normalized:   {normalized}")
        print()


def demo_clustering():
    """Demonstrate issue clustering."""
    print("=" * 60)
    print("CLUSTERING DEMO")
    print("=" * 60)

    issues = create_sample_issues()
    clusterer = FingerprintClusterer()

    print(f"\nClustering {len(issues)} issues...")

    for issue in issues:
        clusterer.add_issue(issue)

    clusters = clusterer.get_clusters()
    stats = clusterer.get_stats()

    print("\nClustering Results:")
    print(f"  Total issues: {stats['total_issues']}")
    print(f"  Unique fingerprints: {stats['unique_fingerprints']}")
    print(f"  Repeated clusters: {stats['repeated_clusters']}")
    print(f"  Single occurrences: {stats['single_occurrences']}")

    print("\nTop Clusters:")
    print("-" * 40)
    for i, cluster in enumerate(clusters[:5], 1):
        print(f"{i}. [{cluster.category}] {cluster.count} occurrences")


def demo_repeated_issue_detection():
    """Demonstrate repeated issue detection with mock Redis data."""
    print("\n" + "=" * 60)
    print("REPEATED ISSUE DETECTION DEMO")
    print("=" * 60)

    # Create mock Redis with sample evaluation data
    mock_redis = MagicMock()
    now = datetime.now(UTC)

    # Create evaluation results with repeated issues
    eval_results = []
    for hour in range(0, 48, 6):
        result = {
            "eval_id": f"eval-{hour}",
            "timestamp": (now - timedelta(hours=hour)).isoformat(),
            "cadence": "6h",
            "issues": [],
        }

        # Add some repeated issues
        if hour % 12 == 0:
            result["issues"].append(
                {
                    "issue_id": f"redis-issue-{hour}",
                    "category": "db_connectivity",
                    "severity": "P1",
                    "description": f"Redis connection timeout at {(now - timedelta(hours=hour)).isoformat()}",
                    "source": "MiniBrainEval.run_6h_eval",
                    "timestamp": (now - timedelta(hours=hour)).isoformat(),
                }
            )

        if hour % 18 == 0:
            result["issues"].append(
                {
                    "issue_id": f"mem-issue-{hour}",
                    "category": "env_slowdown",
                    "severity": "P2",
                    "description": f"High memory usage at pid {10000 + hour}",
                    "source": "MiniBrainEval._collect_proxy_metrics",
                    "timestamp": (now - timedelta(hours=hour)).isoformat(),
                }
            )

        eval_results.append(result)

    keys = [f"bmad:chiseai:brain:eval:mini:6h:eval-{i * 6}" for i in range(8)]
    mock_redis.scan.return_value = (0, keys)

    def mock_get(key):
        for i, k in enumerate(keys):
            if k == key:
                return json.dumps(eval_results[i])
        return None

    mock_redis.get.side_effect = mock_get

    # Run detection
    detector = RepeatedIssueDetector(redis_client=mock_redis)
    report = detector.detect_repeated_issues(time_window_hours=48)

    # Display report
    print(f"\n{report}")

    print("\nTrend Analysis:")
    print("-" * 40)
    if report.trend_analysis:
        print(
            f"Issues by hour: {len(report.trend_analysis.issues_by_hour)} time buckets"
        )
        print(f"Categories: {list(report.trend_analysis.categories_trend.keys())}")
        print(f"Severity distribution: {report.trend_analysis.severity_distribution}")


def main():
    """Run all demos."""
    print("\n")
    print("*" * 60)
    print("REPEATED ISSUE DETECTION SYSTEM DEMO")
    print("*" * 60)

    demo_fingerprinting()
    demo_clustering()
    demo_repeated_issue_detection()

    print("\n" + "=" * 60)
    print("DEMO COMPLETE")
    print("=" * 60)
    print("\nThe repeated issue detection system can:")
    print("  1. Generate fingerprints from issues with normalized descriptions")
    print("  2. Cluster similar issues together")
    print("  3. Detect repeated issues across evaluation runs")
    print("  4. Generate trend analysis and recommendations")
    print("  5. Store and retrieve reports from Redis")
    print()


if __name__ == "__main__":
    main()
