"""Multi-modal fusion engine for combining signals from multiple sources."""

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from src.neuro_symbolic.fusion.aggregator import (
    AggregatedSignals,
    AggregationConfig,
    SignalAggregator,
)
from src.neuro_symbolic.fusion.strategy_selector import (
    FusionStrategy,
    FusionStrategySelector,
    SelectorConfig,
    StrategyPerformance,
)
from src.neuro_symbolic.multimodal.encoder import (
    EncodedSignal,
    EncoderConfig,
    ModalityEncoder,
)
from src.neuro_symbolic.multimodal.types import (
    FusionWeights,
    ModalityType,
    MultiModalSignal,
    SignalBatch,
    SignalMetadata,
    TemporalContext,
)


@dataclass
class FusionConfig:
    """Configuration for the multi-modal fusion engine."""

    # Encoder settings
    encoder_config: EncoderConfig = field(default_factory=EncoderConfig)

    # Aggregator settings
    aggregation_config: AggregationConfig = field(default_factory=AggregationConfig)

    # Selector settings
    selector_config: SelectorConfig = field(default_factory=SelectorConfig)

    # Fusion settings
    default_strategy: FusionStrategy = FusionStrategy.ADAPTIVE
    confidence_threshold: float = 0.3
    enable_adaptive_weights: bool = True
    enable_temporal_decay: bool = True
    temporal_decay_factor: float = 0.95

    # Output settings
    output_smoothing: float = 0.3
    min_confidence_for_output: float = 0.2


@dataclass
class FusionResult:
    """Result from multi-modal fusion."""

    fused_value: float
    confidence: float
    strategy_used: FusionStrategy
    modality_contributions: dict[ModalityType, float]
    signal_count: int
    alignment_quality: float
    processing_time_ms: float
    timestamp: datetime
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fused_value": self.fused_value,
            "confidence": self.confidence,
            "strategy_used": self.strategy_used.value,
            "modality_contributions": {
                m.value: c for m, c in self.modality_contributions.items()
            },
            "signal_count": self.signal_count,
            "alignment_quality": self.alignment_quality,
            "processing_time_ms": self.processing_time_ms,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    @property
    def direction(self) -> str:
        """Get signal direction."""
        if self.fused_value > 0.1:
            return "bullish"
        elif self.fused_value < -0.1:
            return "bearish"
        return "neutral"


