"""Signal aggregator for temporal alignment and confidence weighting."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from src.neuro_symbolic.multimodal.types import (
    ModalityType,
    MultiModalSignal,
    SignalBatch,
    TemporalContext,
)


@dataclass
class AggregationConfig:
    """Configuration for signal aggregation."""

    alignment_window_ms: int = 60000  # 1 minute
    max_staleness_ms: int = 300000  # 5 minutes
    min_signals_per_modality: int = 1
    confidence_threshold: float = 0.3
    weight_by_confidence: bool = True
    weight_by_reliability: bool = True
    weight_by_staleness: bool = True
    alignment_strategy: str = "nearest"  # nearest, interpolate, latest


@dataclass
class AggregatedSignals:
    """Result of signal aggregation."""

    signals: list[MultiModalSignal]
    aligned_timestamp: datetime
    alignment_quality: float
    modality_weights: dict[ModalityType, float]
    confidence_scores: dict[ModalityType, float]
    coverage: dict[ModalityType, float]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_count": len(self.signals),
            "aligned_timestamp": self.aligned_timestamp.isoformat(),
            "alignment_quality": self.alignment_quality,
            "modality_weights": {m.value: w for m, w in self.modality_weights.items()},
            "confidence_scores": {
                m.value: c for m, c in self.confidence_scores.items()
            },
            "coverage": {m.value: c for m, c in self.coverage.items()},
            "metadata": self.metadata,
        }

    def get_weighted_value(self) -> float:
        """Calculate weighted average signal value."""
        if not self.signals:
            return 0.0

        total_weight = 0.0
        weighted_sum = 0.0

        for signal in self.signals:
            weight = self.modality_weights.get(signal.modality, 0.0)
            confidence = self.confidence_scores.get(signal.modality, 0.0)
            effective_weight = weight * confidence
            weighted_sum += signal.value * effective_weight
            total_weight += effective_weight

        if total_weight == 0:
            return 0.0

        return weighted_sum / total_weight


class SignalAggregator:
    """Aggregates signals across modalities with temporal alignment.

    This class handles:
    - Temporal alignment of signals from different sources
    - Confidence-weighted aggregation
    - Modality coverage tracking
    - Signal quality assessment

    Example:
        >>> aggregator = SignalAggregator()
        >>> signals = [signal1, signal2, signal3]
        >>> aggregated = aggregator.aggregate(signals)
        >>> print(aggregated.alignment_quality)
    """

    def __init__(self, config: AggregationConfig | None = None):
        """Initialize the signal aggregator.

        Args:
            config: Aggregation configuration. Uses defaults if not provided.
        """
        self.config = config or AggregationConfig()
        self._aggregation_count = 0
        self._quality_history: list[float] = []

    def aggregate(
        self,
        signals: list[MultiModalSignal],
        target_time: datetime | None = None,
    ) -> AggregatedSignals:
        """Aggregate signals with temporal alignment.

        Args:
            signals: List of signals to aggregate.
            target_time: Target time for alignment. Uses current time if not provided.

        Returns:
            AggregatedSignals with aligned and weighted signals.
        """
        target_time = target_time or datetime.utcnow()

        # Filter signals by staleness
        valid_signals = self._filter_by_staleness(signals, target_time)

        # Align signals temporally
        aligned_signals, alignment_quality = self._align_temporally(
            valid_signals, target_time
        )

        # Calculate modality weights
        modality_weights = self._calculate_modality_weights(aligned_signals)

        # Calculate confidence scores
        confidence_scores = self._calculate_confidence_scores(aligned_signals)

        # Calculate coverage
        coverage = self._calculate_coverage(aligned_signals)

        # Update statistics
        self._aggregation_count += 1
        self._quality_history.append(alignment_quality)
        if len(self._quality_history) > 100:
            self._quality_history.pop(0)

        return AggregatedSignals(
            signals=aligned_signals,
            aligned_timestamp=target_time,
            alignment_quality=alignment_quality,
            modality_weights=modality_weights,
            confidence_scores=confidence_scores,
            coverage=coverage,
            metadata={
                "original_count": len(signals),
                "valid_count": len(valid_signals),
                "aligned_count": len(aligned_signals),
            },
        )

    def create_batch(
        self,
        signals: list[MultiModalSignal],
        target_time: datetime | None = None,
    ) -> SignalBatch:
        """Create a signal batch for fusion.

        Args:
            signals: List of signals to batch.
            target_time: Target time for alignment.

        Returns:
            SignalBatch ready for fusion.
        """
        target_time = target_time or datetime.utcnow()
        aggregated = self.aggregate(signals, target_time)

        # Calculate modality coverage
        modality_coverage = {
            modality: any(s.modality == modality for s in aggregated.signals)
            for modality in ModalityType
        }

        return SignalBatch(
            signals=aggregated.signals,
            aligned_timestamp=aggregated.aligned_timestamp,
            alignment_quality=aggregated.alignment_quality,
            modality_coverage=modality_coverage,
        )

    def get_statistics(self) -> dict[str, Any]:
        """Get aggregator statistics.

        Returns:
            Dictionary with aggregation statistics.
        """
        avg_quality = (
            sum(self._quality_history) / len(self._quality_history)
            if self._quality_history
            else 0.0
        )

        return {
            "aggregation_count": self._aggregation_count,
            "average_quality": avg_quality,
            "quality_history_size": len(self._quality_history),
            "config": {
                "alignment_window_ms": self.config.alignment_window_ms,
                "max_staleness_ms": self.config.max_staleness_ms,
                "alignment_strategy": self.config.alignment_strategy,
            },
        }

    def reset_statistics(self) -> None:
        """Reset aggregation statistics."""
        self._aggregation_count = 0
        self._quality_history = []

    def _filter_by_staleness(
        self,
        signals: list[MultiModalSignal],
        target_time: datetime,
    ) -> list[MultiModalSignal]:
        """Filter out stale signals."""
        valid_signals = []

        for signal in signals:
            staleness = (
                target_time - signal.temporal_context.timestamp
            ).total_seconds() * 1000

            if staleness <= self.config.max_staleness_ms:
                # Update staleness in metadata
                signal.metadata.staleness_ms = int(staleness)
                valid_signals.append(signal)

        return valid_signals

    def _align_temporally(
        self,
        signals: list[MultiModalSignal],
        target_time: datetime,
    ) -> tuple[list[MultiModalSignal], float]:
        """Align signals temporally to target time.

        Returns:
            Tuple of (aligned signals, alignment quality score).
        """
        if not signals:
            return [], 0.0

        aligned = []
        total_deviation = 0.0

        window = timedelta(milliseconds=self.config.alignment_window_ms)

        for signal in signals:
            deviation = abs(
                (signal.temporal_context.timestamp - target_time).total_seconds() * 1000
            )

            if deviation <= self.config.alignment_window_ms:
                aligned.append(signal)
                total_deviation += deviation

        # Calculate alignment quality (1.0 = perfect alignment, 0.0 = max deviation)
        if aligned:
            max_total_deviation = len(aligned) * self.config.alignment_window_ms
            alignment_quality = 1.0 - (total_deviation / max_total_deviation)
        else:
            alignment_quality = 0.0

        return aligned, alignment_quality

    def _calculate_modality_weights(
        self,
        signals: list[MultiModalSignal],
    ) -> dict[ModalityType, float]:
        """Calculate weights for each modality."""
        modality_counts: dict[ModalityType, int] = {}
        modality_confidence: dict[ModalityType, float] = {}

        for signal in signals:
            if signal.modality not in modality_counts:
                modality_counts[signal.modality] = 0
                modality_confidence[signal.modality] = 0.0

            modality_counts[signal.modality] += 1
            modality_confidence[signal.modality] += signal.effective_confidence

        # Calculate weights
        total_confidence = sum(modality_confidence.values())
        weights = {}

        for modality, conf_sum in modality_confidence.items():
            if self.config.weight_by_confidence and total_confidence > 0:
                weights[modality] = conf_sum / total_confidence
            else:
                # Equal weight per modality
                weights[modality] = (
                    1.0 / len(modality_counts) if modality_counts else 0.0
                )

        return weights

    def _calculate_confidence_scores(
        self,
        signals: list[MultiModalSignal],
    ) -> dict[ModalityType, float]:
        """Calculate average confidence scores per modality."""
        confidence_sums: dict[ModalityType, float] = {}
        counts: dict[ModalityType, int] = {}

        for signal in signals:
            if signal.modality not in confidence_sums:
                confidence_sums[signal.modality] = 0.0
                counts[signal.modality] = 0

            confidence_sums[signal.modality] += signal.effective_confidence
            counts[signal.modality] += 1

        # Calculate averages
        scores = {}
        for modality, total in confidence_sums.items():
            scores[modality] = total / counts[modality]

        return scores

    def _calculate_coverage(
        self,
        signals: list[MultiModalSignal],
    ) -> dict[ModalityType, float]:
        """Calculate coverage for each modality (0.0 to 1.0)."""
        coverage = {}

        for modality in ModalityType:
            modality_signals = [s for s in signals if s.modality == modality]
            if modality_signals:
                # Coverage based on signal count and confidence
                count_coverage = min(
                    len(modality_signals) / self.config.min_signals_per_modality, 1.0
                )
                confidence_coverage = sum(
                    s.effective_confidence for s in modality_signals
                ) / len(modality_signals)
                coverage[modality] = (count_coverage + confidence_coverage) / 2
            else:
                coverage[modality] = 0.0

        return coverage


def aggregate_signals(
    signals: list[MultiModalSignal],
    config: AggregationConfig | None = None,
) -> AggregatedSignals:
    """Convenience function to aggregate signals.

    Args:
        signals: List of signals to aggregate.
        config: Optional aggregation configuration.

    Returns:
        Aggregated signals.
    """
    aggregator = SignalAggregator(config=config)
    return aggregator.aggregate(signals)
