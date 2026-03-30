"""JSON export module for report data.

Provides JSON serialization with schema compliance,
pretty-printing, and configurable output options.

For ST-NS-023-T2: Report Delivery & Dashboard Integration
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


class JSONExporter:
    """JSON report exporter with schema support.

    Features:
    - Schema-compliant JSON output
    - Pretty-printing option
    - Custom datetime serialization
    - Configurable indentation

    Attributes:
        pretty: Whether to use pretty printing
        indent: Indentation spaces (default: 2)
        ensure_ascii: Whether to escape non-ASCII characters
    """

    def __init__(
        self,
        pretty: bool = True,
        indent: int = 2,
        ensure_ascii: bool = False,
    ) -> None:
        """Initialize JSON exporter.

        Args:
            pretty: Enable pretty printing
            indent: Number of spaces for indentation
            ensure_ascii: Escape non-ASCII characters
        """
        self.pretty = pretty
        self.indent = indent
        self.ensure_ascii = ensure_ascii

    def _json_serializer(self, obj: Any) -> Any:
        """Custom JSON serializer for special types.

        Args:
            obj: Object to serialize

        Returns:
            JSON-serializable representation
        """
        if isinstance(obj, datetime):
            return obj.isoformat()
        if hasattr(obj, "to_dict"):
            return obj.to_dict()
        if hasattr(obj, "__dict__"):
            return obj.__dict__
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

    def export(self, data: dict[str, Any]) -> str:
        """Export data to JSON string.

        Args:
            data: Report data dictionary

        Returns:
            JSON string
        """
        try:
            if self.pretty:
                return json.dumps(
                    data,
                    indent=self.indent,
                    ensure_ascii=self.ensure_ascii,
                    default=self._json_serializer,
                )
            return json.dumps(
                data,
                ensure_ascii=self.ensure_ascii,
                default=self._json_serializer,
            )
        except Exception as e:
            logger.error(f"Failed to export JSON: {e}")
            raise

    def export_to_bytes(self, data: dict[str, Any]) -> bytes:
        """Export data to JSON bytes.

        Args:
            data: Report data dictionary

        Returns:
            JSON bytes
        """
        return self.export(data).encode("utf-8")

    def export_report(
        self,
        report: Any,
        pretty: bool | None = None,
    ) -> str:
        """Export report object to JSON.

        Args:
            report: Report object with to_dict() method
            pretty: Override pretty printing setting

        Returns:
            JSON string
        """
        data = report.to_dict() if hasattr(report, "to_dict") else report

        if pretty is not None:
            original_pretty = self.pretty
            self.pretty = pretty
            result = self.export(data)
            self.pretty = original_pretty
            return result

        return self.export(data)

    def validate_schema(
        self,
        data: dict[str, Any],
        required_fields: list[str],
    ) -> tuple[bool, list[str]]:
        """Validate that data contains required fields.

        Args:
            data: Data dictionary to validate
            required_fields: List of required field names

        Returns:
            Tuple of (is_valid, missing_fields)
        """
        missing = []
        for field in required_fields:
            if field not in data:
                missing.append(field)
        return (len(missing) == 0, missing)

    def export_with_metadata(
        self,
        data: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Export data with metadata wrapper.

        Args:
            data: Main data to export
            metadata: Optional metadata fields

        Returns:
            JSON string with metadata
        """
        wrapper = {
            "exported_at": datetime.now(UTC).isoformat(),
            "data": data,
        }

        if metadata:
            wrapper["metadata"] = metadata

        return self.export(wrapper)
