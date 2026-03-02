"""Feedback Integrator for adaptive learning.

Processes trade outcomes and generates learning signals for model adaptation.
"""

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np
from src.neuro_symbolic.learning.base import (
    FeedbackSignal,
    PerformanceMetrics,
    SignalType,
)


@dataclass
class FeedbackHistory:
    """Tracks historical feedback signals."""

    signals: deque[FeedbackSignal] = field(default_factory=lambda: deque(maxlen=1000))
    rewards_by_strategy: dict[str, deque[float]] = field(default_factory=dict)
    penalties_by_strategy: dict[str, deque[float]] = field(default_factory=dict)

    def add_signal(self, signal: FeedbackSignal) -> None:
        """Add a feedback signal to history."""
        self.signals.append(signal)

        strategy = signal.strategy_id
        if strategy not in self.rewards_by_strategy:
            self.rewards_by_strategy[strategy] = deque(maxlen=100)
            self.penalties_by_strategy[strategy] = deque(maxlen=100)

        if signal.signal_type == SignalType.REWARD:
            self.rewards_by_strategy[strategy].append(signal.value)
        elif signal.signal_type == SignalType.PENALTY:
            self.penalties_by_strategy[strategy].append(abs(signal.value))

    def get_strategy_stats(self, strategy_id: str) -> dict[str, float]:
        """Get statistics for a specific strategy."""
        rewards = list(self.rewards_by_strategy.get(strategy_id, []))
        penalties = list(self.penalties_by_strategy.get(strategy_id, []))

        return {
            "total_rewards": sum(rewards),
            "total_penalties": sum(penalties),
            "avg_reward": np.mean(rewards) if rewards else 0.0,
            "avg_penalty": np.mean(penalties) if penalties else 0.0,
            "reward_count": len(rewards),
            "penalty_count": len(penalties),
            "net_signal": sum(rewards) - sum(penalties),
        }

    def clear(self) -> None:
        """Clear all history."""
        self.signals.clear()
        self.rewards_by_strategy.clear()
        self.penalties_by_strategy.clear()


@dataclass
class IntegratorConfig:
    """Configuration for FeedbackIntegrator."""

    history_size: int = 1000
    reward_scale: float = 1.0
    penalty_scale: float = 1.5  # Penalize losses more heavily
    decay_rate: float = 0.95
    min_samples_for_stats: int = 10
    profit_threshold: float = 0.0
    loss_threshold: float = -0.05
    confidence_weight: float = 0.3
    outcome_weight: float = 0.7


