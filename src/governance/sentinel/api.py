"""
Task Sentinel API - FastAPI endpoints for validation (ST-GOV-003).

Provides REST API for:
- Task validation
- Approval requests
- Pending approvals management
- Conflict detection

Story: ST-GOV-003
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import logging

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .task_sentinel import TaskSentinel, TaskInfo, SentinelConfig
from .dependency_checker import DependencyChecker, DependencyDeclaration
from .conflict_detector import (
    ConflictDetector,
    ScopeDeclaration,
    ConflictSeverity,
)
from .approval_workflow import ApprovalWorkflow, ApprovalStatus

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Task Decomposition Sentinel API",
    description="API for validating task sizes, detecting conflicts, and managing approvals",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)


# Pydantic models for request/response
class ValidateTaskRequest(BaseModel):
    """Request to validate a task."""

    task_id: str = Field(..., description="Task identifier")
    story_points: float = Field(..., ge=0, description="Story points estimate")
    title: str = Field(..., description="Task title")
    description: Optional[str] = Field(None, description="Task description")
    assignee: Optional[str] = Field(None, description="Assigned agent/person")
    labels: list[str] = Field(default_factory=list, description="Task labels")


class ValidateTaskResponse(BaseModel):
    """Response from task validation."""

    is_valid: bool
    requires_approval: bool
    story_points: float
    max_allowed: int
    message: str
    task_id: str


class RequestApprovalRequest(BaseModel):
    """Request to create an approval request."""

    task_id: str
    story_points: float = Field(..., ge=0)
    justification: str = Field(..., min_length=10, description="Why task is oversized")
    requester: str
    timeout_hours: Optional[int] = Field(None, description="Custom timeout")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class RequestApprovalResponse(BaseModel):
    """Response from approval request."""

    success: bool
    request_id: str
    message: str


class ApproveTaskRequest(BaseModel):
    """Request to approve a task."""

    approver: str
    notes: Optional[str] = None


class RejectTaskRequest(BaseModel):
    """Request to reject a task."""

    rejector: str
    reason: str


class PendingApprovalResponse(BaseModel):
    """Response with pending approval details."""

    request_id: str
    task_id: str
    story_points: float
    justification: str
    requester: str
    status: str
    created_at: Optional[str]
    expires_at: Optional[str]


class CheckDependenciesRequest(BaseModel):
    """Request to check dependencies."""

    declarations: list[dict]
    required_scopes: Optional[dict[str, list[str]]] = None


class CheckDependenciesResponse(BaseModel):
    """Response from dependency check."""

    is_valid: bool
    has_circular_dependencies: bool
    missing_dependencies: list[str]
    circular_paths: list[list[str]]
    undeclared_scopes: list[str]
    message: str


class CheckConflictsRequest(BaseModel):
    """Request to check conflicts."""

    scopes: list[dict]


class ConflictDetail(BaseModel):
    """Details of a detected conflict."""

    conflict_type: str
    severity: str
    task_ids: list[str]
    description: str
    affected_paths: list[str]
    affected_resources: list[str]
    resolution_hint: Optional[str]


class CheckConflictsResponse(BaseModel):
    """Response from conflict check."""

    has_conflicts: bool
    has_critical_conflicts: bool
    conflicts: list[ConflictDetail]
    safe_for_parallel: bool
    message: str


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str
    redis_connected: bool
    timestamp: str


# Global instances (will be injected in production)
_sentinel: Optional[TaskSentinel] = None
_dependency_checker: Optional[DependencyChecker] = None
_conflict_detector: Optional[ConflictDetector] = None
_approval_workflow: Optional[ApprovalWorkflow] = None


def get_sentinel() -> TaskSentinel:
    """Get or create TaskSentinel instance."""
    global _sentinel
    if _sentinel is None:
        # Try to connect to Redis
        try:
            import redis

            redis_client = redis.Redis(
                host="host.docker.internal",
                port=6380,
                db=0,
                decode_responses=True,
            )
            redis_client.ping()
            _sentinel = TaskSentinel(redis_client=redis_client)
        except Exception as e:
            logger.warning(f"Redis not available, using in-memory sentinel: {e}")
            _sentinel = TaskSentinel(redis_client=None)
    return _sentinel


def get_dependency_checker() -> DependencyChecker:
    """Get or create DependencyChecker instance."""
    global _dependency_checker
    if _dependency_checker is None:
        _dependency_checker = DependencyChecker()
    return _dependency_checker


def get_conflict_detector() -> ConflictDetector:
    """Get or create ConflictDetector instance."""
    global _conflict_detector
    if _conflict_detector is None:
        try:
            import redis

            redis_client = redis.Redis(
                host="host.docker.internal",
                port=6380,
                db=0,
                decode_responses=True,
            )
            redis_client.ping()
            _conflict_detector = ConflictDetector(redis_client=redis_client)
        except Exception:
            _conflict_detector = ConflictDetector(redis_client=None)
    return _conflict_detector


def get_approval_workflow() -> ApprovalWorkflow:
    """Get or create ApprovalWorkflow instance."""
    global _approval_workflow
    if _approval_workflow is None:
        try:
            import redis

            redis_client = redis.Redis(
                host="host.docker.internal",
                port=6380,
                db=0,
                decode_responses=True,
            )
            redis_client.ping()
            _approval_workflow = ApprovalWorkflow(redis_client=redis_client)
        except Exception as e:
            logger.warning(f"Redis not available: {e}")
            raise RuntimeError("Redis required for approval workflow")
    return _approval_workflow


# API Endpoints
@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """Health check endpoint."""
    redis_connected = False
    try:
        import redis

        client = redis.Redis(host="host.docker.internal", port=6380, db=0)
        client.ping()
        redis_connected = True
    except Exception:
        pass

    return HealthResponse(
        status="healthy",
        version="1.0.0",
        redis_connected=redis_connected,
        timestamp=datetime.utcnow().isoformat(),
    )


@app.post(
    "/validate-task",
    response_model=ValidateTaskResponse,
    tags=["Task Validation"],
)
async def validate_task(
    request: ValidateTaskRequest,
    sentinel: TaskSentinel = Depends(get_sentinel),
):
    """
    Validate a task's size against constitution bounds.

    Returns whether the task is valid or requires approval.
    """
    task = TaskInfo(
        task_id=request.task_id,
        story_points=request.story_points,
        title=request.title,
        description=request.description,
        assignee=request.assignee,
        labels=request.labels,
    )

    result = sentinel.validate_task_size(task)

    return ValidateTaskResponse(
        is_valid=result.is_valid,
        requires_approval=result.requires_approval,
        story_points=result.story_points,
        max_allowed=result.max_allowed,
        message=result.message,
        task_id=result.task_id or request.task_id,
    )


@app.post(
    "/request-approval",
    response_model=RequestApprovalResponse,
    tags=["Approvals"],
)
async def request_approval(
    request: RequestApprovalRequest,
    workflow: ApprovalWorkflow = Depends(get_approval_workflow),
):
    """
    Request approval for an oversized task.

    Requires justification for keeping the task oversized.
    """
    try:
        request_id = workflow.request_approval(
            task_id=request.task_id,
            story_points=request.story_points,
            justification=request.justification,
            requester=request.requester,
            timeout_hours=request.timeout_hours,
            metadata=request.metadata,
        )

        return RequestApprovalResponse(
            success=True,
            request_id=request_id,
            message=f"Approval request created: {request_id}",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.get(
    "/pending-approvals",
    response_model=list[PendingApprovalResponse],
    tags=["Approvals"],
)
async def get_pending_approvals(
    limit: int = 50,
    workflow: ApprovalWorkflow = Depends(get_approval_workflow),
):
    """
    Get all pending approval requests.

    Returns a list of requests awaiting approval.
    """
    requests = workflow.get_pending_approvals(limit=limit)

    return [
        PendingApprovalResponse(
            request_id=r.request_id,
            task_id=r.task_id,
            story_points=r.story_points,
            justification=r.justification,
            requester=r.requester,
            status=r.status.value,
            created_at=r.created_at.isoformat() if r.created_at else None,
            expires_at=r.expires_at.isoformat() if r.expires_at else None,
        )
        for r in requests
    ]


@app.post(
    "/approve-task/{request_id}",
    response_model=RequestApprovalResponse,
    tags=["Approvals"],
)
async def approve_task(
    request_id: str,
    request: ApproveTaskRequest,
    workflow: ApprovalWorkflow = Depends(get_approval_workflow),
):
    """
    Approve a pending approval request.

    Marks the task as approved and allows it to proceed.
    """
    result = workflow.approve(
        request_id=request_id,
        approver=request.approver,
        notes=request.notes,
    )

    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)

    return RequestApprovalResponse(
        success=True,
        request_id=request_id,
        message=result.message,
    )


@app.post(
    "/reject-task/{request_id}",
    response_model=RequestApprovalResponse,
    tags=["Approvals"],
)
async def reject_task(
    request_id: str,
    request: RejectTaskRequest,
    workflow: ApprovalWorkflow = Depends(get_approval_workflow),
):
    """
    Reject a pending approval request.

    Marks the task as rejected with a reason.
    """
    result = workflow.reject(
        request_id=request_id,
        rejector=request.rejector,
        reason=request.reason,
    )

    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)

    return RequestApprovalResponse(
        success=True,
        request_id=request_id,
        message=result.message,
    )


@app.post(
    "/check-dependencies",
    response_model=CheckDependenciesResponse,
    tags=["Dependencies"],
)
async def check_dependencies(
    request: CheckDependenciesRequest,
    checker: DependencyChecker = Depends(get_dependency_checker),
):
    """
    Check task dependencies for issues.

    Validates for:
    - Circular dependencies
    - Missing dependencies
    - Undeclared scopes
    """
    declarations = [DependencyDeclaration.from_dict(d) for d in request.declarations]

    result = checker.check_dependencies(
        declarations=declarations,
        required_scopes=request.required_scopes,
    )

    return CheckDependenciesResponse(
        is_valid=result.is_valid,
        has_circular_dependencies=result.has_circular_dependencies,
        missing_dependencies=result.missing_dependencies,
        circular_paths=result.circular_paths,
        undeclared_scopes=result.undeclared_scopes,
        message=result.message,
    )


@app.post(
    "/check-conflicts",
    response_model=CheckConflictsResponse,
    tags=["Conflicts"],
)
async def check_conflicts(
    request: CheckConflictsRequest,
    detector: ConflictDetector = Depends(get_conflict_detector),
):
    """
    Check for conflicts between task scopes.

    Detects:
    - Scope overlaps (file/directory)
    - Shared resource conflicts
    - Global lock contention
    """
    scopes = []
    for s in request.scopes:
        scopes.append(
            ScopeDeclaration(
                task_id=s.get("task_id", ""),
                scope_globs=s.get("scope_globs", []),
                read_only_globs=s.get("read_only_globs", []),
                forbidden_globs=s.get("forbidden_globs", []),
                shared_resources=s.get("shared_resources", []),
                global_locks=s.get("global_locks", []),
            )
        )

    result = detector.detect_conflicts(scopes)

    conflicts = [
        ConflictDetail(
            conflict_type=c.conflict_type.value,
            severity=c.severity.value,
            task_ids=c.task_ids,
            description=c.description,
            affected_paths=c.affected_paths,
            affected_resources=c.affected_resources,
            resolution_hint=c.resolution_hint,
        )
        for c in result.conflicts
    ]

    return CheckConflictsResponse(
        has_conflicts=result.has_conflicts,
        has_critical_conflicts=result.has_critical_conflicts,
        conflicts=conflicts,
        safe_for_parallel=result.safe_for_parallel,
        message=result.message,
    )


@app.get(
    "/is-task-approved/{task_id}",
    tags=["Approvals"],
)
async def is_task_approved(
    task_id: str,
    workflow: ApprovalWorkflow = Depends(get_approval_workflow),
):
    """Check if a task has been approved."""
    approved = workflow.is_task_approved(task_id)
    return {"task_id": task_id, "approved": approved}


# Error handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    logger.exception("Unhandled exception in API")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"},
    )


# Router for mounting in main app
def create_router():
    """Create a router for mounting in the main FastAPI app."""
    from fastapi import APIRouter

    router = APIRouter(prefix="/api/v1/sentinel", tags=["Sentinel"])

    # Include all routes
    router.get("/health", response_model=HealthResponse)(health_check)
    router.post("/validate-task", response_model=ValidateTaskResponse)(validate_task)
    router.post("/request-approval", response_model=RequestApprovalResponse)(
        request_approval
    )
    router.get("/pending-approvals", response_model=list[PendingApprovalResponse])(
        get_pending_approvals
    )
    router.post("/approve-task/{request_id}", response_model=RequestApprovalResponse)(
        approve_task
    )
    router.post("/reject-task/{request_id}", response_model=RequestApprovalResponse)(
        reject_task
    )
    router.post("/check-dependencies", response_model=CheckDependenciesResponse)(
        check_dependencies
    )
    router.post("/check-conflicts", response_model=CheckConflictsResponse)(
        check_conflicts
    )
    router.get("/is-task-approved/{task_id}")(is_task_approved)

    return router
