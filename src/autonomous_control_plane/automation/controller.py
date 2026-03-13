"""Automation Controller for closed-loop remediation orchestration.

Provides comprehensive self-healing automation with:
- Closed-loop remediation orchestration
- Integration with telemetry pipeline for metrics-driven healing
- Automated decision engine for healing action selection
- Escalation policies and thresholds
- Concurrent workflow management (50+ workflows)

For ST-CONTROL-002: Self-Healing Automation
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Callable

from autonomous_control_plane.components.self_healing_engine import SelfHealingEngine
from autonomous_control_plane.healing_actions.base import BaseHealingAction
from autonomous_control_plane.models.healing import (
    ActionPriority,
    FailurePatternType,
    HealingAttempt,
    HealingContext,
    HealingResult,
    HealingStatus,
    LogEntry,
    ResourceLimits,
)
from autonomous_control_plane.telemetry.metrics import TelemetryCollector

logger = logging.getLogger(__name__)


class RemediationStatus(StrEnum):
    """Status of a remediation workflow."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    ESCALATED = "escalated"
    TIMEOUT = "timeout"


class EscalationLevel(StrEnum):
    """Escalation levels for remediation."""

    AUTO = "auto"  # Fully automated
    NOTIFY = "notify"  # Notify operators
    APPROVE = "approve"  # Require approval
    MANUAL = "manual"  # Manual intervention required
    EMERGENCY = "emergency"  # Emergency escalation


@dataclass
class EscalationPolicy:
    """Policy for escalating remediation failures.

    Attributes:
        max_auto_attempts: Maximum automated attempts before escalation
        escalation_delay_seconds: Delay before escalating
        notify_channels: List of notification channels
        auto_escalate_to: Next escalation level
    """

    max_auto_attempts: int = 3
    escalation_delay_seconds: float = 300.0  # 5 minutes
    notify_channels: list[str] = field(default_factory=lambda: ["log", "metrics"])
    auto_escalate_to: EscalationLevel = EscalationLevel.NOTIFY

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "max_auto_attempts": self.max_auto_attempts,
            "escalation_delay_seconds": self.escalation_delay_seconds,
            "notify_channels": self.notify_channels,
            "auto_escalate_to": self.auto_escalate_to.value,
        }


@dataclass
class RemediationWorkflow:
    """A remediation workflow instance.

    Attributes:
        workflow_id: Unique workflow identifier
        service: Service being remediated
        pattern_type: Type of failure pattern
        status: Current workflow status
        created_at: When workflow was created
        started_at: When workflow started execution
        completed_at: When workflow completed
        steps: List of remediation steps
        current_step: Current step index
        escalation_level: Current escalation level
        escalation_policy: Policy for escalation
        attempts: List of healing attempts
        metrics: Workflow metrics
        context: Additional context
    """

    service: str
    pattern_type: FailurePatternType
    workflow_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: RemediationStatus = RemediationStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    steps: list[RemediationStep] = field(default_factory=list)
    current_step: int = 0
    escalation_level: EscalationLevel = EscalationLevel.AUTO
    escalation_policy: EscalationPolicy = field(default_factory=EscalationPolicy)
    attempts: list[HealingAttempt] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "workflow_id": self.workflow_id,
            "service": self.service,
            "pattern_type": self.pattern_type.value,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
            "steps": [s.to_dict() for s in self.steps],
            "current_step": self.current_step,
            "escalation_level": self.escalation_level.value,
            "escalation_policy": self.escalation_policy.to_dict(),
            "attempts": [a.to_dict() for a in self.attempts],
            "metrics": self.metrics,
            "context": self.context,
        }


@dataclass
class RemediationStep:
    """A single step in a remediation workflow.

    Attributes:
        step_id: Unique step identifier
        name: Human-readable step name
        action_type: Type of healing action
        status: Current step status
        started_at: When step started
        completed_at: When step completed
        result: Step execution result
        retry_count: Number of retries
        max_retries: Maximum retries allowed
        depends_on: List of step IDs this step depends on
        parallel: Whether this step can run in parallel
        timeout_seconds: Step timeout
    """

    name: str
    action_type: str
    step_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: RemediationStatus = RemediationStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: dict[str, Any] = field(default_factory=dict)
    retry_count: int = 0
    max_retries: int = 2
    depends_on: list[str] = field(default_factory=list)
    parallel: bool = False
    timeout_seconds: float = 60.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "step_id": self.step_id,
            "name": self.name,
            "action_type": self.action_type,
            "status": self.status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
            "result": self.result,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "depends_on": self.depends_on,
            "parallel": self.parallel,
            "timeout_seconds": self.timeout_seconds,
        }


