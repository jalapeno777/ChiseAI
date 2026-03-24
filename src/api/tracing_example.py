"""
Example: Instrumenting ChiseAI API with OpenTelemetry

TEMPO-2026-001: Usage example for tracing module
"""

from fastapi import FastAPI

from src.observability import (
    init_tracing,
    instrument_fastapi,
)


def setup_tracing(app: FastAPI, service_name: str = "chiseai-api"):
    """
    Setup OpenTelemetry tracing for the API.

    Args:
        app: FastAPI application
        service_name: Service name for traces
    """
    # Initialize tracing
    tracer = init_tracing(service_name)

    # Instrument FastAPI
    instrument_fastapi(app)

    # Instrument other libraries (call these after initializing respective clients)
    # instrument_sqlalchemy(engine)
    # instrument_redis()
    # instrument_requests()

    return tracer
