"""Threshold Guardrails and Manual Override for ChiseAI Calibration System.

This module provides safety guardrails and manual override functionality for
dynamic threshold adjustments. It includes:

- Manual override API (pauses auto-adjustment for 7 days)
- Oscillation detection and freeze logic
- Boundary enforcement (min/max thresholds)
- Audit logging for all threshold changes

Acceptance Criteria:
- Manual override pauses auto-adjustment for 7 days
- Oscillation detection: 3+ direction changes in 7 days triggers 48h freeze
- Boundary enforcement: min 40%, max 95%
- Full audit logging for all changes
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, Protocol

from confidence.ece import SignalType

logger = logging.getLogger(__name__)


class OverrideReason(str, Enum):
    """Reasons for manual override."""

    MANUAL_ADJUSTMENT = "manual_adjustment"
    MARKET_CONDITIONS = "market_conditions"
    STRATEGY_CHANGE = "strategy_change"
    EXPERIMENT = "experiment"
    INCIDENT_RESPONSE = "incident_response"
    OTHER = "other"


class AuditEventType(str, Enum):
    """Types of audit events."""

    THRESHOLD_CHANGE = "threshold_change"
    MANUAL_OVERRIDE_ENABLED = "manual_override_enabled"
    MANUAL_OVERRIDE_DISABLED = "manual_override_disabled"
    OSCILLATION_FREEZE = "oscillation_freeze"
    OSCILLATION_UNFROZEN = "oscillation_unfrozen"
    BOUNDARY_ENFORCED = "boundary_enforced"


@dataclass(frozen=True)
class ManualOverride:
    """Record of a manual override.

    Attributes:
        strategy_id: Strategy identifier
        signal_type: Signal type affected
        enabled_at: When the override was enabled
        expires_at: When the override expires
        reason: Reason for the override
        override_reason: Categorized reason type
        user_id: ID of user who created the override
        threshold_value: Optional fixed threshold to use during override
        notes: Additional notes about the override
    """

    strategy_id: str
    signal_type: SignalType
    enabled_at: datetime
    expires_at: datetime
    reason: str
    override_reason: OverrideReason
    user_id: str
    threshold_value: float | None = None
    notes: str = ""

    @property
    def is_active(self) -> bool:
        """Check if the override is currently active."""
        return datetime.now(UTC) < self.expires_at

    def time_remaining(self) -> timedelta:
        """Get remaining time for the override."""
        remaining = self.expires_at - datetime.now(UTC)
        return max(remaining, timedelta(0))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "strategy_id": self.strategy_id,
            "signal_type": self.signal_type.value,
            "enabled_at": self.enabled_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "reason": self.reason,
            "override_reason": self.override_reason.value,
            "user_id": self.user_id,
            "threshold_value": (
                round(self.threshold_value, 4) if self.threshold_value else None
            ),
            "notes": self.notes,
            "is_active": self.is_active,
            "time_remaining_hours": self.time_remaining().total_seconds() / 3600,
        }


@dataclass(frozen=True)
class AuditLogEntry:
    """Single audit log entry.

    Attributes:
        timestamp: When the event occurred
        event_type: Type of event
        strategy_id: Strategy identifier
        signal_type: Signal type
        old_value: Previous value (if applicable)
        new_value: New value (if applicable)
        reason: Reason for the change
        user_id: User who made the change (or "system" for auto)
        metadata: Additional event metadata
    """

    timestamp: datetime
    event_type: AuditEventType
    strategy_id: str
    signal_type: SignalType
    old_value: float | None = None
    new_value: float | None = None
    reason: str = ""
    user_id: str = "system"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type.value,
            "strategy_id": self.strategy_id,
            "signal_type": self.signal_type.value,
            "old_value": (
                round(self.old_value, 4) if self.old_value is not None else None
            ),
            "new_value": (
                round(self.new_value, 4) if self.new_value is not None else None
            ),
            "reason": self.reason,
            "user_id": self.user_id,
            "metadata": self.metadata,
        }


@dataclass
class GuardrailConfig:
    """Configuration for threshold guardrails.

    Attributes:
        min_threshold: Minimum allowed threshold (default 0.40 = 40%)
        max_threshold: Maximum allowed threshold (default 0.95 = 95%)
        manual_override_duration_days: Days manual override is active (default 7)
        oscillation_window_days: Days to check for oscillation (default 7)
        oscillation_freeze_hours: Hours to freeze after oscillation (default 48)
        oscillation_direction_changes: Direction changes to trigger freeze (default 3)
    """

    min_threshold: float = 0.40
    max_threshold: float = 0.95
    manual_override_duration_days: int = 7
    oscillation_window_days: int = 7
    oscillation_freeze_hours: int = 48
    oscillation_direction_changes: int = 3

    def __post_init__(self) -> None:
        """Validate configuration."""
        if not 0.0 <= self.min_threshold <= 1.0:
            msg = f"min_threshold must be in [0, 1], got {self.min_threshold}"
            raise ValueError(msg)
        if not 0.0 <= self.max_threshold <= 1.0:
            msg = f"max_threshold must be in [0, 1], got {self.max_threshold}"
            raise ValueError(msg)
        if self.min_threshold >= self.max_threshold:
            msg = "min_threshold must be < max_threshold"
            raise ValueError(msg)


class ThresholdStorage(Protocol):
    """Protocol for threshold storage backends."""

    async def get_threshold(
        self,
        strategy_id: str,
        signal_type: SignalType,
    ) -> float | None:
        """Get current threshold for a strategy/signal type.

        Args:
            strategy_id: Strategy identifier
            signal_type: Signal type

        Returns:
            Current threshold or None if not set
        """
        ...

    async def set_threshold(
        self,
        strategy_id: str,
        signal_type: SignalType,
        value: float,
    ) -> bool:
        """Set threshold for a strategy/signal type.

        Args:
            strategy_id: Strategy identifier
            signal_type: Signal type
            value: New threshold value

        Returns:
            True if successful
        """
        ...


class ThresholdGuardrails:
    """Safety guardrails for threshold adjustments.

    Provides:
    - Manual override management (pauses auto-adjustment for 7 days)
    - Oscillation detection and freeze logic
    - Boundary enforcement (min/max thresholds)
    - Comprehensive audit logging

    Example:
        >>> from ml.calibration.threshold_guardrails import ThresholdGuardrails
        >>> guardrails = ThresholdGuardrails()
        >>> # Enable manual override
        >>> override = guardrails.enable_manual_override(
        ...     strategy_id="grid_btc_1h",
        ...     signal_type=SignalType.ENTRY,
        ...     reason="Market volatility",
        ...     user_id="user123"
        ... )
        >>> # Check if auto-adjustment is allowed
        >>> can_adjust = guardrails.can_auto_adjust("grid_btc_1h", SignalType.ENTRY)
    """

    def __init__(
        self,
        storage: ThresholdStorage | None = None,
        config: GuardrailConfig | None = None,
    ):
        """Initialize threshold guardrails.

        Args:
            storage: Storage backend for thresholds
            config: Guardrail configuration
        """
        self.storage = storage
        self.config = config or GuardrailConfig()
        self._overrides: dict[tuple[str, SignalType], ManualOverride] = {}
        self._frozen_until: dict[tuple[str, SignalType], datetime] = {}
        self._audit_log: list[AuditLogEntry] = []
        self._adjustment_history: list[AuditLogEntry] = []

        logger.info(
            f"ThresholdGuardrails initialized: "
            f"min={self.config.min_threshold}, max={self.config.max_threshold}, "
            f"override_duration={self.config.manual_override_duration_days}d"
        )

    def enable_manual_override(
        self,
        strategy_id: str,
        signal_type: SignalType,
        reason: str,
        user_id: str,
        override_reason: OverrideReason = OverrideReason.MANUAL_ADJUSTMENT,
        threshold_value: float | None = None,
        notes: str = "",
    ) -> ManualOverride:
        """Enable manual override for a strategy/signal type.

        This pauses automatic threshold adjustments for the configured
        duration (default 7 days).

        Args:
            strategy_id: Strategy identifier
            signal_type: Signal type
            reason: Human-readable reason for override
            user_id: ID of user enabling the override
            override_reason: Categorized reason type
            threshold_value: Optional fixed threshold to use during override
            notes: Additional notes

        Returns:
            ManualOverride record
        """
        now = datetime.now(UTC)
        expires_at = now + timedelta(days=self.config.manual_override_duration_days)

        override = ManualOverride(
            strategy_id=strategy_id,
            signal_type=signal_type,
            enabled_at=now,
            expires_at=expires_at,
            reason=reason,
            override_reason=override_reason,
            user_id=user_id,
            threshold_value=threshold_value,
            notes=notes,
        )

        self._overrides[(strategy_id, signal_type)] = override

        # Log the override
        self._log_audit(
            event_type=AuditEventType.MANUAL_OVERRIDE_ENABLED,
            strategy_id=strategy_id,
            signal_type=signal_type,
            reason=reason,
            user_id=user_id,
            metadata={
                "override_reason": override_reason.value,
                "threshold_value": threshold_value,
                "expires_at": expires_at.isoformat(),
            },
        )

        logger.info(
            f"Manual override enabled for {strategy_id}/{signal_type.value} "
            f"by {user_id}: {reason} (expires {expires_at})"
        )

        return override

    def disable_manual_override(
        self,
        strategy_id: str,
        signal_type: SignalType,
        user_id: str,
        reason: str = "",
    ) -> bool:
        """Disable manual override early.

        Args:
            strategy_id: Strategy identifier
            signal_type: Signal type
            user_id: ID of user disabling the override
            reason: Reason for early disable

        Returns:
            True if override was disabled, False if no override existed
        """
        key = (strategy_id, signal_type)
        if key not in self._overrides:
            return False

        del self._overrides[key]

        self._log_audit(
            event_type=AuditEventType.MANUAL_OVERRIDE_DISABLED,
            strategy_id=strategy_id,
            signal_type=signal_type,
            reason=reason,
            user_id=user_id,
        )

        logger.info(
            f"Manual override disabled for {strategy_id}/{signal_type.value} "
            f"by {user_id}"
        )

        return True

    def get_manual_override(
        self,
        strategy_id: str,
        signal_type: SignalType,
    ) -> ManualOverride | None:
        """Get active manual override for a strategy/signal type.

        Args:
            strategy_id: Strategy identifier
            signal_type: Signal type

        Returns:
            Active override or None
        """
        key = (strategy_id, signal_type)
        override = self._overrides.get(key)

        if override is None:
            return None

        # Check if expired
        if not override.is_active:
            del self._overrides[key]
            return None

        return override

    def can_auto_adjust(
        self,
        strategy_id: str,
        signal_type: SignalType,
    ) -> tuple[bool, str]:
        """Check if automatic adjustment is allowed.

        Args:
            strategy_id: Strategy identifier
            signal_type: Signal type

        Returns:
            Tuple of (allowed, reason_if_blocked)
        """
        # Check manual override
        override = self.get_manual_override(strategy_id, signal_type)
        if override is not None:
            remaining_hours = override.time_remaining().total_seconds() / 3600
            return (
                False,
                f"Manual override active (expires in {remaining_hours:.1f}h): "
                f"{override.reason}",
            )

        # Check oscillation freeze
        key = (strategy_id, signal_type)
        freeze_until = self._frozen_until.get(key)
        if freeze_until and datetime.now(UTC) < freeze_until:
            remaining = freeze_until - datetime.now(UTC)
            return (
                False,
                f"Oscillation freeze active "
                f"({remaining.total_seconds() / 3600:.1f}h remaining)",
            )

        return True, ""

    def enforce_boundaries(self, threshold: float) -> tuple[float, bool, str]:
        """Enforce threshold boundaries.

        Args:
            threshold: Proposed threshold value

        Returns:
            Tuple of (clamped_value, was_enforced, reason)
        """
        if threshold < self.config.min_threshold:
            return (
                self.config.min_threshold,
                True,
                f"Clamped to minimum threshold ({self.config.min_threshold})",
            )

        if threshold > self.config.max_threshold:
            return (
                self.config.max_threshold,
                True,
                f"Clamped to maximum threshold ({self.config.max_threshold})",
            )

        return threshold, False, ""

    def record_threshold_change(
        self,
        strategy_id: str,
        signal_type: SignalType,
        old_threshold: float,
        new_threshold: float,
        reason: str,
        user_id: str = "system",
        metadata: dict[str, Any] | None = None,
    ) -> AuditLogEntry:
        """Record a threshold change in the audit log.

        Args:
            strategy_id: Strategy identifier
            signal_type: Signal type
            old_threshold: Previous threshold
            new_threshold: New threshold
            reason: Reason for change
            user_id: User who made the change (or "system")
            metadata: Additional metadata

        Returns:
            Audit log entry
        """
        entry = AuditLogEntry(
            timestamp=datetime.now(UTC),
            event_type=AuditEventType.THRESHOLD_CHANGE,
            strategy_id=strategy_id,
            signal_type=signal_type,
            old_value=old_threshold,
            new_value=new_threshold,
            reason=reason,
            user_id=user_id,
            metadata=metadata or {},
        )

        self._audit_log.append(entry)
        self._adjustment_history.append(entry)

        logger.info(
            f"Threshold changed: {strategy_id}/{signal_type.value} "
            f"{old_threshold:.4f} -> {new_threshold:.4f} by {user_id}: {reason}"
        )

        return entry

    def detect_oscillation(
        self,
        strategy_id: str,
        signal_type: SignalType,
    ) -> tuple[bool, int]:
        """Detect oscillation in recent threshold adjustments.

        Args:
            strategy_id: Strategy identifier
            signal_type: Signal type

        Returns:
            Tuple of (oscillation_detected, direction_change_count)
        """
        cutoff = datetime.now(UTC) - timedelta(days=self.config.oscillation_window_days)

        # Get recent adjustments for this strategy/signal type
        recent = [
            e
            for e in self._adjustment_history
            if e.strategy_id == strategy_id
            and e.signal_type == signal_type
            and e.timestamp >= cutoff
            and e.event_type == AuditEventType.THRESHOLD_CHANGE
        ]

        if len(recent) < 2:
            return False, 0

        # Sort by timestamp
        recent_sorted = sorted(recent, key=lambda e: e.timestamp)

        # Count direction changes
        direction_changes = 0
        for i in range(1, len(recent_sorted)):
            prev = recent_sorted[i - 1]
            curr = recent_sorted[i]

            if prev.new_value is None or curr.new_value is None:
                continue

            prev_change = prev.new_value - (prev.old_value or 0)
            curr_change = curr.new_value - (curr.old_value or 0)

            prev_direction = 1 if prev_change > 0 else -1
            curr_direction = 1 if curr_change > 0 else -1

            if prev_direction != curr_direction:
                direction_changes += 1

        oscillation_detected = (
            direction_changes >= self.config.oscillation_direction_changes
        )

        return oscillation_detected, direction_changes

    def apply_oscillation_freeze(
        self,
        strategy_id: str,
        signal_type: SignalType,
    ) -> datetime | None:
        """Apply oscillation freeze to a strategy/signal type.

        Args:
            strategy_id: Strategy identifier
            signal_type: Signal type

        Returns:
            Freeze expiration time if freeze was applied, None otherwise
        """
        oscillation_detected, direction_changes = self.detect_oscillation(
            strategy_id, signal_type
        )

        if not oscillation_detected:
            return None

        freeze_until = datetime.now(UTC) + timedelta(
            hours=self.config.oscillation_freeze_hours
        )
        key = (strategy_id, signal_type)
        self._frozen_until[key] = freeze_until

        self._log_audit(
            event_type=AuditEventType.OSCILLATION_FREEZE,
            strategy_id=strategy_id,
            signal_type=signal_type,
            reason=(
                f"{direction_changes} direction changes in "
                f"{self.config.oscillation_window_days} days"
            ),
            metadata={
                "direction_changes": direction_changes,
                "freeze_until": freeze_until.isoformat(),
            },
        )

        logger.warning(
            f"Oscillation freeze applied to {strategy_id}/{signal_type.value}: "
            f"{direction_changes} direction changes, frozen until {freeze_until}"
        )

        return freeze_until

    def clear_oscillation_freeze(
        self,
        strategy_id: str,
        signal_type: SignalType,
        user_id: str,
        reason: str = "",
    ) -> bool:
        """Clear oscillation freeze early.

        Args:
            strategy_id: Strategy identifier
            signal_type: Signal type
            user_id: User clearing the freeze
            reason: Reason for clearing

        Returns:
            True if freeze was cleared, False if no freeze existed
        """
        key = (strategy_id, signal_type)
        if key not in self._frozen_until:
            return False

        del self._frozen_until[key]

        self._log_audit(
            event_type=AuditEventType.OSCILLATION_UNFROZEN,
            strategy_id=strategy_id,
            signal_type=signal_type,
            reason=reason,
            user_id=user_id,
        )

        logger.info(
            f"Oscillation freeze cleared for {strategy_id}/{signal_type.value} "
            f"by {user_id}"
        )

        return True

    def _log_audit(
        self,
        event_type: AuditEventType,
        strategy_id: str,
        signal_type: SignalType,
        reason: str,
        user_id: str = "system",
        old_value: float | None = None,
        new_value: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Log an audit entry."""
        entry = AuditLogEntry(
            timestamp=datetime.now(UTC),
            event_type=event_type,
            strategy_id=strategy_id,
            signal_type=signal_type,
            old_value=old_value,
            new_value=new_value,
            reason=reason,
            user_id=user_id,
            metadata=metadata or {},
        )
        self._audit_log.append(entry)

    def get_audit_log(
        self,
        strategy_id: str | None = None,
        signal_type: SignalType | None = None,
        event_type: AuditEventType | None = None,
        days: int = 30,
    ) -> list[AuditLogEntry]:
        """Get audit log entries.

        Args:
            strategy_id: Filter by strategy
            signal_type: Filter by signal type
            event_type: Filter by event type
            days: Number of days to look back

        Returns:
            List of matching audit log entries
        """
        cutoff = datetime.now(UTC) - timedelta(days=days)

        entries = self._audit_log

        if strategy_id is not None:
            entries = [e for e in entries if e.strategy_id == strategy_id]

        if signal_type is not None:
            entries = [e for e in entries if e.signal_type == signal_type]

        if event_type is not None:
            entries = [e for e in entries if e.event_type == event_type]

        entries = [e for e in entries if e.timestamp >= cutoff]

        return sorted(entries, key=lambda e: e.timestamp)

    def get_active_overrides(self) -> list[ManualOverride]:
        """Get all active manual overrides.

        Returns:
            List of active overrides
        """
        # Clean up expired overrides first
        expired = [
            key for key, override in self._overrides.items() if not override.is_active
        ]
        for key in expired:
            del self._overrides[key]

        return list(self._overrides.values())

    def get_frozen_strategies(self) -> list[tuple[str, SignalType, datetime]]:
        """Get all strategies currently under oscillation freeze.

        Returns:
            List of (strategy_id, signal_type, freeze_until) tuples
        """
        now = datetime.now(UTC)
        result = []

        for (strategy_id, signal_type), freeze_until in list(
            self._frozen_until.items()
        ):
            if now < freeze_until:
                result.append((strategy_id, signal_type, freeze_until))
            else:
                # Clean up expired freeze
                del self._frozen_until[(strategy_id, signal_type)]

        return result

    def validate_threshold_change(
        self,
        strategy_id: str,
        signal_type: SignalType,
        proposed_threshold: float,
    ) -> tuple[bool, str, float]:
        """Validate a proposed threshold change.

        Args:
            strategy_id: Strategy identifier
            signal_type: Signal type
            proposed_threshold: Proposed new threshold

        Returns:
            Tuple of (is_valid, reason, final_threshold)
        """
        # Check if auto-adjustment is allowed
        can_adjust, reason = self.can_auto_adjust(strategy_id, signal_type)
        if not can_adjust:
            return False, reason, proposed_threshold

        # Enforce boundaries
        final_threshold, was_enforced, boundary_reason = self.enforce_boundaries(
            proposed_threshold
        )

        if was_enforced:
            return True, boundary_reason, final_threshold

        return True, "", final_threshold

    def get_summary(self) -> dict[str, Any]:
        """Get summary of guardrail state.

        Returns:
            Dictionary with guardrail statistics
        """
        return {
            "active_overrides": len(self.get_active_overrides()),
            "frozen_strategies": len(self.get_frozen_strategies()),
            "total_audit_entries": len(self._audit_log),
            "config": {
                "min_threshold": self.config.min_threshold,
                "max_threshold": self.config.max_threshold,
                "manual_override_duration_days": (
                    self.config.manual_override_duration_days
                ),
                "oscillation_window_days": self.config.oscillation_window_days,
                "oscillation_freeze_hours": self.config.oscillation_freeze_hours,
            },
        }

    def reset(self) -> None:
        """Reset all state (for testing)."""
        self._overrides.clear()
        self._frozen_until.clear()
        self._audit_log.clear()
        self._adjustment_history.clear()
        logger.info("ThresholdGuardrails reset")


__all__ = [
    "ThresholdGuardrails",
    "ManualOverride",
    "OverrideReason",
    "AuditLogEntry",
    "AuditEventType",
    "GuardrailConfig",
    "ThresholdStorage",
]
