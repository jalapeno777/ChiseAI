"""
Brain Rollback Handler - Safety + Rollback Steps

Handles rollback triggers, safety checks, and rollback execution
with full logging for post-mortem analysis.

ST-CHISE-005: Chise v1 Rollback Plan - Safety + Rollback Steps
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("rollback_handler")


class RollbackTrigger(Enum):
    """Valid rollback trigger conditions."""

    ECE_DEGRADATION = "ece_degradation"
    SAFETY_VIOLATION = "safety_violation"
    HUMAN_REQUEST = "human_request"
    WIN_RATE_DROP = "win_rate_drop"
    MAX_DRAWDOWN = "max_drawdown"
    SYSTEM_ERROR = "system_error"


class RollbackStatus(Enum):
    """Status of rollback execution."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"
    VERIFIED = "verified"


class SafetyCheckResult(Enum):
    """Result of a safety check."""

    PASS = "pass"
    FAIL = "fail"
    WARNING = "warning"
    SKIP = "skip"


@dataclass
class SystemState:
    """System state snapshot before rollback."""

    timestamp: datetime
    brain_version: str
    active_signals: bool
    active_trades_count: int
    data_consistency_ok: bool
    last_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "brain_version": self.brain_version,
            "active_signals": self.active_signals,
            "active_trades_count": self.active_trades_count,
            "data_consistency_ok": self.data_consistency_ok,
            "last_error": self.last_error,
        }


@dataclass
class RollbackStepResult:
    """Result of executing a single rollback step."""

    step_number: int
    description: str
    status: RollbackStatus
    started_at: datetime
    completed_at: datetime | None = None
    duration_seconds: float = 0.0
    output: str = ""
    error_message: str | None = None
    verification_passed: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "step_number": self.step_number,
            "description": self.description,
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
            "duration_seconds": self.duration_seconds,
            "output": self.output,
            "error_message": self.error_message,
            "verification_passed": self.verification_passed,
        }


