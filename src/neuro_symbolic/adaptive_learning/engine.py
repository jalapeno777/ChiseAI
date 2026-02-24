"""Adaptive Learning Engine for continuous model improvement.

Main orchestration class that integrates feedback, model adaptation,
and scheduling for continuous learning from market data.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from src.neuro_symbolic.adaptive_learning.adapter import (
    AdapterConfig,
    ModelAdapter,
)
from src.neuro_symbolic.adaptive_learning.feedback import (
    FeedbackIntegrator,
    IntegratorConfig,
)
from src.neuro_symbolic.adaptive_learning.scheduler import (
    LearningScheduler,
    SchedulerConfig,
)
from src.neuro_symbolic.learning.base import (
    AdaptationResult,
    AdaptationStatus,
    FeedbackSignal,
    LearningConfig,
    PerformanceMetrics,
    TriggerCondition,
)


@dataclass
class EngineConfig:
    """Configuration for AdaptiveLearningEngine."""

    learning_config: LearningConfig = field(default_factory=LearningConfig)
    feedback_config: IntegratorConfig = field(default_factory=IntegratorConfig)
    adapter_config: AdapterConfig = field(default_factory=AdapterConfig)
    scheduler_config: SchedulerConfig = field(default_factory=SchedulerConfig)
    enable_online_learning: bool = True
    enable_auto_rollback: bool = True
    checkpoint_interval_hours: int = 6
    max_history_size: int = 10000


@dataclass
class EngineState:
    """State of the adaptive learning engine."""

    is_adapted: bool = False
    last_adaptation: datetime | None = None
    total_adaptations: int = 0
    successful_adaptations: int = 0
    rollback_count: int = 0
    start_time: datetime = field(default_factory=datetime.now)
    current_strategy: str | None = None
    performance_trend: str = "unknown"


class AdaptiveLearningEngine:
    """Main engine for adaptive learning from market feedback.

    Coordinates feedback integration, model adaptation, and scheduled
    updates for continuous model improvement.
    """

    def __init__(self, config: EngineConfig | None = None):
        """Initialize the adaptive learning engine.

        Args:
            config: Engine configuration
        """
        self.config = config or EngineConfig()
        self._state = EngineState()

        # Initialize components
        self.feedback = FeedbackIntegrator(self.config.feedback_config)
        self.adapter = ModelAdapter(
            config=self.config.adapter_config,
            learning_config=self.config.learning_config,
        )
        self.scheduler = LearningScheduler(
            config=self.config.scheduler_config,
            learning_config=self.config.learning_config,
        )

        # Set up scheduler callback
        self.scheduler.set_adaptation_callback(self._execute_adaptation)

        # Internal state
        self._model_parameters: dict[str, np.ndarray] = {}
        self._performance_buffer: list[PerformanceMetrics] = []
        self._adaptation_history: list[AdaptationResult] = []
        self._gradients_buffer: list[dict[str, np.ndarray]] = []

    def set_model_parameters(self, parameters: dict[str, np.ndarray]) -> None:
        """Set the model parameters to be adapted.

        Args:
            parameters: Dictionary of parameter name to numpy array
        """
        self._model_parameters = parameters.copy()
        self.adapter.set_parameters(parameters)

    def get_model_parameters(self) -> dict[str, np.ndarray]:
        """Get current model parameters."""
        return self.adapter.get_parameters()

    def adapt(
        self,
        feedback: dict[str, Any] | None = None,
        gradients: dict[str, np.ndarray] | None = None,
        metrics: PerformanceMetrics | None = None,
    ) -> AdaptationResult:
        """Perform model adaptation based on feedback.

        Args:
            feedback: Optional feedback dictionary for processing
            gradients: Optional pre-computed gradients
            metrics: Optional current performance metrics

        Returns:
            AdaptationResult describing the outcome
        """
        # Process feedback if provided
        if feedback:
            signal = self._process_feedback_dict(feedback)
            gradients = gradients or self._compute_gradients_from_signal(signal)

        # Use stored gradients if none provided
        if gradients is None and self._gradients_buffer:
            gradients = self._aggregate_gradients()

        if gradients is None:
            return AdaptationResult(
                status=AdaptationStatus.SKIPPED,
                error_message="No gradients available for adaptation",
            )

        # Perform adaptation
        result = self.adapter.adapt(
            gradients=gradients,
            metrics=metrics,
            trigger=TriggerCondition.MANUAL,
        )

        # Update state
        self._update_state(result)
        self._adaptation_history.append(result)

        # Auto-rollback if enabled and adaptation failed
        if (
            self.config.enable_auto_rollback
            and result.status == AdaptationStatus.FAILED
            and self.adapter.get_checkpoints()
        ):
            self.rollback()
            self._state.rollback_count += 1

        # Update model parameters
        if result.is_successful:
            self._model_parameters = self.adapter.get_parameters()
            self._state.is_adapted = True

        return result

    def _process_feedback_dict(self, feedback: dict[str, Any]) -> FeedbackSignal:
        """Process feedback dictionary into a signal."""
        strategy_id = feedback.get("strategy", "default")

        outcome = {
            "pnl": feedback.get("pnl", 0.0),
            "pnl_pct": feedback.get("pnl_pct", 0.0),
            "confidence": feedback.get("confidence", 0.5),
            "duration": feedback.get("duration", 0),
            "exit_reason": feedback.get("exit_reason", "unknown"),
        }

        return self.feedback.process_trade_outcome(
            strategy_id=strategy_id,
            outcome=outcome,
            trade_id=feedback.get("trade_id"),
            symbol=feedback.get("symbol"),
        )

    def _compute_gradients_from_signal(
        self,
        signal: FeedbackSignal,
    ) -> dict[str, np.ndarray]:
        """Compute parameter gradients from a feedback signal."""
        gradients = {}

        # Use signal value as learning signal
        learning_signal = signal.to_array()

        for name, param in self._model_parameters.items():
            # Simple gradient: scale parameters by learning signal
            # In practice, this would use backpropagation through the model
            noise = np.random.randn(*param.shape) * 0.01
            gradient = (
                noise * learning_signal[0] * self.config.learning_config.learning_rate
            )
            gradients[name] = gradient

        return gradients

    def _aggregate_gradients(self) -> dict[str, np.ndarray]:
        """Aggregate buffered gradients."""
        if not self._gradients_buffer:
            return {}

        aggregated = {}
        for grad_dict in self._gradients_buffer:
            for name, grad in grad_dict.items():
                if name not in aggregated:
                    aggregated[name] = np.zeros_like(grad)
                aggregated[name] += grad

        # Average
        n = len(self._gradients_buffer)
        for name in aggregated:
            aggregated[name] /= n

        # Clear buffer
        self._gradients_buffer.clear()

        return aggregated

    def _update_state(self, result: AdaptationResult) -> None:
        """Update engine state after adaptation."""
        self._state.total_adaptations += 1
        self._state.last_adaptation = datetime.now()

        if result.is_successful:
            self._state.successful_adaptations += 1

    def _execute_adaptation(
        self,
        trigger: TriggerCondition,
        metadata: dict[str, Any],
    ) -> AdaptationResult:
        """Execute scheduled adaptation.

        Args:
            trigger: What triggered this adaptation
            metadata: Additional metadata

        Returns:
            AdaptationResult
        """
        # Get recent feedback
        recent_signals = self.feedback.get_recent_signals(
            n=self.config.learning_config.performance_window
        )

        if not recent_signals:
            return AdaptationResult(
                status=AdaptationStatus.SKIPPED,
                trigger=trigger,
                error_message="No recent feedback for adaptation",
            )

        # Compute gradients from recent feedback
        gradients = {}
        for signal in recent_signals:
            signal_grads = self._compute_gradients_from_signal(signal)
            for name, grad in signal_grads.items():
                if name not in gradients:
                    gradients[name] = np.zeros_like(grad)
                gradients[name] += grad

        # Average gradients
        for name in gradients:
            gradients[name] /= len(recent_signals)

        # Get current metrics
        metrics = self.get_performance_metrics()

        # Perform adaptation
        result = self.adapter.adapt(
            gradients=gradients,
            metrics=metrics,
            trigger=trigger,
        )

        self._update_state(result)
        self._adaptation_history.append(result)

        if result.is_successful:
            self._model_parameters = self.adapter.get_parameters()
            self._state.is_adapted = True

        return result

    def process_outcome(
        self,
        strategy_id: str,
        outcome: dict[str, Any],
        trade_id: str | None = None,
        symbol: str | None = None,
    ) -> FeedbackSignal:
        """Process a trade outcome for learning.

        Args:
            strategy_id: Strategy that made the trade
            outcome: Trade outcome dictionary
            trade_id: Optional trade identifier
            symbol: Optional trading symbol

        Returns:
            Generated FeedbackSignal
        """
        signal = self.feedback.process_trade_outcome(
            strategy_id=strategy_id,
            outcome=outcome,
            trade_id=trade_id,
            symbol=symbol,
        )

        # Record for scheduler
        metrics = self.feedback.compute_strategy_performance(strategy_id)
        self.scheduler.record_performance(metrics)

        # Store gradients for online learning
        if self.config.enable_online_learning:
            gradients = self._compute_gradients_from_signal(signal)
            self._gradients_buffer.append(gradients)

            # Trigger online update if enough samples
            if (
                len(self._gradients_buffer)
                >= self.config.learning_config.min_samples_for_adaptation
            ):
                self.adapt()

        return signal

    def batch_process_outcomes(
        self,
        outcomes: list[dict[str, Any]],
        strategy_id: str,
    ) -> list[FeedbackSignal]:
        """Process multiple trade outcomes.

        Args:
            outcomes: List of outcome dictionaries
            strategy_id: Strategy ID for all outcomes

        Returns:
            List of generated FeedbackSignals
        """
        return self.feedback.integrate_batch(outcomes, strategy_id)

    def get_performance_metrics(
        self,
        strategy_id: str | None = None,
    ) -> PerformanceMetrics:
        """Get current performance metrics.

        Args:
            strategy_id: Optional strategy to get metrics for

        Returns:
            PerformanceMetrics
        """
        if strategy_id:
            return self.feedback.compute_strategy_performance(strategy_id)

        # Aggregate across all strategies
        aggregated = self.feedback.get_aggregated_feedback()
        strategies = list(aggregated.get("strategies", {}).keys())

        if not strategies:
            return PerformanceMetrics()

        # Average metrics across strategies
        total_metrics = PerformanceMetrics()
        count = 0

        for strat_id in strategies:
            metrics = self.feedback.compute_strategy_performance(strat_id)
            if metrics.sample_count > 0:
                total_metrics.accuracy += metrics.accuracy
                total_metrics.precision += metrics.precision
                total_metrics.recall += metrics.recall
                total_metrics.f1_score += metrics.f1_score
                total_metrics.sharpe_ratio += metrics.sharpe_ratio
                total_metrics.win_rate += metrics.win_rate
                total_metrics.sample_count += metrics.sample_count
                count += 1

        if count > 0:
            total_metrics.accuracy /= count
            total_metrics.precision /= count
            total_metrics.recall /= count
            total_metrics.f1_score /= count
            total_metrics.sharpe_ratio /= count
            total_metrics.win_rate /= count

        return total_metrics

    def schedule_update(
        self,
        interval_hours: int | None = None,
        trigger: TriggerCondition = TriggerCondition.SCHEDULED,
    ) -> None:
        """Schedule a model update.

        Args:
            interval_hours: Hours until update (uses config default if None)
            trigger: Trigger condition for the update
        """
        interval = interval_hours or self.config.scheduler_config.default_interval_hours
        self.scheduler.schedule_recurring(interval, trigger)

    def check_and_adapt(self) -> AdaptationResult | None:
        """Check if adaptation is needed and perform it.

        Returns:
            AdaptationResult if adaptation was performed, None otherwise
        """
        should_update, trigger, reason = self.scheduler.should_update()

        if should_update and trigger:
            return self.scheduler.execute_next_task()

        return None

    def rollback(self, checkpoint_id: str | None = None) -> AdaptationResult:
        """Rollback to a previous model state.

        Args:
            checkpoint_id: Specific checkpoint to rollback to

        Returns:
            AdaptationResult
        """
        result = self.adapter.rollback(checkpoint_id)

        if result.status == AdaptationStatus.ROLLED_BACK:
            self._model_parameters = self.adapter.get_parameters()
            self._state.rollback_count += 1
            self._state.is_adapted = False

        return result

    def create_checkpoint(self) -> str:
        """Create a checkpoint of current state.

        Returns:
            Checkpoint ID
        """
        _metrics = self.get_performance_metrics()
        checkpoints = self.adapter.get_checkpoints()
        if checkpoints:
            return checkpoints[-1].checkpoint_id
        return ""

    def is_adapted(self) -> bool:
        """Check if the model has been adapted.

        Returns:
            True if model has been adapted from initial state
        """
        return self._state.is_adapted

    def get_state(self) -> EngineState:
        """Get current engine state."""
        return self._state

    def get_adaptation_history(self, limit: int = 100) -> list[AdaptationResult]:
        """Get recent adaptation history.

        Args:
            limit: Maximum number of results

        Returns:
            List of AdaptationResults
        """
        return self._adaptation_history[-limit:]

    def start_online_learning(self) -> None:
        """Start online learning mode."""
        self.config.enable_online_learning = True

    def stop_online_learning(self) -> None:
        """Stop online learning mode."""
        self.config.enable_online_learning = False

    def reset(self) -> None:
        """Reset the engine to initial state."""
        self.feedback.clear_history()
        self._gradients_buffer.clear()
        self._adaptation_history.clear()
        self._state = EngineState()
        self._state.is_adapted = False

    def save(self, path: Path) -> None:
        """Save engine state to disk.

        Args:
            path: Directory to save to
        """
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)

        # Save adapter
        self.adapter.save(path / "adapter")

        # Save engine state
        state_dict = {
            "is_adapted": self._state.is_adapted,
            "last_adaptation": self._state.last_adaptation.isoformat()
            if self._state.last_adaptation
            else None,
            "total_adaptations": self._state.total_adaptations,
            "successful_adaptations": self._state.successful_adaptations,
            "rollback_count": self._state.rollback_count,
            "start_time": self._state.start_time.isoformat(),
        }
        with open(path / "engine_state.json", "w") as f:
            json.dump(state_dict, f, indent=2)

        # Save config
        config_dict = {
            "enable_online_learning": self.config.enable_online_learning,
            "enable_auto_rollback": self.config.enable_auto_rollback,
            "checkpoint_interval_hours": self.config.checkpoint_interval_hours,
            "max_history_size": self.config.max_history_size,
            "learning_config": self.config.learning_config.to_dict(),
        }
        with open(path / "engine_config.json", "w") as f:
            json.dump(config_dict, f, indent=2)

    def load(self, path: Path) -> None:
        """Load engine state from disk.

        Args:
            path: Directory to load from
        """
        path = Path(path)

        # Load adapter
        if (path / "adapter").exists():
            self.adapter.load(path / "adapter")

        # Load engine state
        state_file = path / "engine_state.json"
        if state_file.exists():
            with open(state_file) as f:
                state_dict = json.load(f)

            self._state.is_adapted = state_dict.get("is_adapted", False)
            self._state.total_adaptations = state_dict.get("total_adaptations", 0)
            self._state.successful_adaptations = state_dict.get(
                "successful_adaptations", 0
            )
            self._state.rollback_count = state_dict.get("rollback_count", 0)

            if state_dict.get("last_adaptation"):
                self._state.last_adaptation = datetime.fromisoformat(
                    state_dict["last_adaptation"]
                )
            if state_dict.get("start_time"):
                self._state.start_time = datetime.fromisoformat(
                    state_dict["start_time"]
                )

    def get_status(self) -> dict[str, Any]:
        """Get comprehensive engine status.

        Returns:
            Status dictionary
        """
        return {
            "state": {
                "is_adapted": self._state.is_adapted,
                "total_adaptations": self._state.total_adaptations,
                "successful_adaptations": self._state.successful_adaptations,
                "rollback_count": self._state.rollback_count,
                "last_adaptation": self._state.last_adaptation.isoformat()
                if self._state.last_adaptation
                else None,
            },
            "config": {
                "online_learning": self.config.enable_online_learning,
                "auto_rollback": self.config.enable_auto_rollback,
            },
            "feedback": {
                "total_signals": len(self.feedback.history.signals),
                "strategies": len(self.feedback.history.rewards_by_strategy),
            },
            "scheduler": self.scheduler.to_dict(),
            "performance": self.get_performance_metrics().to_dict(),
        }

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"AdaptiveLearningEngine("
            f"adapted={self._state.is_adapted}, "
            f"total_adaptations={self._state.total_adaptations}, "
            f"signals={len(self.feedback.history.signals)})"
        )
