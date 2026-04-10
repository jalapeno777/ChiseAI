"""
Tests for audit_capture.py - Baseline Metrics Capture.

Tests for Phase 1 PoC 8-metric baseline capture with anti-gaming protections.

Acceptance Criteria:
- AC1: All 8 baseline metrics captured
- AC2: Redis keys use append-only pattern
- AC3: capture_hash SHA256 included
- AC4: Baseline TTL refreshed when < 7 days
- AC5: All 6 original metrics still work (regression)
"""

from unittest.mock import MagicMock, patch

# Import the module under test
from src.governance.memory.audit_capture import (
    BASELINE_TTL_SECONDS,
    MemoryHealthMetrics,
    MemoryHealthSummary,
    _capture_metric_to_redis,
    _compute_capture_hash,
    _parse_metric_entry,
    _refresh_ttl_if_needed,
    capture_baseline_metrics,
    capture_baseline_metrics_all,
    capture_fp_rate_baseline,
    capture_near_dup_rate_baseline,
    capture_recall_accuracy_baseline,
    get_memory_health_summary,
    get_memory_health_summary_all,
)


class TestCaptureHash:
    """Tests for SHA256 capture hash computation."""

    def test_compute_capture_hash_format(self):
        """SHA256 hash should be prefixed with 'sha256:'."""
        value = 0.85
        captured_at = "2026-04-09T12:00:00Z"
        result = _compute_capture_hash(value, captured_at)
        assert result.startswith("sha256:")

    def test_compute_capture_hash_deterministic(self):
        """Same inputs should produce same hash."""
        value = 0.65
        captured_at = "2026-04-09T12:00:00Z"
        hash1 = _compute_capture_hash(value, captured_at)
        hash2 = _compute_capture_hash(value, captured_at)
        assert hash1 == hash2

    def test_compute_capture_hash_different_values(self):
        """Different values should produce different hashes."""
        captured_at = "2026-04-09T12:00:00Z"
        hash1 = _compute_capture_hash(0.5, captured_at)
        hash2 = _compute_capture_hash(0.6, captured_at)
        assert hash1 != hash2


class TestParseMetricEntry:
    """Tests for metric entry parsing."""

    def test_parse_valid_entry(self):
        """Should parse a valid entry string."""
        entry = "0.85|sha256:abc123|7776000"
        result = _parse_metric_entry(entry)
        assert result is not None
        assert result["value"] == 0.85
        assert result["capture_hash"] == "sha256:abc123"
        assert result["ttl"] == 7776000

    def test_parse_invalid_entry_wrong_parts(self):
        """Should return None for entry with wrong number of parts."""
        entry = "0.85|abc123"
        result = _parse_metric_entry(entry)
        assert result is None

    def test_parse_invalid_entry_bad_value(self):
        """Should return None for entry with non-float value."""
        entry = "not_a_float|sha256:abc123|7776000"
        result = _parse_metric_entry(entry)
        assert result is None


class TestRefreshTTL:
    """Tests for TTL refresh logic."""

    @patch("src.governance.memory.audit_capture._get_redis_conn")
    def test_refresh_ttl_when_key_not_exists(self, mock_get_conn):
        """Should set TTL when key doesn't exist (TTL < 0)."""
        mock_redis = MagicMock()
        mock_redis.ttl.return_value = -1
        mock_get_conn.return_value = mock_redis

        result = _refresh_ttl_if_needed("test_key")

        assert result is True
        mock_redis.expire.assert_called_once_with("test_key", BASELINE_TTL_SECONDS)

    @patch("src.governance.memory.audit_capture._get_redis_conn")
    def test_refresh_ttl_when_below_threshold(self, mock_get_conn):
        """Should refresh TTL when current TTL < 7 days."""
        mock_redis = MagicMock()
        mock_redis.ttl.return_value = 86400  # 1 day
        mock_get_conn.return_value = mock_redis

        result = _refresh_ttl_if_needed("test_key")

        assert result is True
        mock_redis.expire.assert_called_once_with("test_key", BASELINE_TTL_SECONDS)

    @patch("src.governance.memory.audit_capture._get_redis_conn")
    def test_no_refresh_when_ttl_sufficient(self, mock_get_conn):
        """Should not refresh when TTL >= 7 days."""
        mock_redis = MagicMock()
        mock_redis.ttl.return_value = 8 * 24 * 60 * 60  # 8 days
        mock_get_conn.return_value = mock_redis

        result = _refresh_ttl_if_needed("test_key")

        assert result is False
        mock_redis.expire.assert_not_called()


