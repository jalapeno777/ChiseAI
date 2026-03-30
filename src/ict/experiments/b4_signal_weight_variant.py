"""B4 Signal Weight Variant Experiment.

Tests different signal weighting strategies.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.ict.data_collection.collector import ICTDataCollector

from src.ict.experiments.key_schema import ExperimentKey
from src.ict.experiments.registry import ExperimentRegistry

logger = logging.getLogger(__name__)


@dataclass
class WeightingConfig:
    """Configuration for signal weighting.

    Attributes:
        weighting_method: Weighting strategy
        decay_factor: Decay factor for recency weighting
    """

    weighting_method: str = "equal"  # "equal", "confidence", "recency"
    decay_factor: float = 0.9


class B4SignalWeightExperiment:
    """Signal weight variant of ICT experiment.

    Tests different signal weighting strategies:
    - "equal_weight": All signals weighted equally
    - "confidence_weighted": Higher confidence = higher weight
    - "recency_weighted": More recent signals weighted higher

    Attributes:
        experiment_key: The experiment key for this run
        registry: Experiment registry instance
        collector: ICT data collector instance
        weighting_config: Weighting configuration
        _running: Whether the experiment is currently running
    """

    VARIANTS = ["equal_weight", "confidence_weighted", "recency_weighted"]

    def __init__(
        self,
        collector: ICTDataCollector,
        registry: ExperimentRegistry | None = None,
        variant: str = "equal_weight",
        weighting_config: WeightingConfig | None = None,
    ) -> None:
        """Initialize the B4 signal weight experiment.

        Args:
            collector: ICT data collector instance
            registry: Optional experiment registry
            variant: Weighting variant to use
            weighting_config: Optional weighting configuration
        """
        if variant not in self.VARIANTS:
            raise ValueError(
                f"Invalid variant: {variant}. Must be one of {self.VARIANTS}"
            )

        self.experiment_key = ExperimentKey(
            experiment_id="ICT-B4",
            variant=variant,
            started_at=datetime.now(UTC),
        )
        self.registry = registry or ExperimentRegistry()
        self.collector = collector
        self.weighting_config = weighting_config or WeightingConfig(
            weighting_method=variant.replace("_weight", "")
        )
        self._running = False

    def start(self) -> bool:
        """Start the signal weight experiment."""
        if self._running:
            logger.warning("Experiment already running")
            return False

        success = self.registry.register_experiment(self.experiment_key)
        if success:
            self._running = True
            logger.info(f"Started B4 signal weight experiment: {self.experiment_key}")
        return success

    async def stop(self) -> bool:
        """Stop the signal weight experiment."""
        if not self._running:
            logger.warning("Experiment not running")
            return False

        await self.collector.stop_collection()
        success = self.registry.close_experiment(self.experiment_key)
        if success:
            self._running = False
        return success

    def is_running(self) -> bool:
        """Check if experiment is running."""
        return self._running

    def calculate_signal_weight(
        self, confidence: float, age_seconds: float = 0
    ) -> float:
        """Calculate signal weight based on weighting method.

        Args:
            confidence: Signal confidence score
            age_seconds: Signal age in seconds

        Returns:
            Calculated weight
        """
        method = self.weighting_config.weighting_method

        if method == "equal":
            return 1.0
        elif method == "confidence":
            return confidence
        elif method == "recency":
            decay = self.weighting_config.decay_factor ** (
                age_seconds / 3600
            )  # Per hour
            return decay * confidence
        else:
            return 1.0

    async def record_signal(
        self,
        symbol: str,
        signal_type: str,
        confidence: float,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Record a signal with weighting applied."""
        weight = self.calculate_signal_weight(confidence)
        return await self.collector.collect_signal(
            symbol=symbol,
            signal_type=signal_type,
            confidence=confidence,
            context={
                **(context or {}),
                "weight": weight,
                "weighting_method": self.weighting_config.weighting_method,
            },
            experiment_key=self.experiment_key.key_format(),
        )