class MultiModalFusionEngine:
    """Fuses signals from multiple modalities into unified predictions.

    This engine combines signals from technical analysis, sentiment analysis,
    on-chain metrics, and other sources using adaptive fusion strategies.

    Features:
    - Multi-source signal fusion
    - Temporal alignment
    - Confidence-weighted aggregation
    - Adaptive strategy selection
    - Performance-based optimization

    Example:
        >>> engine = MultiModalFusionEngine()
        >>> signals = {
        ...     'technical': 0.8,
        ...     'sentiment': 0.6,
        ...     'onchain': 0.7
        ... }
        >>> result = engine.fuse(signals)
        >>> print(result.fused_value)
        >>> print(result.confidence)
    """

    def __init__(self, config: FusionConfig | None = None):
        """Initialize the multi-modal fusion engine.

        Args:
            config: Fusion configuration. Uses defaults if not provided.
        """
        self.config = config or FusionConfig()

        # Initialize components
        self._encoder = ModalityEncoder(config=self.config.encoder_config)
        self._aggregator = SignalAggregator(config=self.config.aggregation_config)
        self._strategy_selector = FusionStrategySelector(
            config=self.config.selector_config
        )

        # State tracking
        self._last_result: FusionResult | None = None
        self._fusion_count = 0
        self._weights = FusionWeights()

        # Performance tracking
        self._performance_history: list[dict[str, Any]] = []

    def fuse(
        self,
        signals: dict[str, float] | list[MultiModalSignal],
        context: dict[str, Any] | None = None,
    ) -> FusionResult:
        """Fuse signals from multiple modalities.

        Args:
            signals: Either a dict mapping modality names to values, or a list
                of MultiModalSignal objects.
            context: Additional context for fusion.

        Returns:
            FusionResult with fused value and confidence.
        """
        start_time = time.perf_counter()
        context = context or {}

        # Convert simple dict to MultiModalSignal list if needed
        if isinstance(signals, dict):
            signals = self._dict_to_signals(signals)

        if not signals:
            return self._empty_result(start_time)

        # Encode signals
        encoded_signals = self._encoder.encode_batch(signals)

        # Aggregate with temporal alignment
        aggregated = self._aggregator.aggregate(signals)

        # Select fusion strategy
        modality_coverage = aggregated.coverage
        signal_quality = aggregated.alignment_quality

        # Use default strategy if explicitly set (non-adaptive), otherwise let selector choose
        if self.config.default_strategy != FusionStrategy.ADAPTIVE:
            strategy = self.config.default_strategy
        else:
            strategy = self._strategy_selector.select(
                modality_coverage,
                signal_quality,
                context,
            )

        # Apply fusion strategy
        fused_value, confidence, contributions = self._apply_strategy(
            encoded_signals,
            aggregated,
            strategy,
        )

        # Apply smoothing with previous result
        if self._last_result and self.config.output_smoothing > 0:
            alpha = self.config.output_smoothing
            fused_value = (
                alpha * fused_value + (1 - alpha) * self._last_result.fused_value
            )

        # Calculate processing time
        processing_time = (time.perf_counter() - start_time) * 1000

        # Build result
        result = FusionResult(
            fused_value=fused_value,
            confidence=confidence,
            strategy_used=strategy,
            modality_contributions=contributions,
            signal_count=len(signals),
            alignment_quality=aggregated.alignment_quality,
            processing_time_ms=processing_time,
            timestamp=datetime.utcnow(),
            metadata={
                "engine_version": "1.0.0",
                "fusion_count": self._fusion_count,
                "aggregated_metadata": aggregated.metadata,
            },
        )

        self._last_result = result
        self._fusion_count += 1

        return result

    def fuse_batch(
        self,
        signal_batches: list[list[MultiModalSignal]],
        context: dict[str, Any] | None = None,
    ) -> list[FusionResult]:
        """Fuse multiple batches of signals.

        Args:
            signal_batches: List of signal batches to fuse.
            context: Additional context for fusion.

        Returns:
            List of FusionResults.
        """
        return [self.fuse(batch, context) for batch in signal_batches]

    def update_strategy_performance(
        self,
        strategy: FusionStrategy,
        metrics: dict[str, float],
    ) -> None:
        """Update performance metrics for a fusion strategy.

        Args:
            strategy: The strategy to update.
            metrics: Performance metrics (accuracy, precision, etc.).
        """
        self._strategy_selector.update_performance(strategy, metrics)

    def set_weights(self, weights: FusionWeights) -> None:
        """Set custom fusion weights.

        Args:
            weights: New fusion weights to use.
        """
        self._weights = weights.normalize()

    def get_weights(self) -> FusionWeights:
        """Get current fusion weights.

        Returns:
            Current FusionWeights.
        """
        return self._weights

    def get_last_result(self) -> FusionResult | None:
        """Get the last fusion result.

        Returns:
            Last FusionResult if available, None otherwise.
        """
        return self._last_result

    def get_statistics(self) -> dict[str, Any]:
        """Get engine statistics.

        Returns:
            Dictionary with engine statistics.
        """
        return {
            "fusion_count": self._fusion_count,
            "encoder_stats": self._encoder.get_statistics(),
            "aggregator_stats": self._aggregator.get_statistics(),
            "selector_stats": self._strategy_selector.get_statistics(),
            "current_weights": self._weights.to_dict(),
            "config": {
                "default_strategy": self.config.default_strategy.value,
                "confidence_threshold": self.config.confidence_threshold,
                "enable_adaptive_weights": self.config.enable_adaptive_weights,
            },
        }

    def reset_state(self) -> None:
        """Reset engine state."""
        self._last_result = None
        self._encoder.reset_statistics()
        self._aggregator.reset_statistics()
        self._strategy_selector.reset_performance()
        self._fusion_count = 0

    def _dict_to_signals(
        self, signals_dict: dict[str, float]
    ) -> list[MultiModalSignal]:
        """Convert simple dict to MultiModalSignal list."""
        signals = []
        now = datetime.utcnow()

        modality_mapping = {
            "technical": ModalityType.TECHNICAL,
            "sentiment": ModalityType.SENTIMENT,
            "onchain": ModalityType.ONCHAIN,
            "on-chain": ModalityType.ONCHAIN,
            "fundamental": ModalityType.FUNDAMENTAL,
            "news": ModalityType.NEWS,
            "social": ModalityType.SOCIAL,
        }

        for key, value in signals_dict.items():
            modality = modality_mapping.get(key.lower())
            if modality is None:
                continue

            signal = MultiModalSignal(
                value=value,
                modality=modality,
                metadata=SignalMetadata(
                    source=f"default_{key}",
                    modality=modality,
                    confidence=0.8,
                ),
                temporal_context=TemporalContext(timestamp=now),
            )
            signals.append(signal)

        return signals

    def _empty_result(self, start_time: float) -> FusionResult:
        """Create an empty fusion result."""
        processing_time = (time.perf_counter() - start_time) * 1000
        return FusionResult(
            fused_value=0.0,
            confidence=0.0,
            strategy_used=self.config.default_strategy,
            modality_contributions={},
            signal_count=0,
            alignment_quality=0.0,
            processing_time_ms=processing_time,
            timestamp=datetime.utcnow(),
            metadata={"reason": "no_signals"},
        )

    def _apply_strategy(
        self,
        encoded_signals: list[EncodedSignal],
        aggregated: AggregatedSignals,
        strategy: FusionStrategy,
    ) -> tuple[float, float, dict[ModalityType, float]]:
        """Apply fusion strategy to encoded signals.

        Returns:
            Tuple of (fused_value, confidence, contributions).
        """
        if not encoded_signals:
            return 0.0, 0.0, {}

        strategy_handlers = {
            FusionStrategy.WEIGHTED_AVERAGE: self._weighted_average_fusion,
            FusionStrategy.CONFIDENCE_WEIGHTED: self._confidence_weighted_fusion,
            FusionStrategy.ADAPTIVE: self._adaptive_fusion,
            FusionStrategy.ATTENTION_BASED: self._attention_based_fusion,
            FusionStrategy.HIERARCHICAL: self._hierarchical_fusion,
            FusionStrategy.ENSEMBLE: self._ensemble_fusion,
            FusionStrategy.BAYESIAN: self._bayesian_fusion,
            FusionStrategy.NEURAL: self._neural_fusion,
        }

        handler = strategy_handlers.get(strategy, self._adaptive_fusion)
        return handler(encoded_signals, aggregated)

    def _weighted_average_fusion(
        self,
        encoded_signals: list[EncodedSignal],
        aggregated: AggregatedSignals,
    ) -> tuple[float, float, dict[ModalityType, float]]:
        """Simple weighted average fusion."""
        contributions: dict[ModalityType, float] = {}
        weighted_sum = 0.0
        total_weight = 0.0

        for signal in encoded_signals:
            weight = self._weights.get_weight(signal.modality)
            contributions[signal.modality] = signal.original_signal.value * weight
            weighted_sum += signal.original_signal.value * weight
            total_weight += weight

        if total_weight == 0:
            return 0.0, 0.0, contributions

        fused_value = weighted_sum / total_weight
        confidence = aggregated.alignment_quality

        return fused_value, confidence, contributions

    def _confidence_weighted_fusion(
        self,
        encoded_signals: list[EncodedSignal],
        aggregated: AggregatedSignals,
    ) -> tuple[float, float, dict[ModalityType, float]]:
        """Confidence-weighted fusion."""
        contributions: dict[ModalityType, float] = {}
        weighted_sum = 0.0
        total_weight = 0.0

        for signal in encoded_signals:
            confidence = signal.original_signal.effective_confidence
            base_weight = self._weights.get_weight(signal.modality)
            weight = confidence * base_weight

            contributions[signal.modality] = signal.original_signal.value * weight
            weighted_sum += signal.original_signal.value * weight
            total_weight += weight

        if total_weight == 0:
            return 0.0, 0.0, contributions

        fused_value = weighted_sum / total_weight
        # Average confidence across modalities
        avg_confidence = sum(
            signal.original_signal.effective_confidence for signal in encoded_signals
        ) / len(encoded_signals)

        return fused_value, avg_confidence, contributions

    def _adaptive_fusion(
        self,
        encoded_signals: list[EncodedSignal],
        aggregated: AggregatedSignals,
    ) -> tuple[float, float, dict[ModalityType, float]]:
        """Adaptive fusion based on modality performance."""
        contributions: dict[ModalityType, float] = {}

        # Get adaptive weights based on coverage and confidence
        adaptive_weights = self._calculate_adaptive_weights(
            encoded_signals,
            aggregated,
        )

        weighted_sum = 0.0
        total_weight = 0.0

        for signal in encoded_signals:
            weight = adaptive_weights.get(signal.modality, 0.0)
            contributions[signal.modality] = signal.original_signal.value * weight
            weighted_sum += signal.original_signal.value * weight
            total_weight += weight

        if total_weight == 0:
            return 0.0, 0.0, contributions

        fused_value = weighted_sum / total_weight

        # Confidence based on weight distribution
        confidence = self._calculate_fusion_confidence(
            adaptive_weights,
            aggregated.confidence_scores,
        )

        return fused_value, confidence, contributions

    def _attention_based_fusion(
        self,
        encoded_signals: list[EncodedSignal],
        aggregated: AggregatedSignals,
    ) -> tuple[float, float, dict[ModalityType, float]]:
        """Attention-based fusion using encoded attention weights."""
        contributions: dict[ModalityType, float] = {}

        # Calculate attention-weighted value for each modality
        modality_attention: dict[ModalityType, float] = {}
        modality_value: dict[ModalityType, float] = {}

        for signal in encoded_signals:
            # Average attention across dimensions
            avg_attention = sum(signal.attention_weights) / len(
                signal.attention_weights
            )
            modality_attention[signal.modality] = avg_attention
            modality_value[signal.modality] = signal.original_signal.value

        # Normalize attention
        total_attention = sum(modality_attention.values())
        if total_attention > 0:
            for modality in modality_attention:
                modality_attention[modality] /= total_attention

        # Calculate fused value
        fused_value = 0.0
        for modality, value in modality_value.items():
            attention = modality_attention.get(modality, 0.0)
            contributions[modality] = value * attention
            fused_value += value * attention

        confidence = (
            sum(modality_attention.values()) / len(modality_attention)
            if modality_attention
            else 0.0
        )

        return fused_value, confidence, contributions

    def _hierarchical_fusion(
        self,
        encoded_signals: list[EncodedSignal],
        aggregated: AggregatedSignals,
    ) -> tuple[float, float, dict[ModalityType, float]]:
        """Hierarchical fusion with priority levels."""
        contributions: dict[ModalityType, float] = {}

        # Define hierarchy levels
        hierarchy = [
            [ModalityType.TECHNICAL],  # Level 1: Primary
            [ModalityType.SENTIMENT, ModalityType.ONCHAIN],  # Level 2: Secondary
            [
                ModalityType.FUNDAMENTAL,
                ModalityType.NEWS,
                ModalityType.SOCIAL,
            ],  # Level 3: Tertiary
        ]
        level_weights = [0.5, 0.35, 0.15]

        modality_values: dict[ModalityType, float] = {}
        modality_confidence: dict[ModalityType, float] = {}

        for signal in encoded_signals:
            modality_values[signal.modality] = signal.original_signal.value
            modality_confidence[signal.modality] = (
                signal.original_signal.effective_confidence
            )

        fused_value = 0.0
        total_contributions = 0.0

        for level, modalities in enumerate(hierarchy):
            level_weight = level_weights[level] if level < len(level_weights) else 0.1
            level_values = [
                modality_values.get(m, 0.0) for m in modalities if m in modality_values
            ]

            if level_values:
                level_avg = sum(level_values) / len(level_values)
                contribution = level_avg * level_weight
                fused_value += contribution

                for m in modalities:
                    if m in modality_values:
                        contributions[m] = modality_values[m] * level_weight
                        total_contributions += level_weight

        # Normalize contributions
        if total_contributions > 0:
            for m in contributions:
                contributions[m] /= total_contributions

        confidence = aggregated.alignment_quality

        return fused_value, confidence, contributions

    def _ensemble_fusion(
        self,
        encoded_signals: list[EncodedSignal],
        aggregated: AggregatedSignals,
    ) -> tuple[float, float, dict[ModalityType, float]]:
        """Ensemble fusion combining multiple strategies."""
        # Get results from different strategies
        strategies = [
            self._weighted_average_fusion,
            self._confidence_weighted_fusion,
            self._adaptive_fusion,
        ]

        results = [strategy(encoded_signals, aggregated) for strategy in strategies]

        # Average the results
        fused_value = sum(r[0] for r in results) / len(results)
        confidence = sum(r[1] for r in results) / len(results)

        # Combine contributions
        contributions: dict[ModalityType, float] = {}
        for _, _, contrib in results:
            for modality, value in contrib.items():
                contributions[modality] = contributions.get(
                    modality, 0.0
                ) + value / len(results)

        return fused_value, confidence, contributions

    def _bayesian_fusion(
        self,
        encoded_signals: list[EncodedSignal],
        aggregated: AggregatedSignals,
    ) -> tuple[float, float, dict[ModalityType, float]]:
        """Bayesian-style fusion treating signals as priors."""
        contributions: dict[ModalityType, float] = {}

        # Use confidence as precision (inverse variance)
        prior_mean = 0.0
        prior_precision = 1.0

        posterior_mean = prior_mean
        posterior_precision = prior_precision

        for signal in encoded_signals:
            value = signal.original_signal.value
            confidence = signal.original_signal.effective_confidence

            # Treat confidence as precision
            likelihood_precision = confidence * 10 + 0.1

            # Bayesian update
            new_precision = posterior_precision + likelihood_precision
            new_mean = (
                posterior_precision * posterior_mean + likelihood_precision * value
            ) / new_precision

            contributions[signal.modality] = (
                (value - posterior_mean) * likelihood_precision / new_precision
            )

            posterior_mean = new_mean
            posterior_precision = new_precision

        fused_value = posterior_mean
        confidence = min(posterior_precision / (len(encoded_signals) * 5 + 1), 1.0)

        return fused_value, confidence, contributions

    def _neural_fusion(
        self,
        encoded_signals: list[EncodedSignal],
        aggregated: AggregatedSignals,
    ) -> tuple[float, float, dict[ModalityType, float]]:
        """Simulated neural-style fusion using encoded vectors."""
        contributions: dict[ModalityType, float] = {}

        if not encoded_signals:
            return 0.0, 0.0, contributions

        # Concatenate encoded vectors (simulating neural processing)
        all_vectors = []
        all_attention = []

        for signal in encoded_signals:
            all_vectors.extend(signal.encoded_vector[:16])  # Use first 16 dims
            all_attention.extend(signal.attention_weights[:16])

        if not all_vectors:
            return self._adaptive_fusion(encoded_signals, aggregated)

        # Simulated neural activation
        import math

        activation = sum(
            v * a for v, a in zip(all_vectors, all_attention[: len(all_vectors)])
        )
        activation = math.tanh(
            activation / len(all_vectors) * 5
        )  # Normalize and activate

        fused_value = activation

        # Calculate contributions based on attention
        total_attention = sum(all_attention)
        if total_attention > 0:
            idx = 0
            for signal in encoded_signals:
                modality_attention = sum(signal.attention_weights[:16]) / 16
                contributions[signal.modality] = (
                    modality_attention / total_attention * abs(fused_value)
                )
                idx += 16

        confidence = abs(activation) * aggregated.alignment_quality

        return fused_value, confidence, contributions

    def _calculate_adaptive_weights(
        self,
        encoded_signals: list[EncodedSignal],
        aggregated: AggregatedSignals,
    ) -> dict[ModalityType, float]:
        """Calculate adaptive weights based on signal quality."""
        adaptive_weights = {}

        for signal in encoded_signals:
            base_weight = self._weights.get_weight(signal.modality)
            confidence = signal.original_signal.effective_confidence
            coverage = aggregated.coverage.get(signal.modality, 0.0)

            # Adaptive weight combines base weight, confidence, and coverage
            adaptive_weights[signal.modality] = (
                base_weight * confidence * (0.5 + 0.5 * coverage)
            )

        # Normalize
        total = sum(adaptive_weights.values())
        if total > 0:
            for modality in adaptive_weights:
                adaptive_weights[modality] /= total

        return adaptive_weights

    def _calculate_fusion_confidence(
        self,
        weights: dict[ModalityType, float],
        confidence_scores: dict[ModalityType, float],
    ) -> float:
        """Calculate overall fusion confidence."""
        if not weights or not confidence_scores:
            return 0.0

        # Weight confidence by modality importance
        weighted_confidence = 0.0
        total_weight = 0.0

        for modality, weight in weights.items():
            conf = confidence_scores.get(modality, 0.0)
            weighted_confidence += weight * conf
            total_weight += weight

        if total_weight == 0:
            return 0.0

        return weighted_confidence / total_weight


# Convenience function
def fuse_signals(
    signals: dict[str, float] | list[MultiModalSignal],
    config: FusionConfig | None = None,
) -> FusionResult:
    """Convenience function to fuse signals.

    Args:
        signals: Signals to fuse (dict or list of MultiModalSignal).
        config: Optional fusion configuration.

    Returns:
        FusionResult with fused value and confidence.
    """
    engine = MultiModalFusionEngine(config=config)
    return engine.fuse(signals)
