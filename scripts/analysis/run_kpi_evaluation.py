#!/usr/bin/env python3
"""Unified KPI Evaluation Runner.

Detects trading_mode from environment/config and runs the appropriate KPI calculator:
- If trading_mode in ['demo', 'live']: run Bybit KPI (canonical)
- If trading_mode == 'paper': run journal KPI (canonical for paper only)

Generates both reports with clear labeling for comparison.

Usage:
    python3 scripts/analysis/run_kpi_evaluation.py --days 7
    python3 scripts/analysis/run_kpi_evaluation.py --days 7 --trading-mode demo
    python3 scripts/analysis/run_kpi_evaluation.py --days 7 --run-both

Environment Variables:
    TRADING_MODE - Override trading mode (demo, live, paper)
    BYBIT_API_KEY / BYBIT_API_SECRET - Bybit credentials
    BYBIT_DEMO_API_KEY / BYBIT_DEMO_API_SECRET - Bybit demo credentials
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root))


def detect_trading_mode() -> str:
    """Detect trading mode from environment.

    Returns:
        Trading mode: 'demo', 'live', or 'paper'
    """
    # Check explicit environment variable first
    env_mode = os.getenv("TRADING_MODE", "").lower()
    if env_mode in ["demo", "live", "paper"]:
        return env_mode

    # Check for Bybit demo credentials
    if os.getenv("BYBIT_DEMO_API_KEY") and os.getenv("BYBIT_DEMO_API_SECRET"):
        return "demo"

    # Check for Bybit live credentials
    if os.getenv("BYBIT_API_KEY") and os.getenv("BYBIT_API_SECRET"):
        # Check if it's explicitly marked as demo
        if os.getenv("BYBIT_DEMO_MODE", "").lower() == "true":
            return "demo"
        return "live"

    # Default to paper trading if no API credentials
    return "paper"


def run_paper_kpis(
    days: int,
    output_dir: str,
    story_id: str,
) -> dict[str, Any]:
    """Run paper trading KPI calculator.

    Args:
        days: Number of days to look back
        output_dir: Output directory for reports
        story_id: Story ID for tracking

    Returns:
        Dictionary with result status and paths
    """
    logger.info(f"Running paper trading KPI calculator ({days} days)...")

    script_path = Path(__file__).parent / "calculate_paper_kpis.py"

    cmd = [
        sys.executable,
        str(script_path),
        "--days",
        str(days),
        "--output-dir",
        output_dir,
        "--story-id",
        story_id,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode == 0:
            logger.info("Paper trading KPI calculation completed successfully")
        else:
            logger.warning(
                f"Paper trading KPI calculation returned code {result.returncode}"
            )

        # Find generated files
        output_path = Path(output_dir)
        date_str = datetime.now(UTC).strftime("%Y%m%d")

        json_file = output_path / f"{story_id}-KPI-SNAPSHOT-{date_str}.json"
        md_file = output_path / f"{story_id}-KPI-REPORT-{date_str}.md"

        return {
            "success": result.returncode in [0, 3],  # 3 is warning (stale data)
            "return_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "json_file": str(json_file) if json_file.exists() else None,
            "md_file": str(md_file) if md_file.exists() else None,
            "source": "paper_journal_sim",
            "canonical_for_go": False,
        }

    except subprocess.TimeoutExpired:
        logger.error("Paper trading KPI calculation timed out")
        return {
            "success": False,
            "error": "Timeout",
            "source": "paper_journal_sim",
            "canonical_for_go": False,
        }
    except Exception as e:
        logger.error(f"Paper trading KPI calculation failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "source": "paper_journal_sim",
            "canonical_for_go": False,
        }


def run_bybit_kpis(
    days: int,
    output_dir: str,
    story_id: str,
    trading_mode: str,
) -> dict[str, Any]:
    """Run Bybit truth KPI calculator.

    Args:
        days: Number of days to look back
        output_dir: Output directory for reports
        story_id: Story ID for tracking
        trading_mode: 'demo' or 'live'

    Returns:
        Dictionary with result status and paths
    """
    logger.info(
        f"Running Bybit truth KPI calculator ({trading_mode} mode, {days} days)..."
    )

    script_path = Path(__file__).parent / "calculate_bybit_kpis.py"

    cmd = [
        sys.executable,
        str(script_path),
        "--days",
        str(days),
        "--output-dir",
        output_dir,
        "--story-id",
        story_id,
        "--trading-mode",
        trading_mode,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,  # Longer timeout for API calls
        )

        if result.returncode == 0:
            logger.info("Bybit truth KPI calculation completed successfully")
        else:
            logger.warning(
                f"Bybit truth KPI calculation returned code {result.returncode}"
            )

        # Find generated files
        output_path = Path(output_dir)
        date_str = datetime.now(UTC).strftime("%Y%m%d")

        json_file = output_path / f"{story_id}-BYBIT-TRUTH-KPI-{date_str}.json"
        md_file = output_path / f"{story_id}-BYBIT-TRUTH-REPORT-{date_str}.md"

        return {
            "success": result.returncode in [0, 3],  # 3 is warning (stale data)
            "return_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "json_file": str(json_file) if json_file.exists() else None,
            "md_file": str(md_file) if md_file.exists() else None,
            "source": "bybit_truth",
            "canonical_for_go": True,
            "trading_mode": trading_mode,
        }

    except subprocess.TimeoutExpired:
        logger.error("Bybit truth KPI calculation timed out")
        return {
            "success": False,
            "error": "Timeout",
            "source": "bybit_truth",
            "canonical_for_go": True,
            "trading_mode": trading_mode,
        }
    except Exception as e:
        logger.error(f"Bybit truth KPI calculation failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "source": "bybit_truth",
            "canonical_for_go": True,
            "trading_mode": trading_mode,
        }


def generate_comparison_report(
    results: list[dict[str, Any]],
    output_path: Path,
    story_id: str,
) -> None:
    """Generate a comparison report of all KPI sources.

    Args:
        results: List of result dictionaries from each calculator
        output_path: Path to output file
        story_id: Story ID for tracking
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    datetime.now(UTC).strftime("%Y%m%d")

    report = f"""# Unified KPI Evaluation Report

**Story ID:** {story_id}  
**Generated:** {datetime.now(UTC).isoformat()}

## Summary

This report compares KPI data from multiple sources to provide a complete picture
of trading performance.

| Source | Type | Canonical for GO | Status |
|--------|------|------------------|--------|
"""

    for result in results:
        source = result.get("source", "unknown")
        canonical = "✅ Yes" if result.get("canonical_for_go") else "❌ No"
        status = "✅ Success" if result.get("success") else "❌ Failed"
        source_type = "Bybit API" if source == "bybit_truth" else "Simulation"

        report += f"| `{source}` | {source_type} | {canonical} | {status} |\n"

    report += """
## Source Details

"""

    for result in results:
        source = result.get("source", "unknown")
        report += f"""### {source}

| Attribute | Value |
|-----------|-------|
| Source | `{source}` |
| Canonical for GO Gates | {"✅ Yes" if result.get("canonical_for_go") else "❌ No"} |
| Success | {"✅ Yes" if result.get("success") else "❌ No"} |
"""

        if result.get("trading_mode"):
            report += f"| Trading Mode | `{result['trading_mode']}` |\n"

        if result.get("json_file"):
            report += f"| JSON Output | `{result['json_file']}` |\n"

        if result.get("md_file"):
            report += f"| Markdown Report | `{result['md_file']}` |\n"

        if result.get("error"):
            report += f"| Error | `{result['error']}` |\n"

        report += "\n"

    report += """## GO Gate Decision Guidance

Based on the trading mode, use the following source for GO gate decisions:

"""

    # Find canonical source
    canonical_results = [
        r for r in results if r.get("canonical_for_go") and r.get("success")
    ]

    if canonical_results:
        canonical = canonical_results[0]
        report += f"""### ✅ Canonical Source

**Source:** `{canonical["source"]}`

This is the canonical source for GO gate decisions. Use the data from this source
for all live trading promotion decisions.

**Output Files:**
- JSON: `{canonical.get("json_file", "N/A")}`
- Markdown: `{canonical.get("md_file", "N/A")}`

"""
    else:
        report += """### ⚠️ No Canonical Source Available

No successful canonical source was found. Please check:
1. API credentials are configured correctly
2. Trading mode is set appropriately
3. Network connectivity to Bybit API

"""

    report += """## All Generated Files

| File | Description |
|------|-------------|
"""

    for result in results:
        if result.get("json_file"):
            source = result.get("source", "unknown")
            report += f"| `{result['json_file']}` | {source} KPI data |\n"
        if result.get("md_file"):
            source = result.get("source", "unknown")
            report += f"| `{result['md_file']}` | {source} report |\n"

    report += """

---

*Report generated by scripts/analysis/run_kpi_evaluation.py*
"""

    with open(output_path, "w") as f:
        f.write(report)

    logger.info(f"Comparison report saved to: {output_path}")


