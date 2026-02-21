"""Exporter for calibration data.

This module provides functionality to export calibration records to various
formats (Parquet, CSV) for ECE analysis and external tooling.
"""

from __future__ import annotations

import csv
import json
import logging
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

from ml.calibration.models import CalibrationRecord, SignalType
from ml.calibration.storage import CalibrationStorage, InMemoryCalibrationStorage

logger = logging.getLogger(__name__)


class ExportFormat(Enum):
    """Supported export formats."""

    PARQUET = "parquet"
    CSV = "csv"
    JSON = "json"


class CalibrationExporter:
    """Exporter for calibration data.

    Provides methods to export calibration records to various formats
    for ECE analysis and integration with external tools.

    Example:
        >>> exporter = CalibrationExporter(storage)
        >>> exporter.export("data.parquet", ExportFormat.PARQUET)
        >>> exporter.export_for_ece("ece_data.csv", ExportFormat.CSV)
    """

    def __init__(self, storage: CalibrationStorage | None = None):
        """Initialize the exporter.

        Args:
            storage: Storage backend to export from (defaults to in-memory)
        """
        self.storage = storage or InMemoryCalibrationStorage()

    async def export(
        self,
        filepath: str,
        format: ExportFormat,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        signal_type: SignalType | None = None,
    ) -> bool:
        """Export calibration data to a file.

        Args:
            filepath: Path to output file
            format: Export format (PARQUET, CSV, or JSON)
            start_time: Optional start time filter
            end_time: Optional end time filter
            signal_type: Optional signal type filter

        Returns:
            True if export was successful
        """
        try:
            # Get records from storage
            from datetime import UTC, datetime as dt

            if end_time is None:
                end_time = dt.now(UTC)
            if start_time is None:
                from datetime import timedelta

                start_time = end_time - timedelta(days=30)

            records = await self.storage.get_records(
                start_time, end_time, signal_type, limit=100000
            )

            if not records:
                logger.warning("No records to export")
                return False

            # Export based on format
            if format == ExportFormat.PARQUET:
                return self._export_to_parquet(records, filepath)
            elif format == ExportFormat.CSV:
                return self._export_to_csv(records, filepath)
            elif format == ExportFormat.JSON:
                return self._export_to_json(records, filepath)
            else:
                logger.error(f"Unsupported export format: {format}")
                return False

        except Exception as e:
            logger.error(f"Failed to export calibration data: {e}")
            return False

    def _export_to_parquet(
        self, records: list[CalibrationRecord], filepath: str
    ) -> bool:
        """Export records to Parquet format.

        Args:
            records: List of calibration records
            filepath: Output file path

        Returns:
            True if successful
        """
        try:
            import pandas as pd

            # Convert records to dictionaries
            data = [r.to_dict() for r in records]

            # Create DataFrame
            df = pd.DataFrame(data)

            # Handle metadata column (convert dict to string or expand)
            if "metadata" in df.columns:
                df["metadata"] = df["metadata"].apply(json.dumps)

            # Write to Parquet
            df.to_parquet(filepath, index=False)

            logger.info(f"Exported {len(records)} records to Parquet: {filepath}")
            return True

        except ImportError:
            logger.error("pandas is required for Parquet export")
            return False

        except Exception as e:
            logger.error(f"Failed to export to Parquet: {e}")
            return False

    def _export_to_csv(self, records: list[CalibrationRecord], filepath: str) -> bool:
        """Export records to CSV format.

        Args:
            records: List of calibration records
            filepath: Output file path

        Returns:
            True if successful
        """
        try:
            if not records:
                return False

            # Get field names from first record
            fieldnames = [
                "timestamp",
                "signal_id",
                "predicted_prob",
                "actual_outcome",
                "signal_type",
                "confidence_bin",
                "strategy_id",
                "metadata",
            ]

            with open(filepath, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()

                for record in records:
                    row = record.to_dict()
                    # Convert metadata dict to JSON string
                    row["metadata"] = json.dumps(row.get("metadata", {}))
                    writer.writerow(row)

            logger.info(f"Exported {len(records)} records to CSV: {filepath}")
            return True

        except Exception as e:
            logger.error(f"Failed to export to CSV: {e}")
            return False

    def _export_to_json(self, records: list[CalibrationRecord], filepath: str) -> bool:
        """Export records to JSON format.

        Args:
            records: List of calibration records
            filepath: Output file path

        Returns:
            True if successful
        """
        try:
            data = {
                "records": [r.to_dict() for r in records],
                "count": len(records),
                "export_timestamp": datetime.now(UTC).isoformat(),
            }

            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

            logger.info(f"Exported {len(records)} records to JSON: {filepath}")
            return True

        except Exception as e:
            logger.error(f"Failed to export to JSON: {e}")
            return False

    async def export_for_ece(
        self,
        filepath: str,
        format: ExportFormat = ExportFormat.PARQUET,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        signal_type: SignalType | None = None,
    ) -> bool:
        """Export calibration data in ECE-compatible format.

        This format includes only the fields needed for ECE calculation:
        - confidence: predicted probability
        - outcome: actual outcome (0 or 1)
        - confidence_bin: bin index for grouping

        Args:
            filepath: Path to output file
            format: Export format (PARQUET or CSV)
            start_time: Optional start time filter
            end_time: Optional end time filter
            signal_type: Optional signal type filter

        Returns:
            True if export was successful
        """
        try:
            # Get records from storage
            from datetime import UTC, datetime as dt

            if end_time is None:
                end_time = dt.now(UTC)
            if start_time is None:
                from datetime import timedelta

                start_time = end_time - timedelta(days=30)

            records = await self.storage.get_records(
                start_time, end_time, signal_type, limit=100000
            )

            if not records:
                logger.warning("No records to export for ECE")
                return False

            # Convert to ECE format
            ece_data = [r.to_ece_format() for r in records]

            if format == ExportFormat.PARQUET:
                return self._export_ece_to_parquet(ece_data, filepath)
            elif format == ExportFormat.CSV:
                return self._export_ece_to_csv(ece_data, filepath)
            else:
                logger.error(f"Unsupported ECE export format: {format}")
                return False

        except Exception as e:
            logger.error(f"Failed to export for ECE: {e}")
            return False

    def _export_ece_to_parquet(
        self, ece_data: list[dict[str, Any]], filepath: str
    ) -> bool:
        """Export ECE-formatted data to Parquet.

        Args:
            ece_data: List of ECE-format dictionaries
            filepath: Output file path

        Returns:
            True if successful
        """
        try:
            import pandas as pd

            df = pd.DataFrame(ece_data)
            df.to_parquet(filepath, index=False)

            logger.info(f"Exported {len(ece_data)} ECE records to Parquet: {filepath}")
            return True

        except ImportError:
            logger.error("pandas is required for Parquet export")
            return False

        except Exception as e:
            logger.error(f"Failed to export ECE to Parquet: {e}")
            return False

    def _export_ece_to_csv(self, ece_data: list[dict[str, Any]], filepath: str) -> bool:
        """Export ECE-formatted data to CSV.

        Args:
            ece_data: List of ECE-format dictionaries
            filepath: Output file path

        Returns:
            True if successful
        """
        try:
            if not ece_data:
                return False

            fieldnames = ["confidence", "outcome"]

            with open(filepath, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(ece_data)

            logger.info(f"Exported {len(ece_data)} ECE records to CSV: {filepath}")
            return True

        except Exception as e:
            logger.error(f"Failed to export ECE to CSV: {e}")
            return False

    async def export_by_signal_type(
        self,
        base_filepath: str,
        format: ExportFormat = ExportFormat.PARQUET,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> dict[SignalType, bool]:
        """Export calibration data separately for each signal type.

        Args:
            base_filepath: Base path for output files (signal type will be appended)
            format: Export format
            start_time: Optional start time filter
            end_time: Optional end time filter

        Returns:
            Dictionary mapping SignalType to success status
        """
        results = {}

        for signal_type in SignalType:
            # Modify filepath to include signal type
            import os

            base, ext = os.path.splitext(base_filepath)
            filepath = f"{base}_{signal_type.value.lower()}{ext}"

            success = await self.export(
                filepath, format, start_time, end_time, signal_type
            )
            results[signal_type] = success

        return results
