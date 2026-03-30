"""B1 Baseline ICT Experiment.

Implements the baseline ICT signals without modifications
for use as the control group in experiments.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.ict.data_collection.collector import ICTDataCollector

from src.ict.experiments.key_schema import ExperimentKey
from src.ict.experiments.registry import ExperimentRegistry

logger = logging.getLogger(__name__)


class B1BaselineExperiment:
    """Baseline ICT experiment using standard signals.

    This experiment:
    - Uses standard ICT signals without modifications
    - Registers with the experiment registry
    - Integrates with ICTDataCollector for outcome tracking
    - Provides start() and stop() lifecycle methods

    Attributes:
        experiment_key: The experiment key for this run
        registry: Experiment registry instance
        collector: ICT data collector instance
        _running: Whether the experiment is currently running
    """

    def __init__(
        self,
        collector: ICTDataCollector,
        registry: ExperimentRegistry | None = None,
    ) -> None:
        """Initialize the B1 baseline experiment.

        Args:
            collector: ICT data collector for signal tracking
            registry: Optional experiment registry. Creates one if not provided.
        """
        self.experiment_key = ExperimentKey(
            experiment_id="ICT-B1",
            variant="baseline",
            started_at=datetime.now(UTC),
        )
        self.registry = registry or ExperimentRegistry()
        self.collector = collector
        self._running = False

    def start(self) -> bool:
        """Start the baseline experiment.

        Returns:
            True if started successfully
        """
        if self._running:
            logger.warning("Experiment already running")
            return False

        success = self.registry.register_experiment(self.experiment_key)
        if success:
            self._running = True
            logger.info(f"Started B1 baseline experiment: {self.experiment_key}")
        return success

    async def stop(self) -> bool:
        """Stop the baseline experiment.

        Returns:
            True if stopped successfully
        """
        if not self._running:
            logger.warning("Experiment not running")
            return False

        await self.collector.stop_collection()
        success = self.registry.close_experiment(self.experiment_key)
        if success:
            self._running = False
            logger.info(f"Stopped B1 baseline experiment: {self.experiment_key}")
        return success

    def is_running(self) -> bool:
        """Check if experiment is running.

        Returns:
            True if running
        """
        return self._running

    async def record_signal(
        self,
        symbol: str,
        signal_type: str,
        confidence: float,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Record a signal for this experiment.

        Args:
            symbol: Trading pair symbol
            signal_type: Type of signal
            confidence: Confidence score
            context: Additional context

        Returns:
            Signal ID
        """
        return await self.collector.collect_signal(
            symbol=symbol,
            signal_type=signal_type,
            confidence=confidence,
            context=context,
            experiment_key=self.experiment_key.key_format(),
        )

    async def record_outcome(
        self,
        position_id: str,
        signal_id: str,
        outcome: str,
        pnl: float,
    ) -> None:
        """Record an outcome for correlation.

        Args:
            position_id: Position ID
            signal_id: Signal ID
            outcome: Outcome type
            pnl: Realized PnL
        """
        await self.collector.record_outcome(
            position_id=position_id,
            signal_id=signal_id,
            outcome=outcome,
            pnl=pnl,
        )
