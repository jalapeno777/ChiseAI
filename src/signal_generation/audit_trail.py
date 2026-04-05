"""Pipeline audit trail for signal processing decisions.

Provides structured audit logging for every pipeline decision including
filter, dedup, execution, and outcome events with full traceability.

For ST-PIPELINE-TRANSPARENCY P2: Audit Trail
Every pipeline decision is logged with:
- timestamp (UTC)
- signal_id
- decision type
- reason/rejection code
- actionable boolean
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Redis key patterns for audit trail
_AUDIT_KEY_PREFIX = "chiseai:audit:pipeline"


class AuditDecisionType(Enum):
    """Types of pipeline decisions that can be audited."""

    QUALITY_FILTER = "quality_filter"
    DEDUP_CHECK = "dedup_check"
    VALIDATION = "validation"
    ENRICHMENT = "enrichment"
    STORAGE = "storage"
    DELIVERY = "delivery"
    EXECUTION = "execution"
    OUTCOME = "outcome"


@dataclass
class PipelineAuditEvent:
    """Audit event for a pipeline decision.

    Attributes:
        timestamp: When the decision was made (UTC)
        signal_id: Unique signal identifier
        decision_type: Type of pipeline decision
        reason: Human-readable reason for decision
        rejection_code: Machine-readable rejection code (if applicable)
        actionable: Whether the signal is actionable after this decision
        metadata: Additional event-specific metadata
        token: Trading pair/token
        direction: Signal direction
    """

    timestamp: datetime
    signal_id: str
    decision_type: AuditDecisionType
    reason: str
    rejection_code: str | None = None
    actionable: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)
    token: str = ""
    direction: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization.

        Returns:
            Dictionary representation of the audit event
        """
        return {
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "signal_id": self.signal_id,
            "decision_type": self.decision_type.value,
            "reason": self.reason,
            "rejection_code": self.rejection_code,
            "actionable": self.actionable,
            "metadata": self.metadata,
            "token": self.token,
            "direction": self.direction,
        }

    def to_json(self) -> str:
        """Convert to JSON string.

        Returns:
            JSON string representation
        """
        return json.dumps(self.to_dict())