@dataclass
class RollbackOutcome:
    """Complete rollback outcome for post-mortem analysis."""

    # Identification
    rollback_id: str
    trigger: RollbackTrigger
    reason: str

    # Versions
    from_version: str
    to_version: str

    # Timing
    initiated_at: datetime
    initiated_by: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    total_duration_seconds: float = 0.0

    # State
    initial_state: SystemState | None = None
    final_state: SystemState | None = None

    # Execution
    steps_results: list[RollbackStepResult] = field(default_factory=list)
    status: RollbackStatus = RollbackStatus.NOT_STARTED

    # Context
    force_override: bool = False
    safety_checks_overridden: list[str] = field(default_factory=list)

    # Post-mortem
    lessons_learned: str = ""
    follow_up_actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "rollback_id": self.rollback_id,
            "trigger": self.trigger.value,
            "reason": self.reason,
            "from_version": self.from_version,
            "to_version": self.to_version,
            "initiated_at": self.initiated_at.isoformat(),
            "initiated_by": self.initiated_by,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
            "total_duration_seconds": self.total_duration_seconds,
            "initial_state": self.initial_state.to_dict()
            if self.initial_state
            else None,
            "final_state": self.final_state.to_dict() if self.final_state else None,
            "steps_results": [sr.to_dict() for sr in self.steps_results],
            "status": self.status.value,
            "force_override": self.force_override,
            "safety_checks_overridden": self.safety_checks_overridden,
            "lessons_learned": self.lessons_learned,
            "follow_up_actions": self.follow_up_actions,
        }

    def to_markdown(self) -> str:
        """Generate post-mortem markdown report."""
        lines = [
            f"# Rollback Post-Mortem: {self.rollback_id}",
            "",
            "## Summary",
            "",
            f"- **Rollback ID:** `{self.rollback_id}`",
            f"- **Trigger:** {self.trigger.value}",
            f"- **Reason:** {self.reason}",
            f"- **Status:** {self.status.value.upper()}",
            f"- **Force Override:** {'Yes' if self.force_override else 'No'}",
            "",
            "## Version Information",
            "",
            f"- **From Version:** `{self.from_version}`",
            f"- **To Version:** `{self.to_version}`",
            "",
            "## Timeline",
            "",
            f"- **Initiated:** {self.initiated_at.strftime('%Y-%m-%d %H:%M:%S UTC')}",
            f"- **Initiated By:** {self.initiated_by}",
        ]

        if self.started_at:
            lines.append(
                f"- **Started:** {self.started_at.strftime('%Y-%m-%d %H:%M:%S UTC')}"
            )
        if self.completed_at:
            lines.append(
                f"- **Completed:** {self.completed_at.strftime('%Y-%m-%d %H:%M:%S UTC')}"
            )

        lines.extend(
            [
                f"- **Total Duration:** {self.total_duration_seconds:.1f} seconds",
                "",
            ]
        )

        # Initial state
        if self.initial_state:
            lines.extend(
                [
                    "## Initial System State",
                    "",
                    f"- **Brain Version:** `{self.initial_state.brain_version}`",
                    f"- **Active Signals:** {'Yes' if self.initial_state.active_signals else 'No'}",
                    f"- **Active Trades:** {self.initial_state.active_trades_count}",
                    f"- **Data Consistency:** {'OK' if self.initial_state.data_consistency_ok else 'FAILED'}",
                ]
            )
            if self.initial_state.last_error:
                lines.append(f"- **Last Error:** {self.initial_state.last_error}")
            lines.append("")

        # Steps results
        lines.extend(
            [
                "## Rollback Steps",
                "",
                "| Step | Description | Status | Duration | Verification |",
                "|------|-------------|--------|----------|--------------|",
            ]
        )

        for sr in self.steps_results:
            status_emoji = {
                RollbackStatus.COMPLETED: "✅",
                RollbackStatus.FAILED: "❌",
                RollbackStatus.IN_PROGRESS: "⏳",
                RollbackStatus.PARTIAL: "⚠️",
            }.get(sr.status, "❓")
            lines.append(
                f"| {sr.step_number} | {sr.description} | {status_emoji} {sr.status.value} | "
                f"{sr.duration_seconds:.1f}s | {'✅' if sr.verification_passed else '❌'} |"
            )

        lines.append("")

        # Safety overrides
        if self.safety_checks_overridden:
            lines.extend(
                [
                    "## Safety Checks Overridden",
                    "",
                    "⚠️ **The following safety checks were overridden due to --force flag:**",
                    "",
                ]
            )
            for check in self.safety_checks_overridden:
                lines.append(f"- {check}")
            lines.append("")

        # Lessons learned
        if self.lessons_learned:
            lines.extend(
                [
                    "## Lessons Learned",
                    "",
                    self.lessons_learned,
                    "",
                ]
            )

        # Follow-up actions
        if self.follow_up_actions:
            lines.extend(
                [
                    "## Follow-up Actions",
                    "",
                ]
            )
            for action in self.follow_up_actions:
                lines.append(f"- [ ] {action}")
            lines.append("")

        lines.extend(
            [
                "---",
                "",
                "*This report was automatically generated by the Rollback Handler*",
            ]
        )

        return "\n".join(lines)


