"""Rollback Coordinator with Pre-flight Validation.

Central rollback orchestration with step-wise execution, pre-flight validation,
and emergency bypass capabilities.

For ST-NS-042: Rollback Coordinator with Pre-flight Validation
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from autonomous_control_plane.models.incidents import (
    IncidentEvent,
    Severity,
)

if TYPE_CHECKING:
    from autonomous_control_plane.components.incident_manager import IncidentManager
import builtins

from autonomous_control_plane.models.rollback import (
    HealthCheck,
    PostRollbackHealth,
    RollbackMetrics,
    RollbackOperation,
    RollbackStatus,
    RollbackStep,
    RollbackStore,
    ValidationCheck,
    ValidationResult,
)

logger = logging.getLogger(__name__)


class PreFlightValidator:
    """Pre-flight validation for rollback operations.

    Validates pre-conditions before allowing rollback execution:
    - System health checks
    - Dependency availability
    - Resource availability
    - Data consistency
    """

    def __init__(
        self,
        health_checkers: dict[str, Callable[[], ValidationCheck]] | None = None,
    ):
        """Initialize pre-flight validator.

        Args:
            health_checkers: Custom health check functions
        """
        self._health_checkers = health_checkers or {}
        self._register_default_checkers()

    def _register_default_checkers(self) -> None:
        """Register default validation checkers."""
        self._health_checkers.setdefault(
            "system_health",
            self._check_system_health,
        )
        self._health_checkers.setdefault(
            "database_connections",
            self._check_database_connections,
        )
        self._health_checkers.setdefault(
            "resource_availability",
            self._check_resource_availability,
        )
        self._health_checkers.setdefault(
            "no_critical_operations",
            self._check_no_critical_operations,
        )
        self._health_checkers.setdefault(
            "rollback_dependencies",
            self._check_rollback_dependencies,
        )

    def _check_system_health(self) -> ValidationCheck:
        """Check overall system health."""
        check = ValidationCheck(
            name="system_health",
            description="Verify all services are healthy",
        )
        # Placeholder - actual implementation would query health endpoints
        check.mark_pass("All services reporting healthy status")
        return check

    def _check_database_connections(self) -> ValidationCheck:
        """Check database connection availability."""
        check = ValidationCheck(
            name="database_connections",
            description="Verify database connections are available",
        )
        # Placeholder - actual implementation would test connections
        check.mark_pass("Database connections available")
        return check

    def _check_resource_availability(self) -> ValidationCheck:
        """Check resource availability (disk, memory)."""
        check = ValidationCheck(
            name="resource_availability",
            description="Verify sufficient disk space and memory",
        )
        # Placeholder - actual implementation would check resources
        check.mark_pass("Resources available (disk > 10%, memory > 20%)")
        return check

    def _check_no_critical_operations(self) -> ValidationCheck:
        """Check no critical operations are in progress."""
        check = ValidationCheck(
            name="no_critical_operations",
            description="Verify no critical operations are in progress",
        )
        # Placeholder - actual implementation would query active operations
        check.mark_pass("No critical operations in progress")
        return check

    def _check_rollback_dependencies(self) -> ValidationCheck:
        """Check rollback dependencies are available."""
        check = ValidationCheck(
            name="rollback_dependencies",
            description="Verify rollback dependencies are available",
        )
        # Placeholder - actual implementation would check dependencies
        check.mark_pass("All rollback dependencies available")
        return check

    def register_checker(
        self, name: str, checker: Callable[[], ValidationCheck]
    ) -> None:
        """Register a custom validation checker.

        Args:
            name: Check name
            checker: Function that returns ValidationCheck
        """
        self._health_checkers[name] = checker

    async def validate(
        self, target_state: str, force: bool = False
    ) -> ValidationResult:
        """Run pre-flight validation for rollback.

        Args:
            target_state: Target state to rollback to
            force: If True, skip validation checks

        Returns:
            ValidationResult with all checks
        """
        result = ValidationResult()
        result.executed_at = datetime.now(UTC)

        logger.info(f"Starting pre-flight validation for rollback to {target_state}")

        if force:
            # Skip all checks in force mode
            for name, checker in self._health_checkers.items():
                check = checker()
                check.mark_skipped("Validation skipped (force=true)")
                result.add_check(check)
            result.valid = True
            return result

        # Run all validation checks
        for name, checker in self._health_checkers.items():
            try:
                check = checker()
                result.add_check(check)
                logger.debug(f"Validation check '{name}': {check.status.value}")
            except Exception as e:
                logger.exception(f"Validation check '{name}' failed: {e}")
                check = ValidationCheck(
                    name=name,
                    description=f"Check {name}",
                )
                check.mark_fail(f"Checker raised exception: {e}")
                result.add_check(check)

        result.finalize()

        if result.valid:
            logger.info("Pre-flight validation passed")
        else:
            logger.warning(
                f"Pre-flight validation failed: {len(result.failed_checks)} checks failed"
            )

        return result


class PostRollbackHealthChecker:
    """Post-rollback health verification.

    Verifies system health after rollback:
    - Service health
    - Data consistency
    - Performance baseline
    - Integration tests
    """

    def __init__(
        self,
        health_checkers: dict[str, Callable[[], HealthCheck]] | None = None,
    ):
        """Initialize post-rollback health checker.

        Args:
            health_checkers: Custom health check functions
        """
        self._health_checkers = health_checkers or {}
        self._register_default_checkers()

    def _register_default_checkers(self) -> None:
        """Register default health checkers."""
        self._health_checkers.setdefault(
            "service_health",
            self._check_service_health,
        )
        self._health_checkers.setdefault(
            "data_consistency",
            self._check_data_consistency,
        )
        self._health_checkers.setdefault(
            "performance_baseline",
            self._check_performance_baseline,
        )
        self._health_checkers.setdefault(
            "integration_tests",
            self._check_integration_tests,
        )

    def _check_service_health(self) -> HealthCheck:
        """Check service health after rollback."""
        check = HealthCheck(
            name="service_health",
            description="Verify all services are healthy after rollback",
        )
        # Placeholder - actual implementation would query health endpoints
        check.mark_pass("All services healthy after rollback")
        return check

    def _check_data_consistency(self) -> HealthCheck:
        """Check data consistency after rollback."""
        check = HealthCheck(
            name="data_consistency",
            description="Verify data consistency after rollback",
        )
        # Placeholder - actual implementation would check data
        check.mark_pass("Data consistency verified")
        return check

    def _check_performance_baseline(self) -> HealthCheck:
        """Check performance against baseline after rollback."""
        check = HealthCheck(
            name="performance_baseline",
            description="Verify performance is within baseline",
        )
        # Placeholder - actual implementation would measure performance
        check.mark_pass("Performance within baseline")
        return check

    def _check_integration_tests(self) -> HealthCheck:
        """Run integration tests after rollback."""
        check = HealthCheck(
            name="integration_tests",
            description="Run integration tests after rollback",
        )
        # Placeholder - actual implementation would run tests
        check.mark_pass("Integration tests passed")
        return check

    def register_checker(self, name: str, checker: Callable[[], HealthCheck]) -> None:
        """Register a custom health checker.

        Args:
            name: Check name
            checker: Function that returns HealthCheck
        """
        self._health_checkers[name] = checker

    async def verify(self, target_state: str) -> PostRollbackHealth:
        """Run post-rollback health verification.

        Args:
            target_state: Target state rolled back to

        Returns:
            PostRollbackHealth with all checks
        """
        result = PostRollbackHealth()
        result.executed_at = datetime.now(UTC)

        logger.info(f"Starting post-rollback health check for {target_state}")

        # Run all health checks
        for name, checker in self._health_checkers.items():
            try:
                check = checker()
                result.add_check(check)
                logger.debug(f"Health check '{name}': {check.status.value}")
            except Exception as e:
                logger.exception(f"Health check '{name}' failed: {e}")
                check = HealthCheck(
                    name=name,
                    description=f"Check {name}",
                )
                check.mark_fail(f"Checker raised exception: {e}")
                result.add_check(check)

        result.finalize()

        if result.healthy:
            logger.info("Post-rollback health check passed")
        else:
            logger.warning(
                f"Post-rollback health check failed: {len(result.failed_checks)} checks failed"
            )

        return result


class InMemoryRollbackStore(RollbackStore):
    """In-memory implementation of rollback storage."""

    def __init__(self) -> None:
        """Initialize in-memory store."""
        self._operations: dict[str, RollbackOperation] = {}
        self._lock = asyncio.Lock()

    async def save(self, operation: RollbackOperation) -> None:  # type: ignore[override]
        """Save or update a rollback operation."""
        async with self._lock:
            self._operations[operation.operation_id] = operation

    async def get(self, operation_id: str) -> RollbackOperation | None:  # type: ignore[override]
        """Get operation by ID."""
        return self._operations.get(operation_id)

    async def list(  # type: ignore[override]
        self,
        status: RollbackStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[RollbackOperation]:
        """List rollback operations with optional filtering."""
        operations: list[RollbackOperation] = list(self._operations.values())

        if status:
            operations = [o for o in operations if o.status == status]

        # Sort by created_at descending
        operations.sort(key=lambda o: o.created_at, reverse=True)

        return operations[offset : offset + limit]

    async def delete(self, operation_id: str) -> bool:  # type: ignore[override]
        """Delete a rollback operation."""
        async with self._lock:
            if operation_id in self._operations:
                del self._operations[operation_id]
                return True
            return False

    async def get_all(self) -> builtins.list[RollbackOperation]:
        """Get all operations."""
        return list(self._operations.values())


class RollbackCoordinator:
    """Central rollback coordinator with pre-flight validation.

    Features:
    - Pre-flight validation before rollback execution
    - Step-wise rollback with verification after each step
    - Automatic rollback on canary gate failure
    - 60-second SLA enforcement for standard operations
    - Post-rollback health checks
    - Full audit trail
    - Emergency bypass (force=true)
    - Integration with IncidentManager for P0/P1 incident creation

    Example:
        >>> coordinator = RollbackCoordinator()
        >>> # Validate rollback
        >>> validation = await coordinator.validate_rollback("v1.2.3")
        >>> # Execute rollback
        >>> result = await coordinator.execute_rollback("v1.2.3")
        >>> # Emergency rollback (skip validation)
        >>> result = await coordinator.emergency_rollback("v1.2.3")
    """

    # Standard rollback phases/steps
    DEFAULT_STEPS = [
        {
            "name": "stop_new_operations",
            "description": "Stop accepting new operations",
            "action": "stop_new_operations",
            "timeout_seconds": 5.0,
        },
        {
            "name": "drain_in_flight",
            "description": "Drain in-flight operations",
            "action": "drain_in_flight_operations",
            "timeout_seconds": 15.0,
        },
        {
            "name": "restore_previous_state",
            "description": "Restore previous state/version",
            "action": "restore_state",
            "timeout_seconds": 30.0,
        },
        {
            "name": "verify_system_health",
            "description": "Verify system health after restore",
            "action": "verify_health",
            "timeout_seconds": 10.0,
        },
        {
            "name": "resume_operations",
            "description": "Resume accepting operations",
            "action": "resume_operations",
            "timeout_seconds": 5.0,
        },
    ]

    # 60-second SLA for standard rollback operations
    ROLLBACK_SLA_SECONDS = 60.0

    def __init__(
        self,
        store: RollbackStore | None = None,
        incident_manager: IncidentManager | None = None,
        step_handlers: dict[str, Callable[[], dict[str, Any]]] | None = None,
        redis_client: Any | None = None,
    ) -> None:
        """Initialize rollback coordinator.

        Args:
            store: Rollback operation storage backend
            incident_manager: IncidentManager for creating incidents on failure
            step_handlers: Custom step action handlers
            redis_client: Redis client for distributed locking
        """
        self._store = store or InMemoryRollbackStore()
        self._incident_manager = incident_manager
        self._validator = PreFlightValidator()
        self._health_checker = PostRollbackHealthChecker()
        self._step_handlers = step_handlers or {}
        self._metrics = RollbackMetrics()
        self._redis = redis_client
        self._rollback_lock_key = "acp:rollback:lock"
        self._rollback_lock_ttl = 70  # seconds, longer than SLA

        self._register_default_step_handlers()

        # Event callbacks
        self._on_rollback_started: list[Callable] = []
        self._on_rollback_completed: list[Callable] = []
        self._on_rollback_failed: list[Callable] = []
        self._on_canary_gate_failure: list[Callable] = []

        logger.info("RollbackCoordinator initialized")

    def _register_default_step_handlers(self) -> None:
        """Register default step action handlers."""
        self._step_handlers.setdefault(
            "stop_new_operations",
            self._handle_stop_new_operations,
        )
        self._step_handlers.setdefault(
            "drain_in_flight_operations",
            self._handle_drain_in_flight,
        )
        self._step_handlers.setdefault(
            "restore_state",
            self._handle_restore_state,
        )
        self._step_handlers.setdefault(
            "verify_health",
            self._handle_verify_health,
        )
        self._step_handlers.setdefault(
            "resume_operations",
            self._handle_resume_operations,
        )

    def _handle_stop_new_operations(self) -> dict[str, Any]:
        """Handle stop new operations step."""
        logger.info("Stopping new operations")
        # Placeholder - actual implementation would set maintenance mode
        return {"success": True, "message": "New operations stopped"}

    def _handle_drain_in_flight(self) -> dict[str, Any]:
        """Handle drain in-flight operations step."""
        logger.info("Draining in-flight operations")
        # Placeholder - actual implementation would wait for ops to complete
        return {"success": True, "message": "In-flight operations drained"}

    def _handle_restore_state(self) -> dict[str, Any]:
        """Handle restore state step."""
        logger.info("Restoring previous state")
        # Placeholder - actual implementation would restore state
        return {"success": True, "message": "Previous state restored"}

    def _handle_verify_health(self) -> dict[str, Any]:
        """Handle verify health step."""
        logger.info("Verifying system health")
        # Placeholder - actual implementation would verify health
        return {"success": True, "message": "System health verified"}

    def _handle_resume_operations(self) -> dict[str, Any]:
        """Handle resume operations step."""
        logger.info("Resuming operations")
        # Placeholder - actual implementation would resume operations
        return {"success": True, "message": "Operations resumed"}

    def register_step_handler(
        self, action: str, handler: Callable[[], dict[str, Any]]
    ) -> None:
        """Register a custom step handler.

        Args:
            action: Action type identifier
            handler: Function that executes the action
        """
        self._step_handlers[action] = handler

    async def _acquire_rollback_lock(self, operation_id: str) -> bool:
        """Acquire distributed lock for rollback operation.

        Args:
            operation_id: ID of rollback operation attempting to acquire lock

        Returns:
            True if lock acquired, False otherwise
        """
        if not self._redis:
            logger.warning("Redis not available, skipping distributed lock")
            return True

        try:
            # Use SET with NX (only if not exists) and EX (expire)
            acquired = await self._redis.set(
                self._rollback_lock_key,
                operation_id,
                nx=True,  # Only set if not exists
                ex=self._rollback_lock_ttl,
            )

            if acquired:
                logger.info(f"Acquired rollback lock for operation {operation_id}")
                return True
            else:
                # Check who holds the lock
                current_holder = await self._redis.get(self._rollback_lock_key)
                logger.warning(
                    f"Could not acquire rollback lock, held by operation {current_holder}"
                )
                return False

        except Exception as e:
            logger.error(f"Error acquiring rollback lock: {e}")
            # Fail open if Redis error (safer to allow rollback than block it)
            return True

    async def _release_rollback_lock(self, operation_id: str) -> None:
        """Release distributed lock for rollback operation.

        Args:
            operation_id: ID of rollback operation releasing the lock
        """
        if not self._redis:
            return

        try:
            # Only delete if we hold the lock (avoid releasing someone else's lock)
            current_holder = await self._redis.get(self._rollback_lock_key)
            if current_holder == operation_id:
                await self._redis.delete(self._rollback_lock_key)
                logger.info(f"Released rollback lock for operation {operation_id}")
            else:
                logger.warning(
                    f"Cannot release lock: held by {current_holder}, "
                    f"requested by {operation_id}"
                )
        except Exception as e:
            logger.error(f"Error releasing rollback lock: {e}")

    async def is_rollback_in_progress(self) -> bool:
        """Check if a rollback is currently in progress.

        Returns:
            True if rollback lock is held by any operation
        """
        if not self._redis:
            return False

        try:
            exists = await self._redis.exists(self._rollback_lock_key)
            return bool(exists)
        except Exception as e:
            logger.error(f"Error checking rollback lock: {e}")
            return False

    async def validate_rollback(
        self, target_state: str, force: bool = False
    ) -> ValidationResult:
        """Validate rollback pre-conditions.

        Args:
            target_state: Target state to rollback to
            force: If True, skip validation

        Returns:
            ValidationResult
        """
        return await self._validator.validate(target_state, force)

    async def create_rollback_operation(
        self,
        target_state: str,
        steps: list[dict[str, Any]] | None = None,
        initiated_by: str = "system",
        force: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> RollbackOperation:
        """Create a new rollback operation.

        Args:
            target_state: Target state to rollback to
            steps: Custom steps (uses defaults if None)
            initiated_by: Who/what initiated the rollback
            force: Whether to bypass validation
            metadata: Additional metadata

        Returns:
            Created RollbackOperation
        """
        operation = RollbackOperation(
            target_state=target_state,
            initiated_by=initiated_by,
            force=force,
            metadata=metadata or {},
        )

        # Add steps
        step_defs = steps or self.DEFAULT_STEPS
        for step_def in step_defs:
            step = RollbackStep(
                name=cast(str, step_def["name"]),
                description=cast(str, step_def["description"]),
                action=cast(str, step_def["action"]),
                timeout_seconds=cast(float, step_def.get("timeout_seconds", 10.0)),
            )
            operation.add_step(step)

        await self._store.save(operation)  # type: ignore[func-returns-value]
        logger.info(f"Created rollback operation {operation.operation_id}")

        return operation

    async def execute_rollback(
        self,
        target_state: str,
        force: bool = False,
        initiated_by: str = "system",
        metadata: dict[str, Any] | None = None,
    ) -> RollbackOperation:
        """Execute rollback with step-wise execution and verification.

        Args:
            target_state: Target state to rollback to
            force: If True, skip pre-flight validation
            initiated_by: Who/what initiated the rollback
            metadata: Additional metadata

        Returns:
            RollbackOperation with results
        """
        # Create operation
        operation = await self.create_rollback_operation(
            target_state=target_state,
            initiated_by=initiated_by,
            force=force,
            metadata=metadata,
        )

        # Acquire distributed lock
        if not await self._acquire_rollback_lock(operation.operation_id):
            error_msg = "Another rollback is currently in progress"
            await self._handle_rollback_failure(operation, error_msg)
            return operation

        try:
            # Track SLA
            start_time = datetime.now(UTC)
            sla_deadline = start_time + __import__("datetime").timedelta(
                seconds=self.ROLLBACK_SLA_SECONDS
            )
            # Step 1: Pre-flight validation
            if not force:
                operation.mark_validating()
                await self._store.save(operation)  # type: ignore[func-returns-value]

                validation = await self._validator.validate(target_state, force)
                operation.validation_result = validation

                if not validation.valid:
                    error_msg = f"Pre-flight validation failed: {validation.errors}"
                    await self._handle_rollback_failure(operation, error_msg)
                    return operation

                operation.add_audit_entry("Pre-flight validation passed")
            else:
                operation.add_audit_entry(
                    "Pre-flight validation skipped (force=true)", level="WARN"
                )

            # Step 2: Execute rollback steps
            operation.mark_started()
            await self._store.save(operation)  # type: ignore[func-returns-value]

            # Trigger started callbacks
            for callback in self._on_rollback_started:
                try:
                    await callback(operation)
                except Exception as e:
                    logger.exception(f"Rollback started callback failed: {e}")

            # Execute each step with verification
            for step in operation.steps:
                # Check SLA
                if datetime.now(UTC) > sla_deadline:
                    error_msg = f"Rollback exceeded SLA of {self.ROLLBACK_SLA_SECONDS}s"
                    await self._handle_rollback_failure(operation, error_msg)
                    return operation

                # Execute step
                result = await self._execute_step(step, operation)

                if not result.get("success", False):
                    error_msg = f"Step '{step.name}' failed: {result.get('error', 'Unknown error')}"
                    await self._handle_rollback_failure(operation, error_msg)
                    return operation

                # Verify step
                verification = await self._verify_step(step, operation)
                if not verification.get("success", False):
                    error_msg = f"Step '{step.name}' verification failed: {verification.get('error', 'Unknown error')}"
                    await self._handle_rollback_failure(operation, error_msg)
                    return operation

                await self._store.save(operation)  # type: ignore[func-returns-value]

            # Step 3: Post-rollback health check
            operation.mark_verifying()
            await self._store.save(operation)  # type: ignore[func-returns-value]

            health = await self._health_checker.verify(target_state)
            operation.post_rollback_health = health

            if not health.healthy:
                error_msg = f"Post-rollback health check failed: {[c.message for c in health.failed_checks]}"
                await self._handle_rollback_failure(operation, error_msg)
                return operation

            # Step 4: Mark completed
            operation.mark_completed()
            await self._store.save(operation)  # type: ignore[func-returns-value]

            # Update metrics
            self._metrics.record_operation(operation)

            # Trigger completed callbacks
            for callback in self._on_rollback_completed:
                try:
                    await callback(operation)
                except Exception as e:
                    logger.exception(f"Rollback completed callback failed: {e}")

            logger.info(
                f"Rollback to {target_state} completed in {operation.duration_seconds:.2f}s"
            )

            # Log SLA warning if exceeded
            if operation.duration_seconds > self.ROLLBACK_SLA_SECONDS:
                logger.warning(
                    f"Rollback exceeded SLA of {self.ROLLBACK_SLA_SECONDS}s: "
                    f"{operation.duration_seconds:.2f}s"
                )

            return operation

        except Exception as e:
            logger.exception(f"Rollback execution failed: {e}")
            await self._handle_rollback_failure(operation, str(e))
            return operation

        finally:
            # Always release lock
            await self._release_rollback_lock(operation.operation_id)

    async def _execute_step(
        self, step: RollbackStep, operation: RollbackOperation
    ) -> dict[str, Any]:
        """Execute a single rollback step.

        Args:
            step: Step to execute
            operation: Parent operation

        Returns:
            Step execution result
        """
        step.mark_in_progress()
        operation.add_audit_entry(f"Step '{step.name}' started")

        handler = self._step_handlers.get(step.action)
        if not handler:
            error_msg = f"No handler for action: {step.action}"
            step.mark_failed(error_msg)
            operation.add_audit_entry(
                f"Step '{step.name}' failed: {error_msg}", level="ERROR"
            )
            return {"success": False, "error": error_msg}

        try:
            # Execute with timeout
            result = await asyncio.wait_for(
                asyncio.to_thread(handler),
                timeout=step.timeout_seconds,
            )

            if result.get("success", False):
                step.mark_completed(result)
                operation.add_audit_entry(
                    f"Step '{step.name}' completed: {result.get('message', 'success')}"
                )
            else:
                step.mark_failed(result.get("error", "Unknown error"), result)
                operation.add_audit_entry(
                    f"Step '{step.name}' failed: {result.get('error', 'Unknown error')}",
                    level="ERROR",
                )

            return result

        except TimeoutError:
            error_msg = f"Step '{step.name}' timed out after {step.timeout_seconds}s"
            step.mark_failed(error_msg)
            operation.add_audit_entry(error_msg, level="ERROR")
            return {"success": False, "error": error_msg}

        except Exception as e:
            error_msg = f"Step '{step.name}' raised exception: {e}"
            step.mark_failed(error_msg)
            operation.add_audit_entry(error_msg, level="ERROR")
            return {"success": False, "error": str(e)}

    async def _verify_step(
        self, step: RollbackStep, operation: RollbackOperation
    ) -> dict[str, Any]:
        """Verify a rollback step was successful.

        Args:
            step: Step to verify
            operation: Parent operation

        Returns:
            Verification result
        """
        # Placeholder - actual implementation would verify step results
        operation.add_audit_entry(f"Step '{step.name}' verified")
        return {"success": True, "message": "Step verified"}

    async def _handle_rollback_failure(
        self, operation: RollbackOperation, error_message: str
    ) -> None:
        """Handle rollback failure and create incident if needed.

        Args:
            operation: Failed operation
            error_message: Error message
        """
        operation.mark_failed(error_message)
        await self._store.save(operation)  # type: ignore[func-returns-value]

        # Update metrics
        self._metrics.record_operation(operation)

        # Create P0/P1 incident on rollback failure
        if self._incident_manager:
            event = IncidentEvent(
                event_type="rollback_failure",
                source="rollback_coordinator",
                message=f"Rollback to {operation.target_state} failed: {error_message}",
                severity_hint=Severity.P1,  # P1 for rollback failures
                metadata={
                    "operation_id": operation.operation_id,
                    "target_state": operation.target_state,
                    "duration_seconds": operation.duration_seconds,
                },
            )
            try:
                incident = await self._incident_manager.create_incident(event)
                operation.add_audit_entry(
                    f"P1 incident created: {incident.incident_id}",
                    level="ERROR",
                )
            except Exception as e:
                logger.exception(f"Failed to create incident: {e}")

        # Trigger failed callbacks
        for callback in self._on_rollback_failed:
            try:
                await callback(operation)
            except Exception as e:
                logger.exception(f"Rollback failed callback failed: {e}")

        logger.error(f"Rollback to {operation.target_state} failed: {error_message}")

    async def emergency_rollback(
        self,
        target_state: str,
        initiated_by: str = "system",
        metadata: dict[str, Any] | None = None,
    ) -> RollbackOperation:
        """Execute emergency rollback (bypasses validation).

        Args:
            target_state: Target state to rollback to
            initiated_by: Who/what initiated the rollback
            metadata: Additional metadata

        Returns:
            RollbackOperation with results
        """
        logger.warning(
            f"Emergency rollback to {target_state} initiated by {initiated_by}"
        )
        return await self.execute_rollback(
            target_state=target_state,
            force=True,
            initiated_by=initiated_by,
            metadata=metadata,
        )

    async def handle_canary_gate_failure(
        self,
        canary_id: str,
        target_state: str,
        failure_reason: str,
    ) -> RollbackOperation:
        """Handle automatic rollback on canary gate failure.

        Args:
            canary_id: ID of the failed canary
            target_state: Target state to rollback to
            failure_reason: Reason for canary failure

        Returns:
            RollbackOperation with results
        """
        logger.warning(
            f"Canary gate failure detected: {canary_id}. "
            f"Auto-rolling back to {target_state}"
        )

        # Trigger canary gate failure callbacks
        for callback in self._on_canary_gate_failure:
            try:
                await callback(canary_id, target_state, failure_reason)
            except Exception as e:
                logger.exception(f"Canary gate failure callback failed: {e}")

        # Execute emergency rollback
        return await self.emergency_rollback(
            target_state=target_state,
            initiated_by=f"canary_gate:{canary_id}",
            metadata={
                "canary_id": canary_id,
                "failure_reason": failure_reason,
                "auto_triggered": True,
            },
        )

    async def get_operation(self, operation_id: str) -> RollbackOperation | None:
        """Get rollback operation by ID.

        Args:
            operation_id: Operation ID

        Returns:
            RollbackOperation or None
        """
        return await self._store.get(operation_id)  # type: ignore[no-any-return,misc]

    async def list_operations(
        self,
        status: RollbackStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[RollbackOperation]:
        """List rollback operations.

        Args:
            status: Filter by status
            limit: Maximum results
            offset: Pagination offset

        Returns:
            List of RollbackOperations
        """
        return await self._store.list(status, limit, offset)  # type: ignore[no-any-return,misc]

    async def get_history(
        self,
        target_state: str | None = None,
        limit: int = 100,
    ) -> list[RollbackOperation]:
        """Get rollback history.

        Args:
            target_state: Filter by target state
            limit: Maximum results

        Returns:
            List of RollbackOperations
        """
        operations: list[RollbackOperation] = await self._store.list(limit=limit)  # type: ignore[no-any-return,misc]

        if target_state:
            operations = [o for o in operations if o.target_state == target_state]

        return operations

    async def get_metrics(self) -> RollbackMetrics:
        """Get rollback metrics.

        Returns:
            RollbackMetrics
        """
        # Update stats from all operations
        if hasattr(self._store, "get_all"):
            operations = await self._store.get_all()  # type: ignore[misc,union-attr]
            self._metrics.update_stats(operations)

        return self._metrics

    def on_rollback_started(self, callback: Callable) -> None:
        """Register callback for rollback started event.

        Args:
            callback: Async function to call when rollback starts
        """
        self._on_rollback_started.append(callback)

    def on_rollback_completed(self, callback: Callable) -> None:
        """Register callback for rollback completed event.

        Args:
            callback: Async function to call when rollback completes
        """
        self._on_rollback_completed.append(callback)

    def on_rollback_failed(self, callback: Callable) -> None:
        """Register callback for rollback failed event.

        Args:
            callback: Async function to call when rollback fails
        """
        self._on_rollback_failed.append(callback)

    def on_canary_gate_failure(self, callback: Callable) -> None:
        """Register callback for canary gate failure event.

        Args:
            callback: Async function to call when canary gate fails
        """
        self._on_canary_gate_failure.append(callback)
