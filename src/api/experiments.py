"""Experiment Query REST API for ChiseAI.

Provides FastAPI endpoints for querying experiment history, artifacts,
hyperparameters, lineage, and comparisons.

Endpoints:
    GET  /api/v1/experiments - List experiments with filters
    GET  /api/v1/experiments/{experiment_id} - Get experiment details
    GET  /api/v1/experiments/{experiment_id}/artifacts - Get artifacts
    GET  /api/v1/experiments/{experiment_id}/hyperparameters - Get hyperparams
    GET  /api/v1/experiments/{experiment_id}/lineage - Get lineage
    GET  /api/v1/experiments/compare - Compare two experiments
    POST /api/v1/experiments/{experiment_id}/rollback - Rollback

Example:
    from src.api.experiments import router
    app.include_router(router)
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from ml.training.artifacts import ArtifactManager, ArtifactType
from ml.training.lineage import LineageTracker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/experiments", tags=["experiments"])

# Global service instances (initialized by application)
_artifact_manager: ArtifactManager | None = None
_lineage_tracker: LineageTracker | None = None


def set_experiment_services(
    artifact_manager: ArtifactManager,
    lineage_tracker: LineageTracker,
) -> None:
    """Set the global experiment service instances.

    Args:
        artifact_manager: ArtifactManager instance for artifact queries.
        lineage_tracker: LineageTracker instance for lineage queries.
    """
    global _artifact_manager, _lineage_tracker
    _artifact_manager = artifact_manager
    _lineage_tracker = lineage_tracker
    logger.info("Experiment services registered with API")


def get_artifact_manager() -> ArtifactManager | None:
    """Get the global artifact manager instance."""
    return _artifact_manager


def get_lineage_tracker() -> LineageTracker | None:
    """Get the global lineage tracker instance."""
    return _lineage_tracker


# ---------------------------------------------------------------------------
# Pydantic response models
# ---------------------------------------------------------------------------


class ArtifactInfo(BaseModel):
    """Summary of a single artifact."""

    artifact_id: str
    artifact_type: str
    experiment_id: str
    created_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExperimentSummary(BaseModel):
    """High-level experiment summary returned in list views."""

    experiment_id: str
    artifact_count: int
    latest_checkpoint_epoch: int | None = None
    latest_log_status: str | None = None
    final_metrics: dict[str, float] = Field(default_factory=dict)
    training_duration_seconds: float | None = None


class ExperimentDetail(BaseModel):
    """Full experiment details with all artifact summaries."""

    experiment_id: str
    checkpoint_count: int
    config_count: int
    log_count: int
    latest_checkpoint_epoch: int | None = None
    latest_config_id: str | None = None
    latest_log_status: str | None = None
    training_duration_seconds: float | None = None
    final_metrics: dict[str, float] = Field(default_factory=dict)


class ListExperimentsResponse(BaseModel):
    """Response for listing experiments."""

    success: bool
    experiments: list[ExperimentSummary]
    count: int


class GetExperimentResponse(BaseModel):
    """Response for a single experiment."""

    success: bool
    experiment: ExperimentDetail


class ArtifactsResponse(BaseModel):
    """Response for experiment artifacts."""

    success: bool
    experiment_id: str
    artifacts: list[ArtifactInfo]
    count: int


class HyperparameterInfo(BaseModel):
    """Hyperparameter set information."""

    learning_rate: float | None = None
    batch_size: int | None = None
    epochs: int | None = None
    optimizer: str | None = None
    loss_function: str | None = None
    model_architecture: dict[str, Any] = Field(default_factory=dict)
    data_config: dict[str, Any] = Field(default_factory=dict)
    random_seed: int | None = None
    framework: str | None = None
    captured_at: str | None = None


class HyperparametersResponse(BaseModel):
    """Response for experiment hyperparameters."""

    success: bool
    experiment_id: str
    hyperparameters: list[HyperparameterInfo]
    count: int


class LineageNodeInfo(BaseModel):
    """A single node in the lineage graph."""

    node_id: str
    node_type: str
    created_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class LineageEdgeInfo(BaseModel):
    """A single edge in the lineage graph."""

    edge_id: str
    source_id: str
    target_id: str
    relationship_type: str
    created_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class LineageResponse(BaseModel):
    """Response for experiment lineage."""

    success: bool
    experiment_id: str
    nodes: list[LineageNodeInfo]
    edges: list[LineageEdgeInfo]


class CompareExperimentsRequest(BaseModel):
    """Request body for comparing two experiments."""

    experiment_id_1: str = Field(..., description="First experiment ID")
    experiment_id_2: str = Field(..., description="Second experiment ID")


class CompareExperimentsResponse(BaseModel):
    """Response comparing two experiments."""

    success: bool
    experiment_1: ExperimentDetail
    experiment_2: ExperimentDetail
    metric_diffs: dict[str, float]


class RollbackResponse(BaseModel):
    """Response for experiment rollback."""

    success: bool
    message: str
    experiment_id: str
    rolled_back_to: str


class ErrorResponse(BaseModel):
    """Generic error response."""

    success: bool = False
    error: str
    detail: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_artifact_manager() -> ArtifactManager:
    """Return the artifact manager or raise 503."""
    if _artifact_manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Experiment services not initialized",
        )
    return _artifact_manager


def _artifact_to_info(artifact: Any) -> ArtifactInfo:
    """Convert a TrainingArtifact dataclass to an ArtifactInfo pydantic model."""
    d = artifact.to_dict()
    return ArtifactInfo(
        artifact_id=d["artifact_id"],
        artifact_type=d["artifact_type"],
        experiment_id=d["experiment_id"],
        created_at=d["created_at"],
        metadata=d.get("metadata", {}),
    )


def _summary_from_dict(summary: dict[str, Any]) -> ExperimentSummary:
    """Build ExperimentSummary from the manager's summary dict."""
    return ExperimentSummary(
        experiment_id=summary["experiment_id"],
        artifact_count=(
            summary["checkpoint_count"] + summary["config_count"] + summary["log_count"]
        ),
        latest_checkpoint_epoch=summary.get("latest_checkpoint_epoch"),
        latest_log_status=summary.get("latest_log_status"),
        final_metrics=summary.get("final_metrics", {}),
        training_duration_seconds=summary.get("training_duration_seconds"),
    )