class PipelineAuditLogger:
    """Audit logger for pipeline decisions with Redis persistence.

    Logs all pipeline decisions to Redis streams for Grafana visibility
    and long-term audit compliance.

    Usage:
        audit = PipelineAuditLogger()

        # Log a quality filter decision
        audit.log_decision(
            signal_id="abc-123",
            decision_type=AuditDecisionType.QUALITY_FILTER,
            reason="Signal quality_score 45% below threshold 50%",
            rejection_code="QUALITY_BELOW_THRESHOLD",
            actionable=False,
            token="BTC/USDT",
            direction="LONG",
        )
    """

    # Redis connection settings
    DEFAULT_REDIS_HOST = "host.docker.internal"
    DEFAULT_REDIS_PORT = 6380
    DEFAULT_REDIS_DB = 0

    def __init__(
        self,
        redis_host: str | None = None,
        redis_port: int | None = None,
        redis_db: int | None = None,
    ):
        """Initialize audit logger.

        Args:
            redis_host: Redis host (defaults to host.docker.internal)
            redis_port: Redis port (defaults to 6380)
            redis_db: Redis DB number (defaults to 0)
        """
        self._redis_host = redis_host or self.DEFAULT_REDIS_HOST
        self._redis_port = redis_port or self.DEFAULT_REDIS_PORT
        self._redis_db = redis_db if redis_db is not None else self.DEFAULT_REDIS_DB
        self._redis_client: Any = None
        self._redis_lock = threading.Lock()

        # Statistics
        self._event_count = 0
        self._failed_writes = 0

        logger.info("PipelineAuditLogger initialized")

    def _get_redis_client(self) -> Any | None:
        """Get or create Redis client.

        Returns:
            Redis client or None if connection fails
        """
        if self._redis_client is not None:
            return self._redis_client

        with self._redis_lock:
            if self._redis_client is not None:
                return self._redis_client

            try:
                import redis

                client = redis.Redis(
                    host=self._redis_host,
                    port=self._redis_port,
                    db=self._redis_db,
                    decode_responses=True,
                    socket_timeout=5.0,
                    socket_connect_timeout=5.0,
                )
                client.ping()
                self._redis_client = client
                logger.debug("PipelineAuditLogger: Redis client connected")
                return client
            except Exception as e:
                logger.warning(f"PipelineAuditLogger: Redis connection failed: {e}")
                return None

    def log_decision(
        self,
        signal_id: str,
        decision_type: AuditDecisionType,
        reason: str,
        rejection_code: str | None = None,
        actionable: bool = True,
        token: str = "",
        direction: str = "",
        metadata: dict[str, Any] | None = None,
        timestamp: datetime | None = None,
    ) -> bool:
        """Log a pipeline decision event.

        Args:
            signal_id: Unique signal identifier
            decision_type: Type of pipeline decision
            reason: Human-readable reason for the decision
            rejection_code: Machine-readable code (if rejected)
            actionable: Whether signal remains actionable
            token: Trading pair/token
            direction: Signal direction
            metadata: Additional event metadata
            timestamp: Event timestamp (defaults to now)

        Returns:
            True if logged successfully
        """
        event = PipelineAuditEvent(
            timestamp=timestamp or datetime.now(UTC),
            signal_id=signal_id,
            decision_type=decision_type,
            reason=reason,
            rejection_code=rejection_code,
            actionable=actionable,
            metadata=metadata or {},
            token=token,
            direction=direction,
        )

        # Always log to standard logger
        log_level = logging.INFO if actionable else logging.WARNING
        logger.log(
            log_level,
            f"AUDIT: {decision_type.value} signal_id={signal_id} "
            f"actionable={actionable} reason={reason}",
        )

        # Persist to Redis
        return self._persist_event(event)

    def _persist_event(self, event: PipelineAuditEvent) -> bool:
        """Persist audit event to Redis.

        Args:
            event: The audit event to persist

        Returns:
            True if persisted successfully
        """
        client = self._get_redis_client()
        if client is None:
            return False

        try:
            # Primary stream for all events
            stream_key = f"{_AUDIT_KEY_PREFIX}:events"
            client.xadd(stream_key, {"data": event.to_json()})

            # Separate stream by decision type for easy querying
            type_stream_key = f"{_AUDIT_KEY_PREFIX}:{event.decision_type.value}"
            client.xadd(type_stream_key, {"data": event.to_json()})

            # If signal was rejected, also add to rejected stream
            if not event.actionable:
                rejected_key = f"{_AUDIT_KEY_PREFIX}:rejected"
                client.xadd(rejected_key, {"data": event.to_json()})

            self._event_count += 1
            return True

        except Exception as e:
            self._failed_writes += 1
            logger.warning(f"PipelineAuditLogger: Failed to persist event: {e}")
            return False

    def log_quality_filter(
        self,
        signal_id: str,
        passed: bool,
        reason: str,
        quality_score: float | None,
        threshold: float,
        token: str = "",
        direction: str = "",
    ) -> bool:
        """Log a quality filter decision.

        Args:
            signal_id: Unique signal identifier
            passed: Whether signal passed the filter
            reason: Reason for the decision
            quality_score: The quality score that was evaluated
            threshold: The threshold that was used
            token: Trading pair/token
            direction: Signal direction

        Returns:
            True if logged successfully
        """
        metadata = {
            "quality_score": quality_score,
            "threshold": threshold,
        }
        return self.log_decision(
            signal_id=signal_id,
            decision_type=AuditDecisionType.QUALITY_FILTER,
            reason=reason,
            rejection_code=None if passed else "QUALITY_BELOW_THRESHOLD",
            actionable=passed,
            token=token,
            direction=direction,
            metadata=metadata,
        )

    def log_dedup(
        self,
        signal_id: str,
        is_duplicate: bool,
        window_start: float | None = None,
        window_end: float | None = None,
        token: str = "",
        direction: str = "",
    ) -> bool:
        """Log a deduplication decision.

        Args:
            signal_id: Unique signal identifier
            is_duplicate: Whether signal was a duplicate
            window_start: Start of dedup window (if duplicate)
            window_end: End of dedup window (if duplicate)
            token: Trading pair/token
            direction: Signal direction

        Returns:
            True if logged successfully
        """
        reason = (
            f"Duplicate signal detected (window={window_end - window_start:.1f}s)"
            if is_duplicate
            else "Signal is unique"
        )
        metadata = {
            "window_start": window_start,
            "window_end": window_end,
        }
        return self.log_decision(
            signal_id=signal_id,
            decision_type=AuditDecisionType.DEDUP_CHECK,
            reason=reason,
            rejection_code="DUPLICATE_SIGNAL" if is_duplicate else None,
            actionable=not is_duplicate,
            token=token,
            direction=direction,
            metadata=metadata,
        )

    def log_execution(
        self,
        signal_id: str,
        order_id: str,
        success: bool,
        reason: str,
        token: str = "",
        direction: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Log an execution decision.

        Args:
            signal_id: Unique signal identifier
            order_id: Exchange order ID
            success: Whether execution succeeded
            reason: Reason for the outcome
            token: Trading pair/token
            direction: Signal direction
            metadata: Additional execution metadata

        Returns:
            True if logged successfully
        """
        exec_metadata = {"order_id": order_id}
        if metadata:
            exec_metadata.update(metadata)

        return self.log_decision(
            signal_id=signal_id,
            decision_type=AuditDecisionType.EXECUTION,
            reason=reason,
            rejection_code=None if success else "EXECUTION_FAILED",
            actionable=success,
            token=token,
            direction=direction,
            metadata=exec_metadata,
        )

    def log_outcome(
        self,
        signal_id: str,
        order_id: str,
        outcome_type: str,
        pnl: float | None,
        token: str = "",
        direction: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Log an outcome decision.

        Args:
            signal_id: Unique signal identifier
            order_id: Exchange order ID
            outcome_type: Type of outcome (tp_hit, sl_hit, etc.)
            pnl: Profit/loss amount
            token: Trading pair/token
            direction: Signal direction
            metadata: Additional outcome metadata

        Returns:
            True if logged successfully
        """
        outcome_metadata = {
            "order_id": order_id,
            "outcome_type": outcome_type,
            "pnl": pnl,
        }
        if metadata:
            outcome_metadata.update(metadata)

        reason = f"Outcome recorded: {outcome_type}"
        if pnl is not None:
            reason += f" (PnL: {pnl:.2f})"

        return self.log_decision(
            signal_id=signal_id,
            decision_type=AuditDecisionType.OUTCOME,
            reason=reason,
            actionable=True,  # Outcomes don't affect actionability
            token=token,
            direction=direction,
            metadata=outcome_metadata,
        )

    def get_stats(self) -> dict[str, Any]:
        """Get audit logger statistics.

        Returns:
            Dictionary with statistics
        """
        return {
            "event_count": self._event_count,
            "failed_writes": self._failed_writes,
            "redis_host": self._redis_host,
            "redis_port": self._redis_port,
        }
