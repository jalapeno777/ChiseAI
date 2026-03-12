"""FastAPI routes for rollback operations.

For ST-NS-042: Rollback Coordinator with Pre-flight Validation
For ST-SAFETY-003: Rollback Automation
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, status

from autonomous_control_plane.components.rollback_coordinator import (
    RollbackCoordinator,
)
from autonomous_control_plane.components.rollback_automation import (
    RollbackAutomationCoordinator,
)
from autonomous_control_plane.models.rollback import (
    RollbackStatus,
    RollbackTemplateType,
    RollbackTrigger,
    RollbackTriggerType,
    CoordinatedRollbackConfig,
)

router = APIRouter(prefix="/rollback", tags=["rollback"])

# Global coordinator instances (would be injected in production)
_coordinator: RollbackCoordinator | None = None
_automation_coordinator: RollbackAutomationCoordinator | None = None


def get_coordinator() -> RollbackCoordinator:
    """Get the rollback coordinator instance.

    Returns:
        RollbackCoordinator

    Raises:
        HTTPException: If coordinator not initialized
    """
    if _coordinator is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Rollback coordinator not initialized",
        )
    return _coordinator


def set_coordinator(coordinator: RollbackCoordinator) -> None:
    """Set the rollback coordinator instance.

    Args:
        coordinator: RollbackCoordinator instance
    """
    global _coordinator
    _coordinator = coordinator


def get_automation_coordinator() -> RollbackAutomationCoordinator:
    """Get the automation coordinator instance.

    Returns:
        RollbackAutomationCoordinator

    Raises:
        HTTPException: If coordinator not initialized
    """
    if _automation_coordinator is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Rollback automation coordinator not initialized",
        )
    return _automation_coordinator


def set_automation_coordinator(coordinator: RollbackAutomationCoordinator) -> None:
    """Set the automation coordinator instance.

    Args:
        coordinator: RollbackAutomationCoordinator instance
    """
    global _automation_coordinator
    _automation_coordinator = coordinator


@router.post("/validate", response_model=dict[str, Any])
async def validate_rollback(
    target_state: str,
    force: bool = False,
) -> dict[str, Any]:
    """Run pre-flight validation for rollback.

    Args:
        target_state: Target state to rollback to
        force: If True, skip validation

    Returns:
        Validation result
    """
    coordinator = get_coordinator()
    result = await coordinator.validate_rollback(target_state, force)
    return result.to_dict()


@router.post("/execute", response_model=dict[str, Any])
async def execute_rollback(
    target_state: str,
    force: bool = False,
    initiated_by: str = "api",
) -> dict[str, Any]:
    """Execute rollback with pre-flight validation.

    Args:
        target_state: Target state to rollback to
        force: If True, bypass validation
        initiated_by: Who initiated the rollback

    Returns:
        Rollback operation result
    """
    coordinator = get_coordinator()
    operation = await coordinator.execute_rollback(
        target_state=target_state,
        force=force,
        initiated_by=initiated_by,
    )
    return operation.to_dict()


@router.post("/emergency", response_model=dict[str, Any])
async def emergency_rollback(
    target_state: str,
    initiated_by: str = "api",
) -> dict[str, Any]:
    """Execute emergency rollback (bypasses validation).

    Args:
        target_state: Target state to rollback to
        initiated_by: Who initiated the rollback

    Returns:
        Rollback operation result
    """
    coordinator = get_coordinator()
    operation = await coordinator.emergency_rollback(
        target_state=target_state,
        initiated_by=initiated_by,
    )
    return operation.to_dict()


@router.get("/{operation_id}", response_model=dict[str, Any])
async def get_rollback_status(operation_id: str) -> dict[str, Any]:
    """Get rollback operation status.

    Args:
        operation_id: Operation ID

    Returns:
        Rollback operation

    Raises:
        HTTPException: If operation not found
    """
    coordinator = get_coordinator()
    operation = await coordinator.get_operation(operation_id)

    if not operation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rollback operation {operation_id} not found",
        )

    return operation.to_dict()


@router.get("/history", response_model=list[dict[str, Any]])
async def get_rollback_history(
    target_state: str | None = None,
    status: RollbackStatus | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    """Get rollback history.

    Args:
        target_state: Filter by target state
        status: Filter by status
        limit: Maximum results
        offset: Pagination offset

    Returns:
        List of rollback operations
    """
    coordinator = get_coordinator()

    if target_state:
        operations = await coordinator.get_history(target_state, limit)
    else:
        operations = await coordinator.list_operations(status, limit, offset)

    return [op.to_dict() for op in operations]


@router.get("/metrics", response_model=dict[str, Any])
async def get_rollback_metrics() -> dict[str, Any]:
    """Get rollback metrics.

    Returns:
        Rollback metrics
    """
    coordinator = get_coordinator()
    metrics = await coordinator.get_metrics()
    return metrics.to_dict()


# ==================== Automation Endpoints ====================


@router.post("/automated/execute", response_model=dict[str, Any])
async def execute_automated_rollback(
    target_state: str,
    template_type: RollbackTemplateType = RollbackTemplateType.FULL_DEPLOYMENT,
    services: list[str] | None = None,
    skip_impact_analysis: bool = False,
    force: bool = False,
    initiated_by: str = "api",
) -> dict[str, Any]:
    """Execute rollback with full automation pipeline.

    Args:
        target_state: Target state to rollback to
        template_type: Type of rollback template
        services: List of services to rollback
        skip_impact_analysis: Skip impact analysis
        force: Bypass confirmation requirements
        initiated_by: Who initiated the rollback

    Returns:
        Rollback result with impact analysis and validation
    """
    coordinator = get_automation_coordinator()
    result = await coordinator.execute_rollback_with_automation(
        target_state=target_state,
        template_type=template_type,
        services=services,
        skip_impact_analysis=skip_impact_analysis,
        force=force,
        initiated_by=initiated_by,
    )
    return result


@router.post("/impact-analysis", response_model=dict[str, Any])
async def analyze_rollback_impact(
    target_state: str,
    services: list[str] | None = None,
    template_type: RollbackTemplateType = RollbackTemplateType.FULL_DEPLOYMENT,
) -> dict[str, Any]:
    """Analyze impact of rollback operation.

    Args:
        target_state: Target state to rollback to
        services: List of services to analyze
        template_type: Type of rollback template

    Returns:
        Impact analysis results
    """
    coordinator = get_automation_coordinator()
    analysis = await coordinator.analyze_rollback_impact(
        target_state=target_state,
        services=services,
        template_type=template_type,
    )
    return analysis.to_dict()


# ==================== Template Endpoints ====================


@router.get("/templates", response_model=list[dict[str, Any]])
async def list_rollback_templates() -> list[dict[str, Any]]:
    """List all available rollback templates.

    Returns:
        List of rollback templates
    """
    coordinator = get_automation_coordinator()
    templates = coordinator.list_templates()
    return [t.to_dict() for t in templates]


@router.get("/templates/{template_id}", response_model=dict[str, Any])
async def get_rollback_template(template_id: str) -> dict[str, Any]:
    """Get a specific rollback template.

    Args:
        template_id: Template identifier

    Returns:
        Rollback template

    Raises:
        HTTPException: If template not found
    """
    coordinator = get_automation_coordinator()
    template = coordinator.get_template(template_id)

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template {template_id} not found",
        )

    return template.to_dict()


# ==================== Trigger Endpoints ====================


@router.get("/triggers", response_model=list[dict[str, Any]])
async def list_rollback_triggers(
    enabled_only: bool = False,
) -> list[dict[str, Any]]:
    """List rollback triggers.

    Args:
        enabled_only: Only return enabled triggers

    Returns:
        List of triggers
    """
    coordinator = get_automation_coordinator()
    triggers = coordinator.list_triggers(enabled_only=enabled_only)
    return [t.to_dict() for t in triggers]


@router.post("/triggers", response_model=dict[str, Any])
async def create_rollback_trigger(
    trigger_type: RollbackTriggerType,
    name: str,
    target_state: str,
    template_id: str,
    description: str = "",
    sensitivity: str = "medium",
    conditions: dict[str, Any] | None = None,
    require_confirmation: bool = False,
) -> dict[str, Any]:
    """Create a new rollback trigger.

    Args:
        trigger_type: Type of trigger
        name: Trigger name
        target_state: Target state for rollback
        template_id: Template to use
        description: Trigger description
        sensitivity: Sensitivity level (low/medium/high)
        conditions: Trigger conditions
        require_confirmation: Require manual confirmation

    Returns:
        Created trigger
    """
    coordinator = get_automation_coordinator()

    trigger = RollbackTrigger(
        trigger_type=trigger_type,
        name=name,
        description=description,
        target_state=target_state,
        template_id=template_id,
        sensitivity=sensitivity,
        conditions=conditions or {},
        require_confirmation=require_confirmation,
    )

    coordinator.register_trigger(trigger)
    return trigger.to_dict()


@router.post("/triggers/default", response_model=list[dict[str, Any]])
async def create_default_triggers(
    target_state: str,
    sensitivity: str = "medium",
) -> list[dict[str, Any]]:
    """Create default rollback triggers.

    Args:
        target_state: Target state for rollback
        sensitivity: Sensitivity level (low/medium/high)

    Returns:
        List of created triggers
    """
    coordinator = get_automation_coordinator()
    triggers = coordinator.create_default_triggers(target_state, sensitivity)
    return [t.to_dict() for t in triggers]


@router.post("/triggers/monitoring/start")
async def start_trigger_monitoring(
    interval_seconds: float = 10.0,
) -> dict[str, str]:
    """Start trigger monitoring.

    Args:
        interval_seconds: Monitoring interval in seconds

    Returns:
        Status message
    """
    coordinator = get_automation_coordinator()
    await coordinator.start_trigger_monitoring(interval_seconds)
    return {"status": "started", "interval_seconds": str(interval_seconds)}


@router.post("/triggers/monitoring/stop")
async def stop_trigger_monitoring() -> dict[str, str]:
    """Stop trigger monitoring.

    Returns:
        Status message
    """
    coordinator = get_automation_coordinator()
    await coordinator.stop_trigger_monitoring()
    return {"status": "stopped"}


# ==================== Coordinated Rollback Endpoints ====================


@router.post("/coordinated/execute", response_model=dict[str, Any])
async def execute_coordinated_rollback(
    target_state: str,
    services: list[str],
    parallel_groups: list[list[str]] | None = None,
    dependencies: dict[str, list[str]] | None = None,
    circuit_breaker_integration: bool = True,
    retry_budget_preservation: bool = True,
    initiated_by: str = "api",
) -> dict[str, Any]:
    """Execute coordinated multi-service rollback.

    Args:
        target_state: Target state to rollback to
        services: List of services to rollback
        parallel_groups: Groups of services for parallel execution
        dependencies: Service dependency mapping
        circuit_breaker_integration: Open circuit breakers before rollback
        retry_budget_preservation: Preserve retry budgets during rollback
        initiated_by: Who initiated the rollback

    Returns:
        Rollback results for each service
    """
    coordinator = get_automation_coordinator()

    config = CoordinatedRollbackConfig(
        service_order=services,
        parallel_groups=parallel_groups or [],
        dependencies=dependencies or {},
        circuit_breaker_integration=circuit_breaker_integration,
        retry_budget_preservation=retry_budget_preservation,
    )

    results = await coordinator.execute_coordinated_rollback(
        config=config,
        target_state=target_state,
        initiated_by=initiated_by,
    )

    return {service: op.to_dict() for service, op in results.items()}


# ==================== Post-Rollback Validation Endpoints ====================


@router.post("/validation/{operation_id}", response_model=dict[str, Any])
async def run_post_rollback_validation(
    operation_id: str,
    services: list[str] | None = None,
) -> dict[str, Any]:
    """Run post-rollback validation.

    Args:
        operation_id: Rollback operation ID
        services: Services to validate

    Returns:
        Validation results
    """
    coordinator = get_automation_coordinator()
    result = await coordinator.run_post_rollback_validation(operation_id, services)
    return result.to_dict()