# Exit codes
EXIT_SUCCESS = 0
EXIT_NO_DATA = 2
EXIT_STALE_DATA = 3
EXIT_NON_CANONICAL_SOURCE = 5  # Hard guardrail violation


def validate_go_gate_eligibility(
    result: dict[str, Any],
    trading_mode: str,
    enforce_canonical: bool = True,
) -> tuple[bool, str]:
    """Validate that KPI result is eligible for GO gate decisions.

    Args:
        result: KPI result dictionary
        trading_mode: Trading mode ('demo', 'live', 'paper')
        enforce_canonical: If True, raises exception for non-canonical sources

    Returns:
        Tuple of (is_eligible, message)

    Raises:
        SystemExit: If enforce_canonical=True and source is non-canonical
    """
    source = result.get("source", "unknown")
    result.get("canonical_for_go", False)

    # Import validation function
    try:
        sys.path.insert(0, str(project_root / "src"))
        from evaluation.kpi_persistence import (
            NonCanonicalSourceError,
            validate_canonical_source,
        )

        is_valid, reason = validate_canonical_source(
            source, trading_mode, enforce=enforce_canonical
        )

        if not is_valid and trading_mode in ["demo", "live"]:
            warning_msg = (
                f"\n{'=' * 70}\n"
                f"⚠️  NON-CANONICAL SOURCE WARNING\n"
                f"{'=' * 70}\n"
                f"Source: {source}\n"
                f"Trading Mode: {trading_mode}\n"
                f"Issue: {reason}\n"
                f"\n"
                f"GO GATE DECISIONS in demo/live mode MUST use 'bybit_truth' source.\n"
                f"Using '{source}' for GO gates is PROHIBITED.\n"
                f"{'=' * 70}\n"
            )
            logger.warning(warning_msg)
            print(warning_msg, file=sys.stderr)

            if enforce_canonical:
                raise NonCanonicalSourceError(reason)

        return is_valid, reason

    except ImportError:
        # Fallback if validation module not available
        if trading_mode in ["demo", "live"] and source != "bybit_truth":
            msg = f"Source '{source}' is not canonical for {trading_mode} mode"
            if enforce_canonical:
                logger.error(msg)
                sys.exit(EXIT_NON_CANONICAL_SOURCE)
            return False, msg
        return True, "Source is canonical"


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Unified KPI evaluation runner")
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Number of days to look back (default: 7)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="docs/validation/evidence",
        help="Output directory for reports (default: docs/validation/evidence)",
    )
    parser.add_argument(
        "--story-id",
        type=str,
        default="ST-KPI-FIX-001",
        help="Story ID for tracking (default: ST-KPI-FIX-001)",
    )
    parser.add_argument(
        "--trading-mode",
        type=str,
        choices=["demo", "live", "paper", "auto"],
        default="auto",
        help="Trading mode (default: auto-detect)",
    )
    parser.add_argument(
        "--run-both",
        action="store_true",
        help="Run both paper and Bybit KPI calculators for comparison",
    )
    parser.add_argument(
        "--enforce-canonical",
        type=lambda x: x.lower() in ("true", "1", "yes"),
        default=True,
        help="Enforce canonical source for GO gates (default: True for demo/live)",
    )
    parser.add_argument(
        "--skip-go-validation",
        action="store_true",
        help="Skip GO gate source validation (NOT recommended for production)",
    )

    args = parser.parse_args()

    # Determine trading mode
    if args.trading_mode == "auto":
        trading_mode = detect_trading_mode()
        logger.info(f"Auto-detected trading mode: {trading_mode}")
    else:
        trading_mode = args.trading_mode
        logger.info(f"Using specified trading mode: {trading_mode}")

    results = []

    if args.run_both:
        # Run both calculators for comparison
        logger.info("Running both paper and Bybit KPI calculators...")

        # Run paper KPIs
        paper_result = run_paper_kpis(
            days=args.days,
            output_dir=args.output_dir,
            story_id=args.story_id,
        )
        results.append(paper_result)

        # Run Bybit KPIs (if credentials available)
        if trading_mode in ["demo", "live"]:
            bybit_result = run_bybit_kpis(
                days=args.days,
                output_dir=args.output_dir,
                story_id=args.story_id,
                trading_mode=trading_mode,
            )
            results.append(bybit_result)
        else:
            logger.warning("Skipping Bybit KPIs - no API credentials configured")

    else:
        # Run only the appropriate calculator for the trading mode
        if trading_mode == "paper":
            result = run_paper_kpis(
                days=args.days,
                output_dir=args.output_dir,
                story_id=args.story_id,
            )
            results.append(result)
        elif trading_mode in ["demo", "live"]:
            result = run_bybit_kpis(
                days=args.days,
                output_dir=args.output_dir,
                story_id=args.story_id,
                trading_mode=trading_mode,
            )
            results.append(result)
        else:
            logger.error(f"Unknown trading mode: {trading_mode}")
            return 1

    # Generate comparison report if multiple results
    if len(results) > 1:
        output_path = (
            Path(args.output_dir)
            / f"{args.story_id}-KPI-COMPARISON-{datetime.now(UTC).strftime('%Y%m%d')}.md"
        )
        generate_comparison_report(results, output_path, args.story_id)

    # Print summary
    print("\n" + "=" * 60)
    print("UNIFIED KPI EVALUATION SUMMARY")
    print("=" * 60)
    print(f"\nTrading Mode: {trading_mode}")
    print(f"Story ID: {args.story_id}")
    print("\nResults:")

    for result in results:
        source = result.get("source", "unknown")
        canonical = "✅" if result.get("canonical_for_go") else "❌"
        status = "✅" if result.get("success") else "❌"
        print(f"  {source}: canonical={canonical}, success={status}")

        if result.get("json_file"):
            print(f"    JSON: {result['json_file']}")
        if result.get("md_file"):
            print(f"    MD: {result['md_file']}")

    # Find canonical result
    canonical_results = [
        r for r in results if r.get("canonical_for_go") and r.get("success")
    ]
    if canonical_results:
        print(f"\n✅ Canonical source for GO gates: {canonical_results[0]['source']}")
    else:
        print("\n⚠️ No canonical source available")

    print("=" * 60)

    # Validate GO gate eligibility for demo/live modes
    if not args.skip_go_validation and trading_mode in ["demo", "live"]:
        for result in results:
            if result.get("success"):
                try:
                    is_eligible, msg = validate_go_gate_eligibility(
                        result, trading_mode, args.enforce_canonical
                    )
                    if not is_eligible:
                        logger.warning(f"GO gate validation failed: {msg}")
                        if args.enforce_canonical:
                            return EXIT_NON_CANONICAL_SOURCE
                except Exception as e:
                    logger.error(f"GO gate validation error: {e}")
                    if args.enforce_canonical:
                        return EXIT_NON_CANONICAL_SOURCE

    # Return success if at least one calculator succeeded
    if any(r.get("success") for r in results):
        return EXIT_SUCCESS
    else:
        return 1


if __name__ == "__main__":
    sys.exit(main())
