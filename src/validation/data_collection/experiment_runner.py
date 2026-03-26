"""Experiment Runner for ICT Hypothesis Testing.

Orchestrates the data collection experiment for evaluating ICT signal alpha.
Provides:
- Automated signal processing pipeline
- Early stopping mechanism (p > 0.3 after 50 signals)
- Integration with hypothesis framework for statistical evaluation
- Redis-based data storage

Early Stopping Rule:
    After each signal, calculate interim p-value. If p > 0.3 and we have
    at least 50 signals, stop collection as evidence suggests H0 cannot be rejected.

Control vs Treatment:
    - Control: Entry signals WITHOUT ICT confluence scoring
    - Treatment: Entry signals WITH ICT confluence scoring (CVD, FVG, Order Block)
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from validation.statistical.hypothesis_framework import (
    EffectSizeThresholds,
    HypothesisDecision,
    HypothesisTestResult,
    ICTHypothesisFramework,
    SignalResult,
    TestParameters,
)

from validation.data_collection.signal_tracker import (
    SignalGroup,
    SignalTracker,
    TrackedSignal,
)


@dataclass
class ExperimentConfig:
    """Configuration for the experiment runner.

    Attributes:
        early_stop_signals: Minimum signals before early stopping check
        early_stop_p_threshold: P-value threshold for early stopping
        minimum_signals: Minimum signals needed for full evaluation
        alpha: Significance level for hypothesis test
        power: Target statistical power
        effect_size: Expected effect size (Cohen's h)
        positive_threshold: Return threshold for positive outcome
    """

    early_stop_signals: int = 50
    early_stop_p_threshold: float = 0.30
    minimum_signals: int = 100
    alpha: float = 0.05
    power: float = 0.80
    effect_size: float = 0.50
    positive_threshold: float = 0.0

    def to_test_parameters(self) -> TestParameters:
        """Convert to hypothesis framework TestParameters."""
        return TestParameters(
            alpha=self.alpha,
            power=self.power,
            minimum_signals=self.minimum_signals,
            early_stop_signals=self.early_stop_signals,
            early_stop_p_threshold=self.early_stop_p_threshold,
            effect_size=self.effect_size,
        )


@dataclass
class ExperimentState:
    """Current state of the experiment.

    Attributes:
        status: Current experiment status
        signals_analyzed: Number of signals processed
        control_signals: Number of control signals
        treatment_signals: Number of treatment signals
        current_p_value: Most recent p-value
        current_effect_size: Most recent effect size
        decision: Current hypothesis decision
        should_stop: Whether early stopping was triggered
        stop_reason: Reason for stopping (if applicable)
        last_evaluation_time: Timestamp of last evaluation
    """

    status: str = "initialized"
    signals_analyzed: int = 0
    control_signals: int = 0
    treatment_signals: int = 0
    current_p_value: float = 1.0
    current_effect_size: float = 0.0
    decision: HypothesisDecision = HypothesisDecision.CONTINUE
    should_stop: bool = False
    stop_reason: str = ""
    last_evaluation_time: int = 0


class ExperimentRunner:
    """Orchestrates the ICT hypothesis experiment.

    Handles:
    - Processing signals from both control and treatment groups
    - Calculating interim hypothesis test results
    - Early stopping evaluation
    - Coordination with hypothesis framework

    Usage:
        config = ExperimentConfig()
        tracker = SignalTracker(redis_client)
        runner = ExperimentRunner(config, tracker)

        # Process a new signal
        result = runner.process_signal(
            signal_type="cvd",
            group=SignalGroup.TREATMENT,
            entry_price=1.1000,
            confluence_score=0.75,
            outcome_pnl=0.023,
            outcome="win"
        )

        # Check if should stop
        if runner.should_stop():
            print(f"Stopping: {runner.get_stop_reason()}")

        # Get current state
        state = runner.get_state()
    """

    def __init__(
        self,
        config: ExperimentConfig | None = None,
        tracker: SignalTracker | None = None,
    ) -> None:
        """Initialize experiment runner.

        Args:
            config: Experiment configuration
            tracker: Signal tracker instance
        """
        self.config = config or ExperimentConfig()
        self._tracker = tracker
        self._framework = ICTHypothesisFramework(
            parameters=self.config.to_test_parameters(),
            thresholds=EffectSizeThresholds(),
        )
        self._state = ExperimentState()
        self._callbacks: list[Callable[[ExperimentState], None]] = []

    @property
    def tracker(self) -> SignalTracker:
        """Get signal tracker, raising if not set."""
        if self._tracker is None:
            raise RuntimeError("SignalTracker not set. Provide tracker to constructor.")
        return self._tracker

    def set_tracker(self, tracker: SignalTracker) -> None:
        """Set signal tracker after initialization."""
        self._tracker = tracker

    def register_callback(self, callback: Callable[[ExperimentState], None]) -> None:
        """Register a callback for state changes.

        Args:
            callback: Function to call on state updates
        """
        self._callbacks.append(callback)

    def _notify_callbacks(self) -> None:
        """Notify all registered callbacks of state change."""
        for callback in self._callbacks:
            callback(self._state)

    def process_signal(
        self,
        signal_type: str,
        group: SignalGroup,
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
        signal_id: str | None = None,
        timestamp: int | None = None,
    ) -> TrackedSignal:
        """Process a new signal and optionally record its outcome.

        Args:
            signal_type: Type of signal (cvd, fvg, order_block)
            group: Control or treatment group
            entry_price: Entry price
            direction: Trading direction
            confluence_score: ICT confluence score (treatment only)
            stop_loss: Stop loss price
            take_profit: Take profit price
            outcome_pnl: PnL ratio if outcome is known
            outcome: Outcome string (win/loss/breakeven/pending)
            exit_price: Exit price
            holding_period: Position holding time in seconds
            metadata: Additional metadata
            signal_id: Optional custom signal ID
            timestamp: Optional custom timestamp

        Returns:
            TrackedSignal instance
        """
        # Track the signal
        signal = self.tracker.track_signal(
            signal_type=signal_type,
            group=group,
            entry_price=entry_price,
            direction=direction,
            confluence_score=confluence_score,
            stop_loss=stop_loss,
            take_profit=take_profit,
            metadata=metadata,
            signal_id=signal_id,
            timestamp=timestamp,
        )

        # Record outcome if provided
        if outcome_pnl is not None or outcome is not None:
            self.tracker.record_outcome(
                signal_id=signal.signal_id,
                pnl=outcome_pnl or 0.0,
                outcome=outcome or "pending",
                exit_price=exit_price,
                holding_period=holding_period,
                metadata=metadata,
            )

        # Update state
        self._update_state()

        # Add to hypothesis framework if outcome is known
        if outcome_pnl is not None:
            self._add_to_framework(signal, outcome_pnl)

        return signal

    def _add_to_framework(self, signal: TrackedSignal, pnl: float) -> None:
        """Add signal result to hypothesis framework.

        Args:
            signal: The tracked signal
            pnl: PnL ratio for the trade
        """
        outcome = self.tracker.get_outcome(signal.signal_id)
        if outcome is None:
            return

        # For treatment group, use actual PnL
        # For control group, we need paired comparison
        # In practice, control and treatment should have paired entries
        # Here we use the signal's own PnL for both in paired analysis
        result = SignalResult(
            signal_id=signal.signal_id,
            timestamp=signal.timestamp,
            treatment_return=pnl if signal.group == SignalGroup.TREATMENT else 0.0,
            control_return=pnl if signal.group == SignalGroup.CONTROL else 0.0,
        )

        # For proper analysis, we'd need paired control/treatment signals
        # This is a simplified version - full implementation would require
        # matching control signals to treatment signals
        self._framework.add_result(result)

    def _update_state(self) -> None:
        """Update experiment state from tracker data."""
        self._state.signals_analyzed = self.tracker.get_signal_count(
            SignalGroup.CONTROL
        ) + self.tracker.get_signal_count(SignalGroup.TREATMENT)
        self._state.control_signals = self.tracker.get_signal_count(SignalGroup.CONTROL)
        self._state.treatment_signals = self.tracker.get_signal_count(
            SignalGroup.TREATMENT
        )
        self._state.last_evaluation_time = int(time.time())

        # Run hypothesis evaluation if we have signals
        if self._state.signals_analyzed > 0:
            self._evaluate()

    def _evaluate(self) -> HypothesisTestResult:
        """Run hypothesis evaluation and update state."""
        result = self._framework.evaluate(
            positive_threshold=self.config.positive_threshold
        )

        self._state.current_p_value = result.p_value
        self._state.current_effect_size = result.effect_size
        self._state.decision = result.decision

        # Check early stopping
        if self._state.signals_analyzed >= self.config.early_stop_signals:
            if result.p_value > self.config.early_stop_p_threshold:
                self._state.should_stop = True
                self._state.stop_reason = (
                    f"Early stopping: p={result.p_value:.4f} > "
                    f"{self.config.early_stop_p_threshold} after "
                    f"{self._state.signals_analyzed} signals"
                )
                self._state.status = "stopped_early"
            else:
                self._state.status = "running"
        else:
            self._state.status = "collecting"

        # Check final decision
        if result.decision in (
            HypothesisDecision.ACCEPT_H0,
            HypothesisDecision.REJECT_H0,
        ):
            self._state.status = "completed"

        return result

    def evaluate_now(self) -> HypothesisTestResult:
        """Force immediate evaluation of current data.

        Returns:
            HypothesisTestResult from the evaluation
        """
        return self._evaluate()

    def should_stop(self) -> bool:
        """Check if experiment should stop.

        Returns:
            True if early stopping criteria are met
        """
        return self._state.should_stop

    def get_stop_reason(self) -> str:
        """Get reason for stopping.

        Returns:
            Stop reason string or empty if not stopping
        """
        return self._state.stop_reason

    def get_state(self) -> ExperimentState:
        """Get current experiment state.

        Returns:
            ExperimentState instance
        """
        return self._state

    def get_latest_result(self) -> HypothesisTestResult:
        """Get the latest hypothesis test result.

        Returns:
            HypothesisTestResult from last evaluation
        """
        return self._framework.evaluate(
            positive_threshold=self.config.positive_threshold
        )

    def reset(self) -> None:
        """Reset experiment to initial state.

        Clears all data from tracker and resets framework.
        """
        if self._tracker:
            self._tracker.clear_experiment_data()

        self._framework = ICTHypothesisFramework(
            parameters=self.config.to_test_parameters(),
            thresholds=EffectSizeThresholds(),
        )
        self._state = ExperimentState()
        self._state.status = "initialized"

    def generate_report(self) -> str:
        """Generate human-readable experiment report.

        Returns:
            Formatted report string
        """
        result = self.get_latest_result()
        state = self.get_state()

        lines = [
            "ICT Experiment Runner Status Report",
            "=" * 50,
            f"Status: {state.status}",
            f"Signals analyzed: {state.signals_analyzed}",
            f"  Control: {state.control_signals}",
            f"  Treatment: {state.treatment_signals}",
            "",
            "Early Stopping Check:",
            f"  Minimum signals: {self.config.early_stop_signals}",
            f"  P-value threshold: {self.config.early_stop_p_threshold}",
            f"  Should stop: {state.should_stop}",
            f"  Reason: {state.stop_reason or 'N/A'}",
            "",
            "Hypothesis Test Results:",
            f"  Decision: {state.decision.value}",
            f"  P-value: {state.current_p_value:.4f}",
            f"  Effect size: {state.current_effect_size:.4f}",
            f"  Power achieved: {result.power_achieved:.2%}",
            "",
        ]

        if state.should_stop:
            lines.append("Experiment STOPPED - see reason above")
        elif state.status == "completed":
            lines.append(f"Experiment COMPLETED with decision: {state.decision.value}")
        else:
            lines.append(
                f"Continue collecting signals (need {self.config.minimum_signals - state.signals_analyzed} more)"
            )

        return "\n".join(lines)
