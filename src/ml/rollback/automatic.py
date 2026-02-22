"""Automatic rollback system for model validation failures.

This module provides automatic rollback capabilities when model validation
fails. It integrates with the model registry to revert to the previous
champion within 60 seconds.

Acceptance Criteria:
- Automatic rollback triggers on validation failure
- Rollback completes in <60 seconds
- Integration with model registry champion/challenger pattern

Example:
    >>> from ml.rollback.automatic import RollbackManager
    >>> from ml.model_registry.registry import ModelRegistry
    >>>
    >>> registry = ModelRegistry()
    >>> rollback = RollbackManager(registry=registry)
    >>>
    >>> # Trigger rollback on validation failure
    >>> result = await rollback.rollback_on_failure(
    ...     failed_version_id="grid_btc_1h_v2_20260222_120000",
    ...     reason="Validation failed: accuracy 0.65 < 0.75"
    ... )
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, auto
from typing import Any, Protocol

from ml.model_registry.registry import (
    ModelRegistry,
    ModelStatus,
    ModelType,
    ModelVersion,
)

logger = logging.getLogger(__name__)


class RollbackState(Enum):
    """States for rollback operations."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RollbackReason(Enum):
    """Reasons for rollback."""

    VALIDATION_FAILED = "validation_failed"
    PERFORMANCE_DEGRADATION = "performance_degradation"
    MANUAL = "manual"
    SYSTEM_ERROR = "system_error"


@dataclass(frozen=True)
class RollbackResult:
    """Result of a rollback operation.

    Attributes:
        success: Whether rollback succeeded
        rollback_id: Unique rollback identifier
        failed_version_id: Version that failed
        target_version_id: Version rolled back to
        state: Final state of rollback
        started_at: When rollback started
        completed_at: When rollback completed
        duration_seconds: Time taken for rollback
        reason: Reason for rollback
        message: Human-readable message
        evidence: Full evidence log
    """

    success: bool
    rollback_id: str
    failed_version_id: str
    target_version_id: str | None
    state: RollbackState
    started_at: datetime
    completed_at: datetime | None
    duration_seconds: float
    reason: RollbackReason
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "rollback_id": self.rollback_id,
            "failed_version_id": self.failed_version_id,
            "target_version_id": self.target_version_id,
            "state": self.state.value,
            "started_at": self.started_at.isoformat(),
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "duration_seconds": self.duration_seconds,
            "reason": self.reason.value,
            "message": self.message,
            "evidence": self.evidence,
        }


@dataclass
class RollbackConfig:
    """Configuration for rollback manager.

    Attributes:
        max_rollback_time_seconds: Maximum time allowed for rollback (AC5: <60s)
        auto_rollback_enabled: Whether auto-rollback is enabled
        require_confirmation: Require confirmation before rollback
        preserve_challenger: Keep challenger status for failed versions
        notification_channels: List of notification channels
    """

    max_rollback_time_seconds: float = 60.0  # AC5: Rollback completes in <60 seconds
    auto_rollback_enabled: bool = True
    require_confirmation: bool = False
    preserve_challenger: bool = False
    notification_channels: list[str] = field(default_factory=list)


class RollbackNotifier(Protocol):
    """Protocol for rollback notifications."""

    async def notify_rollback_started(
        self,
        rollback_id: str,
        failed_version: str,
        target_version: str | None,
    ) -> bool:
        """Notify that rollback has started."""
        ...

    async def notify_rollback_completed(
        self,
        rollback_id: str,
        result: RollbackResult,
    ) -> bool:
        """Notify that rollback has completed."""
        ...


