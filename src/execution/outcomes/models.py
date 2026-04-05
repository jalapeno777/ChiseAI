"""Database models for outcome store.

Defines the SQLite database schema for storing and querying signal outcomes.

For ST-ICT-P1: Signal Outcome Database Backend
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from ml.models.signal_outcome import OutcomeType, SignalOutcome, SignalOutcomeStatus

# SQLite schema definition
SCHEMA = """
CREATE TABLE IF NOT EXISTS signal_outcomes (
    -- Primary identifiers
    outcome_id TEXT PRIMARY KEY,
    signal_id TEXT,
    order_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    token TEXT NOT NULL,
    
    -- Trade details
    side TEXT NOT NULL,
    direction TEXT NOT NULL,
    fill_price REAL NOT NULL DEFAULT 0,
    fill_quantity REAL NOT NULL DEFAULT 0,
    fill_timestamp TEXT,
    
    -- Outcome classification
    outcome_type TEXT NOT NULL DEFAULT 'unknown',
    pnl REAL,
    fee REAL,
    status TEXT NOT NULL DEFAULT 'pending',
    
    -- Timestamps
    created_at TEXT NOT NULL,
    entry_time TEXT,
    entry_price REAL NOT NULL DEFAULT 0,
    exit_price REAL,
    exit_time TEXT,
    
    -- Position details
    position_size REAL NOT NULL DEFAULT 0,
    leverage REAL NOT NULL DEFAULT 1.0,
    entry_reason TEXT DEFAULT '',
    
    -- Provenance (ST-VENUE-001)
    execution_venue TEXT DEFAULT '',
    execution_mode TEXT DEFAULT '',
    execution_source TEXT DEFAULT '',
    
    -- Additional metadata
    metadata TEXT DEFAULT '{}',
    venue_metadata TEXT DEFAULT '{}',
    
    -- Signal correlation (ST-PIPELINE-Q2)
    confidence_score REAL NOT NULL DEFAULT 0.0,
    signal_type TEXT DEFAULT '',
    
    -- Test trade labeling (DISCORD-TRADING-001)
    is_test INTEGER NOT NULL DEFAULT 0
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_outcomes_signal_id ON signal_outcomes(signal_id);
CREATE INDEX IF NOT EXISTS idx_outcomes_symbol ON signal_outcomes(symbol);
CREATE INDEX IF NOT EXISTS idx_outcomes_fill_timestamp ON signal_outcomes(fill_timestamp);
CREATE INDEX IF NOT EXISTS idx_outcomes_outcome_type ON signal_outcomes(outcome_type);
CREATE INDEX IF NOT EXISTS idx_outcomes_status ON signal_outcomes(status);
CREATE INDEX IF NOT EXISTS idx_outcomes_created_at ON signal_outcomes(created_at);
"""


def dict_to_row(data: dict[str, Any]) -> dict[str, Any]:
    """Convert a SignalOutcome dict to database row format.

    Args:
        data: Dictionary with outcome data

    Returns:
        Dictionary with database-compatible values
    """
    # Handle UUID serialization
    outcome_id = data.get("outcome_id", str(uuid4()))
    if isinstance(outcome_id, UUID):
        outcome_id = str(outcome_id)

    signal_id = data.get("signal_id")
    if signal_id is not None and isinstance(signal_id, UUID):
        signal_id = str(signal_id)

    # Handle Decimal conversion
    def to_float(val: Any) -> float:
        if val is None:
            return 0.0
        if isinstance(val, Decimal):
            return float(val)
        if isinstance(val, (int, float, str)):
            return float(val)
        return 0.0

    def to_str(val: Any) -> str | None:
        if val is None:
            return None
        return str(val)

    # Handle datetime serialization
    def to_iso(val: Any) -> str | None:
        if val is None:
            return None
        if isinstance(val, datetime):
            return val.isoformat()
        return str(val)

    # Handle outcome_type and status enums
    outcome_type = data.get("outcome_type", OutcomeType.UNKNOWN)
    if hasattr(outcome_type, "value"):
        outcome_type = outcome_type.value

    status = data.get("status", SignalOutcomeStatus.PENDING)
    if hasattr(status, "value"):
        status = status.value

    # Handle boolean
    is_test = 1 if data.get("is_test", False) else 0

    # Handle JSON fields
    import json

    metadata = data.get("metadata", {})
    if isinstance(metadata, dict):
        metadata = json.dumps(metadata)

    venue_metadata = data.get("venue_metadata", {})
    if isinstance(venue_metadata, dict):
        venue_metadata = json.dumps(venue_metadata)

    return {
        "outcome_id": outcome_id,
        "signal_id": signal_id,
        "order_id": data.get("order_id", ""),
        "symbol": data.get("symbol", ""),
        "token": data.get("token", ""),
        "side": data.get("side", ""),
        "direction": data.get("direction", ""),
        "fill_price": to_float(data.get("fill_price")),
        "fill_quantity": to_float(data.get("fill_quantity")),
        "fill_timestamp": to_iso(data.get("fill_timestamp")),
        "outcome_type": outcome_type,
        "pnl": to_float(data.get("pnl")) if data.get("pnl") is not None else None,
        "fee": to_float(data.get("fee")) if data.get("fee") is not None else None,
        "status": status,
        "created_at": to_iso(data.get("created_at")) or datetime.now(UTC).isoformat(),
        "entry_time": to_iso(data.get("entry_time")),
        "entry_price": to_float(data.get("entry_price")),
        "exit_price": (
            to_float(data.get("exit_price"))
            if data.get("exit_price") is not None
            else None
        ),
        "exit_time": to_iso(data.get("exit_time")),
        "position_size": to_float(data.get("position_size")),
        "leverage": to_float(data.get("leverage", 1.0)),
        "entry_reason": to_str(data.get("entry_reason", "")),
        "execution_venue": to_str(data.get("execution_venue", "")),
        "execution_mode": to_str(data.get("execution_mode", "")),
        "execution_source": to_str(data.get("execution_source", "")),
        "metadata": metadata,
        "venue_metadata": venue_metadata,
        "confidence_score": float(data.get("confidence_score", 0.0)),
        "signal_type": to_str(data.get("signal_type", "")),
        "is_test": is_test,
    }


def row_to_signal_outcome(row: dict[str, Any]) -> SignalOutcome:
    """Convert a database row back to SignalOutcome.

    Args:
        row: Database row dictionary

    Returns:
        SignalOutcome instance
    """
    import json

    # Parse outcome_type enum
    outcome_type_str = row.get("outcome_type", "unknown")
    try:
        outcome_type = OutcomeType(outcome_type_str)
    except ValueError:
        outcome_type = OutcomeType.UNKNOWN

    # Parse status enum
    status_str = row.get("status", "pending")
    try:
        status = SignalOutcomeStatus(status_str)
    except ValueError:
        status = SignalOutcomeStatus.PENDING

    # Parse timestamps
    def parse_datetime(val: str | None) -> datetime | None:
        if val is None:
            return None
        try:
            # Handle ISO format
            if val.endswith("Z"):
                val = val[:-1] + "+00:00"
            return datetime.fromisoformat(val)
        except (ValueError, TypeError):
            return None

    # Parse metadata JSON
    metadata_str = row.get("metadata", "{}")
    if isinstance(metadata_str, str):
        try:
            metadata = json.loads(metadata_str)
        except json.JSONDecodeError:
            metadata = {}
    else:
        metadata = metadata_str or {}

    venue_metadata_str = row.get("venue_metadata", "{}")
    if isinstance(venue_metadata_str, str):
        try:
            venue_metadata = json.loads(venue_metadata_str)
        except json.JSONDecodeError:
            venue_metadata = {}
    else:
        venue_metadata = venue_metadata_str or {}

    return SignalOutcome(
        outcome_id=UUID(row["outcome_id"]) if row.get("outcome_id") else uuid4(),
        signal_id=UUID(row["signal_id"]) if row.get("signal_id") else None,
        order_id=row.get("order_id", ""),
        symbol=row.get("symbol", ""),
        token=row.get("token", ""),
        side=row.get("side", ""),
        direction=row.get("direction", ""),
        fill_price=Decimal(str(row.get("fill_price", 0))),
        fill_quantity=Decimal(str(row.get("fill_quantity", 0))),
        fill_timestamp=parse_datetime(row.get("fill_timestamp")) or datetime.now(UTC),
        outcome_type=outcome_type,
        pnl=Decimal(str(row["pnl"])) if row.get("pnl") is not None else None,
        fee=Decimal(str(row["fee"])) if row.get("fee") is not None else None,
        status=status,
        created_at=parse_datetime(row.get("created_at")) or datetime.now(UTC),
        metadata=metadata,
        entry_price=Decimal(str(row.get("entry_price", 0))),
        exit_price=(
            Decimal(str(row["exit_price"]))
            if row.get("exit_price") is not None
            else None
        ),
        entry_time=parse_datetime(row.get("entry_time")) or datetime.now(UTC),
        exit_time=parse_datetime(row.get("exit_time")),
        leverage=Decimal(str(row.get("leverage", 1.0))),
        entry_reason=row.get("entry_reason", "") or "",
        position_size=Decimal(str(row.get("position_size", 0))),
        execution_venue=row.get("execution_venue", "") or "",
        execution_mode=row.get("execution_mode", "") or "",
        execution_source=row.get("execution_source", "") or "",
        venue_metadata=venue_metadata,
        confidence_score=float(row.get("confidence_score", 0.0)),
        signal_type=row.get("signal_type", "") or "",
        is_test=bool(row.get("is_test", 0)),
    )


def init_db(conn: sqlite3.Connection) -> None:
    """Initialize database schema.

    Args:
        conn: SQLite database connection
    """
    conn.executescript(SCHEMA)
    conn.commit()
