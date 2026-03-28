"""Training pipeline for autocog calibration models.

This module provides the main integration layer for autocog model training,
combining gradient learning primitives with training loop, batch processing,
checkpointing, and validation.

Features:
- Integration with gradient_learning primitives (GradientComputer, Optimizer, etc.)
- Epoch-based training with early stopping
- Configurable batch processing
- Model checkpointing (best, top N, rollback)
- Validation using TrainingDataLoader (70/15/15 split)
- Constitution audit approval for parameter updates

Example:
    from src.autonomous_cognition.training import create_autocog_pipeline

    # Create pipeline
    pipeline = create_autocog_pipeline(
        params={"threshold": 0.5, "learning_rate": 0.01},
        metric_fns={"calibration_error": compute_calibration_error},
        config=AutocogTrainingConfig(
            max_epochs=100,
            batch_size=32,
        ),
    )

    # Run training
    result = await pipeline.train(training_data, validation_data)

    # Get best model
    best_params = pipeline.get_best_params()
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from src.autonomous_cognition.gradient_learning import (
    ClipMode,
    GradientLearningOptimizer,
    ParameterUpdateRejected,
    ScheduleType,
)
from src.ml.training.training_pipeline import TrainingConfig

from .batch_processor import Batch, BatchProcessor, create_batch_processor
from .checkpointing import (
    CheckpointType,
    ModelCheckpoint,
    ModelCheckpointConfig,
    ModelCheckpointing,
    create_model_checkpointing,
)
from .training_loop import (
    EarlyStoppingMode,
    EpochMetrics,
    TrainingLoop,
    TrainingLoopState,
)
from .validation import (
    ValidationMetrics,
    ValidationSplit,
    ValidationSplitManager,
    create_validation_split_manager,
)

logger = logging.getLogger(__name__)


@dataclass
class AutocogTrainingConfig:
    """Configuration for autocog training pipeline.

    Attributes:
        max_epochs: Maximum training epochs
        batch_size: Batch size for training
        early_stopping_patience: Epochs before early stopping
        early_stopping_metric: Metric to use for early stopping
        early_stopping_direction: 'minimize' or 'maximize'
        learning_rate: Initial learning rate
        optimizer_type: 'SGD' or 'Adam'
        scheduler_type: Learning rate schedule type
        gradient_clip_mode: Gradient clipping mode
        gradient_clip_norm: Max gradient norm for clipping
        checkpoint_dir: Directory for model checkpoints
        max_checkpoints: Maximum checkpoints to keep
        constitution_audit_required: Require audit for parameter updates
        require_constitution_audit: Alias for constitution_audit_required
    """

    max_epochs: int = 100
    batch_size: int = 32
    early_stopping_patience: int = 10
    early_stopping_metric: str = "val_loss"
    early_stopping_direction: str = "minimize"
    learning_rate: float = 0.01
    optimizer_type: str = "SGD"
    scheduler_type: str = "exponential"
    gradient_clip_mode: str = "norm"
    gradient_clip_norm: float = 1.0
    checkpoint_dir: str = "checkpoints/autocog"
    max_checkpoints: int = 5
    constitution_audit_required: bool = True
    require_constitution_audit: bool = True  # Alias

    # Split ratios (70/15/15 default)
    train_ratio: float = 0.70
    validation_ratio: float = 0.15
    test_ratio: float = 0.15
    random_seed: int = 42

    def __post_init__(self) -> None:
        """Validate configuration."""
        if not self.require_constitution_audit:
            self.constitution_audit_required = False

        total = self.train_ratio + self.validation_ratio + self.test_ratio
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"Split ratios must sum to 1.0, got {total}")


@dataclass
class AutocogTrainingResult:
    """Result of autocog training.

    Attributes:
        success: Whether training succeeded
        final_state: Final training loop state
        best_params: Best model parameters
        best_metrics: Metrics at best checkpoint
        training_history: List of epoch metrics
        checkpoint_info: Information about saved checkpoints
    """

    success: bool = False
    final_state: TrainingLoopState | None = None
    best_params: dict[str, float] = field(default_factory=dict)
    best_metrics: dict[str, float] = field(default_factory=dict)
    training_history: list[EpochMetrics] = field(default_factory=list)
    checkpoint_info: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "final_state": self.final_state.to_dict() if self.final_state else None,
            "best_params": self.best_params,
            "best_metrics": self.best_metrics,
            "training_history": [e.to_dict() for e in self.training_history],
            "checkpoint_info": self.checkpoint_info,
        }


class AutocogTrainingPipeline:
    """Training pipeline for autocog calibration models.

    Integrates:
    - GradientLearningOptimizer (gradient computation, optimization, clipping)
    - TrainingLoop (epoch-based training, early stopping)
    - BatchProcessor (batch processing, shuffling)
    - ModelCheckpointing (best model, top N, rollback)
    - ValidationSplitManager (70/15/15 split, metrics computation)

    All parameter updates go through constitution_audit approval.

    Example:
        pipeline = AutocogTrainingPipeline(
            params={"threshold": 0.5},
            metric_fns={"calibration_error": compute_calibration_error},
            constitution_audit_fn=audit_fn,
        )

        result = await pipeline.train(
            train_samples=train_data,
            val_samples=val_data,
        )
    """

    def __init__(
        self,
        params: dict[str, float],
        metric_fns: dict[str, Callable[[dict[str, float]], float]],
        config: AutocogTrainingConfig | None = None,
        constitution_audit_fn: Callable[[dict[str, Any]], bool] | None = None,
        gradient_optimizer: GradientLearningOptimizer | None = None,
    ):
        """Initialize autocog training pipeline.

        Args:
            params: Initial model parameters
            metric_fns: Dictionary of metric functions to optimize
            config: Training configuration
            constitution_audit_fn: Function to approve parameter updates
            gradient_optimizer: Pre-configured gradient optimizer
        """
        self.params = params.copy()
        self.metric_fns = metric_fns
        self.config = config or AutocogTrainingConfig()
        self.constitution_audit_fn = constitution_audit_fn

        # Create validation split manager
        self._validation_manager = ValidationSplitManager(
            config=TrainingConfig(
                train_ratio=self.config.train_ratio,
                validation_ratio=self.config.validation_ratio,
                test_ratio=self.config.test_ratio,
                random_seed=self.config.random_seed,
            )
        )

        # Create batch processor
        self._batch_processor = create_batch_processor(
            batch_size=self.config.batch_size,
            shuffle=True,
        )

        # Create checkpointing
        self._checkpointing = create_model_checkpointing(
            checkpoint_dir=self.config.checkpoint_dir,
            max_checkpoints=self.config.max_checkpoints,
            metric_name=self.config.early_stopping_metric,
            metric_direction=self.config.early_stopping_direction,
            save_best_only=True,
        )

        # Create or use provided gradient optimizer
        if gradient_optimizer:
            self._gradient_optimizer = gradient_optimizer
        else:
            self._gradient_optimizer = self._create_gradient_optimizer()

        # Training state
        self._current_params = params.copy()
        self._training_history: list[EpochMetrics] = []
        self._is_training = False

    def _create_gradient_optimizer(self) -> GradientLearningOptimizer:
        """Create the gradient learning optimizer.

        Returns:
            Configured GradientLearningOptimizer
        """
        # Map scheduler type string to ScheduleType enum
        scheduler_type_map = {
            "exponential": ScheduleType.EXPONENTIAL,
            "step": ScheduleType.STEP,
            "cosine": ScheduleType.COSINE,
        }
        scheduler_type = scheduler_type_map.get(
            self.config.scheduler_type.lower(), ScheduleType.EXPONENTIAL
        )

        # Map clip mode string to ClipMode enum
        clip_mode_map = {
            "norm": ClipMode.NORM,
            "value": ClipMode.VALUE,
        }
        clip_mode = clip_mode_map.get(
            self.config.gradient_clip_mode.lower(), ClipMode.NORM
        )

        return GradientLearningOptimizer(
            params=self.params.copy(),
            metric_fns=self.metric_fns,
            constitution_audit_fn=self.constitution_audit_fn,
            optimizer_type=self.config.optimizer_type.upper(),
            learning_rate=self.config.learning_rate,
            scheduler_type=scheduler_type,
            clip_mode=clip_mode,
            clip_max_norm=self.config.gradient_clip_norm,
            checkpoint_dir=f"{self.config.checkpoint_dir}/gradient",
            checkpoint_every=self.config.max_epochs + 1,  # Only manual saves
            require_audit=self.config.constitution_audit_required,
        )

    @property
    def validation_manager(self) -> ValidationSplitManager:
        """Get validation manager."""
        return self._validation_manager

    @property
    def batch_processor(self) -> BatchProcessor:
        """Get batch processor."""
        return self._batch_processor

    @property
    def checkpointing(self) -> ModelCheckpointing:
        """Get checkpointing manager."""
        return self._checkpointing

    @property
    def gradient_optimizer(self) -> GradientLearningOptimizer:
        """Get gradient optimizer."""
        return self._gradient_optimizer

    @property
    def current_params(self) -> dict[str, float]:
        """Get current parameters."""
        return self._current_params.copy()

    @property
    def training_history(self) -> list[EpochMetrics]:
        """Get training history."""
        return self._training_history.copy()

    def get_best_params(self) -> dict[str, float]:
        """Get best parameters from checkpointing.

        Returns:
            Best model parameters
        """
        return self._checkpointing.get_best_params() or self._current_params.copy()

    def get_best_metrics(self) -> dict[str, float]:
        """Get metrics from best checkpoint.

        Returns:
            Best model metrics
        """
        return self._checkpointing.get_best_metrics() or {}

    async def train(
        self,
        train_samples: list[Any],
        val_samples: list[Any] | None = None,
        test_samples: list[Any] | None = None,
    ) -> AutocogTrainingResult:
        """Run the training pipeline.

        Args:
            train_samples: Training samples
            val_samples: Optional validation samples (uses split if not provided)
            test_samples: Optional test samples

        Returns:
            AutocogTrainingResult with training outcome
        """
        self._is_training = True
        self._training_history = []

        logger.info(
            f"Starting autocog training: epochs={self.config.max_epochs}, "
            f"batch_size={self.config.batch_size}"
        )

        try:
            # If val_samples not provided, split from train_samples
            if val_samples is None:
                split = self._validation_manager.create_split(train_samples)
                train_data = split.train_data
                val_data = split.val_data
            else:
                train_data = train_samples
                val_data = val_samples

            # Create batches
            batches = self._batch_processor.process(train_data)

            # Create training loop with callbacks
            def checkpoint_callback(epoch: int, metrics: EpochMetrics) -> None:
                self._checkpointing.check_and_save(
                    epoch=epoch,
                    params=self._current_params,
                    metrics={
                        "val_loss": metrics.val_loss,
                        "val_metric": metrics.val_metric,
                    },
                    checkpoint_type=CheckpointType.PERIODIC,
                )

            loop = TrainingLoop(
                max_epochs=self.config.max_epochs,
                early_stopping_patience=self.config.early_stopping_patience,
                early_stopping_mode=EarlyStoppingMode.PATIENCE,
                early_stopping_metric_direction=self.config.early_stopping_direction,
                checkpoint_callback=checkpoint_callback,
            )

            # Define training step
            async def train_step(
                params: dict[str, float], batch: Batch
            ) -> tuple[float, dict[str, Any]]:
                """Train on a batch."""
                try:
                    result = self._gradient_optimizer.step(
                        rationale=f"Training batch at epoch {loop.state.current_epoch}",
                    )

                    loss = 0.0
                    if result.metrics:
                        loss = result.metrics.get("loss", 0.0)

                    return loss, {"metric": result.learning_rate}
                except ParameterUpdateRejected:
                    # Return current loss without update
                    return 0.0, {"rejected": True}

            # Define validation step
            async def val_step(
                params: dict[str, float], val_data: list[Any]
            ) -> tuple[float, float | None]:
                """Validate on validation set."""
                total_metric = 0.0
                count = 0

                for _sample in val_data:
                    try:
                        for _metric_name, metric_fn in self.metric_fns.items():
                            value = metric_fn(params)
                            total_metric += value
                            count += 1
                    except Exception as e:
                        logger.debug(f"Error computing metric: {e}")

                avg_metric = total_metric / count if count > 0 else None
                return avg_metric or 0.0, avg_metric

            # Run training loop
            state = await loop.run(
                initial_params=self._current_params,
                train_step=train_step,
                val_step=lambda p, d: val_step(p, val_data),
                train_data=batches,
                val_data=val_data,
                current_lr=self.config.learning_rate,
            )

            self._current_params = self.get_best_params()
            self._training_history = loop.history

            result = AutocogTrainingResult(
                success=True,
                final_state=state,
                best_params=self._current_params,
                best_metrics=self.get_best_metrics(),
                training_history=loop.history,
                checkpoint_info=self._checkpointing.get_checkpoint_info(),
            )

            logger.info(
                f"Training completed: success={result.success}, "
                f"best_epoch={state.best_epoch}, "
                f"best_val_loss={state.best_val_loss:.6f}"
            )

            return result

        except Exception as e:
            logger.exception(f"Training failed: {e}")
            return AutocogTrainingResult(
                success=False,
                best_params=self._current_params,
                best_metrics=self.get_best_metrics(),
                training_history=self._training_history,
                checkpoint_info=self._checkpointing.get_checkpoint_info(),
            )

        finally:
            self._is_training = False

    def rollback_to_best(self) -> dict[str, float]:
        """Rollback parameters to best checkpoint.

        Returns:
            Best parameters
        """
        best_params = self._checkpointing.rollback_to_best()
        if best_params:
            self._current_params = best_params
        return self._current_params.copy()


def create_autocog_pipeline(
    params: dict[str, float],
    metric_fns: dict[str, Callable[[dict[str, float]], float]],
    constitution_audit_fn: Callable[[dict[str, Any]], bool] | None = None,
    max_epochs: int = 100,
    batch_size: int = 32,
    learning_rate: float = 0.01,
    optimizer_type: str = "SGD",
    checkpoint_dir: str = "checkpoints/autocog",
    **kwargs,
) -> AutocogTrainingPipeline:
    """Factory function to create an autocog training pipeline.

    Args:
        params: Initial model parameters
        metric_fns: Metric functions to optimize
        constitution_audit_fn: Constitution audit function
        max_epochs: Maximum training epochs
        batch_size: Batch size
        learning_rate: Learning rate
        optimizer_type: Optimizer type ('SGD' or 'Adam')
        checkpoint_dir: Checkpoint directory
        **kwargs: Additional AutocogTrainingConfig options

    Returns:
        Configured AutocogTrainingPipeline
    """
    config = AutocogTrainingConfig(
        max_epochs=max_epochs,
        batch_size=batch_size,
        learning_rate=learning_rate,
        optimizer_type=optimizer_type,
        checkpoint_dir=checkpoint_dir,
        **kwargs,
    )

    return AutocogTrainingPipeline(
        params=params,
        metric_fns=metric_fns,
        config=config,
        constitution_audit_fn=constitution_audit_fn,
    )


__all__ = [
    # Configuration
    "AutocogTrainingConfig",
    "AutocogTrainingResult",
    # Components
    "BatchProcessor",
    "Batch",
    "create_batch_processor",
    # Checkpointing
    "ModelCheckpointing",
    "ModelCheckpoint",
    "ModelCheckpointConfig",
    "CheckpointType",
    "create_model_checkpointing",
    # Training Loop
    "TrainingLoop",
    "TrainingLoopState",
    "EpochMetrics",
    "EarlyStoppingMode",
    # Validation
    "ValidationSplitManager",
    "ValidationSplit",
    "ValidationMetrics",
    "create_validation_split_manager",
    # Pipeline
    "AutocogTrainingPipeline",
    "create_autocog_pipeline",
]
