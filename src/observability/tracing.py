"""
OpenTelemetry Tracing Initialization for ChiseAI

TEMPO-2026-001: Distributed tracing with Grafana Tempo
"""

import logging
import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

# Import auto-instrumentation
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import (
    DEPLOYMENT_ENVIRONMENT,
    SERVICE_NAME,
    SERVICE_VERSION,
    Resource,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def get_resource_attributes(service_name: str) -> Resource:
    """
    Create resource attributes for the service.

    Args:
        service_name: Name of the service (e.g., "chiseai-api")

    Returns:
        OpenTelemetry Resource with attributes
    """
    return Resource.create(
        {
            SERVICE_NAME: service_name,
            SERVICE_VERSION: os.getenv("SERVICE_VERSION", "1.0.0"),
            DEPLOYMENT_ENVIRONMENT: os.getenv("DEPLOYMENT_ENVIRONMENT", "development"),
            "chiseai.service.type": service_name.replace("chiseai-", ""),
            "chiseai.service.group": _get_service_group(service_name),
            "host.name": os.getenv("HOSTNAME", "localhost"),
        }
    )


def _get_service_group(service_name: str) -> str:
    """Map service name to service group."""
    group_mapping = {
        "chiseai-api": "api",
        "chiseai-strategy": "strategy",
        "chiseai-ingestion": "data",
        "chiseai-worker": "worker",
    }
    return group_mapping.get(service_name, "unknown")


def get_sampler():
    """
    Get trace sampler based on environment.

    Configurable via TEMPO_SAMPLE_RATE environment variable.
    Default rates: development=100%, staging=50%, production=10%.

    Returns:
        Sampler instance

    Raises:
        ValueError: If TEMPO_SAMPLE_RATE is not a valid float between 0.0 and 1.0
    """
    from opentelemetry.sdk.trace.sampling import TraceIdRatioBased

    logger = logging.getLogger(__name__)
    environment = os.getenv("DEPLOYMENT_ENVIRONMENT", "development")

    # Default sampling rates from Phase 0 design
    sampling_rates = {
        "development": 1.0,  # 100%
        "staging": 0.5,  # 50%
        "production": 0.1,  # 10%
    }

    # Allow override via environment variable
    env_rate = os.getenv("TEMPO_SAMPLE_RATE")
    if env_rate is not None:
        try:
            sample_rate = float(env_rate)
        except ValueError:
            raise ValueError(
                f"TEMPO_SAMPLE_RATE must be a valid float, got: {env_rate!r}"
            )
    else:
        sample_rate = sampling_rates.get(environment, 0.1)

    # Validate sample rate is within valid range [0.0, 1.0]
    if not 0.0 <= sample_rate <= 1.0:
        raise ValueError(f"Sample rate must be between 0.0 and 1.0, got: {sample_rate}")

    # Log the effective sample rate
    logger.info(
        f"OpenTelemetry sampler initialized: rate={sample_rate} "
        f"(environment={environment}, env_override={'yes' if env_rate else 'no'})"
    )

    return TraceIdRatioBased(sample_rate)


def init_tracing(service_name: str) -> trace.Tracer:
    """
    Initialize OpenTelemetry tracing for a service.

    Args:
        service_name: Name of the service (e.g., "chiseai-api")

    Returns:
        Tracer instance for the service
    """
    # Create resource
    resource = get_resource_attributes(service_name)

    # Create OTLP exporter
    tempo_endpoint = os.getenv("TEMPO_ENDPOINT", "http://chiseai-tempo:4317")
    exporter = OTLPSpanExporter(endpoint=tempo_endpoint)

    # Create span processor
    span_processor = BatchSpanProcessor(
        exporter,
        max_queue_size=2048,
        max_export_batch_size=512,
        schedule_delay_millis=5000,
    )

    # Create tracer provider with sampler
    provider = TracerProvider(
        resource=resource,
        sampler=get_sampler(),
    )
    provider.add_span_processor(span_processor)

    # Set global tracer provider
    trace.set_tracer_provider(provider)

    # Get tracer for this service
    tracer = trace.get_tracer(service_name)

    return tracer


def instrument_fastapi(app):
    """
    Instrument FastAPI application.

    Args:
        app: FastAPI application instance
    """
    FastAPIInstrumentor.instrument_app(
        app,
        excluded_urls="/health,/ready",  # Exclude health checks
    )


def instrument_sqlalchemy(engine):
    """
    Instrument SQLAlchemy engine.

    Args:
        engine: SQLAlchemy engine instance
    """
    SQLAlchemyInstrumentor().instrument(
        engine=engine,
    )


def instrument_redis():
    """Instrument Redis client."""
    RedisInstrumentor().instrument()


def instrument_requests():
    """Instrument requests library."""
    RequestsInstrumentor().instrument()


def get_tempo_exporter() -> OTLPSpanExporter:
    """
    Get the Tempo OTLP exporter.

    Returns:
        OTLPSpanExporter instance
    """
    tempo_endpoint = os.getenv("TEMPO_ENDPOINT", "http://chiseai-tempo:4317")
    return OTLPSpanExporter(endpoint=tempo_endpoint)


def shutdown_tracing():
    """Shutdown the tracer provider and flush spans."""
    provider = trace.get_tracer_provider()
    if hasattr(provider, "shutdown"):
        provider.shutdown()
