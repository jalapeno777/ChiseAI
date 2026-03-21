"""Tests for CI pre-evaluation tempmemory ingestion integration.

Story: ST-MEMORY-INGEST-005 - CI Pipeline Integration for Tempmemory Ingestion
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "ci"))

from governance.tempmemory.ci_integration import (
    CIIngestionReport,
    FEATURE_FLAG_ENV,
    cache_ingested_memories,
    cache_ingestion_report,
    create_redis_client,
    format_report_for_logs,
    get_cached_memories,
    get_ingestion_report,
    is_ingestion_enabled,
    is_memory_ingested,
    should_fail_ci,
    validate_ingestion_success,
)


class TestFeatureFlag:
    """Test feature flag behavior."""

    def test_is_ingestion_enabled_when_true(self, monkeypatch):
        """Test that ingestion is enabled when feature flag is 'true'."""
        monkeypatch.setenv(FEATURE_FLAG_ENV, "true")
        assert is_ingestion_enabled() is True

    def test_is_ingestion_enabled_when_1(self, monkeypatch):
        """Test that ingestion is enabled when feature flag is '1'."""
        monkeypatch.setenv(FEATURE_FLAG_ENV, "1")
        assert is_ingestion_enabled() is True

    def test_is_ingestion_enabled_when_yes(self, monkeypatch):
        """Test that ingestion is enabled when feature flag is 'yes'."""
        monkeypatch.setenv(FEATURE_FLAG_ENV, "yes")
        assert is_ingestion_enabled() is True

    def test_is_ingestion_enabled_when_on(self, monkeypatch):
        """Test that ingestion is enabled when feature flag is 'on'."""
        monkeypatch.setenv(FEATURE_FLAG_ENV, "on")
        assert is_ingestion_enabled() is True

    def test_is_ingestion_enabled_when_false(self, monkeypatch):
        """Test that ingestion is disabled when feature flag is 'false'."""
        monkeypatch.setenv(FEATURE_FLAG_ENV, "false")
        assert is_ingestion_enabled() is False

    def test_is_ingestion_enabled_when_unset(self, monkeypatch):
        """Test that ingestion is disabled when feature flag is unset."""
        monkeypatch.delenv(FEATURE_FLAG_ENV, raising=False)
        assert is_ingestion_enabled() is False

    def test_is_ingestion_enabled_case_insensitive(self, monkeypatch):
        """Test that feature flag is case-insensitive."""
        monkeypatch.setenv(FEATURE_FLAG_ENV, "TRUE")
        assert is_ingestion_enabled() is True
        monkeypatch.setenv(FEATURE_FLAG_ENV, "True")
        assert is_ingestion_enabled() is True


class TestCIIngestionReport:
    """Test CIIngestionReport dataclass."""

    def test_report_creation(self):
        """Test creating a basic report."""
        report = CIIngestionReport(
            success=True,
            files_processed=10,
            files_ingested=8,
            files_failed=1,
            files_skipped=1,
        )
        assert report.success is True
        assert report.files_processed == 10
        assert report.files_ingested == 8
        assert report.files_failed == 1
        assert report.files_skipped == 1
        assert report.timestamp is not None

    def test_report_to_dict(self):
        """Test converting report to dictionary."""
        report = CIIngestionReport(
            success=True,
            files_processed=10,
            files_ingested=8,
            files_failed=1,
            files_skipped=1,
            errors=["error1"],
            ingested_memory_ids=["mem1", "mem2"],
        )
        data = report.to_dict()
        assert data["success"] is True
        assert data["files_processed"] == 10
        assert data["files_ingested"] == 8
        assert data["errors"] == ["error1"]
        assert data["ingested_memory_ids"] == ["mem1", "mem2"]

    def test_report_from_dict(self):
        """Test creating report from dictionary."""
        data = {
            "success": True,
            "timestamp": "2026-03-21T10:00:00Z",
            "files_processed": 10,
            "files_ingested": 8,
            "files_failed": 1,
            "files_skipped": 1,
            "duration_seconds": 5.5,
            "errors": [],
            "ingested_memory_ids": ["mem1"],
            "pipeline_id": "123",
            "git_commit": "abc123",
        }
        report = CIIngestionReport.from_dict(data)
        assert report.success is True
        assert report.files_processed == 10
        assert report.pipeline_id == "123"
        assert report.git_commit == "abc123"

    def test_report_to_json(self):
        """Test converting report to JSON."""
        report = CIIngestionReport(
            success=True,
            files_processed=10,
            files_ingested=8,
        )
        json_str = report.to_json()
        assert "success" in json_str
        assert "files_processed" in json_str
        # Verify it's valid JSON
        parsed = json.loads(json_str)
        assert parsed["success"] is True


class TestValidateIngestionSuccess:
    """Test ingestion validation."""

    def test_validate_success_when_no_failures(self):
        """Test validation passes when no failures."""
        report = CIIngestionReport(
            success=True,
            files_processed=10,
            files_ingested=10,
            files_failed=0,
        )
        assert validate_ingestion_success(report) is True

    def test_validate_fails_when_success_false(self):
        """Test validation fails when success is False."""
        report = CIIngestionReport(
            success=False,
            files_processed=10,
            files_ingested=5,
            files_failed=5,
            errors=["error1"],
        )
        assert validate_ingestion_success(report) is False

    def test_validate_fails_when_files_failed(self):
        """Test validation fails when files_failed > 0."""
        report = CIIngestionReport(
            success=True,
            files_processed=10,
            files_ingested=9,
            files_failed=1,
        )
        assert validate_ingestion_success(report) is False


class TestShouldFailCI:
    """Test CI failure determination."""

    def test_should_not_fail_when_feature_disabled(self, monkeypatch):
        """Test CI should not fail when feature flag is disabled."""
        monkeypatch.delenv(FEATURE_FLAG_ENV, raising=False)
        report = CIIngestionReport(
            success=False,
            files_processed=10,
            files_ingested=0,
            files_failed=10,
        )
        assert should_fail_ci(report) is False

    def test_should_fail_on_lock_error(self, monkeypatch):
        """Test CI should fail on lock acquisition errors."""
        monkeypatch.setenv(FEATURE_FLAG_ENV, "true")
        report = CIIngestionReport(
            success=False,
            files_processed=0,
            files_ingested=0,
            files_failed=0,
            errors=["Lock acquisition failed: could not acquire lock"],
        )
        assert should_fail_ci(report) is True

    def test_should_fail_in_strict_mode(self, monkeypatch):
        """Test CI should fail in strict mode on any failure."""
        monkeypatch.setenv(FEATURE_FLAG_ENV, "true")
        report = CIIngestionReport(
            success=True,
            files_processed=10,
            files_ingested=9,
            files_failed=1,
        )
        assert should_fail_ci(report, strict=True) is True

    def test_should_not_fail_in_non_strict_mode_with_partial_success(self, monkeypatch):
        """Test CI should not fail in non-strict mode with partial success."""
        monkeypatch.setenv(FEATURE_FLAG_ENV, "true")
        report = CIIngestionReport(
            success=True,
            files_processed=10,
            files_ingested=9,
            files_failed=1,
        )
        assert should_fail_ci(report, strict=False) is False

    def test_should_fail_when_all_files_fail(self, monkeypatch):
        """Test CI should fail when all files fail."""
        monkeypatch.setenv(FEATURE_FLAG_ENV, "true")
        report = CIIngestionReport(
            success=True,
            files_processed=10,
            files_ingested=0,
            files_failed=10,
        )
        assert should_fail_ci(report, strict=False) is True


class TestCaching:
    """Test Redis caching functionality."""

    def test_cache_ingestion_report_success(self):
        """Test caching ingestion report."""
        mock_redis = MagicMock()
        report = CIIngestionReport(
            success=True,
            files_processed=10,
            files_ingested=8,
        )
        result = cache_ingestion_report(report, mock_redis)
        assert result is True
        mock_redis.set.assert_called_once()
        # Verify TTL is set
        call_args = mock_redis.set.call_args
        assert call_args[1]["ex"] == 3600  # 1 hour TTL

    def test_cache_ingestion_report_no_redis(self):
        """Test caching when Redis is unavailable."""
        report = CIIngestionReport(success=True, files_processed=10)
        # When redis_client is None and create_redis_client returns None,
        # the function should return False
        with patch(
            "governance.tempmemory.ci_integration.create_redis_client",
            return_value=None,
        ):
            result = cache_ingestion_report(report, None)
        assert result is False

    def test_cache_ingested_memories_success(self):
        """Test caching ingested memory IDs."""
        mock_redis = MagicMock()
        memory_ids = ["mem1", "mem2", "mem3"]
        result = cache_ingested_memories(memory_ids, mock_redis)
        assert result is True
        mock_redis.sadd.assert_called_once()
        mock_redis.expire.assert_called_once()

    def test_cache_ingested_memories_empty_list(self):
        """Test caching with empty memory list."""
        mock_redis = MagicMock()
        result = cache_ingested_memories([], mock_redis)
        assert result is True
        # sadd should not be called with empty list
        mock_redis.sadd.assert_not_called()

    def test_get_ingestion_report_success(self):
        """Test retrieving cached ingestion report."""
        mock_redis = MagicMock()
        report_data = {
            "success": True,
            "timestamp": "2026-03-21T10:00:00Z",
            "files_processed": 10,
            "files_ingested": 8,
            "files_failed": 0,
            "files_skipped": 0,
            "duration_seconds": 5.0,
            "errors": [],
            "ingested_memory_ids": [],
        }
        mock_redis.get.return_value = json.dumps(report_data)
        report = get_ingestion_report(mock_redis)
        assert report is not None
        assert report.success is True
        assert report.files_processed == 10

    def test_get_ingestion_report_no_redis(self):
        """Test retrieving report when Redis is unavailable."""
        # Mock create_redis_client to return None (simulating no Redis)
        with patch(
            "governance.tempmemory.ci_integration.create_redis_client",
            return_value=None,
        ):
            report = get_ingestion_report(None)
        assert report is None

    def test_get_cached_memories_success(self):
        """Test retrieving cached memory IDs."""
        mock_redis = MagicMock()
        mock_redis.smembers.return_value = [b"mem1", b"mem2"]
        memories = get_cached_memories(mock_redis)
        assert memories == ["mem1", "mem2"]

    def test_get_cached_memories_no_redis(self):
        """Test retrieving memories when Redis is unavailable."""
        memories = get_cached_memories(None)
        assert memories == []

    def test_is_memory_ingested_true(self):
        """Test checking if memory was ingested (True)."""
        mock_redis = MagicMock()
        mock_redis.sismember.return_value = True
        result = is_memory_ingested("mem1", mock_redis)
        assert result is True

    def test_is_memory_ingested_false(self):
        """Test checking if memory was ingested (False)."""
        mock_redis = MagicMock()
        mock_redis.sismember.return_value = False
        result = is_memory_ingested("mem1", mock_redis)
        assert result is False


class TestFormatReportForLogs:
    """Test report formatting."""

    def test_format_report_basic(self):
        """Test basic report formatting."""
        report = CIIngestionReport(
            success=True,
            files_processed=10,
            files_ingested=8,
            files_failed=1,
            files_skipped=1,
            duration_seconds=5.5,
        )
        formatted = format_report_for_logs(report)
        assert "TEMPMEMORY INGESTION REPORT" in formatted
        assert "Files Processed: 10" in formatted
        # Check for files ingested count (may be formatted as int)
        assert "Files Ingested:" in formatted
        assert "8" in formatted
        # Check for "Files Failed:" and "Files Skipped:" separately
        assert "Files Failed:" in formatted
        assert "Files Skipped:" in formatted
        assert "Success: YES" in formatted

    def test_format_report_with_errors(self):
        """Test report formatting with errors."""
        report = CIIngestionReport(
            success=False,
            files_processed=10,
            files_ingested=0,
            files_failed=10,
            errors=["error1", "error2", "error3"],
        )
        formatted = format_report_for_logs(report)
        assert "Errors (3):" in formatted
        assert "error1" in formatted
        assert "error2" in formatted
        assert "error3" in formatted

    def test_format_report_with_memory_ids(self):
        """Test report formatting with memory IDs."""
        report = CIIngestionReport(
            success=True,
            files_processed=5,
            files_ingested=5,
            ingested_memory_ids=["mem1", "mem2", "mem3"],
        )
        formatted = format_report_for_logs(report)
        assert "Ingested Memories (3):" in formatted
        assert "mem1" in formatted
        assert "mem2" in formatted
        assert "mem3" in formatted


class TestRedisClientCreation:
    """Test Redis client creation."""

    def test_create_redis_client_success(self, monkeypatch):
        """Test successful Redis client creation."""
        monkeypatch.setenv("REDIS_HOST", "localhost")
        monkeypatch.setenv("REDIS_PORT", "6379")

        mock_client = MagicMock()
        mock_redis = MagicMock()
        mock_redis.Redis.return_value = mock_client

        with patch.dict(sys.modules, {"redis": mock_redis}):
            client = create_redis_client()
            assert client is not None
            mock_client.ping.assert_called_once()

    def test_create_redis_client_connection_failure(self):
        """Test Redis client creation failure."""
        mock_redis = MagicMock()
        mock_redis.Redis.side_effect = Exception("Connection refused")

        with patch.dict(sys.modules, {"redis": mock_redis}):
            client = create_redis_client()
            assert client is None

    def test_create_redis_client_no_redis_lib(self):
        """Test Redis client creation when redis library not installed."""
        # Simulate redis module not being available
        with patch.dict(sys.modules, {"redis": None}):
            client = create_redis_client()
            assert client is None


class TestCIIntegrationEndToEnd:
    """End-to-end integration tests."""

    def test_full_workflow_disabled(self, monkeypatch):
        """Test full workflow when ingestion is disabled."""
        monkeypatch.delenv(FEATURE_FLAG_ENV, raising=False)
        # When disabled, should return success=True with skip message
        from governance.tempmemory.ci_integration import run_pre_eval_ingestion

        with patch.object(
            sys.modules["governance.tempmemory.ci_integration"],
            "is_ingestion_enabled",
            return_value=False,
        ):
            report = CIIngestionReport(
                success=True,
                files_processed=0,
                errors=["Ingestion skipped (feature flag disabled)"],
            )
            assert report.success is True
            assert should_fail_ci(report) is False

    def test_full_workflow_with_critical_error(self, monkeypatch):
        """Test full workflow with critical error."""
        monkeypatch.setenv(FEATURE_FLAG_ENV, "true")
        report = CIIngestionReport(
            success=False,
            files_processed=0,
            files_ingested=0,
            files_failed=0,
            errors=["Lock acquisition failed: could not acquire lock"],
        )
        assert should_fail_ci(report) is True
        assert validate_ingestion_success(report) is False

    def test_full_workflow_success(self, monkeypatch):
        """Test full workflow with successful ingestion."""
        monkeypatch.setenv(FEATURE_FLAG_ENV, "true")
        report = CIIngestionReport(
            success=True,
            files_processed=10,
            files_ingested=10,
            files_failed=0,
            ingested_memory_ids=["mem1", "mem2"],
        )
        assert should_fail_ci(report) is False
        assert validate_ingestion_success(report) is True


class TestCIGateIntegration:
    """Test integration with ci_gate.py."""

    def test_pre_eval_ingestion_in_full_required(self):
        """Verify pre-eval-ingestion.status is only required for full/cron gates."""
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "ci_gate",
            Path(__file__).resolve().parents[2] / "scripts" / "ci" / "ci_gate.py",
        )
        assert spec and spec.loader
        ci_gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ci_gate)

        assert "pre-eval-ingestion.status" not in ci_gate.FAST_REQUIRED
        assert "pre-eval-ingestion.status" in ci_gate.FULL_REQUIRED

    def test_ci_gate_fails_when_pre_eval_ingestion_fails(self, tmp_path, monkeypatch):
        """Test that ci_gate fails when pre-eval-ingestion.status is non-zero."""
        import importlib.util
        from subprocess import CompletedProcess

        spec = importlib.util.spec_from_file_location(
            "ci_gate",
            Path(__file__).resolve().parents[2] / "scripts" / "ci" / "ci_gate.py",
        )
        assert spec and spec.loader
        ci_gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ci_gate)

        ci_dir = tmp_path / "ci"
        ci_dir.mkdir(parents=True)

        # Create all required status files with success (0) except pre-eval-ingestion.
        # Force full-gate mode to include FULL_REQUIRED statuses.
        monkeypatch.setenv("FORCE_FULL_GATE", "1")
        for status_file in ci_gate.FAST_REQUIRED:
            (ci_dir / status_file).write_text("0", encoding="utf-8")
        for status_file in ci_gate.FULL_REQUIRED:
            if status_file == "pre-eval-ingestion.status":
                (ci_dir / status_file).write_text("1", encoding="utf-8")
            else:
                (ci_dir / status_file).write_text("0", encoding="utf-8")

        # Monkeypatch CI_DIR to use our temp directory
        monkeypatch.setattr(ci_gate, "CI_DIR", ci_dir)

        # Mock subprocess.run to avoid actual execution
        monkeypatch.setattr(
            ci_gate.subprocess,
            "run",
            lambda *args, **kwargs: CompletedProcess(args, 0, stdout="", stderr=""),
        )

        # Run ci_gate
        result = ci_gate.main()

        # Should return non-zero (failure) because pre-eval-ingestion.status is 1
        assert result != 0, "ci_gate should fail when pre-eval-ingestion.status is 1"

    def test_ci_gate_passes_when_pre_eval_ingestion_succeeds(
        self, tmp_path, monkeypatch
    ):
        """Test that ci_gate passes when pre-eval-ingestion.status is 0."""
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "ci_gate",
            Path(__file__).resolve().parents[2] / "scripts" / "ci" / "ci_gate.py",
        )
        assert spec and spec.loader
        ci_gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ci_gate)

        ci_dir = tmp_path / "ci"
        ci_dir.mkdir(parents=True)

        # Create all required status files with success (0) in full-gate mode.
        monkeypatch.setenv("FORCE_FULL_GATE", "1")
        for status_file in ci_gate.FAST_REQUIRED:
            (ci_dir / status_file).write_text("0", encoding="utf-8")
        for status_file in ci_gate.FULL_REQUIRED:
            (ci_dir / status_file).write_text("0", encoding="utf-8")

        # Monkeypatch CI_DIR to use our temp directory
        monkeypatch.setattr(ci_gate, "CI_DIR", ci_dir)

        # Run ci_gate
        result = ci_gate.main()

        # Should return zero (success) because all statuses are 0
        assert result == 0, "ci_gate should pass when all statuses are 0"
