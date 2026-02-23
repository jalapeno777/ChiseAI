"""
Audit trail exporter for S3 and local exports.

Provides automated daily exports with configurable retention.
"""

from __future__ import annotations

import gzip
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from src.governance.audit_trail.query import (
    AuditTrailQuery,
    QueryFilter,
    QueryResult,
    SortOrder,
)
from src.governance.audit_trail.trail import AuditTrailEntry

logger = logging.getLogger(__name__)


class ExportFormat(str, Enum):
    """Export file format."""

    JSON = "json"
    JSONL = "jsonl"  # JSON Lines (one JSON object per line)
    CSV = "csv"


class ExportStatus(str, Enum):
    """Status of an export operation."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class S3Config:
    """
    Configuration for S3 export.

    Attributes:
        bucket: S3 bucket name
        prefix: Key prefix for exports
        region: AWS region
        access_key_id: AWS access key ID (optional, uses env if not set)
        secret_access_key: AWS secret access key (optional, uses env if not set)
        endpoint_url: Custom endpoint URL (for S3-compatible storage)
        use_ssl: Whether to use SSL
    """

    bucket: str = "chiseai-audit-exports"
    prefix: str = "audit-trail/"
    region: str = "us-east-1"
    access_key_id: str | None = None
    secret_access_key: str | None = None
    endpoint_url: str | None = None
    use_ssl: bool = True

    @classmethod
    def from_env(cls) -> "S3Config":
        """Create S3Config from environment variables."""
        return cls(
            bucket=os.getenv("AUDIT_EXPORT_S3_BUCKET", "chiseai-audit-exports"),
            prefix=os.getenv("AUDIT_EXPORT_S3_PREFIX", "audit-trail/"),
            region=os.getenv("AWS_REGION", "us-east-1"),
            access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            endpoint_url=os.getenv("S3_ENDPOINT_URL"),
            use_ssl=os.getenv("S3_USE_SSL", "true").lower() == "true",
        )


@dataclass
class ExportConfig:
    """
    Configuration for export operations.

    Attributes:
        format: Export format
        compress: Whether to gzip compress the output
        include_chain_verification: Whether to include chain verification data
        batch_size: Number of entries per batch (for large exports)
        retention_years: Number of years to retain exports (default: 7)
        daily_export_hour: Hour (UTC) for daily exports
    """

    format: ExportFormat = ExportFormat.JSONL
    compress: bool = True
    include_chain_verification: bool = True
    batch_size: int = 10000
    retention_years: int = 7
    daily_export_hour: int = 2  # 2 AM UTC

    @property
    def retention_days(self) -> int:
        """Get retention in days."""
        return (
            self.retention_years * 365 + self.retention_years // 4
        )  # Account for leap years


@dataclass
class ExportResult:
    """
    Result of an export operation.

    Attributes:
        status: Export status
        file_path: Local file path (if exported locally)
        s3_key: S3 key (if exported to S3)
        entry_count: Number of entries exported
        file_size_bytes: Size of the exported file
        started_at: Export start time
        completed_at: Export completion time
        error_message: Error message if export failed
        chain_valid: Whether chain verification passed
        checksum: SHA-256 checksum of exported data
    """

    status: ExportStatus = ExportStatus.PENDING
    file_path: str | None = None
    s3_key: str | None = None
    entry_count: int = 0
    file_size_bytes: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    chain_valid: bool | None = None
    checksum: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "status": self.status.value,
            "file_path": self.file_path,
            "s3_key": self.s3_key,
            "entry_count": self.entry_count,
            "file_size_bytes": self.file_size_bytes,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
            "error_message": self.error_message,
            "chain_valid": self.chain_valid,
            "checksum": self.checksum,
        }


@runtime_checkable
class StorageBackend(Protocol):
    """Protocol for storage backend."""

    def upload(
        self, key: str, data: bytes, metadata: dict[str, str] | None = None
    ) -> bool:
        """Upload data to storage."""
        ...

    def download(self, key: str) -> bytes | None:
        """Download data from storage."""
        ...

    def delete(self, key: str) -> bool:
        """Delete data from storage."""
        ...

    def list_keys(self, prefix: str) -> list[str]:
        """List keys with prefix."""
        ...


class AuditTrailExporter:
    """
    Exporter for audit trail data.

    Supports export to:
    - Local filesystem
    - S3 (or S3-compatible storage)

    Features:
    - Configurable format (JSON, JSONL, CSV)
    - Compression (gzip)
    - Chain verification inclusion
    - Daily scheduled exports
    - Retention-based cleanup

    Example:
        >>> exporter = AuditTrailExporter(
        ...     query_interface=my_query,
        ...     s3_config=S3Config.from_env(),
        ... )
        >>> result = exporter.export_daily()
        >>> print(f"Exported {result.entry_count} entries")
    """

    def __init__(
        self,
        query_interface: AuditTrailQuery,
        config: ExportConfig | None = None,
        s3_config: S3Config | None = None,
        storage_backend: StorageBackend | None = None,
        output_dir: str = "/tmp/audit_exports",
    ):
        """
        Initialize the exporter.

        Args:
            query_interface: Query interface for fetching entries
            config: Export configuration
            s3_config: S3 configuration (for S3 exports)
            storage_backend: Custom storage backend (optional)
            output_dir: Local directory for exports
        """
        self._query = query_interface
        self._config = config or ExportConfig()
        self._s3_config = s3_config
        self._storage_backend = storage_backend
        self._output_dir = output_dir

        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)

    def export_to_file(
        self,
        filter_criteria: QueryFilter | None = None,
        file_path: str | None = None,
        chain_state: dict[str, Any] | None = None,
    ) -> ExportResult:
        """
        Export audit trail to a local file.

        Args:
            filter_criteria: Optional filter for entries
            file_path: Output file path (auto-generated if None)
            chain_state: Optional chain state to include

        Returns:
            ExportResult with export details
        """
        result = ExportResult(
            status=ExportStatus.IN_PROGRESS,
            started_at=datetime.now(UTC),
        )

        try:
            # Generate file path if not provided
            if file_path is None:
                timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
                extension = self._get_file_extension()
                file_path = os.path.join(
                    self._output_dir, f"audit_trail_{timestamp}{extension}"
                )

            # Fetch entries
            query_result = self._query.query(
                filter_criteria=filter_criteria,
                page_size=1000000,  # Large page size for full export
                sort_order=SortOrder.ASC,
            )

            entries = query_result.entries
            result.entry_count = len(entries)

            # Build export data
            export_data = self._build_export_data(entries, chain_state)

            # Write to file
            content = self._serialize(export_data)

            if self._config.compress:
                content = gzip.compress(content.encode("utf-8"))
                file_path += ".gz"

            with open(file_path, "wb" if self._config.compress else "w") as f:
                f.write(content)

            # Calculate checksum
            result.checksum = self._calculate_checksum(
                content if isinstance(content, bytes) else content.encode("utf-8")
            )

            result.file_path = file_path
            result.file_size_bytes = (
                os.path.getsize(file_path)
                if os.path.exists(file_path)
                else len(content)
                if isinstance(content, bytes)
                else len(content)
            )
            result.chain_valid = chain_state is None or chain_state.get("valid", True)
            result.status = ExportStatus.COMPLETED
            result.completed_at = datetime.now(UTC)

            logger.info(
                f"Exported {result.entry_count} entries to {file_path} "
                f"({result.file_size_bytes} bytes)"
            )

        except Exception as e:
            result.status = ExportStatus.FAILED
            result.error_message = str(e)
            result.completed_at = datetime.now(UTC)
            logger.error(f"Export failed: {e}")

        return result

    def export_to_s3(
        self,
        filter_criteria: QueryFilter | None = None,
        s3_key: str | None = None,
        chain_state: dict[str, Any] | None = None,
    ) -> ExportResult:
        """
        Export audit trail to S3.

        Args:
            filter_criteria: Optional filter for entries
            s3_key: S3 key (auto-generated if None)
            chain_state: Optional chain state to include

        Returns:
            ExportResult with export details
        """
        result = ExportResult(
            status=ExportStatus.IN_PROGRESS,
            started_at=datetime.now(UTC),
        )

        try:
            # First export to local file
            local_result = self.export_to_file(
                filter_criteria=filter_criteria,
                chain_state=chain_state,
            )

            if local_result.status != ExportStatus.COMPLETED:
                return local_result

            result.entry_count = local_result.entry_count
            result.chain_valid = local_result.chain_valid
            result.checksum = local_result.checksum

            # Check S3 config is available
            if self._s3_config is None:
                result.status = ExportStatus.FAILED
                result.error_message = "S3 configuration not provided"
                result.completed_at = datetime.now(UTC)
                return result

            # Generate S3 key if not provided
            if s3_key is None:
                timestamp = datetime.now(UTC).strftime("%Y/%m/%d")
                filename = f"audit_trail_{datetime.now(UTC).strftime('%H%M%S')}.jsonl"
                if self._config.compress:
                    filename += ".gz"
                s3_key = f"{self._s3_config.prefix}{timestamp}/{filename}"

            # Upload to S3
            if self._storage_backend is not None and local_result.file_path is not None:
                with open(local_result.file_path, "rb") as f:
                    data = f.read()

                metadata = {
                    "entry_count": str(result.entry_count),
                    "checksum": result.checksum or "",
                    "chain_valid": str(result.chain_valid or False),
                    "export_time": datetime.now(UTC).isoformat(),
                }

                success = self._storage_backend.upload(s3_key, data, metadata)
                if not success:
                    raise RuntimeError("Failed to upload to storage backend")

            result.s3_key = s3_key
            result.file_path = local_result.file_path
            result.file_size_bytes = local_result.file_size_bytes
            result.status = ExportStatus.COMPLETED
            result.completed_at = datetime.now(UTC)

            logger.info(
                f"Exported {result.entry_count} entries to s3://{self._s3_config.bucket}/{s3_key}"
            )

        except Exception as e:
            result.status = ExportStatus.FAILED
            result.error_message = str(e)
            result.completed_at = datetime.now(UTC)
            logger.error(f"S3 export failed: {e}")

        return result

    def export_daily(self) -> ExportResult:
        """
        Perform daily export.

        Exports all entries from the previous day to S3.

        Returns:
            ExportResult with export details
        """
        # Check S3 config is available
        if self._s3_config is None:
            return ExportResult(
                status=ExportStatus.FAILED,
                error_message="S3 configuration not provided",
                started_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
            )

        # Calculate time range for previous day
        today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday = today - timedelta(days=1)

        filter_criteria = QueryFilter(
            start_time=yesterday,
            end_time=today,
        )

        # Generate S3 key with date structure
        s3_key = (
            f"{self._s3_config.prefix}daily/"
            f"{yesterday.strftime('%Y/%m/%d')}/"
            f"audit_trail.jsonl"
        )
        if self._config.compress:
            s3_key += ".gz"

        return self.export_to_s3(
            filter_criteria=filter_criteria,
            s3_key=s3_key,
        )

    def export_full(self) -> ExportResult:
        """
        Perform full export of all entries.

        Returns:
            ExportResult with export details
        """
        # Check S3 config is available
        if self._s3_config is None:
            return ExportResult(
                status=ExportStatus.FAILED,
                error_message="S3 configuration not provided",
                started_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
            )

        s3_key = (
            f"{self._s3_config.prefix}full/"
            f"{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}/"
            f"audit_trail_full.jsonl"
        )
        if self._config.compress:
            s3_key += ".gz"

        return self.export_to_s3(s3_key=s3_key)

    def cleanup_old_exports(self, retention_days: int | None = None) -> int:
        """
        Clean up old exports based on retention policy.

        Args:
            retention_days: Override retention days (uses config if None)

        Returns:
            Number of files deleted
        """
        retention_days = retention_days or self._config.retention_days
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)

        deleted_count = 0

        # Clean up local files
        if os.path.exists(self._output_dir):
            for filename in os.listdir(self._output_dir):
                file_path = os.path.join(self._output_dir, filename)
                if os.path.isfile(file_path):
                    file_time = datetime.fromtimestamp(
                        os.path.getmtime(file_path), tz=UTC
                    )
                    if file_time < cutoff:
                        try:
                            os.remove(file_path)
                            deleted_count += 1
                            logger.info(f"Deleted old export: {file_path}")
                        except Exception as e:
                            logger.warning(f"Failed to delete {file_path}: {e}")

        return deleted_count

    def _build_export_data(
        self,
        entries: list[AuditTrailEntry],
        chain_state: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Build export data structure."""
        export_data: dict[str, Any] = {
            "export_metadata": {
                "version": "1.0",
                "exported_at": datetime.now(UTC).isoformat(),
                "entry_count": len(entries),
                "format": self._config.format.value,
                "compressed": self._config.compress,
            },
            "entries": [e.to_dict() for e in entries],
        }

        if chain_state is not None:
            export_data["chain_state"] = chain_state

        return export_data

    def _serialize(self, data: dict[str, Any]) -> str:
        """Serialize export data to string."""
        if self._config.format == ExportFormat.JSONL:
            # JSONL: one entry per line
            lines = [json.dumps(data["export_metadata"])]
            lines.extend(json.dumps(entry) for entry in data["entries"])
            if "chain_state" in data:
                lines.append(json.dumps({"chain_state": data["chain_state"]}))
            return "\n".join(lines)
        else:
            # Default to JSON
            return json.dumps(data, indent=2)

    def _get_file_extension(self) -> str:
        """Get file extension for configured format."""
        extensions = {
            ExportFormat.JSON: ".json",
            ExportFormat.JSONL: ".jsonl",
            ExportFormat.CSV: ".csv",
        }
        return extensions.get(self._config.format, ".json")

    @staticmethod
    def _calculate_checksum(data: bytes) -> str:
        """Calculate SHA-256 checksum."""
        import hashlib

        return f"sha256:{hashlib.sha256(data).hexdigest()}"


