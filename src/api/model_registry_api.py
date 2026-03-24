"""Model Registry REST API for ChiseAI.

Provides FastAPI endpoints for model versioning, storage, and retrieval.

Endpoints:
    POST /api/v1/models - Register new model
    GET /api/v1/models/{name} - List all versions
    GET /api/v1/models/{name}/{version} - Get specific model
    GET /api/v1/models/{name}/latest - Get latest model
    POST /api/v1/models/{name}/rollback - Rollback to version
    GET /api/v1/models/{name}/history - Get version history
    GET /api/v1/models/{name}/compare - Compare two versions
    GET /health - Health check endpoint

Example:
    from src.api.model_registry_api import router
    app.include_router(router)
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import (
    APIRouter,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field, field_validator

from ml.models.model_registry import ModelRegistry
from ml.models.model_storage import (
    ModelMetadata,
    ModelNotFoundError,
    ModelRegistryError,
    ModelValidationError,
    ModelVersionExistsError,
)

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/v1/models", tags=["models"])

# Global registry instance (initialized by application)
_registry: ModelRegistry | None = None


def set_model_registry(registry: ModelRegistry) -> None:
    """Set the global model registry instance.

    Args:
        registry: ModelRegistry instance
    """
    global _registry
    _registry = registry
    logger.info("Model registry registered with API")


def get_model_registry() -> ModelRegistry | None:
    """Get the global model registry instance.

    Returns:
        ModelRegistry instance or None
    """
    return _registry


# Pydantic models for request/response
class ModelMetadataRequest(BaseModel):
    """Request model for model metadata."""

    model_name: str = Field(..., min_length=1, description="Name of the model")
    version: str = Field(
        ...,
        pattern=r"^\d+\.\d+\.\d+$",
        description="Semantic version (MAJOR.MINOR.PATCH)",
    )
    training_data: str = Field(
        ..., min_length=1, description="Reference to training dataset"
    )
    hyperparameters: dict[str, Any] = Field(
        default_factory=dict, description="Model hyperparameters"
    )
    metrics: dict[str, float] = Field(
        default_factory=dict, description="Performance metrics"
    )
    tags: list[str] = Field(default_factory=list, description="Tags for categorization")

    @field_validator("version")
    @classmethod
    def validate_version_format(cls, v: str) -> str:
        """Validate semantic version format."""
        parts = v.split(".")
        if len(parts) != 3:
            raise ValueError("Version must be in MAJOR.MINOR.PATCH format")
        for part in parts:
            if not part.isdigit():
                raise ValueError("Version parts must be numeric")
        return v


class ModelMetadataResponse(BaseModel):
    """Response model for model metadata."""

    model_name: str
    version: str
    created_at: str
    training_data: str
    hyperparameters: dict[str, Any]
    metrics: dict[str, float]
    tags: list[str]
    checksum: str | None = None


class ModelVersionInfo(BaseModel):
    """Model version information."""

    version: str
    created_at: str
    model_name: str
    checksum: str | None = None


class RegisterModelResponse(BaseModel):
    """Response for model registration."""

    success: bool
    message: str
    model: ModelVersionInfo


class ListVersionsResponse(BaseModel):
    """Response for listing model versions."""

    success: bool
    model_name: str
    versions: list[ModelVersionInfo]
    count: int


class GetModelResponse(BaseModel):
    """Response for getting a specific model."""

    success: bool
    model_name: str
    version: str
    metadata: ModelMetadataResponse


class RollbackResponse(BaseModel):
    """Response for rollback operation."""

    success: bool
    message: str
    model_name: str
    rolled_back_to: str


class HistoryResponse(BaseModel):
    """Response for version history."""

    success: bool
    model_name: str
    history: list[dict[str, Any]]


class CompareResponse(BaseModel):
    """Response for version comparison."""

    success: bool
    model_name: str
    version1: dict[str, Any]
    version2: dict[str, Any]
    metric_diffs: dict[str, float]


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    registry_initialized: bool
    timestamp: str


class ErrorResponse(BaseModel):
    """Error response model."""

    success: bool = False
    error: str
    detail: str | None = None


@router.post(
    "",
    response_model=RegisterModelResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        409: {"model": ErrorResponse, "description": "Version already exists"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def register_model(
    model_file: UploadFile = File(  # noqa: B008
        ..., description="Model file to upload"
    ),
    model_name: str = Form(..., min_length=1, description="Name of the model"),
    version: str = Form(
        ..., pattern=r"^\d+\.\d+\.\d+$", description="Semantic version"
    ),
    training_data: str = Form(
        ..., min_length=1, description="Training dataset reference"
    ),
    hyperparameters: str = Form("{}", description="JSON string of hyperparameters"),
    metrics: str = Form("{}", description="JSON string of metrics"),
    tags: str = Form("[]", description="JSON string of tags array"),
) -> RegisterModelResponse:
    """Register a new model version.

    Uploads a model file and registers it with the given metadata.
    Model versions are immutable - once registered, they cannot be modified.

    Args:
        model_file: The model file to upload (pickle/joblib format)
        model_name: Name of the model
        version: Semantic version (e.g., "1.0.0")
        training_data: Reference to training dataset
        hyperparameters: JSON string of hyperparameters
        metrics: JSON string of performance metrics
        tags: JSON string of tags array

    Returns:
        Registration response with version info

    Raises:
        HTTPException: If registration fails
    """
    if _registry is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model registry not initialized",
        )

    try:
        import json
        import pickle

        # Parse JSON strings
        try:
            hyperparams_dict = json.loads(hyperparameters)
            metrics_dict = json.loads(metrics)
            tags_list = json.loads(tags)
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid JSON in parameters: {e}",
            ) from e

        # Read and deserialize model file
        try:
            content = await model_file.read()
            model = pickle.loads(content)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to load model file: {e}",
            ) from e

        # Create metadata
        metadata = ModelMetadata(
            model_name=model_name,
            version=version,
            created_at=datetime.now(UTC),
            training_data=training_data,
            hyperparameters=hyperparams_dict,
            metrics=metrics_dict,
            tags=tags_list,
        )

        # Register the model
        model_version = _registry.register_model(model, metadata)

        return RegisterModelResponse(
            success=True,
            message=f"Model {model_name}@{version} registered successfully",
            model=ModelVersionInfo(
                version=model_version.version,
                created_at=model_version.created_at.isoformat(),
                model_name=model_version.model_name,
                checksum=model_version.checksum,
            ),
        )

    except ModelVersionExistsError as e:
        logger.warning(f"Version exists error: {e}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        ) from e
    except ModelValidationError as e:
        logger.warning(f"Validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except ModelRegistryError as e:
        logger.error(f"Registry error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        ) from e
    except HTTPException:
        # Re-raise HTTPException without modification
        raise
    except Exception as e:
        logger.exception("Unexpected error during model registration")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to register model: {e}",
        ) from e


@router.get(
    "/{name}",
    response_model=ListVersionsResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Model not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def list_versions(
    name: str,
    limit: int = Query(
        100, ge=1, le=1000, description="Maximum number of versions to return"
    ),
    offset: int = Query(0, ge=0, description="Number of versions to skip"),
) -> ListVersionsResponse:
    """List all versions of a model.

    Args:
        name: Name of the model
        limit: Maximum number of versions to return
        offset: Number of versions to skip

    Returns:
        List of model versions

    Raises:
        HTTPException: If operation fails
    """
    if _registry is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model registry not initialized",
        )

    try:
        versions = _registry.list_versions(name)

        # Apply pagination
        total = len(versions)
        paginated_versions = versions[offset : offset + limit]

        return ListVersionsResponse(
            success=True,
            model_name=name,
            versions=[
                ModelVersionInfo(
                    version=v.version,
                    created_at=v.created_at.isoformat(),
                    model_name=v.model_name,
                    checksum=v.checksum,
                )
                for v in paginated_versions
            ],
            count=total,
        )

    except Exception as e:
        logger.exception(f"Failed to list versions for model {name}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list versions: {e}",
        ) from e


@router.get(
    "/{name}/latest",
    response_model=GetModelResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Model not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def get_latest_model(name: str) -> GetModelResponse:
    """Get the latest version of a model.

    Args:
        name: Name of the model

    Returns:
        Latest model metadata

    Raises:
        HTTPException: If model not found or operation fails
    """
    if _registry is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model registry not initialized",
        )

    try:
        model, metadata = _registry.get_latest(name)

        return GetModelResponse(
            success=True,
            model_name=name,
            version=metadata.version,
            metadata=ModelMetadataResponse(
                model_name=metadata.model_name,
                version=metadata.version,
                created_at=metadata.created_at.isoformat(),
                training_data=metadata.training_data,
                hyperparameters=metadata.hyperparameters,
                metrics=metadata.metrics,
                tags=metadata.tags,
                checksum=metadata.checksum,
            ),
        )

    except ModelNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.exception(f"Failed to get latest model {name}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get latest model: {e}",
        ) from e


@router.post(
    "/{name}/rollback",
    response_model=RollbackResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Model not found"},
        400: {"model": ErrorResponse, "description": "Invalid version"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def rollback_model(
    name: str,
    version: str = Query(..., description="Version to rollback to"),
) -> RollbackResponse:
    """Rollback to a previous model version.

    Updates the "latest" pointer to the target version without
    modifying the actual model files (immutable registry).

    Args:
        name: Name of the model
        version: Version to rollback to

    Returns:
        Rollback confirmation

    Raises:
        HTTPException: If rollback fails
    """
    if _registry is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model registry not initialized",
        )

    try:
        success = _registry.rollback(name, version)

        if success:
            return RollbackResponse(
                success=True,
                message=f"Successfully rolled back {name} to version {version}",
                model_name=name,
                rolled_back_to=version,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Rollback operation failed",
            )

    except ModelNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.exception(f"Failed to rollback model {name} to {version}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to rollback: {e}",
        ) from e


@router.get(
    "/{name}/history",
    response_model=HistoryResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Model not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def get_version_history(name: str) -> HistoryResponse:
    """Get detailed version history for a model.

    Args:
        name: Name of the model

    Returns:
        Version history with metadata

    Raises:
        HTTPException: If operation fails
    """
    if _registry is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model registry not initialized",
        )

    try:
        history = _registry.get_version_history(name)

        return HistoryResponse(
            success=True,
            model_name=name,
            history=history,
        )

    except Exception as e:
        logger.exception(f"Failed to get history for model {name}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get version history: {e}",
        ) from e


@router.get(
    "/{name}/compare",
    response_model=CompareResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Model not found"},
        400: {"model": ErrorResponse, "description": "Invalid version"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def compare_versions(
    name: str,
    v1: str = Query(..., alias="version1", description="First version to compare"),
    v2: str = Query(..., alias="version2", description="Second version to compare"),
) -> CompareResponse:
    """Compare two model versions.

    Args:
        name: Name of the model
        v1: First version to compare
        v2: Second version to compare

    Returns:
        Comparison results with metric differences

    Raises:
        HTTPException: If comparison fails
    """
    if _registry is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model registry not initialized",
        )

    try:
        comparison = _registry.compare_versions(name, v1, v2)

        return CompareResponse(
            success=True,
            model_name=name,
            version1=comparison["version1"],
            version2=comparison["version2"],
            metric_diffs=comparison["metric_diffs"],
        )

    except ModelNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.exception(f"Failed to compare versions for model {name}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to compare versions: {e}",
        ) from e


@router.get(
    "/{name}/{version}",
    response_model=GetModelResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Model not found"},
        400: {"model": ErrorResponse, "description": "Invalid version format"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def get_model(name: str, version: str) -> GetModelResponse:
    """Get a specific version of a model.

    Args:
        name: Name of the model
        version: Version string (e.g., "1.0.0")

    Returns:
        Model metadata

    Raises:
        HTTPException: If model not found or operation fails
    """
    if _registry is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model registry not initialized",
        )

    try:
        model, metadata = _registry.get_model(name, version)

        return GetModelResponse(
            success=True,
            model_name=name,
            version=version,
            metadata=ModelMetadataResponse(
                model_name=metadata.model_name,
                version=metadata.version,
                created_at=metadata.created_at.isoformat(),
                training_data=metadata.training_data,
                hyperparameters=metadata.hyperparameters,
                metrics=metadata.metrics,
                tags=metadata.tags,
                checksum=metadata.checksum,
            ),
        )

    except ModelNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.exception(f"Failed to get model {name}@{version}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get model: {e}",
        ) from e


@router.delete(
    "/{name}/{version}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        404: {"model": ErrorResponse, "description": "Model not found"},
        400: {"model": ErrorResponse, "description": "Cannot delete latest version"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def delete_version(name: str, version: str) -> None:
    """Delete a specific model version.

    Warning: This permanently deletes the model files. Use with caution.
    Cannot delete the current "latest" version.

    Args:
        name: Name of the model
        version: Version to delete

    Raises:
        HTTPException: If deletion fails
    """
    if _registry is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model registry not initialized",
        )

    try:
        _registry.delete_version(name, version)
        logger.info(f"Deleted model version: {name}@{version}")

    except ModelNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e
    except ModelRegistryError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.exception(f"Failed to delete model version {name}@{version}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete version: {e}",
        ) from e


# Health check endpoint (not under /models prefix)
health_router = APIRouter(tags=["health"])


@health_router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Check registry health status.

    Returns:
        Health status information
    """
    return HealthResponse(
        status="healthy" if _registry is not None else "unhealthy",
        registry_initialized=_registry is not None,
        timestamp=datetime.now(UTC).isoformat(),
    )