class RollbackHandler:
    """
    Handles brain version rollbacks with safety checks and logging.

    Features:
    - Trigger detection and validation
    - Pre-rollback safety verification
    - Step-by-step rollback execution
    - Post-rollback verification
    - Comprehensive logging
    """

    # Rollback triggers with thresholds
    TRIGGER_THRESHOLDS: dict[RollbackTrigger, dict[str, Any]] = {
        RollbackTrigger.ECE_DEGRADATION: {
            "threshold": 0.15,
            "description": "ECE degradation > 0.15",
        },
        RollbackTrigger.WIN_RATE_DROP: {
            "threshold": 0.50,
            "description": "Win rate drops below 50%",
        },
        RollbackTrigger.MAX_DRAWDOWN: {
            "threshold": 0.20,
            "description": "Max drawdown exceeds 20%",
        },
    }

    def __init__(
        self,
        logs_dir: Path | None = None,
        current_version: str = "unknown",
        previous_version: str = "unknown",
    ):
        """
        Initialize rollback handler.

        Args:
            logs_dir: Directory for rollback logs
            current_version: Current brain version
            previous_version: Previous stable version to rollback to
        """
        self.logs_dir = logs_dir or Path("_bmad-output/rollback-logs")
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.current_version = current_version
        self.previous_version = previous_version
        self._outcome: RollbackOutcome | None = None

    async def verify_system_state(self) -> SystemState:
        """
        Verify system state before rollback.

        Checks:
        - No active trades
        - Data consistency
        - Signal generation status

        Returns:
            SystemState snapshot
        """
        logger.info("Verifying system state before rollback...")

        state = SystemState(
            timestamp=datetime.utcnow(),
            brain_version=self.current_version,
            active_signals=False,  # Will be checked
            active_trades_count=0,  # Will be checked
            data_consistency_ok=True,  # Will be checked
        )

        try:
            # Check active signals
            state.active_signals = await self._check_active_signals()

            # Check active trades
            state.active_trades_count = await self._check_active_trades()

            # Check data consistency
            state.data_consistency_ok = await self._check_data_consistency()

            logger.info(f"System state verified: {state.to_dict()}")

        except Exception as e:
            logger.error(f"Error verifying system state: {e}")
            state.last_error = str(e)

        return state

    async def _check_active_signals(self) -> bool:
        """Check if signal generation is active."""
        # Placeholder - implement actual check
        # This would query the signal generation service
        return False

    async def _check_active_trades(self) -> int:
        """Check number of active trades."""
        # Placeholder - implement actual check
        # This would query the execution service
        return 0

    async def _check_data_consistency(self) -> bool:
        """Check data consistency."""
        # Placeholder - implement actual check
        # This would run consistency checks on databases
        return True

    def validate_trigger(
        self,
        trigger: RollbackTrigger,
        value: float | None = None,
    ) -> tuple[bool, str]:
        """
        Validate if a trigger condition is met.

        Args:
            trigger: The trigger type
            value: Optional measured value to check against threshold

        Returns:
            Tuple of (is_valid, reason)
        """
        if trigger in self.TRIGGER_THRESHOLDS and value is not None:
            threshold = self.TRIGGER_THRESHOLDS[trigger]["threshold"]
            description = self.TRIGGER_THRESHOLDS[trigger]["description"]

            if trigger == RollbackTrigger.ECE_DEGRADATION:
                if value > threshold:
                    return True, f"{description}: measured {value:.3f}"
            elif trigger == RollbackTrigger.MAX_DRAWDOWN:
                if value > threshold:
                    return True, f"{description}: measured {value:.3f}"
            elif trigger == RollbackTrigger.WIN_RATE_DROP:
                # Win rate drop triggers when value is BELOW threshold
                if value < threshold:
                    return True, f"{description}: measured {value:.3f}"

        # Human request and safety violations are always valid triggers
        if trigger in (RollbackTrigger.HUMAN_REQUEST, RollbackTrigger.SAFETY_VIOLATION):
            return True, f"Valid trigger: {trigger.value}"

        return False, f"Trigger condition not met for {trigger.value}"

    async def trigger_rollback(
        self,
        trigger: RollbackTrigger,
        reason: str,
        initiated_by: str = "system",
        force: bool = False,
    ) -> RollbackOutcome:
        """
        Trigger and execute a rollback.

        Args:
            trigger: Rollback trigger type
            reason: Detailed reason for rollback
            initiated_by: Who/what initiated the rollback
            force: Force rollback even if safety checks fail

        Returns:
            RollbackOutcome with full execution details
        """
        rollback_id = f"RB-{int(time.time())}-{trigger.value}"

        logger.info(f"Initiating rollback {rollback_id}: {trigger.value} - {reason}")

        # Create outcome record
        outcome = RollbackOutcome(
            rollback_id=rollback_id,
            trigger=trigger,
            reason=reason,
            from_version=self.current_version,
            to_version=self.previous_version,
            initiated_at=datetime.utcnow(),
            initiated_by=initiated_by,
            force_override=force,
        )
        self._outcome = outcome

        # Verify initial system state
        outcome.initial_state = await self.verify_system_state()

        # Check if rollback is safe
        safety_issues = []

        if outcome.initial_state.active_trades_count > 0:
            issue = (
                f"Active trades detected: {outcome.initial_state.active_trades_count}"
            )
            safety_issues.append(issue)
            logger.warning(issue)

        if not outcome.initial_state.data_consistency_ok:
            issue = "Data consistency check failed"
            safety_issues.append(issue)
            logger.warning(issue)

        if safety_issues and not force:
            outcome.status = RollbackStatus.FAILED
            outcome.lessons_learned = f"Safety checks failed: {'; '.join(safety_issues)}. Use --force to override."
            await self._log_outcome(outcome)
            raise RollbackSafetyError(outcome.lessons_learned)

        if safety_issues and force:
            outcome.safety_checks_overridden = safety_issues
            logger.warning(f"Safety checks overridden: {safety_issues}")

        # Execute rollback steps
        outcome.status = RollbackStatus.IN_PROGRESS
        outcome.started_at = datetime.utcnow()

        try:
            await self._execute_rollback_steps(outcome)
            outcome.status = RollbackStatus.COMPLETED
        except Exception as e:
            logger.error(f"Rollback failed: {e}")
            outcome.status = RollbackStatus.FAILED
            outcome.lessons_learned = f"Rollback execution failed: {e}"

        outcome.completed_at = datetime.utcnow()
        if outcome.started_at:
            outcome.total_duration_seconds = (
                outcome.completed_at - outcome.started_at
            ).total_seconds()

        # Verify final state
        outcome.final_state = await self.verify_system_state()

        # Log outcome
        await self._log_outcome(outcome)

        return outcome

    async def _execute_rollback_steps(self, outcome: RollbackOutcome) -> None:
        """Execute the rollback steps."""
        steps = [
            ("Stop signal generation", self._stop_signals),
            ("Verify no active trades", self._verify_no_trades),
            ("Switch brain version", self._switch_version),
            ("Verify data consistency", self._verify_data_consistency),
            ("Resume signal generation", self._start_signals),
        ]

        for step_num, (description, step_func) in enumerate(steps, 1):
            step_result = RollbackStepResult(
                step_number=step_num,
                description=description,
                status=RollbackStatus.IN_PROGRESS,
                started_at=datetime.utcnow(),
            )

            logger.info(f"Executing step {step_num}: {description}")

            try:
                output = await step_func()
                step_result.output = output
                step_result.status = RollbackStatus.COMPLETED
                step_result.verification_passed = True
            except Exception as e:
                logger.error(f"Step {step_num} failed: {e}")
                step_result.status = RollbackStatus.FAILED
                step_result.error_message = str(e)
                step_result.verification_passed = False
                outcome.status = RollbackStatus.PARTIAL

            step_result.completed_at = datetime.utcnow()
            step_result.duration_seconds = (
                step_result.completed_at - step_result.started_at
            ).total_seconds()

            outcome.steps_results.append(step_result)

    async def _stop_signals(self) -> str:
        """Stop signal generation."""
        # Placeholder - implement actual stop
        logger.info("Stopping signal generation...")
        await asyncio.sleep(0.1)  # Simulate work
        return "Signal generation stopped successfully"

    async def _verify_no_trades(self) -> str:
        """Verify no active trades."""
        logger.info("Verifying no active trades...")
        active_trades = await self._check_active_trades()
        if active_trades > 0:
            raise RollbackSafetyError(f"Active trades still present: {active_trades}")
        return "No active trades confirmed"

    async def _switch_version(self) -> str:
        """Switch to previous brain version."""
        logger.info(
            f"Switching from {self.current_version} to {self.previous_version}..."
        )
        # Placeholder - implement actual version switch
        await asyncio.sleep(0.5)  # Simulate work
        return f"Version switched to {self.previous_version}"

    async def _verify_data_consistency(self) -> str:
        """Verify data consistency after switch."""
        logger.info("Verifying data consistency...")
        if not await self._check_data_consistency():
            raise RollbackSafetyError(
                "Data consistency check failed after version switch"
            )
        return "Data consistency verified"

    async def _start_signals(self) -> str:
        """Resume signal generation."""
        logger.info("Resuming signal generation...")
        # Placeholder - implement actual start
        await asyncio.sleep(0.1)  # Simulate work
        return "Signal generation resumed successfully"

    async def _log_outcome(self, outcome: RollbackOutcome) -> None:
        """Log rollback outcome to disk."""
        # Save JSON
        json_path = self.logs_dir / f"{outcome.rollback_id}.json"
        with open(json_path, "w") as f:
            json.dump(outcome.to_dict(), f, indent=2)

        # Save Markdown report
        md_path = self.logs_dir / f"{outcome.rollback_id}.md"
        with open(md_path, "w") as f:
            f.write(outcome.to_markdown())

        logger.info(f"Rollback outcome logged: {json_path}")

    async def emergency_rollback(
        self,
        reason: str,
        force: bool = False,
    ) -> RollbackOutcome:
        """
        Emergency rollback with minimal checks.

        Args:
            reason: Emergency reason
            force: Force rollback regardless of state

        Returns:
            RollbackOutcome
        """
        logger.warning(f"EMERGENCY ROLLBACK INITIATED: {reason}")

        return await self.trigger_rollback(
            trigger=RollbackTrigger.HUMAN_REQUEST,
            reason=f"EMERGENCY: {reason}",
            initiated_by="emergency_cli",
            force=force,
        )

    def get_last_outcome(self) -> RollbackOutcome | None:
        """Get the last rollback outcome."""
        return self._outcome

    def list_rollback_logs(self) -> list[str]:
        """List all rollback log IDs."""
        return [f.stem for f in self.logs_dir.glob("*.json")]

    def load_rollback_log(self, rollback_id: str) -> RollbackOutcome | None:
        """Load a rollback log."""
        json_path = self.logs_dir / f"{rollback_id}.json"

        if not json_path.exists():
            return None

        with open(json_path) as f:
            data = json.load(f)

        # Reconstruct outcome from dict
        return RollbackOutcome(
            rollback_id=data["rollback_id"],
            trigger=RollbackTrigger(data["trigger"]),
            reason=data["reason"],
            from_version=data["from_version"],
            to_version=data["to_version"],
            initiated_at=datetime.fromisoformat(data["initiated_at"]),
            initiated_by=data["initiated_by"],
            started_at=datetime.fromisoformat(data["started_at"])
            if data.get("started_at")
            else None,
            completed_at=datetime.fromisoformat(data["completed_at"])
            if data.get("completed_at")
            else None,
            total_duration_seconds=data.get("total_duration_seconds", 0),
            initial_state=SystemState(**data["initial_state"])
            if data.get("initial_state")
            else None,
            final_state=SystemState(**data["final_state"])
            if data.get("final_state")
            else None,
            steps_results=[
                RollbackStepResult(
                    step_number=sr["step_number"],
                    description=sr["description"],
                    status=RollbackStatus(sr["status"]),
                    started_at=datetime.fromisoformat(sr["started_at"]),
                    completed_at=datetime.fromisoformat(sr["completed_at"])
                    if sr.get("completed_at")
                    else None,
                    duration_seconds=sr.get("duration_seconds", 0),
                    output=sr.get("output", ""),
                    error_message=sr.get("error_message"),
                    verification_passed=sr.get("verification_passed", False),
                )
                for sr in data.get("steps_results", [])
            ],
            status=RollbackStatus(data.get("status", "not_started")),
            force_override=data.get("force_override", False),
            safety_checks_overridden=data.get("safety_checks_overridden", []),
            lessons_learned=data.get("lessons_learned", ""),
            follow_up_actions=data.get("follow_up_actions", []),
        )


