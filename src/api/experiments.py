"""Experiment Query REST API for ChiseAI.

Provides FastAPI endpoints for querying experiment history, comparing
experiments, and rolling back to previous experiment versions.

Endpoints:
    GET  /api/v1/experiments - List experiments with optional filters
    GET  /api/v1/experiments/{experiment_id} - Get full experiment details
    GET  /api/v1/experiments/{experiment_id}/artifacts - List experiment artifacts
    GET  /api/v1/experiments/{experiment_id}/hyperparameters - Get hyperparams
    GET  /api/v1/experiments/{experiment_id}/lineage - Get lineage graph
    GET  /api/v1/experiments/compare - Compare two experiments
    POST /api/v1/experiments/{experiment_id}/rollback - Rollback to version

Example:
    from src.api.experiments import router
    app.include_router(router)
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Protocol
from enum import Enum

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    status,
)
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/v1/experiments", tags=["experiments"])


# ---------------------------------------------------------------------------
# Protocol for experiment store (allows mocking in tests)
# ---------------------------------------------------------------------------


class ExperimentStatus(str, Enum):
    """Status of an experiment."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExperimentStore(Protocol):
    """Protocol for the experiment store backend.

    Any implementation must provide these methods.  The API router
    accepts a store that satisfies this protocol.
    """

    def list_experiments(
        self,
        model_id: str | None = None,
        experiment_status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]: ...

    def get_experiment(self, experiment_id: str) -> dict[str, Any] | None: ...

    def get_artifacts(self, experiment_id: str) -> list[dict[str, Any]]: ...

    def get_hyperparameters(self, experiment_id: str) -> dict[str, Any] | None: ...

    def get_lineage(self, experiment_id: str) -> dict[str, Any] | None: ...

    def compare_experiments(self, exp1_id: str, exp2_id: str) -> dict[str, Any]: ...

    def rollback_experiment(self, experiment_id: str) -> dict[str, Any]: ...


# Global store instance (initialized by application)
_store: ExperimentStore | None = None


def set_experiment_store(store: ExperimentStore) -> None:
    """Set the global experiment store instance.

    Args:
        store: ExperimentStore instance
    """
    global _store
    _store = store
    logger.info("Experiment store registered with API")


def get_experiment_store() -> ExperimentStore | None:
    """Get the global experiment store instance.

    Returns:
        ExperimentStore instance or None
    """
    return _store


# ---------------------------------------------------------------------------
# Pydantic response models
# ---------------------------------------------------------------------------


class ExperimentSummary(BaseModel):
    """Summary view of an experiment."""

    experiment_id: str
    model_id: str
    status: str
    created_at: str
    updated_at: str | None = None
    metrics: dict[str, float] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class ExperimentDetail(ExperimentSummary):
    """Full experiment details."""

    description: str | None = None
    hyperparameters: dict[str, Any] = Field(default_factory=dict)
    artifact_count: int = 0
    duration_seconds: float | None = None
    error_message: str | None = None


class ArtifactInfo(BaseModel):
    """Single artifact info."""

    artifact_id: str
    artifact_type: str
    created_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArtifactListResponse(BaseModel):
    """Response for experiment artifacts."""

    success: bool
    experiment_id: str
    artifacts: list[ArtifactInfo]
    count: int


class HyperparametersResponse(BaseModel):
    """Response for experiment hyperparameters."""

    success: bool
    experiment_id: str
    hyperparameters: dict[str, Any]
    fingerprint: str | None = None


class LineageNode(BaseModel):
    """A single node in the lineage graph."""

    experiment_id: str
    model_id: str
    status: str
    created_at: str


class LineageEdge(BaseModel):
    """An edge connecting two lineage nodes."""

    source_id: str
    target_id: str
    relationship: str


class LineageResponse(BaseModel):
    """Response for experiment lineage."""

    success: bool
    experiment_id: str
    nodes: list[LineageNode]
    edges: list[LineageEdge]


class ComparisonMetrics(BaseModel):
    """Metric differences between two experiments."""

    metric_name: str
    exp1_value: float | None = None
    exp2_value: float | None = None
    difference: float | None = None


class ComparisonHyperparam(BaseModel):
    """Hyperparameter differences between two experiments."""

    param_name: str
    exp1_value: Any = None
    exp2_value: Any = None
    changed: bool = False


class ComparisonResponse(BaseModel):
    """Response for experiment comparison."""

    success: bool
    experiment1: ExperimentSummary
    experiment2: ExperimentSummary
    metric_diffs: list[ComparisonMetrics]
    hyperparam_diffs: list[ComparisonHyperparam]


class RollbackResponse(BaseModel):
    """Response for rollback operation."""

    success: bool
    message: str
    experiment_id: str
    rolled_back_to_version: str | None = None
    previous_version: str | None = None


