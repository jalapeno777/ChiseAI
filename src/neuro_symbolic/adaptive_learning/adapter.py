"""Model Adapter for adaptive learning.

Handles model parameter adjustments, hyperparameter optimization,
and A/B testing for model variants.
"""

import json
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from src.neuro_symbolic.learning.base import (
    AdaptationResult,
    AdaptationStatus,
    LearningConfig,
    ModelCheckpoint,
    PerformanceMetrics,
    TriggerCondition,
)


@dataclass
class HyperparameterSpace:
    """Defines a hyperparameter search space."""

    name: str
    min_value: float
    max_value: float
    current_value: float
    step: float | None = None
    log_scale: bool = False

    def sample(self) -> float:
        """Sample a value from the space."""
        if self.log_scale:
            log_min = np.log(self.min_value)
            log_max = np.log(self.max_value)
            return np.exp(np.random.uniform(log_min, log_max))
        return np.random.uniform(self.min_value, self.max_value)

    def clip(self, value: float) -> float:
        """Clip value to valid range."""
        return max(self.min_value, min(self.max_value, value))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "current_value": self.current_value,
            "step": self.step,
            "log_scale": self.log_scale,
        }


@dataclass
class ABTestVariant:
    """Represents a variant in A/B testing."""

    variant_id: str
    parameters: dict[str, Any]
    metrics: PerformanceMetrics | None = None
    sample_count: int = 0
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "variant_id": self.variant_id,
            "parameters": self.parameters,
            "metrics": self.metrics.to_dict() if self.metrics else None,
            "sample_count": self.sample_count,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class ABTest:
    """A/B test for comparing model variants."""

    test_id: str
    control_variant: ABTestVariant
    treatment_variants: list[ABTestVariant] = field(default_factory=list)
    traffic_split: list[float] = field(
        default_factory=list
    )  # Probability for each variant
    status: str = "running"  # running, completed, cancelled
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None
    winner_id: str | None = None
    confidence_level: float = 0.95

    def __post_init__(self):
        """Initialize traffic split if not provided."""
        if not self.traffic_split:
            n_variants = 1 + len(self.treatment_variants)
            self.traffic_split = [1.0 / n_variants] * n_variants

    def select_variant(self) -> ABTestVariant:
        """Select a variant based on traffic split."""
        variants = [self.control_variant] + self.treatment_variants
        idx = np.random.choice(len(variants), p=self.traffic_split)
        return variants[idx]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "test_id": self.test_id,
            "control_variant": self.control_variant.to_dict(),
            "treatment_variants": [v.to_dict() for v in self.treatment_variants],
            "traffic_split": self.traffic_split,
            "status": self.status,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
            "winner_id": self.winner_id,
            "confidence_level": self.confidence_level,
        }


@dataclass
class AdapterConfig:
    """Configuration for ModelAdapter."""

    adaptation_rate: float = 0.1
    momentum: float = 0.9
    min_improvement: float = 0.01
    max_parameter_change: float = 0.5
    checkpoint_dir: str | None = None
    max_checkpoints: int = 10
    ab_test_min_samples: int = 100
    ab_test_significance: float = 0.05


