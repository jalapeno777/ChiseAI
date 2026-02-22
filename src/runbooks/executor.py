"""
Runbook executor for running executable steps from markdown documentation.
"""

import json
import logging
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .parser import RunbookParser, RunbookStep


@dataclass
class StepResult:
    """Result of executing a single step."""

    step_name: str
    success: bool
    return_code: int
    stdout: str
    stderr: str
    execution_time_ms: float
    timestamp: datetime = field(default_factory=datetime.utcnow)
    error_message: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "step_name": self.step_name,
            "success": self.success,
            "return_code": self.return_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "execution_time_ms": self.execution_time_ms,
            "timestamp": self.timestamp.isoformat(),
            "error_message": self.error_message,
        }


@dataclass
class ExecutionResult:
    """Result of executing a complete runbook."""

    runbook_name: str
    success: bool
    dry_run: bool
    steps: list[StepResult]
    start_time: datetime
    end_time: datetime
    total_steps: int
    passed_steps: int
    failed_steps: int
    log_file: Optional[Path] = None

    @property
    def execution_time_seconds(self) -> float:
        """Calculate total execution time."""
        return (self.end_time - self.start_time).total_seconds()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "runbook_name": self.runbook_name,
            "success": self.success,
            "dry_run": self.dry_run,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "execution_time_seconds": self.execution_time_seconds,
            "total_steps": self.total_steps,
            "passed_steps": self.passed_steps,
            "failed_steps": self.failed_steps,
            "log_file": str(self.log_file) if self.log_file else None,
            "steps": [step.to_dict() for step in self.steps],
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)


