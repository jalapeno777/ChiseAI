"""Base classes and data structures for learning systems.

Provides foundational types for adaptive learning including feedback signals,
performance metrics, and adaptation results.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
import numpy as np


class SignalType(Enum):
    """Types of feedback signals."""

    REWARD = "reward"
    PENALTY = "penalty"
    NEUTRAL = "neutral"


class AdaptationStatus(Enum):
    """Status of model adaptation."""

    SUCCESS = "success"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    SKIPPED = "skipped"


class TriggerCondition(Enum):
    """Conditions that trigger model updates."""

    PERFORMANCE_DEGRADATION = "performance_degradation"
    SCHEDULED = "scheduled"
    THRESHOLD_BREACH = "threshold_breach"
    DATA_DRIFT = "data_drift"
    MANUAL = "manual"


@dataclass
class LearningConfig:
    """Configuration for learning systems."""

    learning_rate: float = 0.001
    min_samples_for_adaptation: int = 100
    performance_window: int = 100
    degradation_threshold: float = 0.1
    adaptation_cooldown: int = 3600  # seconds
    max_adaptations_per_day: int = 10
    rollback_threshold: float = 0.2
    confidence_threshold: float = 0.7
    enable_auto_rollback: bool = True
    validation_split: float = 0.2

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "learning_rate": self.learning_rate,
            "min_samples_for_adaptation": self.min_samples_for_adaptation,
            "performance_window": self.performance_window,
            "degradation_threshold": self.degradation_threshold,
            "adaptation_cooldown": self.adaptation_cooldown,
            "max_adaptations_per_day": self.max_adaptations_per_day,
            "rollback_threshold": self.rollback_threshold,
            "confidence_threshold": self.confidence_threshold,
            "enable_auto_rollback": self.enable_auto_rollback,
            "validation_split": self.validation_split,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LearningConfig":
        """Create from dictionary."""
        return cls(**{k: v for k, v in data.items() if hasattr(cls, k)})


@dataclass
class FeedbackSignal:
    """Represents a feedback signal from trade outcomes.

    Encapsulates reward/penalty information for learning.
    """

    signal_type: SignalType
    value: float
    strategy_id: str
    timestamp: datetime = field(default_factory=datetime.now)
    trade_id: Optional[str] = None
    symbol: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate signal after initialization."""
        if self.signal_type == SignalType.REWARD and self.value < 0:
            raise ValueError("Reward signal must have non-negative value")
        if self.signal_type == SignalType.PENALTY and self.value > 0:
            raise ValueError("Penalty signal must have non-positive value")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "signal_type": self.signal_type.value,
            "value": self.value,
            "strategy_id": self.strategy_id,
            "timestamp": self.timestamp.isoformat(),
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FeedbackSignal":
        """Create from dictionary."""
        return cls(
            signal_type=SignalType(data["signal_type"]),
            value=data["value"],
            strategy_id=data["strategy_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            trade_id=data.get("trade_id"),
            symbol=data.get("symbol"),
            metadata=data.get("metadata", {}),
        )

    def to_array(self) -> np.ndarray:
        """Convert to numpy array for processing."""
        return np.array(
            [
                self.value,
                1.0 if self.signal_type == SignalType.REWARD else 0.0,
                1.0 if self.signal_type == SignalType.PENALTY else 0.0,
            ]
        )


@dataclass
class PerformanceMetrics:
    """Performance metrics for model evaluation.

    Tracks various metrics for assessing model performance.
    """

    accuracy: float = 0.0
    precision: float = 0.0
    recall: float = 0.0
    f1_score: float = 0.0
    sharpe_ratio: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    max_drawdown: float = 0.0
    sample_count: int = 0
    timestamp: datetime = field(default_factory=datetime.now)
    per_strategy: Dict[str, Dict[str, float]] = field(default_factory=dict)

    def __post_init__(self):
        """Validate metrics after initialization."""
        for attr in ["accuracy", "precision", "recall", "f1_score", "win_rate"]:
            value = getattr(self, attr)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{attr} must be between 0 and 1, got {value}")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "accuracy": self.accuracy,
            "precision": self.precision,
            "recall": self.recall,
            "f1_score": self.f1_score,
            "sharpe_ratio": self.sharpe_ratio,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "max_drawdown": self.max_drawdown,
            "sample_count": self.sample_count,
            "timestamp": self.timestamp.isoformat(),
            "per_strategy": self.per_strategy,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PerformanceMetrics":
        """Create from dictionary."""
        return cls(
            accuracy=data.get("accuracy", 0.0),
            precision=data.get("precision", 0.0),
            recall=data.get("recall", 0.0),
            f1_score=data.get("f1_score", 0.0),
            sharpe_ratio=data.get("sharpe_ratio", 0.0),
            win_rate=data.get("win_rate", 0.0),
            profit_factor=data.get("profit_factor", 0.0),
            max_drawdown=data.get("max_drawdown", 0.0),
            sample_count=data.get("sample_count", 0),
            timestamp=datetime.fromisoformat(data["timestamp"])
            if "timestamp" in data
            else datetime.now(),
            per_strategy=data.get("per_strategy", {}),
        )

    def compute_degradation(self, other: "PerformanceMetrics") -> float:
        """Compute performance degradation relative to another metric set.

        Args:
            other: Reference metrics to compare against

        Returns:
            Degradation value (positive means degradation)
        """
        # Weighted combination of key metrics
        weights = {
            "accuracy": 0.3,
            "f1_score": 0.25,
            "sharpe_ratio": 0.25,
            "win_rate": 0.2,
        }

        degradation = 0.0
        for metric, weight in weights.items():
            current = getattr(self, metric)
            reference = getattr(other, metric)
            degradation += weight * (reference - current)

        return degradation

    def is_significantly_worse(
        self, other: "PerformanceMetrics", threshold: float = 0.1
    ) -> bool:
        """Check if this metric set is significantly worse than another.

        Args:
            other: Reference metrics
            threshold: Degradation threshold

        Returns:
            True if significantly worse
        """
        return self.compute_degradation(other) > threshold

    def to_array(self) -> np.ndarray:
        """Convert to numpy array for processing."""
        return np.array(
            [
                self.accuracy,
                self.precision,
                self.recall,
                self.f1_score,
                self.sharpe_ratio,
                self.win_rate,
                self.profit_factor,
                self.max_drawdown,
            ]
        )


@dataclass
class AdaptationResult:
    """Result of a model adaptation attempt.

    Contains information about the adaptation outcome.
    """

    status: AdaptationStatus
    timestamp: datetime = field(default_factory=datetime.now)
    previous_metrics: Optional[PerformanceMetrics] = None
    new_metrics: Optional[PerformanceMetrics] = None
    parameters_changed: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None
    adaptation_id: str = ""
    rollback_available: bool = False
    trigger: Optional[TriggerCondition] = None

    def __post_init__(self):
        """Generate adaptation ID if not provided."""
        if not self.adaptation_id:
            self.adaptation_id = f"adapt_{self.timestamp.strftime('%Y%m%d_%H%M%S')}"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "status": self.status.value,
            "timestamp": self.timestamp.isoformat(),
            "previous_metrics": self.previous_metrics.to_dict()
            if self.previous_metrics
            else None,
            "new_metrics": self.new_metrics.to_dict() if self.new_metrics else None,
            "parameters_changed": self.parameters_changed,
            "error_message": self.error_message,
            "adaptation_id": self.adaptation_id,
            "rollback_available": self.rollback_available,
            "trigger": self.trigger.value if self.trigger else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AdaptationResult":
        """Create from dictionary."""
        return cls(
            status=AdaptationStatus(data["status"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            previous_metrics=PerformanceMetrics.from_dict(data["previous_metrics"])
            if data.get("previous_metrics")
            else None,
            new_metrics=PerformanceMetrics.from_dict(data["new_metrics"])
            if data.get("new_metrics")
            else None,
            parameters_changed=data.get("parameters_changed", {}),
            error_message=data.get("error_message"),
            adaptation_id=data.get("adaptation_id", ""),
            rollback_available=data.get("rollback_available", False),
            trigger=TriggerCondition(data["trigger"]) if data.get("trigger") else None,
        )

    @property
    def is_successful(self) -> bool:
        """Check if adaptation was successful."""
        return self.status == AdaptationStatus.SUCCESS

    @property
    def improvement(self) -> Optional[float]:
        """Compute improvement in accuracy if both metrics available."""
        if self.previous_metrics and self.new_metrics:
            return self.new_metrics.accuracy - self.previous_metrics.accuracy
        return None


@dataclass
class ModelCheckpoint:
    """Checkpoint for model state rollback.

    Stores model parameters for potential rollback.
    """

    checkpoint_id: str
    timestamp: datetime = field(default_factory=datetime.now)
    parameters: Dict[str, np.ndarray] = field(default_factory=dict)
    metrics: Optional[PerformanceMetrics] = None
    config: Optional[LearningConfig] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary (without numpy arrays)."""
        return {
            "checkpoint_id": self.checkpoint_id,
            "timestamp": self.timestamp.isoformat(),
            "parameters": {k: v.tolist() for k, v in self.parameters.items()},
            "metrics": self.metrics.to_dict() if self.metrics else None,
            "config": self.config.to_dict() if self.config else None,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelCheckpoint":
        """Create from dictionary."""
        return cls(
            checkpoint_id=data["checkpoint_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            parameters={k: np.array(v) for k, v in data.get("parameters", {}).items()},
            metrics=PerformanceMetrics.from_dict(data["metrics"])
            if data.get("metrics")
            else None,
            config=LearningConfig.from_dict(data["config"])
            if data.get("config")
            else None,
            metadata=data.get("metadata", {}),
        )
