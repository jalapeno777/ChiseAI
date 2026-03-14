"""Tests for API tracing utilities.

TEMPO-2026-001: Phase 4 Service Coverage
"""

from __future__ import annotations

from unittest.mock import MagicMock, Mock, patch
import pytest
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient
from opentelemetry import trace
from opentelemetry.trace import SpanKind
import asyncio

# Import directly from the tracing module to not from src.api
from src.api.tracing import get_trace_context
from src.api.tracing import get_current_trace_id
from src.api.tracing import trace_api_endpoint
from src.api.tracing import trace_api_middleware


class TestGetTraceContext:
    """Tests for get_trace_context function."""

    def test_get_trace_context_with_context(self):
        """Test getting trace context when available."""
        mock_request = MagicMock(spec=Request)
        mock_request.state = {"trace_id": "test-trace-123", "span_id": "test-span-456"}

        mock_span = MagicMock()
        mock_context = MagicMock()
        mock_context.trace_context = "test-trace-789"
        mock_span.context = mock_context

        with patch("src.api.tracing.trace.get_current_span", return_value=mock_span):
            ctx = get_trace_context(mock_request)

            assert ctx is not None
            assert "trace_id" in ctx

    def test_get_trace_context_without_span(self):
        """Test getting trace context when no span available."""
        mock_request = MagicMock(spec=Request)

        with patch("src.api.tracing.trace.get_current_span", return_value=None):
            ctx = get_trace_context(mock_request)

            assert ctx is None

    def test_get_trace_context_without_context(self):
        """Test getting trace context when no context in request."""
        mock_request = MagicMock(spec=Request)
        mock_request.state = {}

        with patch("src.api.tracing.trace.get_current_span", return_value=MagicMock()):
            ctx = get_trace_context(mock_request)

            assert ctx is None


class TestTraceApiEndpoint:
    """Tests for trace_api_endpoint decorator."""

    @patch("src.api.tracing.trace.get_tracer")
    def test_trace_endpoint_success(self, mock_get_tracer):
        """Test successful endpoint tracing."""
        mock_request = MagicMock(spec=Request)
        mock_request.method = "GET"
        mock_request.url.path = "/api/test"
        mock_request.url.hostname = "localhost"

        mock_span = MagicMock()
        mock_span_context = MagicMock()
        mock_span_context.trace_context = "test-trace-123"
        mock_span.context = mock_span_context

        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(
            return_value=mock_span
        )
        mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(
            return_value=False
        )
        mock_get_tracer.return_value = mock_tracer

        @trace_api_endpoint(name="test_endpoint")
        async def test_endpoint(request: Request):
            return Response(content="Success", status_code=200)

        create_user(mock_request)

        # Verify
        assert result.status_code == 200
        assert result.headers["X-Trace-Id"] == "test-trace-123"

        # Verify span attributes were set
        assert mock_span.set_attribute.call_count > 10

        # Verify important attributes were set
        assert mock_span.set_attribute.assert_any_call("endpoint.name", "test_endpoint")
        mock_span.set_attribute.assert_any_call("http.method", "GET")
        mock_span.set_attribute.assert_any_call("http.route", "/api/test")
        mock_span.set_attribute.assert_any_call("http.host", "localhost")
        mock_span.set_attribute.assert_any_call("response.duration_ms", 0.0)
        mock_span.set_attribute.assert_any_call("http.status_code", 200)

    @patch("src.api.tracing.trace.get_tracer")
    def test_trace_endpoint_with_custom_attributes(self, mock_get_tracer):
        """Test endpoint tracing with custom attributes."""
        mock_request = MagicMock(spec=Request)
        mock_request.method = "POST"
        mock_request.url.path = "/api/users"
        mock_request.url.hostname = "localhost"

        mock_span = MagicMock()
        mock_span_context = MagicMock()
        mock_span_context.trace_context = "test-trace-def-456"
        mock_span.context = mock_span_context

        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(
            return_value=mock_span
        )
        mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(
            return_value=False
        )
        mock_get_tracer.return_value = mock_tracer

        @trace_api_endpoint(
            name="create_user",
            custom_attributes={"user.type": "admin", "api.version": "v2"},
        )
        async def create_user(request: Request):
            return Response(content="User created", status_code=201)

        create_user(mock_request)

        # Verify custom attributes were set
        mock_span.set_attribute.assert_any_call("user.type", "admin")
        mock_span.set_attribute.assert_any_call("api.version", "v2")

    @patch("src.api.tracing.trace.get_tracer")
    def test_trace_endpoint_exception(self, mock_get_tracer):
        """Test endpoint tracing with exception."""
        mock_request = MagicMock(spec=Request)
        mock_request.method = "GET"
        mock_request.url.path = "/api/error"
        mock_request.url.hostname = "localhost"

        mock_span = MagicMock()
        mock_span_context = MagicMock()
        mock_span_context.trace_context = "test-trace-xyz-789"
        mock_span.context = mock_span_context

        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(
            return_value=mock_span
        )
        mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(
            return_value=False
        )
        mock_get_tracer.return_value = mock_tracer

        @trace_api_endpoint(name="error_endpoint")
        async def error_endpoint(request: Request):
            raise ValueError("Test error")

        with pytest.raises(ValueError, match="Test error"):
            asyncio.get_event_loop().run_until_complete(error_endpoint(mock_request))

        # Verify error attributes were set
        mock_span.set_attribute.assert_any_call("error", True)
        mock_span.set_attribute.assert_any_call("error.type", "ValueError")
        mock_span.set_attribute.assert_any_call("error.message", "Test error")
        mock_span.set_attribute.assert_any_call("error.stack_trace")


