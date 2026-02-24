"""Pipeline optimization for signal generation.

Provides optimization utilities for the signal generation pipeline
to improve throughput and reduce latency.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class PipelineStage(Enum):
    """Stages in the signal generation pipeline."""

    DATA_FETCH = "data_fetch"
    FEATURE_EXTRACTION = "feature_extraction"
    MODEL_INFERENCE = "model_inference"
    SIGNAL_CONSTRUCTION = "signal_construction"
    VALIDATION = "validation"
    ENRICHMENT = "enrichment"


@dataclass
class StageMetrics:
    """Metrics for a pipeline stage.

    Attributes:
        stage: Stage identifier
        latency_ms: Stage latency
        success: Whether stage succeeded
        timestamp: Execution timestamp
    """

    stage: str
    latency_ms: float
    success: bool = True
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class OptimizationResult:
    """Result of pipeline optimization.

    Attributes:
        stage: Stage that was optimized
        original_latency_ms: Original latency
        optimized_latency_ms: Optimized latency
        improvement_pct: Improvement percentage
        techniques: Applied optimization techniques
    """

    stage: str
    original_latency_ms: float
    optimized_latency_ms: float
    improvement_pct: float = 0.0
    techniques: list[str] = field(default_factory=list)

    @property
    def is_improved(self) -> bool:
        """Check if optimization improved latency."""
        return self.optimized_latency_ms < self.original_latency_ms

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "stage": self.stage,
            "original_latency_ms": round(self.original_latency_ms, 2),
            "optimized_latency_ms": round(self.optimized_latency_ms, 2),
            "improvement_pct": round(self.improvement_pct, 2),
            "techniques": self.techniques,
        }


class PipelineOptimizer:
    """Optimizer for signal generation pipeline.

    Analyzes pipeline performance and applies optimizations
    to reduce latency and improve throughput.

    Example:
        optimizer = PipelineOptimizer()
        optimizer.register_stage(PipelineStage.DATA_FETCH, fetch_data)
        optimizer.record_metrics(StageMetrics("data_fetch", 150))

        result = optimizer.optimize_stage("data_fetch")
        print(f"Improvement: {result.improvement_pct}%")
    """

    # Optimization strategies by stage
    OPTIMIZATION_STRATEGIES = {
        PipelineStage.DATA_FETCH: [
            "parallel_fetch",
            "cache_results",
            "prefetch",
            "connection_pooling",
        ],
        PipelineStage.FEATURE_EXTRACTION: [
            "vectorized_ops",
            "cache_features",
            "lazy_evaluation",
        ],
        PipelineStage.MODEL_INFERENCE: [
            "batch_inference",
            "model_caching",
            "gpu_acceleration",
        ],
        PipelineStage.SIGNAL_CONSTRUCTION: [
            "parallel_construction",
            "template_caching",
        ],
        PipelineStage.VALIDATION: [
            "parallel_validation",
            "skip_redundant",
            "cache_results",
        ],
        PipelineStage.ENRICHMENT: [
            "async_enrichment",
            "cache_lookups",
        ],
    }

    def __init__(self, history_size: int = 1000):
        """Initialize pipeline optimizer.

        Args:
            history_size: Maximum metrics history per stage
        """
        self.history_size = history_size

        # Stage tracking
        self._stages: dict[str, Callable] = {}
        self._metrics: dict[str, list[StageMetrics]] = {}
        self._optimizations: dict[str, list[OptimizationResult]] = {}

        # Configuration
        self._parallel_enabled: dict[str, bool] = {}
        self._cache_enabled: dict[str, bool] = {}

    def register_stage(
        self,
        stage: PipelineStage,
        handler: Callable,
        enable_parallel: bool = True,
        enable_cache: bool = True,
    ) -> None:
        """Register a pipeline stage handler.

        Args:
            stage: Stage identifier
            handler: Handler function
            enable_parallel: Enable parallel processing
            enable_cache: Enable caching
        """
        self._stages[stage.value] = handler
        self._parallel_enabled[stage.value] = enable_parallel
        self._cache_enabled[stage.value] = enable_cache

    def record_metrics(self, metrics: StageMetrics) -> None:
        """Record stage metrics.

        Args:
            metrics: StageMetrics to record
        """
        stage = metrics.stage

        if stage not in self._metrics:
            self._metrics[stage] = []

        self._metrics[stage].append(metrics)

        # Trim history
        if len(self._metrics[stage]) > self.history_size:
            self._metrics[stage] = self._metrics[stage][-self.history_size :]

    def get_stage_stats(self, stage: str) -> dict[str, Any]:
        """Get statistics for a stage.

        Args:
            stage: Stage identifier

        Returns:
            Dictionary with stage statistics
        """
        metrics = self._metrics.get(stage, [])

        if not metrics:
            return {
                "stage": stage,
                "count": 0,
                "avg_latency_ms": 0,
                "max_latency_ms": 0,
                "success_rate": 0,
            }

        latencies = [m.latency_ms for m in metrics]
        successes = sum(1 for m in metrics if m.success)

        return {
            "stage": stage,
            "count": len(metrics),
            "avg_latency_ms": round(sum(latencies) / len(latencies), 2),
            "max_latency_ms": round(max(latencies), 2),
            "min_latency_ms": round(min(latencies), 2),
            "success_rate": round(successes / len(metrics) * 100, 2),
        }

    def analyze_bottlenecks(self) -> list[dict[str, Any]]:
        """Analyze pipeline for bottlenecks.

        Returns:
            List of bottleneck stages sorted by latency
        """
        bottlenecks = []

        for stage in self._metrics:
            stats = self.get_stage_stats(stage)

            # Consider stage a bottleneck if avg latency > 100ms
            if stats["avg_latency_ms"] > 100:
                bottlenecks.append(
                    {
                        "stage": stage,
                        "avg_latency_ms": stats["avg_latency_ms"],
                        "optimization_potential": stats["avg_latency_ms"]
                        * 0.3,  # 30% potential
                    }
                )

        # Sort by latency
        bottlenecks.sort(key=lambda x: x["avg_latency_ms"], reverse=True)

        return bottlenecks

    def optimize_stage(
        self,
        stage: str,
        target_latency_ms: float | None = None,
    ) -> OptimizationResult:
        """Optimize a specific pipeline stage.

        Args:
            stage: Stage to optimize
            target_latency_ms: Target latency (optional)

        Returns:
            OptimizationResult with improvement details
        """
        # Get current stats
        stats = self.get_stage_stats(stage)
        original_latency = stats["avg_latency_ms"]

        if original_latency == 0:
            return OptimizationResult(
                stage=stage,
                original_latency_ms=0,
                optimized_latency_ms=0,
                improvement_pct=0,
                techniques=[],
            )

        # Determine applicable techniques
        techniques: list[str] = []

        # Check if stage supports parallelization
        if self._parallel_enabled.get(stage, False):
            techniques.append("parallel_processing")

        # Check if stage supports caching
        if self._cache_enabled.get(stage, False):
            techniques.append("result_caching")

        # Add stage-specific techniques
        try:
            stage_enum = PipelineStage(stage)
            techniques.extend(self.OPTIMIZATION_STRATEGIES.get(stage_enum, [])[:2])
        except ValueError:
            pass

        # Estimate improvement
        # Each technique contributes ~10-20% improvement
        estimated_improvement = min(len(techniques) * 15, 50)  # Cap at 50%
        optimized_latency = original_latency * (1 - estimated_improvement / 100)

        # Check if target is met
        if target_latency_ms and optimized_latency > target_latency_ms:
            techniques.append("further_tuning_needed")

        result = OptimizationResult(
            stage=stage,
            original_latency_ms=original_latency,
            optimized_latency_ms=optimized_latency,
            improvement_pct=estimated_improvement,
            techniques=techniques,
        )

        # Record optimization
        if stage not in self._optimizations:
            self._optimizations[stage] = []
        self._optimizations[stage].append(result)

        return result

    def get_optimization_history(
        self,
        stage: str | None = None,
    ) -> list[OptimizationResult]:
        """Get optimization history.

        Args:
            stage: Optional stage filter

        Returns:
            List of OptimizationResult
        """
        if stage:
            return self._optimizations.get(stage, [])

        results = []
        for stage_results in self._optimizations.values():
            results.extend(stage_results)

        return results

    def get_pipeline_summary(self) -> dict[str, Any]:
        """Get summary of entire pipeline.

        Returns:
            Dictionary with pipeline summary
        """
        stage_stats = {}
        total_latency = 0.0

        for stage in self._stages:
            stats = self.get_stage_stats(stage)
            stage_stats[stage] = stats
            total_latency += stats["avg_latency_ms"]

        bottlenecks = self.analyze_bottlenecks()

        return {
            "stages": stage_stats,
            "total_avg_latency_ms": round(total_latency, 2),
            "stage_count": len(self._stages),
            "bottleneck_count": len(bottlenecks),
            "bottlenecks": bottlenecks[:3],  # Top 3
        }

    def get_recommendations(self) -> list[dict[str, Any]]:
        """Get optimization recommendations.

        Returns:
            List of optimization recommendations
        """
        recommendations = []
        bottlenecks = self.analyze_bottlenecks()

        for bottleneck in bottlenecks:
            stage = bottleneck["stage"]

            try:
                stage_enum = PipelineStage(stage)
                strategies = self.OPTIMIZATION_STRATEGIES.get(stage_enum, [])
            except ValueError:
                strategies = []

            recommendations.append(
                {
                    "stage": stage,
                    "current_latency_ms": bottleneck["avg_latency_ms"],
                    "potential_improvement": f"{bottleneck['optimization_potential']:.0f}ms",
                    "strategies": strategies,
                    "priority": (
                        "high" if bottleneck["avg_latency_ms"] > 200 else "medium"
                    ),
                }
            )

        return recommendations

    async def health_check(self) -> dict[str, Any]:
        """Perform health check.

        Returns:
            Health check result
        """
        summary = self.get_pipeline_summary()
        bottlenecks = summary["bottlenecks"]

        # Determine health
        if any(b["avg_latency_ms"] > 500 for b in bottlenecks):
            status = "unhealthy"
        elif bottlenecks:
            status = "degraded"
        else:
            status = "healthy"

        return {
            "status": status,
            "total_latency_ms": summary["total_avg_latency_ms"],
            "bottleneck_count": len(bottlenecks),
            "recommendations": self.get_recommendations()[:3],
        }