class ExperimentListResponse(BaseModel):
    """Response for listing experiments."""

    success: bool
    experiments: list[ExperimentSummary]
    count: int


class ErrorResponse(BaseModel):
    """Error response model."""

    success: bool = False
    error: str
    detail: str | None = None


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _require_store() -> ExperimentStore:
    """Return the store or raise 503."""
    if _store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Experiment store not initialized",
        )
    return _store


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=ExperimentListResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def list_experiments(
    model_id: str | None = Query(None, description="Filter by model ID"),
    status_filter: str | None = Query(
        None, alias="status", description="Filter by status"
    ),
    limit: int = Query(50, ge=1, le=500, description="Maximum experiments to return"),
    offset: int = Query(0, ge=0, description="Number of experiments to skip"),
) -> ExperimentListResponse:
    """List experiments with optional filtering.

    Args:
        model_id: Optional model ID to filter by
        status_filter: Optional status to filter by
        limit: Maximum number of results
        offset: Pagination offset

    Returns:
        Paginated list of experiment summaries
    """
    store = _require_store()

    try:
        experiments = store.list_experiments(
            model_id=model_id,
            experiment_status=status_filter,
            limit=limit,
            offset=offset,
        )

        summaries = [
            ExperimentSummary(
                experiment_id=exp.get("experiment_id", ""),
                model_id=exp.get("model_id", ""),
                status=exp.get("status", "unknown"),
                created_at=exp.get("created_at", ""),
                updated_at=exp.get("updated_at"),
                metrics=exp.get("metrics", {}),
                tags=exp.get("tags", []),
            )
            for exp in experiments
        ]

        return ExperimentListResponse(
            success=True,
            experiments=summaries,
            count=len(summaries),
        )
    except Exception as e:
        logger.exception("Failed to list experiments")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list experiments: {e}",
        ) from e


