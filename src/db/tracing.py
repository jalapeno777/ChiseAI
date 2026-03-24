"""Database tracing instrumentation for SQL queries and transactions.

TEMPO-2026-001: Database span wrappers with SQL type and table name extraction.
"""

from __future__ import annotations

import functools
import re
import time
from collections.abc import Callable
from typing import Any, TypeVar

from opentelemetry import trace

F = TypeVar("F", bound=Callable[..., Any])

# SQL command patterns for extracting query type
SQL_COMMANDS = [
    "SELECT",
    "INSERT",
    "UPDATE",
    "DELETE",
    "CREATE",
    "DROP",
    "ALTER",
    "TRUNCATE",
    "MERGE",
    "UPSERT",
    "CALL",
    "EXEC",
]

# Regex to extract table name from common SQL patterns
TABLE_NAME_PATTERNS = [
    # FROM table_name (SELECT, DELETE)
    re.compile(r"\bFROM\s+(\w+)(?:\s|$|,)", re.IGNORECASE),
    # INTO table_name (INSERT)
    re.compile(r"\bINTO\s+(\w+)(?:\s|$)", re.IGNORECASE),
    # UPDATE table_name
    re.compile(r"\bUPDATE\s+(\w+)(?:\s|$)", re.IGNORECASE),
    # CREATE TABLE table_name
    re.compile(
        r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)(?:\s|$|\()", re.IGNORECASE
    ),
    # DROP TABLE table_name
    re.compile(r"\bDROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?(\w+)(?:\s|$|;)", re.IGNORECASE),
    # ALTER TABLE table_name
    re.compile(r"\bALTER\s+TABLE\s+(\w+)(?:\s|$)", re.IGNORECASE),
]


def extract_sql_type(query: str) -> str:
    """Extract the SQL command type from a query.

    Args:
        query: SQL query string

    Returns:
        SQL command type (SELECT, INSERT, UPDATE, DELETE, etc.) or "UNKNOWN"
    """
    query_upper = query.strip().upper()
    for command in SQL_COMMANDS:
        if query_upper.startswith(command):
            return command
    return "UNKNOWN"


def extract_table_name(query: str) -> str | None:
    """Extract the primary table name from a SQL query.

    Args:
        query: SQL query string

    Returns:
        Table name if found, None otherwise
    """
    for pattern in TABLE_NAME_PATTERNS:
        match = pattern.search(query)
        if match:
            return match.group(1)
    return None


def trace_db_query(func: F) -> F:
    """Decorator to trace database query execution.

    Creates spans with attributes for:
    - SQL query type (SELECT, INSERT, UPDATE, DELETE, etc.)
    - Table name (extracted from query)
    - Query duration
    - Row count (if available in result)

    Args:
        func: Function to decorate (should execute a SQL query)

    Returns:
        Decorated function

    Example:
        @trace_db_query
        def get_user_by_id(db_session, user_id: int):
            return db_session.execute(select(User).where(User.id == user_id))
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        tracer = trace.get_tracer("chiseai-database")

        # Extract query from kwargs or args
        query = kwargs.get("query", "")
        if not query and len(args) >= 2:
            # Assume second positional arg might be the query
            query = str(args[1]) if args[1] else ""

        sql_type = extract_sql_type(query)
        table_name = extract_table_name(query)

        span_name = (
            f"db.query.{sql_type.lower() if sql_type != 'UNKNOWN' else 'unknown'}"
        )

        with tracer.start_as_current_span(span_name) as span:
            span.set_attribute("chiseai.db.query_type", sql_type)
            if table_name:
                span.set_attribute("chiseai.db.table", table_name)
            if query:
                # Truncate long queries for span size limits
                truncated_query = query[:500] + "..." if len(query) > 500 else query
                span.set_attribute("chiseai.db.query", truncated_query)

            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                duration_ms = (time.time() - start_time) * 1000

                span.set_attribute("chiseai.db.duration_ms", duration_ms)
                span.set_attribute("chiseai.db.success", True)

                # Try to extract row count if result supports it
                row_count = _extract_row_count(result)
                if row_count is not None:
                    span.set_attribute("chiseai.db.row_count", row_count)

                return result
            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                span.set_attribute("chiseai.db.duration_ms", duration_ms)
                span.set_attribute("chiseai.db.success", False)
                span.set_attribute("chiseai.db.error", str(e))
                span.set_attribute("chiseai.db.error_type", type(e).__name__)
                span.record_exception(e)
                raise

    return wrapper  # type: ignore[return-value]


def trace_db_transaction(func: F) -> F:
    """Decorator to trace database transaction boundaries.

    Creates spans for transaction begin, commit, and rollback operations.

    Args:
        func: Function to decorate (should manage a transaction)

    Returns:
        Decorated function

    Example:
        @trace_db_transaction
        def transfer_funds(db_session, from_id: int, to_id: int, amount: float):
            with db_session.begin():
                # ... transaction logic ...
                pass
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        tracer = trace.get_tracer("chiseai-database")

        span_name = "db.transaction"
        transaction_id = kwargs.get("transaction_id", "")

        with tracer.start_as_current_span(span_name) as span:
            if transaction_id:
                span.set_attribute("chiseai.db.transaction_id", transaction_id)

            span.set_attribute("chiseai.db.transaction_start", True)
            start_time = time.time()

            try:
                result = func(*args, **kwargs)
                duration_ms = (time.time() - start_time) * 1000

                span.set_attribute("chiseai.db.duration_ms", duration_ms)
                span.set_attribute("chiseai.db.committed", True)
                span.set_attribute("chiseai.db.success", True)

                return result
            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000

                span.set_attribute("chiseai.db.duration_ms", duration_ms)
                span.set_attribute("chiseai.db.committed", False)
                span.set_attribute("chiseai.db.rolled_back", True)
                span.set_attribute("chiseai.db.success", False)
                span.set_attribute("chiseai.db.error", str(e))
                span.record_exception(e)
                raise

    return wrapper  # type: ignore[return-value]


def _extract_row_count(result: Any) -> int | None:
    """Extract row count from query result if available.

    Args:
        result: Query result object

    Returns:
        Row count if extractable, None otherwise
    """
    if result is None:
        return None

    # Handle SQLAlchemy result objects
    if hasattr(result, "rowcount"):
        return result.rowcount

    # Handle list results
    if isinstance(result, list):
        return len(result)

    # Handle dict results
    if isinstance(result, dict) and "rowcount" in result:
        return result["rowcount"]

    return None
