"""
Tests for audit trail exporter.

ST-GOV-009: Decision Audit Trail Export
"""

import gzip
import json
import os
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.governance.audit_trail.decision import DecisionOutcome, DecisionType
from src.governance.audit_trail.exporter import (
    AuditTrailExporter,
    ExportConfig,
    ExportFormat,
    ExportResult,
    ExportStatus,
    LocalStorageBackend,
    S3Config,
)
from src.governance.audit_trail.query import AuditTrailQuery
from src.governance.audit_trail.trail import AuditTrail


class TestExportConfig:
    """Tests for ExportConfig."""

    def test_default_config(self):
        """Test default export configuration."""
        config = ExportConfig()

        assert config.format == ExportFormat.JSONL
        assert config.compress is True
        assert config.include_chain_verification is True
        assert config.retention_years == 7

    def test_retention_days_calculation(self):
        """Test retention days calculation."""
        config = ExportConfig(retention_years=7)
        # 7 years = 7 * 365 + 1 or 2 leap years
        assert 2550 <= config.retention_days <= 2560


class TestS3Config:
    """Tests for S3Config."""

    def test_default_config(self):
        """Test default S3 configuration."""
        config = S3Config()

        assert config.bucket == "chiseai-audit-exports"
        assert config.prefix == "audit-trail/"
        assert config.region == "us-east-1"

    def test_from_env(self, monkeypatch):
        """Test creating config from environment."""
        monkeypatch.setenv("AUDIT_EXPORT_S3_BUCKET", "my-bucket")
        monkeypatch.setenv("AUDIT_EXPORT_S3_PREFIX", "my-prefix/")
        monkeypatch.setenv("AWS_REGION", "eu-west-1")

        config = S3Config.from_env()

        assert config.bucket == "my-bucket"
        assert config.prefix == "my-prefix/"
        assert config.region == "eu-west-1"


class TestExportResult:
    """Tests for ExportResult."""

    def test_default_result(self):
        """Test default export result."""
        result = ExportResult()

        assert result.status == ExportStatus.PENDING
        assert result.entry_count == 0

    def test_result_to_dict(self):
        """Test result serialization."""
        result = ExportResult(
            status=ExportStatus.COMPLETED,
            file_path="/tmp/export.jsonl",
            entry_count=100,
            file_size_bytes=5000,
            chain_valid=True,
            checksum="sha256:abc123",
        )

        data = result.to_dict()

        assert data["status"] == "completed"
        assert data["file_path"] == "/tmp/export.jsonl"
        assert data["entry_count"] == 100
        assert data["chain_valid"] is True


class TestLocalStorageBackend:
    """Tests for LocalStorageBackend."""

    def test_upload_and_download(self):
        """Test uploading and downloading data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = LocalStorageBackend(base_path=tmpdir)

            data = b"test data content"
            metadata = {"entry_count": "10"}

            # Upload
            success = backend.upload("test/key.txt", data, metadata)
            assert success is True

            # Download
            downloaded = backend.download("test/key.txt")
            assert downloaded == data

    def test_list_keys(self):
        """Test listing keys."""
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = LocalStorageBackend(base_path=tmpdir)

            backend.upload("2024/01/file1.txt", b"data1")
            backend.upload("2024/01/file2.txt", b"data2")
            backend.upload("2024/02/file3.txt", b"data3")

            keys = backend.list_keys("2024/01/")

            assert len(keys) == 2
            assert any("file1.txt" in k for k in keys)
            assert any("file2.txt" in k for k in keys)

    def test_delete(self):
        """Test deleting data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = LocalStorageBackend(base_path=tmpdir)

            backend.upload("test/file.txt", b"data")
            assert backend.download("test/file.txt") == b"data"

            backend.delete("test/file.txt")
            assert backend.download("test/file.txt") is None