class TestTraceApiMiddleware:
    """Tests for trace_api_middleware function."""

    def test_middleware_factory(self):
        """Test that middleware factory creates a class."""
        middleware_class = trace_api_middleware(
            custom_attributes={"app.version": "1.0.0"}
        )
        assert middleware_class is not None
        assert hasattr(middleware_class, "dispatch")

    @patch("src.api.tracing.trace.get_tracer")
    def test_middleware_dispatch_success(self, mock_get_tracer):
        """Test middleware dispatch with successful request."""
        mock_span = MagicMock()
        mock_span_context = MagicMock()
        mock_span_context.trace_context = "test-trace-middleware-123"
        mock_span.context = mock_span_context

        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(
            return_value=mock_span
        )
        mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(
            return_value=False
        )
        mock_get_tracer.return_value = mock_tracer

        # Create mock app and app = FastAPI()

        # Create mock request
        mock_request = MagicMock(spec=Request)
        mock_request.method = "GET"
        mock_request.url.path = "/api/test"
        mock_request.url.hostname = "localhost"
        mock_request.headers = {}

        # Create mock response
        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 200
        mock_response.headers = {}

        # Create middleware instance
        middleware_class = trace_api_middleware(custom_attributes={"service": "api"})
        middleware = middleware_class(app, custom_attributes={"service": "api"})

        # Mock call_next
        async def call_next(request):
            return mock_response

        # Execute
        result = asyncio.get_event_loop().run_until_complete(
            middleware.dispatch(mock_request, call_next)
        )

        # Verify
        assert result.status_code == 200
        assert "X-Trace-Id" in result.headers
        assert result.headers["X-Trace-Id"] == "test-trace-middleware-123"

        # Verify span attributes were set
        assert mock_span.set_attribute.call_count > 8

        # Verify important attributes were set
        assert mock_span.set_attribute.assert_any_call("http.method", "GET")
        mock_span.set_attribute.assert_any_call("http.route", "/api/test")
        mock_span.set_attribute.assert_any_call("service", "api")
        mock_span.set_attribute.assert_any_call("response.duration_ms", 0.0)
        mock_span.set_attribute.assert_any_call("http.status_code", 200)

    @patch("src.api.tracing.trace.get_tracer")
    def test_middleware_dispatch_exception(self, mock_get_tracer):
        """Test middleware dispatch with exception."""
        mock_span = MagicMock()
        mock_span_context = MagicMock()
        mock_span_context.trace_context = "test-trace-error-123"
        mock_span.context = mock_span_context

        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(
            return_value=mock_span
        )
        mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(
            return_value=False
        )
        mock_get_tracer.return_value = mock_tracer

        app = FastAPI()

        mock_request = MagicMock(spec=Request)
        mock_request.method = "POST"
        mock_request.url.path = "/api/error"
        mock_request.url.hostname = "localhost"
        mock_request.headers = {}

        middleware_class = trace_api_middleware(custom_attributes={"service": "api"})
        middleware = middleware_class(app, custom_attributes={"service": "api"})

        # Mock call_next that raises exception
        async def call_next(request):
            raise RuntimeError("Middleware error")

        # Execute
        with pytest.raises(RuntimeError, match="Middleware error"):
            asyncio.get_event_loop().run_until_complete(
                middleware.dispatch(mock_request, call_next)
            )

        # Verify error attributes were set
        mock_span.set_attribute.assert_any_call("error", True)
        mock_span.set_attribute.assert_any_call("error.type", "RuntimeError")
        mock_span.set_attribute.assert_any_call("error.message", "Middleware error")


class TestGetCurrentTraceId:
    """Tests for get_current_trace_id function."""

    def test_get_current_trace_id_with_span(self):
        """Test getting trace ID when span available."""
        mock_span = MagicMock()
        mock_context = MagicMock()
        mock_context.trace_context = "trace-abc-123"
        mock_span.context = mock_context

        with patch("src.api.tracing.trace.get_current_span", return_value=mock_span):
            trace_id = get_current_trace_id()

        assert trace_id == "trace-abc-123"

    def test_get_current_trace_id_without_span(self):
        """Test getting trace ID when no span available."""
        with patch("src.api.tracing.trace.get_current_span", return_value=None):
            trace_id = get_current_trace_id()

        assert trace_id is None
