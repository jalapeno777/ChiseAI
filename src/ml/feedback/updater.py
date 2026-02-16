"""Model Updater for ML Feedback Loop.

This module provides functionality to apply incremental learning from new outcomes,
support online learning algorithms, and version control for model updates.

Features:
- Apply incremental learning from new outcomes
- Support online learning algorithms (SGD, incremental learners)
- Version control for model updates
- Rollback capability for bad updates
- A/B testing support for model variants

Usage:
    from ml.feedback.updater import ModelUpdater, UpdateConfig

    config = UpdateConfig()
    updater = ModelUpdater(config)
    result = await updater.update_model(model, new_data)
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from ml.feedback.analyzer import FeedbackAnalysisReport
    from ml.feedback.matcher import PredictionOutcomeMatch

logger = logging.getLogger(__name__)


class UpdateStrategy(Enum):
    """Strategy for model updates."""

    BATCH_RETRAIN = "batch_retrain"  # Full retrain on accumulated data
    INCREMENTAL = "incremental"  # Online/incremental learning
    WARM_START = "warm_start"  # Fine-tune from current weights
    ENSEMBLE_UPDATE = "ensemble_update"  # Update ensemble weights
    NO_UPDATE = "no_update"  # Skip update


class UpdateStatus(Enum):
    """Status of a model update."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    VALIDATING = "validating"


class ModelType(Enum):
    """Type of ML model."""

    SKLEARN = "sklearn"
    TENSORFLOW = "tensorflow"
    PYTORCH = "pytorch"
    XGBOOST = "xgboost"
    LIGHTGBM = "lightgbm"
    CUSTOM = "custom"


class IncrementalLearner(Protocol):
    """Protocol for models supporting incremental learning."""

    def partial_fit(self, X: Any, y: Any) -> None: ...


@dataclass
class UpdateConfig:
    """Configuration for model updates.

    Attributes:
        update_strategy: Strategy for applying updates
        min_samples_for_update: Minimum samples before updating
        max_samples_for_incremental: Maximum samples for incremental learning
        validation_split: Fraction of data to use for validation
        early_stopping_patience: Patience for early stopping
        learning_rate_decay: Learning rate decay factor
        version_prefix: Prefix for version strings
        backup_before_update: Whether to backup before updating
        auto_rollback_on_failure: Whether to auto-rollback on failure
        max_update_time_hours: Maximum time allowed for update
    """

    update_strategy: UpdateStrategy = UpdateStrategy.INCREMENTAL
    min_samples_for_update: int = 100
    max_samples_for_incremental: int = 10000
    validation_split: float = 0.2
    early_stopping_patience: int = 5
    learning_rate_decay: float = 0.95
    version_prefix: str = "v"
    backup_before_update: bool = True
    auto_rollback_on_failure: bool = True
    max_update_time_hours: float = 4.0


@dataclass
class ModelVersion:
    """Version information for a model.

    Attributes:
        version_id: Unique version identifier
        model_id: Parent model identifier
        created_at: Creation timestamp
        parent_version: Previous version (if any)
        update_strategy: Strategy used for this version
        performance_metrics: Performance metrics for this version
        training_samples: Number of samples used for training
        features_used: List of features used
        hyperparameters: Hyperparameter configuration
        file_path: Path to model file
        checksum: Model file checksum
        metadata: Additional metadata
    """

    version_id: str
    model_id: str
    created_at: datetime
    parent_version: str | None = None
    update_strategy: UpdateStrategy = UpdateStrategy.NO_UPDATE
    performance_metrics: dict[str, float] = field(default_factory=dict)
    training_samples: int = 0
    features_used: list[str] = field(default_factory=list)
    hyperparameters: dict[str, Any] = field(default_factory=dict)
    file_path: str = ""
    checksum: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "version_id": self.version_id,
            "model_id": self.model_id,
            "created_at": self.created_at.isoformat(),
            "parent_version": self.parent_version,
            "update_strategy": self.update_strategy.value,
            "performance_metrics": self.performance_metrics,
            "training_samples": self.training_samples,
            "features_used": self.features_used,
            "hyperparameters": self.hyperparameters,
            "file_path": self.file_path,
            "checksum": self.checksum,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModelVersion:
        """Create from dictionary."""
        return cls(
            version_id=data["version_id"],
            model_id=data["model_id"],
            created_at=datetime.fromisoformat(data["created_at"]),
            parent_version=data.get("parent_version"),
            update_strategy=UpdateStrategy(data.get("update_strategy", "no_update")),
            performance_metrics=data.get("performance_metrics", {}),
            training_samples=data.get("training_samples", 0),
            features_used=data.get("features_used", []),
            hyperparameters=data.get("hyperparameters", {}),
            file_path=data.get("file_path", ""),
            checksum=data.get("checksum", ""),
            metadata=data.get("metadata", {}),
        )


