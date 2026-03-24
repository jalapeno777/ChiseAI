"""REST API endpoints for Quality Gate.

Provides HTTP access to quality scoring, gate evaluation,
and override management.

For ST-GOV-006: Self-Review Quality Gate
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from src.governance.quality_gate.gate import (
    QualityGate,
)
from src.governance.quality_gate.override import (
    OverrideManager,
)
from src.governance.quality_gate.scorer import (
    QualityScorer,
)

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/v1/quality-gate", tags=["quality-gate"])

# Global instances (initialized by application)
_gate: QualityGate | None = None
_scorer: QualityScorer | None = None
_override_manager: OverrideManager | None = None


def set_quality_gate(gate: QualityGate) -> None:
    """Set the global quality gate instance."""
    global _gate
    _gate = gate
    logger.info("Quality gate registered with API")


def set_scorer(scorer: QualityScorer) -> None:
    """Set the global quality scorer instance."""
    global _scorer
    _scorer = scorer
    logger.info("Quality scorer registered with API")


def set_override_manager(manager: OverrideManager) -> None:
    """Set the global override manager instance."""
    global _override_manager
    _override_manager = manager
    logger.info("Override manager registered with API")


def get_gate() -> QualityGate:
    """Get the quality gate or raise 503."""
    if _gate is None:
        raise HTTPException(
            status_code=503,
            detail="Quality gate not initialized",
        )
    return _gate


def get_scorer() -> QualityScorer:
    """Get the quality scorer or raise 503."""
    if _scorer is None:
        raise HTTPException(
            status_code=503,
            detail="Quality scorer not initialized",
        )
    return _scorer


def get_override_manager() -> OverrideManager:
    """Get the override manager or raise 503."""
    if _override_manager is None:
        raise HTTPException(
            status_code=503,
            detail="Override manager not initialized",
        )
    return _override_manager


@router.post("/evaluate", response_model=dict[str, Any])
async def evaluate_pr(
    pr_number: int,
    changed_files: list[str],
    branch: str,
    repo_path: str = Query(".", description="Path to repository root"),
) -> dict[str, Any]:
    """Evaluate a PR through the quality gate.

    Args:
        pr_number: PR number
        changed_files: List of changed file paths
        branch: Branch name
        repo_path: Path to repository root

    Returns:
        QualityGateResult with pass/fail status and recommendations
    """
    try:
        gate = get_gate()
        result = gate.evaluate(
            pr_number=pr_number,
            changed_files=changed_files,
            branch=branch,
            repo_path=repo_path,
        )

        return {
            "success": True,
            "data": result.to_dict(),
        }

    except Exception as e:
        logger.error(f"Failed to evaluate PR: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to evaluate PR: {str(e)}",
        ) from e


@router.post("/score", response_model=dict[str, Any])
async def calculate_score(
    changed_files: list[str],
    pr_number: int | None = None,
    branch: str | None = None,
    repo_path: str = Query(".", description="Path to repository root"),
) -> dict[str, Any]:
    """Calculate quality score without blocking.

    Args:
        changed_files: List of changed file paths
        pr_number: Optional PR number
        branch: Optional branch name
        repo_path: Path to repository root

    Returns:
        QualityScore breakdown
    """
    try:
        scorer = get_scorer()
        score = scorer.calculate_score(
            changed_files=changed_files,
            pr_number=pr_number,
            branch=branch,
            repo_path=repo_path,
        )

        return {
            "success": True,
            "data": score.to_dict(),
        }

    except Exception as e:
        logger.error(f"Failed to calculate score: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to calculate score: {str(e)}",
        ) from e


@router.get("/stats", response_model=dict[str, Any])
async def get_stats() -> dict[str, Any]:
    """Get quality gate statistics.

    Returns:
        Stats including validation gate status
    """
    try:
        gate = get_gate()
        return {
            "success": True,
            "data": gate.get_stats(),
        }

    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get stats: {str(e)}",
        ) from e


@router.post("/override", response_model=dict[str, Any])
async def create_override_request(
    pr_number: int,
    requester: str,
    justification: str,
    risk_assessment: str,
    rollback_plan: str,
    affected_systems: list[str] | None = None,
    expiration_hours: int = Query(24, ge=1, le=24),
) -> dict[str, Any]:
    """Create a human override request.

    Args:
        pr_number: PR number to override
        requester: ID of person requesting override
        justification: Reason for override (min 50 characters)
        risk_assessment: Risk level (low/medium/high/critical)
        rollback_plan: Plan for rolling back changes
        affected_systems: List of affected systems
        expiration_hours: Hours until override expires (max 24)

    Returns:
        Created override request
    """
    try:
        manager = get_override_manager()
        override = manager.create_request(
            pr_number=pr_number,
            requester=requester,
            justification=justification,
            risk_assessment=risk_assessment,
            rollback_plan=rollback_plan,
            affected_systems=affected_systems,
            expiration_hours=expiration_hours,
        )

        return {
            "success": True,
            "data": override.to_dict(),
            "message": "Override request created. Requires approval.",
        }

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.error(f"Failed to create override: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create override: {str(e)}",
        ) from e


@router.post("/override/{override_id}/approve", response_model=dict[str, Any])
async def approve_override(
    override_id: str,
    approver: str,
) -> dict[str, Any]:
    """Approve an override request.

    Args:
        override_id: Override request ID
        approver: ID of approver

    Returns:
        Approved override request
    """
    try:
        manager = get_override_manager()
        override = manager.approve_request(override_id, approver)

        return {
            "success": True,
            "data": override.to_dict(),
            "message": "Override approved. Can now be activated.",
        }

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.error(f"Failed to approve override: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to approve override: {str(e)}",
        ) from e


@router.post("/override/{override_id}/activate", response_model=dict[str, Any])
async def activate_override(
    override_id: str,
) -> dict[str, Any]:
    """Activate an approved override.

    Args:
        override_id: Override ID to activate

    Returns:
        Activated override
    """
    try:
        manager = get_override_manager()
        override = manager.activate_override(override_id)

        return {
            "success": True,
            "data": override.to_dict(),
            "message": "Override activated. PR can now be merged.",
        }

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.error(f"Failed to activate override: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to activate override: {str(e)}",
        ) from e


@router.post("/override/{override_id}/revoke", response_model=dict[str, Any])
async def revoke_override(
    override_id: str,
    revoked_by: str,
    reason: str,
) -> dict[str, Any]:
    """Revoke an active override.

    Args:
        override_id: Override ID to revoke
        revoked_by: ID of revoker
        reason: Reason for revocation

    Returns:
        Revoked override
    """
    try:
        manager = get_override_manager()
        override = manager.revoke_override(override_id, revoked_by, reason)

        return {
            "success": True,
            "data": override.to_dict(),
            "message": "Override revoked.",
        }

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.error(f"Failed to revoke override: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to revoke override: {str(e)}",
        ) from e


@router.post("/override/{override_id}/rollback", response_model=dict[str, Any])
async def rollback_override(
    override_id: str,
    rolled_back_by: str,
) -> dict[str, Any]:
    """Roll back an override (within 24-hour window).

    Args:
        override_id: Override ID to roll back
        rolled_back_by: ID of person performing rollback

    Returns:
        Rolled back override
    """
    try:
        manager = get_override_manager()
        override = manager.rollback_override(override_id, rolled_back_by)

        return {
            "success": True,
            "data": override.to_dict(),
            "message": "Override rolled back successfully.",
        }

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.error(f"Failed to rollback override: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to rollback override: {str(e)}",
        ) from e


@router.get("/override/{override_id}", response_model=dict[str, Any])
async def get_override(override_id: str) -> dict[str, Any]:
    """Get an override request by ID.

    Args:
        override_id: Override request ID

    Returns:
        Override request details
    """
    try:
        manager = get_override_manager()
        override = manager.get_request(override_id)

        if override is None:
            raise HTTPException(
                status_code=404,
                detail=f"Override not found: {override_id}",
            )

        return {
            "success": True,
            "data": override.to_dict(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get override: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get override: {str(e)}",
        ) from e


@router.get("/overrides/active", response_model=dict[str, Any])
async def get_active_overrides() -> dict[str, Any]:
    """Get all active overrides.

    Returns:
        List of active overrides
    """
    try:
        manager = get_override_manager()
        overrides = manager.get_active_overrides()

        return {
            "success": True,
            "data": {
                "overrides": [o.to_dict() for o in overrides],
                "count": len(overrides),
            },
        }

    except Exception as e:
        logger.error(f"Failed to get active overrides: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get active overrides: {str(e)}",
        ) from e


@router.get("/overrides/pending", response_model=dict[str, Any])
async def get_pending_overrides() -> dict[str, Any]:
    """Get all pending override requests.

    Returns:
        List of pending override requests
    """
    try:
        manager = get_override_manager()
        requests = manager.get_pending_requests()

        return {
            "success": True,
            "data": {
                "requests": [r.to_dict() for r in requests],
                "count": len(requests),
            },
        }

    except Exception as e:
        logger.error(f"Failed to get pending overrides: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get pending overrides: {str(e)}",
        ) from e


@router.get("/audit-trail", response_model=dict[str, Any])
async def get_audit_trail(
    override_id: str | None = Query(None, description="Filter by override ID"),
    pr_number: int | None = Query(None, description="Filter by PR number"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
) -> dict[str, Any]:
    """Get audit trail entries.

    Args:
        override_id: Filter by override ID
        pr_number: Filter by PR number
        limit: Maximum entries to return

    Returns:
        Audit trail entries
    """
    try:
        manager = get_override_manager()
        trail = manager.get_audit_trail(
            override_id=override_id,
            pr_number=pr_number,
            limit=limit,
        )

        return {
            "success": True,
            "data": {
                "entries": trail,
                "count": len(trail),
            },
        }

    except Exception as e:
        logger.error(f"Failed to get audit trail: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get audit trail: {str(e)}",
        ) from e


@router.get("/health", response_model=dict[str, Any])
async def health_check() -> dict[str, Any]:
    """Health check for quality gate service.

    Returns:
        Health status
    """
    return {
        "success": True,
        "status": "healthy",
        "service": "quality-gate",
        "components": {
            "scorer": _scorer is not None,
            "gate": _gate is not None,
            "override_manager": _override_manager is not None,
        },
    }
