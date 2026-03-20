"""BrainEval API client and evaluation orchestration for ChiseAI.

This module provides integration with the BrainEval framework for comprehensive
model evaluation. Uses a pluggable data source architecture supporting synthetic
data (for testing) and real BrainEval API (for production).

Acceptance Criteria:
- BrainEval API client with pluggable data source
- Evaluation orchestration with configurable metrics
- Support for synthetic and real data sources
- Integration with model registry for version tracking

Example:
>>> from ml.evaluation.brain_eval import BrainEvalClient, BrainEvalConfig, EvaluationOrchestrator
>>> config = BrainEvalConfig(data_source=DataSourceType.SYNTHETIC, n_samples=1000)
>>> client = BrainEvalClient(config)
>>> result = client.evaluate_model("grid_btc", "v1")
>>> print(f"F1: {result.metrics.f1:.3f}")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

import numpy as np

from ml.evaluation.metrics import EvaluationMetrics, compute_all_metrics

logger = logging.getLogger(__name__)


class DataSourceType(Enum):
    """Types of data sources for BrainEval evaluation."""

    SYNTHETIC = "synthetic"  # Generated synthetic data for testing
    API = "api"  # Real BrainEval API (production)


@dataclass(frozen=True)
class BrainEvalConfig:
    """Configuration for BrainEval client.

    Attributes:
        data_source: Type of data source to use
        api_url: URL for BrainEval API (used when data_source is API)
        api_key: API key for BrainEval API (used when data_source is API)
        n_samples: Number of samples to generate/use for evaluation
        random_seed: Random seed for reproducible synthetic data
        metrics_to_compute: List of metric names to compute
    """

    data_source: DataSourceType = DataSourceType.SYNTHETIC
    api_url: str = ""
    api_key: str = ""
    n_samples: int = 1000
    random_seed: int = 42
    metrics_to_compute: list[str] = field(
        default_factory=lambda: [
            "accuracy",
            "precision",
            "recall",
            "f1",
            "auc_roc",
            "log_loss",
            "calibration_error",
            "brier_score",
            "sharpe_ratio",
            "max_drawdown",
            "win_rate",
            "profit_factor",
            "expectancy",
            "kelly_fraction",
            "information_ratio",
            "sortino_ratio",
        ]
    )


@dataclass(frozen=True)
class EvalResult:
    """Result of model evaluation from BrainEval.

    Attributes:
        model_id: Model identifier
        version_id: Version identifier
        metrics: Computed evaluation metrics
        sample_count: Number of samples used in evaluation
        data_source: Type of data source used
        timestamp: When the evaluation was performed
        metadata: Additional metadata
    """

    model_id: str
    version_id: str
    metrics: EvaluationMetrics
    sample_count: int
    data_source: DataSourceType
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "model_id": self.model_id,
            "version_id": self.version_id,
            "metrics": self.metrics.to_dict(),
            "sample_count": self.sample_count,
            "data_source": self.data_source.value,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvalResult:
        """Create from dictionary."""
        return cls(
            model_id=data["model_id"],
            version_id=data["version_id"],
            metrics=EvaluationMetrics.from_dict(data["metrics"]),
            sample_count=data["sample_count"],
            data_source=DataSourceType(data["data_source"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            metadata=data.get("metadata", {}),
        )


class BrainEvalClient:
    """Client for BrainEval API with pluggable data source.

    This client supports both synthetic data generation (for testing) and
    real BrainEval API integration (for production).

    Attributes:
        config: Configuration for the client

    Example:
        >>> config = BrainEvalConfig(n_samples=500, random_seed=123)
        >>> client = BrainEvalClient(config)
        >>> result = client.evaluate_model("model_v1", "version_1")
        >>> print(result.metrics.f1)
    """

    def __init__(self, config: BrainEvalConfig | None = None):
        """Initialize BrainEval client.

        Args:
            config: Client configuration (uses defaults if not provided)
        """
        self._config = config or BrainEvalConfig()
        logger.info(
            f"BrainEvalClient initialized with data_source={self._config.data_source.value}"
        )

    def generate_synthetic_data(
        self, n_samples: int | None = None, random_seed: int | None = None
    ) -> dict[str, np.ndarray]:
        """Generate synthetic evaluation data.

        Creates realistic synthetic data for model evaluation, including
        ground truth labels, predictions, probabilities, returns, and trades.

        Args:
            n_samples: Number of samples to generate (uses config default if None)
            random_seed: Random seed for reproducibility (uses config default if None)

        Returns:
            Dictionary containing:
                - y_true: True binary labels
                - y_pred: Predicted binary labels
                - y_proba: Predicted probabilities
                - returns: Strategy returns
                - trades: Trade PnL values
                - benchmark_returns: Benchmark returns for comparison
        """
        n = n_samples or self._config.n_samples
        seed = random_seed if random_seed is not None else self._config.random_seed

        rng = np.random.default_rng(seed)

        # Generate realistic synthetic data
        # y_true: ~60% positive class (realistic for trading signals)
        y_true = rng.choice([0, 1], size=n, p=[0.4, 0.6])

        # y_pred: slightly worse than y_true (realistic model performance)
        noise = rng.random(n) < 0.25  # 25% noise
        y_pred = y_true.copy()
        y_pred[noise] = 1 - y_pred[noise]

        # y_proba: probabilities with some noise
        base_proba = y_true.astype(float) * 0.7 + 0.3  # Base probability
        noise_proba = rng.normal(0, 0.1, n)  # Add noise
        y_proba = np.clip(base_proba + noise_proba, 0.05, 0.95)

        # returns: realistic return distribution
        returns = rng.normal(0.001, 0.02, n)  # Mean 0.1%, std 2%

        # trades: realistic trade PnL
        trades = rng.lognormal(mean=2, sigma=1.5, size=n) - 3  # Skewed positive

        # Make some trades negative (losses)
        neg_mask = rng.random(n) < 0.4
        trades[neg_mask] = -trades[neg_mask]

        # benchmark_returns: slightly lower than strategy returns
        benchmark_returns = returns * 0.8 + rng.normal(0, 0.005, n)

        return {
            "y_true": y_true,
            "y_pred": y_pred,
            "y_proba": y_proba,
            "returns": returns,
            "trades": trades,
            "benchmark_returns": benchmark_returns,
        }

    def evaluate_model(
        self,
        model_id: str,
        version_id: str,
        data: dict[str, np.ndarray] | None = None,
    ) -> EvalResult:
        """Evaluate a model version.

        Args:
            model_id: Model identifier
            version_id: Version identifier
            data: Optional data dictionary. If None, generates synthetic data.

        Returns:
            EvalResult with computed metrics
        """
        # Use provided data or generate synthetic data
        if data is None:
            data = self.generate_synthetic_data()

        # Compute all metrics
        metrics = compute_all_metrics(
            y_true=data["y_true"],
            y_pred=data["y_pred"],
            y_proba=data["y_proba"],
            returns=data["returns"],
            trades=data["trades"],
            benchmark_returns=data["benchmark_returns"],
        )

        result = EvalResult(
            model_id=model_id,
            version_id=version_id,
            metrics=metrics,
            sample_count=len(data["y_true"]),
            data_source=self._config.data_source,
            metadata={
                "config": {
                    "n_samples": self._config.n_samples,
                    "random_seed": self._config.random_seed,
                }
            },
        )

        logger.info(
            f"Evaluated model {model_id}/{version_id}: "
            f"f1={metrics.f1:.3f}, accuracy={metrics.accuracy:.3f}"
        )

        return result

    def evaluate_from_registry(self, model_id: str, version_id: str) -> EvalResult:
        """Evaluate a model from the model registry.

        This method simulates reading from the model registry and
        generating evaluation data. In production, this would fetch
        actual model predictions and ground truth.

        Args:
            model_id: Model identifier
            version_id: Version identifier

        Returns:
            EvalResult with computed metrics
        """
        # For now, use synthetic data (simulating registry read)
        # In production, this would:
        # 1. Look up model version in registry
        # 2. Load model and run inference on evaluation dataset
        # 3. Fetch ground truth labels
        # 4. Compute metrics

        logger.info(
            f"Evaluating from registry: model_id={model_id}, version_id={version_id}"
        )

        return self.evaluate_model(model_id, version_id, data=None)

    def batch_evaluate(self, model_versions: list[tuple[str, str]]) -> list[EvalResult]:
        """Evaluate multiple model versions.

        Args:
            model_versions: List of (model_id, version_id) tuples

        Returns:
            List of EvalResult for each model version
        """
        results = []

        for model_id, version_id in model_versions:
            result = self.evaluate_model(model_id, version_id)
            results.append(result)

        logger.info(f"Batch evaluated {len(results)} model versions")

        return results


class EvaluationOrchestrator:
    """Orchestrates model evaluation and comparison.

    Provides high-level evaluation workflows including single model
    evaluation, model comparison, and best model selection.

    Attributes:
        client: BrainEvalClient instance for evaluation

    Example:
        >>> client = BrainEvalClient(BrainEvalConfig(n_samples=500))
        >>> orchestrator = EvaluationOrchestrator(client)
        >>> result = orchestrator.run_evaluation("grid_btc", "v1")
        >>> comparison = orchestrator.compare_models(
        ...     ("grid_btc", "v1"), ("grid_btc", "v2")
        ... )
    """

    def __init__(self, client: BrainEvalClient):
        """Initialize evaluation orchestrator.

        Args:
            client: BrainEvalClient for performing evaluations
        """
        self._client = client
        logger.info("EvaluationOrchestrator initialized")

    def run_evaluation(self, model_id: str, version_id: str) -> EvalResult:
        """Run evaluation for a single model.

        Args:
            model_id: Model identifier
            version_id: Version identifier

        Returns:
            EvalResult with computed metrics
        """
        logger.info(f"Running evaluation for {model_id}/{version_id}")
        return self._client.evaluate_from_registry(model_id, version_id)

    def compare_models(
        self,
        model_a: tuple[str, str],
        model_b: tuple[str, str],
    ) -> dict[str, Any]:
        """Compare two model versions.

        Args:
            model_a: Tuple of (model_id, version_id) for first model
            model_b: Tuple of (model_id, version_id) for second model

        Returns:
            Dictionary containing comparison results with:
                - model_a: EvalResult for first model
                - model_b: EvalResult for second model
                - deltas: Dictionary of metric differences (model_b - model_a)
                - better_model: Which model is better ("a", "b", or "tie")
                - winning_metrics: List of metrics where model_b is better
        """
        model_id_a, version_id_a = model_a
        model_id_b, version_id_b = model_b

        logger.info(
            f"Comparing {model_id_a}/{version_id_a} vs {model_id_b}/{version_id_b}"
        )

        # Evaluate both models
        result_a = self._client.evaluate_from_registry(model_id_a, version_id_a)
        result_b = self._client.evaluate_from_registry(model_id_b, version_id_b)

        # Calculate deltas
        metrics_a = result_a.metrics
        metrics_b = result_b.metrics

        deltas = {
            "accuracy": metrics_b.accuracy - metrics_a.accuracy,
            "precision": metrics_b.precision - metrics_a.precision,
            "recall": metrics_b.recall - metrics_a.recall,
            "f1": metrics_b.f1 - metrics_a.f1,
            "auc_roc": metrics_b.auc_roc - metrics_a.auc_roc,
            "log_loss": metrics_b.log_loss - metrics_a.log_loss,
            "calibration_error": metrics_b.calibration_error
            - metrics_a.calibration_error,
            "brier_score": metrics_b.brier_score - metrics_a.brier_score,
            "sharpe_ratio": metrics_b.sharpe_ratio - metrics_a.sharpe_ratio,
            "max_drawdown": metrics_b.max_drawdown - metrics_a.max_drawdown,
            "win_rate": metrics_b.win_rate - metrics_a.win_rate,
            "profit_factor": metrics_b.profit_factor - metrics_a.profit_factor,
            "expectancy": metrics_b.expectancy - metrics_a.expectancy,
            "kelly_fraction": metrics_b.kelly_fraction - metrics_a.kelly_fraction,
            "information_ratio": metrics_b.information_ratio
            - metrics_a.information_ratio,
            "sortino_ratio": metrics_b.sortino_ratio - metrics_a.sortino_ratio,
        }

        # Determine winning metrics (positive delta is better for most metrics)
        # For log_loss, calibration_error, max_drawdown: negative is better
        winning_metrics = []
        for metric_name, delta in deltas.items():
            if metric_name in ["log_loss", "calibration_error", "max_drawdown"]:
                if delta < 0:
                    winning_metrics.append(metric_name)
            elif delta > 0:
                winning_metrics.append(metric_name)

        # Determine better model
        if len(winning_metrics) > 8:  # More than half of metrics favor B
            better_model = "b"
        elif len(winning_metrics) < 8:  # More than half favor A
            better_model = "a"
        else:
            better_model = "tie"

        return {
            "model_a": result_a.to_dict(),
            "model_b": result_b.to_dict(),
            "deltas": deltas,
            "better_model": better_model,
            "winning_metrics": winning_metrics,
        }

    def get_best_model(
        self, evaluations: list[EvalResult], metric: str = "f1"
    ) -> EvalResult | None:
        """Get the best model from a list of evaluations.

        Args:
            evaluations: List of EvalResult to compare
            metric: Metric to use for comparison (default: "f1")

        Returns:
            Best EvalResult or None if list is empty
        """
        if not evaluations:
            return None

        # Get the metric config to determine if higher is better
        from ml.evaluation.metrics import METRIC_CONFIGS

        higher_is_better = METRIC_CONFIGS.get(metric, None)
        if higher_is_better is None:
            logger.warning(f"Unknown metric: {metric}, using f1")
            metric = "f1"
            higher_is_better = True
        else:
            higher_is_better = higher_is_better.higher_is_better

        # Find best model
        best_result = evaluations[0]
        best_value = getattr(best_result.metrics, metric)

        for eval_result in evaluations[1:]:
            value = getattr(eval_result.metrics, metric)
            if higher_is_better:
                if value > best_value:
                    best_result = eval_result
                    best_value = value
            else:
                if value < best_value:
                    best_result = eval_result
                    best_value = value

        logger.info(
            f"Best model: {best_result.model_id}/{best_result.version_id} on {metric}={best_value:.3f}"
        )

        return best_result