@dataclass
class UpdateResult:
    """Result of a model update operation.

    Attributes:
        status: Update status
        version: New model version (if successful)
        previous_version: Previous version
        samples_used: Number of samples used for update
        training_time_seconds: Time spent training
        validation_metrics: Validation metrics
        improvement_metrics: Metrics showing improvement
        error_message: Error message (if failed)
        warnings: List of warnings
    """

    status: UpdateStatus
    version: ModelVersion | None = None
    previous_version: ModelVersion | None = None
    samples_used: int = 0
    training_time_seconds: float = 0.0
    validation_metrics: dict[str, float] = field(default_factory=dict)
    improvement_metrics: dict[str, float] = field(default_factory=dict)
    error_message: str = ""
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "status": self.status.value,
            "version": self.version.to_dict() if self.version else None,
            "previous_version": (
                self.previous_version.to_dict() if self.previous_version else None
            ),
            "samples_used": self.samples_used,
            "training_time_seconds": round(self.training_time_seconds, 2),
            "validation_metrics": self.validation_metrics,
            "improvement_metrics": self.improvement_metrics,
            "error_message": self.error_message,
            "warnings": self.warnings,
        }


class ModelUpdater:
    """Updates ML models based on feedback loop data.

    This class provides methods to:
    - Apply incremental learning updates
    - Manage model versions
    - Support rollback operations
    - Validate updates before deployment
    """

    def __init__(
        self,
        config: UpdateConfig | None = None,
        model_storage_path: str = "models/feedback",
    ):
        """Initialize the updater.

        Args:
            config: Update configuration
            model_storage_path: Path for model storage
        """
        self.config = config or UpdateConfig()
        self.model_storage_path = Path(model_storage_path)
        self.model_storage_path.mkdir(parents=True, exist_ok=True)

        self._versions: dict[str, list[ModelVersion]] = {}
        self._current_versions: dict[str, str] = {}  # model_id -> version_id

    async def update_from_matches(
        self,
        model: Any,
        matches: list[PredictionOutcomeMatch],
        model_id: str = "default",
        model_type: ModelType = ModelType.SKLEARN,
    ) -> UpdateResult:
        """Update model using prediction-outcome matches.

        Args:
            model: Model to update
            matches: List of matches with outcomes
            model_id: Model identifier
            model_type: Type of model

        Returns:
            UpdateResult with update status and metrics
        """
        result = UpdateResult(
            status=UpdateStatus.PENDING,
            previous_version=self._get_current_version(model_id),
        )

        # Check minimum samples
        if len(matches) < self.config.min_samples_for_update:
            result.status = UpdateStatus.FAILED
            result.error_message = (
                f"Insufficient samples: {len(matches)} "
                f"(minimum {self.config.min_samples_for_update})"
            )
            return result

        result.status = UpdateStatus.IN_PROGRESS
        start_time = datetime.now(timezone.utc)

        try:
            # Prepare training data
            X, y = self._prepare_training_data(matches)
            result.samples_used = len(X)

            # Backup current model if needed
            if self.config.backup_before_update:
                await self._backup_model(model, model_id)

            # Apply update based on strategy
            if self.config.update_strategy == UpdateStrategy.INCREMENTAL:
                updated_model = await self._apply_incremental_update(
                    model, X, y, model_type
                )
            elif self.config.update_strategy == UpdateStrategy.BATCH_RETRAIN:
                updated_model = await self._apply_batch_retrain(model, X, y, model_type)
            elif self.config.update_strategy == UpdateStrategy.WARM_START:
                updated_model = await self._apply_warm_start(model, X, y, model_type)
            else:
                result.status = UpdateStatus.FAILED
                result.error_message = (
                    f"Unsupported update strategy: {self.config.update_strategy}"
                )
                return result

            # Calculate training time
            result.training_time_seconds = (
                datetime.now(timezone.utc) - start_time
            ).total_seconds()

            # Validate update
            result.status = UpdateStatus.VALIDATING
            val_metrics = await self._validate_update(updated_model, X, y, model_type)
            result.validation_metrics = val_metrics

            # Calculate improvement
            result.improvement_metrics = self._calculate_improvement(
                result.previous_version, val_metrics
            )

            # Create new version
            version = self._create_version(
                model_id=model_id,
                parent_version=(
                    result.previous_version.version_id
                    if result.previous_version
                    else None
                ),
                strategy=self.config.update_strategy,
                metrics=val_metrics,
                samples=len(X),
            )

            # Save model
            await self._save_model(updated_model, version, model_type)

            result.version = version
            result.status = UpdateStatus.COMPLETED

            logger.info(
                f"Model {model_id} updated to version {version.version_id}: "
                f"accuracy={val_metrics.get('accuracy', 0):.2%}"
            )

        except Exception as e:
            result.status = UpdateStatus.FAILED
            result.error_message = str(e)
            logger.error(f"Model update failed: {e}")

            # Auto-rollback if enabled
            if self.config.auto_rollback_on_failure and result.previous_version:
                await self.rollback(model_id)

        return result

    async def update_from_analysis(
        self,
        model: Any,
        analysis_report: FeedbackAnalysisReport,
        matches: list[PredictionOutcomeMatch],
        model_id: str = "default",
        model_type: ModelType = ModelType.SKLEARN,
    ) -> UpdateResult:
        """Update model using feedback analysis report.

        Args:
            model: Model to update
            analysis_report: Analysis report with recommendations
            matches: List of matches with outcomes
            model_id: Model identifier
            model_type: Type of model

        Returns:
            UpdateResult with update status and metrics
        """
        # Adjust strategy based on analysis
        if analysis_report.overall_accuracy < 0.5:
            # Poor performance - use batch retrain
            original_strategy = self.config.update_strategy
            self.config.update_strategy = UpdateStrategy.BATCH_RETRAIN
            result = await self.update_from_matches(
                model, matches, model_id, model_type
            )
            self.config.update_strategy = original_strategy
        else:
            # Normal update
            result = await self.update_from_matches(
                model, matches, model_id, model_type
            )

        # Add analysis-based warnings
        for rec in analysis_report.recommendations:
            if "drift" in rec.lower() or "retrain" in rec.lower():
                result.warnings.append(rec)

        return result

    async def rollback(self, model_id: str) -> ModelVersion | None:
        """Rollback to previous version.

        Args:
            model_id: Model identifier

        Returns:
            Previous version or None if no rollback possible
        """
        current = self._get_current_version(model_id)
        if not current or not current.parent_version:
            logger.warning(f"No previous version to rollback to for {model_id}")
            return None

        # Find parent version
        parent = self._get_version(model_id, current.parent_version)
        if not parent:
            logger.error(f"Parent version {current.parent_version} not found")
            return None

        # Restore from backup
        backup_path = self._get_backup_path(model_id, parent.version_id)
        if backup_path.exists():
            model_path = self._get_model_path(model_id, parent.version_id)
            shutil.copy2(backup_path, model_path)

        # Update current version
        self._current_versions[model_id] = parent.version_id

        logger.info(f"Rolled back {model_id} to version {parent.version_id}")
        return parent

    def get_version_history(self, model_id: str) -> list[ModelVersion]:
        """Get version history for a model.

        Args:
            model_id: Model identifier

        Returns:
            List of versions (newest first)
        """
        versions = self._versions.get(model_id, [])
        return sorted(versions, key=lambda v: v.created_at, reverse=True)

    def get_current_version(self, model_id: str) -> ModelVersion | None:
        """Get current version for a model.

        Args:
            model_id: Model identifier

        Returns:
            Current version or None
        """
        return self._get_current_version(model_id)

    def _get_current_version(self, model_id: str) -> ModelVersion | None:
        """Get current version for a model (internal)."""
        version_id = self._current_versions.get(model_id)
        if version_id:
            return self._get_version(model_id, version_id)
        return None

    def _get_version(self, model_id: str, version_id: str) -> ModelVersion | None:
        """Get specific version."""
        versions = self._versions.get(model_id, [])
        for v in versions:
            if v.version_id == version_id:
                return v
        return None

    def _create_version(
        self,
        model_id: str,
        parent_version: str | None,
        strategy: UpdateStrategy,
        metrics: dict[str, float],
        samples: int,
    ) -> ModelVersion:
        """Create a new model version."""
        version_num = len(self._versions.get(model_id, [])) + 1
        version_id = f"{self.config.version_prefix}{version_num}"

        version = ModelVersion(
            version_id=version_id,
            model_id=model_id,
            created_at=datetime.now(timezone.utc),
            parent_version=parent_version,
            update_strategy=strategy,
            performance_metrics=metrics,
            training_samples=samples,
        )

        if model_id not in self._versions:
            self._versions[model_id] = []
        self._versions[model_id].append(version)
        self._current_versions[model_id] = version_id

        return version

    async def _backup_model(self, model: Any, model_id: str) -> None:
        """Backup current model."""
        current = self._get_current_version(model_id)
        if not current:
            return

        backup_path = self._get_backup_path(model_id, current.version_id)
        model_path = self._get_model_path(model_id, current.version_id)

        if model_path.exists():
            shutil.copy2(model_path, backup_path)

    async def _save_model(
        self,
        model: Any,
        version: ModelVersion,
        model_type: ModelType,
    ) -> None:
        """Save model to storage."""
        model_path = self._get_model_path(version.model_id, version.version_id)

        if model_type == ModelType.SKLEARN:
            import joblib

            joblib.dump(model, model_path)
        elif model_type == ModelType.XGBOOST:
            model.save_model(str(model_path))
        elif model_type == ModelType.LIGHTGBM:
            model.save_model(str(model_path))
        else:
            # Generic pickle fallback
            import pickle

            with open(model_path, "wb") as f:
                pickle.dump(model, f)

        version.file_path = str(model_path)

    async def _apply_incremental_update(
        self,
        model: Any,
        X: list[Any],
        y: list[Any],
        model_type: ModelType,
    ) -> Any:
        """Apply incremental learning update."""
        if model_type == ModelType.SKLEARN:
            # Check if model supports partial_fit
            if hasattr(model, "partial_fit"):
                model.partial_fit(X, y)
            else:
                # Fall back to warm start
                if hasattr(model, "warm_start"):
                    model.warm_start = True
                model.fit(X, y)
        elif model_type == ModelType.XGBOOST:
            # XGBoost supports incremental via update
            if hasattr(model, "fit"):
                model.fit(X, y, xgb_model=model)
        elif model_type == ModelType.LIGHTGBM:
            # LightGBM supports incremental via init_model
            if hasattr(model, "fit"):
                model.fit(X, y, init_model=model)
        else:
            # Generic: just refit
            model.fit(X, y)

        return model

    async def _apply_batch_retrain(
        self,
        model: Any,
        X: list[Any],
        y: list[Any],
        model_type: ModelType,
    ) -> Any:
        """Apply full batch retrain."""
        # Create fresh model instance
        if model_type == ModelType.SKLEARN:
            from sklearn.base import clone

            new_model = clone(model)
            new_model.fit(X, y)
            return new_model
        else:
            # For other types, just fit (may need fresh instance)
            model.fit(X, y)
            return model

    async def _apply_warm_start(
        self,
        model: Any,
        X: list[Any],
        y: list[Any],
        model_type: ModelType,
    ) -> Any:
        """Apply warm start update."""
        if hasattr(model, "warm_start"):
            model.warm_start = True

        model.fit(X, y)
        return model

    async def _validate_update(
        self,
        model: Any,
        X: list[Any],
        y: list[Any],
        model_type: ModelType,
    ) -> dict[str, float]:
        """Validate updated model."""
        from sklearn.metrics import (
            accuracy_score,
            precision_score,
            recall_score,
            f1_score,
        )

        # Split validation data
        split_idx = int(len(X) * (1 - self.config.validation_split))
        X_val = X[split_idx:]
        y_val = y[split_idx:]

        if len(X_val) == 0:
            return {"accuracy": 0.0, "precision": 0.0, "recall": 0.0, "f1": 0.0}

        # Predict
        y_pred = model.predict(X_val)

        # Calculate metrics
        metrics = {
            "accuracy": accuracy_score(y_val, y_pred),
            "precision": precision_score(
                y_val, y_pred, average="binary", zero_division=0
            ),
            "recall": recall_score(y_val, y_pred, average="binary", zero_division=0),
            "f1": f1_score(y_val, y_pred, average="binary", zero_division=0),
        }

        return metrics

    def _calculate_improvement(
        self,
        previous_version: ModelVersion | None,
        current_metrics: dict[str, float],
    ) -> dict[str, float]:
        """Calculate improvement over previous version."""
        if not previous_version:
            return {}

        improvement = {}
        for metric, value in current_metrics.items():
            prev_value = previous_version.performance_metrics.get(metric, 0)
            if prev_value > 0:
                improvement[f"{metric}_delta"] = value - prev_value
                improvement[f"{metric}_pct_change"] = (
                    (value - prev_value) / prev_value
                ) * 100

        return improvement

    def _prepare_training_data(
        self,
        matches: list[PredictionOutcomeMatch],
    ) -> tuple[list[Any], list[Any]]:
        """Prepare training data from matches."""
        X = []
        y = []

        for match in matches:
            # Extract features from signal
            features = self._extract_features(match)
            X.append(features)

            # Extract label from outcome
            label = self._extract_label(match)
            y.append(label)

        return X, y

    def _extract_features(self, match: PredictionOutcomeMatch) -> list[float]:
        """Extract feature vector from match."""
        features = [
            match.signal.confidence,
            match.signal.score / 100.0,  # Normalize to 0-1
        ]

        # Add metadata features if available
        if match.signal.metadata:
            features.extend(
                [
                    match.signal.metadata.get("rsi", 50) / 100,
                    match.signal.metadata.get("macd", 0),
                    (
                        match.signal.metadata.get("atr", 0) / match.signal.entry_price
                        if match.signal.entry_price
                        else 0
                    ),
                ]
            )

        return features

    def _extract_label(self, match: PredictionOutcomeMatch) -> int:
        """Extract binary label from match."""
        if match.outcome is None:
            return 0

        # Check PnL
        if hasattr(match.outcome, "pnl"):
            return 1 if match.outcome.pnl > 0 else 0

        # Check outcome type
        if hasattr(match.outcome, "outcome_type"):
            from market_analysis.signal_storage.models import OutcomeType

            if match.outcome.outcome_type == OutcomeType.TP_HIT:
                return 1
            elif match.outcome.outcome_type == OutcomeType.SL_HIT:
                return 0

        return 0

    def _get_model_path(self, model_id: str, version_id: str) -> Path:
        """Get path for model file."""
        return self.model_storage_path / f"{model_id}_{version_id}.pkl"

    def _get_backup_path(self, model_id: str, version_id: str) -> Path:
        """Get path for backup file."""
        return self.model_storage_path / f"{model_id}_{version_id}.backup.pkl"

    def save_version_history(self, model_id: str) -> None:
        """Save version history to disk."""
        versions = self._versions.get(model_id, [])
        if not versions:
            return

        history_path = self.model_storage_path / f"{model_id}_versions.json"
        with open(history_path, "w") as f:
            json.dump([v.to_dict() for v in versions], f, indent=2)

    def load_version_history(self, model_id: str) -> list[ModelVersion]:
        """Load version history from disk."""
        history_path = self.model_storage_path / f"{model_id}_versions.json"
        if not history_path.exists():
            return []

        with open(history_path) as f:
            data = json.load(f)

        versions = [ModelVersion.from_dict(v) for v in data]
        self._versions[model_id] = versions

        # Restore current version
        if versions:
            latest = max(versions, key=lambda v: v.created_at)
            self._current_versions[model_id] = latest.version_id

        return versions
