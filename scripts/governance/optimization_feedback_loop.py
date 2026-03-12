#!/usr/bin/env python3
"""
Week 2 Optimization Feedback Loop Script.

ST-GOV-MINI-002: Week 2 Optimization Feedback Loop

Analyzes Week 1 data to generate optimization recommendations for:
- Retrieval latency improvements
- Memory hit rate optimization
- Deduplication efficiency
- Cadence adherence
- Skill coverage gaps

Usage:
    python scripts/governance/optimization_feedback_loop.py --week=1 [--output-dir PATH]

Output:
    - Stores recommendations in Redis: bmad:chiseai:governance:optimization:recommendations
    - Creates artifact: docs/evidence/ST-GOV-MINI-002/optimization-results.json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.governance.audit.baseline import (
    AuditSnapshot,
    RetrievalBaseline,
    evaluate_metric,
    METRIC_THRESHOLDS,
)
from src.governance.retrieval.evaluator import RetrievalEvaluator
from src.governance.memory.deduplication import MemoryDeduplicationEngine

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR = project_root / "docs" / "evidence" / "ST-GOV-MINI-002"
REDIS_RECOMMENDATIONS_KEY = "bmad:chiseai:governance:optimization:recommendations"


@dataclass
class OptimizationRecommendation:
    """A single optimization recommendation."""

    category: str
    metric: str
    current_value: float
    target_value: float
    priority: str  # "high", "medium", "low"
    action: str
    rationale: str
    estimated_impact: str
    implementation_steps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "metric": self.metric,
            "current_value": self.current_value,
            "target_value": self.target_value,
            "priority": self.priority,
            "action": self.action,
            "rationale": self.rationale,
            "estimated_impact": self.estimated_impact,
            "implementation_steps": self.implementation_steps,
        }


@dataclass
class OptimizationResults:
    """Complete optimization results from Week 1 analysis."""

    metadata: dict[str, Any] = field(default_factory=dict)
    week1_baseline: dict[str, Any] = field(default_factory=dict)
    week1_metrics: dict[str, float] = field(default_factory=dict)
    recommendations: list[OptimizationRecommendation] = field(default_factory=list)
    kpi_improvements: dict[str, dict[str, float]] = field(default_factory=dict)
    execution_time_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "metadata": self.metadata,
            "week1_baseline": self.week1_baseline,
            "week1_metrics": self.week1_metrics,
            "recommendations": [r.to_dict() for r in self.recommendations],
            "kpi_improvements": self.kpi_improvements,
            "execution_time_seconds": self.execution_time_seconds,
        }


def get_redis_client() -> Any | None:
    """Get Redis client if available."""
    try:
        import redis

        client = redis.Redis(
            host=os.getenv("REDIS_HOST", "host.docker.internal"),
            port=int(os.getenv("REDIS_PORT", "6380")),
            db=int(os.getenv("REDIS_DB", "1")),
            decode_responses=True,
        )
        client.ping()
        return client
    except Exception as e:
        logger.warning(f"Redis not available: {e}")
        return None


def get_qdrant_client() -> Any | None:
    """Get Qdrant client if available."""
    try:
        from qdrant_client import QdrantClient

        client = QdrantClient(
            host=os.getenv("QDRANT_HOST", "host.docker.internal"),
            port=int(os.getenv("QDRANT_PORT", "6334")),
        )
        client.get_collections()
        return client
    except Exception as e:
        logger.warning(f"Qdrant not available: {e}")
        return None


def load_week1_baseline(
    audit_dir: Path = Path("docs/governance/audit"),
) -> dict[str, Any]:
    """
    Load Week 1 baseline data from audit files.

    Args:
        audit_dir: Directory containing audit files

    Returns:
        Dictionary with baseline metrics
    """
    baseline = {
        "retrieval_latency_ms": 25.0,
        "memory_hit_rate": 75.0,
        "deduplication_ratio": 0.7,
        "active_ownership_locks": 20,
        "parallel_workers": 3,
    }

    # Try to load week1_snapshot file
    snapshot_files = list(audit_dir.glob("week1_snapshot_*.json"))
    if snapshot_files:
        try:
            with open(snapshot_files[0]) as f:
                data = json.load(f)

            if "governance_metrics" in data:
                gm = data["governance_metrics"]
                baseline["retrieval_latency_ms"] = gm.get("retrieval_latency_ms", 25.0)
                baseline["memory_hit_rate"] = gm.get("memory_hit_rate", 75.0)
                baseline["deduplication_ratio"] = gm.get("deduplication_ratio", 0.7)
                baseline["active_ownership_locks"] = gm.get(
                    "active_ownership_locks", 20
                )
                baseline["parallel_workers"] = gm.get("parallel_workers", 3)

            logger.info(f"Loaded Week 1 baseline from {snapshot_files[0]}")
        except Exception as e:
            logger.warning(f"Failed to load week1_snapshot: {e}, using defaults")

    # Try to load retrieval_baseline file for more detailed metrics
    retrieval_files = list(audit_dir.glob("retrieval_baseline_*.json"))
    if retrieval_files:
        try:
            with open(retrieval_files[0]) as f:
                data = json.load(f)

            if "latency" in data:
                baseline["retrieval_p95_ms"] = data["latency"].get("p95_ms", 25.0)
                baseline["retrieval_mean_ms"] = data["latency"].get("mean_ms", 25.0)

            if "relevance" in data:
                baseline["relevance_mean_score"] = data["relevance"].get(
                    "mean_score", 0.78
                )

            if "top_k_accuracy" in data:
                baseline["precision_at_5"] = data["top_k_accuracy"].get(
                    "k5_precision", 1.0
                )
                baseline["recall_at_10"] = data["top_k_accuracy"].get("k10_recall", 1.0)
                baseline["mrr"] = data["top_k_accuracy"].get("mrr", 1.0)

            if "coverage" in data:
                baseline["coverage_ratio"] = data["coverage"].get("coverage_ratio", 1.0)

            logger.info(f"Loaded retrieval baseline from {retrieval_files[0]}")
        except Exception as e:
            logger.warning(f"Failed to load retrieval_baseline: {e}")

    return baseline


def analyze_retrieval_latency(
    baseline: dict[str, Any],
) -> OptimizationRecommendation | None:
    """
    Analyze retrieval latency and generate recommendations.

    Args:
        baseline: Week 1 baseline metrics

    Returns:
        OptimizationRecommendation if improvement needed, None otherwise
    """
    latency_ms = baseline.get("retrieval_latency_ms", 25.0)
    p95_ms = baseline.get("retrieval_p95_ms", latency_ms)

    rating = evaluate_metric("retrieval_latency_ms", latency_ms)

    if rating in ["excellent", "good"]:
        logger.info(
            f"Retrieval latency is {rating} ({latency_ms:.2f}ms), no action needed"
        )
        return None

    # Generate recommendation based on current performance
    if latency_ms > 100:
        priority = "high"
        target = 50.0
        action = "Implement Redis connection pooling and enable query result caching"
    elif latency_ms > 50:
        priority = "medium"
        target = 25.0
        action = "Optimize Qdrant vector search parameters and add Redis caching layer"
    else:
        priority = "low"
        target = 10.0
        action = "Fine-tune vector index parameters for sub-10ms retrieval"

    return OptimizationRecommendation(
        category="retrieval",
        metric="retrieval_latency_ms",
        current_value=latency_ms,
        target_value=target,
        priority=priority,
        action=action,
        rationale=f"Current p95 latency ({p95_ms:.2f}ms) exceeds acceptable thresholds",
        estimated_impact=f"Reduce latency by {((latency_ms - target) / latency_ms * 100):.1f}%",
        implementation_steps=[
            "Enable Redis connection pooling (max 20 connections)",
            "Implement query result caching with 5-minute TTL",
            "Optimize Qdrant HNSW index parameters (ef=128, m=16)",
            "Add latency monitoring alerts at 50ms threshold",
        ],
    )


def analyze_memory_hit_rate(
    baseline: dict[str, Any],
) -> OptimizationRecommendation | None:
    """
    Analyze memory hit rate and generate recommendations.

    Args:
        baseline: Week 1 baseline metrics

    Returns:
        OptimizationRecommendation if improvement needed, None otherwise
    """
    hit_rate = baseline.get("memory_hit_rate", 75.0)

    rating = evaluate_metric("memory_hit_rate", hit_rate)

    if rating in ["excellent", "good"]:
        logger.info(f"Memory hit rate is {rating} ({hit_rate:.1f}%), no action needed")
        return None

    if hit_rate < 60:
        priority = "high"
        target = 80.0
        action = "Implement aggressive Redis caching strategy with prefetching"
    elif hit_rate < 80:
        priority = "medium"
        target = 85.0
        action = "Increase Redis cache TTL and implement cache warming"
    else:
        priority = "low"
        target = 95.0
        action = "Fine-tune cache eviction policies"

    return OptimizationRecommendation(
        category="memory",
        metric="memory_hit_rate",
        current_value=hit_rate,
        target_value=target,
        priority=priority,
        action=action,
        rationale=f"Current hit rate ({hit_rate:.1f}%) below optimal threshold (80%+)",
        estimated_impact=f"Improve hit rate by {target - hit_rate:.1f} percentage points",
        implementation_steps=[
            "Increase Redis cache TTL from 5 days to 7 days",
            "Implement cache warming for frequently accessed patterns",
            "Add cache hit/miss metrics to monitoring dashboard",
            "Review and optimize cache key patterns for better locality",
        ],
    )


def analyze_deduplication_ratio(
    baseline: dict[str, Any],
) -> OptimizationRecommendation | None:
    """
    Analyze deduplication ratio and generate recommendations.

    Args:
        baseline: Week 1 baseline metrics

    Returns:
        OptimizationRecommendation if improvement needed, None otherwise
    """
    dedup_ratio = baseline.get("deduplication_ratio", 0.7)

    rating = evaluate_metric("deduplication_ratio", dedup_ratio)

    if rating in ["excellent", "good"]:
        logger.info(
            f"Deduplication ratio is {rating} ({dedup_ratio:.2f}), no action needed"
        )
        return None

    if dedup_ratio < 0.5:
        priority = "high"
        target = 0.7
        action = "Enable MemoryDeduplicationEngine with aggressive similarity threshold"
    elif dedup_ratio < 0.7:
        priority = "medium"
        target = 0.8
        action = "Tune deduplication similarity threshold and run full scan"
    else:
        priority = "low"
        target = 0.9
        action = "Optimize deduplication batch processing"

    return OptimizationRecommendation(
        category="storage",
        metric="deduplication_ratio",
        current_value=dedup_ratio,
        target_value=target,
        priority=priority,
        action=action,
        rationale=f"Current dedup ratio ({dedup_ratio:.2f}) indicates {((1 - dedup_ratio) * 100):.1f}% potential duplicates",
        estimated_impact=f"Reduce storage by {((target - dedup_ratio) * 100):.1f}% through deduplication",
        implementation_steps=[
            "Enable feature flag: chise:feature_flags:governance:memory_dedup_enabled",
            "Set similarity threshold to 0.95 for semantic deduplication",
            "Run weekly deduplication sweep during low-traffic periods",
            "Monitor deduplication stats and adjust threshold as needed",
        ],
    )


def analyze_cadence_adherence(
    baseline: dict[str, Any],
) -> OptimizationRecommendation | None:
    """
    Analyze cadence adherence and generate recommendations.

    Args:
        baseline: Week 1 baseline metrics

    Returns:
        OptimizationRecommendation if improvement needed, None otherwise
    """
    # Check for cadence-related metrics in Redis
    parallel_workers = baseline.get("parallel_workers", 3)
    ownership_locks = baseline.get("active_ownership_locks", 20)

    # Calculate worker efficiency
    if parallel_workers == 0:
        efficiency = 0.0
    else:
        efficiency = min(ownership_locks / (parallel_workers * 10), 1.0)

    if efficiency > 0.8:
        logger.info(f"Cadence adherence is good (efficiency: {efficiency:.2f})")
        return None

    return OptimizationRecommendation(
        category="cadence",
        metric="cadence_adherence",
        current_value=efficiency * 100,
        target_value=90.0,
        priority="medium",
        action="Optimize parallel worker scheduling and ownership claim patterns",
        rationale=f"Current worker efficiency ({efficiency * 100:.1f}%) indicates scheduling optimization opportunities",
        estimated_impact="Improve throughput by 15-20% through better parallelization",
        implementation_steps=[
            "Implement dynamic worker pool sizing based on queue depth",
            "Add ownership claim timeouts to prevent stale locks",
            "Optimize story batching to reduce context switching",
            "Add cadence monitoring dashboard with real-time metrics",
        ],
    )


def analyze_skill_coverage(
    baseline: dict[str, Any],
) -> OptimizationRecommendation | None:
    """
    Analyze skill coverage and generate recommendations.

    Args:
        baseline: Week 1 baseline metrics

    Returns:
        OptimizationRecommendation if improvement needed, None otherwise
    """
    # Based on coverage ratio from retrieval baseline
    coverage = baseline.get("coverage_ratio", 1.0)
    relevance = baseline.get("relevance_mean_score", 0.78)

    if coverage >= 0.95 and relevance >= 0.8:
        logger.info(
            f"Skill coverage is adequate (coverage: {coverage:.2f}, relevance: {relevance:.2f})"
        )
        return None

    if coverage < 0.9:
        priority = "high"
        target_coverage = 0.95
        action = "Expand skill library to cover identified gaps"
    else:
        priority = "medium"
        target_coverage = 0.98
        action = "Improve skill documentation and cross-referencing"

    return OptimizationRecommendation(
        category="skills",
        metric="skill_coverage",
        current_value=coverage * 100,
        target_value=target_coverage * 100,
        priority=priority,
        action=action,
        rationale=f"Query coverage ({coverage * 100:.1f}%) and relevance ({relevance:.2f}) indicate skill gaps",
        estimated_impact="Improve agent effectiveness by 10-15% through better skill coverage",
        implementation_steps=[
            "Audit Qdrant for uncovered query patterns",
            "Create missing skills for high-frequency uncovered queries",
            "Improve skill cross-referencing in metadata",
            "Add skill effectiveness metrics to weekly reports",
        ],
    )


def generate_recommendations(
    baseline: dict[str, Any],
) -> list[OptimizationRecommendation]:
    """
    Generate all optimization recommendations based on Week 1 data.

    Args:
        baseline: Week 1 baseline metrics

    Returns:
        List of optimization recommendations
    """
    recommendations = []

    # Analyze each metric category
    analyzers = [
        analyze_retrieval_latency,
        analyze_memory_hit_rate,
        analyze_deduplication_ratio,
        analyze_cadence_adherence,
        analyze_skill_coverage,
    ]

    for analyzer in analyzers:
        try:
            rec = analyzer(baseline)
            if rec:
                recommendations.append(rec)
        except Exception as e:
            logger.warning(f"Analyzer {analyzer.__name__} failed: {e}")

    # Sort by priority
    priority_order = {"high": 0, "medium": 1, "low": 2}
    recommendations.sort(key=lambda r: priority_order.get(r.priority, 3))

    return recommendations


def calculate_kpi_improvements(
    baseline: dict[str, Any], recommendations: list[OptimizationRecommendation]
) -> dict[str, dict[str, float]]:
    """
    Calculate potential KPI improvements from recommendations.

    Args:
        baseline: Week 1 baseline metrics
        recommendations: List of optimization recommendations

    Returns:
        Dictionary of KPI improvements
    """
    improvements = {}

    for rec in recommendations:
        metric = rec.metric
        current = rec.current_value
        target = rec.target_value

        if current > 0:
            if metric == "retrieval_latency_ms":
                # Lower is better
                pct_change = ((current - target) / current) * 100
            else:
                # Higher is better
                pct_change = ((target - current) / current) * 100

            improvements[metric] = {
                "before": current,
                "after": target,
                "improvement_percent": pct_change,
                "priority": rec.priority,
            }

    return improvements


def store_recommendations_in_redis(
    redis_client: Any,
    results: OptimizationResults,
    ttl_seconds: int = 30 * 24 * 60 * 60,  # 30 days
) -> bool:
    """
    Store optimization recommendations in Redis.

    Args:
        redis_client: Redis client instance
        results: Optimization results to store
        ttl_seconds: TTL for Redis entries

    Returns:
        True if successful, False otherwise
    """
    if redis_client is None:
        logger.warning("No Redis client, skipping Redis storage")
        return False

    try:
        timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")

        # Store main recommendations hash
        redis_client.hset(
            REDIS_RECOMMENDATIONS_KEY,
            "timestamp",
            datetime.now(UTC).isoformat(),
        )
        redis_client.hset(
            REDIS_RECOMMENDATIONS_KEY,
            "week",
            results.metadata.get("week", 1),
        )
        redis_client.hset(
            REDIS_RECOMMENDATIONS_KEY,
            "recommendation_count",
            len(results.recommendations),
        )
        redis_client.hset(
            REDIS_RECOMMENDATIONS_KEY,
            "data",
            json.dumps(results.to_dict()),
        )
        redis_client.expire(REDIS_RECOMMENDATIONS_KEY, ttl_seconds)

        # Store individual recommendations as separate entries for easy querying
        for i, rec in enumerate(results.recommendations):
            rec_key = f"{REDIS_RECOMMENDATIONS_KEY}:{timestamp}:{i}"
            redis_client.hset(rec_key, "data", json.dumps(rec.to_dict()))
            redis_client.hset(rec_key, "priority", rec.priority)
            redis_client.hset(rec_key, "category", rec.category)
            redis_client.expire(rec_key, ttl_seconds)

        logger.info(f"Stored {len(results.recommendations)} recommendations in Redis")
        return True

    except Exception as e:
        logger.error(f"Failed to store recommendations in Redis: {e}")
        return False


def save_results_to_file(
    results: OptimizationResults,
    output_dir: Path,
) -> Path:
    """
    Save optimization results to file.

    Args:
        results: Optimization results to save
        output_dir: Directory to save to

    Returns:
        Path to saved file
    """
    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate filename
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    filename = f"optimization-results-week1-{timestamp}.json"
    filepath = output_dir / filename

    # Write file
    with open(filepath, "w") as f:
        json.dump(results.to_dict(), f, indent=2, default=str)

    logger.info(f"Results saved to: {filepath}")
    return filepath


def run_optimization_pipeline(
    week: int = 1,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    redis_client: Any | None = None,
) -> OptimizationResults:
    """
    Run the complete optimization feedback loop.

    Args:
        week: Week number to analyze
        output_dir: Directory for output files
        redis_client: Optional Redis client

    Returns:
        OptimizationResults with all recommendations
    """
    start_time = time.perf_counter()
    results = OptimizationResults()

    # Metadata
    results.metadata = {
        "story_id": "ST-GOV-MINI-002",
        "week": week,
        "execution_time": datetime.now(UTC).isoformat(),
        "agent_version": "1.0.0",
    }

    logger.info(f"Starting Week {week} optimization feedback loop...")

    # 1. Load Week 1 baseline
    logger.info("Loading Week 1 baseline data...")
    results.week1_baseline = load_week1_baseline()
    results.week1_metrics = {
        "retrieval_latency_ms": results.week1_baseline.get(
            "retrieval_latency_ms", 25.0
        ),
        "memory_hit_rate": results.week1_baseline.get("memory_hit_rate", 75.0),
        "deduplication_ratio": results.week1_baseline.get("deduplication_ratio", 0.7),
        "coverage_ratio": results.week1_baseline.get("coverage_ratio", 1.0),
        "mrr": results.week1_baseline.get("mrr", 1.0),
    }

    # 2. Generate recommendations
    logger.info("Generating optimization recommendations...")
    results.recommendations = generate_recommendations(results.week1_baseline)

    # 3. Calculate KPI improvements
    logger.info("Calculating potential KPI improvements...")
    results.kpi_improvements = calculate_kpi_improvements(
        results.week1_baseline, results.recommendations
    )

    # 4. Record execution time
    results.execution_time_seconds = time.perf_counter() - start_time

    logger.info(
        f"Optimization pipeline completed in {results.execution_time_seconds:.2f}s"
    )

    return results


def print_results_summary(results: OptimizationResults) -> None:
    """Print a formatted summary of optimization results."""
    print(f"\n{'=' * 70}")
    print("WEEK 2 OPTIMIZATION FEEDBACK LOOP RESULTS")
    print(f"{'=' * 70}")
    print(f"Story ID: {results.metadata.get('story_id', 'N/A')}")
    print(f"Week: {results.metadata.get('week', 1)}")
    print(f"Execution Time: {results.execution_time_seconds:.2f}s")
    print()

    print("WEEK 1 BASELINE METRICS:")
    for metric, value in results.week1_metrics.items():
        print(f"  {metric}: {value:.2f}")
    print()

    print(f"RECOMMENDATIONS GENERATED: {len(results.recommendations)}")
    print()

    if results.recommendations:
        print("TOP RECOMMENDATIONS:")
        for i, rec in enumerate(results.recommendations[:5], 1):
            print(f"\n  {i}. [{rec.priority.upper()}] {rec.category}")
            print(f"     Metric: {rec.metric}")
            print(
                f"     Current: {rec.current_value:.2f} → Target: {rec.target_value:.2f}"
            )
            print(f"     Action: {rec.action}")
            print(f"     Impact: {rec.estimated_impact}")

    if results.kpi_improvements:
        print("\n" + "-" * 70)
        print("POTENTIAL KPI IMPROVEMENTS:")
        for metric, improvement in results.kpi_improvements.items():
            print(f"  {metric}: {improvement['improvement_percent']:+.1f}%")

    print(f"\n{'=' * 70}\n")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Week 2 Optimization Feedback Loop for ChiseAI Governance"
    )
    parser.add_argument(
        "--week",
        type=int,
        default=1,
        help="Week number to analyze (default: 1)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory for results (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--store-redis",
        action="store_true",
        default=True,
        help="Store recommendations in Redis (default: True)",
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

    # Get Redis client if needed
    redis_client = get_redis_client() if args.store_redis else None

    # Run optimization pipeline
    results = run_optimization_pipeline(
        week=args.week,
        output_dir=args.output_dir,
        redis_client=redis_client,
    )

    # Store in Redis
    if args.store_redis and redis_client:
        store_recommendations_in_redis(redis_client, results)

    # Save to file
    filepath = save_results_to_file(results, args.output_dir)

    # Print summary
    print_results_summary(results)

    # Final status
    print(f"Optimization results saved to: {filepath}")
    if args.store_redis and redis_client:
        print(f"Recommendations stored in Redis key: {REDIS_RECOMMENDATIONS_KEY}")

    # Return success if we have at least one recommendation
    return 0 if len(results.recommendations) > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
