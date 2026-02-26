#!/usr/bin/env python3
"""Run all monitoring checks sequentially.

Runs all monitoring checks and reports overall health status.
Suitable for cron execution.

Exit codes:
    0 - All checks passed
    1 - One or more checks failed
    2 - Critical error (could not run checks)
"""

import os
import sys
import subprocess
import logging
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def find_project_root() -> Path:
    """Find the project root directory."""
    script_path = Path(__file__).absolute()
    current = script_path.parent

    while current != current.parent:
        if (current / ".env").exists() or (current / ".git").exists():
            return current
        current = current.parent

    return script_path.parent.parent.parent


def run_check(script_name: str, project_root: Path) -> Tuple[int, str, str]:
    """
    Run a single monitoring check script.

    Returns:
        Tuple of (exit_code, stdout, stderr)
    """
    script_path = project_root / "scripts" / "monitoring" / script_name

    if not script_path.exists():
        logger.error(f"Script not found: {script_path}")
        return (1, "", f"Script not found: {script_path}")

    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=60,  # 1 minute timeout per check
        )

        return (result.returncode, result.stdout, result.stderr)

    except subprocess.TimeoutExpired:
        logger.error(f"{script_name} timed out")
        return (1, "", "Timeout after 60 seconds")
    except Exception as e:
        logger.error(f"Error running {script_name}: {e}")
        return (1, "", str(e))


def format_summary(results: List[Dict]) -> str:
    """Format overall summary message."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    passed = sum(1 for r in results if r["exit_code"] == 0)
    failed = sum(1 for r in results if r["exit_code"] != 0)

    lines = [
        f"**🔍 All Monitoring Checks** | {timestamp}",
        f"",
        f"**Overall Status:** {passed} passed, {failed} failed",
        f"",
    ]

    for result in results:
        status = "✅" if result["exit_code"] == 0 else "❌"
        lines.append(f"{status} **{result['name']}**: Exit code {result['exit_code']}")

        # Add error details if failed
        if result["exit_code"] != 0 and result["stderr"]:
            # Truncate long error messages
            error = (
                result["stderr"][:100] + "..."
                if len(result["stderr"]) > 100
                else result["stderr"]
            )
            lines.append(f"   Error: {error}")

    lines.extend([f"", f"_Run completed at {timestamp}_"])

    return "\n".join(lines)


def log_summary(message: str, project_root: Path) -> str:
    """Log summary to file."""
    try:
        log_dir = project_root / "logs" / "monitoring"
        os.makedirs(log_dir, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        log_path = log_dir / f"all-checks-{timestamp}.log"

        with open(log_path, "w") as f:
            f.write(message)

        return str(log_path)
    except Exception as e:
        logger.error(f"Failed to log summary: {e}")
        return ""


def main() -> int:
    """Main entry point."""
    logger.info("Starting all monitoring checks")

    project_root = find_project_root()
    logger.info(f"Project root: {project_root}")

    # Define checks to run
    checks = [
        ("hourly_health_check.py", "Hourly Health Check"),
        ("daily_executive_summary.py", "Daily Executive Summary"),
        ("checkpoint_gate_audit.py", "Checkpoint Gate Audit"),
    ]

    results = []

    for script_name, display_name in checks:
        logger.info(f"Running {display_name}...")

        exit_code, stdout, stderr = run_check(script_name, project_root)

        result = {
            "name": display_name,
            "script": script_name,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
        }
        results.append(result)

        if exit_code == 0:
            logger.info(f"✅ {display_name} passed")
        else:
            logger.warning(f"❌ {display_name} failed (exit code: {exit_code})")
            if stderr:
                logger.warning(f"   Error: {stderr[:200]}")

    # Format and log summary
    summary = format_summary(results)
    log_path = log_summary(summary, project_root)

    if log_path:
        logger.info(f"Summary logged to: {log_path}")

    # Print summary to stdout
    print("\n" + "=" * 60)
    print(summary)
    print("=" * 60)

    # Determine overall exit code
    failed_count = sum(1 for r in results if r["exit_code"] != 0)

    if failed_count == 0:
        logger.info("All monitoring checks passed")
        return 0
    else:
        logger.warning(f"{failed_count} monitoring check(s) failed")
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        logger.exception(f"Critical error in run_all_checks: {e}")
        sys.exit(2)
