"""Rollback handler for Chise v1 brain operations.

Provides safe rollback capabilities with pre-rollback state verification,
step-by-step execution, and post-mortem reporting.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, auto
from typing import Any

logger = logging.getLogger(__name__)


class RollbackTrigger(Enum):
    """Enumeration of rollback trigger conditions."""

    ECE_DEGRADATION = auto()
    WIN_RATE_DROP = auto()
    MAX_DRAWDOWN_BREACH = auto()
    SAFETY_VIOLATION = auto()
    HUMAN_REQUEST = auto()


@dataclass
class RollbackStep:
    """Represents a single step in the rollback process.

    Attributes:
        step_number: Sequential step identifier
        description: Human-readable step description
        verification_command: Command to verify step completion
        expected_result: Expected output from verification command
        completed: Whether this step has been executed
    """

    step_number: int
    description: str
    verification_command: str
    expected_result: str
    completed: bool = False


@dataclass
class RollbackResult:
    """Result of a rollback operation.

    Attributes:
        success: Whether rollback completed successfully
        target_version: Version rolled back to
        steps_completed: Number of steps successfully executed
        total_steps: Total number of steps in the rollback
        error_message: Error message if rollback failed
        timestamp: When the rollback was executed
        duration_seconds: Time taken to execute rollback
    """

    success: bool
    target_version: str
    steps_completed: int
    total_steps: int
    error_message: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    duration_seconds: float = 0.0


@dataclass
class PostmortemReport:
    """Post-mortem report for rollback analysis.

    Attributes:
        trigger: What triggered the rollback
        timeline: Sequence of events during rollback
        steps_executed: List of steps that were executed
        outcome: Final result of the rollback
        root_cause_analysis: Analysis of why rollback was needed
        timestamp: When the report was generated
        metadata: Additional context and metrics
    """

    trigger: RollbackTrigger
    timeline: list[dict[str, Any]]
    steps_executed: list[dict[str, Any]]
    outcome: RollbackResult
    root_cause_analysis: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        """Export report to JSON format."""
        data = {
            "trigger": self.trigger.name,
            "timeline": self.timeline,
            "steps_executed": self.steps_executed,
            "outcome": {
                "success": self.outcome.success,
                "target_version": self.outcome.target_version,
                "steps_completed": self.outcome.steps_completed,
                "total_steps": self.outcome.total_steps,
                "error_message": self.outcome.error_message,
                "timestamp": self.outcome.timestamp.isoformat(),
                "duration_seconds": self.outcome.duration_seconds,
            },
            "root_cause_analysis": self.root_cause_analysis,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }
        return json.dumps(data, indent=2)

    def to_markdown(self) -> str:
        """Export report to Markdown format."""
        lines = [
            "# Rollback Post-Mortem Report",
            "",
            f"**Generated:** {self.timestamp.isoformat()}",
            f"**Trigger:** {self.trigger.name}",
            "",
            "## Timeline",
            "",
        ]

        for event in self.timeline:
            ts = event.get("timestamp", "unknown")
            desc = event.get("description", "no description")
            lines.append(f"- `{ts}`: {desc}")

        lines.extend(
            [
                "",
                "## Steps Executed",
                "",
                "| Step | Description | Status |",
                "|------|-------------|--------|",
            ]
        )

        for step in self.steps_executed:
            num = step.get("step_number", "?")
            desc = step.get("description", "unknown")
            status = "✅" if step.get("completed", False) else "❌"
            lines.append(f"| {num} | {desc} | {status} |")

        lines.extend(
            [
                "",
                "## Outcome",
                "",
                f"- **Success:** {self.outcome.success}",
                f"- **Target Version:** {self.outcome.target_version}",
                f"- **Steps Completed:** {self.outcome.steps_completed}/{self.outcome.total_steps}",
                f"- **Duration:** {self.outcome.duration_seconds:.2f} seconds",
            ]
        )

        if self.outcome.error_message:
            lines.extend(
                [
                    "",
                    f"- **Error:** {self.outcome.error_message}",
                ]
            )

        lines.extend(
            [
                "",
                "## Root Cause Analysis",
                "",
                self.root_cause_analysis,
                "",
                "## Metadata",
                "",
            ]
        )

        for key, value in self.metadata.items():
            lines.append(f"- **{key}:** {value}")

        return "\n".join(lines)


class RollbackHandler:
    """Handles brain version rollback operations with safety checks.

    Provides methods for checking rollback triggers, validating pre-rollback
    state, executing step-by-step rollbacks, and generating post-mortem reports.

    Attributes:
        ece_threshold: Threshold for ECE degradation trigger (default: 0.15)
        win_rate_threshold: Threshold for win rate drop trigger
        max_drawdown_threshold: Threshold for max drawdown trigger
        active_trades_check: Whether to check for active trades
        version_registry: Registry of available versions for rollback
    """

    def __init__(
        self,
        ece_threshold: float = 0.15,
        win_rate_threshold: float | None = None,
        max_drawdown_threshold: float | None = None,
        active_trades_check: bool = True,
        version_registry: list[str] | None = None,
    ):
        self.ece_threshold = ece_threshold
        self.win_rate_threshold = win_rate_threshold
        self.max_drawdown_threshold = max_drawdown_threshold
        self.active_trades_check = active_trades_check
        self.version_registry = version_registry or []
        self._current_metrics: dict[str, float] = {}
        self._rollback_history: list[RollbackResult] = []
        self._paused_step: int | None = None

    def update_metrics(self, metrics: dict[str, float]) -> None:
        """Update current system metrics for trigger evaluation.

        Args:
            metrics: Dictionary of metric names to values
        """
        self._current_metrics.update(metrics)

    def check_triggers(self) -> list[RollbackTrigger]:
        """Evaluate all rollback trigger conditions.

        Returns:
            List of triggers that are currently active
        """
        triggers = []

        # Check ECE degradation
        ece = self._current_metrics.get("ece", 0.0)
        if ece > self.ece_threshold:
            triggers.append(RollbackTrigger.ECE_DEGRADATION)
            logger.warning(
                f"ECE degradation detected: {ece:.4f} > {self.ece_threshold}"
            )

        # Check win rate drop
        if self.win_rate_threshold is not None:
            win_rate = self._current_metrics.get("win_rate", 1.0)
            baseline = self._current_metrics.get("baseline_win_rate", win_rate)
            if baseline - win_rate > self.win_rate_threshold:
                triggers.append(RollbackTrigger.WIN_RATE_DROP)
                logger.warning(
                    f"Win rate drop detected: {win_rate:.4f} "
                    f"(baseline: {baseline:.4f}, threshold: {self.win_rate_threshold})"
                )

        # Check max drawdown breach
        if self.max_drawdown_threshold is not None:
            drawdown = self._current_metrics.get("max_drawdown", 0.0)
            if drawdown > self.max_drawdown_threshold:
                triggers.append(RollbackTrigger.MAX_DRAWDOWN_BREACH)
                logger.warning(
                    f"Max drawdown breach: {drawdown:.4f} > {self.max_drawdown_threshold}"
                )

        # Check safety violations (from metrics)
        safety_violations = self._current_metrics.get("safety_violations", 0)
        if safety_violations > 0:
            triggers.append(RollbackTrigger.SAFETY_VIOLATION)
            logger.warning(f"Safety violations detected: {safety_violations}")

        return triggers

    def validate_pre_rollback_state(self, target_version: str) -> bool:
        """Verify system state before allowing rollback.

        Performs the following checks:
        1. No active trades (if active_trades_check enabled)
        2. Data consistency
        3. Target version exists in registry

        Args:
            target_version: The version to roll back to

        Returns:
            True if pre-rollback state is valid
        """
        logger.info(f"Validating pre-rollback state for target: {target_version}")

        # Check no active trades
        if self.active_trades_check:
            active_trades = self._current_metrics.get("active_trades", 0)
            if active_trades > 0:
                logger.error(f"Cannot rollback with {active_trades} active trades")
                return False

        # Verify data consistency
        data_consistent = self._current_metrics.get("data_consistent", True)
        if not data_consistent:
            logger.error("Data consistency check failed")
            return False

        # Confirm target version exists
        if target_version not in self.version_registry:
            logger.error(f"Target version '{target_version}' not in registry")
            return False

        logger.info("Pre-rollback state validation passed")
        return True

    def execute_rollback(
        self,
        target_version: str,
        steps: list[RollbackStep],
        resume_from: int | None = None,
    ) -> RollbackResult:
        """Execute a step-by-step rollback.

        Args:
            target_version: Version to roll back to
            steps: List of rollback steps to execute
            resume_from: Step number to resume from (for pause/resume)

        Returns:
            RollbackResult with execution details
        """
        start_time = datetime.now(UTC)
        timeline = [
            {"timestamp": start_time.isoformat(), "description": "Rollback initiated"}
        ]

        # Validate pre-rollback state
        if not self.validate_pre_rollback_state(target_version):
            return RollbackResult(
                success=False,
                target_version=target_version,
                steps_completed=0,
                total_steps=len(steps),
                error_message="Pre-rollback state validation failed",
            )

        timeline.append(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "description": "Pre-rollback validation passed",
            }
        )

        # Determine starting step
        start_step = resume_from if resume_from is not None else 0
        completed_steps = 0

        try:
            for i, step in enumerate(steps):
                if step.step_number < start_step:
                    # Skip already completed steps
                    completed_steps += 1
                    continue

                logger.info(f"Executing step {step.step_number}: {step.description}")

                # Execute the step (simulated - in production would call actual commands)
                step.completed = self._execute_step(step)

                if step.completed:
                    completed_steps += 1
                    timeline.append(
                        {
                            "timestamp": datetime.now(UTC).isoformat(),
                            "description": f"Step {step.step_number} completed: {step.description}",
                        }
                    )
                else:
                    error_msg = f"Step {step.step_number} failed: {step.description}"
                    logger.error(error_msg)
                    self._paused_step = step.step_number

                    duration = (datetime.now(UTC) - start_time).total_seconds()
                    result = RollbackResult(
                        success=False,
                        target_version=target_version,
                        steps_completed=completed_steps,
                        total_steps=len(steps),
                        error_message=error_msg,
                        duration_seconds=duration,
                    )
                    self._rollback_history.append(result)
                    return result

            # All steps completed
            duration = (datetime.now(UTC) - start_time).total_seconds()
            result = RollbackResult(
                success=True,
                target_version=target_version,
                steps_completed=completed_steps,
                total_steps=len(steps),
                duration_seconds=duration,
            )
            self._rollback_history.append(result)
            self._paused_step = None

            timeline.append(
                {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "description": "Rollback completed successfully",
                }
            )

            logger.info(f"Rollback to {target_version} completed in {duration:.2f}s")
            return result

        except Exception as e:
            duration = (datetime.now(UTC) - start_time).total_seconds()
            error_msg = f"Unexpected error during rollback: {str(e)}"
            logger.exception(error_msg)

            result = RollbackResult(
                success=False,
                target_version=target_version,
                steps_completed=completed_steps,
                total_steps=len(steps),
                error_message=error_msg,
                duration_seconds=duration,
            )
            self._rollback_history.append(result)
            return result

    def _execute_step(self, step: RollbackStep) -> bool:
        """Execute a single rollback step.

        In production, this would execute the actual command and verify result.
        For testing, it simulates success.

        Args:
            step: The rollback step to execute

        Returns:
            True if step executed successfully
        """
        # Simulate step execution
        # In production: execute step.verification_command and check output
        logger.debug(f"Executing: {step.verification_command}")
        return True

    def emergency_rollback(
        self,
        target_version: str,
        force: bool = False,
        steps: list[RollbackStep] | None = None,
    ) -> RollbackResult:
        """Execute emergency rollback with optional force flag.

        Emergency rollback bypasses some safety checks when force=True,
        but still logs all actions for audit purposes.

        Args:
            target_version: Version to roll back to
            force: If True, bypass some safety checks
            steps: Optional custom steps (uses default if not provided)

        Returns:
            RollbackResult with execution details
        """
        if not force:
            # Normal rollback path
            if steps is None:
                steps = self._get_default_rollback_steps()
            return self.execute_rollback(target_version, steps)

        # Force path - bypass some checks but still log
        logger.warning(f"EMERGENCY ROLLBACK (force=True) to {target_version}")

        start_time = datetime.now(UTC)

        # Still verify target version exists (never bypass this)
        if target_version not in self.version_registry:
            return RollbackResult(
                success=False,
                target_version=target_version,
                steps_completed=0,
                total_steps=0,
                error_message="Target version not in registry (cannot bypass)",
            )

        # Log that we're bypassing checks
        if self.active_trades_check:
            active_trades = self._current_metrics.get("active_trades", 0)
            if active_trades > 0:
                logger.warning(f"Force rollback with {active_trades} active trades")

        if steps is None:
            steps = self._get_default_rollback_steps()

        # Execute with minimal validation
        completed_steps = 0
        try:
            for step in steps:
                logger.info(
                    f"[FORCE] Executing step {step.step_number}: {step.description}"
                )
                step.completed = self._execute_step(step)
                if step.completed:
                    completed_steps += 1
                else:
                    break

            duration = (datetime.now(UTC) - start_time).total_seconds()
            success = completed_steps == len(steps)

            result = RollbackResult(
                success=success,
                target_version=target_version,
                steps_completed=completed_steps,
                total_steps=len(steps),
                duration_seconds=duration,
            )
            self._rollback_history.append(result)

            logger.warning(f"Emergency rollback completed: success={success}")
            return result

        except Exception as e:
            duration = (datetime.now(UTC) - start_time).total_seconds()
            result = RollbackResult(
                success=False,
                target_version=target_version,
                steps_completed=completed_steps,
                total_steps=len(steps),
                error_message=f"Emergency rollback failed: {str(e)}",
                duration_seconds=duration,
            )
            self._rollback_history.append(result)
            return result

    def _get_default_rollback_steps(self) -> list[RollbackStep]:
        """Get default rollback steps for emergency rollback.

        Returns:
            List of default rollback steps
        """
        return [
            RollbackStep(
                step_number=1,
                description="Stop active trading",
                verification_command="systemctl stop chise-trader",
                expected_result="trader stopped",
            ),
            RollbackStep(
                step_number=2,
                description="Backup current state",
                verification_command="chise-backup create --tag pre-rollback",
                expected_result="backup created",
            ),
            RollbackStep(
                step_number=3,
                description="Switch to target version",
                verification_command="chise-version switch",
                expected_result="version switched",
            ),
            RollbackStep(
                step_number=4,
                description="Verify version",
                verification_command="chise-version current",
                expected_result="version verified",
            ),
            RollbackStep(
                step_number=5,
                description="Restart services",
                verification_command="systemctl start chise-trader",
                expected_result="trader started",
            ),
        ]

    def generate_postmortem(
        self,
        trigger: RollbackTrigger,
        result: RollbackResult,
        root_cause_analysis: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> PostmortemReport:
        """Generate a post-mortem report for rollback analysis.

        Args:
            trigger: What triggered the rollback
            result: The rollback result
            root_cause_analysis: Analysis of why rollback was needed
            metadata: Additional context and metrics

        Returns:
            PostmortemReport with full analysis
        """
        # Build timeline from rollback history
        timeline = [
            {
                "timestamp": result.timestamp.isoformat(),
                "description": "Rollback executed",
            },
        ]

        # Build steps executed list
        steps_executed = []
        if result.steps_completed > 0:
            for i in range(1, result.steps_completed + 1):
                steps_executed.append(
                    {
                        "step_number": i,
                        "description": f"Step {i}",
                        "completed": True,
                    }
                )

        # Add failure step if applicable
        if not result.success and result.steps_completed < result.total_steps:
            steps_executed.append(
                {
                    "step_number": result.steps_completed + 1,
                    "description": f"Step {result.steps_completed + 1} (FAILED)",
                    "completed": False,
                }
            )

        report = PostmortemReport(
            trigger=trigger,
            timeline=timeline,
            steps_executed=steps_executed,
            outcome=result,
            root_cause_analysis=root_cause_analysis or "Analysis pending",
            metadata=metadata or {},
        )

        logger.info(f"Post-mortem report generated for {trigger.name}")
        return report

    def get_rollback_history(self) -> list[RollbackResult]:
        """Get history of rollback operations.

        Returns:
            List of rollback results
        """
        return self._rollback_history.copy()

    def get_paused_step(self) -> int | None:
        """Get the step number where rollback was paused.

        Returns:
            Step number if paused, None otherwise
        """
        return self._paused_step

    def clear_paused_state(self) -> None:
        """Clear the paused state to allow new rollbacks."""
        self._paused_step = None
        logger.info("Paused state cleared")
