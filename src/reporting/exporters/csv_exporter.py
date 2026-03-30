"""CSV export module for report data.

Provides CSV serialization with configurable column selection,
UTF-8 encoding, and proper escaping.

For ST-NS-023-T2: Report Delivery & Dashboard Integration
"""

from __future__ import annotations

import csv
import io
import logging
from typing import Any

logger = logging.getLogger(__name__)


class CSVExporter:
    """CSV report exporter with column selection.

    Features:
    - Configurable column selection
    - UTF-8 encoding with BOM support
    - Proper CSV escaping
    - Nested field flattening
    - Header row generation

    Attributes:
        delimiter: CSV delimiter character
        quotechar: Quote character for fields
        include_bom: Include UTF-8 BOM for Excel compatibility
    """

    def __init__(
        self,
        delimiter: str = ",",
        quotechar: str = '"',
        include_bom: bool = False,
    ) -> None:
        """Initialize CSV exporter.

        Args:
            delimiter: CSV field delimiter
            quotechar: Character for quoting fields
            include_bom: Include UTF-8 BOM for Excel
        """
        self.delimiter = delimiter
        self.quotechar = quotechar
        self.include_bom = include_bom

    def _flatten_dict(
        self,
        data: dict[str, Any],
        parent_key: str = "",
        sep: str = ".",
    ) -> dict[str, Any]:
        """Flatten nested dictionary to dot-notation keys.

        Args:
            data: Dictionary to flatten
            parent_key: Parent key prefix
            sep: Separator for nested keys

        Returns:
            Flattened dictionary
        """
        items: dict[str, Any] = {}

        for key, value in data.items():
            new_key = f"{parent_key}{sep}{key}" if parent_key else key

            if isinstance(value, dict):
                items.update(self._flatten_dict(value, new_key, sep))
            elif isinstance(value, list):
                # Convert list to JSON string representation
                items[new_key] = str(value)
            else:
                items[new_key] = value

        return items

    def _prepare_row(
        self,
        data: dict[str, Any],
        columns: list[str] | None,
    ) -> dict[str, Any]:
        """Prepare data row with column selection.

        Args:
            data: Row data dictionary
            columns: List of columns to include (None = all)

        Returns:
            Filtered dictionary
        """
        flattened = self._flatten_dict(data)

        if columns is None:
            return flattened

        return {k: flattened.get(k, "") for k in columns}

    def export(
        self,
        data: list[dict[str, Any]],
        columns: list[str] | None = None,
    ) -> str:
        """Export list of dictionaries to CSV string.

        Args:
            data: List of row dictionaries
            columns: List of columns to include (None = all)

        Returns:
            CSV string
        """
        if not data:
            return ""

        # Determine columns from first row if not specified
        if columns is None:
            flattened_sample = self._flatten_dict(data[0])
            columns = list(flattened_sample.keys())

        # Flatten all rows
        flattened_data = [self._prepare_row(row, columns) for row in data]

        # Write CSV
        output = io.StringIO()
        output.write("\ufeff" if self.include_bom else "")  # BOM

        writer = csv.DictWriter(
            output,
            fieldnames=columns,
            delimiter=self.delimiter,
            quotechar=self.quotechar,
            quoting=csv.QUOTE_MINIMAL,
            extrasaction="ignore",
        )

        writer.writeheader()
        writer.writerows(flattened_data)

        return output.getvalue()

    def export_to_bytes(
        self,
        data: list[dict[str, Any]],
        columns: list[str] | None = None,
    ) -> bytes:
        """Export to CSV bytes.

        Args:
            data: List of row dictionaries
            columns: List of columns to include

        Returns:
            CSV bytes
        """
        return self.export(data, columns).encode("utf-8-sig")

    def export_single(
        self,
        data: dict[str, Any],
        columns: list[str] | None = None,
    ) -> str:
        """Export single record to CSV (with header).

        Args:
            data: Single record dictionary
            columns: List of columns to include

        Returns:
            CSV string with header
        """
        return self.export([data], columns)

    def export_report(
        self,
        report: Any,
        columns: list[str] | None = None,
    ) -> str:
        """Export report object to CSV.

        Args:
            report: Report object with to_dict() method
            columns: List of columns to include

        Returns:
            CSV string
        """
        data = report.to_dict() if hasattr(report, "to_dict") else report

        # Handle different report structures
        if "daily_breakdown" in data and isinstance(data["daily_breakdown"], list):
            # Weekly report with daily breakdown
            return self.export(data["daily_breakdown"], columns)
        elif isinstance(data, dict):
            # Single report - convert to list
            return self.export([data], columns)

        return self.export([], columns)

    def get_column_names(
        self,
        data: list[dict[str, Any]],
    ) -> list[str]:
        """Extract all possible column names from data.

        Args:
            data: List of row dictionaries

        Returns:
            List of unique column names
        """
        columns: set[str] = set()

        for row in data:
            flattened = self._flatten_dict(row)
            columns.update(flattened.keys())

        return sorted(list(columns))