class RunbookExecutor:
    """Execute runbooks with logging and dry-run support."""

    def __init__(
        self,
        runbooks_dir: Optional[Path] = None,
        scripts_dir: Optional[Path] = None,
        log_dir: Optional[Path] = None,
        dry_run: bool = False,
    ):
        """
        Initialize the executor.

        Args:
            runbooks_dir: Directory containing runbook markdown files
            scripts_dir: Directory containing operation scripts
            log_dir: Directory for execution logs
            dry_run: If True, show what would be executed without running
        """
        self.parser = RunbookParser(runbooks_dir)
        self.dry_run = dry_run

        # Find repo root for default paths
        repo_root = self._find_repo_root()

        self.scripts_dir = (
            Path(scripts_dir) if scripts_dir else repo_root / "scripts" / "ops"
        )
        self.log_dir = Path(log_dir) if log_dir else repo_root / "logs" / "runbooks"

        # Ensure log directory exists
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Setup logging
        self.logger = self._setup_logger()

    def _find_repo_root(self) -> Path:
        """Find the repository root directory."""
        current = Path.cwd()
        while current != current.parent:
            if (current / ".git").exists() or (current / "pyproject.toml").exists():
                return current
            current = current.parent
        return Path.cwd()

    def _setup_logger(self) -> logging.Logger:
        """Setup logger for execution output."""
        logger = logging.getLogger("runbook_executor")
        logger.setLevel(logging.DEBUG)

        # Prevent duplicate handlers
        if logger.handlers:
            return logger

        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_format = logging.Formatter("%(levelname)s: %(message)s")
        console_handler.setFormatter(console_format)
        logger.addHandler(console_handler)

        return logger

    def list_runbooks(self) -> list[str]:
        """List all available runbooks."""
        return self.parser.list_runbooks()

    def execute(
        self, runbook_name: str, dry_run: Optional[bool] = None
    ) -> ExecutionResult:
        """
        Execute a runbook by name.

        Args:
            runbook_name: Name of the runbook (without .md extension)
            dry_run: Override dry-run mode for this execution

        Returns:
            ExecutionResult with full execution details
        """
        dry_run = dry_run if dry_run is not None else self.dry_run
        start_time = datetime.utcnow()

        self.logger.info(
            f"{'[DRY-RUN] ' if dry_run else ''}Executing runbook: {runbook_name}"
        )

        try:
            runbook = self.parser.parse(runbook_name)
        except FileNotFoundError as e:
            self.logger.error(f"Runbook not found: {runbook_name}")
            return ExecutionResult(
                runbook_name=runbook_name,
                success=False,
                dry_run=dry_run,
                steps=[],
                start_time=start_time,
                end_time=datetime.utcnow(),
                total_steps=0,
                passed_steps=0,
                failed_steps=1,
            )

        # Log runbook info
        self.logger.info(f"Title: {runbook.metadata.title or 'N/A'}")
        self.logger.info(f"Category: {runbook.metadata.category or 'N/A'}")
        self.logger.info(f"Severity: {runbook.metadata.severity or 'N/A'}")
        self.logger.info(f"Executable: {runbook.is_executable}")
        self.logger.info(f"Steps found: {len(runbook.steps)}")

        if not runbook.is_executable:
            self.logger.warning(
                f"Runbook '{runbook_name}' is not marked as executable or has no executable steps"
            )

        # Execute steps
        step_results = []
        passed = 0
        failed = 0

        for i, step in enumerate(runbook.steps, 1):
            self.logger.info(f"\nStep {i}/{len(runbook.steps)}: {step.name}")

            if not step.is_executable():
                self.logger.info("  Skipping (no executable action)")
                continue

            result = self._execute_step(step, dry_run)
            step_results.append(result)

            if result.success:
                passed += 1
                self.logger.info(f"  ✓ Success (took {result.execution_time_ms:.0f}ms)")
            else:
                failed += 1
                self.logger.error(f"  ✗ Failed (exit code: {result.return_code})")
                if result.error_message:
                    self.logger.error(f"    Error: {result.error_message}")

            # Stop on first failure unless it's a dry run
            if not result.success and not dry_run:
                self.logger.error("Stopping execution due to step failure")
                break

        end_time = datetime.utcnow()

        # Create execution result
        execution_result = ExecutionResult(
            runbook_name=runbook_name,
            success=failed == 0,
            dry_run=dry_run,
            steps=step_results,
            start_time=start_time,
            end_time=end_time,
            total_steps=len([s for s in runbook.steps if s.is_executable()]),
            passed_steps=passed,
            failed_steps=failed,
        )

        # Log to file
        log_file = self._save_execution_log(execution_result)
        execution_result.log_file = log_file

        # Summary
        self.logger.info(f"\n{'=' * 50}")
        self.logger.info("Execution Summary")
        self.logger.info(f"{'=' * 50}")
        self.logger.info(f"Total steps: {execution_result.total_steps}")
        self.logger.info(f"Passed: {passed}")
        self.logger.info(f"Failed: {failed}")
        self.logger.info(f"Duration: {execution_result.execution_time_seconds:.2f}s")
        self.logger.info(f"Log file: {log_file}")
        self.logger.info(
            f"Result: {'SUCCESS' if execution_result.success else 'FAILED'}"
        )

        return execution_result

    def _execute_step(self, step: RunbookStep, dry_run: bool) -> StepResult:
        """Execute a single step."""
        import time

        start_time = time.time()

        if dry_run:
            # In dry-run mode, just show what would be executed
            if step.command:
                self.logger.info(f"  [DRY-RUN] Would execute: {step.command[:80]}...")
            elif step.script:
                self.logger.info(f"  [DRY-RUN] Would run script: {step.script}")

            return StepResult(
                step_name=step.name,
                success=True,
                return_code=0,
                stdout="[DRY-RUN] Command not executed",
                stderr="",
                execution_time_ms=0.0,
            )

        # Determine what to execute
        if step.script:
            # Script path - resolve relative to scripts_dir
            script_path = self._resolve_script_path(step.script)
            cmd = str(script_path)
            run_args = [cmd]

            if not script_path.exists():
                return StepResult(
                    step_name=step.name,
                    success=False,
                    return_code=1,
                    stdout="",
                    stderr="",
                    execution_time_ms=(time.time() - start_time) * 1000,
                    error_message=f"Script not found: {script_path}",
                )
        elif step.command:
            cmd = step.command
            # Route command strings through bash without using shell=True.
            run_args = ["bash", "-lc", cmd]
        else:
            return StepResult(
                step_name=step.name,
                success=False,
                return_code=1,
                stdout="",
                stderr="",
                execution_time_ms=(time.time() - start_time) * 1000,
                error_message="No command or script specified",
            )

        # Execute the command
        try:
            timeout = step.timeout or 300  # Default 5 minute timeout

            self.logger.debug(f"Executing: {cmd}")

            result = subprocess.run(
                run_args,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self._find_repo_root(),
            )

            execution_time_ms = (time.time() - start_time) * 1000

            return StepResult(
                step_name=step.name,
                success=result.returncode == 0,
                return_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                execution_time_ms=execution_time_ms,
                error_message=(
                    None
                    if result.returncode == 0
                    else f"Command failed with exit code {result.returncode}"
                ),
            )

        except subprocess.TimeoutExpired:
            execution_time_ms = (time.time() - start_time) * 1000
            return StepResult(
                step_name=step.name,
                success=False,
                return_code=-1,
                stdout="",
                stderr="",
                execution_time_ms=execution_time_ms,
                error_message=f"Command timed out after {timeout} seconds",
            )
        except Exception as e:
            execution_time_ms = (time.time() - start_time) * 1000
            return StepResult(
                step_name=step.name,
                success=False,
                return_code=-1,
                stdout="",
                stderr=str(e),
                execution_time_ms=execution_time_ms,
                error_message=str(e),
            )

    def _resolve_script_path(self, script: str) -> Path:
        """Resolve a script path relative to scripts_dir."""
        # If it's already an absolute path, use it
        script_path = Path(script)
        if script_path.is_absolute():
            return script_path

        # If it starts with scripts/, resolve from repo root
        if script.startswith("scripts/"):
            return self._find_repo_root() / script

        # Otherwise, resolve from scripts_dir
        return self.scripts_dir / script

    def _save_execution_log(self, result: ExecutionResult) -> Path:
        """Save execution result to log file."""
        import time

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        # Add microseconds to ensure uniqueness for rapid successive executions
        unique_suffix = str(int(time.time() * 1000) % 1000).zfill(3)
        log_file = (
            self.log_dir / f"{result.runbook_name}_{timestamp}_{unique_suffix}.json"
        )

        log_data = {
            "execution": result.to_dict(),
            "metadata": {"version": "0.1.0", "executor": "runbook_executor"},
        }

        log_file.write_text(json.dumps(log_data, indent=2))
        return log_file

    def get_execution_history(
        self, runbook_name: Optional[str] = None, limit: int = 10
    ) -> list[Path]:
        """Get list of execution log files."""
        if not self.log_dir.exists():
            return []

        logs = sorted(
            self.log_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True
        )

        if runbook_name:
            logs = [log for log in logs if log.name.startswith(f"{runbook_name}_")]

        return logs[:limit]
