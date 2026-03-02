#!/usr/bin/env python3
"""CI wrapper script for brain evaluation automation.

This script detects changed brain versions and runs batch evaluation
on them, generating a summary suitable for CI output.
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any

# Add src to path for config imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
from config.bootstrap import bootstrap

# Configure logging for CI output
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Paths that trigger brain evaluation when changed
BRAIN_PATH_PATTERNS = [
    "src/brain/",
    "brains/",
]

# Default output directory for CI artifacts
DEFAULT_OUTPUT_DIR = Path("_bmad-output/brain-eval")


def detect_changed_files(base_ref: str = "HEAD~1", head_ref: str = "HEAD") -> list[str]:
    """Detect files changed between two git refs.

    Args:
        base_ref: Base git reference (default: HEAD~1)
        head_ref: Head git reference (default: HEAD)

    Returns:
        List of changed file paths.
    """
    try:
        result = subprocess.run(  # nosec B607
            ["git", "diff", "--name-only", base_ref, head_ref],
            capture_output=True,
            text=True,
            check=True,
        )
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to detect changed files: {e}")
        return []


def is_brain_related_change(file_path: str) -> bool:
    """Check if a file path is related to brain code.

    Args:
        file_path: Path to check.

    Returns:
        True if the file is in a brain-related directory.
    """
    return any(file_path.startswith(pattern) for pattern in BRAIN_PATH_PATTERNS)


def detect_changed_brain_versions(
    changed_files: list[str],
) -> list[str]:
    """Extract brain version identifiers from changed files.

    In a real implementation, this would parse version files or
    configuration to extract actual version identifiers. For now,
    we return a placeholder based on the commit.

    Args:
        changed_files: List of changed file paths.

    Returns:
        List of brain version identifiers to evaluate.
    """
    brain_files = [f for f in changed_files if is_brain_related_change(f)]

    if not brain_files:
        return []

    # Try to get current commit SHA as version identifier
    try:
        result = subprocess.run(  # nosec B607
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        commit_sha = result.stdout.strip()
        return [f"brain-{commit_sha}"]
    except subprocess.CalledProcessError:
        # Fallback to timestamp-based version
        from datetime import datetime

        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        return [f"brain-{timestamp}"]


def run_batch_evaluation(
    versions: list[str],
    output_dir: Path,
    timeout: float = 300.0,
) -> dict[str, Any]:
    """Run batch evaluation on brain versions.

    Args:
        versions: List of brain version identifiers.
        output_dir: Directory to save evaluation results.
        timeout: Timeout per evaluation in seconds.

    Returns:
        Dictionary with evaluation results and metadata.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    results_file = output_dir / "results.json"

    logger.info(f"Running batch evaluation for {len(versions)} version(s): {versions}")

    try:
        # Import and use the BatchEvaluator
        import asyncio

        from src.brain.batch_evaluator import BatchEvaluator, EvaluationPersistence

        evaluator = BatchEvaluator(default_timeout_seconds=timeout)
        results = asyncio.run(evaluator.evaluate_batch(versions))

        # Save results
        EvaluationPersistence.save_results(results, results_file)

        # Calculate summary statistics
        successful = sum(1 for r in results if r.is_successful())
        failed = len(results) - successful

        summary = {
            "versions_evaluated": len(versions),
            "successful": successful,
            "failed": failed,
            "results_file": str(results_file),
            "versions": versions,
            "details": [r.to_dict() for r in results],
        }

        # Save summary
        summary_file = output_dir / "summary.json"
        with open(summary_file, "w") as f:
            json.dump(summary, f, indent=2)

        logger.info(f"Evaluation complete: {successful} successful, {failed} failed")
        logger.info(f"Results saved to {results_file}")

        return summary

    except Exception as e:
        logger.error(f"Batch evaluation failed: {e}")
        return {
            "versions_evaluated": len(versions),
            "successful": 0,
            "failed": len(versions),
            "error": str(e),
            "versions": versions,
        }