class TestCaptureMetricToRedis:
    """Tests for capturing metrics to Redis with anti-gaming."""

    @patch("src.governance.memory.audit_capture._get_redis_conn")
    @patch("src.governance.memory.audit_capture._refresh_ttl_if_needed")
    def test_capture_creates_new_entry(self, mock_refresh, mock_get_conn):
        """Should create new entry with SHA256 hash."""
        mock_redis = MagicMock()
        mock_get_conn.return_value = mock_redis

        result = _capture_metric_to_redis("test_key", 0.85)

        assert result["value"] == 0.85
        assert "captured_at" in result
        assert result["capture_hash"].startswith("sha256:")
        assert result["ttl"] == BASELINE_TTL_SECONDS

    @patch("src.governance.memory.audit_capture._get_redis_conn")
    @patch("src.governance.memory.audit_capture._refresh_ttl_if_needed")
    def test_capture_uses_timestamp_as_field(self, mock_refresh, mock_get_conn):
        """Should use timestamp as field name for append-only behavior."""
        mock_redis = MagicMock()
        mock_get_conn.return_value = mock_redis

        timestamp = "2026-04-09T12:00:00Z"
        _capture_metric_to_redis("test_key", 0.85, captured_at=timestamp)

        # The field name should be the timestamp
        mock_redis.hset.assert_called_once()
        call_args = mock_redis.hset.call_args
        assert call_args[0][1] == timestamp


class TestAppendOnlyPattern:
    """Tests for append-only Redis pattern (AC2)."""

    @patch("src.governance.memory.audit_capture._get_redis_conn")
    @patch("src.governance.memory.audit_capture._refresh_ttl_if_needed")
    def test_second_capture_creates_new_entry(self, mock_refresh, mock_get_conn):
        """AC2: Second capture should create a NEW entry, not overwrite."""
        mock_redis = MagicMock()
        mock_get_conn.return_value = mock_redis

        # First capture
        _capture_metric_to_redis("test_key", 0.85, captured_at="2026-04-09T12:00:00Z")

        # Second capture with different timestamp
        _capture_metric_to_redis("test_key", 0.90, captured_at="2026-04-09T13:00:00Z")

        # Should have been called twice (two appends)
        assert mock_redis.hset.call_count == 2


class TestCaptureHashPresence:
    """Tests for capture_hash presence (AC3)."""

    @patch("src.governance.memory.audit_capture._get_redis_conn")
    @patch("src.governance.memory.audit_capture._refresh_ttl_if_needed")
    def test_sha256_hash_included(self, mock_refresh, mock_get_conn):
        """AC3: capture_hash field should be present and start with sha256:."""
        mock_redis = MagicMock()
        mock_get_conn.return_value = mock_redis

        result = _capture_metric_to_redis("test_key", 0.65)

        assert "capture_hash" in result
        assert result["capture_hash"].startswith("sha256:")
        # Verify it's a proper SHA256 hex string (64 chars after prefix)
        hex_part = result["capture_hash"].replace("sha256:", "")
        assert len(hex_part) == 64


class TestTTLRefresh:
    """Tests for TTL refresh behavior (AC4)."""

    @patch("src.governance.memory.audit_capture._get_redis_conn")
    @patch("src.governance.memory.audit_capture._refresh_ttl_if_needed")
    def test_ttl_refresh_called_on_capture(self, mock_refresh, mock_get_conn):
        """AC4: TTL refresh should be called after each capture."""
        mock_redis = MagicMock()
        mock_get_conn.return_value = mock_redis

        _capture_metric_to_redis("test_key", 0.85)

        mock_refresh.assert_called_once_with("test_key")


class Test8BaselineMetricsCapture:
    """Tests for all 8 baseline metrics (AC1)."""

    @patch("src.governance.memory.audit_capture._get_latest_metric_from_redis")
    def test_all_8_metrics_present(self, mock_get_latest):
        """AC1: All 8 baseline metrics should be captured."""
        # Setup mock to return values for all metrics
        mock_get_latest.side_effect = [
            {
                "value": 0.85,
                "captured_at": "2026-04-09T12:00:00Z",
                "capture_hash": "sha256:abc",
                "ttl": 7776000,
            },
            {
                "value": 1500.0,
                "captured_at": "2026-04-09T12:00:00Z",
                "capture_hash": "sha256:def",
                "ttl": 7776000,
            },
            {
                "value": 0.72,
                "captured_at": "2026-04-09T12:00:00Z",
                "capture_hash": "sha256:ghi",
                "ttl": 7776000,
            },
            {
                "value": 0.15,
                "captured_at": "2026-04-09T12:00:00Z",
                "capture_hash": "sha256:jkl",
                "ttl": 7776000,
            },
            {
                "value": 0.45,
                "captured_at": "2026-04-09T12:00:00Z",
                "capture_hash": "sha256:mno",
                "ttl": 7776000,
            },
            {
                "value": 0.90,
                "captured_at": "2026-04-09T12:00:00Z",
                "capture_hash": "sha256:pqr",
                "ttl": 7776000,
            },
            {
                "value": 0.05,
                "captured_at": "2026-04-09T12:00:00Z",
                "capture_hash": "sha256:stu",
                "ttl": 7776000,
            },
            {
                "value": 0.08,
                "captured_at": "2026-04-09T12:00:00Z",
                "capture_hash": "sha256:vwx",
                "ttl": 7776000,
            },
        ]

        result = capture_baseline_metrics_all()

        assert len(result) == 8
        expected_metrics = [
            "recall_accuracy",
            "context_cost",
            "dedup_effectiveness",
            "staleness",
            "compression_ratio",
            "coverage",
            "fp_rate",
            "near_dup_rate",
        ]
        for metric in expected_metrics:
            assert metric in result


