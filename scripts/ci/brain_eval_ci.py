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
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# Add repo and src roots to path for robust imports in CI and local runs.
REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
for path_entry in (str(REPO_ROOT), str(SRC_ROOT)):
    if path_entry not in sys.path:
        sys.path.insert(0, path_entry)

from src.config.bootstrap import bootstrap

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


def create_redis_client() -> Any | None:
    """Create a Redis client if available.

    Returns:
        Redis client if connection successful, None otherwise.
    """
    try:
        import redis as redis_lib

        redis_host = os.getenv("REDIS_HOST", "host.docker.internal")
        redis_port = int(os.getenv("REDIS_PORT", "6380"))
        redis_db = int(os.getenv("REDIS_DB", "0"))
        redis_password = os.getenv("REDIS_PASSWORD", None)

        client = redis_lib.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            password=redis_password,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        client.ping()
        logger.info(f"Redis connected: {redis_host}:{redis_port}")
        return client
    except Exception as e:
        logger.warning(f"Redis not available: {e}")
        return None


def resolve_base_ref(preferred: str = "origin/main") -> str | None:
    """Resolve a git base ref that exists in the current checkout."""
    candidates = [
        preferred,
        "refs/remotes/origin/main",
        "origin/main",
        "main",
        "HEAD~1",
    ]
    for candidate in candidates:
        result = subprocess.run(  # nosec B607
            ["git", "rev-parse", "--verify", candidate],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return candidate
    return None


def detect_brain_changes(base_ref: str = "origin/main") -> bool:
    """Detect if brain-related files have changed.

    Args:
        base_ref: Base git reference to compare against

    Returns:
        True if brain files were modified, False otherwise
    """
    changed_files: list[str] = []

    # Preferred path: diff against base ref.
    try:
        resolved_base = resolve_base_ref(base_ref)
        if resolved_base is None:
            raise subprocess.CalledProcessError(1, ["git", "rev-parse", "--verify"])
        result = subprocess.run(  # nosec B607
            ["git", "diff", "--name-only", resolved_base, "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        changed_files = [f.strip() for f in result.stdout.splitlines() if f.strip()]
    except subprocess.CalledProcessError as e:
        logger.warning(f"Failed to detect changes from {base_ref}: {e}")

    # CI fallback: use Woodpecker-provided changed file list.
    if not changed_files:
        raw = os.getenv("CI_PIPELINE_FILES", "")
        if raw:
            for item in (
                raw.replace("[", "").replace("]", "").replace('"', "").split(",")
            ):
                item = item.strip()
                if item:
                    changed_files.append(item)

    # Local fallback: inspect HEAD commit changed files.
    if not changed_files:
        try:
            result = subprocess.run(  # nosec B607
                ["git", "show", "--name-only", "--pretty=", "HEAD"],
                capture_output=True,
                text=True,
                check=True,
            )
            changed_files = [f.strip() for f in result.stdout.splitlines() if f.strip()]
        except subprocess.CalledProcessError as e:
            logger.warning(f"Failed to read changed files from HEAD: {e}")

    for file_path in changed_files:
        for brain_path in BRAIN_PATHS:
            if brain_path in file_path:
                logger.info(f"Brain change detected: {file_path}")
                return True

    logger.info("No brain changes detected")
    return False


def run_memory_ingestion(
    sources: list[str],
    track_provenance: bool = False,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Run memory-source ingestion before brain evaluation.

    Args:
        sources: List of sources to ingest from (iterlog, tempmemory, redis)
        track_provenance: Whether to track provenance for ingested memories
        dry_run: If True, don't make actual changes

    Returns:
        Dictionary with ingestion results including metrics and provenance
    """
    start_time = time.time()

    # Create Redis client first
    redis_client = create_redis_client()

    # Validate Redis availability if provenance tracking is requested
    if track_provenance and redis_client is None:
        logger.warning(
            "Provenance tracking requested but Redis is not available. "
            "Provenance records will not be persisted."
        )

    try:
        # Import BrainEvalIntegration from governance.tempmemory.brain_integration
        from governance.tempmemory.brain_integration import BrainEvalIntegration
        from governance.tempmemory.provenance import ProvenanceTracker

        # Initialize provenance tracker if requested, with Redis client
        provenance_tracker = None
        if track_provenance:
            provenance_tracker = ProvenanceTracker(
                redis_client=redis_client,
                dry_run=dry_run,
            )

        # Initialize brain evaluators for KPI updates
        brain_evaluator = None
        mini_eval = None
        try:
            from src.evaluation.mini_brain_eval import MiniBrainEval

            from brain.evaluation import BrainEvaluator

            brain_evaluator = BrainEvaluator()
            mini_eval = MiniBrainEval()
            logger.info("Brain evaluators initialized for KPI updates")
        except Exception as e:
            logger.warning(f"Could not initialize brain evaluators: {e}")

        # Initialize BrainEvalIntegration with evaluators and Redis client
        integration = BrainEvalIntegration(
            brain_evaluator=brain_evaluator,
            mini_eval=mini_eval,
            provenance_tracker=provenance_tracker,
            redis_client=redis_client,
            dry_run=dry_run,
        )

        all_metrics = []
        total_processed = 0
        total_ingested = 0
        total_failed = 0

        # Ingest from each requested source
        for source in sources:
            source = source.strip().lower()
            logger.info(f"Ingesting from source: {source}")

            try:
                if source == "iterlog":
                    metrics = integration.ingest_from_iterlog(update_kpis=True)
                elif source == "tempmemory":
                    metrics = integration.ingest_from_tempmemory_files(update_kpis=True)
                elif source == "redis":
                    # Run full migration and ingest from the report
                    from governance.tempmemory.migration import (
                        TempmemoryMigrationEngine,
                    )

                    engine = TempmemoryMigrationEngine(
                        redis_client=redis_client,
                        dry_run=dry_run,
                    )
                    report = engine.run_migration()
                    metrics = integration.ingest_from_migration_report(
                        report, update_kpis=True
                    )
                else:
                    logger.warning(f"Unknown source: {source}")
                    continue

                all_metrics.append(metrics.to_dict())
                total_processed += metrics.items_processed
                total_ingested += metrics.items_ingested
                total_failed += metrics.items_failed

            except Exception as e:
                logger.error(f"Failed to ingest from {source}: {e}")
                total_failed += 1

        duration = time.time() - start_time

        # Build provenance summary if tracking enabled
        provenance_summary = None
        if track_provenance and provenance_tracker:
            try:
                # Generate audit report for provenance summary
                audit_report = provenance_tracker.generate_audit_report()
                by_source = audit_report.get("statistics", {}).get("by_source", {})

                provenance_summary = {
                    "tracked_memories": audit_report.get("statistics", {}).get(
                        "total_records", 0
                    ),
                    "sources": by_source,
                }
            except Exception as e:
                logger.warning(f"Failed to generate provenance summary: {e}")
                provenance_summary = {
                    "tracked_memories": total_ingested,
                    "sources": {},
                }

        return {
            "success": True,
            "sources": sources,
            "metrics": {
                "items_processed": total_processed,
                "items_ingested": total_ingested,
                "items_failed": total_failed,
                "duration_seconds": round(duration, 2),
            },
            "source_metrics": all_metrics,
            "provenance": provenance_summary,
        }

    except ImportError as e:
        logger.error(f"Failed to import BrainEvalIntegration: {e}")
        return {
            "success": False,
            "error": f"Import error: {e}",
            "sources": sources,
            "metrics": {
                "items_processed": 0,
                "items_ingested": 0,
                "items_failed": len(sources),
                "duration_seconds": time.time() - start_time,
            },
        }
    except Exception as e:
        logger.exception("Memory ingestion failed")
        return {
            "success": False,
            "error": str(e),
            "sources": sources,
            "metrics": {
                "items_processed": 0,
                "items_ingested": 0,
                "items_failed": len(sources),
                "duration_seconds": time.time() - start_time,
            },
        }


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
    parser.add_argument(
        "--with-memory-ingestion",
        action="store_true",
        help="Enable memory ingestion before brain evaluation",
    )
    parser.add_argument(
        "--memory-sources",
        type=str,
        default="iterlog,tempmemory,redis",
        help="Comma-separated list of memory sources to ingest (iterlog,tempmemory,redis)",
    )
    parser.add_argument(
        "--track-provenance",
        action="store_true",
        help="Enable provenance tracking for ingested memories",
    )

    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Initialize result structure
    result = {
        "success": True,
        "version": "1.0.0",
        "memory_ingestion": None,
        "brain_evaluation": None,
    }

    # Run memory ingestion if enabled
    if args.with_memory_ingestion:
        logger.info("Memory ingestion enabled, running multi-source ingestion...")
        sources = [s.strip() for s in args.memory_sources.split(",") if s.strip()]
        ingestion_result = run_memory_ingestion(
            sources=sources,
            track_provenance=args.track_provenance,
            dry_run=False,  # In CI, we want actual changes
        )
        result["memory_ingestion"] = ingestion_result

        if not ingestion_result.get("success"):
            logger.warning(
                "Memory ingestion had errors, continuing with brain evaluation"
            )

    # Detect brain changes
    if not args.force and not detect_brain_changes(args.base_ref):
        logger.info("No brain changes detected, skipping evaluation")
        result["brain_evaluation"] = {
            "status": "skipped",
            "reason": "No brain changes detected",
        }
        output_path.write_text(json.dumps(result, indent=2))
        return 0

    # Run evaluation
    logger.info("Running brain evaluation...")
    evaluation_result = run_brain_evaluation(output_path)
    result["brain_evaluation"] = {
        "status": evaluation_result.get("status", "unknown"),
        "metrics": {
            "accuracy": evaluation_result.get("metrics", {}).get("accuracy"),
            "precision": evaluation_result.get("metrics", {}).get("precision"),
            "recall": evaluation_result.get("metrics", {}).get("recall"),
        },
    }

    # Update overall success
    result["success"] = evaluation_result.get("success", False)

    # Save results
    output_path.write_text(json.dumps(result, indent=2))
    logger.info(f"Evaluation results saved to {output_path}")

    # Check gates unless skipped
    if not args.skip_gates and not check_evaluation_gates(evaluation_result):
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
