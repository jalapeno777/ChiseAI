"""Fusion strategy selector for adaptive strategy selection."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from src.neuro_symbolic.multimodal.types import ModalityType


class FusionStrategy(Enum):
    """Available fusion strategies for combining signals."""

    WEIGHTED_AVERAGE = "weighted_average"
    CONFIDENCE_WEIGHTED = "confidence_weighted"
    ADAPTIVE = "adaptive"
    ATTENTION_BASED = "attention_based"
    HIERARCHICAL = "hierarchical"
    ENSEMBLE = "ensemble"
    BAYESIAN = "bayesian"
    NEURAL = "neural"


@dataclass
class StrategyPerformance:
    """Performance metrics for a fusion strategy."""

    strategy: FusionStrategy
    accuracy: float = 0.0
    precision: float = 0.0
    recall: float = 0.0
    f1_score: float = 0.0
    calibration_error: float = 0.0
    sample_count: int = 0
    last_used: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy.value,
            "accuracy": self.accuracy,
            "precision": self.precision,
            "recall": self.recall,
            "f1_score": self.f1_score,
            "calibration_error": self.calibration_error,
            "sample_count": self.sample_count,
            "last_used": self.last_used.isoformat() if self.last_used else None,
        }

    @property
    def composite_score(self) -> float:
        """Calculate composite performance score."""
        return (
            0.3 * self.accuracy
            + 0.3 * self.f1_score
            + 0.2 * (1 - self.calibration_error)
            + 0.2 * min(self.sample_count / 100, 1.0)  # Confidence from samples
        )

    def update(self, **kwargs: float) -> None:
        """Update performance metrics."""
        if "accuracy" in kwargs:
            # Exponential moving average update
            alpha = 0.1
            self.accuracy = alpha * kwargs["accuracy"] + (1 - alpha) * self.accuracy
        if "precision" in kwargs:
            self.precision = 0.1 * kwargs["precision"] + 0.9 * self.precision
        if "recall" in kwargs:
            self.recall = 0.1 * kwargs["recall"] + 0.9 * self.recall
        if "f1_score" in kwargs:
            self.f1_score = 0.1 * kwargs["f1_score"] + 0.9 * self.f1_score
        if "calibration_error" in kwargs:
            self.calibration_error = (
                0.1 * kwargs["calibration_error"] + 0.9 * self.calibration_error
            )

        self.sample_count += 1
        self.last_used = datetime.utcnow()


@dataclass
class SelectorConfig:
    """Configuration for the fusion strategy selector."""

    default_strategy: FusionStrategy = FusionStrategy.ADAPTIVE
    min_samples_for_adaptation: int = 50
    performance_window: int = 100
    exploration_rate: float = 0.1
    adaptation_threshold: float = 0.05
    enable_meta_learning: bool = True
    strategy_rotation_interval: int = 1000


class FusionStrategySelector:
    """Selects optimal fusion strategy based on conditions and performance.

    This class implements adaptive strategy selection with:
    - Performance-based selection
    - Exploration/exploitation balance
    - Context-aware adaptation
    - Meta-learning for strategy optimization

    Example:
        >>> selector = FusionStrategySelector()
        >>> strategy = selector.select(modality_coverage, signal_quality)
        >>> print(strategy)
    """

    def __init__(self, config: SelectorConfig | None = None):
        """Initialize the fusion strategy selector.

        Args:
            config: Selector configuration. Uses defaults if not provided.
        """
        self.config = config or SelectorConfig()
        self._strategy_performance: dict[FusionStrategy, StrategyPerformance] = {}
        self._selection_count = 0
        self._last_rotation = 0

        # Initialize performance tracking for all strategies
        for strategy in FusionStrategy:
            self._strategy_performance[strategy] = StrategyPerformance(
                strategy=strategy
            )

    def select(
        self,
        modality_coverage: dict[ModalityType, float],
        signal_quality: float,
        context: dict[str, Any] | None = None,
    ) -> FusionStrategy:
        """Select the best fusion strategy for current conditions.

        Args:
            modality_coverage: Coverage of each modality (0.0 to 1.0).
            signal_quality: Overall signal quality score (0.0 to 1.0).
            context: Additional context for selection.

        Returns:
            Selected FusionStrategy.
        """
        context = context or {}
        self._selection_count += 1

        # Check for exploration (epsilon-greedy)
        import random

        if random.random() < self.config.exploration_rate:
            return self._explore_strategy()

        # Check if we have enough samples for adaptation
        total_samples = sum(p.sample_count for p in self._strategy_performance.values())

        if total_samples < self.config.min_samples_for_adaptation:
            # Use heuristics until we have enough data
            return self._heuristic_selection(modality_coverage, signal_quality, context)

        # Performance-based selection
        return self._performance_based_selection(
            modality_coverage, signal_quality, context
        )

    def update_performance(
        self,
        strategy: FusionStrategy,
        metrics: dict[str, float],
    ) -> None:
        """Update performance metrics for a strategy.

        Args:
            strategy: The strategy to update.
            metrics: Performance metrics to update.
        """
        if strategy in self._strategy_performance:
            self._strategy_performance[strategy].update(**metrics)

    def get_best_strategy(self) -> FusionStrategy:
        """Get the current best performing strategy.

        Returns:
            Best performing FusionStrategy.
        """
        best_strategy = self.config.default_strategy
        best_score = -1.0

        for strategy, perf in self._strategy_performance.items():
            if perf.sample_count >= self.config.min_samples_for_adaptation:
                if perf.composite_score > best_score:
                    best_score = perf.composite_score
                    best_strategy = strategy

        return best_strategy

    def get_strategy_performance(
        self,
        strategy: FusionStrategy,
    ) -> StrategyPerformance | None:
        """Get performance metrics for a specific strategy.

        Args:
            strategy: The strategy to query.

        Returns:
            StrategyPerformance if available, None otherwise.
        """
        return self._strategy_performance.get(strategy)

    def get_all_performance(self) -> dict[FusionStrategy, StrategyPerformance]:
        """Get performance metrics for all strategies.

        Returns:
            Dictionary mapping strategies to their performance.
        """
        return self._strategy_performance.copy()

    def get_statistics(self) -> dict[str, Any]:
        """Get selector statistics.

        Returns:
            Dictionary with selector statistics.
        """
        return {
            "selection_count": self._selection_count,
            "best_strategy": self.get_best_strategy().value,
            "strategy_performance": {
                s.value: p.to_dict() for s, p in self._strategy_performance.items()
            },
            "config": {
                "default_strategy": self.config.default_strategy.value,
                "min_samples_for_adaptation": self.config.min_samples_for_adaptation,
                "exploration_rate": self.config.exploration_rate,
            },
        }

    def reset_performance(self) -> None:
        """Reset all performance metrics."""
        for strategy in FusionStrategy:
            self._strategy_performance[strategy] = StrategyPerformance(
                strategy=strategy
            )
        self._selection_count = 0

    def _explore_strategy(self) -> FusionStrategy:
        """Select a random strategy for exploration."""
        import random

        return random.choice(list(FusionStrategy))

    def _heuristic_selection(
        self,
        modality_coverage: dict[ModalityType, float],
        signal_quality: float,
        context: dict[str, Any],
    ) -> FusionStrategy:
        """Select strategy based on heuristics.

        Rules:
        - Low signal quality -> CONFIDENCE_WEIGHTED
        - High coverage, high quality -> ADAPTIVE
        - Single modality dominant -> WEIGHTED_AVERAGE
        - Multiple modalities balanced -> ENSEMBLE
        """
        # Check signal quality
        if signal_quality < 0.5:
            return FusionStrategy.CONFIDENCE_WEIGHTED

        # Check modality balance
        active_modalities = [m for m, c in modality_coverage.items() if c > 0.1]
        num_active = len(active_modalities)

        if num_active <= 1:
            return FusionStrategy.WEIGHTED_AVERAGE
        elif num_active == 2:
            return FusionStrategy.ADAPTIVE
        elif num_active >= 4:
            return FusionStrategy.ENSEMBLE

        # Check for specific context hints
        if context.get("high_volatility", False):
            return FusionStrategy.HIERARCHICAL
        if context.get("low_confidence", False):
            return FusionStrategy.BAYESIAN

        return self.config.default_strategy

    def _performance_based_selection(
        self,
        modality_coverage: dict[ModalityType, float],
        signal_quality: float,
        context: dict[str, Any],
    ) -> FusionStrategy:
        """Select strategy based on historical performance."""
        # Get context signature
        context_signature = self._get_context_signature(
            modality_coverage, signal_quality
        )

        # Find best performing strategy for similar contexts
        candidates = []

        for strategy, perf in self._strategy_performance.items():
            if perf.sample_count >= self.config.min_samples_for_adaptation:
                # Weight by performance and context similarity
                score = perf.composite_score
                candidates.append((strategy, score))

        # Sort by score
        candidates.sort(key=lambda x: x[1], reverse=True)

        if candidates:
            # Add some randomness to avoid getting stuck
            import random

            if random.random() < 0.2 and len(candidates) > 1:
                return candidates[1][0]
            return candidates[0][0]

        return self.config.default_strategy

    def _get_context_signature(
        self,
        modality_coverage: dict[ModalityType, float],
        signal_quality: float,
    ) -> str:
        """Create a signature for the current context."""
        # Discretize modality coverage
        coverage_bits = []
        for modality in [
            ModalityType.TECHNICAL,
            ModalityType.SENTIMENT,
            ModalityType.ONCHAIN,
        ]:
            coverage_bits.append(
                "1" if modality_coverage.get(modality, 0) > 0.3 else "0"
            )

        # Discretize signal quality
        quality_bucket = int(signal_quality * 10)

        return f"{''.join(coverage_bits)}_q{quality_bucket}"


def select_fusion_strategy(
    modality_coverage: dict[ModalityType, float],
    signal_quality: float,
    config: SelectorConfig | None = None,
) -> FusionStrategy:
    """Convenience function to select a fusion strategy.

    Args:
        modality_coverage: Coverage of each modality.
        signal_quality: Overall signal quality score.
        config: Optional selector configuration.

    Returns:
        Selected FusionStrategy.
    """
    selector = FusionStrategySelector(config=config)
    return selector.select(modality_coverage, signal_quality)
