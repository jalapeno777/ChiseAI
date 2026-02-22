"""Self-Healing Engine with Action Sandboxing.

Main engine that coordinates failure pattern detection, healing action selection,
sandboxed execution, rollback on failure, anti-flap tracking, and human approval.

For ST-NS-040: Self-Healing Engine with Action Sandboxing
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from src.autonomous_control_plane.components.failure_pattern_matcher import (
    FailurePatternMatcher,
)
from src.autonomous_control_plane.healing_actions.base import BaseHealingAction
from src.autonomous_control_plane.healing_actions.redis_restart import (
    RedisRestartAction,
)
from src.autonomous_control_plane.healing_actions.api_timeout_recovery import (
    APIRetryAction,
)
from src.autonomous_control_plane.healing_actions.circuit_breaker_reset import (
    CircuitBreakerResetAction,
)
from src.autonomous_control_plane.models.healing import (
    ActionPriority,
    FailurePatternMatch,
    FailurePatternType,
    HealingAttempt,
    HealingContext,
    HealingResult,
    HealingStats,
    HealingStatus,
    LogEntry,
    ResourceLimits,
)
from src.common.circuit_breaker import CircuitBreakerRegistry

logger = logging.getLogger(__name__)


class SelfHealingEngine:
    """Self-healing engine with sandboxing and safety controls.

    Features:
    - Pattern matching integration with 10+ failure patterns
    - Healing action selection based on pattern type
    - Sandboxed execution with resource limits
    - Automatic rollback within 30s on failure
    - Anti-flap protection (max 3 attempts/hour/service)
    - Human approval workflow for P0/P1 live actions
    - Comprehensive logging for post-mortem analysis
    - Integration with CircuitBreakerRegistry and RetryCoordinator

    Example:
        >>> engine = SelfHealingEngine(trading_mode="paper")
        >>> log_entry = LogEntry(...)
        >>> result = await engine.process_log_entry(log_entry)
        >>> if result.success:
        ...     print(f"Healed: {result.action_type}")
    """

    # Maximum healing attempts per hour per service (anti-flap)
    MAX_ATTEMPTS_PER_HOUR = 3

    # Mapping from failure pattern types to healing actions
    PATTERN_TO_ACTION: dict[FailurePatternType, type[BaseHealingAction]] = {
        FailurePatternType.REDIS_DISCONNECT: RedisRestartAction,
        FailurePatternType.API_TIMEOUT: APIRetryAction,
        FailurePatternType.CIRCUIT_BREAKER_OPEN: CircuitBreakerResetAction,
        # Additional mappings would be added as more actions are implemented
    }

    def __init__(
        self,
        trading_mode: str = "paper",
        redis_client: Any | None = None,
        enable_approval_gates: bool = True,
    ):
        """Initialize self-healing engine.

        Args:
            trading_mode: Current trading mode (paper/live/production)
            redis_client: Redis client for state tracking
            enable_approval_gates: Whether to enable human approval gates
        """
        self._trading_mode = trading_mode
        self._redis = redis_client
        self._enable_approval_gates = enable_approval_gates

        # Initialize pattern matcher
        self._pattern_matcher = FailurePatternMatcher()
        self._pattern_matcher.register_default_patterns()

        # Initialize circuit breaker registry
        self._cb_registry = CircuitBreakerRegistry()

        # Healing attempt tracking (in-memory, backed by Redis if available)
        self._attempts: dict[str, list[HealingAttempt]] = {}
        self._pending_approvals: dict[str, HealingAttempt] = {}
        self._stats = HealingStats()

        # Engine state
        self._enabled = True
        self._healing_history: list[HealingAttempt] = []
        self._max_history = 1000

        # Global healing budget
        self.GLOBAL_BUDGET_KEY = "acp:healing:global_budget"
        self.GLOBAL_BUDGET_MAX = 20  # healings per hour
        self.GLOBAL_BUDGET_WINDOW_SECONDS = 3600  # 1 hour

        logger.info(
            f"SelfHealingEngine initialized (trading_mode={trading_mode}, "
            f"patterns={self._pattern_matcher.pattern_count})"
        )

    async def process_log_entry(self, log_entry: LogEntry) -> HealingAttempt | None:
        """Process a log entry and trigger healing if pattern matches.

        Args:
            log_entry: Log entry to process

        Returns:
            Healing attempt record or None if no action taken
        """
        if not self._enabled:
            logger.debug("Self-healing engine is disabled, skipping log entry")
            return None

        # Match against patterns
        match = self._pattern_matcher.match(log_entry)
        if not match.matched:
            return None

        logger.info(
            f"Matched pattern {match.pattern_type.value} for {log_entry.source} "
            f"(confidence={match.confidence:.2f})"
        )

        # Determine service name
        service = match.extracted_fields.get("service") or log_entry.source

        # Check anti-flap
        if not self._can_attempt_healing(service):
            logger.warning(
                f"Anti-flap: Max attempts exceeded for {service}, "
                f"skipping healing for pattern {match.pattern_type.value}"
            )
            return None

        # Create healing attempt
        attempt = HealingAttempt(
            service=service,
            action_type=self._get_action_type(match.pattern_type),
            attempt_number=self._get_attempt_count(service) + 1,
        )

        # Check if approval is required
        action_class = self.PATTERN_TO_ACTION.get(match.pattern_type)
        if action_class:
            temp_action = action_class()
            if temp_action.requires_human_approval(self._trading_mode):
                attempt.requires_approval = True
                attempt.status = HealingStatus.AWAITING_APPROVAL
                self._pending_approvals[attempt.attempt_id] = attempt
                logger.info(
                    f"Healing action {attempt.action_type} for {service} "
                    f"requires human approval (attempt_id={attempt.attempt_id})"
                )
                return attempt

        # Execute healing
        result = await self._execute_healing(attempt, match, log_entry)
        return result

    async def _check_global_budget(self) -> bool:
        """Check if global healing budget is available.

        Returns:
            True if budget available, False if exhausted
        """
        if not self._redis:
            # Without Redis, can't enforce global budget - allow healing
            return True

        try:
            # Get current count
            count_str = await self._redis.get(self.GLOBAL_BUDGET_KEY)
            if count_str is None:
                # No count means budget is fresh (full)
                return True

            count = int(count_str)
            if count >= self.GLOBAL_BUDGET_MAX:
                logger.warning(
                    f"Global healing budget exhausted: {count}/{self.GLOBAL_BUDGET_MAX} "
                    f"healings in last hour"
                )
                return False

            return True

        except Exception as e:
            logger.error(f"Error checking global budget: {e}")
            # Fail open on error (allow healing)
            return True

    async def _consume_budget(self) -> None:
        """Consume one unit from the global healing budget."""
        if not self._redis:
            return

        try:
            # Increment counter
            count = await self._redis.incr(self.GLOBAL_BUDGET_KEY)

            # Set expiry on first increment (when count == 1)
            if count == 1:
                await self._redis.expire(
                    self.GLOBAL_BUDGET_KEY, self.GLOBAL_BUDGET_WINDOW_SECONDS
                )

            logger.debug(f"Consumed global budget: {count}/{self.GLOBAL_BUDGET_MAX}")

        except Exception as e:
            logger.error(f"Error consuming global budget: {e}")

    def get_global_budget_status(self) -> dict[str, Any]:
        """Get current global budget status.

        Returns:
            Budget status dict
        """
        # Run async check in sync context for status
        try:
            import asyncio

            loop = asyncio.get_event_loop()

            async def get_status():
                if not self._redis:
                    return {
                        "enabled": False,
                        "reason": "Redis not available",
                        "max": self.GLOBAL_BUDGET_MAX,
                        "window_seconds": self.GLOBAL_BUDGET_WINDOW_SECONDS,
                    }

                count_str = await self._redis.get(self.GLOBAL_BUDGET_KEY)
                count = int(count_str) if count_str else 0
                ttl = await self._redis.ttl(self.GLOBAL_BUDGET_KEY)

                return {
                    "enabled": True,
                    "current": count,
                    "max": self.GLOBAL_BUDGET_MAX,
                    "remaining": max(0, self.GLOBAL_BUDGET_MAX - count),
                    "window_seconds": self.GLOBAL_BUDGET_WINDOW_SECONDS,
                    "ttl_seconds": ttl
                    if ttl > 0
                    else self.GLOBAL_BUDGET_WINDOW_SECONDS,
                }

            return loop.run_until_complete(get_status())
        except RuntimeError:
            # No event loop
            return {
                "enabled": self._redis is not None,
                "max": self.GLOBAL_BUDGET_MAX,
                "window_seconds": self.GLOBAL_BUDGET_WINDOW_SECONDS,
            }

    async def _execute_healing(
        self,
        attempt: HealingAttempt,
        match: FailurePatternMatch,
        log_entry: LogEntry,
    ) -> HealingAttempt:
        """Execute healing action.

        Args:
            attempt: Healing attempt record
            match: Pattern match result
            log_entry: Original log entry

        Returns:
            Updated healing attempt
        """
        # Check global budget first
        if not await self._check_global_budget():
            logger.warning(
                f"Skipping healing for {attempt.service}: global budget exhausted"
            )
            attempt.status = HealingStatus.FAILED
            error_result = HealingResult(
                success=False,
                action_id=attempt.attempt_id,
                action_type=attempt.action_type,
                service=attempt.service,
                error="Global healing budget exhausted",
            )
            attempt.complete(error_result)
            return attempt

        # Get action class
        action_class = self.PATTERN_TO_ACTION.get(match.pattern_type)
        if not action_class:
            logger.error(f"No healing action for pattern {match.pattern_type.value}")
            attempt.status = HealingStatus.FAILED
            attempt.complete(
                HealingResult(
                    success=False,
                    action_id=attempt.attempt_id,
                    action_type=attempt.action_type,
                    service=attempt.service,
                    error=f"No healing action for pattern {match.pattern_type.value}",
                )
            )
            return attempt

        # Consume budget before executing
        await self._consume_budget()

        # Create action instance
        action = action_class()

        # Create healing context
        context = HealingContext(
            service=attempt.service,
            action_id=attempt.attempt_id,
            attempt_number=attempt.attempt_number,
            triggered_by=match.pattern_type.value,
            log_entry=log_entry,
            resource_limits=action.get_resource_limits(),
        )

        # Record attempt start
        attempt.status = HealingStatus.IN_PROGRESS
        self._record_attempt(attempt)

        logger.info(
            f"Executing healing action {attempt.action_type} "
            f"for {attempt.service} (attempt {attempt.attempt_number})"
        )

        try:
            # Execute the healing action
            result = action.execute(context)
            attempt.complete(result)

            # Update stats
            self._stats.record_attempt(
                attempt.service,
                match.pattern_type.value,
                attempt.status,
            )

            # Record to history
            self._add_to_history(attempt)

            if result.success:
                logger.info(
                    f"Healing action {attempt.action_type} succeeded for {attempt.service}"
                )
            else:
                logger.error(
                    f"Healing action {attempt.action_type} failed for {attempt.service}: "
                    f"{result.error}"
                )
                # Rollback is handled within action.execute() on failure

        except Exception as e:
            logger.exception(f"Healing execution failed: {e}")
            attempt.status = HealingStatus.FAILED
            error_result = HealingResult(
                success=False,
                action_id=attempt.attempt_id,
                action_type=attempt.action_type,
                service=attempt.service,
                error=str(e),
            )
            attempt.complete(error_result)
            self._stats.record_attempt(
                attempt.service,
                match.pattern_type.value,
                attempt.status,
            )

        return attempt

    def approve_healing(
        self, attempt_id: str, approved_by: str
    ) -> HealingAttempt | None:
        """Approve a pending healing action.

        Args:
            attempt_id: ID of healing attempt to approve
            approved_by: User approving the action

        Returns:
            Updated attempt or None if not found
        """
        attempt = self._pending_approvals.pop(attempt_id, None)
        if not attempt:
            logger.warning(f"Approval requested for unknown attempt: {attempt_id}")
            return None

        attempt.approved_by = approved_by
        attempt.approved_at = datetime.now(UTC)
        attempt.status = HealingStatus.PENDING

        logger.info(f"Healing action {attempt_id} approved by {approved_by}")

        # Trigger async execution
        asyncio.create_task(self._execute_approved_healing(attempt))

        return attempt

    async def _execute_approved_healing(self, attempt: HealingAttempt) -> None:
        """Execute an approved healing action."""
        # Reconstruct the match and log entry from attempt context
        # In production, this would be stored with the pending approval
        logger.info(f"Executing approved healing action {attempt.attempt_id}")

        # Create a minimal log entry for execution
        log_entry = LogEntry(
            timestamp=datetime.now(UTC),
            level="ERROR",
            source=attempt.service,
            message="Approved healing action",
        )

        match = FailurePatternMatch(
            matched=True,
            pattern_type=self._get_pattern_type(attempt.action_type),
            confidence=1.0,
            extracted_fields={"service": attempt.service},
        )

        await self._execute_healing(attempt, match, log_entry)

    def reject_healing(
        self, attempt_id: str, rejected_by: str
    ) -> HealingAttempt | None:
        """Reject a pending healing action.

        Args:
            attempt_id: ID of healing attempt to reject
            rejected_by: User rejecting the action

        Returns:
            Updated attempt or None if not found
        """
        attempt = self._pending_approvals.pop(attempt_id, None)
        if not attempt:
            logger.warning(f"Rejection requested for unknown attempt: {attempt_id}")
            return None

        attempt.status = HealingStatus.REJECTED
        attempt.approved_by = rejected_by
        attempt.approved_at = datetime.now(UTC)

        logger.info(f"Healing action {attempt_id} rejected by {rejected_by}")

        self._stats.record_attempt(
            attempt.service,
            "unknown",
            attempt.status,
        )

        return attempt

    def _can_attempt_healing(self, service: str) -> bool:
        """Check if healing can be attempted for service (anti-flap).

        Args:
            service: Service name

        Returns:
            True if healing can proceed
        """
        attempts = self._get_recent_attempts(service)
        return len(attempts) < self.MAX_ATTEMPTS_PER_HOUR

    def _get_recent_attempts(self, service: str) -> list[HealingAttempt]:
        """Get healing attempts in last hour for service."""
        cutoff = datetime.now(UTC) - timedelta(hours=1)
        service_attempts = self._attempts.get(service, [])
        return [a for a in service_attempts if a.started_at > cutoff]

    def _get_attempt_count(self, service: str) -> int:
        """Get number of attempts in last hour for service."""
        return len(self._get_recent_attempts(service))

    def _record_attempt(self, attempt: HealingAttempt) -> None:
        """Record healing attempt."""
        if attempt.service not in self._attempts:
            self._attempts[attempt.service] = []
        self._attempts[attempt.service].append(attempt)

        # Trim old attempts
        cutoff = datetime.now(UTC) - timedelta(hours=24)
        for service in self._attempts:
            self._attempts[service] = [
                a for a in self._attempts[service] if a.started_at > cutoff
            ]

    def _add_to_history(self, attempt: HealingAttempt) -> None:
        """Add attempt to history."""
        self._healing_history.append(attempt)
        if len(self._healing_history) > self._max_history:
            self._healing_history = self._healing_history[-self._max_history :]

    def _get_action_type(self, pattern_type: FailurePatternType) -> str:
        """Get healing action type for pattern type."""
        action_class = self.PATTERN_TO_ACTION.get(pattern_type)
        return action_class.action_type if action_class else "unknown"

    def _get_pattern_type(self, action_type: str) -> FailurePatternType | None:
        """Get pattern type for action type."""
        for pattern_type, action_class in self.PATTERN_TO_ACTION.items():
            if action_class.action_type == action_type:
                return pattern_type
        return None

    # Public API methods

    def get_status(self) -> dict[str, Any]:
        """Get engine status."""
        return {
            "enabled": self._enabled,
            "trading_mode": self._trading_mode,
            "pattern_count": self._pattern_matcher.pattern_count,
            "pending_approvals": len(self._pending_approvals),
            "total_attempts": self._stats.total_attempts,
            "stats": self._stats.to_dict(),
            "global_budget": self.get_global_budget_status(),
        }

    def get_pending_approvals(self) -> list[HealingAttempt]:
        """Get list of pending approval requests."""
        return list(self._pending_approvals.values())

    def get_healing_history(
        self,
        service: str | None = None,
        limit: int = 100,
    ) -> list[HealingAttempt]:
        """Get healing history.

        Args:
            service: Filter by service (optional)
            limit: Maximum results

        Returns:
            List of healing attempts
        """
        history = self._healing_history

        if service:
            history = [h for h in history if h.service == service]

        return history[-limit:]

    def get_service_stats(self, service: str) -> dict[str, Any]:
        """Get stats for a specific service."""
        attempts = self._attempts.get(service, [])
        recent = self._get_recent_attempts(service)

        return {
            "service": service,
            "total_attempts": len(attempts),
            "attempts_last_hour": len(recent),
            "max_attempts_per_hour": self.MAX_ATTEMPTS_PER_HOUR,
            "can_attempt": self._can_attempt_healing(service),
            "recent_attempts": [a.to_dict() for a in recent[-5:]],
        }

    def disable(self) -> None:
        """Disable self-healing engine."""
        self._enabled = False
        logger.warning("SelfHealingEngine disabled")

    def enable(self) -> None:
        """Enable self-healing engine."""
        self._enabled = True
        logger.info("SelfHealingEngine enabled")

    def is_enabled(self) -> bool:
        """Check if engine is enabled."""
        return self._enabled
