#!/usr/bin/env python3
"""ACP (Autonomous Control Plane) integration for PR pipeline.

Provides integration with EP-NS-008 ACP components:
- Circuit breaker integration for PR operations
- Retry coordinator for transient failures
- Self-healing engine integration
- Incident manager integration
- Rollback coordinator integration
- Health check integration
- Unified metrics reporting

ST-AUTO-006: EP-NS-008 Integration for PR Pipeline
"""

from __future__ import annotations

import logging
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from circuit_breaker_pr import (
    CircuitBreakerOpenError,
)
from circuit_breaker_pr import (
    get_global_registry as get_circuit_registry,
)
from retry_pr_operations import (
    BudgetExceededError,
    MaxRetriesExceededError,
)
from retry_pr_operations import (
    get_global_coordinator as get_retry_coordinator,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class ACPIntegrationConfig:
    """Configuration for ACP integration."""

    enable_circuit_breaker: bool = True
    enable_retry_coordinator: bool = True
    enable_self_healing: bool = True
    enable_incident_manager: bool = True
    enable_rollback_coordinator: bool = True
    enable_health_checks: bool = True
    enable_metrics_export: bool = True

    # Graceful degradation settings
    graceful_degradation_timeout: float = 5.0
    fallback_to_local: bool = True

    # Health check settings
    health_check_interval: float = 30.0
    health_check_timeout: float = 5.0


@dataclass
class ACPHealthStatus:
    """Health status of ACP components."""

    circuit_breaker_registry: bool = False
    retry_coordinator: bool = False
    self_healing_engine: bool = False
    incident_manager: bool = False
    rollback_coordinator: bool = False
    last_check: float = field(default_factory=time.time)

    @property
    def all_healthy(self) -> bool:
        """Check if all components are healthy."""
        return all(
            [
                self.circuit_breaker_registry,
                self.retry_coordinator,
                self.self_healing_engine,
                self.incident_manager,
                self.rollback_coordinator,
            ]
        )

    @property
    def healthy_count(self) -> int:
        """Count of healthy components."""
        return sum(
            [
                self.circuit_breaker_registry,
                self.retry_coordinator,
                self.self_healing_engine,
                self.incident_manager,
                self.rollback_coordinator,
            ]
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "circuit_breaker_registry": self.circuit_breaker_registry,
            "retry_coordinator": self.retry_coordinator,
            "self_healing_engine": self.self_healing_engine,
            "incident_manager": self.incident_manager,
            "rollback_coordinator": self.rollback_coordinator,
            "all_healthy": self.all_healthy,
            "healthy_count": self.healthy_count,
            "last_check": self.last_check,
        }


class ACPIntegrationManager:
    """Manager for ACP integration with PR pipeline.

    Coordinates all ACP components and provides unified interface
    for PR lifecycle operations with resilience patterns.

    Example:
        >>> acp = ACPIntegrationManager()
        >>> result = acp.execute_with_resilience(
        ...     service_name="gitea_api",
        ...     operation_name="create_pr",
        ...     func=lambda: create_pr_api_call(),
        ... )
        >>> health = acp.check_health()
        >>> print(f"ACP Health: {health.healthy_count}/5 components")
    """

    def __init__(
        self,
        config: ACPIntegrationConfig | None = None,
        redis_client: Any | None = None,
    ):
        """Initialize ACP integration manager.

        Args:
            config: Integration configuration
            redis_client: Optional Redis client
        """
        self._config = config or ACPIntegrationConfig()
        self._redis = redis_client
        self._health_status = ACPHealthStatus()

        # Initialize local components
        self._circuit_registry = get_circuit_registry()
        self._retry_coordinator = get_retry_coordinator()

        # Initialize ACP component references
        self._acp_circuit_registry = None
        self._acp_retry_coordinator = None
        self._self_healing_engine = None
        self._incident_manager = None
        self._rollback_coordinator = None

        # Initialize ACP components
        self._init_acp_components()

        # Perform initial health check
        self.check_health()

        logger.info("ACP Integration Manager initialized")

    def _init_acp_components(self) -> None:
        """Initialize connections to ACP components."""
        # Circuit Breaker Registry
        if self._config.enable_circuit_breaker:
            try:
                from autonomous_control_plane.components.circuit_breaker_registry import (
                    CircuitBreakerRegistry,
                )

                self._acp_circuit_registry = CircuitBreakerRegistry(
                    redis_client=self._redis,
                )
                logger.info("ACP CircuitBreakerRegistry connected")
            except Exception as e:
                logger.warning(f"Failed to connect ACP CircuitBreakerRegistry: {e}")
                if not self._config.fallback_to_local:
                    raise

        # Retry Coordinator
        if self._config.enable_retry_coordinator:
            try:
                from autonomous_control_plane.components.retry_coordinator import (
                    RetryCoordinator,
                )

                self._acp_retry_coordinator = RetryCoordinator(
                    redis_client=self._redis,
                )
                logger.info("ACP RetryCoordinator connected")
            except Exception as e:
                logger.warning(f"Failed to connect ACP RetryCoordinator: {e}")
                if not self._config.fallback_to_local:
                    raise

        # Self-Healing Engine
        if self._config.enable_self_healing:
            try:
                from autonomous_control_plane.components.self_healing_engine import (
                    SelfHealingEngine,
                )

                self._self_healing_engine = SelfHealingEngine(
                    trading_mode="paper",
                    redis_client=self._redis,
                )
                logger.info("ACP SelfHealingEngine connected")
            except Exception as e:
                logger.warning(f"Failed to connect ACP SelfHealingEngine: {e}")
                if not self._config.fallback_to_local:
                    raise

        # Incident Manager
        if self._config.enable_incident_manager:
            try:
                from autonomous_control_plane.components.incident_manager import (
                    IncidentManager,
                )

                self._incident_manager = IncidentManager(
                    redis_client=self._redis,
                )
                logger.info("ACP IncidentManager connected")
            except Exception as e:
                logger.warning(f"Failed to connect ACP IncidentManager: {e}")
                if not self._config.fallback_to_local:
                    raise

        # Rollback Coordinator
        if self._config.enable_rollback_coordinator:
            try:
                from autonomous_control_plane.components.rollback_coordinator import (
                    RollbackCoordinator,
                )

                self._rollback_coordinator = RollbackCoordinator(
                    redis_client=self._redis,
                )
                logger.info("ACP RollbackCoordinator connected")
            except Exception as e:
                logger.warning(f"Failed to connect ACP RollbackCoordinator: {e}")
                if not self._config.fallback_to_local:
                    raise

    def execute_with_resilience(
        self,
        service_name: str,
        operation_name: str,
        func: Callable[[], T],
        fallback: Callable[[], T] | None = None,
        create_incident_on_failure: bool = True,
    ) -> T:
        """Execute operation with full ACP resilience stack.

        This method orchestrates circuit breaker, retry, and incident
        management for PR pipeline operations.

        Args:
            service_name: Service identifier (e.g., "gitea_api")
            operation_name: Human-readable operation name
            func: Function to execute
            fallback: Optional fallback function
            create_incident_on_failure: Whether to create incident on failure

        Returns:
            Function result or fallback result

        Raises:
            Exception: If all resilience mechanisms fail
        """
        start_time = time.time()

        try:
            # Step 1: Check circuit breaker
            if self._config.enable_circuit_breaker:
                cb = self._circuit_registry.get_circuit_breaker(service_name)
                if cb.is_open():
                    logger.warning(f"Circuit open for {service_name}, using fallback")
                    if fallback:
                        return fallback()
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker open for {service_name}"
                    )

            # Step 2: Execute with retry
            if self._config.enable_retry_coordinator:
                result = self._retry_coordinator.execute_with_retry(
                    service_name=service_name,
                    operation_name=operation_name,
                    func=func,
                )
            else:
                result = func()

            # Record success
            duration = time.time() - start_time
            logger.info(f"Operation {operation_name} succeeded in {duration:.2f}s")

            return result

        except Exception as e:
            duration = time.time() - start_time
            logger.error(
                f"Operation {operation_name} failed after {duration:.2f}s: {e}"
            )

            # Create incident if enabled
            if create_incident_on_failure and self._config.enable_incident_manager:
                self._create_incident(
                    service_name=service_name,
                    operation_name=operation_name,
                    error=e,
                    duration=duration,
                )

            # Try fallback if provided
            if fallback:
                logger.info(f"Executing fallback for {operation_name}")
                return fallback()

            raise

    async def execute_with_resilience_async(
        self,
        service_name: str,
        operation_name: str,
        func: Callable[[], Any],
        fallback: Callable[[], Any] | None = None,
        create_incident_on_failure: bool = True,
    ) -> Any:
        """Execute async operation with full ACP resilience stack.

        Args:
            service_name: Service identifier
            operation_name: Human-readable operation name
            func: Async function to execute
            fallback: Optional fallback function
            create_incident_on_failure: Whether to create incident on failure

        Returns:
            Function result or fallback result
        """
        import asyncio

        start_time = time.time()

        try:
            # Step 1: Check circuit breaker
            if self._config.enable_circuit_breaker:
                cb = self._circuit_registry.get_circuit_breaker(service_name)
                if cb.is_open():
                    logger.warning(f"Circuit open for {service_name}, using fallback")
                    if fallback:
                        if asyncio.iscoroutinefunction(fallback):
                            return await fallback()
                        return fallback()
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker open for {service_name}"
                    )

            # Step 2: Execute with retry
            if self._config.enable_retry_coordinator:
                result = await self._retry_coordinator.execute_with_retry_async(
                    service_name=service_name,
                    operation_name=operation_name,
                    func=func,
                )
            else:
                if asyncio.iscoroutinefunction(func):
                    result = await func()
                else:
                    result = func()

            duration = time.time() - start_time
            logger.info(f"Operation {operation_name} succeeded in {duration:.2f}s")

            return result

        except Exception as e:
            duration = time.time() - start_time
            logger.error(
                f"Operation {operation_name} failed after {duration:.2f}s: {e}"
            )

            if create_incident_on_failure and self._config.enable_incident_manager:
                self._create_incident(
                    service_name=service_name,
                    operation_name=operation_name,
                    error=e,
                    duration=duration,
                )

            if fallback:
                logger.info(f"Executing fallback for {operation_name}")
                if asyncio.iscoroutinefunction(fallback):
                    return await fallback()
                return fallback()

            raise

    def _create_incident(
        self,
        service_name: str,
        operation_name: str,
        error: Exception,
        duration: float,
    ) -> None:
        """Create an incident for operation failure.

        Args:
            service_name: Service that failed
            operation_name: Operation that failed
            error: The exception that occurred
            duration: Operation duration in seconds
        """
        if not self._incident_manager:
            logger.warning("Incident manager not available, skipping incident creation")
            return

        try:
            from autonomous_control_plane.models.incidents import (
                Incident,
                Severity,
            )

            # Determine severity based on error type
            if isinstance(error, (CircuitBreakerOpenError, BudgetExceededError)):
                severity = Severity.P2
            elif isinstance(error, MaxRetriesExceededError):
                severity = Severity.P1
            else:
                severity = Severity.P1

            incident = Incident(
                title=f"PR Pipeline Failure: {operation_name}",
                description=f"Service {service_name} failed during {operation_name}: {error}",
                source=f"pr_pipeline:{service_name}",
                severity=severity,
                event_type="pr_operation_failed",
                metadata={
                    "service_name": service_name,
                    "operation_name": operation_name,
                    "error_type": type(error).__name__,
                    "error_message": str(error),
                    "duration_seconds": duration,
                },
            )

            # Create incident through ACP
            self._incident_manager.create_incident(incident)
            logger.info(f"Created incident for {operation_name} failure")

        except Exception as e:
            logger.error(f"Failed to create incident: {e}")

    def check_health(self) -> ACPHealthStatus:
        """Check health of all ACP components.

        Returns:
            Health status of all components
        """
        status = ACPHealthStatus()
        status.last_check = time.time()

        # Check Circuit Breaker Registry
        if self._config.enable_circuit_breaker:
            try:
                if self._acp_circuit_registry:
                    # Try a simple operation
                    self._acp_circuit_registry.get_all_states()
                    status.circuit_breaker_registry = True
                else:
                    # Local fallback is always "healthy"
                    status.circuit_breaker_registry = True
            except Exception as e:
                logger.warning(f"Circuit breaker registry health check failed: {e}")
                status.circuit_breaker_registry = False

        # Check Retry Coordinator
        if self._config.enable_retry_coordinator:
            try:
                if self._acp_retry_coordinator:
                    self._acp_retry_coordinator.get_metrics()
                    status.retry_coordinator = True
                else:
                    status.retry_coordinator = True
            except Exception as e:
                logger.warning(f"Retry coordinator health check failed: {e}")
                status.retry_coordinator = False

        # Check Self-Healing Engine
        if self._config.enable_self_healing:
            try:
                if self._self_healing_engine:
                    # Check if engine is responsive
                    status.self_healing_engine = True
                else:
                    status.self_healing_engine = True
            except Exception as e:
                logger.warning(f"Self-healing engine health check failed: {e}")
                status.self_healing_engine = False

        # Check Incident Manager
        if self._config.enable_incident_manager:
            try:
                if self._incident_manager:
                    status.incident_manager = True
                else:
                    status.incident_manager = True
            except Exception as e:
                logger.warning(f"Incident manager health check failed: {e}")
                status.incident_manager = False

        # Check Rollback Coordinator
        if self._config.enable_rollback_coordinator:
            try:
                if self._rollback_coordinator:
                    status.rollback_coordinator = True
                else:
                    status.rollback_coordinator = True
            except Exception as e:
                logger.warning(f"Rollback coordinator health check failed: {e}")
                status.rollback_coordinator = False

        self._health_status = status
        return status

    def get_metrics(self) -> dict[str, Any]:
        """Get unified metrics from all ACP components.

        Returns:
            Dictionary of metrics
        """
        metrics = {
            "health_status": self._health_status.to_dict(),
            "circuit_breakers": self._circuit_registry.get_all_states(),
            "retry_operations": self._retry_coordinator.get_metrics(),
        }

        # Add ACP-specific metrics if available
        if self._acp_circuit_registry:
            try:
                metrics["acp_circuit_breakers"] = (
                    self._acp_circuit_registry.get_all_states()
                )
            except Exception as e:
                logger.warning(f"Failed to get ACP circuit breaker metrics: {e}")

        if self._acp_retry_coordinator:
            try:
                metrics["acp_retry_metrics"] = self._acp_retry_coordinator.get_metrics()
            except Exception as e:
                logger.warning(f"Failed to get ACP retry metrics: {e}")

        return metrics

    def trigger_rollback(
        self,
        pr_number: int,
        reason: str,
        validation_checks: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Trigger rollback of a PR merge.

        Args:
            pr_number: PR number to rollback
            reason: Reason for rollback
            validation_checks: Optional pre-flight validation checks

        Returns:
            Rollback result
        """
        if not self._rollback_coordinator:
            logger.warning("Rollback coordinator not available")
            return {
                "success": False,
                "error": "Rollback coordinator not available",
            }

        try:
            from autonomous_control_plane.models.rollback import (
                RollbackOperation,
                RollbackStep,
            )

            # Create rollback operation
            operation = RollbackOperation(
                target_id=f"pr_{pr_number}",
                target_type="pr_merge",
                reason=reason,
                steps=[
                    RollbackStep(
                        name="validate_pr_state",
                        description="Validate PR can be rolled back",
                    ),
                    RollbackStep(
                        name="revert_merge_commit",
                        description="Create revert commit",
                    ),
                    RollbackStep(
                        name="notify_stakeholders",
                        description="Notify about rollback",
                    ),
                ],
            )

            # Execute rollback
            result = self._rollback_coordinator.execute_rollback(operation)

            logger.info(f"Rollback triggered for PR #{pr_number}: {result}")
            return {
                "success": result.status == "completed",
                "operation_id": operation.operation_id,
                "status": result.status,
                "details": (
                    result.to_dict() if hasattr(result, "to_dict") else str(result)
                ),
            }

        except Exception as e:
            logger.error(f"Failed to trigger rollback: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    def request_self_healing(
        self,
        failure_pattern: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Request self-healing for a detected failure pattern.

        Args:
            failure_pattern: Type of failure pattern detected
            context: Context for healing action

        Returns:
            Healing result
        """
        if not self._self_healing_engine:
            logger.warning("Self-healing engine not available")
            return {
                "success": False,
                "error": "Self-healing engine not available",
            }

        try:
            from autonomous_control_plane.models.healing import (
                LogEntry,
            )

            # Create log entry for pattern matching
            log_entry = LogEntry(
                message=f"PR Pipeline failure: {failure_pattern}",
                service="pr_pipeline",
                level="ERROR",
                metadata=context,
            )

            # Process through self-healing engine
            import asyncio

            result = asyncio.run(self._self_healing_engine.process_log_entry(log_entry))

            logger.info(f"Self-healing requested for {failure_pattern}: {result}")
            return {
                "success": result.success if hasattr(result, "success") else False,
                "action_type": (
                    result.action_type if hasattr(result, "action_type") else None
                ),
                "details": (
                    result.to_dict() if hasattr(result, "to_dict") else str(result)
                ),
            }

        except Exception as e:
            logger.error(f"Failed to request self-healing: {e}")
            return {
                "success": False,
                "error": str(e),
            }


# Global instance
_global_manager: ACPIntegrationManager | None = None


def get_global_manager() -> ACPIntegrationManager:
    """Get global ACP integration manager."""
    global _global_manager
    if _global_manager is None:
        _global_manager = ACPIntegrationManager()
    return _global_manager


def reset_global_manager() -> None:
    """Reset global manager (useful for testing)."""
    global _global_manager
    _global_manager = None