class FeedbackIntegrator:
    """Integrates trade outcomes into learning signals.

    Processes trade results and generates appropriate reward/penalty signals
    for model adaptation.
    """

    def __init__(self, config: IntegratorConfig | None = None):
        """Initialize the feedback integrator.

        Args:
            config: Integrator configuration
        """
        self.config = config or IntegratorConfig()
        self.history = FeedbackHistory()
        self._pending_feedback: list[FeedbackSignal] = []
        self._last_integration_time: datetime | None = None
        self._integration_count: int = 0

    def process_trade_outcome(
        self,
        strategy_id: str,
        outcome: dict[str, Any],
        trade_id: str | None = None,
        symbol: str | None = None,
    ) -> FeedbackSignal:
        """Process a trade outcome and generate feedback signal.

        Args:
            strategy_id: ID of the strategy that made the trade
            outcome: Trade outcome dictionary containing:
                - pnl: Profit/loss amount
                - pnl_pct: Profit/loss percentage
                - confidence: Model confidence for the trade
                - duration: Trade duration
                - exit_reason: Reason for exiting trade
            trade_id: Optional trade identifier
            symbol: Optional trading symbol

        Returns:
            Generated FeedbackSignal
        """
        pnl = outcome.get("pnl", 0.0)
        pnl_pct = outcome.get("pnl_pct", 0.0)
        confidence = outcome.get("confidence", 0.5)
        duration = outcome.get("duration", 0)
        exit_reason = outcome.get("exit_reason", "unknown")

        # Determine signal type and value
        signal_type, value = self._compute_signal(pnl, pnl_pct, confidence, exit_reason)

        # Create feedback signal
        signal = FeedbackSignal(
            signal_type=signal_type,
            value=value,
            strategy_id=strategy_id,
            trade_id=trade_id,
            symbol=symbol,
            metadata={
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "confidence": confidence,
                "duration": duration,
                "exit_reason": exit_reason,
            },
        )

        # Add to history
        self.history.add_signal(signal)
        self._pending_feedback.append(signal)

        return signal

    def _compute_signal(
        self,
        pnl: float,
        pnl_pct: float,
        confidence: float,
        exit_reason: str,
    ) -> tuple[SignalType, float]:
        """Compute feedback signal type and value.

        Args:
            pnl: Profit/loss amount
            pnl_pct: Profit/loss percentage
            confidence: Model confidence
            exit_reason: Reason for trade exit

        Returns:
            Tuple of (signal_type, value)
        """
        # Base signal from PnL
        if pnl > self.config.profit_threshold:
            signal_type = SignalType.REWARD
            # Scale reward by confidence and profit magnitude
            base_value = abs(pnl_pct) * self.config.reward_scale
            confidence_bonus = confidence * self.config.confidence_weight
            value = base_value * (1 + confidence_bonus)
        elif pnl < self.config.loss_threshold:
            signal_type = SignalType.PENALTY
            # Scale penalty (often heavier to discourage losses)
            base_value = abs(pnl_pct) * self.config.penalty_scale
            confidence_penalty = confidence * self.config.confidence_weight
            value = -(base_value * (1 + confidence_penalty))
        else:
            signal_type = SignalType.NEUTRAL
            value = 0.0

        # Adjust for exit reason
        if exit_reason == "stop_loss":
            # Stop loss hit - minor penalty for risk management working
            if signal_type == SignalType.REWARD:
                signal_type = SignalType.NEUTRAL
                value = 0.0
        elif exit_reason == "take_profit":
            # Take profit hit - bonus for good target setting
            if signal_type == SignalType.REWARD:
                value *= 1.2
        elif exit_reason == "timeout":
            # Timed out - slight penalty for indecision
            if signal_type == SignalType.NEUTRAL:
                signal_type = SignalType.PENALTY
                value = -0.01

        return signal_type, value

    def integrate_batch(
        self,
        outcomes: list[dict[str, Any]],
        strategy_id: str,
    ) -> list[FeedbackSignal]:
        """Integrate a batch of trade outcomes.

        Args:
            outcomes: List of trade outcome dictionaries
            strategy_id: Strategy ID for all outcomes

        Returns:
            List of generated feedback signals
        """
        signals = []
        for outcome in outcomes:
            signal = self.process_trade_outcome(
                strategy_id=strategy_id,
                outcome=outcome,
                trade_id=outcome.get("trade_id"),
                symbol=outcome.get("symbol"),
            )
            signals.append(signal)

        self._integration_count += len(signals)
        self._last_integration_time = datetime.now()

        return signals

    def compute_strategy_performance(
        self,
        strategy_id: str,
        window: int | None = None,
    ) -> PerformanceMetrics:
        """Compute performance metrics for a strategy.

        Args:
            strategy_id: Strategy to analyze
            window: Optional window size for recent performance

        Returns:
            PerformanceMetrics for the strategy
        """
        stats = self.history.get_strategy_stats(strategy_id)

        # Get recent signals
        recent_signals = [
            s for s in self.history.signals if s.strategy_id == strategy_id
        ]
        if window:
            recent_signals = recent_signals[-window:]

        if len(recent_signals) < self.config.min_samples_for_stats:
            return PerformanceMetrics(sample_count=len(recent_signals))

        # Compute metrics
        rewards = [
            s.value for s in recent_signals if s.signal_type == SignalType.REWARD
        ]
        penalties = [
            abs(s.value) for s in recent_signals if s.signal_type == SignalType.PENALTY
        ]

        total_trades = len(recent_signals)
        winning_trades = len(rewards)

        win_rate = winning_trades / total_trades if total_trades > 0 else 0.0
        _avg_win = np.mean(rewards) if rewards else 0.0
        _avg_loss = np.mean(penalties) if penalties else 0.0

        # Profit factor
        profit_factor = (
            sum(rewards) / sum(penalties)
            if penalties and sum(penalties) > 0
            else float("inf") if rewards else 0.0
        )

        # Compute Sharpe-like ratio
        returns = [s.value for s in recent_signals]
        avg_return = np.mean(returns) if returns else 0.0
        std_return = np.std(returns) if len(returns) > 1 else 0.0
        sharpe = avg_return / std_return if std_return > 0 else 0.0

        # Max drawdown approximation
        cumulative = np.cumsum(returns)
        running_max = np.maximum.accumulate(cumulative)
        drawdowns = running_max - cumulative
        max_drawdown = np.max(drawdowns) if len(drawdowns) > 0 else 0.0

        # Approximate precision/recall from win rate and profit factor
        precision = win_rate  # Approximation
        recall = (
            min(win_rate * profit_factor, 1.0)
            if profit_factor != float("inf")
            else win_rate
        )
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )

        return PerformanceMetrics(
            accuracy=win_rate,
            precision=precision,
            recall=recall,
            f1_score=f1,
            sharpe_ratio=sharpe,
            win_rate=win_rate,
            profit_factor=min(profit_factor, 10.0),  # Cap for numerical stability
            max_drawdown=max_drawdown,
            sample_count=total_trades,
            per_strategy={strategy_id: stats},
        )

    def get_aggregated_feedback(
        self,
        strategy_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Get aggregated feedback across strategies.

        Args:
            strategy_ids: Optional list of strategies to include

        Returns:
            Aggregated feedback statistics
        """
        signals = list(self.history.signals)

        if strategy_ids:
            signals = [s for s in signals if s.strategy_id in strategy_ids]

        if not signals:
            return {"total_signals": 0, "strategies": {}}

        # Aggregate by strategy
        strategy_stats = {}
        for strategy_id in set(s.strategy_id for s in signals):
            strategy_stats[strategy_id] = self.history.get_strategy_stats(strategy_id)

        # Overall stats
        rewards = [s.value for s in signals if s.signal_type == SignalType.REWARD]
        penalties = [s.value for s in signals if s.signal_type == SignalType.PENALTY]

        return {
            "total_signals": len(signals),
            "total_rewards": len(rewards),
            "total_penalties": len(penalties),
            "net_signal": sum(rewards) + sum(penalties),
            "avg_reward": np.mean(rewards) if rewards else 0.0,
            "avg_penalty": np.mean(penalties) if penalties else 0.0,
            "strategies": strategy_stats,
            "last_integration": (
                self._last_integration_time.isoformat()
                if self._last_integration_time
                else None
            ),
        }

    def get_pending_feedback(self) -> list[FeedbackSignal]:
        """Get and clear pending feedback signals.

        Returns:
            List of pending feedback signals
        """
        pending = self._pending_feedback.copy()
        self._pending_feedback.clear()
        return pending

    def apply_decay(self) -> None:
        """Apply time decay to historical signals.

        Reduces the weight of older signals.
        """
        now = datetime.now()
        for signal in self.history.signals:
            age_seconds = (now - signal.timestamp).total_seconds()
            decay_factor = self.config.decay_rate ** (
                age_seconds / 3600
            )  # Decay per hour
            signal.value *= decay_factor

    def clear_history(self) -> None:
        """Clear all feedback history."""
        self.history.clear()
        self._pending_feedback.clear()

    def get_recent_signals(
        self,
        n: int = 100,
        strategy_id: str | None = None,
    ) -> list[FeedbackSignal]:
        """Get the n most recent feedback signals.

        Args:
            n: Number of signals to return
            strategy_id: Optional filter by strategy

        Returns:
            List of recent feedback signals
        """
        signals = list(self.history.signals)

        if strategy_id:
            signals = [s for s in signals if s.strategy_id == strategy_id]

        return signals[-n:]

    def to_feature_vector(
        self,
        strategy_id: str,
        window: int = 50,
    ) -> np.ndarray:
        """Convert recent feedback to a feature vector for learning.

        Args:
            strategy_id: Strategy to get features for
            window: Number of recent signals to include

        Returns:
            Feature vector as numpy array
        """
        signals = self.get_recent_signals(window, strategy_id)

        if not signals:
            return np.zeros(window * 3)

        # Pad if necessary
        if len(signals) < window:
            padding = [FeedbackSignal(SignalType.NEUTRAL, 0.0, strategy_id)] * (
                window - len(signals)
            )
            signals = padding + signals

        # Convert to features
        features = []
        for signal in signals[-window:]:
            features.extend(
                [
                    signal.value,
                    1.0 if signal.signal_type == SignalType.REWARD else 0.0,
                    1.0 if signal.signal_type == SignalType.PENALTY else 0.0,
                ]
            )

        return np.array(features)

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"FeedbackIntegrator("
            f"signals={len(self.history.signals)}, "
            f"strategies={len(self.history.rewards_by_strategy)}, "
            f"pending={len(self._pending_feedback)})"
        )
