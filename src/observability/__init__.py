"""
ChiseAI Observability Module

TEMPO-2026-001: Distributed tracing with Grafana Tempo
"""

from .tracing import (
    init_tracing,
    instrument_fastapi,
    instrument_sqlalchemy,
    instrument_redis,
    instrument_requests,
    get_tempo_exporter,
    shutdown_tracing,
    get_sampler,
)

from .exporters import (
    get_tempo_exporter,
    get_console_exporter,
    get_exporter_for_environment,
)

__all__ = [
    "init_tracing",
    "instrument_fastapi",
    "instrument_sqlalchemy",
    "instrument_redis",
    "instrument_requests",
    "get_tempo_exporter",
    "shutdown_tracing",
    "get_sampler",
    "get_console_exporter",
    "get_exporter_for_environment",
]
