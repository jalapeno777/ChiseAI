"""
OpenTelemetry Exporters Configuration

TEMPO-2026-001: OTLP exporter configuration for Tempo
"""

import os

from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import ConsoleSpanExporter


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
