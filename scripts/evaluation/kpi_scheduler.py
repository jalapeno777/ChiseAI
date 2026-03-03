#!/usr/bin/env python3
"""KPI Scheduler - Docker-safe scheduling for brain evaluation.

# SAFETY: No risk cap logic modified
# SAFETY: No promotion gate logic modified
# SAFETY: No live trading flow modified

Provides Docker-safe scheduling for KPI evaluation cycles:
- 6h cycle: Mini ingest/eval (every 6 hours)
- Daily cycle: Trend rollups + daily reflection
- Weekly cycle: Deep reflection

Docker-safe design:
- No systemd dependencies
- Uses while/sleep loop or external cron container
- All commands idempotent (check before write)
- Non-destructive (never delete data, only append)
- Exit codes: 0=success, 1=failure

Usage:
    # Run specific cycles
    python kpi_scheduler.py --cycle 6h
    python kpi_scheduler.py --cycle daily
    python kpi_scheduler.py --cycle weekly

    # Dry-run all cycles for validation
    python kpi_scheduler.py --dry-run-all

    # Run in daemon mode (continuous scheduling)
    python kpi_scheduler.py --daemon
"""

from __future__ import annotations

import argparse
import http.server
import json
import logging
import os
import signal
import socketserver
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("kpi_scheduler")


class SchedulerState(Enum):
    """Scheduler state machine states."""

    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    SHUTTING_DOWN = "shutting_down"
    ERROR = "error"