def _detail_from_dict(summary: dict[str, Any]) -> ExperimentDetail:
    """Build ExperimentDetail from the manager's summary dict."""
    return ExperimentDetail(
        experiment_id=summary["experiment_id"],
        checkpoint_count=summary["checkpoint_count"],
        config_count=summary["config_count"],
        log_count=summary["log_count"],
        latest_checkpoint_epoch=summary.get("latest_checkpoint_epoch"),
        latest_config_id=summary.get("latest_config_id"),
        latest_log_status=summary.get("latest_log_status"),
        training_duration_seconds=summary.get("training_duration_seconds"),
        final_metrics=summary.get("final_metrics", {}),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=ListExperimentsResponse,
    responses={
        503: {"model": ErrorResponse, "description": "Services not initialized"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def list_experiments(
    limit: int = Query(100, ge=1, le=1000, description="Max experiments to return"),
    offset: int = Query(0, ge=0, description="Number of experiments to skip"),
) -> ListExperimentsResponse:
    """List all experiments with optional pagination.

    Returns a summary for each experiment including artifact counts,
    latest checkpoint epoch, and final training metrics.
    """
    manager = _require_artifact_manager()

    try:
        experiment_ids = manager.list_experiments()
        total = len(experiment_ids)

        summaries: list[ExperimentSummary] = []
        for eid in experiment_ids[offset : offset + limit]:
            try:
                raw = manager.experiment_summary(eid)
                summaries.append(_summary_from_dict(raw))
            except Exception:
                # Best-effort: include a minimal entry if summary fails
                summaries.append(
                    ExperimentSummary(
                        experiment_id=eid,
                        artifact_count=0,
                    )
                )

        return ListExperimentsResponse(
            success=True,
            experiments=summaries,
            count=total,
        )
    except Exception as e:
        logger.exception("Failed to list experiments")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list experiments: {e}",
        ) from e


@router.get(
    "/compare",
    response_model=CompareExperimentsResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Experiment not found"},
        503: {"model": ErrorResponse, "description": "Services not initialized"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def compare_experiments(
    experiment_id_1: str = Query(
        ..., alias="experiment_id_1", description="First experiment ID"
    ),
    experiment_id_2: str = Query(
        ..., alias="experiment_id_2", description="Second experiment ID"
    ),
) -> CompareExperimentsResponse:
    """Compare two experiments side-by-side.

    Returns both experiment details and the difference between their
    final metrics (experiment_2 - experiment_1).
    """
    manager = _require_artifact_manager()

    try:
        all_ids = manager.list_experiments()

        for eid in (experiment_id_1, experiment_id_2):
            if eid not in all_ids:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Experiment '{eid}' not found",
                )

        raw1 = manager.experiment_summary(experiment_id_1)
        raw2 = manager.experiment_summary(experiment_id_2)

        detail1 = _detail_from_dict(raw1)
        detail2 = _detail_from_dict(raw2)

        # Compute metric diffs (experiment_2 - experiment_1)
        metrics1 = raw1.get("final_metrics", {})
        metrics2 = raw2.get("final_metrics", {})
        all_keys = set(metrics1) | set(metrics2)
        metric_diffs: dict[str, float] = {}
        for key in all_keys:
            metric_diffs[key] = metrics2.get(key, 0.0) - metrics1.get(key, 0.0)

        return CompareExperimentsResponse(
            success=True,
            experiment_1=detail1,
            experiment_2=detail2,
            metric_diffs=metric_diffs,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to compare experiments")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to compare experiments: {e}",
        ) from e


@router.get(
    "/{experiment_id}",
    response_model=GetExperimentResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Experiment not found"},
        503: {"model": ErrorResponse, "description": "Services not initialized"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def get_experiment(experiment_id: str) -> GetExperimentResponse:
    """Get detailed information about a single experiment."""
    manager = _require_artifact_manager()

    try:
        all_ids = manager.list_experiments()
        if experiment_id not in all_ids:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Experiment '{experiment_id}' not found",
            )

        raw = manager.experiment_summary(experiment_id)
        return GetExperimentResponse(
            success=True,
            experiment=_detail_from_dict(raw),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to get experiment %s", experiment_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get experiment: {e}",
        ) from e


@router.get(
    "/{experiment_id}/artifacts",
    response_model=ArtifactsResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Experiment not found"},
        503: {"model": ErrorResponse, "description": "Services not initialized"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def get_experiment_artifacts(
    experiment_id: str,
    artifact_type: str | None = Query(
        None, description="Filter by type: checkpoint, config, log"
    ),
) -> ArtifactsResponse:
    """Get all artifacts for an experiment, optionally filtered by type."""
    manager = _require_artifact_manager()

    try:
        type_filter: ArtifactType | None = None
        if artifact_type:
            try:
                type_filter = ArtifactType(artifact_type)
            except ValueError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid artifact_type '{artifact_type}'. "
                    f"Must be one of: checkpoint, config, log",
                ) from e

        artifacts = manager.get_artifacts(experiment_id, type_filter)
        infos = [_artifact_to_info(a) for a in artifacts]

        return ArtifactsResponse(
            success=True,
            experiment_id=experiment_id,
            artifacts=infos,
            count=len(infos),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to get artifacts for %s", experiment_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get artifacts: {e}",
        ) from e


@router.get(
    "/{experiment_id}/hyperparameters",
    response_model=HyperparametersResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Experiment not found"},
        503: {"model": ErrorResponse, "description": "Services not initialized"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def get_experiment_hyperparameters(
    experiment_id: str,
) -> HyperparametersResponse:
    """Get hyperparameters associated with an experiment.

    Hyperparameters are extracted from config artifacts for the experiment.
    """
    manager = _require_artifact_manager()

    try:
        configs = manager.get_configs(experiment_id)

        hparams_list: list[HyperparameterInfo] = []
        for cfg in configs:
            hparams_list.append(
                HyperparameterInfo(
                    learning_rate=cfg.hyperparameters.get("learning_rate"),
                    batch_size=cfg.hyperparameters.get("batch_size"),
                    epochs=cfg.hyperparameters.get("epochs"),
                    optimizer=cfg.hyperparameters.get("optimizer"),
                    loss_function=cfg.hyperparameters.get("loss_function"),
                    model_architecture=(
                        cfg.model_architecture
                        if isinstance(cfg.model_architecture, dict)
                        else {"name": cfg.model_architecture}
                    ),
                    data_config=cfg.data_config,
                    random_seed=cfg.random_seed,
                    framework=cfg.framework,
                    captured_at=cfg.created_at.isoformat(),
                )
            )

        return HyperparametersResponse(
            success=True,
            experiment_id=experiment_id,
            hyperparameters=hparams_list,
            count=len(hparams_list),
        )
    except Exception as e:
        logger.exception("Failed to get hyperparameters for %s", experiment_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get hyperparameters: {e}",
        ) from e


@router.get(
    "/{experiment_id}/lineage",
    response_model=LineageResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Experiment not found"},
        503: {"model": ErrorResponse, "description": "Services not initialized"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def get_experiment_lineage(experiment_id: str) -> LineageResponse:
    """Get the full lineage graph for an experiment.

    Returns all ancestor and descendant nodes (data sources, models, parent
    experiments) connected to the given experiment.
    """
    _require_artifact_manager()

    if _lineage_tracker is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Lineage tracker not initialized",
        )

    try:
        # Combine ancestors and descendants
        ancestors = _lineage_tracker.get_lineage(experiment_id)
        descendants = _lineage_tracker.get_descendants(experiment_id)

        # Merge graphs
        merged = ancestors.merge(descendants)

        nodes = [
            LineageNodeInfo(
                node_id=n.node_id,
                node_type=n.node_type.value,
                created_at=n.created_at.isoformat(),
                metadata=n.metadata,
            )
            for n in merged.nodes.values()
        ]
        edges = [
            LineageEdgeInfo(
                edge_id=e.edge_id,
                source_id=e.source_id,
                target_id=e.target_id,
                relationship_type=e.relationship_type.value,
                created_at=e.created_at.isoformat(),
                metadata=e.metadata,
            )
            for e in merged.edges
        ]

        return LineageResponse(
            success=True,
            experiment_id=experiment_id,
            nodes=nodes,
            edges=edges,
        )
    except Exception as e:
        logger.exception("Failed to get lineage for %s", experiment_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get lineage: {e}",
        ) from e


@router.post(
    "/{experiment_id}/rollback",
    response_model=RollbackResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Experiment not found"},
        400: {"model": ErrorResponse, "description": "No suitable rollback target"},
        503: {"model": ErrorResponse, "description": "Services not initialized"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def rollback_experiment(
    experiment_id: str,
    target_checkpoint_epoch: int | None = Query(
        None, description="Epoch of the checkpoint to rollback to"
    ),
) -> RollbackResponse:
    """Rollback an experiment to a specific checkpoint.

    If *target_checkpoint_epoch* is provided, rolls back to the checkpoint
    with that epoch number.  Otherwise rolls back to the best checkpoint
    (lowest val_loss).
    """
    manager = _require_artifact_manager()

    try:
        all_ids = manager.list_experiments()
        if experiment_id not in all_ids:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Experiment '{experiment_id}' not found",
            )

        checkpoints = manager.get_checkpoints(experiment_id)
        if not checkpoints:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No checkpoints found for experiment '{experiment_id}'",
            )

        if target_checkpoint_epoch is not None:
            target = next(
                (c for c in checkpoints if c.epoch == target_checkpoint_epoch),
                None,
            )
            if target is None:
                available = [c.epoch for c in checkpoints]
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Checkpoint with epoch {target_checkpoint_epoch} not found. "
                        f"Available epochs: {available}"
                    ),
                )
        else:
            target = manager.get_best_checkpoint(
                experiment_id, metric_key="val_loss", minimize=True
            )
            if target is None:
                target = checkpoints[0]

        return RollbackResponse(
            success=True,
            message=(
                f"Experiment '{experiment_id}' rolled back to checkpoint "
                f"'{target.artifact_id}' at epoch {target.epoch}"
            ),
            experiment_id=experiment_id,
            rolled_back_to=target.artifact_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to rollback experiment %s", experiment_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to rollback experiment: {e}",
        ) from e