class RollbackSafetyError(Exception):
    """Raised when rollback safety checks fail."""

    pass


# CLI entry point
def main():
    """CLI entry point for rollback handler."""
    parser = argparse.ArgumentParser(
        description="Brain Rollback Handler",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Emergency rollback with force
  python -m src.brain.rollback_handler emergency --reason="Critical error" --force
  
  # Trigger rollback with specific trigger
  python -m src.brain.rollback_handler trigger --trigger=ece_degradation --reason="ECE > 0.15"
  
  # Verify system state
  python -m src.brain.rollback_handler verify-state
  
  # List rollback logs
  python -m src.brain.rollback_handler list-logs
  
  # View rollback report
  python -m src.brain.rollback_handler report --rollback-id=RB-1234567890-ece_degradation
        """,
    )

    parser.add_argument(
        "command",
        choices=["emergency", "trigger", "verify-state", "list-logs", "report"],
        help="Command to execute",
    )
    parser.add_argument("--reason", help="Reason for rollback")
    parser.add_argument(
        "--trigger", choices=[t.value for t in RollbackTrigger], help="Trigger type"
    )
    parser.add_argument(
        "--force", action="store_true", help="Force rollback even if safety checks fail"
    )
    parser.add_argument("--rollback-id", help="Rollback ID for report command")
    parser.add_argument(
        "--current-version", default="unknown", help="Current brain version"
    )
    parser.add_argument(
        "--previous-version", default="unknown", help="Previous brain version"
    )

    args = parser.parse_args()

    async def run():
        handler = RollbackHandler(
            current_version=args.current_version,
            previous_version=args.previous_version,
        )

        if args.command == "emergency":
            if not args.reason:
                print("Error: --reason required for emergency rollback")
                sys.exit(1)

            outcome = await handler.emergency_rollback(
                reason=args.reason,
                force=args.force,
            )
            print(f"Emergency rollback completed: {outcome.status.value}")
            print(f"Rollback ID: {outcome.rollback_id}")
            print(f"Duration: {outcome.total_duration_seconds:.1f} seconds")

        elif args.command == "trigger":
            if not args.trigger or not args.reason:
                print("Error: --trigger and --reason required")
                sys.exit(1)

            trigger = RollbackTrigger(args.trigger)
            outcome = await handler.trigger_rollback(
                trigger=trigger,
                reason=args.reason,
                force=args.force,
            )
            print(f"Rollback completed: {outcome.status.value}")
            print(f"Rollback ID: {outcome.rollback_id}")

        elif args.command == "verify-state":
            state = await handler.verify_system_state()
            print("System State:")
            print(f"  Brain Version: {state.brain_version}")
            print(f"  Active Signals: {state.active_signals}")
            print(f"  Active Trades: {state.active_trades_count}")
            print(f"  Data Consistency: {state.data_consistency_ok}")

        elif args.command == "list-logs":
            logs = handler.list_rollback_logs()
            print("Rollback Logs:")
            for log_id in logs:
                print(f"  - {log_id}")

        elif args.command == "report":
            if not args.rollback_id:
                print("Error: --rollback-id required")
                sys.exit(1)

            outcome = handler.load_rollback_log(args.rollback_id)
            if outcome:
                print(outcome.to_markdown())
            else:
                print(f"Rollback log not found: {args.rollback_id}")

    asyncio.run(run())


if __name__ == "__main__":
    main()
