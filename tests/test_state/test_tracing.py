"""Tests for Redis tracing instrumentation.

TEMPO-2026-001: Redis span wrapper tests.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from src.state.tracing import (
    get_operation_category,
    sanitize_key_pattern,
    trace_redis_operation,
)


class TestGetOperationCategory:
    """Tests for Redis operation categorization."""

    def test_get_category_read(self):
        """Test categorizing read operations."""
        assert get_operation_category("GET") == "read"
        assert get_operation_category("HGET") == "read"
        assert get_operation_category("HGETALL") == "read"
        assert get_operation_category("LRANGE") == "read"
        assert get_operation_category("SMEMBERS") == "read"
        assert get_operation_category("ZRANGE") == "read"
        assert get_operation_category("EXISTS") == "read"
        assert get_operation_category("TTL") == "read"

    def test_get_category_write(self):
        """Test categorizing write operations."""
        assert get_operation_category("SET") == "write"
        assert get_operation_category("HSET") == "write"
        assert get_operation_category("DELETE") == "write"
        assert get_operation_category("LPUSH") == "write"
        assert get_operation_category("SADD") == "write"
        assert get_operation_category("ZADD") == "write"
        assert get_operation_category("EXPIRE") == "write"

    def test_get_category_case_insensitive(self):
        """Test that operation category is case insensitive."""
        assert get_operation_category("get") == "read"
        assert get_operation_category("SET") == "write"
        assert get_operation_category("Get") == "read"

    def test_get_category_unknown(self):
        """Test categorizing unknown operations."""
        assert get_operation_category("UNKNOWN") == "unknown"
        assert get_operation_category("CUSTOM") == "unknown"


class TestSanitizeKeyPattern:
    """Tests for key pattern sanitization."""

    def test_sanitize_simple_key(self):
        """Test sanitizing simple key."""
        assert sanitize_key_pattern("user:123") == "user:<id>"

    def test_sanitize_uuid(self):
        """Test sanitizing UUID in key."""
        uuid_key = "session:550e8400-e29b-41d4-a716-446655440000"
        assert sanitize_key_pattern(uuid_key) == "session:<uuid>"

    def test_sanitize_email(self):
        """Test sanitizing email in key."""
        email_key = "user:john.doe@example.com"
        assert sanitize_key_pattern(email_key) == "user:<email>"

    def test_sanitize_multiple_ids(self):
        """Test sanitizing multiple IDs."""
        key = "user:123:order:456:item:789"
        assert sanitize_key_pattern(key) == "user:<id>:order:<id>:item:<id>"

    def test_sanitize_empty_key(self):
        """Test sanitizing empty key."""
        assert sanitize_key_pattern("") == ""

    def test_sanitize_none(self):
        """Test sanitizing None."""
        assert sanitize_key_pattern(None) == ""  # type: ignore[arg-type]

    def test_sanitize_plain_key(self):
        """Test sanitizing plain key without patterns."""
        assert sanitize_key_pattern("config:settings") == "config:settings"


class TestTraceRedisOperation:
    """Tests for trace_redis_operation decorator."""

    @patch("src.state.tracing.trace.get_tracer")
    def test_trace_redis_get(self, mock_get_tracer):
        """Test tracing GET operation."""
        mock_span = MagicMock()
        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(
            return_value=mock_span
        )
        mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(
            return_value=False
        )
        mock_get_tracer.return_value = mock_tracer

        @trace_redis_operation("GET")
        def get_value(redis_client, key):
            return b"value"

        result = get_value(None, "user:123")

        assert result == b"value"
        mock_span.set_attribute.assert_any_call("chiseai.redis.operation", "GET")
        mock_span.set_attribute.assert_any_call("chiseai.redis.category", "read")
        mock_span.set_attribute.assert_any_call(
            "chiseai.redis.key_pattern", "user:<id>"
        )
        mock_span.set_attribute.assert_any_call("chiseai.redis.success", True)

    @patch("src.state.tracing.trace.get_tracer")
    def test_trace_redis_set(self, mock_get_tracer):
        """Test tracing SET operation."""
        mock_span = MagicMock()
        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(
            return_value=mock_span
        )
        mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(
            return_value=False
        )
        mock_get_tracer.return_value = mock_tracer

        @trace_redis_operation("SET")
        def set_value(redis_client, key, value):
            return True

        result = set_value(None, "config:settings", "enabled")

        assert result is True
        mock_span.set_attribute.assert_any_call("chiseai.redis.operation", "SET")
        mock_span.set_attribute.assert_any_call("chiseai.redis.category", "write")
        mock_span.set_attribute.assert_any_call("chiseai.redis.success", True)

    @patch("src.state.tracing.trace.get_tracer")
    def test_trace_redis_exception(self, mock_get_tracer):
        """Test tracing with exception."""
        mock_span = MagicMock()
        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(
            return_value=mock_span
        )
        mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(
            return_value=False
        )
        mock_get_tracer.return_value = mock_tracer

        @trace_redis_operation("GET")
        def get_value(redis_client, key):
            raise ConnectionError("Redis connection lost")

        with pytest.raises(ConnectionError, match="Redis connection lost"):
            get_value(None, "user:123")

        mock_span.set_attribute.assert_any_call("chiseai.redis.success", False)
        mock_span.set_attribute.assert_any_call(
            "chiseai.redis.error", "Redis connection lost"
        )
        mock_span.set_attribute.assert_any_call(
            "chiseai.redis.error_type", "ConnectionError"
        )
        mock_span.record_exception.assert_called_once()

    @patch("src.state.tracing.trace.get_tracer")
    def test_trace_redis_auto_infer_get(self, mock_get_tracer):
        """Test auto-inferring GET operation from function name."""
        mock_span = MagicMock()
        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(
            return_value=mock_span
        )
        mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(
            return_value=False
        )
        mock_get_tracer.return_value = mock_tracer

        @trace_redis_operation()
        def redis_get(redis_client, key):
            return b"value"

        redis_get(None, "user:123")

        mock_span.set_attribute.assert_any_call("chiseai.redis.operation", "GET")

    @patch("src.state.tracing.trace.get_tracer")
    def test_trace_redis_auto_infer_set(self, mock_get_tracer):
        """Test auto-inferring SET operation from function name."""
        mock_span = MagicMock()
        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(
            return_value=mock_span
        )
        mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(
            return_value=False
        )
        mock_get_tracer.return_value = mock_tracer

        @trace_redis_operation()
        def redis_set(redis_client, key, value):
            return True

        redis_set(None, "user:123", "data")

        mock_span.set_attribute.assert_any_call("chiseai.redis.operation", "SET")

    @patch("src.state.tracing.trace.get_tracer")
    def test_trace_redis_with_result_size(self, mock_get_tracer):
        """Test tracing with result size."""
        mock_span = MagicMock()
        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(
            return_value=mock_span
        )
        mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(
            return_value=False
        )
        mock_get_tracer.return_value = mock_tracer

        @trace_redis_operation("GET")
        def get_value(redis_client, key):
            return b"x" * 100  # 100 bytes

        get_value(None, "user:123")

        mock_span.set_attribute.assert_any_call("chiseai.redis.result_size_bytes", 100)

    @patch("src.state.tracing.trace.get_tracer")
    def test_trace_redis_list_result_size(self, mock_get_tracer):
        """Test tracing with list result size."""
        mock_span = MagicMock()
        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(
            return_value=mock_span
        )
        mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(
            return_value=False
        )
        mock_get_tracer.return_value = mock_tracer

        @trace_redis_operation("LRANGE")
        def get_list(redis_client, key):
            return [b"item1", b"item2", b"item3"]

        get_list(None, "mylist")

        # 5 + 5 + 5 = 15 bytes
        mock_span.set_attribute.assert_any_call("chiseai.redis.result_size_bytes", 15)

    @patch("src.state.tracing.trace.get_tracer")
    def test_trace_redis_dict_result_size(self, mock_get_tracer):
        """Test tracing with dict result size."""
        mock_span = MagicMock()
        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(
            return_value=mock_span
        )
        mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(
            return_value=False
        )
        mock_get_tracer.return_value = mock_tracer

        @trace_redis_operation("HGETALL")
        def get_hash(redis_client, key):
            return {b"field1": b"value1", b"field2": b"value2"}

        get_hash(None, "myhash")

        mock_span.set_attribute.assert_any_call(
            "chiseai.redis.result_size_bytes", 24
        )  # Total of all keys and values (6+6+6+6)