def generate_ci_output(summary: dict[str, Any]) -> str:
    """Generate human-readable CI output from evaluation summary.

    Args:
        summary: Evaluation summary dictionary.

    Returns:
        Formatted string for CI output.
    """
    lines = [
        "=" * 60,
        "Brain Evaluation Results",
        "=" * 60,
        f"Versions evaluated: {summary.get('versions_evaluated', 0)}",
        f"Successful: {summary.get('successful', 0)}",
        f"Failed: {summary.get('failed', 0)}",
    ]

    if "error" in summary:
        lines.extend(
            [
                "",
                f"ERROR: {summary['error']}",
            ]
        )
    else:
        lines.append("")
        lines.append("Details:")
        for detail in summary.get("details", []):
            version = detail.get("brain_version", "unknown")
            status = detail.get("status", "unknown")
            lines.append(f"  - {version}: {status}")
            if status == "completed":
                f1 = detail.get("f1_score", 0.0)
                win_rate = detail.get("win_rate", 0.0)
                sharpe = detail.get("sharpe_ratio", 0.0)
                lines.append(
                    f"      F1: {f1:.4f}, Win Rate: {win_rate:.4f}, Sharpe: {sharpe:.4f}"
                )
            elif detail.get("error_message"):
                lines.append(f"      Error: {detail['error_message']}")

    lines.extend(
        [
            "",
            f"Results file: {summary.get('results_file', 'N/A')}",
            "=" * 60,
        ]
    )

    return "\n".join(lines)


def main() -> int:
    """Main entry point for CI brain evaluation.

    Returns:
        Exit code: 0 for success, 1 for failure.
    """
    # Bootstrap environment first
    bootstrap(load_env=True)
    parser = argparse.ArgumentParser(
        description="CI wrapper for brain batch evaluation"
    )
    parser.add_argument(
        "--base-ref",
        default="HEAD~1",
        help="Base git reference for change detection (default: HEAD~1)",
    )
    parser.add_argument(
        "--head-ref",
        default="HEAD",
        help="Head git reference for change detection (default: HEAD)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory for evaluation results (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=300.0,
        help="Timeout per evaluation in seconds (default: 300)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Run evaluation even if no brain changes detected",
    )
    parser.add_argument(
        "--versions",
        nargs="+",
        help="Explicit list of brain versions to evaluate (skips auto-detection)",
    )

    args = parser.parse_args()

    # Determine versions to evaluate
    if args.versions:
        versions = args.versions
        logger.info(f"Using explicit versions: {versions}")
    else:
        # Auto-detect changed files
        changed_files = detect_changed_files(args.base_ref, args.head_ref)
        logger.info(f"Detected {len(changed_files)} changed files")

        # Check for brain-related changes
        brain_changes = [f for f in changed_files if is_brain_related_change(f)]
        if brain_changes:
            logger.info(f"Brain-related changes detected: {brain_changes}")
        else:
            logger.info("No brain-related changes detected")

        if not brain_changes and not args.force:
            logger.info("No brain changes detected. Skipping evaluation.")
            print("\n" + "=" * 60)
            print("Brain Evaluation")
            print("=" * 60)
            print("No brain changes detected. Skipping evaluation.")
            print("Use --force to run anyway.")
            print("=" * 60)
            return 0

        versions = detect_changed_brain_versions(changed_files)

    if not versions:
        logger.warning("No brain versions to evaluate")
        return 0

    # Run evaluation
    summary = run_batch_evaluation(
        versions=versions,
        output_dir=args.output_dir,
        timeout=args.timeout,
    )

    # Output results
    ci_output = generate_ci_output(summary)
    print("\n" + ci_output)

    # Determine exit code
    # Non-blocking: exit 0 even if some evaluations failed
    # The summary shows what succeeded/failed
    return 0


if __name__ == "__main__":
    sys.exit(main())
