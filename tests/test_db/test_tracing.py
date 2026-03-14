"""Tests for database tracing instrumentation.

TEMPO-2026-001: Database span wrapper tests.
"""

from __future__ import annotations

from unittest.mock import MagicMock, Mock, patch

import pytest
from opentelemetry import trace

from src.db.tracing import (
    extract_sql_type,
    extract_table_name,
    trace_db_query,
    trace_db_transaction,
)


class TestExtractSqlType:
    """Tests for SQL type extraction."""

    def test_extract_select(self):
        """Test extracting SELECT type."""
        query = "SELECT * FROM users WHERE id = 1"
        assert extract_sql_type(query) == "SELECT"

    def test_extract_insert(self):
        """Test extracting INSERT type."""
        query = "INSERT INTO users (name, email) VALUES ('John', 'john@example.com')"
        assert extract_sql_type(query) == "INSERT"

    def test_extract_update(self):
        """Test extracting UPDATE type."""
        query = "UPDATE users SET name = 'Jane' WHERE id = 1"
        assert extract_sql_type(query) == "UPDATE"

    def test_extract_delete(self):
        """Test extracting DELETE type."""
        query = "DELETE FROM users WHERE id = 1"
        assert extract_sql_type(query) == "DELETE"

    def test_extract_create_table(self):
        """Test extracting CREATE type."""
        query = "CREATE TABLE users (id INT PRIMARY KEY)"
        assert extract_sql_type(query) == "CREATE"

    def test_extract_drop_table(self):
        """Test extracting DROP type."""
        query = "DROP TABLE users"
        assert extract_sql_type(query) == "DROP"

    def test_extract_alter_table(self):
        """Test extracting ALTER type."""
        query = "ALTER TABLE users ADD COLUMN age INT"
        assert extract_sql_type(query) == "ALTER"

    def test_extract_unknown(self):
        """Test extracting unknown type."""
        query = "UNKNOWN COMMAND"
        assert extract_sql_type(query) == "UNKNOWN"

    def test_extract_with_whitespace(self):
        """Test extracting type with leading whitespace."""
        query = "   SELECT * FROM users"
        assert extract_sql_type(query) == "SELECT"


class TestExtractTableName:
    """Tests for table name extraction."""

    def test_extract_from_select(self):
        """Test extracting table from SELECT."""
        query = "SELECT * FROM users WHERE id = 1"
        assert extract_table_name(query) == "users"

    def test_extract_from_insert(self):
        """Test extracting table from INSERT."""
        query = "INSERT INTO orders (id, total) VALUES (1, 100.00)"
        assert extract_table_name(query) == "orders"

    def test_extract_from_update(self):
        """Test extracting table from UPDATE."""
        query = "UPDATE products SET price = 20 WHERE id = 1"
        assert extract_table_name(query) == "products"

    def test_extract_from_delete(self):
        """Test extracting table from DELETE."""
        query = "DELETE FROM logs WHERE created_at < '2024-01-01'"
        assert extract_table_name(query) == "logs"

    def test_extract_from_create_table(self):
        """Test extracting table from CREATE TABLE."""
        query = "CREATE TABLE new_table (id INT)"
        assert extract_table_name(query) == "new_table"

    def test_extract_from_create_table_if_not_exists(self):
        """Test extracting table from CREATE TABLE IF NOT EXISTS."""
        query = "CREATE TABLE IF NOT EXISTS existing_table (id INT)"
        assert extract_table_name(query) == "existing_table"

    def test_extract_from_drop_table(self):
        """Test extracting table from DROP TABLE."""
        query = "DROP TABLE old_table"
        assert extract_table_name(query) == "old_table"

    def test_extract_from_drop_table_if_exists(self):
        """Test extracting table from DROP TABLE IF EXISTS."""
        query = "DROP TABLE IF EXISTS temp_table"
        assert extract_table_name(query) == "temp_table"

    def test_extract_from_alter_table(self):
        """Test extracting table from ALTER TABLE."""
        query = "ALTER TABLE users ADD COLUMN email VARCHAR(255)"
        assert extract_table_name(query) == "users"

    def test_extract_no_table(self):
        """Test extraction when no table found."""
        query = "SELECT 1"
        assert extract_table_name(query) is None


