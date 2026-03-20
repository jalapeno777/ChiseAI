"""Evaluation metrics for ML models in ChiseAI.

This module provides comprehensive evaluation metrics for classification,
regression, trading, and calibration tasks. All metrics are implemented as
dataclasses with to_dict/from_dict serialization support.

Acceptance Criteria:
- 16 evaluation metrics across 4 categories
- MetricConfig for metric metadata
- MetricResult for individual metric results
- EvaluationMetrics for holding all metric values
- Individual computation functions for each metric
- compute_all_metrics for batch computation

Example:
>>> from ml.evaluation.metrics import (
...     compute_all_metrics,
...     EvaluationMetrics,
...     MetricCategory,
... )
>>> metrics = compute_all_metrics(
...     y_true=[1, 0, 1, 1, 0],
...     y_pred=[1, 0, 1, 0, 0],
...     y_proba=[0.9, 0.2, 0.8, 0.4, 0.3],
...     returns=[0.01, -0.005, 0.02, 0.015, -0.01],
...     trades=[100, -50, 150, 80, -30],
...     benchmark_returns=[0.008, -0.003, 0.015, 0.01, -0.008],
... )
>>> print(f"Accuracy: {metrics.accuracy:.3f}, F1: {metrics.f1:.3f}")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


class MetricCategory(Enum):
    """Categories of evaluation metrics."""

    CLASSIFICATION = "classification"
    REGRESSION = "regression"
    TRADING = "trading"
    CALIBRATION = "calibration"


@dataclass
class MetricConfig:
    """Configuration for a metric.

    Attributes:
        name: Metric name
        category: Metric category
        description: Human-readable description
        higher_is_better: Whether higher values are better
        min_value: Minimum possible value
        max_value: Maximum possible value
    """

    name: str
    category: MetricCategory
    description: str
    higher_is_better: bool
    min_value: float = 0.0
    max_value: float = 1.0


@dataclass(frozen=True)
class MetricResult:
    """Result of a single metric computation.

    Attributes:
        name: Metric name
        value: Computed metric value
        category: Metric category
        timestamp: When the metric was computed
        metadata: Additional metadata
    """

    name: str
    value: float
    category: MetricCategory
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "value": self.value,
            "category": self.category.value,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MetricResult:
        """Create from dictionary."""
        return cls(
            name=data["name"],
            value=data["value"],
            category=MetricCategory(data["category"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            metadata=data.get("metadata", {}),
        )


@dataclass(frozen=True)
class EvaluationMetrics:
    """Container for all 16 evaluation metrics.

    Classification metrics:
        accuracy: Classification accuracy
        precision: Precision score
        recall: Recall score
        f1: F1 score
        auc_roc: Area Under ROC Curve
        log_loss: Log loss (cross-entropy)

    Calibration metrics:
        calibration_error: Expected Calibration Error (ECE)
        brier_score: Brier score

    Trading metrics:
        sharpe_ratio: Sharpe ratio
        max_drawdown: Maximum drawdown
        win_rate: Win rate
        profit_factor: Profit factor
        expectancy: Trade expectancy
        kelly_fraction: Kelly criterion fraction

    Risk-adjusted metrics:
        information_ratio: Information ratio
        sortino_ratio: Sortino ratio
    """

    # Classification metrics
    accuracy: float = 0.0
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
    auc_roc: float = 0.0
    log_loss: float = 0.0

    # Calibration metrics
    calibration_error: float = 0.0
    brier_score: float = 0.0

    # Trading metrics
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    kelly_fraction: float = 0.0

    # Risk-adjusted metrics
    information_ratio: float = 0.0
    sortino_ratio: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            # Classification
            "accuracy": self.accuracy,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "auc_roc": self.auc_roc,
            "log_loss": self.log_loss,
            # Calibration
            "calibration_error": self.calibration_error,
            "brier_score": self.brier_score,
            # Trading
            "sharpe_ratio": self.sharpe_ratio,
            "max_drawdown": self.max_drawdown,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "expectancy": self.expectancy,
            "kelly_fraction": self.kelly_fraction,
            # Risk-adjusted
            "information_ratio": self.information_ratio,
            "sortino_ratio": self.sortino_ratio,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvaluationMetrics:
        """Create from dictionary."""
        return cls(
            # Classification
            accuracy=data.get("accuracy", 0.0),
            precision=data.get("precision", 0.0),
            recall=data.get("recall", 0.0),
            f1=data.get("f1", 0.0),
            auc_roc=data.get("auc_roc", 0.0),
            log_loss=data.get("log_loss", 0.0),
            # Calibration
            calibration_error=data.get("calibration_error", 0.0),
            brier_score=data.get("brier_score", 0.0),
            # Trading
            sharpe_ratio=data.get("sharpe_ratio", 0.0),
            max_drawdown=data.get("max_drawdown", 0.0),
            win_rate=data.get("win_rate", 0.0),
            profit_factor=data.get("profit_factor", 0.0),
            expectancy=data.get("expectancy", 0.0),
            kelly_fraction=data.get("kelly_fraction", 0.0),
            # Risk-adjusted
            information_ratio=data.get("information_ratio", 0.0),
            sortino_ratio=data.get("sortino_ratio", 0.0),
        )


# =============================================================================
# Metric Configurations
# =============================================================================

METRIC_CONFIGS: dict[str, MetricConfig] = {
    # Classification metrics
    "accuracy": MetricConfig(
        name="accuracy",
        category=MetricCategory.CLASSIFICATION,
        description="Classification accuracy (proportion of correct predictions)",
        higher_is_better=True,
        min_value=0.0,
        max_value=1.0,
    ),
    "precision": MetricConfig(
        name="precision",
        category=MetricCategory.CLASSIFICATION,
        description="Precision (positive predictive value)",
        higher_is_better=True,
        min_value=0.0,
        max_value=1.0,
    ),
    "recall": MetricConfig(
        name="recall",
        category=MetricCategory.CLASSIFICATION,
        description="Recall (sensitivity, true positive rate)",
        higher_is_better=True,
        min_value=0.0,
        max_value=1.0,
    ),
    "f1": MetricConfig(
        name="f1",
        category=MetricCategory.CLASSIFICATION,
        description="F1 score (harmonic mean of precision and recall)",
        higher_is_better=True,
        min_value=0.0,
        max_value=1.0,
    ),
    "auc_roc": MetricConfig(
        name="auc_roc",
        category=MetricCategory.CLASSIFICATION,
        description="Area Under ROC Curve",
        higher_is_better=True,
        min_value=0.0,
        max_value=1.0,
    ),
    "log_loss": MetricConfig(
        name="log_loss",
        category=MetricCategory.CLASSIFICATION,
        description="Log loss (cross-entropy loss)",
        higher_is_better=False,
        min_value=0.0,
        max_value=float("inf"),
    ),
    # Calibration metrics
    "calibration_error": MetricConfig(
        name="calibration_error",
        category=MetricCategory.CALIBRATION,
        description="Expected Calibration Error (ECE)",
        higher_is_better=False,
        min_value=0.0,
        max_value=1.0,
    ),
    "brier_score": MetricConfig(
        name="brier_score",
        category=MetricCategory.CALIBRATION,
        description="Brier score (mean squared error of probabilities)",
        higher_is_better=False,
        min_value=0.0,
        max_value=1.0,
    ),
    # Trading metrics
    "sharpe_ratio": MetricConfig(
        name="sharpe_ratio",
        category=MetricCategory.TRADING,
        description="Sharpe ratio (risk-adjusted return)",
        higher_is_better=True,
        min_value=float("-inf"),
        max_value=float("inf"),
    ),
    "max_drawdown": MetricConfig(
        name="max_drawdown",
        category=MetricCategory.TRADING,
        description="Maximum drawdown (largest peak-to-trough decline)",
        higher_is_better=False,
        min_value=0.0,
        max_value=1.0,
    ),
    "win_rate": MetricConfig(
        name="win_rate",
        category=MetricCategory.TRADING,
        description="Win rate (proportion of profitable trades)",
        higher_is_better=True,
        min_value=0.0,
        max_value=1.0,
    ),
    "profit_factor": MetricConfig(
        name="profit_factor",
        category=MetricCategory.TRADING,
        description="Profit factor (gross profit / gross loss)",
        higher_is_better=True,
        min_value=0.0,
        max_value=float("inf"),
    ),
    "expectancy": MetricConfig(
        name="expectancy",
        category=MetricCategory.TRADING,
        description="Average profit per trade",
        higher_is_better=True,
        min_value=float("-inf"),
        max_value=float("inf"),
    ),
    "kelly_fraction": MetricConfig(
        name="kelly_fraction",
        category=MetricCategory.TRADING,
        description="Kelly criterion (optimal bet sizing)",
        higher_is_better=True,
        min_value=0.0,
        max_value=1.0,
    ),
    # Risk-adjusted metrics
    "information_ratio": MetricConfig(
        name="information_ratio",
        category=MetricCategory.TRADING,
        description="Information ratio (active return / tracking error)",
        higher_is_better=True,
        min_value=float("-inf"),
        max_value=float("inf"),
    ),
    "sortino_ratio": MetricConfig(
        name="sortino_ratio",
        category=MetricCategory.TRADING,
        description="Sortino ratio (return / downside deviation)",
        higher_is_better=True,
        min_value=float("-inf"),
        max_value=float("inf"),
    ),
}


# =============================================================================
# Classification Metric Functions
# =============================================================================


def compute_accuracy(predictions: np.ndarray, labels: np.ndarray) -> float:
    """Compute classification accuracy.

    Args:
        predictions: Predicted class labels
        labels: True class labels

    Returns:
        Accuracy score (0.0 to 1.0)
    """
    if len(predictions) == 0 or len(labels) == 0:
        return 0.0

    predictions = np.asarray(predictions)
    labels = np.asarray(labels)

    if len(predictions) != len(labels):
        logger.warning("Predictions and labels length mismatch")
        return 0.0

    correct = np.sum(predictions == labels)
    return float(correct / len(labels))


def compute_precision(predictions: np.ndarray, labels: np.ndarray) -> float:
    """Compute precision score.

    Args:
        predictions: Predicted class labels
        labels: True class labels

    Returns:
        Precision score (0.0 to 1.0)
    """
    if len(predictions) == 0 or len(labels) == 0:
        return 0.0

    predictions = np.asarray(predictions)
    labels = np.asarray(labels)

    if len(predictions) != len(labels):
        return 0.0

    # True positives: predicted positive and actually positive
    tp = np.sum((predictions == 1) & (labels == 1))
    # False positives: predicted positive but actually negative
    fp = np.sum((predictions == 1) & (labels == 0))

    if tp + fp == 0:
        return 0.0

    return float(tp / (tp + fp))


def compute_recall(predictions: np.ndarray, labels: np.ndarray) -> float:
    """Compute recall score (sensitivity).

    Args:
        predictions: Predicted class labels
        labels: True class labels

    Returns:
        Recall score (0.0 to 1.0)
    """
    if len(predictions) == 0 or len(labels) == 0:
        return 0.0

    predictions = np.asarray(predictions)
    labels = np.asarray(labels)

    if len(predictions) != len(labels):
        return 0.0

    # True positives: predicted positive and actually positive
    tp = np.sum((predictions == 1) & (labels == 1))
    # False negatives: predicted negative but actually positive
    fn = np.sum((predictions == 0) & (labels == 1))

    if tp + fn == 0:
        return 0.0

    return float(tp / (tp + fn))


def compute_f1(predictions: np.ndarray, labels: np.ndarray) -> float:
    """Compute F1 score (harmonic mean of precision and recall).

    Args:
        predictions: Predicted class labels
        labels: True class labels

    Returns:
        F1 score (0.0 to 1.0)
    """
    precision = compute_precision(predictions, labels)
    recall = compute_recall(predictions, labels)

    if precision + recall == 0:
        return 0.0

    return float(2 * (precision * recall) / (precision + recall))


def compute_auc_roc(scores: np.ndarray, labels: np.ndarray) -> float:
    """Compute Area Under ROC Curve.

    Args:
        scores: Prediction scores (probabilities or logits)
        labels: True class labels (binary)

    Returns:
        AUC-ROC score (0.0 to 1.0)
    """
    if len(scores) == 0 or len(labels) == 0:
        return 0.0

    scores = np.asarray(scores)
    labels = np.asarray(labels)

    if len(scores) != len(labels):
        return 0.0

    # Handle edge case where all labels are the same
    if np.all(labels == labels[0]) or np.std(scores) == 0:
        return 0.5

    # Sort by scores in descending order
    sorted_indices = np.argsort(scores)[::-1]
    labels_sorted = labels[sorted_indices]

    # Calculate TPR and FPR at each threshold
    n_pos = np.sum(labels == 1)
    n_neg = np.sum(labels == 0)

    if n_pos == 0 or n_neg == 0:
        return 0.5

    # Count pairs where positive score > negative score
    tp = 0
    for i, label in enumerate(labels_sorted):
        if label == 1:
            tp += np.sum(labels_sorted[i + 1 :] == 0)

    auc = tp / (n_pos * n_neg)
    return float(auc)


def compute_log_loss(probabilities: np.ndarray, labels: np.ndarray) -> float:
    """Compute log loss (cross-entropy loss).

    Args:
        probabilities: Predicted probabilities for positive class
        labels: True class labels (binary)

    Returns:
        Log loss value (0.0 to infinity, lower is better)
    """
    if len(probabilities) == 0 or len(labels) == 0:
        return 0.0

    probabilities = np.asarray(probabilities)
    labels = np.asarray(labels)

    if len(probabilities) != len(labels):
        return 0.0

    # Clip probabilities to avoid log(0)
    eps = 1e-15
    probabilities = np.clip(probabilities, eps, 1 - eps)

    # Compute log loss
    loss = -np.mean(
        labels * np.log(probabilities) + (1 - labels) * np.log(1 - probabilities)
    )

    return float(loss)


# =============================================================================
# Calibration Metric Functions
# =============================================================================


def compute_calibration_error(
    probabilities: np.ndarray, labels: np.ndarray, n_bins: int = 10
) -> float:
    """Compute Expected Calibration Error (ECE).

    Args:
        probabilities: Predicted probabilities for positive class
        labels: True class labels (binary)
        n_bins: Number of confidence bins

    Returns:
        ECE value (0.0 to 1.0, lower is better)
    """
    if len(probabilities) == 0 or len(labels) == 0:
        return 0.0

    probabilities = np.asarray(probabilities)
    labels = np.asarray(labels)

    if len(probabilities) != len(labels):
        return 0.0

    # Create bins
    bin_edges = np.linspace(0, 1, n_bins + 1)
    ece = 0.0

    for i in range(n_bins):
        bin_lower = bin_edges[i]
        bin_upper = bin_edges[i + 1]

        # Find samples in this bin
        in_bin = (probabilities > bin_lower) & (probabilities <= bin_upper)
        bin_count = np.sum(in_bin)

        if bin_count == 0:
            continue

        # Compute accuracy and confidence in this bin
        bin_accuracy = np.mean(labels[in_bin])
        bin_confidence = np.mean(probabilities[in_bin])

        # Add weighted absolute difference
        ece += (bin_count / len(probabilities)) * abs(bin_accuracy - bin_confidence)

    return float(ece)


def compute_brier_score(probabilities: np.ndarray, labels: np.ndarray) -> float:
    """Compute Brier score (mean squared error of probabilities).

    Args:
        probabilities: Predicted probabilities for positive class
        labels: True class labels (binary)

    Returns:
        Brier score (0.0 to 1.0, lower is better)
    """
    if len(probabilities) == 0 or len(labels) == 0:
        return 0.0

    probabilities = np.asarray(probabilities)
    labels = np.asarray(labels)

    if len(probabilities) != len(labels):
        return 0.0

    # Compute Brier score
    brier = np.mean((probabilities - labels) ** 2)

    return float(brier)


# =============================================================================
# Trading Metric Functions
# =============================================================================


def compute_sharpe_ratio(returns: np.ndarray, risk_free_rate: float = 0.0) -> float:
    """Compute Sharpe ratio.

    Args:
        returns: Array of returns
        risk_free_rate: Risk-free rate (default 0.0)

    Returns:
        Sharpe ratio (can be negative)
    """
    if len(returns) == 0:
        return 0.0

    returns = np.asarray(returns)

    # Calculate excess returns
    excess_returns = returns - risk_free_rate

    # Calculate mean and std
    mean_return = np.mean(excess_returns)
    std_return = np.std(excess_returns, ddof=1)

    if std_return == 0 or np.isnan(std_return):
        return 0.0

    # Annualize (assuming daily returns, 252 trading days)
    sharpe = (mean_return / std_return) * np.sqrt(252)

    return float(sharpe)


def compute_max_drawdown(returns: np.ndarray) -> float:
    """Compute maximum drawdown.

    Args:
        returns: Array of returns

    Returns:
        Maximum drawdown (0.0 to 1.0, lower is better)
    """
    if len(returns) == 0:
        return 0.0

    returns = np.asarray(returns)

    # Calculate cumulative returns
    cumulative = np.cumprod(1 + returns)

    # Calculate running maximum
    running_max = np.maximum.accumulate(cumulative)

    # Calculate drawdown
    drawdown = (cumulative - running_max) / running_max

    # Return maximum drawdown (negative value)
    max_dd = np.min(drawdown)

    return float(abs(max_dd) if np.isfinite(max_dd) else 0.0)


def compute_win_rate(trades: np.ndarray) -> float:
    """Compute win rate (proportion of profitable trades).

    Args:
        trades: Array of trade PnL values

    Returns:
        Win rate (0.0 to 1.0)
    """
    if len(trades) == 0:
        return 0.0

    trades = np.asarray(trades)

    winning_trades = np.sum(trades > 0)
    total_trades = len(trades)

    if total_trades == 0:
        return 0.0

    return float(winning_trades / total_trades)


def compute_profit_factor(trades: np.ndarray) -> float:
    """Compute profit factor (gross profit / gross loss).

    Args:
        trades: Array of trade PnL values

    Returns:
        Profit factor (>= 0, higher is better)
    """
    if len(trades) == 0:
        return 0.0

    trades = np.asarray(trades)

    gross_profit = np.sum(trades[trades > 0])
    gross_loss = abs(np.sum(trades[trades < 0]))

    if gross_loss == 0:
        # If no losses, return infinity-like value or large number
        return float("inf") if gross_profit > 0 else 0.0

    return float(gross_profit / gross_loss)


def compute_expectancy(trades: np.ndarray) -> float:
    """Compute trade expectancy (average profit per trade).

    Args:
        trades: Array of trade PnL values

    Returns:
        Expectancy (can be negative)
    """
    if len(trades) == 0:
        return 0.0

    trades = np.asarray(trades)

    expectancy = np.mean(trades)

    return float(expectancy) if np.isfinite(expectancy) else 0.0


def compute_kelly_fraction(win_rate: float, avg_win: float, avg_loss: float) -> float:
    """Compute Kelly criterion fraction (optimal bet sizing).

    Args:
        win_rate: Proportion of winning trades (0.0 to 1.0)
        avg_win: Average win amount
        avg_loss: Average loss amount (positive value)

    Returns:
        Kelly fraction (0.0 to 1.0, optimal Kelly)
    """
    if win_rate <= 0 or win_rate >= 1 or avg_win <= 0 or avg_loss <= 0:
        return 0.0

    # Kelly formula: f* = p - q/b where p=win_rate, q=1-p, b=avg_win/avg_loss
    win_prob = win_rate
    loss_prob = 1 - win_rate
    win_loss_ratio = avg_win / avg_loss

    if win_loss_ratio == 0:
        return 0.0

    kelly = win_prob - (loss_prob / win_loss_ratio)

    # Kelly should be between 0 and 1
    return float(max(0.0, min(1.0, kelly)))


# =============================================================================
# Risk-Adjusted Metric Functions
# =============================================================================


def compute_information_ratio(
    returns: np.ndarray, benchmark_returns: np.ndarray
) -> float:
    """Compute information ratio (active return / tracking error).

    Args:
        returns: Strategy returns
        benchmark_returns: Benchmark returns

    Returns:
        Information ratio (can be negative)
    """
    if len(returns) == 0 or len(benchmark_returns) == 0:
        return 0.0

    returns = np.asarray(returns)
    benchmark_returns = np.asarray(benchmark_returns)

    if len(returns) != len(benchmark_returns):
        return 0.0

    # Calculate active returns (excess returns over benchmark)
    active_returns = returns - benchmark_returns

    # Calculate mean active return
    mean_active = np.mean(active_returns)

    # Calculate tracking error (std of active returns)
    tracking_error = np.std(active_returns, ddof=1)

    if tracking_error == 0 or np.isnan(tracking_error):
        return 0.0

    # Annualize (assuming daily returns)
    ir = (mean_active / tracking_error) * np.sqrt(252)

    return float(ir)


def compute_sortino_ratio(returns: np.ndarray, risk_free_rate: float = 0.0) -> float:
    """Compute Sortino ratio (return / downside deviation).

    Args:
        returns: Array of returns
        risk_free_rate: Risk-free rate (default 0.0)

    Returns:
        Sortino ratio (can be negative)
    """
    if len(returns) == 0:
        return 0.0

    returns = np.asarray(returns)

    # Calculate excess returns
    excess_returns = returns - risk_free_rate

    # Calculate mean return
    mean_return = np.mean(excess_returns)

    # Calculate downside deviation (only negative returns)
    negative_returns = excess_returns[excess_returns < 0]

    if len(negative_returns) == 0:
        # No negative returns - perfect scenario
        return float("inf") if mean_return > 0 else 0.0

    downside_std = np.std(negative_returns, ddof=1)

    if downside_std == 0 or np.isnan(downside_std):
        return 0.0

    # Annualize (assuming daily returns)
    sortino = (mean_return / downside_std) * np.sqrt(252)

    return float(sortino)


# =============================================================================
# Combined Metric Computation
# =============================================================================


def compute_all_metrics(
    y_true: list[int] | np.ndarray,
    y_pred: list[int] | np.ndarray,
    y_proba: list[float] | np.ndarray,
    returns: list[float] | np.ndarray,
    trades: list[float] | np.ndarray,
    benchmark_returns: list[float] | np.ndarray | None = None,
) -> EvaluationMetrics:
    """Compute all 16 evaluation metrics.

    Args:
        y_true: True class labels (binary)
        y_pred: Predicted class labels
        y_proba: Predicted probabilities for positive class
        returns: Strategy returns
        trades: Trade PnL values
        benchmark_returns: Optional benchmark returns for information ratio

    Returns:
        EvaluationMetrics with all computed values
    """
    # Convert to numpy arrays
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    y_proba = np.asarray(y_proba)
    returns = np.asarray(returns)
    trades = np.asarray(trades)

    if benchmark_returns is not None:
        benchmark_returns = np.asarray(benchmark_returns)
    else:
        # Use zero returns as default benchmark
        benchmark_returns = np.zeros_like(returns)

    # Calculate average win and loss for Kelly criterion
    winning_trades = trades[trades > 0]
    losing_trades = trades[trades < 0]

    avg_win = float(np.mean(winning_trades)) if len(winning_trades) > 0 else 0.0
    avg_loss = float(abs(np.mean(losing_trades))) if len(losing_trades) > 0 else 0.0
    win_rate = compute_win_rate(trades)

    # Compute all metrics
    metrics = EvaluationMetrics(
        # Classification metrics
        accuracy=compute_accuracy(y_pred, y_true),
        precision=compute_precision(y_pred, y_true),
        recall=compute_recall(y_pred, y_true),
        f1=compute_f1(y_pred, y_true),
        auc_roc=compute_auc_roc(y_proba, y_true),
        log_loss=compute_log_loss(y_proba, y_true),
        # Calibration metrics
        calibration_error=compute_calibration_error(y_proba, y_true),
        brier_score=compute_brier_score(y_proba, y_true),
        # Trading metrics
        sharpe_ratio=compute_sharpe_ratio(returns),
        max_drawdown=compute_max_drawdown(returns),
        win_rate=win_rate,
        profit_factor=compute_profit_factor(trades),
        expectancy=compute_expectancy(trades),
        kelly_fraction=compute_kelly_fraction(win_rate, avg_win, avg_loss),
        # Risk-adjusted metrics
        information_ratio=compute_information_ratio(returns, benchmark_returns),
        sortino_ratio=compute_sortino_ratio(returns),
    )

    return metrics
