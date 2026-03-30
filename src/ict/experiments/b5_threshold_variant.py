"""B5 Threshold Variant Experiment.

Tests different entry threshold levels.
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
class ThresholdConfig:
    """Configuration for entry thresholds.

    Attributes:
        entry_threshold: Minimum confidence to enter
        exit_threshold: Minimum confidence to exit
        stop_threshold: Confidence level for stop
    """

    entry_threshold: float = 0.5
    exit_threshold: float = 0.3
    stop_threshold: float = 0.2


class B5ThresholdExperiment:
    """Threshold variant of ICT experiment.

    Tests different entry threshold levels:
    - "low_threshold": entry=0.3, exit=0.2, stop=0.1
    - "medium_threshold": entry=0.5, exit=0.3, stop=0.2 (default)
    - "high_threshold": entry=0.7, exit=0.5, stop=0.4

    Attributes:
        experiment_key: The experiment key for this run
        registry: Experiment registry instance
        collector: ICT data collector instance
        threshold_config: Threshold configuration
        _running: Whether the experiment is currently running
    """

    VARIANTS = ["low_threshold", "medium_threshold", "high_threshold"]

    _VARIANT_CONFIGS = {
        "low_threshold": ThresholdConfig(
            entry_threshold=0.3, exit_threshold=0.2, stop_threshold=0.1
        ),
        "medium_threshold": ThresholdConfig(
            entry_threshold=0.5, exit_threshold=0.3, stop_threshold=0.2
        ),
        "high_threshold": ThresholdConfig(
            entry_threshold=0.7, exit_threshold=0.5, stop_threshold=0.4
        ),
    }

    def __init__(
        self,
        collector: ICTDataCollector,
        registry: ExperimentRegistry | None = None,
        variant: str = "medium_threshold",
        threshold_config: ThresholdConfig | None = None,
    ) -> None:
        """Initialize the B5 threshold experiment.

        Args:
            collector: ICT data collector instance
            registry: Optional experiment registry
            variant: Threshold variant to use
            threshold_config: Optional threshold configuration
        """
        if variant not in self.VARIANTS:
            raise ValueError(
                f"Invalid variant: {variant}. Must be one of {self.VARIANTS}"
            )

        self.experiment_key = ExperimentKey(
            experiment_id="ICT-B5",
            variant=variant,
            started_at=datetime.now(UTC),
        )
        self.registry = registry or ExperimentRegistry()
        self.collector = collector
        self.threshold_config = threshold_config or self._VARIANT_CONFIGS[variant]
        self._running = False

    def start(self) -> bool:
        """Start the threshold experiment."""
        if self._running:
            logger.warning("Experiment already running")
            return False

        success = self.registry.register_experiment(self.experiment_key)
        if success:
            self._running = True
            logger.info(f"Started B5 threshold experiment: {self.experiment_key}")
        return success

    async def stop(self) -> bool:
        """Stop the threshold experiment."""
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

    def should_enter(self, confidence: float) -> bool:
        """Check if confidence meets entry threshold.

        Args:
            confidence: Signal confidence score

        Returns:
            True if should enter position
        """
        return confidence >= self.threshold_config.entry_threshold

    def should_exit(self, confidence: float) -> bool:
        """Check if confidence meets exit threshold.

        Args:
            confidence: Signal confidence score

        Returns:
            True if should exit position
        """
        return confidence <= self.threshold_config.exit_threshold

    async def record_signal(
        self,
        symbol: str,
        signal_type: str,
        confidence: float,
        context: dict[str, Any] | None = None,
    ) -> str | None:
        """Record a signal only if it meets entry threshold."""
        if signal_type == "entry" and not self.should_enter(confidence):
            logger.debug(f"Signal confidence {confidence} below entry threshold")
            return None

        return await self.collector.collect_signal(
            symbol=symbol,
            signal_type=signal_type,
            confidence=confidence,
            context={**(context or {}), "thresholds": self.threshold_config.__dict__},
            experiment_key=self.experiment_key.key_format(),
        )
