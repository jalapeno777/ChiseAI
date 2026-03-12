"""Rollback Automation Coordinator.

Provides intelligent automation features for the rollback coordinator:
- Automated rollback triggers
- Rollback templates
- Impact analysis
- Coordinated multi-service rollback
- Post-rollback validation suite

For ST-SAFETY-003: Rollback Automation
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from autonomous_control_plane.models.rollback import (
    CoordinatedRollbackConfig,
    PostRollbackValidationResult,
    RollbackCheckpoint,
    RollbackImpactAnalysis,
    RollbackOperation,
    RollbackRiskLevel,
    RollbackStatus,
    RollbackStep,
    RollbackTemplate,
    RollbackTemplateStep,
    RollbackTemplateType,
    RollbackTrigger,
    RollbackTriggerType,
)

if TYPE_CHECKING:
    from autonomous_control_plane.components.circuit_breaker_registry import (
        CircuitBreakerRegistry,
    )
    from autonomous_control_plane.components.retry_budget_manager import (
        RetryBudgetManager,
    )
    from autonomous_control_plane.components.rollback_coordinator import (
        RollbackCoordinator,
    )

logger = logging.getLogger(__name__)


class RollbackTemplateLibrary:
    """Library of pre-defined rollback templates."""

    def __init__(self) -> None:
        """Initialize template library with built-in templates."""
        self._templates: dict[str, RollbackTemplate] = {}
        self._register_builtin_templates()

    def _register_builtin_templates(self) -> None:
        """Register built-in rollback templates."""
        # Full Deployment Rollback Template
        full_deployment = RollbackTemplate(
            template_type=RollbackTemplateType.FULL_DEPLOYMENT,
            name="Full Deployment Rollback",
            description="Complete rollback of all services to previous deployment",
            parameters={
                "deployment_id": {"type": "string", "required": True},
                "previous_version": {"type": "string", "required": True},
                "graceful_shutdown": {"type": "boolean", "default": True},
            },
        )
        full_deployment.add_step(
            RollbackTemplateStep(
                name="pre_rollback_validation",
                description="Validate pre-rollback conditions",
                action="validate_pre_rollback",
                timeout_seconds=10.0,
            )
        )
        full_deployment.add_step(
            RollbackTemplateStep(
                name="stop_new_operations",
                description="Stop accepting new operations",
                action="stop_new_operations",
                timeout_seconds=5.0,
            )
        )
        full_deployment.add_step(
            RollbackTemplateStep(
                name="drain_in_flight",
                description="Drain in-flight operations",
                action="drain_in_flight_operations",
                timeout_seconds=30.0,
            )
        )
        full_deployment.add_step(
            RollbackTemplateStep(
                name="restore_deployment",
                description="Restore previous deployment version",
                action="restore_deployment",
                timeout_seconds=60.0,
            )
        )
        full_deployment.add_step(
            RollbackTemplateStep(
                name="verify_deployment",
                description="Verify deployment health",
                action="verify_deployment_health",
                timeout_seconds=15.0,
            )
        )
        full_deployment.add_step(
            RollbackTemplateStep(
                name="resume_operations",
                description="Resume accepting operations",
                action="resume_operations",
                timeout_seconds=5.0,
            )
        )
        self._templates[full_deployment.template_id] = full_deployment

        # Partial Service Rollback Template
        partial_service = RollbackTemplate(
            template_type=RollbackTemplateType.PARTIAL_SERVICE,
            name="Partial Service Rollback",
            description="Rollback specific services while keeping others running",
            parameters={
                "service_names": {"type": "array", "required": True},
                "previous_versions": {"type": "object", "required": True},
                "dependency_check": {"type": "boolean", "default": True},
            },
        )
        partial_service.add_step(
            RollbackTemplateStep(
                name="identify_services",
                description="Identify services to rollback",
                action="identify_services",
                timeout_seconds=5.0,
            )
        )
        partial_service.add_step(
            RollbackTemplateStep(
                name="check_dependencies",
                description="Check service dependencies",
                action="check_dependencies",
                timeout_seconds=10.0,
            )
        )
        partial_service.add_step(
            RollbackTemplateStep(
                name="stop_services",
                description="Stop target services gracefully",
                action="stop_services",
                timeout_seconds=15.0,
            )
        )
        partial_service.add_step(
            RollbackTemplateStep(
                name="restore_services",
                description="Restore services to previous versions",
                action="restore_services",
                timeout_seconds=30.0,
            )
        )
        partial_service.add_step(
            RollbackTemplateStep(
                name="verify_services",
                description="Verify restored services",
                action="verify_services",
                timeout_seconds=10.0,
            )
        )
        partial_service.add_step(
            RollbackTemplateStep(
                name="restart_services",
                description="Restart services",
                action="restart_services",
                timeout_seconds=15.0,
            )
        )
        self._templates[partial_service.template_id] = partial_service

        # Configuration Rollback Template
        configuration = RollbackTemplate(
            template_type=RollbackTemplateType.CONFIGURATION,
            name="Configuration Rollback",
            description="Rollback configuration changes without affecting code deployment",
            parameters={
                "config_keys": {"type": "array", "required": True},
                "previous_values": {"type": "object", "required": True},
                "config_store": {"type": "string", "default": "redis"},
            },
        )
        configuration.add_step(
            RollbackTemplateStep(
                name="backup_current_config",
                description="Backup current configuration",
                action="backup_config",
                timeout_seconds=5.0,
            )
        )
        configuration.add_step(
            RollbackTemplateStep(
                name="restore_config_values",
                description="Restore previous configuration values",
                action="restore_config",
                timeout_seconds=10.0,
            )
        )
        configuration.add_step(
            RollbackTemplateStep(
                name="reload_config",
                description="Reload configuration in services",
                action="reload_config",
                timeout_seconds=15.0,
            )
        )
        configuration.add_step(
            RollbackTemplateStep(
                name="verify_config",
                description="Verify configuration applied correctly",
                action="verify_config",
                timeout_seconds=10.0,
            )
        )
        self._templates[configuration.template_id] = configuration

    def get_template(self, template_id: str) -> RollbackTemplate | None:
        """Get a template by ID.

        Args:
            template_id: Template identifier

        Returns:
            RollbackTemplate or None if not found
        """
        return self._templates.get(template_id)

    def get_template_by_type(
        self, template_type: RollbackTemplateType
    ) -> RollbackTemplate | None:
        """Get first template of a specific type.

        Args:
            template_type: Type of template to find

        Returns:
            RollbackTemplate or None if not found
        """
        for template in self._templates.values():
            if template.template_type == template_type:
                return template
        return None

    def list_templates(self) -> list[RollbackTemplate]:
        """List all available templates.

        Returns:
            List of RollbackTemplates
        """
        return list(self._templates.values())

    def add_template(self, template: RollbackTemplate) -> None:
        """Add a custom template.

        Args:
            template: Template to add

        Raises:
            ValueError: If template is invalid
        """
        errors = template.validate()
        if errors:
            raise ValueError(f"Invalid template: {', '.join(errors)}")
        self._templates[template.template_id] = template
        logger.info(f"Added custom template: {template.name} ({template.template_id})")

    def remove_template(self, template_id: str) -> bool:
        """Remove a template.

        Args:
            template_id: Template ID to remove

        Returns:
            True if removed, False if not found
        """
        if template_id in self._templates:
            del self._templates[template_id]
            logger.info(f"Removed template: {template_id}")
            return True
        return False


class RollbackTriggerManager:
    """Manages automated rollback triggers."""

    # Default trigger configurations by sensitivity
    SENSITIVITY_CONFIGS = {
        "low": {
            "circuit_breaker_threshold": 5,  # 5+ breakers open
            "error_rate_threshold": 0.5,  # 50% error rate
            "error_rate_duration": 300,  # 5 minutes
            "health_check_failures": 5,  # 5 consecutive failures
        },
        "medium": {
            "circuit_breaker_threshold": 3,  # 3+ breakers open
            "error_rate_threshold": 0.3,  # 30% error rate
            "error_rate_duration": 180,  # 3 minutes
            "health_check_failures": 3,  # 3 consecutive failures
        },
        "high": {
            "circuit_breaker_threshold": 2,  # 2+ breakers open
            "error_rate_threshold": 0.15,  # 15% error rate
            "error_rate_duration": 60,  # 1 minute
            "health_check_failures": 2,  # 2 consecutive failures
        },
    }

    def __init__(
        self,
        rollback_coordinator: RollbackCoordinator,
        circuit_breaker_registry: CircuitBreakerRegistry | None = None,
        retry_budget_manager: RetryBudgetManager | None = None,
    ) -> None:
        """Initialize trigger manager.

        Args:
            rollback_coordinator: Coordinator for executing rollbacks
            circuit_breaker_registry: Registry for circuit breaker monitoring
            retry_budget_manager: Manager for retry budget monitoring
        """
        self._coordinator = rollback_coordinator
        self._cb_registry = circuit_breaker_registry
        self._budget_manager = retry_budget_manager
        self._triggers: dict[str, RollbackTrigger] = {}
        self._monitoring = False
        self._monitor_task: asyncio.Task | None = None
        self._on_trigger_fired: list[
            Callable[[RollbackTrigger, RollbackOperation], None]
        ] = []

    def register_trigger(self, trigger: RollbackTrigger) -> None:
        """Register a new trigger.

        Args:
            trigger: Trigger to register
        """
        self._triggers[trigger.trigger_id] = trigger
        logger.info(f"Registered trigger: {trigger.name} ({trigger.trigger_id})")

    def unregister_trigger(self, trigger_id: str) -> bool:
        """Unregister a trigger.

        Args:
            trigger_id: Trigger ID to remove

        Returns:
            True if removed, False if not found
        """
        if trigger_id in self._triggers:
            del self._triggers[trigger_id]
            logger.info(f"Unregistered trigger: {trigger_id}")
            return True
        return False

    def get_trigger(self, trigger_id: str) -> RollbackTrigger | None:
        """Get a trigger by ID.

        Args:
            trigger_id: Trigger identifier

        Returns:
            RollbackTrigger or None
        """
        return self._triggers.get(trigger_id)

    def list_triggers(self, enabled_only: bool = False) -> list[RollbackTrigger]:
        """List all triggers.

        Args:
            enabled_only: If True, only return enabled triggers

        Returns:
            List of triggers
        """
        triggers = list(self._triggers.values())
        if enabled_only:
            triggers = [t for t in triggers if t.enabled]
        return triggers

    def create_default_triggers(
        self,
        target_state: str,
        template_id: str,
        sensitivity: str = "medium",
    ) -> list[RollbackTrigger]:
        """Create default triggers with standard configurations.

        Args:
            target_state: Target state for rollback
            template_id: Template to use
            sensitivity: Sensitivity level (low/medium/high)

        Returns:
            List of created triggers
        """
        config = self.SENSITIVITY_CONFIGS.get(
            sensitivity, self.SENSITIVITY_CONFIGS["medium"]
        )
        triggers = []

        # Circuit breaker group trigger
        cb_trigger = RollbackTrigger(
            trigger_type=RollbackTriggerType.CIRCUIT_BREAKER_GROUP,
            name="Circuit Breaker Group Failure",
            description=f"Trigger when {config['circuit_breaker_threshold']}+ circuit breakers are open",
            conditions={
                "threshold": config["circuit_breaker_threshold"],
                "groups": [],  # Monitor all groups
            },
            target_state=target_state,
            template_id=template_id,
            sensitivity=sensitivity,
            require_confirmation=sensitivity == "low",
        )
        self.register_trigger(cb_trigger)
        triggers.append(cb_trigger)

        # Error rate threshold trigger
        error_trigger = RollbackTrigger(
            trigger_type=RollbackTriggerType.ERROR_RATE_THRESHOLD,
            name="Error Rate Threshold Exceeded",
            description=f"Trigger when error rate exceeds {config['error_rate_threshold']:.0%} for {config['error_rate_duration']}s",
            conditions={
                "threshold": config["error_rate_threshold"],
                "duration_seconds": config["error_rate_duration"],
            },
            target_state=target_state,
            template_id=template_id,
            sensitivity=sensitivity,
            require_confirmation=sensitivity == "low",
        )
        self.register_trigger(error_trigger)
        triggers.append(error_trigger)

        # Health check cascade trigger
        health_trigger = RollbackTrigger(
            trigger_type=RollbackTriggerType.HEALTH_CHECK_CASCADE,
            name="Health Check Cascade Failure",
            description=f"Trigger when {config['health_check_failures']}+ health checks fail in cascade",
            conditions={
                "consecutive_failures": config["health_check_failures"],
            },
            target_state=target_state,
            template_id=template_id,
            sensitivity=sensitivity,
            require_confirmation=sensitivity == "low",
        )
        self.register_trigger(health_trigger)
        triggers.append(health_trigger)

        return triggers

    async def start_monitoring(self, interval_seconds: float = 10.0) -> None:
        """Start monitoring triggers.

        Args:
            interval_seconds: Monitoring interval
        """
        if self._monitoring:
            return

        self._monitoring = True
        self._monitor_task = asyncio.create_task(self._monitor_loop(interval_seconds))
        logger.info(f"Started trigger monitoring (interval={interval_seconds}s)")

    async def stop_monitoring(self) -> None:
        """Stop monitoring triggers."""
        self._monitoring = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None
        logger.info("Stopped trigger monitoring")

    async def _monitor_loop(self, interval_seconds: float) -> None:
        """Main monitoring loop."""
        while self._monitoring:
            try:
                await self._check_triggers()
                await asyncio.sleep(interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Error in trigger monitoring loop: {e}")
                await asyncio.sleep(interval_seconds)

    async def _check_triggers(self) -> None:
        """Check all enabled triggers."""
        for trigger in self._triggers.values():
            if not trigger.enabled:
                continue

            try:
                should_trigger = await self._evaluate_trigger(trigger)
                if should_trigger:
                    await self._fire_trigger(trigger)
            except Exception as e:
                logger.exception(f"Error evaluating trigger {trigger.trigger_id}: {e}")

    async def _evaluate_trigger(self, trigger: RollbackTrigger) -> bool:
        """Evaluate if a trigger should fire.

        Args:
            trigger: Trigger to evaluate

        Returns:
            True if trigger should fire
        """
        if trigger.trigger_type == RollbackTriggerType.CIRCUIT_BREAKER_GROUP:
            return await self._evaluate_circuit_breaker_trigger(trigger)
        elif trigger.trigger_type == RollbackTriggerType.RETRY_BUDGET_POOL:
            return await self._evaluate_retry_budget_trigger(trigger)
        elif trigger.trigger_type == RollbackTriggerType.ERROR_RATE_THRESHOLD:
            return await self._evaluate_error_rate_trigger(trigger)
        elif trigger.trigger_type == RollbackTriggerType.HEALTH_CHECK_CASCADE:
            return await self._evaluate_health_check_trigger(trigger)

        return False

    async def _evaluate_circuit_breaker_trigger(self, trigger: RollbackTrigger) -> bool:
        """Evaluate circuit breaker group trigger."""
        if not self._cb_registry:
            return False

        threshold = trigger.conditions.get("threshold", 3)
        groups = trigger.conditions.get("groups", [])

        # Check specific groups or all groups
        if groups:
            for group_name in groups:
                metrics = self._cb_registry.get_group_metrics(group_name)
                if metrics and metrics.open_count >= threshold:
                    return True
        else:
            # Check all groups
            all_groups = self._cb_registry.list_groups()
            for group_name in all_groups:
                metrics = self._cb_registry.get_group_metrics(group_name)
                if metrics and metrics.open_count >= threshold:
                    return True

            # Also check if enough individual breakers are open
            all_states = self._cb_registry.get_all_states()
            open_count = sum(1 for s in all_states.values() if s.state.value == "open")
            if open_count >= threshold:
                return True

        return False

    async def _evaluate_retry_budget_trigger(self, trigger: RollbackTrigger) -> bool:
        """Evaluate retry budget pool trigger."""
        if not self._budget_manager:
            return False

        pool_ids = trigger.conditions.get("pool_ids", [])
        critical_services = trigger.conditions.get("critical_services", [])

        # Check specific pools
        for pool_id in pool_ids:
            status = self._budget_manager.get_pool_status(pool_id)
            if status:
                total = status.get("total_budget", 0)
                used = status.get("used_budget", 0)
                if total > 0 and used >= total:
                    return True

        # Check critical services
        for service in critical_services:
            status = self._budget_manager.get_budget_status(service)
            if status.get("is_exceeded", False):
                return True

        return False

    async def _evaluate_error_rate_trigger(self, trigger: RollbackTrigger) -> bool:
        """Evaluate error rate threshold trigger."""
        # This would integrate with metrics/telemetry system
        # For now, placeholder implementation
        threshold = trigger.conditions.get("threshold", 0.3)
        duration_seconds = trigger.conditions.get("duration_seconds", 180)

        # TODO: Integrate with actual metrics system
        # This is a placeholder that always returns False
        # In production, this would query metrics for error rates
        logger.debug(
            f"Error rate trigger check: threshold={threshold}, "
            f"duration={duration_seconds}s (placeholder)"
        )
        return False

    async def _evaluate_health_check_trigger(self, trigger: RollbackTrigger) -> bool:
        """Evaluate health check cascade trigger."""
        consecutive_failures = trigger.conditions.get("consecutive_failures", 3)
        services = trigger.conditions.get("services", [])

        # This would integrate with health check system
        # For now, placeholder implementation
        logger.debug(
            f"Health check trigger check: consecutive_failures={consecutive_failures}, "
            f"services={services} (placeholder)"
        )
        return False

    async def _fire_trigger(self, trigger: RollbackTrigger) -> RollbackOperation | None:
        """Fire a trigger and execute rollback.

        Args:
            trigger: Trigger to fire

        Returns:
            RollbackOperation if executed, None if confirmation required
        """
        trigger.mark_triggered()
        logger.warning(
            f"Trigger fired: {trigger.name} ({trigger.trigger_id}) - "
            f"target_state={trigger.target_state}"
        )

        if trigger.require_confirmation:
            logger.info(
                f"Trigger {trigger.trigger_id} requires confirmation before rollback"
            )
            return None

        # Execute rollback
        try:
            operation = await self._coordinator.execute_rollback(
                target_state=trigger.target_state,
                initiated_by=f"trigger:{trigger.trigger_id}",
                metadata={
                    "trigger_id": trigger.trigger_id,
                    "trigger_type": trigger.trigger_type.value,
                    "trigger_name": trigger.name,
                },
            )

            # Notify callbacks
            for callback in self._on_trigger_fired:
                try:
                    callback(trigger, operation)
                except Exception as e:
                    logger.exception(f"Trigger fired callback error: {e}")

            return operation
        except Exception as e:
            logger.exception(
                f"Error executing rollback for trigger {trigger.trigger_id}: {e}"
            )
            return None

    def on_trigger_fired(
        self, callback: Callable[[RollbackTrigger, RollbackOperation], None]
    ) -> None:
        """Register callback for trigger fired events.

        Args:
            callback: Function to call when trigger fires
        """
        self._on_trigger_fired.append(callback)


class RollbackImpactAnalyzer:
    """Analyzes impact of rollback operations."""

    # Risk scoring weights
    RISK_WEIGHTS = {
        "affected_users": 0.3,
        "affected_requests": 0.25,
        "downtime": 0.25,
        "dependencies": 0.2,
    }

    # Risk thresholds
    RISK_THRESHOLDS = {
        "low": {"users": 100, "requests": 1000, "downtime": 30},
        "medium": {"users": 1000, "requests": 10000, "downtime": 120},
    }

    def __init__(
        self,
        circuit_breaker_registry: CircuitBreakerRegistry | None = None,
    ) -> None:
        """Initialize impact analyzer.

        Args:
            circuit_breaker_registry: Registry for service health info
        """
        self._cb_registry = circuit_breaker_registry

    async def analyze_impact(
        self,
        target_state: str,
        services: list[str] | None = None,
        template_type: RollbackTemplateType | None = None,
    ) -> RollbackImpactAnalysis:
        """Analyze impact of a rollback operation.

        Args:
            target_state: Target state to rollback to
            services: List of services to rollback (None for all)
            template_type: Type of rollback template

        Returns:
            RollbackImpactAnalysis with impact assessment
        """
        analysis = RollbackImpactAnalysis()

        # Estimate affected services
        if services:
            analysis.affected_services = services
        else:
            # Estimate based on target state
            analysis.affected_services = await self._estimate_affected_services(
                target_state
            )

        # Calculate affected users and requests
        user_estimate = await self._estimate_affected_users(analysis.affected_services)
        analysis.estimated_affected_users = user_estimate

        request_estimate = await self._estimate_affected_requests(
            analysis.affected_services
        )
        analysis.estimated_affected_requests = request_estimate

        # Estimate downtime
        downtime = self._estimate_downtime(
            len(analysis.affected_services),
            template_type or RollbackTemplateType.FULL_DEPLOYMENT,
        )
        analysis.estimated_downtime_seconds = downtime

        # Identify dependencies
        dependencies = await self._identify_dependencies(analysis.affected_services)
        analysis.affected_dependencies = dependencies

        # Calculate risk score
        risk_score, risk_factors = self._calculate_risk_score(analysis)
        analysis.risk_score = risk_score
        analysis.risk_factors = risk_factors

        # Determine if confirmation is required
        analysis.confirmation_required = risk_score in (
            RollbackRiskLevel.MEDIUM,
            RollbackRiskLevel.HIGH,
        )

        return analysis

    async def _estimate_affected_services(self, target_state: str) -> list[str]:
        """Estimate services affected by rollback."""
        # This would query deployment/service registry
        # Placeholder: return common services
        return ["api", "worker", "scheduler"]

    async def _estimate_affected_users(self, services: list[str]) -> int:
        """Estimate number of users affected."""
        # This would query user metrics
        # Placeholder: estimate based on service count
        base_users = 100
        return base_users * len(services)

    async def _estimate_affected_requests(self, services: list[str]) -> int:
        """Estimate number of requests affected."""
        # This would query request metrics
        # Placeholder: estimate based on service count
        base_requests = 1000
        return base_requests * len(services)

    def _estimate_downtime(
        self,
        service_count: int,
        template_type: RollbackTemplateType,
    ) -> float:
        """Estimate downtime in seconds."""
        base_times = {
            RollbackTemplateType.FULL_DEPLOYMENT: 60.0,
            RollbackTemplateType.PARTIAL_SERVICE: 30.0,
            RollbackTemplateType.CONFIGURATION: 10.0,
            RollbackTemplateType.CUSTOM: 45.0,
        }
        base_time = base_times.get(template_type, 45.0)

        # Add time per service (parallel execution assumed)
        return base_time + (service_count * 2)

    async def _identify_dependencies(self, services: list[str]) -> list[str]:
        """Identify dependencies that may be affected."""
        # This would query dependency graph
        # Placeholder: return common dependencies
        dependencies = set()
        for service in services:
            if service == "api":
                dependencies.update(["database", "cache", "auth"])
            elif service == "worker":
                dependencies.update(["queue", "database"])
            elif service == "scheduler":
                dependencies.update(["database"])
        return list(dependencies)

    def _calculate_risk_score(
        self, analysis: RollbackImpactAnalysis
    ) -> tuple[RollbackRiskLevel, list[str]]:
        """Calculate risk score and identify risk factors.

        Returns:
            Tuple of (risk_level, risk_factors)
        """
        risk_factors = []
        risk_score = 0.0

        # Check user impact
        if analysis.estimated_affected_users > self.RISK_THRESHOLDS["medium"]["users"]:
            risk_factors.append(
                f"High user impact: {analysis.estimated_affected_users} users"
            )
            risk_score += self.RISK_WEIGHTS["affected_users"]
        elif analysis.estimated_affected_users > self.RISK_THRESHOLDS["low"]["users"]:
            risk_factors.append(
                f"Moderate user impact: {analysis.estimated_affected_users} users"
            )
            risk_score += self.RISK_WEIGHTS["affected_users"] * 0.5

        # Check request impact
        if (
            analysis.estimated_affected_requests
            > self.RISK_THRESHOLDS["medium"]["requests"]
        ):
            risk_factors.append(
                f"High request impact: {analysis.estimated_affected_requests} requests"
            )
            risk_score += self.RISK_WEIGHTS["affected_requests"]
        elif (
            analysis.estimated_affected_requests
            > self.RISK_THRESHOLDS["low"]["requests"]
        ):
            risk_factors.append(
                f"Moderate request impact: {analysis.estimated_affected_requests} requests"
            )
            risk_score += self.RISK_WEIGHTS["affected_requests"] * 0.5

        # Check downtime
        if (
            analysis.estimated_downtime_seconds
            > self.RISK_THRESHOLDS["medium"]["downtime"]
        ):
            risk_factors.append(
                f"Extended downtime: {analysis.estimated_downtime_seconds}s"
            )
            risk_score += self.RISK_WEIGHTS["downtime"]
        elif (
            analysis.estimated_downtime_seconds
            > self.RISK_THRESHOLDS["low"]["downtime"]
        ):
            risk_factors.append(
                f"Moderate downtime: {analysis.estimated_downtime_seconds}s"
            )
            risk_score += self.RISK_WEIGHTS["downtime"] * 0.5

        # Check dependencies
        if len(analysis.affected_dependencies) > 3:
            risk_factors.append(
                f"Many dependencies affected: {len(analysis.affected_dependencies)}"
            )
            risk_score += self.RISK_WEIGHTS["dependencies"]
        elif len(analysis.affected_dependencies) > 1:
            risk_factors.append(
                f"Some dependencies affected: {len(analysis.affected_dependencies)}"
            )
            risk_score += self.RISK_WEIGHTS["dependencies"] * 0.5

        # Determine risk level
        if risk_score >= 0.7:
            return RollbackRiskLevel.HIGH, risk_factors
        elif risk_score >= 0.4:
            return RollbackRiskLevel.MEDIUM, risk_factors
        else:
            return RollbackRiskLevel.LOW, risk_factors


class CoordinatedRollbackExecutor:
    """Executes coordinated multi-service rollbacks."""

    def __init__(
        self,
        rollback_coordinator: RollbackCoordinator,
        circuit_breaker_registry: CircuitBreakerRegistry | None = None,
        retry_budget_manager: RetryBudgetManager | None = None,
    ) -> None:
        """Initialize coordinated executor.

        Args:
            rollback_coordinator: Base coordinator for individual rollbacks
            circuit_breaker_registry: Registry for circuit breaker operations
            retry_budget_manager: Manager for retry budget operations
        """
        self._coordinator = rollback_coordinator
        self._cb_registry = circuit_breaker_registry
        self._budget_manager = retry_budget_manager

    async def execute_coordinated_rollback(
        self,
        config: CoordinatedRollbackConfig,
        target_state: str,
        initiated_by: str = "system",
    ) -> dict[str, RollbackOperation]:
        """Execute coordinated rollback across multiple services.

        Args:
            config: Coordinated rollback configuration
            target_state: Target state to rollback to
            initiated_by: Who initiated the rollback

        Returns:
            Dictionary mapping service names to their rollback operations
        """
        results: dict[str, RollbackOperation] = {}
        checkpoints: list[RollbackCheckpoint] = []

        # Open circuit breakers if configured
        if config.circuit_breaker_integration and self._cb_registry:
            await self._open_circuit_breakers(config.service_order)

        try:
            # Execute in parallel groups if specified
            if config.parallel_groups:
                for group in config.parallel_groups:
                    group_results = await self._execute_parallel(
                        group, target_state, initiated_by
                    )
                    results.update(group_results)

                    # Create checkpoint
                    if len(checkpoints) % config.checkpoint_interval == 0:
                        checkpoint = RollbackCheckpoint(
                            operation_id=list(results.values())[0].operation_id
                            if results
                            else "",
                            services_completed=list(results.keys()),
                            services_remaining=[
                                s for s in config.service_order if s not in results
                            ],
                        )
                        checkpoints.append(checkpoint)
            else:
                # Execute sequentially with dependency ordering
                ordered_services = self._order_by_dependencies(
                    config.service_order, config.dependencies
                )

                for i, service in enumerate(ordered_services):
                    operation = await self._execute_service_rollback(
                        service, target_state, initiated_by
                    )
                    results[service] = operation

                    # Create checkpoint
                    if (i + 1) % config.checkpoint_interval == 0:
                        checkpoint = RollbackCheckpoint(
                            operation_id=operation.operation_id,
                            services_completed=list(results.keys()),
                            services_remaining=ordered_services[i + 1 :],
                        )
                        checkpoints.append(checkpoint)

            # Preserve retry budgets if configured
            if config.retry_budget_preservation and self._budget_manager:
                await self._preserve_retry_budgets(config.service_order)

        finally:
            # Close circuit breakers
            if config.circuit_breaker_integration and self._cb_registry:
                await self._close_circuit_breakers(config.service_order)

        return results

    async def _execute_parallel(
        self,
        services: list[str],
        target_state: str,
        initiated_by: str,
    ) -> dict[str, RollbackOperation]:
        """Execute rollbacks for a group of services in parallel."""
        tasks = [
            self._execute_service_rollback(service, target_state, initiated_by)
            for service in services
        ]
        operations = await asyncio.gather(*tasks, return_exceptions=True)

        results = {}
        for service, operation in zip(services, operations):
            if isinstance(operation, Exception):
                logger.error(f"Rollback failed for {service}: {operation}")
                # Create failed operation placeholder
                operation = RollbackOperation(
                    target_state=target_state,
                    initiated_by=initiated_by,
                )
                operation.mark_failed(str(operation))
            results[service] = operation

        return results

    async def _execute_service_rollback(
        self,
        service: str,
        target_state: str,
        initiated_by: str,
    ) -> RollbackOperation:
        """Execute rollback for a single service."""
        # This would call the appropriate service-specific rollback
        # For now, use the base coordinator
        operation = await self._coordinator.execute_rollback(
            target_state=f"{target_state}:{service}",
            initiated_by=f"{initiated_by}:coordinated:{service}",
        )
        return operation

    def _order_by_dependencies(
        self,
        services: list[str],
        dependencies: dict[str, list[str]],
    ) -> list[str]:
        """Order services by dependencies (reverse dependency order for rollback)."""
        # Simple topological sort
        ordered = []
        visited = set()
        temp_mark = set()

        def visit(service: str) -> None:
            if service in temp_mark:
                # Circular dependency - just add it
                return
            if service in visited:
                return

            temp_mark.add(service)

            # Visit dependencies first (we want reverse order for rollback)
            for dep in dependencies.get(service, []):
                if dep in services:
                    visit(dep)

            temp_mark.remove(service)
            visited.add(service)
            ordered.append(service)

        for service in services:
            visit(service)

        return ordered

    async def _open_circuit_breakers(self, services: list[str]) -> None:
        """Open circuit breakers for services."""
        if not self._cb_registry:
            return

        for service in services:
            try:
                self._cb_registry.force_open(service, "coordinated_rollback")
                logger.info(f"Opened circuit breaker for {service}")
            except Exception as e:
                logger.warning(f"Failed to open circuit breaker for {service}: {e}")

    async def _close_circuit_breakers(self, services: list[str]) -> None:
        """Close circuit breakers for services."""
        if not self._cb_registry:
            return

        for service in services:
            try:
                self._cb_registry.force_close(service, "coordinated_rollback_complete")
                logger.info(f"Closed circuit breaker for {service}")
            except Exception as e:
                logger.warning(f"Failed to close circuit breaker for {service}: {e}")

    async def _preserve_retry_budgets(self, services: list[str]) -> None:
        """Preserve retry budgets during rollback."""
        if not self._budget_manager:
            return

        # Reset budgets to ensure fresh start after rollback
        for service in services:
            try:
                self._budget_manager.reset_budget(service)
                logger.info(f"Reset retry budget for {service}")
            except Exception as e:
                logger.warning(f"Failed to reset retry budget for {service}: {e}")


class PostRollbackValidator:
    """Automated post-rollback validation suite."""

    def __init__(
        self,
        circuit_breaker_registry: CircuitBreakerRegistry | None = None,
        retry_budget_manager: RetryBudgetManager | None = None,
    ) -> None:
        """Initialize validator.

        Args:
            circuit_breaker_registry: Registry for CB state verification
            retry_budget_manager: Manager for budget verification
        """
        self._cb_registry = circuit_breaker_registry
        self._budget_manager = retry_budget_manager

    async def run_validation(
        self,
        operation_id: str,
        services: list[str] | None = None,
    ) -> PostRollbackValidationResult:
        """Run complete post-rollback validation suite.

        Args:
            operation_id: Rollback operation ID
            services: Services to validate (None for all)

        Returns:
            PostRollbackValidationResult with validation results
        """
        result = PostRollbackValidationResult(operation_id=operation_id)
        report: dict[str, Any] = {
            "operation_id": operation_id,
            "started_at": datetime.now(UTC).isoformat(),
            "checks": {},
        }

        # Health check validation
        health_result = await self._validate_health_checks(services)
        result.health_checks_passed = health_result["passed"]
        report["checks"]["health_checks"] = health_result

        # Smoke test execution
        smoke_result = await self._run_smoke_tests(services)
        result.smoke_tests_passed = smoke_result["passed"]
        report["checks"]["smoke_tests"] = smoke_result

        # Circuit breaker state verification
        cb_result = await self._verify_circuit_breaker_states(services)
        result.circuit_breaker_states_verified = cb_result["verified"]
        report["checks"]["circuit_breakers"] = cb_result

        # Retry budget reset verification
        budget_result = await self._verify_retry_budgets(services)
        result.retry_budgets_reset = budget_result["verified"]
        report["checks"]["retry_budgets"] = budget_result

        report["completed_at"] = datetime.now(UTC).isoformat()
        result.mark_completed(report)

        return result

    async def _validate_health_checks(
        self, services: list[str] | None
    ) -> dict[str, Any]:
        """Validate health checks for services."""
        result = {"passed": True, "services": {}}

        if not services:
            services = ["api", "worker", "scheduler"]  # Default services

        for service in services:
            # Placeholder: would call actual health check endpoints
            service_healthy = True  # Assume healthy for now
            result["services"][service] = {"healthy": service_healthy}
            if not service_healthy:
                result["passed"] = False

        return result

    async def _run_smoke_tests(self, services: list[str] | None) -> dict[str, Any]:
        """Run smoke tests for services."""
        result = {"passed": True, "tests": {}}

        # Placeholder: would run actual smoke tests
        result["tests"]["connectivity"] = {"passed": True}
        result["tests"]["basic_functionality"] = {"passed": True}

        return result

    async def _verify_circuit_breaker_states(
        self, services: list[str] | None
    ) -> dict[str, Any]:
        """Verify circuit breaker states are correct."""
        result = {"verified": True, "states": {}}

        if not self._cb_registry:
            result["verified"] = True
            result["note"] = "Circuit breaker registry not available"
            return result

        if not services:
            # Check all registered circuit breakers
            all_states = self._cb_registry.get_all_states()
            services = list(all_states.keys())

        for service in services:
            state = self._cb_registry.get(service)
            if state:
                # Verify circuit breaker is in expected state (CLOSED or HALF_OPEN)
                is_valid = state.state.value in ("closed", "half_open")
                result["states"][service] = {
                    "state": state.state.value,
                    "valid": is_valid,
                }
                if not is_valid:
                    result["verified"] = False

        return result

    async def _verify_retry_budgets(self, services: list[str] | None) -> dict[str, Any]:
        """Verify retry budgets have been reset."""
        result = {"verified": True, "budgets": {}}

        if not self._budget_manager:
            result["verified"] = True
            result["note"] = "Retry budget manager not available"
            return result

        if not services:
            # Check all budgets
            all_budgets = self._budget_manager.get_all_budgets()
            for budget in all_budgets:
                service = budget.get("budget_key", "unknown")
                is_reset = budget.get("current_count", 0) == 0
                result["budgets"][service] = {
                    "count": budget.get("current_count", 0),
                    "reset": is_reset,
                }
                if not is_reset:
                    result["verified"] = False
        else:
            for service in services:
                status = self._budget_manager.get_budget_status(service)
                is_reset = status.get("current_count", 0) == 0
                result["budgets"][service] = {
                    "count": status.get("current_count", 0),
                    "reset": is_reset,
                }
                if not is_reset:
                    result["verified"] = False

        return result


class RollbackAutomationCoordinator:
    """Main coordinator for rollback automation features.

    Integrates all automation components:
    - Rollback templates
    - Automated triggers
    - Impact analysis
    - Coordinated rollback
    - Post-rollback validation

    Example:
        >>> coordinator = RollbackAutomationCoordinator(rollback_coordinator)
        >>> # Create default triggers
        >>> triggers = coordinator.create_default_triggers("v1.2.3", sensitivity="medium")
        >>> # Start monitoring
        >>> await coordinator.start_trigger_monitoring()
        >>> # Execute rollback with impact analysis
        >>> analysis = await coordinator.analyze_rollback_impact("v1.2.3")
        >>> if not analysis.confirmation_required:
        ...     operation = await coordinator.execute_rollback("v1.2.3")
    """

    def __init__(
        self,
        rollback_coordinator: RollbackCoordinator,
        circuit_breaker_registry: CircuitBreakerRegistry | None = None,
        retry_budget_manager: RetryBudgetManager | None = None,
    ) -> None:
        """Initialize automation coordinator.

        Args:
            rollback_coordinator: Base rollback coordinator
            circuit_breaker_registry: Circuit breaker registry
            retry_budget_manager: Retry budget manager
        """
        self._coordinator = rollback_coordinator
        self._cb_registry = circuit_breaker_registry
        self._budget_manager = retry_budget_manager

        # Initialize sub-components
        self._template_library = RollbackTemplateLibrary()
        self._trigger_manager = RollbackTriggerManager(
            rollback_coordinator, circuit_breaker_registry, retry_budget_manager
        )
        self._impact_analyzer = RollbackImpactAnalyzer(circuit_breaker_registry)
        self._coordinated_executor = CoordinatedRollbackExecutor(
            rollback_coordinator, circuit_breaker_registry, retry_budget_manager
        )
        self._post_rollback_validator = PostRollbackValidator(
            circuit_breaker_registry, retry_budget_manager
        )

        logger.info("RollbackAutomationCoordinator initialized")

    # ==================== Template Methods ====================

    def get_template(self, template_id: str) -> RollbackTemplate | None:
        """Get a rollback template."""
        return self._template_library.get_template(template_id)

    def get_template_by_type(
        self, template_type: RollbackTemplateType
    ) -> RollbackTemplate | None:
        """Get a rollback template by type."""
        return self._template_library.get_template_by_type(template_type)

    def list_templates(self) -> list[RollbackTemplate]:
        """List all available templates."""
        return self._template_library.list_templates()

    def add_custom_template(self, template: RollbackTemplate) -> None:
        """Add a custom template."""
        self._template_library.add_template(template)

    # ==================== Trigger Methods ====================

    def create_default_triggers(
        self,
        target_state: str,
        sensitivity: str = "medium",
    ) -> list[RollbackTrigger]:
        """Create default automated triggers."""
        # Use full deployment template by default
        template = self._template_library.get_template_by_type(
            RollbackTemplateType.FULL_DEPLOYMENT
        )
        template_id = template.template_id if template else ""

        return self._trigger_manager.create_default_triggers(
            target_state, template_id, sensitivity
        )

    def register_trigger(self, trigger: RollbackTrigger) -> None:
        """Register a trigger."""
        self._trigger_manager.register_trigger(trigger)

    def list_triggers(self, enabled_only: bool = False) -> list[RollbackTrigger]:
        """List triggers."""
        return self._trigger_manager.list_triggers(enabled_only)

    async def start_trigger_monitoring(self, interval_seconds: float = 10.0) -> None:
        """Start monitoring triggers."""
        await self._trigger_manager.start_monitoring(interval_seconds)

    async def stop_trigger_monitoring(self) -> None:
        """Stop monitoring triggers."""
        await self._trigger_manager.stop_monitoring()

    # ==================== Impact Analysis Methods ====================

    async def analyze_rollback_impact(
        self,
        target_state: str,
        services: list[str] | None = None,
        template_type: RollbackTemplateType | None = None,
    ) -> RollbackImpactAnalysis:
        """Analyze impact of rollback."""
        return await self._impact_analyzer.analyze_impact(
            target_state, services, template_type
        )

    # ==================== Coordinated Rollback Methods ====================

    async def execute_coordinated_rollback(
        self,
        config: CoordinatedRollbackConfig,
        target_state: str,
        initiated_by: str = "system",
    ) -> dict[str, RollbackOperation]:
        """Execute coordinated multi-service rollback."""
        return await self._coordinated_executor.execute_coordinated_rollback(
            config, target_state, initiated_by
        )

    # ==================== Post-Rollback Validation Methods ====================

    async def run_post_rollback_validation(
        self,
        operation_id: str,
        services: list[str] | None = None,
    ) -> PostRollbackValidationResult:
        """Run post-rollback validation."""
        return await self._post_rollback_validator.run_validation(
            operation_id, services
        )

    # ==================== High-Level API Methods ====================

    async def execute_rollback_with_automation(
        self,
        target_state: str,
        template_type: RollbackTemplateType = RollbackTemplateType.FULL_DEPLOYMENT,
        services: list[str] | None = None,
        skip_impact_analysis: bool = False,
        force: bool = False,
        initiated_by: str = "system",
    ) -> dict[str, Any]:
        """Execute rollback with full automation pipeline.

        Args:
            target_state: Target state to rollback to
            template_type: Type of rollback to execute
            services: Specific services to rollback (None for all)
            skip_impact_analysis: Skip impact analysis
            force: Bypass confirmation requirements
            initiated_by: Who initiated the rollback

        Returns:
            Dictionary with operation results and metadata
        """
        result = {
            "target_state": target_state,
            "initiated_by": initiated_by,
            "started_at": datetime.now(UTC).isoformat(),
        }

        # Step 1: Impact Analysis
        if not skip_impact_analysis:
            analysis = await self.analyze_rollback_impact(
                target_state, services, template_type
            )
            result["impact_analysis"] = analysis.to_dict()

            if analysis.confirmation_required and not force:
                result["status"] = "awaiting_confirmation"
                result["message"] = "Rollback requires confirmation due to risk level"
                return result

        # Step 2: Get template
        template = self._template_library.get_template_by_type(template_type)
        if template:
            result["template_id"] = template.template_id
            template.mark_used()

        # Step 3: Execute rollback
        if services and len(services) > 1:
            # Coordinated rollback for multiple services
            config = CoordinatedRollbackConfig(service_order=services)
            operations = await self.execute_coordinated_rollback(
                config, target_state, initiated_by
            )
            result["operations"] = {
                service: op.to_dict() for service, op in operations.items()
            }
            primary_op = list(operations.values())[0] if operations else None
        else:
            # Single rollback
            primary_op = await self._coordinator.execute_rollback(
                target_state=target_state,
                force=force,
                initiated_by=initiated_by,
            )
            result["operation"] = primary_op.to_dict()

        # Step 4: Post-rollback validation
        if primary_op and primary_op.status == RollbackStatus.COMPLETED:
            validation = await self.run_post_rollback_validation(
                primary_op.operation_id, services
            )
            result["post_rollback_validation"] = validation.to_dict()

        result["completed_at"] = datetime.now(UTC).isoformat()
        return result
