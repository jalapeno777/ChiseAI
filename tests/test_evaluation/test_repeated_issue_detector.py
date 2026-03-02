"""Tests for repeated issue detection and fingerprinting.

# SAFETY: No risk cap logic modified
# SAFETY: No promotion gate logic modified
# SAFETY: No live trading flow modified
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from evaluation.fingerprinting import (
    FingerprintCluster,
    FingerprintClusterer,
    IssueFingerprint,
)
from evaluation.repeated_issue_detector import (
    IssueCluster,
    RepeatedIssueDetector,
    RepeatedIssueReport,
    TrendAnalysis,
)
from evaluation.schemas.mini_eval import Issue, IssueCategory, IssueSeverity


class TestIssueFingerprint:
    """Tests for IssueFingerprint class."""

    def test_generate_creates_consistent_fingerprint(self) -> None:
        """Test that same issue generates same fingerprint."""
        issue = Issue.create(
            category=IssueCategory.DB_CONNECTIVITY,
            severity=IssueSeverity.P1,
            description="Redis connection timeout",
            source="test",
        )

        fp1 = IssueFingerprint.generate(issue)
        fp2 = IssueFingerprint.generate(issue)

        assert fp1 == fp2
        assert fp1.startswith("db_connectivity:")

    def test_generate_different_issues_different_fingerprints(self) -> None:
        """Test that different issues generate different fingerprints."""
        issue1 = Issue.create(
            category=IssueCategory.DB_CONNECTIVITY,
            severity=IssueSeverity.P1,
            description="Redis connection timeout",
            source="test",
        )
        issue2 = Issue.create(
            category=IssueCategory.FILE_ACCESS,
            severity=IssueSeverity.P2,
            description="File not found",
            source="test",
        )

        fp1 = IssueFingerprint.generate(issue1)
        fp2 = IssueFingerprint.generate(issue2)

        assert fp1 != fp2

    def test_normalize_description_removes_timestamps(self) -> None:
        """Test timestamp normalization."""
        desc = "Error occurred at 2026-03-01T12:00:00Z in module"
        normalized = IssueFingerprint.normalize_description(desc)

        assert "<timestamp>" in normalized.lower()
        assert "2026-03-01" not in normalized

    def test_normalize_description_removes_uuids(self) -> None:
        """Test UUID normalization."""
        desc = "Session a1b2c3d4-e5f6-7890-abcd-ef1234567890 failed"
        normalized = IssueFingerprint.normalize_description(desc)

        assert "<uuid>" in normalized.lower()
        assert "a1b2c3d4" not in normalized

    def test_normalize_description_keeps_filenames(self) -> None:
        """Test that file paths are reduced to filenames."""
        desc = "Error in /path/to/file.py at line 42"
        normalized = IssueFingerprint.normalize_description(desc)

        assert "file.py" in normalized
        assert "/path/to/" not in normalized

    def test_normalize_description_removes_line_numbers(self) -> None:
        """Test line number normalization."""
        desc = "Error at file.py:123 in module"
        normalized = IssueFingerprint.normalize_description(desc)

        assert "<line>" in normalized.lower()
        assert ":123" not in normalized

    def test_normalize_description_removes_pids(self) -> None:
        """Test PID normalization."""
        desc = "Process pid=12345 crashed"
        normalized = IssueFingerprint.normalize_description(desc)

        # After normalization, either <pid> placeholder or no pid text
        assert "<pid>" in normalized.lower() or "12345" not in normalized

    def test_normalize_description_removes_memory_addresses(self) -> None:
        """Test memory address normalization."""
        desc = "Access violation at 0x7fff12345678"
        normalized = IssueFingerprint.normalize_description(desc)

        assert "<addr>" in normalized.lower()
        assert "0x7fff" not in normalized

    def test_normalize_description_removes_ip_addresses(self) -> None:
        """Test IP address normalization."""
        desc = "Connection to 192.168.1.1 failed"
        normalized = IssueFingerprint.normalize_description(desc)

        assert "<ip>" in normalized.lower()
        assert "192.168" not in normalized

    def test_cluster_groups_identical_fingerprints(self) -> None:
        """Test clustering of identical fingerprints."""
        fingerprints = [
            "db_connectivity:abc123",
            "db_connectivity:abc123",
            "file_access:def456",
            "db_connectivity:abc123",
        ]

        clusters = IssueFingerprint.cluster(fingerprints)

        assert len(clusters) == 2
        assert len(clusters["db_connectivity:abc123"]) == 3
        assert len(clusters["file_access:def456"]) == 1

    def test_extract_category(self) -> None:
        """Test category extraction from fingerprint."""
        fingerprint = "db_connectivity:abc123def456"
        category = IssueFingerprint.extract_category(fingerprint)

        assert category == "db_connectivity"

    def test_are_similar_exact_match(self) -> None:
        """Test similarity detection with exact match."""
        assert IssueFingerprint.are_similar("cat:abc", "cat:abc") is True
        assert IssueFingerprint.are_similar("cat:abc", "cat:def") is False


class TestFingerprintCluster:
    """Tests for FingerprintCluster dataclass."""

    def test_add_occurrence_increments_count(self) -> None:
        """Test that add_occurrence increments count."""
        cluster = FingerprintCluster(fingerprint="test:abc", category="test")

        cluster.add_occurrence("desc1")
        cluster.add_occurrence("desc2")

        assert cluster.count == 2
        assert len(cluster.descriptions) == 2

    def test_get_variants_returns_unique_descriptions(self) -> None:
        """Test getting unique description variants."""
        cluster = FingerprintCluster(fingerprint="test:abc", category="test")

        cluster.add_occurrence("desc1")
        cluster.add_occurrence("desc1")  # Duplicate
        cluster.add_occurrence("desc2")

        variants = cluster.get_variants()

        assert len(variants) == 2
        assert "desc1" in variants
        assert "desc2" in variants


class TestFingerprintClusterer:
    """Tests for FingerprintClusterer class."""

    def test_add_issue_creates_cluster(self) -> None:
        """Test that adding an issue creates a cluster."""
        clusterer = FingerprintClusterer()
        issue = Issue.create(
            category=IssueCategory.DB_CONNECTIVITY,
            severity=IssueSeverity.P1,
            description="Redis timeout",
            source="test",
        )

        fingerprint = clusterer.add_issue(issue)

        assert fingerprint in clusterer.clusters
        assert clusterer.clusters[fingerprint].count == 1

    def test_get_clusters_sorted_by_count(self) -> None:
        """Test that clusters are sorted by count descending."""
        clusterer = FingerprintClusterer()

        # Add multiple issues
        for _ in range(3):
            issue = Issue.create(
                category=IssueCategory.DB_CONNECTIVITY,
                severity=IssueSeverity.P1,
                description="Redis timeout",
                source="test",
            )
            clusterer.add_issue(issue)

        for _ in range(1):
            issue = Issue.create(
                category=IssueCategory.FILE_ACCESS,
                severity=IssueSeverity.P2,
                description="File not found",
                source="test",
            )
            clusterer.add_issue(issue)

        clusters = clusterer.get_clusters()

        assert len(clusters) == 2
        assert clusters[0].count == 3
        assert clusters[1].count == 1

    def test_get_repeated_clusters_filters_by_count(self) -> None:
        """Test filtering clusters by minimum count."""
        clusterer = FingerprintClusterer()

        # Add issues - one repeated, one single
        for _ in range(3):
            issue = Issue.create(
                category=IssueCategory.DB_CONNECTIVITY,
                severity=IssueSeverity.P1,
                description="Redis timeout",
                source="test",
            )
            clusterer.add_issue(issue)

        issue = Issue.create(
            category=IssueCategory.FILE_ACCESS,
            severity=IssueSeverity.P2,
            description="File not found",
            source="test",
        )
        clusterer.add_issue(issue)

        repeated = clusterer.get_repeated_clusters(min_count=2)

        assert len(repeated) == 1
        assert repeated[0].count == 3

    def test_get_stats(self) -> None:
        """Test getting cluster statistics."""
        clusterer = FingerprintClusterer()

        for _ in range(5):
            issue = Issue.create(
                category=IssueCategory.DB_CONNECTIVITY,
                severity=IssueSeverity.P1,
                description="Redis timeout",
                source="test",
            )
            clusterer.add_issue(issue)

        stats = clusterer.get_stats()

        assert stats["total_issues"] == 5
        assert stats["unique_fingerprints"] == 1
        assert stats["repeated_clusters"] == 1


class TestIssueCluster:
    """Tests for IssueCluster dataclass."""

    def test_to_dict_roundtrip(self) -> None:
        """Test serialization roundtrip."""
        now = datetime.now(UTC)
        cluster = IssueCluster(
            fingerprint="test:abc",
            category="db_connectivity",
            count=5,
            first_seen=now - timedelta(hours=1),
            last_seen=now,
            examples=[{"issue_id": "1", "description": "test"}],
            severity_trend="stable",
        )

        data = cluster.to_dict()
        restored = IssueCluster.from_dict(data)

        assert restored.fingerprint == cluster.fingerprint
        assert restored.count == cluster.count
        assert restored.severity_trend == cluster.severity_trend


class TestTrendAnalysis:
    """Tests for TrendAnalysis dataclass."""

    def test_to_dict_roundtrip(self) -> None:
        """Test serialization roundtrip."""
        analysis = TrendAnalysis(
            issues_by_hour={"2026-03-01T12": 5, "2026-03-01T13": 3},
            categories_trend={"db_connectivity": {"count": 5}},
            severity_distribution={"P1": 5, "P2": 3},
            time_range_hours=24,
        )

        data = analysis.to_dict()
        restored = TrendAnalysis.from_dict(data)

        assert restored.issues_by_hour == analysis.issues_by_hour
        assert restored.time_range_hours == analysis.time_range_hours


class TestRepeatedIssueReport:
    """Tests for RepeatedIssueReport dataclass."""

    def test_to_dict_roundtrip(self) -> None:
        """Test serialization roundtrip."""
        now = datetime.now(UTC)
        cluster = IssueCluster(
            fingerprint="test:abc",
            category="db_connectivity",
            count=5,
            first_seen=now - timedelta(hours=1),
            last_seen=now,
        )
        trend = TrendAnalysis(
            issues_by_hour={"2026-03-01T12": 5},
            time_range_hours=24,
        )

        report = RepeatedIssueReport(
            generated_at=now,
            time_window_hours=24,
            total_issues=10,
            unique_issues=3,
            repeated_issues=[cluster],
            top_recurring=[cluster],
            recommendations=["Fix this"],
            trend_analysis=trend,
        )

        data = report.to_dict()
        restored = RepeatedIssueReport.from_dict(data)

        assert restored.total_issues == report.total_issues
        assert restored.unique_issues == report.unique_issues
        assert len(restored.repeated_issues) == 1

    def test_str_output(self) -> None:
        """Test string representation."""
        now = datetime.now(UTC)
        cluster = IssueCluster(
            fingerprint="test:abc",
            category="db_connectivity",
            count=5,
            first_seen=now - timedelta(hours=1),
            last_seen=now,
        )

        report = RepeatedIssueReport(
            generated_at=now,
            time_window_hours=24,
            total_issues=10,
            unique_issues=3,
            repeated_issues=[cluster],
            top_recurring=[cluster],
        )

        output = str(report)

        assert "Repeated Issue Report" in output
        assert "Total Issues: 10" in output
        assert "db_connectivity" in output


class TestRepeatedIssueDetector:
    """Tests for RepeatedIssueDetector class."""

    def test_detect_repeated_issues_empty(self) -> None:
        """Test detection with no issues."""
        mock_redis = MagicMock()
        mock_redis.scan.return_value = (0, [])  # No keys

        detector = RepeatedIssueDetector(redis_client=mock_redis)
        report = detector.detect_repeated_issues(time_window_hours=24)

        assert report.total_issues == 0
        assert report.unique_issues == 0
        assert len(report.repeated_issues) == 0

    def test_detect_repeated_issues_with_data(self) -> None:
        """Test detection with sample issues."""
        mock_redis = MagicMock()

        # Create sample evaluation result with repeated issues
        now = datetime.now(UTC)
        eval_result = {
            "eval_id": "test-1",
            "timestamp": now.isoformat(),
            "cadence": "6h",
            "issues": [
                {
                    "issue_id": "issue-1",
                    "category": "db_connectivity",
                    "severity": "P1",
                    "description": "Redis connection timeout at 2026-03-01T12:00:00Z",
                    "source": "test",
                    "timestamp": now.isoformat(),
                },
                {
                    "issue_id": "issue-2",
                    "category": "db_connectivity",
                    "severity": "P1",
                    "description": "Redis connection timeout at 2026-03-01T13:00:00Z",
                    "source": "test",
                    "timestamp": now.isoformat(),
                },
                {
                    "issue_id": "issue-3",
                    "category": "file_access",
                    "severity": "P2",
                    "description": "File not found: /path/to/file.txt",
                    "source": "test",
                    "timestamp": now.isoformat(),
                },
            ],
        }

        mock_redis.scan.return_value = (0, ["bmad:chiseai:brain:eval:mini:6h:test"])
        mock_redis.get.return_value = json.dumps(eval_result)

        detector = RepeatedIssueDetector(redis_client=mock_redis)
        report = detector.detect_repeated_issues(time_window_hours=24)

        assert report.total_issues == 3
        assert (
            report.unique_issues == 2
        )  # db_connectivity issues should cluster together
        assert len(report.repeated_issues) == 1  # db_connectivity is repeated

    def test_generate_recommendations_db_connectivity(self) -> None:
        """Test recommendation generation for DB issues."""
        detector = RepeatedIssueDetector()

        clusters = [
            IssueCluster(
                fingerprint="db:abc",
                category="db_connectivity",
                count=10,
                first_seen=datetime.now(UTC),
                last_seen=datetime.now(UTC),
            )
        ]

        recommendations = detector._generate_recommendations(clusters)

        assert any("connection pooling" in r.lower() for r in recommendations)
        assert any("timeout" in r.lower() for r in recommendations)

    def test_generate_recommendations_env_slowdown(self) -> None:
        """Test recommendation generation for slowdown issues."""
        detector = RepeatedIssueDetector()

        clusters = [
            IssueCluster(
                fingerprint="env:abc",
                category="env_slowdown",
                count=10,
                first_seen=datetime.now(UTC),
                last_seen=datetime.now(UTC),
            )
        ]

        recommendations = detector._generate_recommendations(clusters)

        assert any("resource" in r.lower() for r in recommendations)
        assert any("memory" in r.lower() for r in recommendations)

    def test_calculate_severity_trend_improving(self) -> None:
        """Test severity trend calculation - improving."""
        detector = RepeatedIssueDetector()

        # P0 -> P3 (getting better)
        severities = ["P0", "P0", "P1", "P2", "P3", "P3"]
        trend = detector._calculate_severity_trend(severities)

        assert trend == "improving"

    def test_calculate_severity_trend_worsening(self) -> None:
        """Test severity trend calculation - worsening."""
        detector = RepeatedIssueDetector()

        # P3 -> P0 (getting worse)
        severities = ["P3", "P3", "P2", "P1", "P0", "P0"]
        trend = detector._calculate_severity_trend(severities)

        assert trend == "worsening"

    def test_calculate_severity_trend_stable(self) -> None:
        """Test severity trend calculation - stable."""
        detector = RepeatedIssueDetector()

        # Truly stable - same severity throughout
        severities = ["P2", "P2", "P2", "P2", "P2", "P2"]
        trend = detector._calculate_severity_trend(severities)

        assert trend == "stable"

    def test_store_report(self) -> None:
        """Test report storage in Redis."""
        mock_redis = MagicMock()

        report = RepeatedIssueReport(
            generated_at=datetime.now(UTC),
            time_window_hours=24,
            total_issues=10,
            unique_issues=3,
        )

        detector = RepeatedIssueDetector(redis_client=mock_redis)
        detector._store_report(report)

        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        assert "bmad:chiseai:brain:eval:repeated_issues:" in call_args[0][0]

    def test_get_recent_reports(self) -> None:
        """Test retrieving recent reports."""
        mock_redis = MagicMock()

        report = RepeatedIssueReport(
            generated_at=datetime.now(UTC),
            time_window_hours=24,
            total_issues=10,
            unique_issues=3,
        )

        mock_redis.scan.return_value = (
            0,
            ["bmad:chiseai:brain:eval:repeated_issues:test"],
        )
        mock_redis.get.return_value = report.to_json()

        detector = RepeatedIssueDetector(redis_client=mock_redis)
        reports = detector.get_recent_reports(limit=5)

        assert len(reports) == 1
        assert reports[0].total_issues == 10

    def test_get_report_by_id(self) -> None:
        """Test retrieving specific report by ID."""
        mock_redis = MagicMock()

        report = RepeatedIssueReport(
            generated_at=datetime.now(UTC),
            time_window_hours=24,
            total_issues=10,
            unique_issues=3,
        )

        mock_redis.get.return_value = report.to_json()

        detector = RepeatedIssueDetector(redis_client=mock_redis)
        result = detector.get_report_by_id("20260301_120000")

        assert result is not None
        assert result.total_issues == 10


class TestIntegrationWithBatch1:
    """Integration tests using Batch 1 patterns."""

    def test_fingerprinting_with_batch1_issues(self) -> None:
        """Test fingerprinting with realistic Batch 1 style issues."""
        issues = [
            Issue.create(
                category=IssueCategory.DB_CONNECTIVITY,
                severity=IssueSeverity.P1,
                description="Redis connection timeout at 2026-03-01T06:00:00Z",
                source="MiniBrainEval.run_6h_eval",
            ),
            Issue.create(
                category=IssueCategory.DB_CONNECTIVITY,
                severity=IssueSeverity.P1,
                description="Redis connection timeout at 2026-03-01T12:00:00Z",
                source="MiniBrainEval.run_6h_eval",
            ),
            Issue.create(
                category=IssueCategory.DB_CONNECTIVITY,
                severity=IssueSeverity.P1,
                description="Redis connection timeout at 2026-03-01T18:00:00Z",
                source="MiniBrainEval.run_6h_eval",
            ),
            Issue.create(
                category=IssueCategory.ENV_SLOWDOWN,
                severity=IssueSeverity.P2,
                description="High memory usage during evaluation at pid 12345",
                source="MiniBrainEval._collect_proxy_metrics",
            ),
            Issue.create(
                category=IssueCategory.ENV_SLOWDOWN,
                severity=IssueSeverity.P2,
                description="High memory usage during evaluation at pid 12346",
                source="MiniBrainEval._collect_proxy_metrics",
            ),
        ]

        clusterer = FingerprintClusterer()
        for issue in issues:
            clusterer.add_issue(issue)

        clusters = clusterer.get_clusters()

        # Should have 2 clusters (db_connectivity and env_slowdown)
        assert len(clusters) == 2

        # db_connectivity should have 3 occurrences
        db_cluster = next(c for c in clusters if c.category == "db_connectivity")
        assert db_cluster.count == 3

        # env_slowdown should have 2 occurrences
        env_cluster = next(c for c in clusters if c.category == "env_slowdown")
        assert env_cluster.count == 2

    def test_normalization_consistency(self) -> None:
        """Test that similar issues get normalized to same description."""
        descriptions = [
            "Redis connection timeout at 2026-03-01T06:00:00Z",
            "Redis connection timeout at 2026-03-01T12:00:00Z",
            "Redis connection timeout at 2026-03-01T18:00:00Z",
        ]

        normalized = [IssueFingerprint.normalize_description(d) for d in descriptions]

        # All should normalize to the same thing
        assert len(set(normalized)) == 1
        assert "<timestamp>" in normalized[0].lower()

    def test_end_to_end_detection(self) -> None:
        """Test end-to-end repeated issue detection."""
        mock_redis = MagicMock()

        # Simulate Batch 1 data
        now = datetime.now(UTC)
        eval_results = [
            {
                "eval_id": f"eval-{i}",
                "timestamp": (now - timedelta(hours=i * 6)).isoformat(),
                "cadence": "6h",
                "issues": [
                    {
                        "issue_id": f"issue-{i}-1",
                        "category": "db_connectivity",
                        "severity": "P1",
                        "description": f"Redis connection timeout at {(now - timedelta(hours=i * 6)).isoformat()}",
                        "source": "test",
                        "timestamp": (now - timedelta(hours=i * 6)).isoformat(),
                    }
                ],
            }
            for i in range(5)
        ]

        keys = [f"bmad:chiseai:brain:eval:mini:6h:eval-{i}" for i in range(5)]
        mock_redis.scan.return_value = (0, keys)

        # Mock get to return different results for each key
        def mock_get(key):
            for i, k in enumerate(keys):
                if k == key:
                    return json.dumps(eval_results[i])
            return None

        mock_redis.get.side_effect = mock_get

        detector = RepeatedIssueDetector(redis_client=mock_redis)
        report = detector.detect_repeated_issues(time_window_hours=48)

        # Should detect 5 issues, all clustered as 1 unique type
        assert report.total_issues == 5
        assert report.unique_issues == 1
        assert len(report.repeated_issues) == 1
        assert report.repeated_issues[0].count == 5

    def test_report_str_format(self) -> None:
        """Test report string formatting."""
        now = datetime.now(UTC)

        # Create a report with Batch 1 style data
        cluster = IssueCluster(
            fingerprint="db_connectivity:abc123",
            category="db_connectivity",
            count=15,
            first_seen=now - timedelta(hours=12),
            last_seen=now,
            examples=[
                {
                    "issue_id": "ex-1",
                    "description": "Redis connection timeout",
                    "timestamp": now.isoformat(),
                    "severity": "P1",
                }
            ],
            severity_trend="stable",
        )

        report = RepeatedIssueReport(
            generated_at=now,
            time_window_hours=24,
            total_issues=45,
            unique_issues=12,
            repeated_issues=[cluster],
            top_recurring=[cluster],
            recommendations=["Consider Redis connection pool tuning"],
        )

        output = str(report)

        # Verify expected sections are present
        assert "Repeated Issue Report (Last 24h)" in output
        assert "Total Issues: 45" in output
        assert "Unique Issues: 12" in output
        assert "db_connectivity" in output
        assert "15 occurrences" in output
        assert "Recommendations:" in output