class ModelAdapter:
    """Adapts model parameters based on feedback.

    Handles parameter updates, hyperparameter optimization, and A/B testing.
    """

    def __init__(
        self,
        config: AdapterConfig | None = None,
        learning_config: LearningConfig | None = None,
    ):
        """Initialize the model adapter.

        Args:
            config: Adapter configuration
            learning_config: Learning system configuration
        """
        self.config = config or AdapterConfig()
        self.learning_config = learning_config or LearningConfig()
        self._parameters: dict[str, np.ndarray] = {}
        self._hyperparameter_spaces: dict[str, HyperparameterSpace] = {}
        self._checkpoints: list[ModelCheckpoint] = []
        self._adaptation_history: list[AdaptationResult] = []
        self._ab_tests: dict[str, ABTest] = {}
        self._active_ab_test: str | None = None
        self._velocity: dict[str, np.ndarray] = {}  # For momentum-based updates

    def set_parameters(self, parameters: dict[str, np.ndarray]) -> None:
        """Set model parameters.

        Args:
            parameters: Dictionary of parameter name to numpy array
        """
        self._parameters = deepcopy(parameters)
        # Initialize velocity for momentum
        self._velocity = {k: np.zeros_like(v) for k, v in parameters.items()}

    def get_parameters(self) -> dict[str, np.ndarray]:
        """Get current model parameters."""
        return deepcopy(self._parameters)

    def register_hyperparameter(
        self,
        name: str,
        min_value: float,
        max_value: float,
        current_value: float,
        step: float | None = None,
        log_scale: bool = False,
    ) -> None:
        """Register a hyperparameter for optimization.

        Args:
            name: Parameter name
            min_value: Minimum allowed value
            max_value: Maximum allowed value
            current_value: Current parameter value
            step: Optional step size for discrete parameters
            log_scale: Whether to use log scale for sampling
        """
        self._hyperparameter_spaces[name] = HyperparameterSpace(
            name=name,
            min_value=min_value,
            max_value=max_value,
            current_value=current_value,
            step=step,
            log_scale=log_scale,
        )

    def adapt(
        self,
        gradients: dict[str, np.ndarray],
        metrics: PerformanceMetrics | None = None,
        trigger: TriggerCondition | None = None,
    ) -> AdaptationResult:
        """Adapt model parameters based on gradients.

        Args:
            gradients: Dictionary of parameter gradients
            metrics: Current performance metrics
            trigger: What triggered this adaptation

        Returns:
            AdaptationResult describing the outcome
        """
        timestamp = datetime.now()
        previous_metrics = metrics

        try:
            # Create checkpoint before adaptation
            checkpoint = self._create_checkpoint(previous_metrics)
            self._checkpoints.append(checkpoint)

            # Trim old checkpoints
            if len(self._checkpoints) > self.config.max_checkpoints:
                self._checkpoints = self._checkpoints[-self.config.max_checkpoints :]

            # Apply momentum-based gradient updates
            params_changed = {}
            for param_name, grad in gradients.items():
                if param_name not in self._parameters:
                    continue

                # Initialize velocity if needed
                if param_name not in self._velocity:
                    self._velocity[param_name] = np.zeros_like(grad)

                # Momentum update
                self._velocity[param_name] = (
                    self.config.momentum * self._velocity[param_name]
                    + self.learning_config.learning_rate * grad
                )

                # Apply update with clipping
                update = np.clip(
                    self._velocity[param_name],
                    -self.config.max_parameter_change,
                    self.config.max_parameter_change,
                )
                self._parameters[param_name] += update
                params_changed[param_name] = {
                    "update_norm": float(np.linalg.norm(update)),
                    "grad_norm": float(np.linalg.norm(grad)),
                }

            result = AdaptationResult(
                status=AdaptationStatus.SUCCESS,
                timestamp=timestamp,
                previous_metrics=previous_metrics,
                parameters_changed=params_changed,
                rollback_available=True,
                trigger=trigger,
            )

        except Exception as e:
            result = AdaptationResult(
                status=AdaptationStatus.FAILED,
                timestamp=timestamp,
                previous_metrics=previous_metrics,
                error_message=str(e),
                trigger=trigger,
            )

        self._adaptation_history.append(result)
        return result

    def _create_checkpoint(
        self,
        metrics: PerformanceMetrics | None = None,
    ) -> ModelCheckpoint:
        """Create a checkpoint of current state."""
        checkpoint_id = f"ckpt_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        return ModelCheckpoint(
            checkpoint_id=checkpoint_id,
            parameters=deepcopy(self._parameters),
            metrics=metrics,
            config=self.learning_config,
        )

    def rollback(self, checkpoint_id: str | None = None) -> AdaptationResult:
        """Rollback to a previous checkpoint.

        Args:
            checkpoint_id: Specific checkpoint to rollback to (uses latest if None)

        Returns:
            AdaptationResult describing the rollback
        """
        if not self._checkpoints:
            return AdaptationResult(
                status=AdaptationStatus.FAILED,
                error_message="No checkpoints available for rollback",
            )

        # Find checkpoint
        if checkpoint_id:
            checkpoint = next(
                (c for c in self._checkpoints if c.checkpoint_id == checkpoint_id),
                None,
            )
            if not checkpoint:
                return AdaptationResult(
                    status=AdaptationStatus.FAILED,
                    error_message=f"Checkpoint {checkpoint_id} not found",
                )
        else:
            checkpoint = self._checkpoints[-1]

        # Restore parameters
        self._parameters = deepcopy(checkpoint.parameters)

        result = AdaptationResult(
            status=AdaptationStatus.ROLLED_BACK,
            previous_metrics=checkpoint.metrics,
            rollback_available=False,
        )

        self._adaptation_history.append(result)
        return result

    def optimize_hyperparameters(
        self,
        evaluation_fn: Callable[[dict[str, float]], PerformanceMetrics],
        n_iterations: int = 10,
        method: str = "random",
    ) -> tuple[dict[str, float], PerformanceMetrics]:
        """Optimize hyperparameters.

        Args:
            evaluation_fn: Function that evaluates a parameter set
            n_iterations: Number of optimization iterations
            method: Optimization method ('random', 'grid', 'bayesian')

        Returns:
            Tuple of (best parameters, best metrics)
        """
        best_params = {}
        best_metrics = PerformanceMetrics()

        for _ in range(n_iterations):
            # Sample parameters
            candidate_params = {}
            for name, space in self._hyperparameter_spaces.items():
                candidate_params[name] = space.sample()

            # Evaluate
            metrics = evaluation_fn(candidate_params)

            # Update best if improved
            if metrics.accuracy > best_metrics.accuracy:
                best_params = candidate_params.copy()
                best_metrics = metrics

                # Update current values in spaces
                for name, value in candidate_params.items():
                    self._hyperparameter_spaces[name].current_value = value

        # Update model with best parameters
        for name, _value in best_params.items():
            if name in self._parameters:
                # For scalar hyperparameters that are part of model
                pass  # Handled by learning rate adjustment in adapt()

        return best_params, best_metrics

    def create_ab_test(
        self,
        test_id: str,
        treatment_params: list[dict[str, Any]],
        traffic_split: list[float] | None = None,
    ) -> ABTest:
        """Create a new A/B test.

        Args:
            test_id: Unique test identifier
            treatment_params: List of parameter dictionaries for treatment variants
            traffic_split: Optional traffic split between variants

        Returns:
            Created ABTest
        """
        control = ABTestVariant(
            variant_id=f"{test_id}_control",
            parameters=deepcopy(self._parameters),
        )

        treatments = []
        for i, params in enumerate(treatment_params):
            variant = ABTestVariant(
                variant_id=f"{test_id}_treatment_{i}",
                parameters=params,
            )
            treatments.append(variant)

        ab_test = ABTest(
            test_id=test_id,
            control_variant=control,
            treatment_variants=treatments,
            traffic_split=traffic_split,
        )

        self._ab_tests[test_id] = ab_test
        self._active_ab_test = test_id

        return ab_test

    def get_ab_test_variant(self, test_id: str | None = None) -> ABTestVariant:
        """Get a variant for A/B testing.

        Args:
            test_id: Test ID (uses active test if None)

        Returns:
            Selected ABTestVariant
        """
        test_id = test_id or self._active_ab_test
        if not test_id or test_id not in self._ab_tests:
            # Return current parameters as control
            return ABTestVariant(
                variant_id="default",
                parameters=deepcopy(self._parameters),
            )

        return self._ab_tests[test_id].select_variant()

    def record_ab_test_result(
        self,
        test_id: str,
        variant_id: str,
        metrics: PerformanceMetrics,
    ) -> None:
        """Record results for an A/B test variant.

        Args:
            test_id: Test identifier
            variant_id: Variant identifier
            metrics: Performance metrics for the variant
        """
        if test_id not in self._ab_tests:
            return

        ab_test = self._ab_tests[test_id]

        # Find and update variant
        if variant_id == ab_test.control_variant.variant_id:
            ab_test.control_variant.metrics = metrics
            ab_test.control_variant.sample_count += 1
        else:
            for variant in ab_test.treatment_variants:
                if variant.variant_id == variant_id:
                    variant.metrics = metrics
                    variant.sample_count += 1
                    break

    def analyze_ab_test(
        self,
        test_id: str,
    ) -> dict[str, Any]:
        """Analyze A/B test results.

        Args:
            test_id: Test identifier

        Returns:
            Analysis results including winner if determined
        """
        if test_id not in self._ab_tests:
            return {"error": f"Test {test_id} not found"}

        ab_test = self._ab_tests[test_id]
        variants = [ab_test.control_variant] + ab_test.treatment_variants

        # Check if we have enough samples
        min_samples = min(v.sample_count for v in variants)
        if min_samples < self.config.ab_test_min_samples:
            return {
                "status": "insufficient_data",
                "min_samples": min_samples,
                "required_samples": self.config.ab_test_min_samples,
            }

        # Find best variant
        best_variant = max(
            variants, key=lambda v: v.metrics.accuracy if v.metrics else 0
        )

        # Simple significance check (would use proper statistical test in production)
        all_accuracies = [v.metrics.accuracy for v in variants if v.metrics is not None]

        if len(all_accuracies) < 2:
            return {"status": "incomplete", "message": "Not all variants have metrics"}

        best_accuracy = max(all_accuracies)
        second_best = sorted(all_accuracies, reverse=True)[1]
        improvement = best_accuracy - second_best

        # Determine if improvement is significant
        is_significant = improvement > self.config.ab_test_significance

        result = {
            "test_id": test_id,
            "status": "analyzed",
            "best_variant": best_variant.variant_id,
            "best_accuracy": best_accuracy,
            "improvement": improvement,
            "is_significant": is_significant,
            "variants": [
                {
                    "id": v.variant_id,
                    "accuracy": v.metrics.accuracy if v.metrics else None,
                    "sample_count": v.sample_count,
                }
                for v in variants
            ],
        }

        # Complete test if significant
        if is_significant:
            ab_test.status = "completed"
            ab_test.winner_id = best_variant.variant_id
            ab_test.completed_at = datetime.now()

            # Apply winning parameters if treatment
            if best_variant != ab_test.control_variant:
                self._parameters = deepcopy(best_variant.parameters)

            result["status"] = "completed"
            result["winner"] = best_variant.variant_id

        return result

    def get_active_ab_test(self) -> ABTest | None:
        """Get the currently active A/B test."""
        if self._active_ab_test and self._active_ab_test in self._ab_tests:
            return self._ab_tests[self._active_ab_test]
        return None

    def cancel_ab_test(self, test_id: str) -> bool:
        """Cancel an A/B test.

        Args:
            test_id: Test to cancel

        Returns:
            True if cancelled successfully
        """
        if test_id in self._ab_tests:
            self._ab_tests[test_id].status = "cancelled"
            if self._active_ab_test == test_id:
                self._active_ab_test = None
            return True
        return False

    def get_adaptation_history(
        self,
        limit: int = 100,
    ) -> list[AdaptationResult]:
        """Get recent adaptation history.

        Args:
            limit: Maximum number of results to return

        Returns:
            List of recent AdaptationResults
        """
        return self._adaptation_history[-limit:]

    def get_checkpoints(self) -> list[ModelCheckpoint]:
        """Get all available checkpoints."""
        return self._checkpoints.copy()

    def save(self, path: str | Path) -> None:
        """Save adapter state to disk.

        Args:
            path: Directory to save to
        """
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)

        # Save parameters
        params_dict = {k: v.tolist() for k, v in self._parameters.items()}
        with open(path / "parameters.json", "w") as f:
            json.dump(params_dict, f)

        # Save hyperparameter spaces
        spaces_dict = {k: v.to_dict() for k, v in self._hyperparameter_spaces.items()}
        with open(path / "hyperparameters.json", "w") as f:
            json.dump(spaces_dict, f)

        # Save checkpoints metadata
        checkpoints_meta = [
            {
                "checkpoint_id": c.checkpoint_id,
                "timestamp": c.timestamp.isoformat(),
                "has_metrics": c.metrics is not None,
            }
            for c in self._checkpoints
        ]
        with open(path / "checkpoints_meta.json", "w") as f:
            json.dump(checkpoints_meta, f)

    def load(self, path: str | Path) -> None:
        """Load adapter state from disk.

        Args:
            path: Directory to load from
        """
        path = Path(path)

        # Load parameters
        params_file = path / "parameters.json"
        if params_file.exists():
            with open(params_file) as f:
                params_dict = json.load(f)
            self._parameters = {k: np.array(v) for k, v in params_dict.items()}

        # Load hyperparameter spaces
        spaces_file = path / "hyperparameters.json"
        if spaces_file.exists():
            with open(spaces_file) as f:
                spaces_dict = json.load(f)
            for name, data in spaces_dict.items():
                self._hyperparameter_spaces[name] = HyperparameterSpace(**data)

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"ModelAdapter("
            f"params={len(self._parameters)}, "
            f"checkpoints={len(self._checkpoints)}, "
            f"ab_tests={len(self._ab_tests)})"
        )
