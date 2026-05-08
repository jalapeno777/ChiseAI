"""Experiment Tracker - Coordinator for ICT Validation Experiments.

High-level coordinator that orchestrates data collection experiments.
Integrates with:
- Signal Tracker for data storage
- Experiment Runner for experiment execution
- Hypothesis Framework for statistical evaluation

This module provides the main entry point for running ICT hypothesis experiments.

Usage:
    from validation.experiment_tracker import ExperimentTracker, create_redis_tracker

    # Create tracker with Redis
    tracker = create_redis_tracker()
    coordinator = ExperimentTracker(tracker)

    # Run experiment
    coordinator.start_experiment()
    coordinator.process_signal(...)
    coordinator.stop_experiment()

    # Get results
    report = coordinator.generate_report()
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from validation.data_collection.experiment_runner import (
    ExperimentConfig,
    ExperimentRunner,
    ExperimentState,
)
from validation.data_collection.signal_tracker import (
    SignalGroup,
    SignalTracker,
    SignalType,
)


def create_redis_tracker(
    host: str = "localhost",
    port: int = 6379,
    db: int = 0,
    password: str | None = None,
) -> SignalTracker:
    """Create a SignalTracker with Redis backend.

    Args:
        host: Redis host
        port: Redis port
        db: Redis database number
        password: Optional Redis password

    Returns:
        SignalTracker instance connected to Redis
    """
    import redis

    client = redis.Redis(
        host=host,
        port=port,
        db=db,
        password=password,
        decode_responses=True,
    )
    return SignalTracker(client)


@dataclass
class ExperimentMetadata:
    """Metadata for an experiment run.

    Attributes:
        experiment_id: Unique identifier
        start_time: Unix timestamp when started
        end_time: Unix timestamp when ended
        config: Experiment configuration used
        status: Current status
    """

    experiment_id: str
    start_time: int
    end_time: int | None = None
    config: dict[str, Any] | None = None
    status: str = "initialized"


class ExperimentTracker:
    """High-level coordinator for ICT validation experiments.

    Integrates SignalTracker and ExperimentRunner to provide
    a complete experiment management interface.

    Features:
    - Experiment lifecycle management
    - Signal processing pipeline
    - Early stopping with automatic evaluation
    - Report generation
    - State callbacks for monitoring

    Usage:
        tracker = ExperimentTracker(redis_client)
        tracker.start_experiment()

        # Process signals
        tracker.process_treatment_signal("cvd", 1.1000, confluence_score=0.75)
        tracker.process_control_signal("fvg", 1.0950)

        # Check status
        if tracker.should_stop():
            print(tracker.get_stop_reason())

        # Generate report
        print(tracker.generate_report())

        tracker.stop_experiment()
    """

    def __init__(
        self,
        tracker: SignalTracker | None = None,
        config: ExperimentConfig | None = None,
    ) -> None:
        """Initialize experiment tracker.

        Args:
            tracker: SignalTracker instance (creates default if None)
            config: Experiment configuration
        """
        self._tracker = tracker
        self._runner = ExperimentRunner(config=config)
        self._experiment_id: str | None = None
        self._start_time: int | None = None
        self._callbacks: list[Callable[[ExperimentState], None]] = []

        # Connect runner to tracker
        if tracker:
            self._runner.set_tracker(tracker)

    @property
    def tracker(self) -> SignalTracker:
        """Get signal tracker, raising if not set."""
        if self._tracker is None:
            raise RuntimeError("SignalTracker not set")
        return self._tracker

    def set_tracker(self, tracker: SignalTracker) -> None:
        """Set signal tracker.

        Args:
            tracker: SignalTracker instance
        """
        self._tracker = tracker
        self._runner.set_tracker(tracker)

    def start_experiment(
        self,
        experiment_id: str | None = None,
        config: ExperimentConfig | None = None,
    ) -> str:
        """Start a new experiment.

        Args:
            experiment_id: Optional custom experiment ID
            config: Optional experiment configuration

        Returns:
            Experiment ID
        """
        # Reset any existing experiment
        if config:
            self._runner = ExperimentRunner(config=config)
            if self._tracker:
                self._runner.set_tracker(self._tracker)

        self._experiment_id = experiment_id or f"exp_{int(time.time())}"
        self._start_time = int(time.time())
        self._runner.reset()

        return self._experiment_id

    def stop_experiment(self) -> ExperimentMetadata:
        """Stop the current experiment.

        Returns:
            ExperimentMetadata with final status
        """
        if not self._experiment_id:
            raise RuntimeError("No experiment is running")

        metadata = ExperimentMetadata(
            experiment_id=self._experiment_id,
            start_time=self._start_time or int(time.time()),
            end_time=int(time.time()),
            config=self._get_config_dict(),
            status=(
                "completed"
                if self._runner.get_state().status != "running"
                else "stopped"
            ),
        )

        return metadata

    def _get_config_dict(self) -> dict[str, Any]:
        """Get current configuration as dict."""
        return {
            "early_stop_signals": self._runner.config.early_stop_signals,
            "early_stop_p_threshold": self._runner.config.early_stop_p_threshold,
            "minimum_signals": self._runner.config.minimum_signals,
            "alpha": self._runner.config.alpha,
            "power": self._runner.config.power,
            "effect_size": self._runner.config.effect_size,
        }

    def process_treatment_signal(
        self,
        signal_type: str,
        entry_price: float,
        direction: str = "bullish",
        confluence_score: float | None = None,
        stop_loss: float = 0.0,
        take_profit: float = 0.0,
        outcome_pnl: float | None = None,
        outcome: str | None = None,
        exit_price: float = 0.0,
        holding_period: int = 0,
        metadata: dict[str, Any] | None = None,
    ):
        """Process a treatment group signal (WITH ICT confluence scoring).

        Args:
            signal_type: Type of signal (cvd, fvg, order_block)
            entry_price: Entry price
            direction: Trading direction
            confluence_score: ICT confluence score
            stop_loss: Stop loss price
            take_profit: Take profit price
            outcome_pnl: PnL ratio if outcome is known
            outcome: Outcome string (win/loss/breakeven/pending)
            exit_price: Exit price
            holding_period: Position holding time in seconds
            metadata: Additional metadata
        """
        # Validate signal type
        if not SignalType.is_valid(signal_type):
            raise ValueError(
                f"Invalid signal type: {signal_type}. "
                f"Supported: {[t.value for t in SignalType]}. "
                f"Excluded: {SignalType.excluded_types()}"
            )

        return self._runner.process_signal(
            signal_type=signal_type,
            group=SignalGroup.TREATMENT,
            entry_price=entry_price,
            direction=direction,
            confluence_score=confluence_score,
            stop_loss=stop_loss,
            take_profit=take_profit,
            outcome_pnl=outcome_pnl,
            outcome=outcome,
            exit_price=exit_price,
            holding_period=holding_period,
            metadata=metadata,
        )

    def process_control_signal(
        self,
        signal_type: str,
        entry_price: float,
        direction: str = "bullish",
        stop_loss: float = 0.0,
        take_profit: float = 0.0,
        outcome_pnl: float | None = None,
        outcome: str | None = None,
        exit_price: float = 0.0,
        holding_period: int = 0,
        metadata: dict[str, Any] | None = None,
    ):
        """Process a control group signal (WITHOUT ICT confluence scoring).

        Control signals are baseline entries without ICT confluence scoring.

        Args:
            signal_type: Type of signal (cvd, fvg, order_block)
            entry_price: Entry price
            direction: Trading direction
            stop_loss: Stop loss price
            take_profit: Take profit price
            outcome_pnl: PnL ratio if outcome is known
            outcome: Outcome string (win/loss/breakeven/pending)
            exit_price: Exit price
            holding_period: Position holding time in seconds
            metadata: Additional metadata
        """
        # Validate signal type
        if not SignalType.is_valid(signal_type):
            raise ValueError(
                f"Invalid signal type: {signal_type}. "
                f"Supported: {[t.value for t in SignalType]}. "
                f"Excluded: {SignalType.excluded_types()}"
            )

        return self._runner.process_signal(
            signal_type=signal_type,
            group=SignalGroup.CONTROL,
            entry_price=entry_price,
            direction=direction,
            confluence_score=None,  # No confluence scoring for control
            stop_loss=stop_loss,
            take_profit=take_profit,
            outcome_pnl=outcome_pnl,
            outcome=outcome,
            exit_price=exit_price,
            holding_period=holding_period,
            metadata=metadata,
        )

    def should_stop(self) -> bool:
        """Check if experiment should stop.

        Returns:
            True if early stopping criteria are met
        """
        return self._runner.should_stop()

    def get_stop_reason(self) -> str:
        """Get reason for stopping.

        Returns:
            Stop reason or empty string
        """
        return self._runner.get_stop_reason()

    def get_state(self) -> ExperimentState:
        """Get current experiment state.

        Returns:
            ExperimentState instance
        """
        return self._runner.get_state()

    def evaluate_now(self):
        """Force immediate hypothesis evaluation."""
        return self._runner.evaluate_now()

    def get_stats(self) -> dict[str, Any]:
        """Get experiment statistics.

        Returns:
            Dictionary with experiment stats
        """
        return self.tracker.get_experiment_stats()

    def register_callback(self, callback: Callable[[ExperimentState], None]) -> None:
        """Register a callback for state changes.

        Args:
            callback: Function to call on state updates
        """
        self._runner.register_callback(callback)

    def generate_report(self) -> str:
        """Generate human-readable experiment report.

        Returns:
            Formatted report string
        """
        return self._runner.generate_report()

    def validate_bos_choch_included(self) -> dict[str, Any]:
        """Validate that BOS/CHoCH signals are properly included in the pipeline.

        This is a sanity check to ensure BOS and CHoCH signals flow through
        the pipeline after re-enablement (BL-BOS-CHOCH-001 lifted).

        Returns:
            Dictionary with validation results
        """
        results = {
            "bos_choch_enabled": True,
            "validation_passed": True,
            "signals_tried": [],
        }

        # Verify BOS/CHoCH signals are accepted
        for signal_type in ["bos", "choch"]:
            try:
                self.process_treatment_signal(
                    signal_type=signal_type,
                    entry_price=1.1000,
                )
                results["signals_tried"].append(f"{signal_type}: accepted")
            except ValueError:
                results[f"{signal_type}_enabled"] = False
                results["validation_passed"] = False
                results["signals_tried"].append(f"{signal_type}: rejected (ERROR)")

        return results