class RollbackManager:
    """Manager for automatic rollback operations.

    AC4: Automatic rollback triggers on validation failure.
    AC5: Rollback completes in <60 seconds.

    This manager handles:
    - Automatic rollback on validation failure
    - Rollback to previous champion
    - Rollback completion within 60 seconds
    - Evidence logging
    """

    def __init__(
        self,
        registry: ModelRegistry,
        config: RollbackConfig | None = None,
        notifier: RollbackNotifier | None = None,
    ):
        """Initialize rollback manager.

        Args:
            registry: Model registry for version management
            config: Rollback configuration
            notifier: Optional notifier for rollback events
        """
        self._registry = registry
        self._config = config or RollbackConfig()
        self._notifier = notifier
        self._history: list[RollbackResult] = []

        logger.info(
            f"RollbackManager initialized: auto_rollback={self._config.auto_rollback_enabled}, "
            f"max_time={self._config.max_rollback_time_seconds}s"
        )

    def _generate_rollback_id(self) -> str:
        """Generate unique rollback ID."""
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")
        return f"rollback_{timestamp}"

    async def rollback_on_failure(
        self,
        failed_version_id: str,
        reason: RollbackReason = RollbackReason.VALIDATION_FAILED,
        details: str = "",
        force: bool = False,
    ) -> RollbackResult:
        """Execute rollback when validation fails.

        AC4: Automatic rollback triggers on validation failure.
        AC5: Rollback completes in <60 seconds.

        Args:
            failed_version_id: Version that failed validation
            reason: Reason for rollback
            details: Additional details
            force: Force rollback even if auto-rollback disabled

        Returns:
            RollbackResult with operation details
        """
        started_at = datetime.now(UTC)
        rollback_id = self._generate_rollback_id()

        # Check if auto-rollback is enabled
        if not force and not self._config.auto_rollback_enabled:
            duration = (datetime.now(UTC) - started_at).total_seconds()
            result = RollbackResult(
                success=False,
                rollback_id=rollback_id,
                failed_version_id=failed_version_id,
                target_version_id=None,
                state=RollbackState.CANCELLED,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_seconds=duration,
                reason=reason,
                message="Auto-rollback is disabled",
                evidence={"auto_rollback_enabled": False},
            )
            self._history.append(result)
            return result

        # Get failed version
        failed_version = self._registry.get_version(failed_version_id)
        if not failed_version:
            duration = (datetime.now(UTC) - started_at).total_seconds()
            result = RollbackResult(
                success=False,
                rollback_id=rollback_id,
                failed_version_id=failed_version_id,
                target_version_id=None,
                state=RollbackState.FAILED,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_seconds=duration,
                reason=reason,
                message=f"Failed version not found: {failed_version_id}",
                evidence={},
            )
            self._history.append(result)
            return result

        # Find rollback target
        target = self._registry.get_rollback_target(failed_version.model_type)

        if not target:
            duration = (datetime.now(UTC) - started_at).total_seconds()
            result = RollbackResult(
                success=False,
                rollback_id=rollback_id,
                failed_version_id=failed_version_id,
                target_version_id=None,
                state=RollbackState.FAILED,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_seconds=duration,
                reason=reason,
                message=f"No rollback target found for {failed_version.model_type.value}",
                evidence={"model_type": failed_version.model_type.value},
            )
            self._history.append(result)
            return result

        # Notify rollback started
        if self._notifier:
            await self._notifier.notify_rollback_started(
                rollback_id=rollback_id,
                failed_version=failed_version_id,
                target_version=target.version_id,
            )

        logger.info(
            f"Starting rollback: {failed_version_id} -> {target.version_id}, "
            f"reason={reason.value}"
        )

        try:
            # Execute rollback with timeout
            result = await asyncio.wait_for(
                self._execute_rollback(
                    rollback_id=rollback_id,
                    failed_version=failed_version,
                    target_version=target,
                    reason=reason,
                    started_at=started_at,
                    details=details,
                ),
                timeout=self._config.max_rollback_time_seconds,
            )

        except asyncio.TimeoutError:
            duration = (datetime.now(UTC) - started_at).total_seconds()
            result = RollbackResult(
                success=False,
                rollback_id=rollback_id,
                failed_version_id=failed_version_id,
                target_version_id=target.version_id,
                state=RollbackState.FAILED,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_seconds=duration,
                reason=reason,
                message=f"Rollback timeout after {self._config.max_rollback_time_seconds}s",
                evidence={"timeout": True},
            )
            logger.error(f"Rollback timeout: {rollback_id}")

        except Exception as e:
            duration = (datetime.now(UTC) - started_at).total_seconds()
            result = RollbackResult(
                success=False,
                rollback_id=rollback_id,
                failed_version_id=failed_version_id,
                target_version_id=target.version_id,
                state=RollbackState.FAILED,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_seconds=duration,
                reason=reason,
                message=f"Rollback failed: {str(e)}",
                evidence={"error": str(e)},
            )
            logger.exception(f"Rollback failed: {rollback_id}")

        # Store result
        self._history.append(result)

        # Notify completion
        if self._notifier:
            await self._notifier.notify_rollback_completed(rollback_id, result)

        return result

    async def _execute_rollback(
        self,
        rollback_id: str,
        failed_version: ModelVersion,
        target_version: ModelVersion,
        reason: RollbackReason,
        started_at: datetime,
        details: str,
    ) -> RollbackResult:
        """Execute the actual rollback operation.

        Args:
            rollback_id: Rollback identifier
            failed_version: Version that failed
            target_version: Version to roll back to
            reason: Reason for rollback
            started_at: When rollback started
            details: Additional details

        Returns:
            RollbackResult
        """
        evidence: dict[str, Any] = {
            "failed_version": failed_version.to_dict(),
            "target_version": target_version.to_dict(),
            "reason": reason.value,
            "details": details,
        }

        # Step 1: Mark failed version
        try:
            self._registry.mark_failed(
                failed_version.version_id,
                reason=f"{reason.value}: {details}" if details else reason.value,
            )
            evidence["marked_failed"] = True
        except Exception as e:
            evidence["marked_failed"] = False
            evidence["mark_failed_error"] = str(e)
            logger.warning(f"Failed to mark version as failed: {e}")

        # Step 2: Re-promote target to champion
        try:
            # Note: This is a simplified rollback. In production,
            # you might need to handle cases where the target was deprecated
            new_champion, _ = self._registry.promote_to_champion(
                target_version.version_id,
                force=True,  # Force promotion for rollback
            )
            evidence["promoted_to_champion"] = new_champion.version_id
        except Exception as e:
            evidence["promoted_to_champion"] = None
            evidence["promotion_error"] = str(e)
            logger.error(f"Failed to promote rollback target: {e}")

            duration = (datetime.now(UTC) - started_at).total_seconds()
            return RollbackResult(
                success=False,
                rollback_id=rollback_id,
                failed_version_id=failed_version.version_id,
                target_version_id=target_version.version_id,
                state=RollbackState.FAILED,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_seconds=duration,
                reason=reason,
                message=f"Failed to promote rollback target: {e}",
                evidence=evidence,
            )

        # Rollback successful
        completed_at = datetime.now(UTC)
        duration = (completed_at - started_at).total_seconds()

        logger.info(
            f"Rollback completed: {failed_version.version_id} -> {target_version.version_id}, "
            f"duration={duration:.2f}s"
        )

        return RollbackResult(
            success=True,
            rollback_id=rollback_id,
            failed_version_id=failed_version.version_id,
            target_version_id=target_version.version_id,
            state=RollbackState.COMPLETED,
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration,
            reason=reason,
            message=f"Rollback successful: reverted to {target_version.version_id}",
            evidence=evidence,
        )

    async def manual_rollback(
        self,
        target_version_id: str,
        reason: str = "Manual rollback",
    ) -> RollbackResult:
        """Execute manual rollback to a specific version.

        Args:
            target_version_id: Version to roll back to
            reason: Reason for rollback

        Returns:
            RollbackResult
        """
        started_at = datetime.now(UTC)
        rollback_id = self._generate_rollback_id()

        target = self._registry.get_version(target_version_id)
        if not target:
            duration = (datetime.now(UTC) - started_at).total_seconds()
            return RollbackResult(
                success=False,
                rollback_id=rollback_id,
                failed_version_id="manual",
                target_version_id=target_version_id,
                state=RollbackState.FAILED,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_seconds=duration,
                reason=RollbackReason.MANUAL,
                message=f"Target version not found: {target_version_id}",
                evidence={},
            )

        # Get current champion as "failed" version
        current_champion = self._registry.get_champion(target.model_type)
        failed_version_id = (
            current_champion.version_id if current_champion else "manual"
        )

        logger.info(f"Manual rollback: {failed_version_id} -> {target_version_id}")

        try:
            result = await asyncio.wait_for(
                self._execute_rollback(
                    rollback_id=rollback_id,
                    failed_version=current_champion or target,
                    target_version=target,
                    reason=RollbackReason.MANUAL,
                    started_at=started_at,
                    details=reason,
                ),
                timeout=self._config.max_rollback_time_seconds,
            )

        except asyncio.TimeoutError:
            duration = (datetime.now(UTC) - started_at).total_seconds()
            result = RollbackResult(
                success=False,
                rollback_id=rollback_id,
                failed_version_id=failed_version_id,
                target_version_id=target_version_id,
                state=RollbackState.FAILED,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_seconds=duration,
                reason=RollbackReason.MANUAL,
                message=f"Rollback timeout after {self._config.max_rollback_time_seconds}s",
                evidence={"timeout": True},
            )

        except Exception as e:
            duration = (datetime.now(UTC) - started_at).total_seconds()
            result = RollbackResult(
                success=False,
                rollback_id=rollback_id,
                failed_version_id=failed_version_id,
                target_version_id=target_version_id,
                state=RollbackState.FAILED,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_seconds=duration,
                reason=RollbackReason.MANUAL,
                message=f"Rollback failed: {str(e)}",
                evidence={"error": str(e)},
            )

        self._history.append(result)
        return result

    def get_rollback_history(
        self,
        limit: int = 10,
    ) -> list[RollbackResult]:
        """Get rollback history.

        Args:
            limit: Maximum number of results

        Returns:
            List of rollback results
        """
        return self._history[-limit:]

    def is_auto_rollback_enabled(self) -> bool:
        """Check if auto-rollback is enabled.

        Returns:
            True if enabled
        """
        return self._config.auto_rollback_enabled

    def enable_auto_rollback(self) -> None:
        """Enable automatic rollback."""
        self._config.auto_rollback_enabled = True
        logger.info("Auto-rollback enabled")

    def disable_auto_rollback(self) -> None:
        """Disable automatic rollback."""
        self._config.auto_rollback_enabled = False
        logger.info("Auto-rollback disabled")