class TestTraceDbQuery:
    """Tests for trace_db_query decorator."""

    @patch("src.db.tracing.trace.get_tracer")
    def test_trace_db_query_success(self, mock_get_tracer):
        """Test successful query tracing."""
        # Setup mock tracer
        mock_span = MagicMock()
        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(
            return_value=mock_span
        )
        mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(
            return_value=False
        )
        mock_get_tracer.return_value = mock_tracer

        # Create decorated function
        @trace_db_query
        def execute_query(db, query):
            return {"rowcount": 5}

        # Execute
        result = execute_query(None, "SELECT * FROM users")

        # Verify
        assert result == {"rowcount": 5}
        mock_get_tracer.assert_called_once_with("chiseai-database")
        mock_span.set_attribute.assert_any_call("chiseai.db.query_type", "SELECT")
        mock_span.set_attribute.assert_any_call("chiseai.db.table", "users")
        mock_span.set_attribute.assert_any_call("chiseai.db.success", True)

    @patch("src.db.tracing.trace.get_tracer")
    def test_trace_db_query_with_rowcount(self, mock_get_tracer):
        """Test query tracing with row count extraction."""
        mock_span = MagicMock()
        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(
            return_value=mock_span
        )
        mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(
            return_value=False
        )
        mock_get_tracer.return_value = mock_tracer

        class MockResult:
            rowcount = 10

        @trace_db_query
        def execute_query(db, query):
            return MockResult()

        result = execute_query(None, "UPDATE users SET active = true")

        assert result.rowcount == 10
        mock_span.set_attribute.assert_any_call("chiseai.db.row_count", 10)

    @patch("src.db.tracing.trace.get_tracer")
    def test_trace_db_query_exception(self, mock_get_tracer):
        """Test query tracing with exception."""
        mock_span = MagicMock()
        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(
            return_value=mock_span
        )
        mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(
            return_value=False
        )
        mock_get_tracer.return_value = mock_tracer

        @trace_db_query
        def execute_query(db, query):
            raise ValueError("Connection failed")

        with pytest.raises(ValueError, match="Connection failed"):
            execute_query(None, "SELECT * FROM users")

        mock_span.set_attribute.assert_any_call("chiseai.db.success", False)
        mock_span.set_attribute.assert_any_call("chiseai.db.error", "Connection failed")
        mock_span.set_attribute.assert_any_call("chiseai.db.error_type", "ValueError")
        mock_span.record_exception.assert_called_once()

    @patch("src.db.tracing.trace.get_tracer")
    def test_trace_db_query_truncates_long_query(self, mock_get_tracer):
        """Test that long queries are truncated."""
        mock_span = MagicMock()
        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(
            return_value=mock_span
        )
        mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(
            return_value=False
        )
        mock_get_tracer.return_value = mock_tracer

        @trace_db_query
        def execute_query(db, query):
            return {}

        long_query = "SELECT * FROM users " + "x" * 1000
        execute_query(None, long_query)

        # Check that the query was truncated
        call_args = mock_span.set_attribute.call_args_list
        query_attr = [call for call in call_args if call[0][0] == "chiseai.db.query"]
        assert len(query_attr) == 1
        assert query_attr[0][0][1].endswith("...")


class TestTraceDbTransaction:
    """Tests for trace_db_transaction decorator."""

    @patch("src.db.tracing.trace.get_tracer")
    def test_trace_transaction_success(self, mock_get_tracer):
        """Test successful transaction tracing."""
        mock_span = MagicMock()
        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(
            return_value=mock_span
        )
        mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(
            return_value=False
        )
        mock_get_tracer.return_value = mock_tracer

        @trace_db_transaction
        def process_transaction(db):
            return {"status": "success"}

        result = process_transaction(None)

        assert result == {"status": "success"}
        mock_span.set_attribute.assert_any_call("chiseai.db.transaction_start", True)
        mock_span.set_attribute.assert_any_call("chiseai.db.committed", True)
        mock_span.set_attribute.assert_any_call("chiseai.db.success", True)

    @patch("src.db.tracing.trace.get_tracer")
    def test_trace_transaction_with_id(self, mock_get_tracer):
        """Test transaction tracing with transaction ID."""
        mock_span = MagicMock()
        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(
            return_value=mock_span
        )
        mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(
            return_value=False
        )
        mock_get_tracer.return_value = mock_tracer

        @trace_db_transaction
        def process_transaction(db, transaction_id="txn-123"):
            return {"status": "success"}

        process_transaction(None, transaction_id="txn-123")

        mock_span.set_attribute.assert_any_call("chiseai.db.transaction_id", "txn-123")

    @patch("src.db.tracing.trace.get_tracer")
    def test_trace_transaction_rollback(self, mock_get_tracer):
        """Test transaction tracing with rollback."""
        mock_span = MagicMock()
        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(
            return_value=mock_span
        )
        mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(
            return_value=False
        )
        mock_get_tracer.return_value = mock_tracer

        @trace_db_transaction
        def process_transaction(db):
            raise RuntimeError("Transaction failed")

        with pytest.raises(RuntimeError, match="Transaction failed"):
            process_transaction(None)

        mock_span.set_attribute.assert_any_call("chiseai.db.committed", False)
        mock_span.set_attribute.assert_any_call("chiseai.db.rolled_back", True)
        mock_span.set_attribute.assert_any_call("chiseai.db.success", False)
