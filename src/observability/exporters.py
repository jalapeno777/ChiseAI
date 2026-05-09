"""
OpenTelemetry Exporters Configuration

TEMPO-2026-001: OTLP exporter configuration for Tempo
ST-MVP-008: Dual-format metric export (Prometheus + InfluxDB)
"""

import os

from enum import Enum
from typing import Any

from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import ConsoleSpanExporter


class ExportFormat(Enum):
    """Supported metric export formats."""

    PROMETHEUS = "prometheus"
    INFLUXDB = "influxdb"
    BOTH = "both"


class DualFormatExporter:
    """Exports metrics in Prometheus text format, InfluxDB line protocol, or both.

    Handles metric name sanitization between formats automatically:
    - Prometheus: dots and hyphens become underscores, names lowercased
    - InfluxDB: dots allowed, hyphens become underscores for consistency

    Usage:
        exporter = DualFormatExporter(format=ExportFormat.BOTH)
        prom_lines, influx_lines = exporter.export_metrics(metrics_data)
    """

    def __init__(
        self,
        export_format: ExportFormat = ExportFormat.BOTH,
        namespace: str = "chiseai",
    ) -> None:
        """Initialize the dual-format exporter.

        Args:
            export_format: Which format(s) to export (prometheus, influxdb, both)
            namespace: Metric name prefix (default 'chiseai')
        """
        self.export_format = export_format
        self.namespace = namespace

    def _to_prometheus_text(
        self,
        metrics: dict[str, dict[str, Any]],
    ) -> str:
        """Convert metrics to Prometheus text exposition format.

        Args:
            metrics: Dict of metric_name -> {value, labels, type, help}
                where type is 'counter', 'gauge', or 'histogram'

        Returns:
            Prometheus text exposition format string
        """
        from ml.monitoring.registry_metrics import sanitize_metric_name

        lines: list[str] = []
        for raw_name, metric_data in metrics.items():
            name = sanitize_metric_name(f"{self.namespace}_{raw_name}", "prometheus")
            metric_type = metric_data.get("type", "gauge")
            help_text = metric_data.get("help", f"{name} metric")

            lines.append(f"# HELP {name} {help_text}")
            lines.append(f"# TYPE {name} {metric_type}")

            value = metric_data.get("value", 0)
            labels = metric_data.get("labels", {})

            if labels:
                label_str = ",".join(
                    f'{sanitize_metric_name(k, "prometheus")}="{v}"'
                    for k, v in labels.items()
                )
                lines.append(f"{name}{{{label_str}}} {value}")
            else:
                lines.append(f"{name} {value}")

        return "\n".join(lines) + "\n" if lines else ""

    def _to_influxdb_line_protocol(
        self,
        metrics: dict[str, dict[str, Any]],
        timestamp_ns: int | None = None,
    ) -> str:
        """Convert metrics to InfluxDB line protocol format.

        Format: measurement,tag1=val1,tag2=val2 field1=val1,field2=val2 timestamp

        Args:
            metrics: Dict of metric_name -> {value, tags, fields}
            timestamp_ns: Optional nanosecond timestamp (auto-generated if None)

        Returns:
            InfluxDB line protocol string (one line per metric)
        """
        from ml.monitoring.registry_metrics import sanitize_metric_name

        lines: list[str] = []
        for raw_name, metric_data in metrics.items():
            measurement = sanitize_metric_name(
                f"{self.namespace}_{raw_name}", "influxdb"
            )

            # Tags (indexed, for querying)
            tags = metric_data.get("tags", {})
            if tags:
                tag_parts = ",".join(
                    f"{sanitize_metric_name(k, 'influxdb')}={self._escape_influx_value(str(v))}"
                    for k, v in sorted(tags.items())
                )
                tag_section = f",{tag_parts}"
            else:
                tag_section = ""

            # Fields (data values)
            value = metric_data.get("value", 0)
            extra_fields = metric_data.get("fields", {})

            field_parts: list[str] = []
            if isinstance(value, int):
                field_parts.append(f"value={value}i")
            elif isinstance(value, float):
                field_parts.append(f"value={value}")
            else:
                field_parts.append(f'value="{value}"')

            for fk, fv in extra_fields.items():
                if isinstance(fv, int):
                    field_parts.append(f"{fk}={fv}i")
                elif isinstance(fv, float):
                    field_parts.append(f"{fk}={fv}")
                else:
                    field_parts.append(f'{fk}="{fv}"')

            field_section = ",".join(field_parts)

            # Timestamp
            ts = timestamp_ns or metric_data.get("timestamp")
            if ts is not None:
                lines.append(f"{measurement}{tag_section} {field_section} {ts}")
            else:
                lines.append(f"{measurement}{tag_section} {field_section}")

        return "\n".join(lines) + "\n" if lines else ""

    @staticmethod
    def _escape_influx_value(value: str) -> str:
        """Escape special characters in InfluxDB tag/field string values.

        Args:
            value: String value to escape

        Returns:
            Escaped string safe for InfluxDB line protocol
        """
        return value.replace(" ", "\\ ").replace(",", "\\,").replace("=", "\\=")

    def export_metrics(
        self,
        metrics: dict[str, dict[str, Any]],
        timestamp_ns: int | None = None,
    ) -> tuple[str, str]:
        """Export metrics in configured format(s).

        Args:
            metrics: Dict of metric_name -> metric data (see format-specific
                methods for expected keys)
            timestamp_ns: Optional nanosecond timestamp for InfluxDB

        Returns:
            Tuple of (prometheus_text, influxdb_lines). Empty string for
            formats not selected.
        """
        prom_text = ""
        influx_lines = ""

        if self.export_format in (ExportFormat.PROMETHEUS, ExportFormat.BOTH):
            prom_text = self._to_prometheus_text(metrics)
        if self.export_format in (ExportFormat.INFLUXDB, ExportFormat.BOTH):
            influx_lines = self._to_influxdb_line_protocol(metrics, timestamp_ns)

        return prom_text, influx_lines


def get_tempo_exporter(endpoint: str | None = None) -> OTLPSpanExporter:
    """
    Get OTLP exporter for Grafana Tempo.

    Args:
        endpoint: Tempo OTLP endpoint (defaults to TEMPO_ENDPOINT env var or http://chiseai-tempo:4317)

    Returns:
        OTLPSpanExporter configured for Tempo
    """
    tempo_endpoint = endpoint or os.getenv(
        "TEMPO_ENDPOINT", "http://chiseai-tempo:4317"
    )

    return OTLPSpanExporter(
        endpoint=tempo_endpoint,
        insecure=True,  # Internal network, TLS not required
        timeout=30,
    )


def get_console_exporter() -> ConsoleSpanExporter:
    """
    Get console exporter for debugging.

    Returns:
        ConsoleSpanExporter for local debugging
    """
    return ConsoleSpanExporter()


def get_exporter_for_environment():
    """
    Get appropriate exporter based on environment.

    Returns:
        Exporter instance
    """
    environment = os.getenv("DEPLOYMENT_ENVIRONMENT", "development")

    if (
        environment == "development"
        and os.getenv("OTEL_DEBUG", "false").lower() == "true"
    ):
        return get_console_exporter()

    return get_tempo_exporter()
