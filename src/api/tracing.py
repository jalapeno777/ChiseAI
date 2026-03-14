"""
API Tracing Utilities for Manual Instrumentation

TEMPO-2026-001: Phase 4 Service Coverage
"""

from typing import Callable, Optional, Any, Dict, cast
from functools import wraps
from contextvars import ContextVar
import time
import traceback
from opentelemetry import trace
from opentelemetry.trace import Span, SpanKind
from opentelemetry.util.types import AttributeValue
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from uuid import uuid4


# Context variables for trace context propagation
_trace_context: ContextVar[Optional[Dict[str, Any]]] = ContextVar(
    "trace_context", default=None
)
"""Context variable for trace context propagation"""


def get_trace_context(request: Request) -> Optional[Dict[str, Any]]:
    """
    Get trace context from request.

    Args:
        request: FastAPI request object

    Returns:
        dict with trace context information or None if no span active
    """
    span = trace.get_current_span()
    if span is None:
        return None

    span_context = getattr(span, "context", None)
    if span_context is None:
        return None

    # Return trace context with span information
    return {
        "trace_id": format(span_context.trace_context),
        "span_id": format(span_context.span_id),
        "trace_state": span_context.trace_state,
    }


def trace_api_endpoint(
    name: Optional[str] = None,
    kind: SpanKind = SpanKind.INTERNAL,
    description: Optional[str] = None,
    custom_attributes: Optional[Dict[str, Any]] = None,
) -> Callable:
    """
    Decorator for manual API endpoint tracing.

    Creates a span for the decorated endpoint and adds standard attributes
    (user.id, request.id, endpoint.name, http.method, http.route).

    Args:
        name: Endpoint name for span naming
        kind: Span kind (default: INTERNAL)
        description: Optional description for the span
        custom_attributes: Optional dictionary of custom attributes to add to spans

    Returns:
        Decorated function
    """
    tracer = trace.get_tracer(__name__ or "api.tracing")

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Response:
            # Try to get request from args
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break

            # Create span name
            span_name = name or func.__name__

            start_time = time.time()

            with tracer.start_as_current_span(span_name, kind=kind) as span:
                if request:
                    # Add standard attributes
                    span.set_attribute("endpoint.name", span_name)
                    span.set_attribute("http.method", request.method)
                    span.set_attribute("http.route", str(request.url.path))

                    hostname = request.url.hostname
                    if hostname:
                        span.set_attribute("http.host", hostname)

                    # Add custom attributes if provided
                    if custom_attributes:
                        for key, value in custom_attributes.items():
                            if value is not None:
                                span.set_attribute(key, cast(AttributeValue, value))

                    # Add timing attributes
                    span.set_attribute("request.start_time", start_time)

                try:
                    response = await func(*args, **kwargs)
                    end_time = time.time()

                    # Calculate duration
                    duration_ms = (end_time - start_time) * 1000
                    span.set_attribute("response.duration_ms", duration_ms)
                    span.set_attribute("http.status_code", response.status_code)

                    # Get trace context and add to response
                    if request:
                        ctx = get_trace_context(request)
                        if ctx:
                            response.headers["X-Trace-Id"] = ctx["trace_id"]

                    return response

                except Exception as e:
                    span.set_attribute("error", True)
                    span.set_attribute("error.type", type(e).__name__)
                    span.set_attribute("error.message", str(e))
                    span.set_attribute("error.stack_trace", traceback.format_exc())
                    raise

        return wrapper

    return decorator


def trace_api_middleware(custom_attributes: Optional[Dict[str, Any]] = None):
    """
    Factory for creating middleware with custom attributes.

    Args:
        custom_attributes: Optional dictionary of custom attributes to add to spans
    """

    class TraceApiMiddleware(BaseHTTPMiddleware):
        def __init__(self, app, custom_attributes: Optional[Dict[str, Any]] = None):
            super().__init__(app)
            self.custom_attributes = custom_attributes

        async def dispatch(self, request: Request, call_next) -> Response:
            # Create a span for this middleware
            tracer = trace.get_tracer("chiseai-api-middleware")
            with tracer.start_as_current_span(
                "api.middleware", kind=SpanKind.INTERNAL
            ) as span:
                span.set_attribute("http.method", request.method)
                span.set_attribute("http.route", str(request.url.path))

                hostname = request.url.hostname
                if hostname:
                    span.set_attribute("http.host", hostname)

                # Add custom attributes if provided
                if self.custom_attributes:
                    for key, value in self.custom_attributes.items():
                        if value is not None:
                            span.set_attribute(key, cast(AttributeValue, value))

                # Add timing attributes
                start_time = time.time()
                span.set_attribute("request.start_time", start_time)

                try:
                    response = await call_next(request)
                    end_time = time.time()

                    # Calculate duration
                    duration_ms = (end_time - start_time) * 1000
                    span.set_attribute("response.duration_ms", duration_ms)
                    span.set_attribute("http.status_code", response.status_code)

                    # Get trace context and add to response
                    ctx = get_trace_context(request)
                    if ctx:
                        response.headers["X-Trace-Id"] = ctx["trace_id"]

                    return response

                except Exception as e:
                    span.set_attribute("error", True)
                    span.set_attribute("error.type", type(e).__name__)
                    span.set_attribute("error.message", str(e))
                    span.set_attribute("error.stack_trace", traceback.format_exc())
                    raise

            return await call_next(request)

    return TraceApiMiddleware


def get_current_trace_id() -> Optional[str]:
    """
    Get the current trace ID from the active span context.

    Returns:
        Trace ID if available, None otherwise
    """
    span = trace.get_current_span()
    if span is None:
        return None

    span_context = getattr(span, "context", None)
    if span_context is None:
        return None

    return format(span_context.trace_context)


__all__ = [
    "get_trace_context",
    "get_current_trace_id",
    "trace_api_endpoint",
    "trace_api_middleware",
]
