"""Audit logger for live trading with full audit trail.

Logs all live trades, approvals, and state changes to InfluxDB
for compliance and Grafana visibility.

For ST-EX-002: Bitget Live Trading Gating Implementation
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from execution.live_gating.gate_manager import (
        ApprovalPacket,
        LiveTradingState,
    )

logger = logging.getLogger(__name__)


@dataclass
class TradeAuditRecord:
    """Audit record for a live trade.

    Attributes:
        timestamp: When trade was executed
        trade_id: Unique trade identifier
        symbol: Trading pair (e.g., "BTCUSDT")
        side: Trade side (buy/sell)
        price: Execution price
        quantity: Trade quantity
        reason: Reason for trade (signal, stop-loss, etc.)
        order_id: Exchange order ID
        pnl: Realized PnL (if closing trade)
        fees: Trading fees paid
        environment: Trading environment (always "live" for this logger)
        metadata: Additional trade metadata
    """

    timestamp: datetime
    trade_id: str
    symbol: str
    side: str
    price: float
    quantity: float
    reason: str
    order_id: str = ""
    pnl: float = 0.0
    fees: float = 0.0
    environment: str = "live"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "side": self.side,
            "price": self.price,
            "quantity": self.quantity,
            "reason": self.reason,
            "order_id": self.order_id,
            "pnl": self.pnl,
            "fees": self.fees,
            "environment": self.environment,
            "metadata": self.metadata,
        }


@dataclass
class ApprovalAuditRecord:
    """Audit record for approval events.

    Attributes:
        timestamp: When approval was granted
        approver_id: Identifier of approver
        request_id: Reference to approval request
        signature: Approval signature
        evidence_summary: Summary of paper trading evidence
    """

    timestamp: datetime
    approver_id: str
    request_id: str
    signature: str
    evidence_summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "approver_id": self.approver_id,
            "request_id": self.request_id,
            "signature": (
                self.signature[:16] + "..."
                if len(self.signature) > 16
                else self.signature
            ),
            "evidence_summary": self.evidence_summary,
        }


@dataclass
class StateChangeAuditRecord:
    """Audit record for state changes.

    Attributes:
        timestamp: When state changed
        old_state: Previous state
        new_state: New state
        reason: Reason for state change
        triggered_by: What triggered the change
    """

    timestamp: datetime
    old_state: str
    new_state: str
    reason: str
    triggered_by: str = "system"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "old_state": self.old_state,
            "new_state": self.new_state,
            "reason": self.reason,
            "triggered_by": self.triggered_by,
        }


class LiveTradeAuditLogger:
    """Audit logger for live trading with full audit trail.

    This logger records:
    - All live trades with timestamp, price, quantity, reason
    - Approval events with approver ID and signature
    - State changes with old/new state and reason

    All records are persisted to InfluxDB for Grafana visibility
    and long-term audit compliance.

    Usage:
        logger = LiveTradeAuditLogger(influxdb_client)

        # Log a trade
        logger.log_trade(
            timestamp=datetime.now(UTC),
            price=50000.0,
            quantity=0.1,
            reason="Grid signal: buy level 3"
        )

        # Log approval
        logger.log_approval(approval_packet)

        # Log state change
        logger.log_state_change(
            old_state=LiveTradingState.ACTIVE,
            new_state=LiveTradingState.DISABLED,
            reason="Kill-switch triggered"
        )
    """

    def __init__(
        self,
        influxdb_client: Any | None = None,
        bucket: str = "chiseai",
        org: str = "chiseai",
        measurement: str = "live_trading_audit",
    ) -> None:
        """Initialize audit logger.

        Args:
            influxdb_client: InfluxDB client (optional)
            bucket: InfluxDB bucket name
            org: InfluxDB organization
            measurement: Measurement name for audit records
        """
        self._client = influxdb_client
        self._bucket = bucket
        self._org = org
        self._measurement = measurement
        self._write_api = None

        # In-memory buffer for fallback
        self._buffer: list[Any] = []
        self._buffer_max_size = 10000

        # Statistics
        self._trade_count = 0
        self._approval_count = 0
        self._state_change_count = 0
        self._failed_writes = 0

        logger.info(f"LiveTradeAuditLogger initialized: measurement={measurement}")

    async def _get_write_api(self) -> Any:
        """Get or create InfluxDB write API."""
        if self._write_api is None and self._client is not None:
            self._write_api = self._client.write_api()
        return self._write_api

    def _create_point(
        self,
        record_type: str,
        fields: dict[str, Any],
        tags: dict[str, str],
        timestamp: datetime,
    ) -> Any:
        """Create an InfluxDB point.

        Args:
            record_type: Type of record (trade, approval, state_change)
            fields: Field values
            tags: Tag values
            timestamp: Record timestamp

        Returns:
            InfluxDB Point
        """
        try:
            from influxdb_client import Point

            point = Point(self._measurement)
            point = point.tag("record_type", record_type)

            for key, value in tags.items():
                point = point.tag(key, str(value))

            for key, value in fields.items():
                if isinstance(value, bool):
                    point = point.field(key, value)
                elif isinstance(value, int):
                    point = point.field(key, float(value))
                elif isinstance(value, float):
                    point = point.field(key, value)
                else:
                    point = point.field(key, str(value))

            point = point.time(timestamp)
            return point

        except ImportError:
            logger.warning("influxdb_client not available, using dict fallback")
            return {
                "measurement": self._measurement,
                "tags": {**tags, "record_type": record_type},
                "fields": fields,
                "time": timestamp.isoformat(),
            }

    async def log_trade(
        self,
        timestamp: datetime,
        price: float,
        quantity: float,
        reason: str,
        symbol: str = "",
        side: str = "",
        trade_id: str = "",
        order_id: str = "",
        pnl: float = 0.0,
        fees: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Log a live trade with full audit trail.

        Args:
            timestamp: When trade was executed
            price: Execution price
            quantity: Trade quantity
            reason: Reason for trade
            symbol: Trading pair
            side: Trade side
            trade_id: Unique trade identifier
            order_id: Exchange order ID
            pnl: Realized PnL
            fees: Trading fees
            metadata: Additional metadata

        Returns:
            True if logged successfully
        """
        record = TradeAuditRecord(
            timestamp=timestamp,
            trade_id=trade_id or f"TRADE-{datetime.now(UTC).timestamp()}",
            symbol=symbol,
            side=side,
            price=price,
            quantity=quantity,
            reason=reason,
            order_id=order_id,
            pnl=pnl,
            fees=fees,
            metadata=metadata or {},
        )

        # Create InfluxDB point
        point = self._create_point(
            record_type="trade",
            fields={
                "price": price,
                "quantity": quantity,
                "pnl": pnl,
                "fees": fees,
                "reason": reason,
            },
            tags={
                "symbol": symbol,
                "side": side,
                "trade_id": record.trade_id,
                "order_id": order_id,
            },
            timestamp=timestamp,
        )

        # Write to InfluxDB
        success = await self._write_point(point)

        if success:
            self._trade_count += 1
            logger.info(
                f"Trade logged: {symbol} {side} {quantity} @ {price} - {reason}"
            )
        else:
            logger.error(f"Failed to log trade: {record.trade_id}")

        return success

    async def log_approval(self, packet: ApprovalPacket) -> bool:
        """Log an approval event.

        Args:
            packet: Signed approval packet

        Returns:
            True if logged successfully
        """
        record = ApprovalAuditRecord(
            timestamp=packet.timestamp,
            approver_id=packet.approver_id,
            request_id=packet.request_id,
            signature=packet.signature,
            evidence_summary={
                "strategy_id": packet.paper_evidence.strategy_id,
                "duration_days": packet.paper_evidence.duration_days,
                "sharpe_ratio": packet.paper_evidence.sharpe_ratio,
                "max_drawdown_pct": packet.paper_evidence.max_drawdown_pct,
            },
        )

        # Create InfluxDB point
        point = self._create_point(
            record_type="approval",
            fields={
                "approver_id": packet.approver_id,
                "request_id": packet.request_id,
                "signature_hash": packet.signature[:16],
            },
            tags={
                "approver_id": packet.approver_id,
                "request_id": packet.request_id,
                "strategy_id": packet.paper_evidence.strategy_id,
            },
            timestamp=packet.timestamp,
        )

        # Write to InfluxDB
        success = await self._write_point(point)

        if success:
            self._approval_count += 1
            logger.info(
                f"Approval logged: {packet.approver_id} approved {packet.request_id}"
            )
        else:
            logger.error(f"Failed to log approval: {packet.request_id}")

        return success

    async def log_state_change(
        self,
        old_state: LiveTradingState | str,
        new_state: LiveTradingState | str,
        reason: str,
        triggered_by: str = "system",
    ) -> bool:
        """Log a state change event.

        Args:
            old_state: Previous state
            new_state: New state
            reason: Reason for state change
            triggered_by: What triggered the change

        Returns:
            True if logged successfully
        """
        old_state_str = (
            old_state.value if hasattr(old_state, "value") else str(old_state)
        )
        new_state_str = (
            new_state.value if hasattr(new_state, "value") else str(new_state)
        )

        record = StateChangeAuditRecord(
            timestamp=datetime.now(UTC),
            old_state=old_state_str,
            new_state=new_state_str,
            reason=reason,
            triggered_by=triggered_by,
        )

        # Create InfluxDB point
        point = self._create_point(
            record_type="state_change",
            fields={
                "old_state": old_state_str,
                "new_state": new_state_str,
                "reason": reason,
                "triggered_by": triggered_by,
            },
            tags={
                "old_state": old_state_str,
                "new_state": new_state_str,
                "triggered_by": triggered_by,
            },
            timestamp=datetime.now(UTC),
        )

        # Write to InfluxDB
        success = await self._write_point(point)

        if success:
            self._state_change_count += 1
            logger.info(f"State change logged: {old_state_str} -> {new_state_str}")
        else:
            logger.error(
                f"Failed to log state change: {old_state_str} -> {new_state_str}"
            )

        return success

    async def _write_point(self, point: Any) -> bool:
        """Write a point to InfluxDB.

        Args:
            point: InfluxDB point or dict fallback

        Returns:
            True if write successful
        """
        try:
            write_api = await self._get_write_api()

            if write_api is not None:
                write_api.write(
                    bucket=self._bucket,
                    org=self._org,
                    record=point,
                )
                return True
            else:
                # Buffer for later if no client
                self._buffer.append(point)
                if len(self._buffer) > self._buffer_max_size:
                    self._buffer = self._buffer[-self._buffer_max_size :]
                return True

        except Exception as e:
            logger.error(f"Failed to write to InfluxDB: {e}")
            self._failed_writes += 1

            # Buffer for retry
            self._buffer.append(point)
            if len(self._buffer) > self._buffer_max_size:
                self._buffer = self._buffer[-self._buffer_max_size :]

            return False

    def get_stats(self) -> dict[str, Any]:
        """Get audit logger statistics.

        Returns:
            Dictionary with statistics
        """
        return {
            "trade_count": self._trade_count,
            "approval_count": self._approval_count,
            "state_change_count": self._state_change_count,
            "failed_writes": self._failed_writes,
            "buffer_size": len(self._buffer),
            "measurement": self._measurement,
        }

    async def flush_buffer(self) -> int:
        """Flush buffered records to InfluxDB.

        Returns:
            Number of records flushed
        """
        if not self._buffer:
            return 0

        write_api = await self._get_write_api()
        if write_api is None:
            return 0

        flushed = 0
        remaining = []

        for point in self._buffer:
            try:
                write_api.write(
                    bucket=self._bucket,
                    org=self._org,
                    record=point,
                )
                flushed += 1
            except Exception as e:
                logger.error(f"Failed to flush point: {e}")
                remaining.append(point)

        self._buffer = remaining
        logger.info(f"Flushed {flushed} records, {len(remaining)} remaining")
        return flushed
