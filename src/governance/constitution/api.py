"""Constitution API endpoints.

Provides REST API access to constitution artifacts, health checks,
and human override capability.

For ST-GOV-002: Agent Constitution Artifact
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from src.governance.constitution.artifact import (
    ConstitutionLoader,
)
from src.governance.constitution.audit_logger import (
    AuditLogger,
    RiskAssessment,
)
from src.governance.constitution.violation_detector import (
    ViolationDetector,
    ViolationSeverity,
)

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/v1/constitution", tags=["constitution"])

# Global instances (initialized by application)
_loader: ConstitutionLoader | None = None
_detector: ViolationDetector | None = None
_audit_logger: AuditLogger | None = None


def set_constitution_loader(loader: ConstitutionLoader) -> None:
    """Set the global constitution loader instance."""
    global _loader
    _loader = loader
    logger.info("Constitution loader registered with API")


def set_violation_detector(detector: ViolationDetector) -> None:
    """Set the global violation detector instance."""
    global _detector
    _detector = detector
    logger.info("Violation detector registered with API")


def set_audit_logger(audit_logger: AuditLogger) -> None:
    """Set the global audit logger instance."""
    global _audit_logger
    _audit_logger = audit_logger
    logger.info("Audit logger registered with API")


def get_loader() -> ConstitutionLoader:
    """Get the constitution loader or raise 503."""
    if _loader is None:
        raise HTTPException(
            status_code=503,
            detail="Constitution loader not initialized",
        )
    return _loader


def get_detector() -> ViolationDetector:
    """Get the violation detector or raise 503."""
    if _detector is None:
        raise HTTPException(
            status_code=503,
            detail="Violation detector not initialized",
        )
    return _detector


def get_audit_logger() -> AuditLogger:
    """Get the audit logger or raise 503."""
    if _audit_logger is None:
        raise HTTPException(
            status_code=503,
            detail="Audit logger not initialized",
        )
    return _audit_logger


@router.get("", response_model=dict[str, Any])
async def get_constitution(
    version: str | None = Query(None, description="Specific version to load"),
) -> dict[str, Any]:
    """Get the current constitution artifact.

    Args:
        version: Optional specific version to load

    Returns:
        Constitution artifact data with version, rules, boundaries, and health status

    Latency requirement: <50ms
    """
    start_time = time.time()

    try:
        loader = get_loader()
        artifact = loader.load(version)

        response = {
            "success": True,
            "data": artifact.to_dict(),
            "health": artifact.get_health_status(),
        }

        latency_ms = (time.time() - start_time) * 1000
        response["latency_ms"] = round(latency_ms, 2)

        if latency_ms > 50:
            logger.warning(
                f"Constitution API latency exceeded 50ms: {latency_ms:.2f}ms"
            )

        return response

    except FileNotFoundError as e:
        raise HTTPException(
            status_code=404,
            detail=f"Constitution version not found: {version}",
        ) from e
    except Exception as e:
        logger.error(f"Failed to get constitution: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get constitution: {str(e)}",
        ) from e


@router.get("/health", response_model=dict[str, Any])
async def get_constitution_health() -> dict[str, Any]:
    """Get constitution health status.

    Returns:
        Health status of the constitution system
    """
    try:
        loader = get_loader()
        artifact = loader.load()

        return {
            "success": True,
            "status": "healthy",
            "version": str(artifact.version),
            "loaded_at": artifact.loaded_at.isoformat(),
            "invariant_count": sum(len(v) for v in artifact.safety_invariants.values()),
            "violation_rule_count": len(
                artifact.violation_categories.get("detection_rules", [])
            ),
        }

    except Exception as e:
        logger.error(f"Failed to get constitution health: {e}")
        return {
            "success": False,
            "status": "error",
            "error": str(e),
        }


@router.get("/versions", response_model=dict[str, Any])
async def list_constitution_versions() -> dict[str, Any]:
    """List available constitution versions.

    Returns:
        List of available versions with metadata
    """
    try:
        loader = get_loader()
        versions = loader.list_versions()

        return {
            "success": True,
            "data": {
                "versions": [str(v) for v in versions],
                "count": len(versions),
                "latest": str(versions[0]) if versions else None,
            },
        }

    except Exception as e:
        logger.error(f"Failed to list versions: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list versions: {str(e)}",
        ) from e


@router.get("/invariants", response_model=dict[str, Any])
async def get_invariants(
    invariant_type: str | None = Query(
        None, description="Filter by type (hard_constraints, conditional)"
    ),
) -> dict[str, Any]:
    """Get safety invariants.

    Args:
        invariant_type: Optional filter by invariant type

    Returns:
        List of safety invariants
    """
    try:
        loader = get_loader()
        artifact = loader.load()

        invariants = artifact.safety_invariants
        if invariant_type:
            invariants = {invariant_type: invariants.get(invariant_type, [])}

        return {
            "success": True,
            "data": {k: [inv.to_dict() for inv in v] for k, v in invariants.items()},
        }

    except Exception as e:
        logger.error(f"Failed to get invariants: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get invariants: {str(e)}",
        ) from e


@router.get("/violations", response_model=dict[str, Any])
async def get_violations(
    severity: str | None = Query(
        None, description="Filter by severity (P0, P1, P2, P3)"
    ),
    resolved: bool | None = Query(None, description="Filter by resolved status"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
) -> dict[str, Any]:
    """Get detected violations.

    Args:
        severity: Filter by severity level
        resolved: Filter by resolved status
        limit: Maximum number of results

    Returns:
        List of violations
    """
    try:
        detector = get_detector()

        severity_enum = None
        if severity:
            severity_enum = ViolationSeverity(severity)

        violations = detector.get_violations(
            severity=severity_enum,
            resolved=resolved,
            limit=limit,
        )

        return {
            "success": True,
            "data": {
                "violations": [v.to_dict() for v in violations],
                "count": len(violations),
                "stats": detector.get_stats(),
            },
        }

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid severity: {severity}",
        ) from e
    except Exception as e:
        logger.error(f"Failed to get violations: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get violations: {str(e)}",
        ) from e


@router.post("/violations/detect", response_model=dict[str, Any])
async def detect_violations(
    action: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Check an action for violations.

    Args:
        action: Action text to check
        context: Additional context

    Returns:
        List of detected violations
    """
    try:
        detector = get_detector()
        violations = detector.detect(action, context)

        return {
            "success": True,
            "data": {
                "violations": [v.to_dict() for v in violations],
                "count": len(violations),
                "has_violations": len(violations) > 0,
            },
        }

    except Exception as e:
        logger.error(f"Failed to detect violations: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to detect violations: {str(e)}",
        ) from e


