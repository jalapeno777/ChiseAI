"""Model registry with champion/challenger pattern for ChiseAI.

This module provides a model registry that tracks model versions with
champion/challenger relationships. It supports:
- Model version lifecycle management
- Champion/challenger tracking
- Promotion criteria enforcement
- Metadata storage and retrieval

Acceptance Criteria:
- Champion/challenger pattern for model versions
- Promotion criteria with configurable thresholds
- Metadata storage for model artifacts
- Integration with validation and rollback systems

Example:
    >>> from ml.model_registry.registry import ModelRegistry
    >>> registry = ModelRegistry()
    >>>
    >>> # Register a new model
    >>> version = registry.register_model(
    ...     model_id="grid_btc_1h_v2",
    ...     model_path="/models/grid_btc_1h_v2.pkl",
    ...     metrics={"accuracy": 0.85, "precision": 0.82}
    ... )
    >>>
    >>> # Promote to challenger
    >>> challenger = registry.promote_to_challenger(version.version_id)
    >>>
    >>> # Promote to champion after validation
    >>> champion = registry.promote_to_champion(version.version_id)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, auto
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class ModelStatus(Enum):
    """Lifecycle states for model versions.

    AC1: Model lifecycle states for champion/challenger tracking.
    """

    DRAFT = "draft"  # Initial registration, not ready for use
    CANDIDATE = "candidate"  # Ready for validation
    CHALLENGER = "challenger"  # Passed validation, competing with champion
    CHAMPION = "champion"  # Current best model for production
    DEPRECATED = "deprecated"  # Replaced by newer champion
    FAILED = "failed"  # Failed validation, not usable


class ModelType(Enum):
    """Types of ML models in the system."""

    SIGNAL_PREDICTOR = "signal_predictor"
    CONFIDENCE_CALIBRATOR = "confidence_calibrator"
    OUTCOME_PREDICTOR = "outcome_predictor"


@dataclass(frozen=True)
class ModelVersion:
    """A version of a model with metadata.

    Attributes:
        version_id: Unique version identifier
        model_id: Human-readable model identifier
        model_type: Type of model
        status: Current lifecycle status
        model_path: Path to model artifact
        metrics: Model performance metrics
        created_at: When the version was created
        promoted_at: When promoted to current status
        metadata: Additional metadata
    """

    version_id: str
    model_id: str
    model_type: ModelType
    status: ModelStatus
    model_path: str
    metrics: dict[str, float] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    promoted_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "version_id": self.version_id,
            "model_id": self.model_id,
            "model_type": self.model_type.value,
            "status": self.status.value,
            "model_path": self.model_path,
            "metrics": self.metrics,
            "created_at": self.created_at.isoformat(),
            "promoted_at": self.promoted_at.isoformat() if self.promoted_at else None,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModelVersion:
        """Create from dictionary."""
        return cls(
            version_id=data["version_id"],
            model_id=data["model_id"],
            model_type=ModelType(data["model_type"]),
            status=ModelStatus(data["status"]),
            model_path=data["model_path"],
            metrics=data.get("metrics", {}),
            created_at=datetime.fromisoformat(data["created_at"]),
            promoted_at=(
                datetime.fromisoformat(data["promoted_at"])
                if data.get("promoted_at")
                else None
            ),
            metadata=data.get("metadata", {}),
        )


@dataclass
class PromotionCriteria:
    """Criteria for promoting a model to champion.

    AC3: Documented promotion criteria for challenger -> champion promotion.

    Attributes:
        min_accuracy: Minimum accuracy threshold
        min_precision: Minimum precision threshold
        min_recall: Minimum recall threshold
        min_f1: Minimum F1 score threshold
        max_ece: Maximum Expected Calibration Error
        require_outperformance: Must outperform current champion
        outperformance_margin_pct: Required margin over champion
        require_human_approval: Require human approval for promotion
    """

    min_accuracy: float = 0.75
    min_precision: float = 0.70
    min_recall: float = 0.70
    min_f1: float = 0.72
    max_ece: float = 0.15
    require_outperformance: bool = True
    outperformance_margin_pct: float = 2.0
    require_human_approval: bool = True

    def evaluate(
        self,
        metrics: dict[str, float],
        champion_metrics: dict[str, float] | None = None,
    ) -> tuple[bool, list[str]]:
        """Evaluate if metrics meet promotion criteria.

        Args:
            metrics: Model metrics to evaluate
            champion_metrics: Current champion metrics for comparison

        Returns:
            Tuple of (meets_criteria, list_of_failures)
        """
        failures = []

        # Check minimum thresholds
        if metrics.get("accuracy", 0) < self.min_accuracy:
            failures.append(
                f"accuracy {metrics.get('accuracy', 0):.3f} < {self.min_accuracy}"
            )

        if metrics.get("precision", 0) < self.min_precision:
            failures.append(
                f"precision {metrics.get('precision', 0):.3f} < {self.min_precision}"
            )

        if metrics.get("recall", 0) < self.min_recall:
            failures.append(
                f"recall {metrics.get('recall', 0):.3f} < {self.min_recall}"
            )

        if metrics.get("f1", 0) < self.min_f1:
            failures.append(f"f1 {metrics.get('f1', 0):.3f} < {self.min_f1}")

        if metrics.get("ece", 1.0) > self.max_ece:
            failures.append(f"ece {metrics.get('ece', 1.0):.3f} > {self.max_ece}")

        # Check outperformance if champion exists
        if self.require_outperformance and champion_metrics:
            champion_f1 = champion_metrics.get("f1", 0)
            model_f1 = metrics.get("f1", 0)
            margin = self.outperformance_margin_pct / 100

            if model_f1 < champion_f1 * (1 + margin):
                failures.append(
                    f"f1 {model_f1:.3f} does not outperform champion {champion_f1:.3f} by {self.outperformance_margin_pct}%"
                )

        return len(failures) == 0, failures


class ModelStorage(Protocol):
    """Protocol for model storage backends."""

    async def save(self, version: ModelVersion) -> bool:
        """Save model version to storage."""
        ...

    async def load(self, version_id: str) -> ModelVersion | None:
        """Load model version from storage."""
        ...

    async def list_versions(
        self,
        model_type: ModelType | None = None,
        status: ModelStatus | None = None,
    ) -> list[ModelVersion]:
        """List model versions with optional filters."""
        ...

    async def get_champion(self, model_type: ModelType) -> ModelVersion | None:
        """Get current champion for model type."""
        ...


class ModelRegistry:
    """Registry for model versions with champion/challenger tracking.

    AC1: Concrete ModelRegistry class implementing champion/challenger relationships.

    This registry manages the lifecycle of model versions and supports:
    - Model registration and versioning
    - Champion/challenger promotion
    - Promotion criteria enforcement
    - Metadata tracking
    """

    def __init__(
        self,
        storage: ModelStorage | None = None,
        promotion_criteria: PromotionCriteria | None = None,
    ):
        """Initialize model registry.

        Args:
            storage: Storage backend for model versions
            promotion_criteria: Criteria for promotion to champion
        """
        self._storage = storage
        self._promotion_criteria = promotion_criteria or PromotionCriteria()
        self._versions: dict[str, ModelVersion] = {}
        self._champions: dict[ModelType, str] = {}  # model_type -> version_id
        self._challengers: dict[ModelType, list[str]] = {}  # model_type -> version_ids

        logger.info("ModelRegistry initialized")

    def register_model(
        self,
        model_id: str,
        model_path: str,
        model_type: ModelType = ModelType.SIGNAL_PREDICTOR,
        metrics: dict[str, float] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ModelVersion:
        """Register a new model version.

        Args:
            model_id: Human-readable model identifier
            model_path: Path to model artifact
            model_type: Type of model
            metrics: Initial model metrics
            metadata: Additional metadata

        Returns:
            Registered ModelVersion
        """
        version_id = f"{model_id}_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S_%f')}"

        version = ModelVersion(
            version_id=version_id,
            model_id=model_id,
            model_type=model_type,
            status=ModelStatus.DRAFT,
            model_path=model_path,
            metrics=metrics or {},
            metadata=metadata or {},
        )

        self._versions[version_id] = version
        logger.info(f"Registered model version: {version_id}")

        return version

    def promote_to_candidate(self, version_id: str) -> ModelVersion:
        """Promote model to candidate status (ready for validation).

        Args:
            version_id: Version to promote

        Returns:
            Updated ModelVersion

        Raises:
            ValueError: If version not found
        """
        if version_id not in self._versions:
            raise ValueError(f"Version not found: {version_id}")

        old_version = self._versions[version_id]
        new_version = ModelVersion(
            version_id=old_version.version_id,
            model_id=old_version.model_id,
            model_type=old_version.model_type,
            status=ModelStatus.CANDIDATE,
            model_path=old_version.model_path,
            metrics=old_version.metrics,
            created_at=old_version.created_at,
            promoted_at=datetime.now(UTC),
            metadata=old_version.metadata,
        )

        self._versions[version_id] = new_version
        logger.info(f"Promoted {version_id} to CANDIDATE")

        return new_version

    def promote_to_challenger(self, version_id: str) -> ModelVersion:
        """Promote model to challenger status.

        Args:
            version_id: Version to promote

        Returns:
            Updated ModelVersion

        Raises:
            ValueError: If version not found
        """
        if version_id not in self._versions:
            raise ValueError(f"Version not found: {version_id}")

        old_version = self._versions[version_id]
        model_type = old_version.model_type

        new_version = ModelVersion(
            version_id=old_version.version_id,
            model_id=old_version.model_id,
            model_type=model_type,
            status=ModelStatus.CHALLENGER,
            model_path=old_version.model_path,
            metrics=old_version.metrics,
            created_at=old_version.created_at,
            promoted_at=datetime.now(UTC),
            metadata=old_version.metadata,
        )

        self._versions[version_id] = new_version

        # Add to challengers list
        if model_type not in self._challengers:
            self._challengers[model_type] = []
        if version_id not in self._challengers[model_type]:
            self._challengers[model_type].append(version_id)

        logger.info(f"Promoted {version_id} to CHALLENGER")

        return new_version

    def promote_to_champion(
        self,
        version_id: str,
        force: bool = False,
    ) -> tuple[ModelVersion, ModelVersion | None]:
        """Promote model to champion status.

        AC3: Promotion criteria enforcement for challenger -> champion.

        Args:
            version_id: Version to promote
            force: Force promotion even if criteria not met

        Returns:
            Tuple of (new_champion, old_champion_or_none)

        Raises:
            ValueError: If version not found or criteria not met
        """
        if version_id not in self._versions:
            raise ValueError(f"Version not found: {version_id}")

        version = self._versions[version_id]
        model_type = version.model_type

        # Check promotion criteria unless forced
        if not force:
            champion = self.get_champion(model_type)
            champion_metrics = champion.metrics if champion else None

            meets_criteria, failures = self._promotion_criteria.evaluate(
                version.metrics,
                champion_metrics,
            )

            if not meets_criteria:
                raise ValueError(
                    f"Promotion criteria not met for {version_id}: {', '.join(failures)}"
                )

        # Demote existing champion
        old_champion = None
        old_champion_id = self._champions.get(model_type)
        if old_champion_id and old_champion_id in self._versions:
            old_champion = self._deprecate_version(old_champion_id)

        # Promote to champion
        new_champion = ModelVersion(
            version_id=version.version_id,
            model_id=version.model_id,
            model_type=model_type,
            status=ModelStatus.CHAMPION,
            model_path=version.model_path,
            metrics=version.metrics,
            created_at=version.created_at,
            promoted_at=datetime.now(UTC),
            metadata=version.metadata,
        )

        self._versions[version_id] = new_champion
        self._champions[model_type] = version_id

        # Remove from challengers
        if (
            model_type in self._challengers
            and version_id in self._challengers[model_type]
        ):
            self._challengers[model_type].remove(version_id)

        logger.info(f"Promoted {version_id} to CHAMPION")

        return new_champion, old_champion

    def _deprecate_version(self, version_id: str) -> ModelVersion:
        """Deprecate a version (internal use).

        Args:
            version_id: Version to deprecate

        Returns:
            Deprecated ModelVersion
        """
        old_version = self._versions[version_id]

        deprecated = ModelVersion(
            version_id=old_version.version_id,
            model_id=old_version.model_id,
            model_type=old_version.model_type,
            status=ModelStatus.DEPRECATED,
            model_path=old_version.model_path,
            metrics=old_version.metrics,
            created_at=old_version.created_at,
            promoted_at=datetime.now(UTC),
            metadata={
                **old_version.metadata,
                "deprecated_at": datetime.now(UTC).isoformat(),
            },
        )

        self._versions[version_id] = deprecated
        logger.info(f"Deprecated version: {version_id}")

        return deprecated

    def mark_failed(self, version_id: str, reason: str) -> ModelVersion:
        """Mark a version as failed.

        Args:
            version_id: Version to mark
            reason: Failure reason

        Returns:
            Failed ModelVersion
        """
        if version_id not in self._versions:
            raise ValueError(f"Version not found: {version_id}")

        old_version = self._versions[version_id]

        failed = ModelVersion(
            version_id=old_version.version_id,
            model_id=old_version.model_id,
            model_type=old_version.model_type,
            status=ModelStatus.FAILED,
            model_path=old_version.model_path,
            metrics=old_version.metrics,
            created_at=old_version.created_at,
            promoted_at=datetime.now(UTC),
            metadata={**old_version.metadata, "failure_reason": reason},
        )

        self._versions[version_id] = failed
        logger.info(f"Marked {version_id} as FAILED: {reason}")

        return failed

    def get_version(self, version_id: str) -> ModelVersion | None:
        """Get a model version by ID.

        Args:
            version_id: Version identifier

        Returns:
            ModelVersion or None if not found
        """
        return self._versions.get(version_id)

    def get_champion(self, model_type: ModelType) -> ModelVersion | None:
        """Get current champion for model type.

        Args:
            model_type: Type of model

        Returns:
            Champion ModelVersion or None
        """
        champion_id = self._champions.get(model_type)
        if champion_id:
            return self._versions.get(champion_id)
        return None

    def get_challengers(self, model_type: ModelType) -> list[ModelVersion]:
        """Get all challengers for model type.

        Args:
            model_type: Type of model

        Returns:
            List of challenger ModelVersions
        """
        challenger_ids = self._challengers.get(model_type, [])
        return [self._versions[vid] for vid in challenger_ids if vid in self._versions]

    def list_versions(
        self,
        model_type: ModelType | None = None,
        status: ModelStatus | None = None,
    ) -> list[ModelVersion]:
        """List model versions with optional filters.

        Args:
            model_type: Filter by model type
            status: Filter by status

        Returns:
            List of matching ModelVersions
        """
        versions = list(self._versions.values())

        if model_type:
            versions = [v for v in versions if v.model_type == model_type]

        if status:
            versions = [v for v in versions if v.status == status]

        return sorted(versions, key=lambda v: v.created_at, reverse=True)

    def get_rollback_target(self, model_type: ModelType) -> ModelVersion | None:
        """Get rollback target for model type.

        Returns the most recent deprecated champion that can be
        rolled back to.

        Args:
            model_type: Type of model

        Returns:
            Rollback target ModelVersion or None
        """
        deprecated = [
            v
            for v in self._versions.values()
            if v.model_type == model_type and v.status == ModelStatus.DEPRECATED
        ]

        if deprecated:
            return max(deprecated, key=lambda v: v.promoted_at or v.created_at)

        return None

    def update_metrics(
        self, version_id: str, metrics: dict[str, float]
    ) -> ModelVersion:
        """Update metrics for a version.

        Args:
            version_id: Version to update
            metrics: New metrics (merged with existing)

        Returns:
            Updated ModelVersion
        """
        if version_id not in self._versions:
            raise ValueError(f"Version not found: {version_id}")

        old_version = self._versions[version_id]

        updated = ModelVersion(
            version_id=old_version.version_id,
            model_id=old_version.model_id,
            model_type=old_version.model_type,
            status=old_version.status,
            model_path=old_version.model_path,
            metrics={**old_version.metrics, **metrics},
            created_at=old_version.created_at,
            promoted_at=old_version.promoted_at,
            metadata=old_version.metadata,
        )

        self._versions[version_id] = updated
        logger.info(f"Updated metrics for {version_id}")

        return updated
