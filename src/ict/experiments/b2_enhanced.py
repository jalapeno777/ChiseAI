"""B2 Enhanced ICT Experiment with Risk Overlay.

Implements ICT signals with risk management overlay
for comparison against baseline.
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
class RiskLimits:
    """Risk management limits for enhanced experiment.

    Attributes:
        max_position_size: Maximum position size allowed
        max_loss_per_trade: Maximum loss allowed per trade
        kill_switch_threshold: Total loss threshold to trigger kill switch
    """

    max_position_size: float = 1.0
    max_loss_per_trade: float = 0.02  # 2% of portfolio
    kill_switch_threshold: float = 0.10  # 10% of portfolio


class B2EnhancedExperiment:
    """Enhanced ICT experiment with risk overlay.

    This experiment:
    - Extends baseline with risk overlay
    - Uses position sizing limits
    - Implements kill switch integration
    - Registers with the experiment registry

    Attributes:
        experiment_key: The experiment key for this run
        registry: Experiment registry instance
        collector: ICT data collector instance
        risk_limits: Risk management limits
        _running: Whether the experiment is currently running
        _kill_switch_active: Whether kill switch has been triggered
    """

    def __init__(
        self,
        collector: ICTDataCollector,
        registry: ExperimentRegistry | None = None,
        risk_limits: RiskLimits | None = None,
    ) -> None:
        """Initialize the B2 enhanced experiment.

        Args:
            collector: ICT data collector for signal tracking
            registry: Optional experiment registry
            risk_limits: Optional risk limits
        """
        self.experiment_key = ExperimentKey(
            experiment_id="ICT-B2",
            variant="enhanced",
            started_at=datetime.now(UTC),
        )
        self.registry = registry or ExperimentRegistry()
        self.collector = collector
        self.risk_limits = risk_limits or RiskLimits()
        self._running = False
        self._kill_switch_active = False
        self._total_loss = 0.0

    def start(self) -> bool:
        """Start the enhanced experiment.

        Returns:
            True if started successfully
        """
        if self._running:
            logger.warning("Experiment already running")
            return False

        success = self.registry.register_experiment(self.experiment_key)
        if success:
            self._running = True
            self._kill_switch_active = False
            self._total_loss = 0.0
            logger.info(f"Started B2 enhanced experiment: {self.experiment_key}")
        return success

    async def stop(self) -> bool:
        """Stop the enhanced experiment.

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
            logger.info(f"Stopped B2 enhanced experiment: {self.experiment_key}")
        return success

    def is_running(self) -> bool:
        """Check if experiment is running.

        Returns:
            True if running
        """
        return self._running

    def is_kill_switch_active(self) -> bool:
        """Check if kill switch has been triggered.

        Returns:
            True if kill switch is active
        """
        return self._kill_switch_active

    def check_position_size(self, proposed_size: float) -> float:
        """Check and adjust position size against risk limits.

        Args:
            proposed_size: Proposed position size

        Returns:
            Adjusted position size respecting limits
        """
        if proposed_size > self.risk_limits.max_position_size:
            logger.warning(
                f"Position size {proposed_size} exceeds limit "
                f"{self.risk_limits.max_position_size}, capping"
            )
            return self.risk_limits.max_position_size
        return proposed_size

    def check_loss_limit(self, trade_loss: float) -> bool:
        """Check if trade loss exceeds per-trade limit.

        Args:
            trade_loss: Proposed/actual trade loss

        Returns:
            True if within limits
        """
        if abs(trade_loss) > self.risk_limits.max_loss_per_trade:
            logger.warning(
                f"Trade loss {trade_loss} exceeds limit "
                f"{self.risk_limits.max_loss_per_trade}"
            )
            return False
        return True

    def update_total_loss(self, pnl: float) -> bool:
        """Update total loss tracking and check kill switch.

        Args:
            pnl: PnL from a closed position

        Returns:
            True if kill switch not triggered
        """
        if pnl < 0:
            self._total_loss += abs(pnl)

            if self._total_loss >= self.risk_limits.kill_switch_threshold:
                self._kill_switch_active = True
                logger.critical(
                    f"KILL SWITCH TRIGGERED: Total loss {self._total_loss:.4f} "
                    f"exceeds threshold {self.risk_limits.kill_switch_threshold}"
                )
                return False
        return True

    async def record_signal(
        self,
        symbol: str,
        signal_type: str,
        confidence: float,
        context: dict[str, Any] | None = None,
    ) -> str | None:
        """Record a signal for this experiment.

        Args:
            symbol: Trading pair symbol
            signal_type: Type of signal
            confidence: Confidence score
            context: Additional context

        Returns:
            Signal ID or None if kill switch is active
        """
        if self._kill_switch_active:
            logger.warning("Kill switch active, not recording signals")
            return None

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
        """Record an outcome and update risk tracking.

        Args:
            position_id: Position ID
            signal_id: Signal ID
            outcome: Outcome type
            pnl: Realized PnL
        """
        self.update_total_loss(pnl)
        await self.collector.record_outcome(
            position_id=position_id,
            signal_id=signal_id,
            outcome=outcome,
            pnl=pnl,
        )
