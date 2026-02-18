#!/usr/bin/env python3
"""CLI tool for generating daily paper trading health reports.

Generates paper trading health reports as JSON artifacts and Markdown summaries,
saved to reports/paper/daily/YYYY-MM-DD/ directory.

For PAPER-004: Daily paper trading health/performance reports
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from reporting.daily_generator import DailyReportGenerator
from reporting.models import PaperHealthReport

logger = logging.getLogger(__name__)


DEFAULT_CONFIG = {
    "redis_error_rate_max_pct": 5.0,
    "validation_failure_max_pct": 10.0,
    "data_freshness_max_seconds": 60.0,
}


def load_config(config_path: str | None = None) -> dict[str, Any]:
    """Load configuration from YAML file or use defaults.

    Args:
        config_path: Path to config file (optional)

    Returns:
        Configuration dictionary
    """
    config = DEFAULT_CONFIG.copy()

    if config_path and os.path.exists(config_path):
        try:
            import yaml

            with open(config_path, "r") as f:
                file_config = yaml.safe_load(f)

            if file_config and "paper_health" in file_config:
                config.update(file_config["paper_health"])
                logger.info(f"Loaded config from {config_path}")
        except Exception as e:
            logger.warning(f"Failed to load config from {config_path}: {e}")

    return config


def get_output_dir(base_dir: str, date: datetime) -> Path:
    """Get output directory for a specific date.

    Args:
        base_dir: Base reports directory
        date: Report date

    Returns:
        Path to daily report directory
    """
    date_str = date.strftime("%Y-%m-%d")
    output_dir = Path(base_dir) / "paper" / "daily" / date_str
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def cleanup_old_reports(base_dir: str, retention_days: int) -> int:
    """Remove old reports beyond retention period.

    Args:
        base_dir: Base reports directory
        retention_days: Number of days to retain

    Returns:
        Number of directories removed
    """
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    daily_dir = Path(base_dir) / "paper" / "daily"

    if not daily_dir.exists():
        return 0

    removed = 0
    for date_dir in daily_dir.iterdir():
        if not date_dir.is_dir():
            continue

        try:
            dir_date = datetime.strptime(date_dir.name, "%Y-%m-%d").replace(tzinfo=UTC)
            if dir_date < cutoff:
                import shutil

                shutil.rmtree(date_dir)
                removed += 1
                logger.info(f"Removed old report directory: {date_dir}")
        except ValueError:
            # Invalid directory name format
            continue

    return removed


def get_paper_tracker() -> Any | None:
    """Get PaperTracker instance if available.

    Returns:
        PaperTracker instance or None
    """
    try:
        from portfolio.paper_tracker import PaperTracker

        return PaperTracker()
    except Exception as e:
        logger.warning(f"Could not initialize PaperTracker: {e}")
        return None


async def generate_report(
    date: datetime,
    output_dir: str,
    config: dict[str, Any],
    paper_tracker: Any | None = None,
) -> PaperHealthReport:
    """Generate paper health report.

    Args:
        date: Report date
        output_dir: Output directory
        config: Configuration dictionary
        paper_tracker: PaperTracker instance (optional)

    Returns:
        Generated PaperHealthReport
    """
    generator = DailyReportGenerator()

    thresholds = {
        "redis_error_rate_max_pct": config.get("redis_error_rate_max_pct", 5.0),
        "validation_failure_max_pct": config.get("validation_failure_max_pct", 10.0),
        "data_freshness_max_seconds": config.get("data_freshness_max_seconds", 60.0),
    }

    report = await generator.generate_paper_health_report(
        paper_tracker=paper_tracker,
        date=date,
        thresholds=thresholds,
    )

    return report


def save_report(report: PaperHealthReport, output_dir: Path) -> tuple[Path, Path]:
    """Save report to JSON and Markdown files.

    Args:
        report: Report to save
        output_dir: Output directory

    Returns:
        Tuple of (json_path, markdown_path)
    """
    # Save JSON (handle Infinity values)
    json_path = output_dir / "report.json"
    report_dict = report.to_dict()

    def convert_infinity(obj):
        """Convert Infinity values to string for JSON serialization."""
        if isinstance(obj, float):
            if obj == float("inf"):
                return "Infinity"
            elif obj == float("-inf"):
                return "-Infinity"
        return obj

    # Recursively convert all values
    def deep_convert(d):
        if isinstance(d, dict):
            return {k: deep_convert(v) for k, v in d.items()}
        elif isinstance(d, list):
            return [deep_convert(item) for item in d]
        else:
            return convert_infinity(d)

    with open(json_path, "w") as f:
        json.dump(deep_convert(report_dict), f, indent=2)

    # Save Markdown
    md_path = output_dir / "report.md"
    with open(md_path, "w") as f:
        f.write(report.to_markdown())

    return json_path, md_path


async def main() -> int:
    """Main entry point.

    Returns:
        Exit code: 0 if all health checks pass, 1 otherwise
    """
    parser = argparse.ArgumentParser(
        description="Generate daily paper trading health reports"
    )
    parser.add_argument(
        "--date",
        type=str,
        help="Report date (YYYY-MM-DD format, default: today)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./reports",
        help="Base output directory for reports (default: ./reports)",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to config file (default: config/reporting.yaml)",
    )
    parser.add_argument(
        "--retention-days",
        type=int,
        default=30,
        help="Number of days to retain reports (default: 30)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Parse date
    if args.date:
        try:
            date = datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=UTC)
        except ValueError:
            logger.error(f"Invalid date format: {args.date}. Use YYYY-MM-DD.")
            return 1
    else:
        date = datetime.now(UTC)

    logger.info(f"Generating paper health report for {date.strftime('%Y-%m-%d')}")

    # Load config
    config_path = args.config or "config/reporting.yaml"
    config = load_config(config_path)

    # Get PaperTracker instance
    paper_tracker = get_paper_tracker()

    # Generate report
    try:
        report = await generate_report(
            date=date,
            output_dir=args.output_dir,
            config=config,
            paper_tracker=paper_tracker,
        )
    except Exception as e:
        logger.error(f"Failed to generate report: {e}")
        return 1

    # Create output directory
    daily_dir = get_output_dir(args.output_dir, date)
    logger.info(f"Output directory: {daily_dir}")

    # Save report
    try:
        json_path, md_path = save_report(report, daily_dir)
        logger.info(f"Saved JSON report: {json_path}")
        logger.info(f"Saved Markdown report: {md_path}")
    except Exception as e:
        logger.error(f"Failed to save report: {e}")
        return 1

    # Cleanup old reports
    removed = cleanup_old_reports(args.output_dir, args.retention_days)
    if removed > 0:
        logger.info(f"Cleaned up {removed} old report directories")

    # Summary
    status = report.health_metrics.overall_health
    all_pass = report.health_metrics.all_pass

    logger.info(f"Report status: {status}")
    logger.info(f"All checks pass: {all_pass}")

    if report.warnings:
        logger.warning("Warnings:")
        for warning in report.warnings:
            logger.warning(f"  - {warning}")

    # Exit code: 0 if all pass, 1 if any failures
    return 0 if all_pass else 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        sys.exit(1)
