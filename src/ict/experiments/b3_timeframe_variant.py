"""B3 Timeframe Variant Experiment.

Tests different timeframe aggregations for ICT signals.
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
class TimeframeConfig:
    """Configuration for timeframe variant.

    Attributes:
        timeframe: Timeframe identifier (e.g., "15m", "1h", "4h")
        aggregation_method: How to aggregate signals
    """

    timeframe: str = "1h"
    aggregation_method: str = "last"  # "last", "mean", "max"


class B3TimeframeExperiment:
    """Timeframe variant of ICT experiment.

    Tests different timeframe aggregations:
    - "timeframe_15m": 15-minute aggregation
    - "timeframe_1h": 1-hour aggregation (default)
    - "timeframe_4h": 4-hour aggregation

    Attributes:
        experiment_key: The experiment key for this run
        registry: Experiment registry instance
        collector: ICT data collector instance
        timeframe_config: Timeframe configuration
        _running: Whether the experiment is currently running
    """

    VARIANTS = ["timeframe_15m", "timeframe_1h", "timeframe_4h"]

    def __init__(
        self,
        collector: ICTDataCollector,
        registry: ExperimentRegistry | None = None,
        variant: str = "timeframe_1h",
        timeframe_config: TimeframeConfig | None = None,
    ) -> None:
        """Initialize the B3 timeframe experiment.

        Args:
            collector: ICT data collector instance
            registry: Optional experiment registry
            variant: Timeframe variant to use
            timeframe_config: Optional timeframe configuration
        """
        if variant not in self.VARIANTS:
            raise ValueError(
                f"Invalid variant: {variant}. Must be one of {self.VARIANTS}"
            )

        self.experiment_key = ExperimentKey(
            experiment_id="ICT-B3",
            variant=variant,
            started_at=datetime.now(UTC),
        )
        self.registry = registry or ExperimentRegistry()
        self.collector = collector
        self.timeframe_config = timeframe_config or TimeframeConfig(
            timeframe=variant.split("_")[1]
        )
        self._running = False

    def start(self) -> bool:
        """Start the timeframe experiment."""
        if self._running:
            logger.warning("Experiment already running")
            return False

        success = self.registry.register_experiment(self.experiment_key)
        if success:
            self._running = True
            logger.info(f"Started B3 timeframe experiment: {self.experiment_key}")
        return success

    async def stop(self) -> bool:
        """Stop the timeframe experiment."""
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

    async def record_signal(
        self,
        symbol: str,
        signal_type: str,
        confidence: float,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Record a signal with timeframe aggregation applied."""
        return await self.collector.collect_signal(
            symbol=symbol,
            signal_type=signal_type,
            confidence=confidence,
            context={**(context or {}), "timeframe": self.timeframe_config.timeframe},
            experiment_key=self.experiment_key.key_format(),
        )
