"""Data collector for calibration analysis.

This module provides the main CalibrationDataCollector class for gathering
prediction probability vs actual outcome pairs for ECE analysis.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Sequence

from ml.calibration.models import (
    CalibrationConfig,
    CalibrationRecord,
    CollectionWindow,
    SignalType,
)
from ml.calibration.storage import (
    CalibrationStorage,
    InMemoryCalibrationStorage,
    RedisCalibrationStorage,
)

logger = logging.getLogger(__name__)


@dataclass
class CollectionResult:
    """Result of a collection operation.

    Attributes:
        success: Whether the collection was successful
        record: The CalibrationRecord that was collected (if successful)
        error_message: Error message if collection failed
        timestamp: When the collection was attempted
    """

    success: bool
    record: CalibrationRecord | None = None
    error_message: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "success": self.success,
            "record": self.record.to_dict() if self.record else None,
            "error_message": self.error_message,
            "timestamp": self.timestamp.isoformat(),
        }


class CalibrationDataCollector:
    """Collects prediction vs outcome pairs for calibration analysis.

    This class provides methods to:
    - Collect calibration data from signal predictions and outcomes
    - Store data efficiently using Redis time-series storage
    - Query records by time window and signal type
    - Export data for ECE (Expected Calibration Error) analysis

    Example:
        >>> collector = CalibrationDataCollector()
        >>> result = collector.collect(
        ...     signal_id="test-sig-001",
        ...     predicted_prob=0.75,
        ...     actual_outcome=1,
        ...     signal_type="LONG"
        ... )
        >>> records = collector.get_records(window="24h")
        >>> collector.export_to_parquet("calibration_data.parquet")
    """

    def __init__(
        self,
        config: CalibrationConfig | None = None,
        storage: CalibrationStorage | None = None,
    ):
        """Initialize the calibration data collector.

        Args:
            config: Configuration for the collector
            storage: Storage backend (defaults to Redis if available, else in-memory)
        """
        self.config = config or CalibrationConfig()
        self._storage = storage
        self._collection_stats: dict[str, Any] = {
            "total_collected": 0,
            "total_failed": 0,
            "by_signal_type": {},
        }

    def _get_storage(self) -> CalibrationStorage:
        """Get or create storage backend.

        Returns:
            CalibrationStorage instance
        """
        if self._storage is None:
            # Try Redis first, fall back to in-memory
            try:
                self._storage = RedisCalibrationStorage(self.config)
                logger.info("Using Redis calibration storage")
            except Exception as e:
                logger.warning(
                    f"Failed to connect to Redis, using in-memory storage: {e}"
                )
                self._storage = InMemoryCalibrationStorage(self.config)

        return self._storage

    def collect(
        self,
        signal_id: str,
        predicted_prob: float,
        actual_outcome: int,
        signal_type: str | SignalType,
        timestamp: datetime | None = None,
        strategy_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CollectionResult:
        """Collect a single calibration record.

        Args:
            signal_id: Unique signal identifier
            predicted_prob: Predicted probability of success (0.0-1.0)
            actual_outcome: Actual outcome (1=win, 0=loss)
            signal_type: Type of signal (LONG, SHORT, SCALP)
            timestamp: Optional timestamp (defaults to now)
            strategy_id: Optional strategy identifier
            metadata: Optional additional metadata

        Returns:
            CollectionResult with success status and record
        """
        try:
            # Convert signal_type to enum if string
            if isinstance(signal_type, str):
                signal_type = SignalType(signal_type.upper())

            # Calculate confidence bin
            confidence_bin = CalibrationRecord.calculate_confidence_bin(predicted_prob)

            # Create timestamp if not provided
            if timestamp is None:
                timestamp = datetime.now(UTC)

            # Create the calibration record
            record = CalibrationRecord(
                timestamp=timestamp,
                signal_id=signal_id,
                predicted_prob=predicted_prob,
                actual_outcome=actual_outcome,
                signal_type=signal_type,
                confidence_bin=confidence_bin,
                strategy_id=strategy_id,
                metadata=metadata or {},
            )

            # Store the record
            storage = self._get_storage()
            # Note: storage.store is async, but we're in sync context
            # We'll use asyncio.run for now, but this could be optimized
            import asyncio

            success = asyncio.run(storage.store(record))

            if success:
                self._collection_stats["total_collected"] += 1
                st_key = signal_type.value
                self._collection_stats["by_signal_type"][st_key] = (
                    self._collection_stats["by_signal_type"].get(st_key, 0) + 1
                )

                logger.debug(f"Collected calibration record for {signal_id}")
                return CollectionResult(success=True, record=record)
            else:
                self._collection_stats["total_failed"] += 1
                return CollectionResult(
                    success=False,
                    error_message="Failed to store calibration record",
                )

        except ValueError as e:
            self._collection_stats["total_failed"] += 1
            logger.error(f"Validation error collecting calibration data: {e}")
            return CollectionResult(success=False, error_message=str(e))

        except Exception as e:
            self._collection_stats["total_failed"] += 1
            logger.exception(f"Unexpected error collecting calibration data: {e}")
            return CollectionResult(success=False, error_message=str(e))

    async def collect_async(
        self,
        signal_id: str,
        predicted_prob: float,
        actual_outcome: int,
        signal_type: str | SignalType,
        timestamp: datetime | None = None,
        strategy_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CollectionResult:
        """Collect a single calibration record (async version).

        Args:
            signal_id: Unique signal identifier
            predicted_prob: Predicted probability of success (0.0-1.0)
            actual_outcome: Actual outcome (1=win, 0=loss)
            signal_type: Type of signal (LONG, SHORT, SCALP)
            timestamp: Optional timestamp (defaults to now)
            strategy_id: Optional strategy identifier
            metadata: Optional additional metadata

        Returns:
            CollectionResult with success status and record
        """
        try:
            # Convert signal_type to enum if string
            if isinstance(signal_type, str):
                signal_type = SignalType(signal_type.upper())

            # Calculate confidence bin
            confidence_bin = CalibrationRecord.calculate_confidence_bin(predicted_prob)

            # Create timestamp if not provided
            if timestamp is None:
                timestamp = datetime.now(UTC)

            # Create the calibration record
            record = CalibrationRecord(
                timestamp=timestamp,
                signal_id=signal_id,
                predicted_prob=predicted_prob,
                actual_outcome=actual_outcome,
                signal_type=signal_type,
                confidence_bin=confidence_bin,
                strategy_id=strategy_id,
                metadata=metadata or {},
            )

            # Store the record
            storage = self._get_storage()
            success = await storage.store(record)

            if success:
                self._collection_stats["total_collected"] += 1
                st_key = signal_type.value
                self._collection_stats["by_signal_type"][st_key] = (
                    self._collection_stats["by_signal_type"].get(st_key, 0) + 1
                )

                logger.debug(f"Collected calibration record for {signal_id}")
                return CollectionResult(success=True, record=record)
            else:
                self._collection_stats["total_failed"] += 1
                return CollectionResult(
                    success=False,
                    error_message="Failed to store calibration record",
                )

        except ValueError as e:
            self._collection_stats["total_failed"] += 1
            logger.error(f"Validation error collecting calibration data: {e}")
            return CollectionResult(success=False, error_message=str(e))

        except Exception as e:
            self._collection_stats["total_failed"] += 1
            logger.exception(f"Unexpected error collecting calibration data: {e}")
            return CollectionResult(success=False, error_message=str(e))

    async def collect_batch(
        self,
        records_data: Sequence[dict[str, Any]],
    ) -> list[CollectionResult]:
        """Collect multiple calibration records in batch.

        Args:
            records_data: List of dictionaries containing record data
                Each dict should have: signal_id, predicted_prob, actual_outcome,
                signal_type, and optionally: timestamp, strategy_id, metadata

        Returns:
            List of CollectionResult objects (in same order as input)
        """
        # First pass: validate and create records, track which ones are valid
        validation_results = []
        calibration_records = []
        valid_indices = []

        for idx, data in enumerate(records_data):
            try:
                signal_type = data["signal_type"]
                if isinstance(signal_type, str):
                    signal_type = SignalType(signal_type.upper())

                predicted_prob = data["predicted_prob"]
                confidence_bin = CalibrationRecord.calculate_confidence_bin(
                    predicted_prob
                )

                timestamp = data.get("timestamp", datetime.now(UTC))
                if timestamp is None:
                    timestamp = datetime.now(UTC)

                record = CalibrationRecord(
                    timestamp=timestamp,
                    signal_id=data["signal_id"],
                    predicted_prob=predicted_prob,
                    actual_outcome=data["actual_outcome"],
                    signal_type=signal_type,
                    confidence_bin=confidence_bin,
                    strategy_id=data.get("strategy_id"),
                    metadata=data.get("metadata", {}),
                )
                calibration_records.append(record)
                valid_indices.append(idx)
                validation_results.append(None)  # Placeholder for valid record

            except (ValueError, KeyError) as e:
                validation_results.append(
                    CollectionResult(
                        success=False,
                        error_message=f"Validation error: {e}",
                    )
                )

        # Store batch
        if calibration_records:
            storage = self._get_storage()
            stored_count = await storage.store_batch(calibration_records)

            # Create results for stored records in order
            for i, idx in enumerate(valid_indices):
                record = calibration_records[i]
                if i < stored_count:
                    self._collection_stats["total_collected"] += 1
                    st_key = record.signal_type.value
                    self._collection_stats["by_signal_type"][st_key] = (
                        self._collection_stats["by_signal_type"].get(st_key, 0) + 1
                    )
                    validation_results[idx] = CollectionResult(
                        success=True, record=record
                    )
                else:
                    self._collection_stats["total_failed"] += 1
                    validation_results[idx] = CollectionResult(
                        success=False,
                        error_message="Failed to store in batch",
                    )

        return validation_results

    def get_records(
        self,
        window: str | CollectionWindow = "24h",
        signal_type: str | SignalType | None = None,
        limit: int = 10000,
    ) -> list[CalibrationRecord]:
        """Get calibration records for a time window.

        Args:
            window: Time window ("1h", "24h", "7d", "30d") or CollectionWindow
            signal_type: Optional signal type filter
            limit: Maximum number of records to return

        Returns:
            List of CalibrationRecord objects
        """
        # Convert window string to enum if needed
        if isinstance(window, str):
            window = CollectionWindow(window)

        # Convert signal_type to enum if string
        if isinstance(signal_type, str):
            signal_type = SignalType(signal_type.upper())

        # Calculate time range
        end_time = datetime.now(UTC)
        start_time = end_time - timedelta(hours=window.to_hours())

        # Query storage
        storage = self._get_storage()
        import asyncio

        records = cast(
            list[CalibrationRecord],
            asyncio.run(storage.get_records(start_time, end_time, signal_type, limit)),
        )

        return records

    async def get_records_async(
        self,
        window: str | CollectionWindow = "24h",
        signal_type: str | SignalType | None = None,
        limit: int = 10000,
    ) -> list[CalibrationRecord]:
        """Get calibration records for a time window (async version).

        Args:
            window: Time window ("1h", "24h", "7d", "30d") or CollectionWindow
            signal_type: Optional signal type filter
            limit: Maximum number of records to return

        Returns:
            List of CalibrationRecord objects
        """
        # Convert window string to enum if needed
        if isinstance(window, str):
            window = CollectionWindow(window)

        # Convert signal_type to enum if string
        if isinstance(signal_type, str):
            signal_type = SignalType(signal_type.upper())

        # Calculate time range
        end_time = datetime.now(UTC)
        start_time = end_time - timedelta(hours=window.to_hours())

        # Query storage
        storage = self._get_storage()
        records = cast(
            list[CalibrationRecord],
            await storage.get_records(start_time, end_time, signal_type, limit),
        )

        return records

    def get_records_by_confidence_bin(
        self,
        bin_index: int,
        window: str | CollectionWindow = "24h",
        signal_type: str | SignalType | None = None,
    ) -> list[CalibrationRecord]:
        """Get calibration records filtered by confidence bin.

        Args:
            bin_index: Confidence bin index (0-9)
            window: Time window
            signal_type: Optional signal type filter

        Returns:
            List of CalibrationRecord objects in the specified bin
        """
        records = self.get_records(window, signal_type)
        return [r for r in records if r.confidence_bin == bin_index]

    def get_statistics(self) -> dict[str, Any]:
        """Get collection statistics.

        Returns:
            Dictionary with collection statistics
        """
        return {
            "total_collected": self._collection_stats["total_collected"],
            "total_failed": self._collection_stats["total_failed"],
            "by_signal_type": self._collection_stats["by_signal_type"].copy(),
            "success_rate": (
                self._collection_stats["total_collected"]
                / (
                    self._collection_stats["total_collected"]
                    + self._collection_stats["total_failed"]
                )
                if (
                    self._collection_stats["total_collected"]
                    + self._collection_stats["total_failed"]
                )
                > 0
                else 0.0
            ),
        }

    def clear_statistics(self) -> None:
        """Clear collection statistics."""
        self._collection_stats = {
            "total_collected": 0,
            "total_failed": 0,
            "by_signal_type": {},
        }

    async def cleanup_old_records(self) -> int:
        """Clean up records older than the retention period.

        Returns:
            Number of deleted records
        """
        retention_days = self.config.retention_days
        cutoff_time = datetime.now(UTC) - timedelta(days=retention_days)

        storage = self._get_storage()
        deleted_count = cast(int, await storage.delete_old_records(cutoff_time))

        logger.info(f"Cleaned up {deleted_count} old calibration records")
        return deleted_count

    async def close(self) -> None:
        """Close the collector and release resources."""
        if self._storage:
            await self._storage.close()
            self._storage = None

    def export_to_parquet(self, filepath: str) -> bool:
        """Export calibration data to Parquet format.

        Args:
            filepath: Path to output Parquet file

        Returns:
            True if export successful
        """
        try:
            import asyncio

            from ml.calibration.exporter import CalibrationExporter, ExportFormat

            exporter = CalibrationExporter(self._get_storage())
            return cast(
                bool, asyncio.run(exporter.export(filepath, ExportFormat.PARQUET))
            )

        except Exception as e:
            logger.error(f"Failed to export to Parquet: {e}")
            return False

    def export_to_csv(self, filepath: str) -> bool:
        """Export calibration data to CSV format.

        Args:
            filepath: Path to output CSV file

        Returns:
            True if export successful
        """
        try:
            import asyncio

            from ml.calibration.exporter import CalibrationExporter, ExportFormat

            exporter = CalibrationExporter(self._get_storage())
            return cast(bool, asyncio.run(exporter.export(filepath, ExportFormat.CSV)))

        except Exception as e:
            logger.error(f"Failed to export to CSV: {e}")
            return False

    def export_for_ece(self, filepath: str, format: str = "parquet") -> bool:
        """Export calibration data in ECE-compatible format.

        Args:
            filepath: Path to output file
            format: Export format ("parquet" or "csv")

        Returns:
            True if export successful
        """
        try:
            import asyncio

            from ml.calibration.exporter import CalibrationExporter, ExportFormat

            export_format = (
                ExportFormat.PARQUET if format == "parquet" else ExportFormat.CSV
            )
            exporter = CalibrationExporter(self._get_storage())
            return cast(
                bool, asyncio.run(exporter.export_for_ece(filepath, export_format))
            )

        except Exception as e:
            logger.error(f"Failed to export for ECE: {e}")
            return False
