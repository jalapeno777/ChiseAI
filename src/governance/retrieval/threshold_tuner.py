"""
Threshold Auto-Tuning for Retrieval Systems.

ST-GOV-007: Retrieval Quality Evaluator

This module provides automatic threshold tuning for similarity-based
retrieval systems. It monitors retrieval performance and adjusts
similarity thresholds to optimize metrics like precision and recall.

Features:
- Configurable target metrics
- Automatic threshold adjustment based on performance
- Support for different optimization strategies
- Integration with RetrievalEvaluator

Story: ST-GOV-007
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

# Redis key constants
TUNER_PREFIX = "governance:retrieval:threshold_tuner"
CONFIG_KEY = f"{TUNER_PREFIX}:config"
HISTORY_KEY = f"{TUNER_PREFIX}:history"


class OptimizationGoal(Enum):
    """Optimization goal for threshold tuning."""

    MAXIMIZE_PRECISION = "maximize_precision"
    MAXIMIZE_RECALL = "maximize_recall"
    BALANCE_F1 = "balance_f1"  # Harmonic mean of precision and recall
    MINIMIZE_FALSE_POSITIVES = "minimize_false_positives"


class AdjustmentStrategy(Enum):
    """Strategy for adjusting thresholds."""

    GRADIENT = "gradient"  # Small incremental adjustments
    BINARY_SEARCH = "binary_search"  # Binary search for optimal
    ADAPTIVE = "adaptive"  # Adaptive based on performance trend


@runtime_checkable
class RedisClient(Protocol):
    """Protocol for Redis client interface."""

    def hset(self, name: str, key: str, value: Any) -> int: ...

    def hget(self, name: str, key: str) -> bytes | None: ...

    def set(self, name: str, value: Any, ex: int | None = None) -> bool: ...

    def get(self, name: str) -> bytes | None: ...

    def lpush(self, name: str, *values: Any) -> int: ...

    def lrange(self, name: str, start: int, end: int) -> list[bytes]: ...


@dataclass
class ThresholdConfig:
    """
    Configuration for a similarity threshold.

    Attributes:
        name: Threshold name (e.g., "similarity_cutoff")
        current_value: Current threshold value
        min_value: Minimum allowed value
        max_value: Maximum allowed value
        step_size: Adjustment step size
        target_metric: Metric to optimize
        target_value: Target value for the metric
    """

    name: str
    current_value: float
    min_value: float = 0.0
    max_value: float = 1.0
    step_size: float = 0.05
    target_metric: str = "precision_at_10"
    target_value: float = 0.85

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "current_value": self.current_value,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "step_size": self.step_size,
            "target_metric": self.target_metric,
            "target_value": self.target_value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ThresholdConfig":
        """Create from dictionary."""
        return cls(
            name=data["name"],
            current_value=data["current_value"],
            min_value=data.get("min_value", 0.0),
            max_value=data.get("max_value", 1.0),
            step_size=data.get("step_size", 0.05),
            target_metric=data.get("target_metric", "precision_at_10"),
            target_value=data.get("target_value", 0.85),
        )


@dataclass
class TuningResult:
    """
    Result of a threshold tuning iteration.

    Attributes:
        threshold_name: Name of the tuned threshold
        old_value: Previous threshold value
        new_value: New threshold value
        metric_name: Metric being optimized
        old_metric_value: Metric value before adjustment
        new_metric_value: Metric value after adjustment
        improvement: Whether the adjustment improved the metric
        timestamp: When tuning occurred
    """

    threshold_name: str
    old_value: float
    new_value: float
    metric_name: str
    old_metric_value: float
    new_metric_value: float
    improvement: bool
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "threshold_name": self.threshold_name,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "metric_name": self.metric_name,
            "old_metric_value": self.old_metric_value,
            "new_metric_value": self.new_metric_value,
            "improvement": self.improvement,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TuningResult":
        """Create from dictionary."""
        return cls(
            threshold_name=data["threshold_name"],
            old_value=data["old_value"],
            new_value=data["new_value"],
            metric_name=data["metric_name"],
            old_metric_value=data["old_metric_value"],
            new_metric_value=data["new_metric_value"],
            improvement=data["improvement"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
        )


@dataclass
class TuningHistory:
    """
    History of threshold tuning adjustments.

    Attributes:
        threshold_name: Threshold name
        adjustments: List of tuning results
        best_value: Best known threshold value
        best_metric_value: Best metric value achieved
    """

    threshold_name: str
    adjustments: list[TuningResult] = field(default_factory=list)
    best_value: float | None = None
    best_metric_value: float | None = None

    def add_result(self, result: TuningResult) -> None:
        """Add a tuning result to history."""
        self.adjustments.append(result)

        # Update best if improved
        if (
            self.best_metric_value is None
            or result.new_metric_value > self.best_metric_value
        ):
            self.best_value = result.new_value
            self.best_metric_value = result.new_metric_value

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "threshold_name": self.threshold_name,
            "adjustments": [a.to_dict() for a in self.adjustments],
            "best_value": self.best_value,
            "best_metric_value": self.best_metric_value,
        }


@dataclass
class TunerConfig:
    """
    Configuration for the threshold tuner.

    Attributes:
        optimization_goal: What to optimize
        adjustment_strategy: How to adjust thresholds
        min_sample_size: Minimum samples before tuning
        learning_rate: How aggressively to adjust
        patience: Iterations without improvement before stopping
        convergence_threshold: Minimum change to continue tuning
    """

    optimization_goal: OptimizationGoal = OptimizationGoal.BALANCE_F1
    adjustment_strategy: AdjustmentStrategy = AdjustmentStrategy.GRADIENT
    min_sample_size: int = 100
    learning_rate: float = 0.1
    patience: int = 10
    convergence_threshold: float = 0.001

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "optimization_goal": self.optimization_goal.value,
            "adjustment_strategy": self.adjustment_strategy.value,
            "min_sample_size": self.min_sample_size,
            "learning_rate": self.learning_rate,
            "patience": self.patience,
            "convergence_threshold": self.convergence_threshold,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TunerConfig":
        """Create from dictionary."""
        return cls(
            optimization_goal=OptimizationGoal(
                data.get("optimization_goal", "balance_f1")
            ),
            adjustment_strategy=AdjustmentStrategy(
                data.get("adjustment_strategy", "gradient")
            ),
            min_sample_size=data.get("min_sample_size", 100),
            learning_rate=data.get("learning_rate", 0.1),
            patience=data.get("patience", 10),
            convergence_threshold=data.get("convergence_threshold", 0.001),
        )


class ThresholdTuner:
    """
    Automatic threshold tuner for retrieval systems.

    This class provides:
    - Configurable threshold management
    - Automatic adjustment based on metrics
    - Multiple optimization strategies
    - History tracking for analysis

    Example:
        tuner = ThresholdTuner(redis_client=redis)

        # Register a threshold to tune
        tuner.register_threshold(
            name="similarity_cutoff",
            initial_value=0.7,
            target_metric="precision_at_10",
            target_value=0.85
        )

        # After collecting metrics, tune the threshold
        result = tuner.tune(
            "similarity_cutoff",
            current_metrics={"precision_at_10": 0.78, "recall_at_10": 0.82}
        )

        # Get the tuned value
        new_value = tuner.get_threshold("similarity_cutoff")
    """

    def __init__(
        self,
        redis_client: RedisClient | None = None,
        config: TunerConfig | None = None,
    ):
        """
        Initialize the threshold tuner.

        Args:
            redis_client: Optional Redis client for persistence
            config: Tuner configuration
        """
        self._redis = redis_client
        self._config = config or TunerConfig()

        # In-memory storage
        self._thresholds: dict[str, ThresholdConfig] = {}
        self._history: dict[str, TuningHistory] = {}
        self._iterations_without_improvement: dict[str, int] = {}

    def register_threshold(
        self,
        name: str,
        initial_value: float,
        min_value: float = 0.0,
        max_value: float = 1.0,
        step_size: float = 0.05,
        target_metric: str = "precision_at_10",
        target_value: float = 0.85,
    ) -> None:
        """
        Register a threshold for tuning.

        Args:
            name: Threshold name
            initial_value: Starting value
            min_value: Minimum allowed value
            max_value: Maximum allowed value
            step_size: Adjustment step size
            target_metric: Metric to optimize
            target_value: Target value for the metric
        """
        config = ThresholdConfig(
            name=name,
            current_value=initial_value,
            min_value=min_value,
            max_value=max_value,
            step_size=step_size,
            target_metric=target_metric,
            target_value=target_value,
        )

        self._thresholds[name] = config
        self._history[name] = TuningHistory(threshold_name=name)
        self._iterations_without_improvement[name] = 0

        logger.info(f"Registered threshold '{name}' with initial value {initial_value}")

    def unregister_threshold(self, name: str) -> bool:
        """Unregister a threshold."""
        if name in self._thresholds:
            del self._thresholds[name]
            del self._history[name]
            del self._iterations_without_improvement[name]
            return True
        return False

    def get_threshold(self, name: str) -> float | None:
        """Get current value of a threshold."""
        if name in self._thresholds:
            return self._thresholds[name].current_value
        return None

    def set_threshold(self, name: str, value: float) -> bool:
        """Manually set a threshold value."""
        if name not in self._thresholds:
            return False

        config = self._thresholds[name]
        config.current_value = max(config.min_value, min(config.max_value, value))
        return True

    def get_all_thresholds(self) -> dict[str, float]:
        """Get all threshold values."""
        return {name: config.current_value for name, config in self._thresholds.items()}

    def tune(
        self,
        threshold_name: str,
        current_metrics: dict[str, float],
        sample_size: int = 100,
    ) -> TuningResult | None:
        """
        Perform a tuning iteration for a threshold.

        Args:
            threshold_name: Threshold to tune
            current_metrics: Current metric values
            sample_size: Number of samples used for metrics

        Returns:
            TuningResult if adjustment was made, None otherwise
        """
        if threshold_name not in self._thresholds:
            logger.warning(f"Threshold '{threshold_name}' not registered")
            return None

        if sample_size < self._config.min_sample_size:
            logger.debug(
                f"Not enough samples ({sample_size} < {self._config.min_sample_size})"
            )
            return None

        config = self._thresholds[threshold_name]
        history = self._history[threshold_name]

        target_metric = config.target_metric
        target_value = config.target_value

        if target_metric not in current_metrics:
            logger.warning(f"Target metric '{target_metric}' not in current metrics")
            return None

        current_metric_value = current_metrics[target_metric]
        old_threshold_value = config.current_value

        # Check if we've converged
        if (
            self._iterations_without_improvement[threshold_name]
            >= self._config.patience
        ):
            logger.info(f"Threshold '{threshold_name}' has converged")
            return None

        # Calculate adjustment based on strategy
        new_threshold_value = self._calculate_adjustment(
            config=config,
            current_metric=current_metric_value,
            target_metric=target_value,
            current_metrics=current_metrics,
        )

        # Clamp to bounds
        new_threshold_value = max(
            config.min_value, min(config.max_value, new_threshold_value)
        )

        # Check if adjustment is meaningful
        if (
            abs(new_threshold_value - old_threshold_value)
            < self._config.convergence_threshold
        ):
            self._iterations_without_improvement[threshold_name] += 1
            logger.debug("Adjustment too small, skipping")
            return None

        # Apply the adjustment
        config.current_value = new_threshold_value

        # Create result
        result = TuningResult(
            threshold_name=threshold_name,
            old_value=old_threshold_value,
            new_value=new_threshold_value,
            metric_name=target_metric,
            old_metric_value=current_metric_value,
            new_metric_value=current_metric_value,  # Will be updated next iteration
            improvement=self._is_improvement(
                old_value=current_metric_value,
                new_value=current_metric_value,  # Placeholder
                goal=self._config.optimization_goal,
            ),
        )

        # Update history
        history.add_result(result)
        self._store_result(result)

        logger.info(
            f"Tuned '{threshold_name}': {old_threshold_value:.3f} -> {new_threshold_value:.3f} "
            f"(target: {target_metric}={target_value:.2%}, current: {current_metric_value:.2%})"
        )

        return result

    def tune_all(
        self, current_metrics: dict[str, float], sample_size: int = 100
    ) -> dict[str, TuningResult]:
        """
        Tune all registered thresholds.

        Args:
            current_metrics: Current metric values
            sample_size: Number of samples used for metrics

        Returns:
            Dict of threshold names to tuning results
        """
        results = {}
        for name in self._thresholds:
            result = self.tune(name, current_metrics, sample_size)
            if result:
                results[name] = result
        return results

    def _calculate_adjustment(
        self,
        config: ThresholdConfig,
        current_metric: float,
        target_metric: float,
        current_metrics: dict[str, float],
    ) -> float:
        """
        Calculate threshold adjustment based on strategy.

        Args:
            config: Threshold configuration
            current_metric: Current value of target metric
            target_metric: Target value for metric
            current_metrics: All current metrics

        Returns:
            New threshold value
        """
        current_threshold = config.current_value

        if self._config.adjustment_strategy == AdjustmentStrategy.GRADIENT:
            # Gradient-based: adjust proportionally to error
            error = target_metric - current_metric
            adjustment = error * self._config.learning_rate * config.step_size

            # For precision targets, higher threshold -> higher precision
            # For recall targets, lower threshold -> higher recall
            if "recall" in config.target_metric:
                adjustment = -adjustment

            return current_threshold + adjustment

        elif self._config.adjustment_strategy == AdjustmentStrategy.BINARY_SEARCH:
            # Binary search: narrow down to optimal
            if current_metric < target_metric:
                # Need better precision -> raise threshold
                return current_threshold + config.step_size
            else:
                # Good enough, try lowering for recall
                return current_threshold - config.step_size

        elif self._config.adjustment_strategy == AdjustmentStrategy.ADAPTIVE:
            # Adaptive: adjust based on improvement trend
            history = self._history.get(config.name)
            if history and len(history.adjustments) >= 2:
                last_improvement = history.adjustments[-1].improvement
                if last_improvement:
                    # Continue in same direction
                    direction = (
                        1
                        if history.adjustments[-1].new_value
                        > history.adjustments[-1].old_value
                        else -1
                    )
                else:
                    # Reverse direction
                    direction = (
                        -1
                        if history.adjustments[-1].new_value
                        > history.adjustments[-1].old_value
                        else 1
                    )
                return current_threshold + direction * config.step_size
            else:
                # Default: try raising threshold
                return current_threshold + config.step_size

        return current_threshold

    def _is_improvement(
        self,
        old_value: float,
        new_value: float,
        goal: OptimizationGoal,
    ) -> bool:
        """Check if the metric improved."""
        if goal == OptimizationGoal.MINIMIZE_FALSE_POSITIVES:
            return new_value < old_value
        else:
            return new_value > old_value

    def get_history(self, threshold_name: str) -> TuningHistory | None:
        """Get tuning history for a threshold."""
        return self._history.get(threshold_name)

    def get_best_value(self, threshold_name: str) -> float | None:
        """Get best known value for a threshold."""
        history = self._history.get(threshold_name)
        if history:
            return history.best_value
        return None

    def reset_threshold(self, threshold_name: str) -> bool:
        """Reset a threshold to its best known value."""
        if threshold_name not in self._thresholds:
            return False

        history = self._history.get(threshold_name)
        if history and history.best_value is not None:
            self._thresholds[threshold_name].current_value = history.best_value
            self._iterations_without_improvement[threshold_name] = 0
            logger.info(
                f"Reset '{threshold_name}' to best value {history.best_value:.3f}"
            )
            return True
        return False

    def auto_tune_from_evaluator(
        self, metrics: dict[str, float], sample_size: int = 100
    ) -> dict[str, TuningResult]:
        """
        Auto-tune all thresholds based on evaluator metrics.

        This is a convenience method that maps standard evaluator
        metrics to threshold targets.

        Args:
            metrics: Metrics from RetrievalEvaluator.calculate_metrics()
            sample_size: Number of samples

        Returns:
            Dict of threshold names to tuning results
        """
        # Map evaluator metrics to our expected format
        formatted_metrics = {
            "precision_at_5": metrics.get("precision_at_5", 0),
            "precision_at_10": metrics.get("precision_at_10", 0),
            "recall_at_5": metrics.get("recall_at_5", 0),
            "recall_at_10": metrics.get("recall_at_10", 0),
            "mrr": metrics.get("mrr", 0),
        }

        return self.tune_all(formatted_metrics, sample_size)

    def get_config(self) -> TunerConfig:
        """Get current tuner configuration."""
        return self._config

    def set_config(self, config: TunerConfig) -> None:
        """Set tuner configuration."""
        self._config = config

    def validate(self) -> bool:
        """
        Validate that the tuner is properly configured.

        Returns:
            True if validation passes
        """
        if not self._thresholds:
            logger.warning("No thresholds registered")
            return False

        for name, config in self._thresholds.items():
            if (
                config.current_value < config.min_value
                or config.current_value > config.max_value
            ):
                logger.error(
                    f"Threshold '{name}' value {config.current_value} "
                    f"outside bounds [{config.min_value}, {config.max_value}]"
                )
                return False

        logger.info("Threshold tuner validation passed")
        return True

    def _store_result(self, result: TuningResult) -> None:
        """Store tuning result to Redis."""
        if self._redis is None:
            return

        try:
            key = f"{HISTORY_KEY}:{result.threshold_name}"
            self._redis.lpush(key, json.dumps(result.to_dict()))
        except Exception as e:
            logger.warning(f"Failed to store tuning result to Redis: {e}")