@dataclass
class SchedulerCheckpoint:
    """Checkpoint data for scheduler state persistence.

    Attributes:
        state: Current scheduler state
        last_run_6h: Timestamp of last 6h cycle run
        last_run_daily: Timestamp of last daily cycle run
        last_run_weekly: Timestamp of last weekly cycle run
        cycle_count: Total number of cycles executed
        error_count: Number of errors encountered
        last_error: Last error message if any
        version: Checkpoint format version
    """

    state: str = SchedulerState.INITIALIZING.value
    last_run_6h: float = 0.0
    last_run_daily: float = 0.0
    last_run_weekly: float = 0.0
    cycle_count: int = 0
    error_count: int = 0
    last_error: str | None = None
    version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        """Convert checkpoint to dictionary."""
        return {
            "state": self.state,
            "last_run_6h": self.last_run_6h,
            "last_run_daily": self.last_run_daily,
            "last_run_weekly": self.last_run_weekly,
            "cycle_count": self.cycle_count,
            "error_count": self.error_count,
            "last_error": self.last_error,
            "version": self.version,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SchedulerCheckpoint:
        """Create checkpoint from dictionary."""
        return cls(
            state=data.get("state", SchedulerState.INITIALIZING.value),
            last_run_6h=data.get("last_run_6h", 0.0),
            last_run_daily=data.get("last_run_daily", 0.0),
            last_run_weekly=data.get("last_run_weekly", 0.0),
            cycle_count=data.get("cycle_count", 0),
            error_count=data.get("error_count", 0),
            last_error=data.get("last_error"),
            version=data.get("version", "1.0"),
        )


class HealthCheckHandler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler for health check endpoint."""

    def __init__(
        self,
        checkpoint: SchedulerCheckpoint,
        *args: Any,
        **kwargs: Any,
    ):
        self.checkpoint = checkpoint
        super().__init__(*args, **kwargs)

    def do_GET(self) -> None:
        """Handle GET requests."""
        if self.path == "/health":
            self._handle_health_check()
        elif self.path == "/status":
            self._handle_status()
        else:
            self.send_error(404)

    def _handle_health_check(self) -> None:
        """Handle health check request."""
        status = {
            "status": "healthy",
            "state": self.checkpoint.state,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        if self.checkpoint.state == SchedulerState.ERROR.value:
            status["status"] = "unhealthy"
            self.send_response(503)
        else:
            self.send_response(200)

        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(status).encode())

    def _handle_status(self) -> None:
        """Handle detailed status request."""
        status = {
            "status": (
                "healthy"
                if self.checkpoint.state != SchedulerState.ERROR.value
                else "unhealthy"
            ),
            "state": self.checkpoint.state,
            "checkpoint": self.checkpoint.to_dict(),
            "timestamp": datetime.now(UTC).isoformat(),
        }

        self.send_response(200 if status["status"] == "healthy" else 503)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(status, indent=2).encode())

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default logging."""
        logger.debug(f"Health check: {format % args}")


class HealthCheckServer:
    """HTTP health check server for scheduler."""

    def __init__(self, checkpoint: SchedulerCheckpoint, port: int = 8080):
        """Initialize health check server.

        Args:
            checkpoint: Shared checkpoint object
            port: Port to listen on
        """
        self.checkpoint = checkpoint
        self.port = port
        self.server: socketserver.TCPServer | None = None
        self.thread: threading.Thread | None = None
        self._running = False

    def _create_handler(self) -> type[http.server.BaseHTTPRequestHandler]:
        """Create request handler class with checkpoint reference."""
        checkpoint = self.checkpoint

        class Handler(HealthCheckHandler):
            def __init__(self, *args: Any, **kwargs: Any):
                super().__init__(checkpoint, *args, **kwargs)

        return Handler

    def start(self) -> None:
        """Start health check server in background thread."""
        if self._running:
            return

        handler_class = self._create_handler()

        class ReusableTCPServer(socketserver.TCPServer):
            allow_reuse_address = True

        self.server = ReusableTCPServer(("", self.port), handler_class)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self._running = True

        logger.info(f"Health check server started on port {self.port}")

    def stop(self) -> None:
        """Stop health check server."""
        if not self._running:
            return

        if self.server:
            self.server.shutdown()
            self.server.server_close()

        self._running = False
        logger.info("Health check server stopped")


class KPIScheduler:
    """Docker-safe scheduler for KPI evaluation cycles.

    Provides scheduling methods for 6h, daily, and weekly evaluation cycles.
    All methods are idempotent and non-destructive.

    Attributes:
        output_dir: Base directory for scheduler output
        dry_run: If True, skip actual execution

    Example:
        >>> scheduler = KPIScheduler(dry_run=False)
        >>> scheduler.run_6h_cycle()  # Run 6h evaluation
        >>> scheduler.run_all_dry()  # Dry-run all cycles
    """

    def __init__(
        self,
        output_dir: Path | str = "_bmad-output/brain-eval/scheduler",
        dry_run: bool = False,
        checkpoint: SchedulerCheckpoint | None = None,
    ) -> None:
        """Initialize KPI scheduler.

        Args:
            output_dir: Base directory for scheduler output
            dry_run: If True, skip actual execution
            checkpoint: Optional checkpoint object for state tracking
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.dry_run = dry_run
        self.checkpoint = checkpoint or SchedulerCheckpoint()

        # Script paths
        self.scripts_dir = Path(__file__).parent
        self.run_mini_eval = self.scripts_dir / "run_mini_eval.py"
        self.run_daily_trends = self.scripts_dir / "run_daily_trends.py"
        self.run_weekly_reflection = self.scripts_dir / "run_weekly_reflection.py"

        # Load checkpoint if exists
        self._load_checkpoint()

    def run_6h_cycle(self) -> int:
        """Run 6h mini ingest/eval cycle.

        Executes mini evaluation cycle that runs every 6 hours.
        Persists KPIs via KPIPersistence.

        Returns:
            Exit code (0=success, 1=failure)
        """
        logger.info("Starting 6h cycle")

        # Log cycle start
        self._log_cycle_start("6h")

        if self.dry_run:
            logger.info("DRY RUN: Skipping 6h cycle execution")
            self._log_cycle_complete("6h", success=True, dry_run=True)
            return 0

        try:
            # Run mini eval script (no --cadence arg, it's always 6h)
            result = self._run_script(self.run_mini_eval)

            if result.returncode == 0:
                logger.info("6h cycle completed successfully")
                self._log_cycle_complete("6h", success=True)
                self.record_cycle_complete("6h", success=True)
                return 0
            else:
                logger.error(f"6h cycle failed with exit code {result.returncode}")
                self._log_cycle_complete("6h", success=False, error=result.stderr)
                self.record_cycle_complete("6h", success=False, error=result.stderr)
                return 1

        except Exception as e:
            logger.exception(f"6h cycle failed: {e}")
            self._log_cycle_complete("6h", success=False, error=str(e))
            self.record_cycle_complete("6h", success=False, error=str(e))
            return 1

    def run_daily_cycle(self) -> int:
        """Run daily trend + reflection cycle.

        Computes trend rollups (24h, 7d, 30d) and generates daily reflection.

        Returns:
            Exit code (0=success, 1=failure)
        """
        logger.info("Starting daily cycle")

        # Log cycle start
        self._log_cycle_start("daily")

        if self.dry_run:
            logger.info("DRY RUN: Skipping daily cycle execution")
            self._log_cycle_complete("daily", success=True, dry_run=True)
            return 0

        try:
            # Run daily trends script
            result = self._run_script(self.run_daily_trends)

            if result.returncode == 0:
                logger.info("Daily cycle completed successfully")
                self._log_cycle_complete("daily", success=True)
                self.record_cycle_complete("daily", success=True)
                return 0
            else:
                logger.error(f"Daily cycle failed with exit code {result.returncode}")
                self._log_cycle_complete("daily", success=False, error=result.stderr)
                self.record_cycle_complete("daily", success=False, error=result.stderr)
                return 1

        except Exception as e:
            logger.exception(f"Daily cycle failed: {e}")
            self._log_cycle_complete("daily", success=False, error=str(e))
            self.record_cycle_complete("daily", success=False, error=str(e))
            return 1

    def run_weekly_cycle(self) -> int:
        """Run weekly deep reflection cycle.

        Generates weekly deep reflection report.

        Returns:
            Exit code (0=success, 1=failure)
        """
        logger.info("Starting weekly cycle")

        # Log cycle start
        self._log_cycle_start("weekly")

        if self.dry_run:
            logger.info("DRY RUN: Skipping weekly cycle execution")
            self._log_cycle_complete("weekly", success=True, dry_run=True)
            return 0

        try:
            # Run weekly reflection script
            result = self._run_script(self.run_weekly_reflection)

            if result.returncode == 0:
                logger.info("Weekly cycle completed successfully")
                self._log_cycle_complete("weekly", success=True)
                self.record_cycle_complete("weekly", success=True)
                return 0
            else:
                logger.error(f"Weekly cycle failed with exit code {result.returncode}")
                self._log_cycle_complete("weekly", success=False, error=result.stderr)
                self.record_cycle_complete("weekly", success=False, error=result.stderr)
                return 1

        except Exception as e:
            logger.exception(f"Weekly cycle failed: {e}")
            self._log_cycle_complete("weekly", success=False, error=str(e))
            self.record_cycle_complete("weekly", success=False, error=str(e))
            return 1

    def run_all_dry(self) -> int:
        """Dry-run all cycles for validation.

        Tests all cycle execution paths without making changes.

        Returns:
            Exit code (0=all success, 1=any failure)
        """
        logger.info("Running dry-run for all cycles")

        # Temporarily enable dry_run mode
        original_dry_run = self.dry_run
        self.dry_run = True

        try:
            results = {
                "6h": self.run_6h_cycle(),
                "daily": self.run_daily_cycle(),
                "weekly": self.run_weekly_cycle(),
            }

            # Report results
            all_success = all(code == 0 for code in results.values())

            logger.info("Dry-run results:")
            for cycle, code in results.items():
                status = "✓ PASS" if code == 0 else "✗ FAIL"
                logger.info(f"  {cycle}: {status}")

            return 0 if all_success else 1

        finally:
            # Restore original dry_run mode
            self.dry_run = original_dry_run

    def _run_script(
        self, script_path: Path, *args: str
    ) -> subprocess.CompletedProcess[str]:
        """Run a subprocess script with proper error handling.

        Args:
            script_path: Path to the script to run
            *args: Arguments to pass to the script

        Returns:
            CompletedProcess with result
        """
        cmd = [sys.executable, str(script_path)] + list(args)
        logger.info(f"Running: {' '.join(cmd)}")

        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
        )

    def _log_cycle_start(self, cycle: str) -> None:
        """Log cycle start to file.

        Args:
            cycle: Cycle name (6h, daily, weekly)
        """
        log_entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event": "cycle_start",
            "cycle": cycle,
            "dry_run": self.dry_run,
        }

        self._append_log(log_entry)

    def _log_cycle_complete(
        self,
        cycle: str,
        success: bool,
        error: str | None = None,
        dry_run: bool = False,
    ) -> None:
        """Log cycle completion to file.

        Args:
            cycle: Cycle name (6h, daily, weekly)
            success: Whether cycle succeeded
            error: Error message if failed
            dry_run: Whether this was a dry run
        """
        log_entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event": "cycle_complete",
            "cycle": cycle,
            "success": success,
            "dry_run": dry_run,
        }

        if error:
            log_entry["error"] = error

        self._append_log(log_entry)

    def _append_log(self, entry: dict[str, Any]) -> None:
        """Append log entry to scheduler log file.

        Args:
            entry: Log entry dictionary
        """
        log_file = self.output_dir / "scheduler.log"

        try:
            with open(log_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.warning(f"Failed to write to scheduler log: {e}")

    def _get_checkpoint_path(self) -> Path:
        """Get path to checkpoint file."""
        return self.output_dir / "checkpoint.json"

    def _load_checkpoint(self) -> None:
        """Load checkpoint from file if exists."""
        checkpoint_path = self._get_checkpoint_path()

        if checkpoint_path.exists():
            try:
                with open(checkpoint_path) as f:
                    data = json.load(f)
                    self.checkpoint = SchedulerCheckpoint.from_dict(data)
                    logger.info(f"Loaded checkpoint: {self.checkpoint.state}")
            except Exception as e:
                logger.warning(f"Failed to load checkpoint: {e}")
                self.checkpoint = SchedulerCheckpoint()

    def _save_checkpoint(self) -> None:
        """Save checkpoint to file."""
        checkpoint_path = self._get_checkpoint_path()

        try:
            with open(checkpoint_path, "w") as f:
                json.dump(self.checkpoint.to_dict(), f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save checkpoint: {e}")

    def update_checkpoint_state(self, state: SchedulerState) -> None:
        """Update scheduler state in checkpoint.

        Args:
            state: New scheduler state
        """
        self.checkpoint.state = state.value
        self._save_checkpoint()
        logger.info(f"Scheduler state changed to: {state.value}")

    def record_cycle_complete(
        self, cycle: str, success: bool, error: str | None = None
    ) -> None:
        """Record cycle completion in checkpoint.

        Args:
            cycle: Cycle name (6h, daily, weekly)
            success: Whether cycle succeeded
            error: Error message if failed
        """
        current_time = time.time()

        if cycle == "6h":
            self.checkpoint.last_run_6h = current_time
        elif cycle == "daily":
            self.checkpoint.last_run_daily = current_time
        elif cycle == "weekly":
            self.checkpoint.last_run_weekly = current_time

        self.checkpoint.cycle_count += 1

        if not success:
            self.checkpoint.error_count += 1
            self.checkpoint.last_error = error or "Unknown error"

        self._save_checkpoint()


def run_daemon() -> int:
    """Run scheduler in daemon mode with continuous scheduling.

    Uses while/sleep loop for Docker-safe scheduling.
    Includes health check endpoint, state machine, and graceful shutdown.

    Returns:
        Exit code (only returns on error or shutdown)
    """
    logger.info("Starting KPI scheduler daemon")

    # Get configuration from environment
    interval_6h = int(os.getenv("SCHEDULER_INTERVAL_6H", 6 * 3600))  # 6 hours
    interval_daily = int(os.getenv("SCHEDULER_INTERVAL_DAILY", 24 * 3600))  # 24 hours
    interval_weekly = int(
        os.getenv("SCHEDULER_INTERVAL_WEEKLY", 7 * 24 * 3600)
    )  # 7 days
    health_port = int(os.getenv("SCHEDULER_HEALTH_PORT", 8080))
    output_dir = os.getenv("SCHEDULER_OUTPUT_DIR", "_bmad-output/brain-eval/scheduler")

    logger.info(
        f"Configuration - 6h: {interval_6h}s, daily: {interval_daily}s, weekly: {interval_weekly}s, "
        f"health_port: {health_port}"
    )

    # Initialize checkpoint and scheduler
    checkpoint = SchedulerCheckpoint()
    scheduler = KPIScheduler(output_dir=output_dir, checkpoint=checkpoint)
    scheduler.update_checkpoint_state(SchedulerState.INITIALIZING)

    # Initialize last run times from checkpoint
    last_run = {
        "6h": checkpoint.last_run_6h,
        "daily": checkpoint.last_run_daily,
        "weekly": checkpoint.last_run_weekly,
    }

    logger.info(
        f"Resumed from checkpoint - 6h: {last_run['6h']}, daily: {last_run['daily']}, weekly: {last_run['weekly']}"
    )

    # Start health check server
    health_server = HealthCheckServer(checkpoint, port=health_port)
    health_server.start()

    # Set up signal handlers for graceful shutdown
    shutdown_requested = threading.Event()

    def signal_handler(signum: int, frame: Any) -> None:
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        shutdown_requested.set()

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Transition to running state
    scheduler.update_checkpoint_state(SchedulerState.RUNNING)

    try:
        while not shutdown_requested.is_set():
            current_time = time.time()

            # Check 6h cycle
            if current_time - last_run["6h"] >= interval_6h:
                logger.info("Triggering 6h cycle")
                exit_code = scheduler.run_6h_cycle()
                scheduler.record_cycle_complete("6h", success=(exit_code == 0))
                last_run["6h"] = current_time

            # Check daily cycle
            if current_time - last_run["daily"] >= interval_daily:
                logger.info("Triggering daily cycle")
                exit_code = scheduler.run_daily_cycle()
                scheduler.record_cycle_complete("daily", success=(exit_code == 0))
                last_run["daily"] = current_time

            # Check weekly cycle
            if current_time - last_run["weekly"] >= interval_weekly:
                logger.info("Triggering weekly cycle")
                exit_code = scheduler.run_weekly_cycle()
                scheduler.record_cycle_complete("weekly", success=(exit_code == 0))
                last_run["weekly"] = current_time

            # Sleep for 60 seconds before next check (or until shutdown)
            shutdown_requested.wait(timeout=60)

        # Graceful shutdown
        logger.info("Graceful shutdown initiated")
        scheduler.update_checkpoint_state(SchedulerState.SHUTTING_DOWN)
        health_server.stop()
        logger.info("Daemon stopped gracefully")
        return 0

    except Exception as e:
        logger.exception(f"Daemon failed: {e}")
        scheduler.update_checkpoint_state(SchedulerState.ERROR)
        scheduler.checkpoint.last_error = str(e)
        scheduler._save_checkpoint()
        health_server.stop()
        return 1


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0=success, 1=failure)
    """
    parser = argparse.ArgumentParser(
        description="KPI Scheduler - Docker-safe scheduling for brain evaluation"
    )
    parser.add_argument(
        "--cycle",
        choices=["6h", "daily", "weekly"],
        help="Run specific cycle",
    )
    parser.add_argument(
        "--dry-run-all",
        action="store_true",
        help="Dry-run all cycles for validation",
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run in daemon mode with continuous scheduling",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("_bmad-output/brain-eval/scheduler"),
        help="Output directory for scheduler logs",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run in dry-run mode (no actual execution)",
    )

    args = parser.parse_args()

    # Handle daemon mode
    if args.daemon:
        return run_daemon()

    # Handle dry-run-all mode
    if args.dry_run_all:
        scheduler = KPIScheduler(output_dir=args.output_dir)
        return scheduler.run_all_dry()

    # Handle specific cycle
    if args.cycle:
        scheduler = KPIScheduler(output_dir=args.output_dir, dry_run=args.dry_run)

        if args.cycle == "6h":
            return scheduler.run_6h_cycle()
        elif args.cycle == "daily":
            return scheduler.run_daily_cycle()
        elif args.cycle == "weekly":
            return scheduler.run_weekly_cycle()

    # No action specified
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