@router.post("/override", response_model=dict[str, Any])
async def create_override_request(
    requester: str,
    justification: str,
    risk_assessment: str,
    affected_systems: list[str],
    rollback_plan: str,
    expiration_hours: int = Query(
        24, ge=1, le=24, description="Hours until expiration"
    ),
) -> dict[str, Any]:
    """Create a human override request.

    Args:
        requester: ID of the human requesting override
        justification: Reason for override (min 50 characters)
        risk_assessment: Risk level (low, medium, high, critical)
        affected_systems: List of affected systems
        rollback_plan: Plan for rolling back changes
        expiration_hours: Hours until override expires (max 24)

    Returns:
        Created override request
    """
    try:
        audit_logger = get_audit_logger()

        # Parse risk assessment
        try:
            risk = RiskAssessment(risk_assessment.lower())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid risk assessment: {risk_assessment}. "
                f"Must be one of: low, medium, high, critical",
            )

        # Create request
        request = audit_logger.create_request(
            requester=requester,
            justification=justification,
            risk_assessment=risk,
            affected_systems=affected_systems,
            rollback_plan=rollback_plan,
            expiration_hours=expiration_hours,
        )

        return {
            "success": True,
            "data": request.to_dict(),
            "message": "Override request created. Requires approval.",
        }

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.error(f"Failed to create override request: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create override request: {str(e)}",
        ) from e


@router.post("/override/{override_id}/approve", response_model=dict[str, Any])
async def approve_override(
    override_id: str,
    approver: str,
) -> dict[str, Any]:
    """Approve an override request.

    Args:
        override_id: ID of the override request
        approver: ID of the approver

    Returns:
        Approved override request
    """
    try:
        audit_logger = get_audit_logger()
        request = audit_logger.approve_request(override_id, approver)

        return {
            "success": True,
            "data": request.to_dict(),
            "message": "Override approved. Can now be activated.",
        }

    except ValueError as e:
        raise HTTPException(
            status_code=404,
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
        override_id: ID of the override to activate

    Returns:
        Activated override
    """
    try:
        audit_logger = get_audit_logger()
        request = audit_logger.activate_override(override_id)

        return {
            "success": True,
            "data": request.to_dict(),
            "message": "Override activated. Actions can now be recorded.",
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


@router.post("/override/{override_id}/rollback", response_model=dict[str, Any])
async def rollback_override(
    override_id: str,
    rolled_back_by: str,
) -> dict[str, Any]:
    """Roll back an override (within 24-hour window).

    Args:
        override_id: ID of the override to roll back
        rolled_back_by: ID of the person performing rollback

    Returns:
        Rolled back override
    """
    try:
        audit_logger = get_audit_logger()
        request = audit_logger.rollback_override(override_id, rolled_back_by)

        return {
            "success": True,
            "data": request.to_dict(),
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


@router.post("/override/{override_id}/revoke", response_model=dict[str, Any])
async def revoke_override(
    override_id: str,
    revoked_by: str,
    reason: str,
) -> dict[str, Any]:
    """Revoke an active override.

    Args:
        override_id: ID of the override to revoke
        revoked_by: ID of the revoker
        reason: Reason for revocation

    Returns:
        Revoked override
    """
    try:
        audit_logger = get_audit_logger()
        request = audit_logger.revoke_override(override_id, revoked_by, reason)

        return {
            "success": True,
            "data": request.to_dict(),
            "message": "Override revoked.",
        }

    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.error(f"Failed to revoke override: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to revoke override: {str(e)}",
        ) from e


@router.get("/override/{override_id}", response_model=dict[str, Any])
async def get_override(override_id: str) -> dict[str, Any]:
    """Get an override request by ID.

    Args:
        override_id: ID of the override request

    Returns:
        Override request details
    """
    try:
        audit_logger = get_audit_logger()
        request = audit_logger.get_request(override_id)

        if request is None:
            raise HTTPException(
                status_code=404,
                detail=f"Override not found: {override_id}",
            )

        return {
            "success": True,
            "data": request.to_dict(),
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
        audit_logger = get_audit_logger()
        overrides = audit_logger.get_active_overrides()

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
        audit_logger = get_audit_logger()
        requests = audit_logger.get_pending_requests()

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
    event_type: str | None = Query(None, description="Filter by event type"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
) -> dict[str, Any]:
    """Get audit trail entries.

    Args:
        override_id: Filter by override ID
        event_type: Filter by event type
        limit: Maximum entries to return

    Returns:
        Audit trail entries
    """
    try:
        audit_logger = get_audit_logger()
        trail = audit_logger.get_audit_trail(
            override_id=override_id,
            event_type=event_type,
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
