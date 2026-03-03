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
import json
import logging
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
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
    ) -> None:
        """Initialize KPI scheduler.

        Args:
            output_dir: Base directory for scheduler output
            dry_run: If True, skip actual execution
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.dry_run = dry_run

        # Script paths
        self.scripts_dir = Path(__file__).parent
        self.run_mini_eval = self.scripts_dir / "run_mini_eval.py"
        self.run_daily_trends = self.scripts_dir / "run_daily_trends.py"
        self.run_weekly_reflection = self.scripts_dir / "run_weekly_reflection.py"

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
                return 0
            else:
                logger.error(f"6h cycle failed with exit code {result.returncode}")
                self._log_cycle_complete("6h", success=False, error=result.stderr)
                return 1

        except Exception as e:
            logger.exception(f"6h cycle failed: {e}")
            self._log_cycle_complete("6h", success=False, error=str(e))
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
                return 0
            else:
                logger.error(f"Daily cycle failed with exit code {result.returncode}")
                self._log_cycle_complete("daily", success=False, error=result.stderr)
                return 1

        except Exception as e:
            logger.exception(f"Daily cycle failed: {e}")
            self._log_cycle_complete("daily", success=False, error=str(e))
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
                return 0
            else:
                logger.error(f"Weekly cycle failed with exit code {result.returncode}")
                self._log_cycle_complete("weekly", success=False, error=result.stderr)
                return 1

        except Exception as e:
            logger.exception(f"Weekly cycle failed: {e}")
            self._log_cycle_complete("weekly", success=False, error=str(e))
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


def run_daemon() -> int:
    """Run scheduler in daemon mode with continuous scheduling.

    Uses while/sleep loop for Docker-safe scheduling.

    Returns:
        Exit code (only returns on error)
    """
    logger.info("Starting KPI scheduler daemon")

    # Get intervals from environment (in seconds)
    interval_6h = int(os.getenv("SCHEDULER_INTERVAL_6H", 6 * 3600))  # 6 hours
    interval_daily = int(os.getenv("SCHEDULER_INTERVAL_DAILY", 24 * 3600))  # 24 hours
    interval_weekly = int(
        os.getenv("SCHEDULER_INTERVAL_WEEKLY", 7 * 24 * 3600)
    )  # 7 days

    logger.info(
        f"Intervals - 6h: {interval_6h}s, daily: {interval_daily}s, weekly: {interval_weekly}s"
    )

    # Track last run times
    last_run = {
        "6h": 0.0,
        "daily": 0.0,
        "weekly": 0.0,
    }

    scheduler = KPIScheduler()

    try:
        while True:
            current_time = time.time()

            # Check 6h cycle
            if current_time - last_run["6h"] >= interval_6h:
                logger.info("Triggering 6h cycle")
                scheduler.run_6h_cycle()
                last_run["6h"] = current_time

            # Check daily cycle
            if current_time - last_run["daily"] >= interval_daily:
                logger.info("Triggering daily cycle")
                scheduler.run_daily_cycle()
                last_run["daily"] = current_time

            # Check weekly cycle
            if current_time - last_run["weekly"] >= interval_weekly:
                logger.info("Triggering weekly cycle")
                scheduler.run_weekly_cycle()
                last_run["weekly"] = current_time

            # Sleep for 60 seconds before next check
            time.sleep(60)

    except KeyboardInterrupt:
        logger.info("Daemon stopped by user")
        return 0
    except Exception as e:
        logger.exception(f"Daemon failed: {e}")
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