class LocalStorageBackend:
    """Simple local filesystem storage backend for testing."""

    def __init__(self, base_path: str = "/tmp/audit_s3_mock"):
        self.base_path = base_path
        os.makedirs(base_path, exist_ok=True)

    def upload(
        self, key: str, data: bytes, metadata: dict[str, str] | None = None
    ) -> bool:
        """Upload to local filesystem."""
        try:
            file_path = os.path.join(self.base_path, key.lstrip("/"))
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "wb") as f:
                f.write(data)

            # Store metadata alongside
            if metadata:
                meta_path = file_path + ".metadata"
                with open(meta_path, "w") as f:
                    json.dump(metadata, f)

            return True
        except Exception as e:
            logger.error(f"Local storage upload failed: {e}")
            return False

    def download(self, key: str) -> bytes | None:
        """Download from local filesystem."""
        try:
            file_path = os.path.join(self.base_path, key.lstrip("/"))
            with open(file_path, "rb") as f:
                return f.read()
        except Exception:
            return None

    def delete(self, key: str) -> bool:
        """Delete from local filesystem."""
        try:
            file_path = os.path.join(self.base_path, key.lstrip("/"))
            os.remove(file_path)
            return True
        except Exception:
            return False

    def list_keys(self, prefix: str) -> list[str]:
        """List keys with prefix."""
        keys = []
        prefix_path = os.path.join(self.base_path, prefix.lstrip("/"))

        if not os.path.exists(prefix_path):
            return keys

        for root, _, files in os.walk(prefix_path):
            for file in files:
                if file.endswith(".metadata"):
                    continue
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, self.base_path)
                keys.append(rel_path)

        return keys