class TestGetMemoryHealthSummaryAll:
    """Tests for get_memory_health_summary_all function."""

    @patch("src.governance.memory.audit_capture._get_latest_metric_from_redis")
    def test_returns_all_required_fields(self, mock_get_latest):
        """Should return dict with value, captured_at, capture_hash, ttl."""
        mock_get_latest.side_effect = [
            {
                "value": 0.85,
                "captured_at": "2026-04-09T12:00:00Z",
                "capture_hash": "sha256:abc",
                "ttl": 7776000,
            },
        ] * 8

        result = get_memory_health_summary_all()

        for metric_data in result.values():
            assert "value" in metric_data
            assert "captured_at" in metric_data
            assert "capture_hash" in metric_data
            assert "ttl" in metric_data


class TestSpecificCaptureFunctions:
    """Tests for individual metric capture functions."""

    @patch("src.governance.memory.audit_capture._capture_metric_to_redis")
    def test_capture_recall_accuracy(self, mock_capture):
        """Should call _capture_metric_to_redis with correct key."""
        mock_capture.return_value = {"value": 0.85}
        result = capture_recall_accuracy_baseline(0.85)
        mock_capture.assert_called_once_with(
            "bmad:chiseai:memory:baseline:recall_accuracy",
            0.85,
        )
        assert result["value"] == 0.85

    @patch("src.governance.memory.audit_capture._capture_metric_to_redis")
    def test_capture_fp_rate(self, mock_capture):
        """Should call _capture_metric_to_redis with fp_rate key."""
        mock_capture.return_value = {"value": 0.05}
        result = capture_fp_rate_baseline(0.05)
        mock_capture.assert_called_once_with(
            "bmad:chiseai:memory:baseline:fp_rate",
            0.05,
        )

    @patch("src.governance.memory.audit_capture._capture_metric_to_redis")
    def test_capture_near_dup_rate(self, mock_capture):
        """Should call _capture_metric_to_redis with near_dup_rate key."""
        mock_capture.return_value = {"value": 0.08}
        result = capture_near_dup_rate_baseline(0.08)
        mock_capture.assert_called_once_with(
            "bmad:chiseai:memory:baseline:near_dup_rate",
            0.08,
        )


class TestRegressionOriginalMetrics:
    """Regression tests for original 6 metrics (AC5)."""

    def test_capture_baseline_metrics_returns_memoryhealthmetrics(self):
        """AC5: capture_baseline_metrics should still return MemoryHealthMetrics."""
        session_samples = [
            {
                "session_id": "s1",
                "token_budget_used": 15000,
                "legacy_missing": ["rec1"],
                "hot_context_results": 5,
                "warm_context_results": 3,
                "cold_context_results": 2,
                "archived_context_results": 1,
                "staleness_violations": 0,
            }
        ]

        result = capture_baseline_metrics(session_samples)

        assert isinstance(result, MemoryHealthMetrics)
        assert result.total_sessions == 1
        assert result.avg_token_budget_used == 15000.0
        assert result.sessions_near_cap == 0  # 15000 < 20000 threshold

    def test_get_memory_health_summary_returns_memoryhealthsummary(self):
        """AC5: get_memory_health_summary should still return MemoryHealthSummary."""
        metrics = MemoryHealthMetrics(
            captured_at="2026-04-09T12:00:00Z",
            total_sessions=1,
            avg_token_budget_used=15000.0,
            max_token_budget_used=15000,
            sessions_near_cap=0,
            legacy_missing_count=1,
            legacy_missing_ratio=0.1,
            context_hit_rates={"hot": 1.0, "warm": 1.0, "cold": 1.0, "archived": 1.0},
            staleness_violations=0,
        )

        result = get_memory_health_summary(metrics)

        assert isinstance(result, MemoryHealthSummary)
        assert result.health_status == "healthy"
        assert len(result.findings) > 0

    def test_health_summary_detects_staleness_violations(self):
        """AC5: Should still detect staleness violations."""
        metrics = MemoryHealthMetrics(
            captured_at="2026-04-09T12:00:00Z",
            total_sessions=1,
            avg_token_budget_used=15000.0,
            max_token_budget_used=15000,
            sessions_near_cap=0,
            legacy_missing_count=0,
            legacy_missing_ratio=0.0,
            context_hit_rates={},
            staleness_violations=5,
        )

        result = get_memory_health_summary(metrics)

        assert result.health_status == "critical"
        assert result.staleness_violations == 5
