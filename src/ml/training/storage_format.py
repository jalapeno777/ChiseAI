"""Storage format handlers for training data.

Provides export/import functionality for multiple formats:
- Parquet (primary): Compressed, columnar format for ML
- CSV (secondary): Human-readable for analysis
- JSON (metadata): Schema and statistics
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from ml.training.version import SchemaVersionManager


class FormatHandler(Protocol):
    """Protocol for format handlers."""

    def export(self, data: list[dict[str, Any]], path: Path) -> bool:
        """Export data to file."""
        ...

    def import_data(self, path: Path) -> list[dict[str, Any]]:
        """Import data from file."""
        ...

    def validate(self, path: Path) -> tuple[bool, str]:
        """Validate file format and content."""
        ...


@dataclass
class DatasetMetadata:
    """Metadata for training dataset.

    Attributes:
        schema_version: Schema version used
        created_at: Creation timestamp
        sample_count: Number of samples
        feature_count: Number of features
        label_count: Number of labels
        tokens: List of tokens in dataset
        timeframes: List of timeframes in dataset
        statistics: Dataset statistics
    """

    schema_version: str
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    sample_count: int = 0
    feature_count: int = 0
    label_count: int = 0
    tokens: list[str] = field(default_factory=list)
    timeframes: list[str] = field(default_factory=list)
    statistics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "sample_count": self.sample_count,
            "feature_count": self.feature_count,
            "label_count": self.label_count,
            "tokens": self.tokens,
            "timeframes": self.timeframes,
            "statistics": self.statistics,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DatasetMetadata:
        """Create from dictionary."""
        return cls(
            schema_version=data.get("schema_version", "1.0.0"),
            created_at=data.get("created_at", datetime.now().isoformat()),
            sample_count=data.get("sample_count", 0),
            feature_count=data.get("feature_count", 0),
            label_count=data.get("label_count", 0),
            tokens=data.get("tokens", []),
            timeframes=data.get("timeframes", []),
            statistics=data.get("statistics", {}),
        )


class ParquetHandler:
    """Handler for Parquet format (primary storage)."""

    def __init__(self) -> None:
        """Initialize handler."""
        self._pyarrow_available = self._check_pyarrow()

    def _check_pyarrow(self) -> bool:
        """Check if pyarrow is available."""
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq

            return True
        except ImportError:
            return False

    def export(self, data: list[dict[str, Any]], path: Path) -> bool:
        """Export data to Parquet file.

        Args:
            data: List of sample dictionaries
            path: Output file path

        Returns:
            True if successful
        """
        if not self._pyarrow_available:
            raise ImportError("pyarrow is required for Parquet export")

        import pyarrow as pa
        import pyarrow.parquet as pq

        if not data:
            # Create empty table with expected schema
            schema = self._get_schema()
            table = pa.Table.from_pydict({}, schema=schema)
        else:
            # Convert to PyArrow table
            table = pa.Table.from_pylist(data)

        # Write with compression
        pq.write_table(
            table,
            path,
            compression="zstd",
            use_dictionary=True,
        )
        return True

    def _get_schema(self) -> Any:
        """Get expected schema for empty table."""
        import pyarrow as pa

        return pa.schema(
            [
                ("sample_id", pa.string()),
                ("timestamp", pa.string()),
                ("schema_version", pa.string()),
                ("token", pa.string()),
                ("timeframe", pa.string()),
                ("rsi", pa.float64()),
                ("macd", pa.float64()),
                ("macd_signal", pa.float64()),
                ("macd_histogram", pa.float64()),
                ("bb_upper", pa.float64()),
                ("bb_lower", pa.float64()),
                ("bb_width", pa.float64()),
                ("atr", pa.float64()),
                ("volume_sma", pa.float64()),
                ("trend_state", pa.string()),
                ("confluence_score", pa.float64()),
                ("confidence", pa.float64()),
                ("direction", pa.string()),
                ("entry_price", pa.float64()),
                ("price_change_24h", pa.float64()),
                ("volatility", pa.float64()),
                ("outcome", pa.int64()),
                ("pnl_percent", pa.float64()),
                ("holding_period_minutes", pa.int64()),
                ("predicted_prob", pa.float64()),
                ("confidence_bin", pa.int64()),
            ]
        )

    def import_data(self, path: Path) -> list[dict[str, Any]]:
        """Import data from Parquet file.

        Args:
            path: Input file path

        Returns:
            List of sample dictionaries
        """
        if not self._pyarrow_available:
            raise ImportError("pyarrow is required for Parquet import")

        import pyarrow.parquet as pq

        table = pq.read_table(path)
        return table.to_pylist()

    def validate(self, path: Path) -> tuple[bool, str]:
        """Validate Parquet file.

        Args:
            path: File path to validate

        Returns:
            Tuple of (is_valid, message)
        """
        if not self._pyarrow_available:
            return False, "pyarrow not available"

        try:
            import pyarrow.parquet as pq

            # Try to read metadata
            metadata = pq.read_metadata(path)

            # Check row count
            if metadata.num_rows == 0:
                return False, "Parquet file is empty"

            return True, f"Valid Parquet file with {metadata.num_rows} rows"
        except Exception as e:
            return False, f"Invalid Parquet file: {e}"


class CSVHandler:
    """Handler for CSV format (human-readable)."""

    def export(self, data: list[dict[str, Any]], path: Path) -> bool:
        """Export data to CSV file.

        Args:
            data: List of sample dictionaries
            path: Output file path

        Returns:
            True if successful
        """
        import csv

        if not data:
            # Create empty file with headers
            with open(path, "w", newline="", encoding="utf-8") as f:
                pass
            return True

        # Get all fieldnames from all samples
        fieldnames_set: set[str] = set()
        for sample in data:
            fieldnames_set.update(sample.keys())
        fieldnames: list[str] = sorted(fieldnames_set)

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)

        return True

    def import_data(self, path: Path) -> list[dict[str, Any]]:
        """Import data from CSV file.

        Args:
            path: Input file path

        Returns:
            List of sample dictionaries
        """
        import csv

        data = []
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Convert numeric strings to numbers
                converted: dict[str, Any] = {}
                for key, value in row.items():
                    if value == "":
                        converted[key] = None
                    else:
                        try:
                            converted[key] = int(value)
                        except ValueError:
                            try:
                                converted[key] = float(value)
                            except ValueError:
                                converted[key] = value
                data.append(converted)

        return data

    def validate(self, path: Path) -> tuple[bool, str]:
        """Validate CSV file.

        Args:
            path: File path to validate

        Returns:
            Tuple of (is_valid, message)
        """
        import csv

        try:
            with open(path, newline="", encoding="utf-8") as f:
                reader = csv.reader(f)
                rows = list(reader)

                if len(rows) == 0:
                    return False, "CSV file is empty"

                if len(rows) == 1:
                    return False, "CSV file has headers but no data"

                header_count = len(rows[0])
                for i, row in enumerate(rows[1:], 1):
                    if len(row) != header_count:
                        return (
                            False,
                            f"Row {i} has {len(row)} columns, expected {header_count}",
                        )

                return True, f"Valid CSV file with {len(rows) - 1} data rows"
        except Exception as e:
            return False, f"Invalid CSV file: {e}"


class JSONHandler:
    """Handler for JSON format (metadata)."""

    def export(self, data: list[dict[str, Any]], path: Path) -> bool:
        """Export data to JSON file.

        Args:
            data: List of sample dictionaries
            path: Output file path

        Returns:
            True if successful
        """
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        return True

    def import_data(self, path: Path) -> list[dict[str, Any]]:
        """Import data from JSON file.

        Args:
            path: Input file path

        Returns:
            List of sample dictionaries
        """
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def validate(self, path: Path) -> tuple[bool, str]:
        """Validate JSON file.

        Args:
            path: File path to validate

        Returns:
            Tuple of (is_valid, message)
        """
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, list):
                return False, "JSON file does not contain a list"

            return True, f"Valid JSON file with {len(data)} items"
        except json.JSONDecodeError as e:
            return False, f"Invalid JSON: {e}"
        except Exception as e:
            return False, f"Error reading JSON: {e}"


class StorageFormatManager:
    """Manages multiple storage formats."""

    def __init__(self) -> None:
        """Initialize format manager."""
        self.handlers: dict[str, FormatHandler] = {
            "parquet": ParquetHandler(),
            "csv": CSVHandler(),
            "json": JSONHandler(),
        }
        self.version_manager = SchemaVersionManager()

    def export(
        self,
        data: list[dict[str, Any]],
        path: Path,
        format_type: str,
    ) -> bool:
        """Export data to specified format.

        Args:
            data: List of sample dictionaries
            path: Output file path
            format_type: Format type (parquet, csv, json)

        Returns:
            True if successful

        Raises:
            ValueError: If format type is not supported
        """
        if format_type not in self.handlers:
            raise ValueError(f"Unsupported format: {format_type}")

        return self.handlers[format_type].export(data, path)

    def import_data(self, path: Path, format_type: str) -> list[dict[str, Any]]:
        """Import data from specified format.

        Args:
            path: Input file path
            format_type: Format type (parquet, csv, json)

        Returns:
            List of sample dictionaries
        """
        if format_type not in self.handlers:
            raise ValueError(f"Unsupported format: {format_type}")

        return self.handlers[format_type].import_data(path)

    def validate(self, path: Path, format_type: str) -> tuple[bool, str]:
        """Validate file in specified format.

        Args:
            path: File path to validate
            format_type: Format type (parquet, csv, json)

        Returns:
            Tuple of (is_valid, message)
        """
        if format_type not in self.handlers:
            return False, f"Unsupported format: {format_type}"

        return self.handlers[format_type].validate(path)

    def export_with_metadata(
        self,
        data: list[dict[str, Any]],
        base_path: Path,
        format_type: str,
        metadata: DatasetMetadata | None = None,
    ) -> tuple[bool, DatasetMetadata]:
        """Export data with metadata file.

        Args:
            data: List of sample dictionaries
            base_path: Base file path (without extension)
            format_type: Primary format type (parquet, csv, json)
            metadata: Optional metadata (auto-generated if not provided)

        Returns:
            Tuple of (success, metadata)
        """
        # Export data
        data_path = base_path.with_suffix(f".{format_type}")
        success = self.export(data, data_path, format_type)

        if not success:
            return False, metadata or DatasetMetadata(
                schema_version=self.version_manager.get_version_string()
            )

        # Generate or update metadata
        if metadata is None:
            metadata = self._generate_metadata(data)

        # Export metadata as JSON
        metadata_path = base_path.with_suffix(".metadata.json")
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata.to_dict(), f, indent=2)

        return True, metadata

    def _generate_metadata(self, data: list[dict[str, Any]]) -> DatasetMetadata:
        """Generate metadata from data."""
        if not data:
            return DatasetMetadata(
                schema_version=self.version_manager.get_version_string()
            )

        # Collect unique values
        tokens = set()
        timeframes = set()

        for sample in data:
            if "token" in sample and sample["token"]:
                tokens.add(sample["token"])
            if "timeframe" in sample and sample["timeframe"]:
                timeframes.add(sample["timeframe"])

        # Calculate statistics
        outcomes: list[Any] = [
            s.get("outcome") for s in data if s.get("outcome") is not None
        ]
        pnl_values: list[Any] = [
            s.get("pnl_percent") for s in data if s.get("pnl_percent") is not None
        ]

        statistics = {
            "win_rate": outcomes.count(1) / len(outcomes) if outcomes else 0.0,
            "avg_pnl": sum(pnl_values) / len(pnl_values) if pnl_values else 0.0,
            "outcome_distribution": (
                {
                    "wins": outcomes.count(1),
                    "losses": outcomes.count(0),
                }
                if outcomes
                else {}
            ),
        }

        return DatasetMetadata(
            schema_version=self.version_manager.get_version_string(),
            sample_count=len(data),
            tokens=sorted(tokens),
            timeframes=sorted(timeframes),
            statistics=statistics,
        )

    def get_supported_formats(self) -> list[str]:
        """Get list of supported format types."""
        return list(self.handlers.keys())
