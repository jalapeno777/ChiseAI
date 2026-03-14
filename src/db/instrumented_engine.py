"""Instrumented SQLAlchemy engine with automatic tracing.

TEMPO-2026-001: SQLAlchemy event listeners for automatic query tracing.
"""

from __future__ import annotations

import time
from typing import Any

from opentelemetry import trace
from sqlalchemy import event
from sqlalchemy.engine import Engine


def instrument_sqlalchemy_engine(engine: Engine) -> Engine:
    """Instrument a SQLAlchemy engine with automatic tracing.

    Adds event listeners that create spans for:
    - Query execution (before_cursor_execute, after_cursor_execute)
    - Transaction begin/commit/rollback
    - Connection events

    Args:
        engine: SQLAlchemy Engine instance to instrument

    Returns:
        The same engine instance (for chaining)

    Example:
        from sqlalchemy import create_engine
        from src.db.instrumented_engine import instrument_sqlalchemy_engine

        engine = create_engine("postgresql://...")
        instrument_sqlalchemy_engine(engine)

        # All queries executed through this engine will be traced
    """
    _attach_query_listeners(engine)
    _attach_transaction_listeners(engine)
    return engine


def _attach_query_listeners(engine: Engine) -> None:
    """Attach query execution event listeners to the engine."""

    @event.listens_for(engine, "before_cursor_execute")
    def before_cursor_execute(
        conn,
        cursor,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ):
        """Track query start time."""
        conn.info.setdefault("query_start_time", time.time())

    @event.listens_for(engine, "after_cursor_execute")
    def after_cursor_execute(
        conn,
        cursor,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ):
        """Create span for completed query."""
        start_time = conn.info.get("query_start_time")
        duration_ms = (time.time() - start_time) * 1000 if start_time else 0

        tracer = trace.get_tracer("chiseai-database")

        # Extract SQL type from statement
        sql_type = _extract_sql_type(statement)
        table_name = _extract_table_name(statement)

        span_name = (
            f"db.query.{sql_type.lower() if sql_type != 'UNKNOWN' else 'unknown'}"
        )

        with tracer.start_as_current_span(span_name) as span:
            span.set_attribute("chiseai.db.query_type", sql_type)
            if table_name:
                span.set_attribute("chiseai.db.table", table_name)

            # Truncate long queries
            truncated_query = (
                statement[:500] + "..." if len(statement) > 500 else statement
            )
            span.set_attribute("chiseai.db.query", truncated_query)
            span.set_attribute("chiseai.db.duration_ms", duration_ms)
            span.set_attribute("chiseai.db.executemany", executemany)

            # Try to get row count
            if hasattr(cursor, "rowcount"):
                span.set_attribute("chiseai.db.row_count", cursor.rowcount)

            # Clean up
            conn.info.pop("query_start_time", None)


def _attach_transaction_listeners(engine: Engine) -> None:
    """Attach transaction event listeners to the engine."""

    @event.listens_for(engine, "begin")
    def on_begin(conn):
        """Track transaction start."""
        conn.info["transaction_start_time"] = time.time()
        conn.info["transaction_id"] = id(conn)

        tracer = trace.get_tracer("chiseai-database")
        with tracer.start_as_current_span("db.transaction.begin") as span:
            span.set_attribute("chiseai.db.transaction_id", conn.info["transaction_id"])
            span.set_attribute("chiseai.db.event", "begin")

    @event.listens_for(engine, "commit")
    def on_commit(conn):
        """Track transaction commit."""
        start_time = conn.info.get("transaction_start_time")
        duration_ms = (time.time() - start_time) * 1000 if start_time else 0

        tracer = trace.get_tracer("chiseai-database")
        with tracer.start_as_current_span("db.transaction.commit") as span:
            span.set_attribute(
                "chiseai.db.transaction_id", conn.info.get("transaction_id", "")
            )
            span.set_attribute("chiseai.db.event", "commit")
            span.set_attribute("chiseai.db.duration_ms", duration_ms)
            span.set_attribute("chiseai.db.committed", True)

        # Clean up
        conn.info.pop("transaction_start_time", None)
        conn.info.pop("transaction_id", None)

    @event.listens_for(engine, "rollback")
    def on_rollback(conn):
        """Track transaction rollback."""
        start_time = conn.info.get("transaction_start_time")
        duration_ms = (time.time() - start_time) * 1000 if start_time else 0

        tracer = trace.get_tracer("chiseai-database")
        with tracer.start_as_current_span("db.transaction.rollback") as span:
            span.set_attribute(
                "chiseai.db.transaction_id", conn.info.get("transaction_id", "")
            )
            span.set_attribute("chiseai.db.event", "rollback")
            span.set_attribute("chiseai.db.duration_ms", duration_ms)
            span.set_attribute("chiseai.db.committed", False)
            span.set_attribute("chiseai.db.rolled_back", True)

        # Clean up
        conn.info.pop("transaction_start_time", None)
        conn.info.pop("transaction_id", None)


# SQL type extraction helpers (mirrored from tracing.py for independence)
def _extract_sql_type(statement: str) -> str:
    """Extract SQL command type from statement."""
    statement_upper = statement.strip().upper()
    commands = [
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
    ]
    for command in commands:
        if statement_upper.startswith(command):
            return command
    return "UNKNOWN"


def _extract_table_name(statement: str) -> str | None:
    """Extract table name from SQL statement."""
    import re

    patterns = [
        re.compile(r"\bFROM\s+(\w+)(?:\s|$|,)", re.IGNORECASE),
        re.compile(r"\bINTO\s+(\w+)(?:\s|$)", re.IGNORECASE),
        re.compile(r"\bUPDATE\s+(\w+)(?:\s|$)", re.IGNORECASE),
        re.compile(
            r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)",
            re.IGNORECASE,
        ),
        re.compile(r"\bDROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?(\w+)", re.IGNORECASE),
        re.compile(r"\bALTER\s+TABLE\s+(\w+)(?:\s|$)", re.IGNORECASE),
    ]

    for pattern in patterns:
        match = pattern.search(statement)
        if match:
            return match.group(1)
    return None


class InstrumentedEngine:
    """Wrapper class for SQLAlchemy engine with automatic tracing.

    Provides a convenient interface for creating instrumented database engines.

    Example:
        from src.db.instrumented_engine import InstrumentedEngine

        engine = InstrumentedEngine("postgresql://user:pass@host/db")
        # All queries through this engine are automatically traced
    """

    def __init__(self, database_url: str, **kwargs: Any):
        """Initialize instrumented engine.

        Args:
            database_url: SQLAlchemy database URL
            **kwargs: Additional arguments passed to create_engine
        """
        from sqlalchemy import create_engine

        self._engine = create_engine(database_url, **kwargs)
        instrument_sqlalchemy_engine(self._engine)

    @property
    def engine(self) -> Engine:
        """Get the underlying SQLAlchemy engine."""
        return self._engine

    def connect(self, *args: Any, **kwargs: Any):
        """Proxy to engine.connect()."""
        return self._engine.connect(*args, **kwargs)

    def execute(self, *args: Any, **kwargs: Any):
        """Proxy to engine.execute()."""
        return self._engine.execute(*args, **kwargs)

    def dispose(self) -> None:
        """Proxy to engine.dispose()."""
        self._engine.dispose()
