#!/usr/bin/env python3
"""Brain evaluation CI script.

This script runs brain evaluation when brain code changes are detected.
It integrates with the CI pipeline to ensure brain versions are evaluated
before promotion.

Usage:
    python brain_eval_ci.py [--force] [--output PATH]

Exit Codes:
    0: Evaluation passed or no brain changes detected
    1: Evaluation failed
    2: Error during evaluation execution
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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Brain code paths that trigger evaluation
BRAIN_PATHS = [
    "src/brain/",
    "src/neuro_symbolic/",
    "src/strategy/",
]

# Evaluation thresholds
EVALUATION_THRESHOLDS = {
    "min_accuracy": 0.80,
    "min_precision": 0.80,
    "min_recall": 0.80,
    "min_f1_score": 0.80,
    "min_paper_carryover_rate": 0.70,
    "max_false_positive_rate": 0.30,
    "min_safety_compliance": 1.0,  # Must be perfect
}


def detect_brain_changes(base_ref: str = "origin/main") -> bool:
    """Detect if brain-related files have changed.

    Args:
        base_ref: Base git reference to compare against

    Returns:
        True if brain files were modified, False otherwise
    """
    try:
        # Get list of changed files
        result = subprocess.run(
            ["git", "diff", "--name-only", base_ref, "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        changed_files = result.stdout.strip().split("\n")

        # Check if any brain paths are in changed files
        for file_path in changed_files:
            for brain_path in BRAIN_PATHS:
                if brain_path in file_path:
                    logger.info(f"Brain change detected: {file_path}")
                    return True

        logger.info("No brain changes detected")
        return False

    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to detect changes: {e}")
        # Fail safe: assume changes if we can't detect
        return True


def run_brain_evaluation(output_path: Path | None = None) -> dict[str, Any]:
    """Run brain evaluation and return results.

    Args:
        output_path: Optional path to save evaluation results

    Returns:
        Dictionary with evaluation results
    """
    try:
        # Import brain evaluation modules
        from brain.batch_evaluator import (
            BatchEvaluator,
            EvaluationPersistence,
            run_batch_evaluation,
        )
        from brain.versioning import VersionManager

        # Get current brain version
        version_manager = VersionManager("_bmad-output/brain/versions")
        current_version = version_manager.current_version

        if current_version is None:
            logger.warning("No brain version initialized, using 'dev'")
            version_str = "dev"
        else:
            version_str = str(current_version)

        logger.info(f"Running evaluation for brain version: {version_str}")

        # Run batch evaluation
        results = run_batch_evaluation(
            [version_str],
            timeout_seconds=300,  # 5 minute timeout per AC requirement
            output_path=output_path,
        )

        if not results:
            return {
                "success": False,
                "error": "No evaluation results returned",
                "version": version_str,
            }

        result = results[0]

        # Check if evaluation passed
        passed = result.status.value == "completed"

        return {
            "success": passed,
            "version": version_str,
            "status": result.status.value,
            "metrics": {
                "accuracy": result.accuracy,
                "precision": result.precision,
                "recall": result.recall,
                "f1_score": result.f1_score,
                "win_rate": result.win_rate,
                "sharpe_ratio": result.sharpe_ratio,
                "max_drawdown": result.max_drawdown,
                "duration_seconds": result.duration_seconds,
            },
            "error_message": result.error_message,
        }

    except Exception as e:
        logger.exception("Brain evaluation failed")
        return {
            "success": False,
            "error": str(e),
            "version": "unknown",
        }


def check_evaluation_gates(evaluation_result: dict[str, Any]) -> bool:
    """Check if evaluation meets promotion gates.

    Args:
        evaluation_result: Result from run_brain_evaluation

    Returns:
        True if evaluation passes all gates
    """
    if not evaluation_result.get("success"):
        logger.error("Evaluation did not complete successfully")
        return False

    metrics = evaluation_result.get("metrics", {})

    # Check each threshold
    gates_passed = True

    if metrics.get("accuracy", 0) < EVALUATION_THRESHOLDS["min_accuracy"]:
        logger.error(
            f"Accuracy gate failed: {metrics.get('accuracy')} < "
            f"{EVALUATION_THRESHOLDS['min_accuracy']}"
        )
        gates_passed = False

    if metrics.get("precision", 0) < EVALUATION_THRESHOLDS["min_precision"]:
        logger.error(
            f"Precision gate failed: {metrics.get('precision')} < "
            f"{EVALUATION_THRESHOLDS['min_precision']}"
        )
        gates_passed = False

    if metrics.get("recall", 0) < EVALUATION_THRESHOLDS["min_recall"]:
        logger.error(
            f"Recall gate failed: {metrics.get('recall')} < "
            f"{EVALUATION_THRESHOLDS['min_recall']}"
        )
        gates_passed = False

    if metrics.get("f1_score", 0) < EVALUATION_THRESHOLDS["min_f1_score"]:
        logger.error(
            f"F1 score gate failed: {metrics.get('f1_score')} < "
            f"{EVALUATION_THRESHOLDS['min_f1_score']}"
        )
        gates_passed = False

    if gates_passed:
        logger.info("All evaluation gates passed")

    return gates_passed


def main() -> int:
    """Main entry point for brain evaluation CI.

    Returns:
        Exit code (0 for success, 1 for failure, 2 for error)
    """
    # Bootstrap environment first
    bootstrap(load_env=True)
    parser = argparse.ArgumentParser(description="Run brain evaluation in CI pipeline")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Run evaluation even if no brain changes detected",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="_bmad-output/ci/brain-eval.json",
        help="Output path for evaluation results",
    )
    parser.add_argument(
        "--base-ref",
        type=str,
        default="origin/main",
        help="Base git reference for change detection",
    )
    parser.add_argument(
        "--skip-gates",
        action="store_true",
        help="Skip promotion gate checks (for testing)",
    )

    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Detect brain changes
    if not args.force and not detect_brain_changes(args.base_ref):
        logger.info("No brain changes detected, skipping evaluation")
        result = {
            "success": True,
            "skipped": True,
            "reason": "No brain changes detected",
        }
        output_path.write_text(json.dumps(result, indent=2))
        return 0

    # Run evaluation
    logger.info("Running brain evaluation...")
    evaluation_result = run_brain_evaluation(output_path)

    # Save results
    output_path.write_text(json.dumps(evaluation_result, indent=2))
    logger.info(f"Evaluation results saved to {output_path}")

    # Check gates unless skipped
    if not args.skip_gates:
        if not check_evaluation_gates(evaluation_result):
            logger.error("Evaluation failed promotion gates")
            return 1

    if evaluation_result.get("success"):
        logger.info("Brain evaluation passed")
        return 0
    else:
        logger.error("Brain evaluation failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