@router.get(
    "/compare",
    response_model=ComparisonResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        404: {"model": ErrorResponse, "description": "Experiment not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def compare_experiments(
    exp1_id: str = Query(..., alias="exp1_id", description="First experiment ID"),
    exp2_id: str = Query(..., alias="exp2_id", description="Second experiment ID"),
) -> ComparisonResponse:
    """Compare two experiments side by side.

    Returns metric differences and hyperparameter differences between
    the two experiments.

    Args:
        exp1_id: First experiment ID
        exp2_id: Second experiment ID

    Returns:
        Comparison results
    """
    store = _require_store()

    try:
        comparison = store.compare_experiments(exp1_id, exp2_id)

        exp1_summary = ExperimentSummary(
            experiment_id=comparison.get("experiment1", {}).get(
                "experiment_id", exp1_id
            ),
            model_id=comparison.get("experiment1", {}).get("model_id", ""),
            status=comparison.get("experiment1", {}).get("status", "unknown"),
            created_at=comparison.get("experiment1", {}).get("created_at", ""),
            metrics=comparison.get("experiment1", {}).get("metrics", {}),
            tags=comparison.get("experiment1", {}).get("tags", []),
        )
        exp2_summary = ExperimentSummary(
            experiment_id=comparison.get("experiment2", {}).get(
                "experiment_id", exp2_id
            ),
            model_id=comparison.get("experiment2", {}).get("model_id", ""),
            status=comparison.get("experiment2", {}).get("status", "unknown"),
            created_at=comparison.get("experiment2", {}).get("created_at", ""),
            metrics=comparison.get("experiment2", {}).get("metrics", {}),
            tags=comparison.get("experiment2", {}).get("tags", []),
        )

        metric_diffs = [
            ComparisonMetrics(
                metric_name=m.get("metric_name", ""),
                exp1_value=m.get("exp1_value"),
                exp2_value=m.get("exp2_value"),
                difference=m.get("difference"),
            )
            for m in comparison.get("metric_diffs", [])
        ]

        hyperparam_diffs = [
            ComparisonHyperparam(
                param_name=h.get("param_name", ""),
                exp1_value=h.get("exp1_value"),
                exp2_value=h.get("exp2_value"),
                changed=h.get("changed", False),
            )
            for h in comparison.get("hyperparam_diffs", [])
        ]

        return ComparisonResponse(
            success=True,
            experiment1=exp1_summary,
            experiment2=exp2_summary,
            metric_diffs=metric_diffs,
            hyperparam_diffs=hyperparam_diffs,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.exception(f"Failed to compare experiments {exp1_id} vs {exp2_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to compare experiments: {e}",
        ) from e


@router.get(
    "/{experiment_id}",
    response_model=ExperimentDetail,
    responses={
        404: {"model": ErrorResponse, "description": "Experiment not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def get_experiment(experiment_id: str) -> ExperimentDetail:
    """Get full details for a specific experiment.

    Args:
        experiment_id: Unique experiment identifier

    Returns:
        Full experiment details including artifacts and hyperparams
    """
    store = _require_store()

    try:
        exp = store.get_experiment(experiment_id)
        if exp is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Experiment not found: {experiment_id}",
            )

        return ExperimentDetail(
            experiment_id=exp.get("experiment_id", experiment_id),
            model_id=exp.get("model_id", ""),
            status=exp.get("status", "unknown"),
            created_at=exp.get("created_at", ""),
            updated_at=exp.get("updated_at"),
            metrics=exp.get("metrics", {}),
            tags=exp.get("tags", []),
            description=exp.get("description"),
            hyperparameters=exp.get("hyperparameters", {}),
            artifact_count=exp.get("artifact_count", 0),
            duration_seconds=exp.get("duration_seconds"),
            error_message=exp.get("error_message"),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get experiment {experiment_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get experiment: {e}",
        ) from e


@router.get(
    "/{experiment_id}/artifacts",
    response_model=ArtifactListResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Experiment not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def get_experiment_artifacts(experiment_id: str) -> ArtifactListResponse:
    """List all artifacts for an experiment.

    Args:
        experiment_id: Unique experiment identifier

    Returns:
        List of artifacts associated with the experiment
    """
    store = _require_store()

    try:
        artifacts = store.get_artifacts(experiment_id)

        artifact_infos = [
            ArtifactInfo(
                artifact_id=a.get("artifact_id", ""),
                artifact_type=a.get("artifact_type", "unknown"),
                created_at=a.get("created_at", ""),
                metadata=a.get("metadata", {}),
            )
            for a in artifacts
        ]

        return ArtifactListResponse(
            success=True,
            experiment_id=experiment_id,
            artifacts=artifact_infos,
            count=len(artifact_infos),
        )
    except Exception as e:
        logger.exception(f"Failed to get artifacts for experiment {experiment_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get artifacts: {e}",
        ) from e


@router.get(
    "/{experiment_id}/hyperparameters",
    response_model=HyperparametersResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Experiment not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def get_experiment_hyperparameters(
    experiment_id: str,
) -> HyperparametersResponse:
    """Get hyperparameters for an experiment.

    Args:
        experiment_id: Unique experiment identifier

    Returns:
        Hyperparameter set with fingerprint
    """
    store = _require_store()

    try:
        hp_data = store.get_hyperparameters(experiment_id)
        if hp_data is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Hyperparameters not found for experiment: {experiment_id}",
            )

        return HyperparametersResponse(
            success=True,
            experiment_id=experiment_id,
            hyperparameters=hp_data.get("hyperparameters", {}),
            fingerprint=hp_data.get("fingerprint"),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            f"Failed to get hyperparameters for experiment {experiment_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get hyperparameters: {e}",
        ) from e


@router.get(
    "/{experiment_id}/lineage",
    response_model=LineageResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Experiment not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def get_experiment_lineage(experiment_id: str) -> LineageResponse:
    """Get lineage graph for an experiment.

    Returns the dependency graph showing how this experiment relates
    to parent experiments and derived experiments.

    Args:
        experiment_id: Unique experiment identifier

    Returns:
        Lineage graph with nodes and edges
    """
    store = _require_store()

    try:
        lineage = store.get_lineage(experiment_id)
        if lineage is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Lineage not found for experiment: {experiment_id}",
            )

        nodes = [
            LineageNode(
                experiment_id=n.get("experiment_id", ""),
                model_id=n.get("model_id", ""),
                status=n.get("status", "unknown"),
                created_at=n.get("created_at", ""),
            )
            for n in lineage.get("nodes", [])
        ]

        edges = [
            LineageEdge(
                source_id=e.get("source_id", ""),
                target_id=e.get("target_id", ""),
                relationship=e.get("relationship", ""),
            )
            for e in lineage.get("edges", [])
        ]

        return LineageResponse(
            success=True,
            experiment_id=experiment_id,
            nodes=nodes,
            edges=edges,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get lineage for experiment {experiment_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get lineage: {e}",
        ) from e


@router.post(
    "/{experiment_id}/rollback",
    response_model=RollbackResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Experiment not found"},
        400: {"model": ErrorResponse, "description": "Invalid rollback request"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def rollback_experiment(experiment_id: str) -> RollbackResponse:
    """Rollback to this experiment's model version.

    Reverts the active model to the version produced by this experiment.

    Args:
        experiment_id: Experiment whose model version to roll back to

    Returns:
        Rollback confirmation with version info
    """
    store = _require_store()

    try:
        result = store.rollback_experiment(experiment_id)

        return RollbackResponse(
            success=result.get("success", True),
            message=result.get(
                "message",
                f"Rolled back to experiment {experiment_id}",
            ),
            experiment_id=experiment_id,
            rolled_back_to_version=result.get("rolled_back_to_version"),
            previous_version=result.get("previous_version"),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.exception(f"Failed to rollback experiment {experiment_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to rollback experiment: {e}",
        ) from e