@dataclass
class DecisionRule:
    """Rule for automated healing action selection.

    Attributes:
        name: Rule name
        pattern_types: Applicable failure patterns
        conditions: Conditions to match
        action_type: Action to select
        priority: Rule priority (higher = more specific)
        enabled: Whether rule is enabled
    """

    name: str
    pattern_types: list[FailurePatternType]
    conditions: dict[str, Any]
    action_type: str
    priority: int = 0
    enabled: bool = True

    def matches(
        self, pattern_type: FailurePatternType, context: dict[str, Any]
    ) -> bool:
        """Check if rule matches pattern and context."""
        if pattern_type not in self.pattern_types:
            return False

        for key, value in self.conditions.items():
            if key not in context or context[key] != value:
                return False

        return True


class AutomationController:
    """Controller for automated self-healing remediation.

    Features:
    - Closed-loop remediation orchestration
    - Metrics-driven healing decisions
    - Concurrent workflow management (50+ workflows)
    - Escalation policies and thresholds
    - Integration with telemetry pipeline
    - Decision engine for action selection

    Example:
        >>> controller = AutomationController(trading_mode="paper")
        >>> workflow = await controller.start_remediation(
        ...     service="redis",
        ...     pattern_type=FailurePatternType.REDIS_DISCONNECT
        ... )
        >>> status = controller.get_workflow_status(workflow.workflow_id)
    """

    # Maximum concurrent workflows
    MAX_CONCURRENT_WORKFLOWS = 50

    # Workflow timeout
    WORKFLOW_TIMEOUT_SECONDS = 300.0  # 5 minutes

    def __init__(
        self,
        trading_mode: str = "paper",
        redis_client: Any | None = None,
        enable_telemetry: bool = True,
    ):
        """Initialize automation controller.

        Args:
            trading_mode: Current trading mode (paper/live/production)
            redis_client: Redis client for state tracking
            enable_telemetry: Whether to enable telemetry export
        """
        self._trading_mode = trading_mode
        self._redis = redis_client
        self._enable_telemetry = enable_telemetry

        # Initialize self-healing engine
        self._healing_engine = SelfHealingEngine(
            trading_mode=trading_mode,
            redis_client=redis_client,
            enable_approval_gates=True,
        )

        # Workflow management
        self._workflows: dict[str, RemediationWorkflow] = {}
        self._workflow_semaphores: dict[str, asyncio.Semaphore] = {}
        self._active_workflows: set[str] = set()
        self._workflow_lock = asyncio.Lock()

        # Decision engine
        self._decision_rules: list[DecisionRule] = []
        self._action_registry: dict[str, type[BaseHealingAction]] = {}
        self._register_default_rules()
        self._register_default_actions()

        # Telemetry
        self._telemetry = TelemetryCollector() if enable_telemetry else None

        # Statistics
        self._stats = {
            "workflows_created": 0,
            "workflows_completed": 0,
            "workflows_failed": 0,
            "workflows_escalated": 0,
            "total_healing_attempts": 0,
            "successful_healings": 0,
        }

        # Running state
        self._running = False
        self._shutdown_event = asyncio.Event()

        logger.info(
            f"AutomationController initialized (trading_mode={trading_mode}, "
            f"max_concurrent={self.MAX_CONCURRENT_WORKFLOWS})"
        )

    def _register_default_rules(self) -> None:
        """Register default decision rules."""
        rules = [
            DecisionRule(
                name="redis_disconnect",
                pattern_types=[FailurePatternType.REDIS_DISCONNECT],
                conditions={},
                action_type="redis_restart",
                priority=10,
            ),
            DecisionRule(
                name="api_timeout",
                pattern_types=[FailurePatternType.API_TIMEOUT],
                conditions={},
                action_type="api_retry",
                priority=10,
            ),
            DecisionRule(
                name="circuit_breaker_open",
                pattern_types=[FailurePatternType.CIRCUIT_BREAKER_OPEN],
                conditions={},
                action_type="circuit_breaker_reset",
                priority=10,
            ),
            DecisionRule(
                name="database_connection",
                pattern_types=[FailurePatternType.DATABASE_CONNECTION],
                conditions={},
                action_type="connection_pool_reset",
                priority=10,
            ),
            DecisionRule(
                name="memory_exhaustion",
                pattern_types=[FailurePatternType.MEMORY_EXHAUSTION],
                conditions={},
                action_type="cache_flush",
                priority=10,
            ),
            DecisionRule(
                name="service_unhealthy",
                pattern_types=[FailurePatternType.SERVICE_UNHEALTHY],
                conditions={},
                action_type="service_restart",
                priority=10,
            ),
        ]

        for rule in rules:
            self.register_decision_rule(rule)

    def _register_default_actions(self) -> None:
        """Register default healing actions."""
        # Actions are registered by the healing engine
        # This is a placeholder for additional action registration
        pass

    def register_decision_rule(self, rule: DecisionRule) -> None:
        """Register a decision rule.

        Args:
            rule: Decision rule to register
        """
        self._decision_rules.append(rule)
        # Sort by priority (highest first)
        self._decision_rules.sort(key=lambda r: r.priority, reverse=True)
        logger.debug(f"Registered decision rule: {rule.name}")

    def select_action(
        self, pattern_type: FailurePatternType, context: dict[str, Any]
    ) -> str | None:
        """Select healing action based on pattern and context.

        Args:
            pattern_type: Type of failure pattern
            context: Additional context for decision

        Returns:
            Selected action type or None if no match
        """
        for rule in self._decision_rules:
            if rule.enabled and rule.matches(pattern_type, context):
                logger.info(
                    f"Selected action '{rule.action_type}' via rule '{rule.name}'"
                )
                return rule.action_type

        logger.warning(f"No decision rule matched for pattern {pattern_type.value}")
        return None

    async def start_remediation(
        self,
        service: str,
        pattern_type: FailurePatternType,
        log_entry: LogEntry | None = None,
        escalation_policy: EscalationPolicy | None = None,
        context: dict[str, Any] | None = None,
    ) -> RemediationWorkflow:
        """Start a new remediation workflow.

        Args:
            service: Service to remediate
            pattern_type: Type of failure pattern
            log_entry: Original log entry that triggered remediation
            escalation_policy: Escalation policy for this workflow
            context: Additional context

        Returns:
            Created remediation workflow

        Raises:
            RuntimeError: If max concurrent workflows exceeded
        """
        async with self._workflow_lock:
            if len(self._active_workflows) >= self.MAX_CONCURRENT_WORKFLOWS:
                raise RuntimeError(
                    f"Max concurrent workflows ({self.MAX_CONCURRENT_WORKFLOWS}) exceeded"
                )

            # Create workflow
            workflow = RemediationWorkflow(
                service=service,
                pattern_type=pattern_type,
                escalation_policy=escalation_policy or EscalationPolicy(),
                context=context or {},
            )

            # Select action and create steps
            action_type = self.select_action(pattern_type, context or {})
            if action_type:
                step = RemediationStep(
                    name=f"Execute {action_type}",
                    action_type=action_type,
                )
                workflow.steps.append(step)

            # Store workflow
            self._workflows[workflow.workflow_id] = workflow
            self._active_workflows.add(workflow.workflow_id)
            self._workflow_semaphores[workflow.workflow_id] = asyncio.Semaphore(1)
            self._stats["workflows_created"] += 1

            logger.info(
                f"Started remediation workflow {workflow.workflow_id} "
                f"for {service} ({pattern_type.value})"
            )

            # Record telemetry
            if self._telemetry:
                self._telemetry.record(
                    measurement="remediation_workflow",
                    tags={
                        "service": service,
                        "pattern_type": pattern_type.value,
                        "status": "started",
                    },
                    fields={"count": 1},
                )

        # Start execution
        asyncio.create_task(self._execute_workflow(workflow, log_entry))

        return workflow

    async def _execute_workflow(
        self, workflow: RemediationWorkflow, log_entry: LogEntry | None = None
    ) -> None:
        """Execute a remediation workflow.

        Args:
            workflow: Workflow to execute
            log_entry: Original log entry
        """
        workflow.started_at = datetime.now(UTC)
        workflow.status = RemediationStatus.RUNNING

        try:
            # Execute with timeout
            await asyncio.wait_for(
                self._execute_workflow_steps(workflow, log_entry),
                timeout=self.WORKFLOW_TIMEOUT_SECONDS,
            )

        except asyncio.TimeoutError:
            workflow.status = RemediationStatus.TIMEOUT
            logger.error(f"Workflow {workflow.workflow_id} timed out")

            # Escalate
            await self._escalate_workflow(workflow, "timeout")

        except Exception as e:
            workflow.status = RemediationStatus.FAILED
            logger.exception(f"Workflow {workflow.workflow_id} failed: {e}")

            # Escalate
            await self._escalate_workflow(workflow, f"exception: {e}")

        finally:
            workflow.completed_at = datetime.now(UTC)
            async with self._workflow_lock:
                self._active_workflows.discard(workflow.workflow_id)

            # Update stats
            if workflow.status == RemediationStatus.COMPLETED:
                self._stats["workflows_completed"] += 1
            elif workflow.status in (
                RemediationStatus.FAILED,
                RemediationStatus.TIMEOUT,
            ):
                self._stats["workflows_failed"] += 1

            # Record telemetry
            if self._telemetry:
                self._telemetry.record(
                    measurement="remediation_workflow",
                    tags={
                        "service": workflow.service,
                        "pattern_type": workflow.pattern_type.value,
                        "status": workflow.status.value,
                    },
                    fields={
                        "count": 1,
                        "duration_seconds": self._get_workflow_duration(workflow),
                    },
                )

    async def _execute_workflow_steps(
        self, workflow: RemediationWorkflow, log_entry: LogEntry | None = None
    ) -> None:
        """Execute workflow steps.

        Args:
            workflow: Workflow to execute
            log_entry: Original log entry
        """
        while workflow.current_step < len(workflow.steps):
            step = workflow.steps[workflow.current_step]

            # Check dependencies
            if step.depends_on:
                deps_completed = all(
                    any(
                        s.step_id == dep_id and s.status == RemediationStatus.COMPLETED
                        for s in workflow.steps
                    )
                    for dep_id in step.depends_on
                )
                if not deps_completed:
                    # Wait for dependencies
                    await asyncio.sleep(0.1)
                    continue

            # Execute step
            await self._execute_step(workflow, step, log_entry)

            # Check if step failed
            if step.status == RemediationStatus.FAILED:
                # Check if we should retry
                if step.retry_count < step.max_retries:
                    step.retry_count += 1
                    logger.info(
                        f"Retrying step {step.name} (attempt {step.retry_count}/{step.max_retries})"
                    )
                    await asyncio.sleep(2**step.retry_count)  # Exponential backoff
                    continue
                else:
                    # Step failed permanently
                    workflow.status = RemediationStatus.FAILED
                    return

            workflow.current_step += 1

        # All steps completed
        workflow.status = RemediationStatus.COMPLETED
        logger.info(f"Workflow {workflow.workflow_id} completed successfully")

    async def _execute_step(
        self,
        workflow: RemediationWorkflow,
        step: RemediationStep,
        log_entry: LogEntry | None = None,
    ) -> None:
        """Execute a single workflow step.

        Args:
            workflow: Parent workflow
            step: Step to execute
            log_entry: Original log entry
        """
        step.started_at = datetime.now(UTC)
        step.status = RemediationStatus.RUNNING

        try:
            # Create healing context
            context = HealingContext(
                service=workflow.service,
                action_id=step.step_id,
                triggered_by=workflow.pattern_type.value,
                log_entry=log_entry,
                timeout_seconds=step.timeout_seconds,
            )

            # Process through healing engine
            attempt = await self._healing_engine.process_log_entry(
                log_entry
                or LogEntry(
                    timestamp=datetime.now(UTC),
                    level="ERROR",
                    source=workflow.service,
                    message=f"Remediation step: {step.name}",
                )
            )

            if attempt:
                workflow.attempts.append(attempt)
                self._stats["total_healing_attempts"] += 1

                if attempt.status == HealingStatus.SUCCEEDED:
                    step.status = RemediationStatus.COMPLETED
                    step.result = attempt.result.to_dict() if attempt.result else {}
                    self._stats["successful_healings"] += 1
                elif attempt.status == HealingStatus.AWAITING_APPROVAL:
                    step.status = RemediationStatus.PENDING
                    # Wait for approval (simplified - in production would use event)
                    await asyncio.sleep(1)
                else:
                    step.status = RemediationStatus.FAILED
                    step.result = {"error": "Healing failed"}
            else:
                # No healing action taken
                step.status = RemediationStatus.COMPLETED
                step.result = {"message": "No healing action required"}

        except Exception as e:
            step.status = RemediationStatus.FAILED
            step.result = {"error": str(e)}
            logger.exception(f"Step {step.name} failed: {e}")

        finally:
            step.completed_at = datetime.now(UTC)

    async def _escalate_workflow(
        self, workflow: RemediationWorkflow, reason: str
    ) -> None:
        """Escalate a failed workflow.

        Args:
            workflow: Workflow to escalate
            reason: Escalation reason
        """
        workflow.escalation_level = EscalationLevel.NOTIFY
        self._stats["workflows_escalated"] += 1

        logger.warning(
            f"Workflow {workflow.workflow_id} escalated: {reason} "
            f"(level={workflow.escalation_level.value})"
        )

        # Record telemetry
        if self._telemetry:
            self._telemetry.record(
                measurement="remediation_escalation",
                tags={
                    "service": workflow.service,
                    "pattern_type": workflow.pattern_type.value,
                    "reason": reason,
                },
                fields={"count": 1},
            )

    def get_workflow_status(self, workflow_id: str) -> dict[str, Any] | None:
        """Get workflow status.

        Args:
            workflow_id: Workflow ID

        Returns:
            Workflow status dict or None if not found
        """
        workflow = self._workflows.get(workflow_id)
        if not workflow:
            return None

        return workflow.to_dict()

    def get_active_workflows(self) -> list[dict[str, Any]]:
        """Get list of active workflows.

        Returns:
            List of active workflow status dicts
        """
        return [
            self._workflows[wid].to_dict()
            for wid in self._active_workflows
            if wid in self._workflows
        ]

    def get_all_workflows(
        self, service: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Get all workflows.

        Args:
            service: Filter by service (optional)
            limit: Maximum results

        Returns:
            List of workflow status dicts
        """
        workflows = list(self._workflows.values())

        if service:
            workflows = [w for w in workflows if w.service == service]

        # Sort by created_at descending
        workflows.sort(key=lambda w: w.created_at, reverse=True)

        return [w.to_dict() for w in workflows[:limit]]

    def get_status(self) -> dict[str, Any]:
        """Get controller status.

        Returns:
            Status dictionary
        """
        return {
            "running": self._running,
            "trading_mode": self._trading_mode,
            "active_workflows": len(self._active_workflows),
            "total_workflows": len(self._workflows),
            "max_concurrent": self.MAX_CONCURRENT_WORKFLOWS,
            "decision_rules": len(self._decision_rules),
            "stats": self._stats.copy(),
            "healing_engine": self._healing_engine.get_status(),
        }

    def _get_workflow_duration(self, workflow: RemediationWorkflow) -> float:
        """Calculate workflow duration in seconds."""
        if workflow.started_at and workflow.completed_at:
            return (workflow.completed_at - workflow.started_at).total_seconds()
        return 0.0

    async def start(self) -> None:
        """Start the automation controller."""
        self._running = True
        self._shutdown_event.clear()
        logger.info("AutomationController started")

        if self._telemetry:
            self._telemetry.start()

    async def stop(self) -> None:
        """Stop the automation controller."""
        self._running = False
        self._shutdown_event.set()

        # Wait for active workflows to complete
        if self._active_workflows:
            logger.info(
                f"Waiting for {len(self._active_workflows)} active workflows to complete"
            )
            await asyncio.sleep(2)  # Give workflows time to finish

        if self._telemetry:
            self._telemetry.stop()

        logger.info("AutomationController stopped")

    def test_live_remediation(self) -> dict[str, Any]:
        """Test live remediation cycle.

        Returns:
            Test results
        """
        import asyncio

        async def run_test():
            # Start controller
            await self.start()

            try:
                # Create test workflow
                workflow = await self.start_remediation(
                    service="test_service",
                    pattern_type=FailurePatternType.REDIS_DISCONNECT,
                    context={"test": True},
                )

                # Wait for completion (with timeout)
                for _ in range(30):  # 30 seconds max
                    await asyncio.sleep(1)
                    status = self.get_workflow_status(workflow.workflow_id)
                    if status and status["status"] in (
                        "completed",
                        "failed",
                        "timeout",
                    ):
                        break

                return {
                    "workflow_id": workflow.workflow_id,
                    "final_status": self.get_workflow_status(workflow.workflow_id),
                    "controller_status": self.get_status(),
                }

            finally:
                await self.stop()

        # Run async test in sync context
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(run_test())
