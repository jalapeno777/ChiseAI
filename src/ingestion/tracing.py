"""Data ingestion tracing instrumentation"""

from opentelemetry import trace


def trace_ingestion_batch(func):
    """Decorator to trace ingestion batches"""

    def wrapper(*args, **kwargs):
        tracer = trace.get_tracer("chiseai-ingestion")
        with tracer.start_as_current_span("ingestion.batch") as span:
            span.set_attribute("chiseai.data.source", kwargs.get("source", "unknown"))
            span.set_attribute("chiseai.ingestion.batch_id", kwargs.get("batch_id", ""))
            return func(*args, **kwargs)

    return wrapper