class TestAuditTrailExporter:
    """Tests for AuditTrailExporter."""

    @pytest.fixture
    def populated_trail_and_query(self):
        """Create a populated trail and query interface."""
        trail = AuditTrail()

        # Log several entries
        for i in range(5):
            trail.log_decision(
                agent_id=f"agent-{i % 2}",
                decision_type=DecisionType.TASK_COMPLETE,
                context={"iteration": i},
                rationale=f"Task {i}",
                outcome=DecisionOutcome.SUCCESS
                if i % 2 == 0
                else DecisionOutcome.FAILURE,
            )

        query = AuditTrailQuery(in_memory_entries=trail._entries)
        return trail, query

    def test_export_to_file(self, populated_trail_and_query):
        """Test exporting to local file."""
        trail, query = populated_trail_and_query

        with tempfile.TemporaryDirectory() as tmpdir:
            exporter = AuditTrailExporter(
                query_interface=query,
                config=ExportConfig(compress=False),
                output_dir=tmpdir,
            )

            chain_state = {
                "valid": True,
                "chain_length": trail.get_chain_state().chain_length,
            }

            result = exporter.export_to_file(chain_state=chain_state)

            assert result.status == ExportStatus.COMPLETED
            assert result.entry_count == 5
            assert result.file_path is not None
            assert os.path.exists(result.file_path)
            assert result.chain_valid is True

    def test_export_to_file_compressed(self, populated_trail_and_query):
        """Test exporting to compressed file."""
        trail, query = populated_trail_and_query

        with tempfile.TemporaryDirectory() as tmpdir:
            exporter = AuditTrailExporter(
                query_interface=query,
                config=ExportConfig(compress=True),
                output_dir=tmpdir,
            )

            result = exporter.export_to_file()

            assert result.status == ExportStatus.COMPLETED
            assert result.file_path.endswith(".gz")

            # Verify gzip file is valid
            with gzip.open(result.file_path, "rt") as f:
                content = f.read()
                # In JSONL format, first line is metadata JSON
                first_line = content.split("\n")[0]
                metadata = json.loads(first_line)
                assert "exported_at" in metadata

    def test_export_format_jsonl(self, populated_trail_and_query):
        """Test JSONL export format."""
        trail, query = populated_trail_and_query

        with tempfile.TemporaryDirectory() as tmpdir:
            exporter = AuditTrailExporter(
                query_interface=query,
                config=ExportConfig(format=ExportFormat.JSONL, compress=False),
                output_dir=tmpdir,
            )

            result = exporter.export_to_file()

            with open(result.file_path) as f:
                lines = f.readlines()

            # First line should be metadata
            metadata = json.loads(lines[0])
            assert "exported_at" in metadata
            assert metadata["entry_count"] == 5

            # Remaining lines should be entries
            for line in lines[1:6]:  # 5 entries
                entry = json.loads(line)
                assert "decision_id" in entry

    def test_export_with_filter(self, populated_trail_and_query):
        """Test exporting with filter criteria."""
        trail, query = populated_trail_and_query

        from src.governance.audit_trail.query import QueryFilter

        filter_criteria = QueryFilter(
            agent_id="agent-0",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            exporter = AuditTrailExporter(
                query_interface=query,
                output_dir=tmpdir,
            )

            result = exporter.export_to_file(filter_criteria=filter_criteria)

            # Should only have entries from agent-0
            assert result.entry_count < 5

    def test_export_to_s3_with_local_backend(self, populated_trail_and_query):
        """Test exporting to S3 using local storage backend."""
        trail, query = populated_trail_and_query

        with tempfile.TemporaryDirectory() as tmpdir:
            storage_backend = LocalStorageBackend(base_path=os.path.join(tmpdir, "s3"))

            exporter = AuditTrailExporter(
                query_interface=query,
                config=ExportConfig(compress=False),
                s3_config=S3Config(bucket="test-bucket"),
                storage_backend=storage_backend,
                output_dir=tmpdir,
            )

            result = exporter.export_to_s3()

            assert result.status == ExportStatus.COMPLETED
            assert result.s3_key is not None

            # Verify data was uploaded to "S3"
            keys = storage_backend.list_keys("")
            assert len(keys) > 0

    def test_export_to_s3_without_config(self, populated_trail_and_query):
        """Test that S3 export fails without config."""
        _, query = populated_trail_and_query

        with tempfile.TemporaryDirectory() as tmpdir:
            exporter = AuditTrailExporter(
                query_interface=query,
                s3_config=None,
                output_dir=tmpdir,
            )

            result = exporter.export_to_s3()

            assert result.status == ExportStatus.FAILED
            assert "S3 configuration not provided" in result.error_message

    def test_export_daily(self, populated_trail_and_query):
        """Test daily export."""
        trail, query = populated_trail_and_query

        with tempfile.TemporaryDirectory() as tmpdir:
            storage_backend = LocalStorageBackend(base_path=os.path.join(tmpdir, "s3"))

            exporter = AuditTrailExporter(
                query_interface=query,
                s3_config=S3Config(bucket="test-bucket"),
                storage_backend=storage_backend,
                output_dir=tmpdir,
            )

            result = exporter.export_daily()

            assert result.status == ExportStatus.COMPLETED
            assert "daily/" in result.s3_key

    def test_export_full(self, populated_trail_and_query):
        """Test full export."""
        trail, query = populated_trail_and_query

        with tempfile.TemporaryDirectory() as tmpdir:
            storage_backend = LocalStorageBackend(base_path=os.path.join(tmpdir, "s3"))

            exporter = AuditTrailExporter(
                query_interface=query,
                s3_config=S3Config(bucket="test-bucket"),
                storage_backend=storage_backend,
                output_dir=tmpdir,
            )

            result = exporter.export_full()

            assert result.status == ExportStatus.COMPLETED
            assert "full/" in result.s3_key

    def test_export_includes_checksum(self, populated_trail_and_query):
        """Test that export includes checksum."""
        _, query = populated_trail_and_query

        with tempfile.TemporaryDirectory() as tmpdir:
            exporter = AuditTrailExporter(
                query_interface=query,
                output_dir=tmpdir,
            )

            result = exporter.export_to_file()

            assert result.checksum is not None
            assert result.checksum.startswith("sha256:")
            assert len(result.checksum) == 71  # "sha256:" + 64 hex chars

    def test_export_schema_compliance(self, populated_trail_and_query):
        """Test that export matches the required schema."""
        trail, query = populated_trail_and_query

        with tempfile.TemporaryDirectory() as tmpdir:
            exporter = AuditTrailExporter(
                query_interface=query,
                config=ExportConfig(format=ExportFormat.JSONL, compress=False),
                output_dir=tmpdir,
            )

            result = exporter.export_to_file()

            with open(result.file_path) as f:
                # Skip metadata line
                next(f)
                # Read first entry
                entry = json.loads(f.readline())

            # Verify all required schema fields
            required_fields = [
                "decision_id",
                "timestamp",
                "agent_id",
                "decision_type",
                "context",
                "rationale",
                "outcome",
                "constitution_principles",
                "hash",
                "prev_hash",
            ]

            for field in required_fields:
                assert field in entry, f"Missing required field: {field}"

    def test_cleanup_old_exports(self, populated_trail_and_query):
        """Test cleaning up old exports."""
        _, query = populated_trail_and_query

        with tempfile.TemporaryDirectory() as tmpdir:
            exporter = AuditTrailExporter(
                query_interface=query,
                output_dir=tmpdir,
            )

            # Create several exports
            for _ in range(3):
                exporter.export_to_file()

            # Should have files
            files_before = os.listdir(tmpdir)
            assert len(files_before) >= 1

            # Manually set old modification time to test cleanup
            import time

            old_time = time.time() - (10 * 24 * 60 * 60)  # 10 days ago
            for f in files_before:
                os.utime(os.path.join(tmpdir, f), (old_time, old_time))

            # Clean up with 7-day retention (should delete 10-day old files)
            deleted = exporter.cleanup_old_exports(retention_days=7)

            # Should have deleted files
            assert deleted >= 1
