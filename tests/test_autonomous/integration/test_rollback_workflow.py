"""Integration tests for Rollback Coordinator workflow.

Integration tests for ST-NS-042: Rollback Coordinator with Pre-flight Validation

These tests verify the end-to-end workflow including:
- Integration with IncidentManager
- Step-wise execution with verification
- Canary gate auto-rollback
- SLA enforcement
- Health check integration
"""

from __future__ import annotations

import time

import pytest
from src.autonomous_control_plane.components.incident_manager import IncidentManager
from src.autonomous_control_plane.components.rollback_coordinator import (
    RollbackCoordinator,
)
from src.autonomous_control_plane.models.incidents import (
    Severity,
)
from src.autonomous_control_plane.models.rollback import (
    RollbackStatus,
    RollbackStepStatus,
    ValidationCheckStatus,
)


@pytest.fixture
def incident_manager():
    """Create a real incident manager for integration tests."""
    return IncidentManager()


@pytest.fixture
def coordinator(incident_manager):
    """Create a rollback coordinator with incident manager integration."""
    return RollbackCoordinator(incident_manager=incident_manager)


class TestRollbackWorkflowIntegration:
    """Integration tests for complete rollback workflow."""

    @pytest.mark.asyncio
    async def test_pre_flight_validation_integration(self, coordinator):
        """AC1: Pre-condition validation - Integration test."""
        # Validate rollback pre-conditions
        validation = await coordinator.validate_rollback("v1.2.3")

        assert validation.valid is True
        assert len(validation.checks) >= 5

        # All checks should pass
        for check in validation.checks:
            assert check.status == ValidationCheckStatus.PASS

    @pytest.mark.asyncio
    async def test_step_wise_rollback_integration(self, coordinator):
        """AC2: Step-wise rollback with verification - Integration test."""
        operation = await coordinator.execute_rollback(
            target_state="v1.2.3",
            initiated_by="integration_test",
        )

        assert operation.status == RollbackStatus.COMPLETED
        assert len(operation.steps) == 5

        # Verify each step was executed in order
        for i, step in enumerate(operation.steps):
            assert step.order == i + 1
            assert step.status == RollbackStepStatus.COMPLETED
            assert step.started_at is not None
            assert step.completed_at is not None

    @pytest.mark.asyncio
    async def test_canary_gate_rollback_integration(self, coordinator):
        """AC3: Automatic rollback on canary failure - Integration test."""
        operation = await coordinator.handle_canary_gate_failure(
            canary_id="canary-test-123",
            target_state="v1.2.2",
            failure_reason="Error rate exceeded 5% threshold",
        )

        assert operation.status == RollbackStatus.COMPLETED
        assert operation.initiated_by == "canary_gate:canary-test-123"
        assert operation.metadata["auto_triggered"] is True
        assert operation.metadata["canary_id"] == "canary-test-123"
        assert (
            operation.metadata["failure_reason"] == "Error rate exceeded 5% threshold"
        )

    @pytest.mark.asyncio
    async def test_rollback_timing_integration(self, coordinator):
        """AC4: Rollback <=60 seconds - Integration timing test."""
        start_time = time.time()
        operation = await coordinator.execute_rollback(target_state="v1.2.3")
        elapsed = time.time() - start_time

        assert operation.status == RollbackStatus.COMPLETED
        assert elapsed < 60.0, f"Rollback took {elapsed}s, exceeding 60s SLA"
        assert operation.duration_seconds < 60.0

        # Verify SLA is enforced
        assert operation.duration_seconds <= coordinator.ROLLBACK_SLA_SECONDS

    @pytest.mark.asyncio
    async def test_post_rollback_health_integration(self, coordinator):
        """AC5: Post-rollback health checks - Integration test."""
        operation = await coordinator.execute_rollback(target_state="v1.2.3")

        assert operation.status == RollbackStatus.COMPLETED
        assert operation.post_rollback_health is not None
        assert operation.post_rollback_health.healthy is True

        # Verify all health checks passed
        for check in operation.post_rollback_health.checks:
            assert check.status.value in ("pass", "warning")

    @pytest.mark.asyncio
    async def test_rollback_history_integration(self, coordinator):
        """AC6: Full audit trail - Integration test for history."""
        # Execute multiple rollbacks
        op1 = await coordinator.execute_rollback(target_state="v1.2.3")
        op2 = await coordinator.execute_rollback(target_state="v1.2.3")
        op3 = await coordinator.execute_rollback(target_state="v1.2.2")

        # Get history
        all_history = await coordinator.get_history()
        v123_history = await coordinator.get_history(target_state="v1.2.3")

        assert len(all_history) == 3
        assert len(v123_history) == 2

        # Verify audit logs are preserved
        for op in [op1, op2, op3]:
            assert len(op.audit_log) > 0

    @pytest.mark.asyncio
    async def test_emergency_rollback_bypass_integration(self, coordinator):
        """AC7: Emergency bypass - Integration test."""
        operation = await coordinator.emergency_rollback(
            target_state="v1.2.3",
            initiated_by="emergency_test",
        )

        assert operation.status == RollbackStatus.COMPLETED
        assert operation.force is True
        assert operation.initiated_by == "emergency_test"
        assert operation.validation_result is None  # Validation skipped

    @pytest.mark.asyncio
    async def test_rollback_failure_creates_incident_integration(
        self, coordinator, incident_manager
    ):
        """Test that rollback failure creates P1 incident via IncidentManager."""
        # Register a failing step handler
        coordinator.register_step_handler(
            "restore_state",
            lambda: {"success": False, "error": "Database connection failed"},
        )

        operation = await coordinator.execute_rollback(target_state="v1.2.3")

        assert operation.status == RollbackStatus.FAILED

        # Verify incident was created
        incidents = await incident_manager.list_incidents()
        rollback_incidents = [i for i in incidents if "rollback" in i.title.lower()]

        assert len(rollback_incidents) >= 1
        assert rollback_incidents[0].severity == Severity.P1

    @pytest.mark.asyncio
    async def test_rollback_metrics_integration(self, coordinator):
        """Test metrics collection during rollback operations."""
        # Execute successful rollbacks
        await coordinator.execute_rollback(target_state="v1.2.3")
        await coordinator.execute_rollback(target_state="v1.2.3")

        # Execute failed rollback
        coordinator.register_step_handler(
            "restore_state",
            lambda: {"success": False, "error": "Failed"},
        )
        await coordinator.execute_rollback(target_state="v1.2.2")

        metrics = await coordinator.get_metrics()

        assert metrics.total_operations == 3
        assert metrics.successful == 2
        assert metrics.failed == 1
        assert "v1.2.3" in metrics.by_target_state
        assert "v1.2.2" in metrics.by_target_state

    @pytest.mark.asyncio
    async def test_rollback_callbacks_integration(self, coordinator):
        """Test event callbacks during rollback."""
        events = []

        async def on_started(op):
            events.append(("started", op.operation_id))

        async def on_completed(op):
            events.append(("completed", op.operation_id))

        coordinator.on_rollback_started(on_started)
        coordinator.on_rollback_completed(on_completed)

        operation = await coordinator.execute_rollback(target_state="v1.2.3")

        assert len(events) == 2
        assert events[0][0] == "started"
        assert events[1][0] == "completed"
        assert events[0][1] == operation.operation_id

    @pytest.mark.asyncio
    async def test_rollback_with_custom_step_handlers(self, coordinator):
        """Test rollback with custom step handlers."""
        custom_calls = []

        def custom_stop_handler():
            custom_calls.append("stop")
            return {"success": True, "message": "Custom stop"}

        def custom_restore_handler():
            custom_calls.append("restore")
            return {"success": True, "message": "Custom restore"}

        coordinator.register_step_handler("stop_new_operations", custom_stop_handler)
        coordinator.register_step_handler("restore_state", custom_restore_handler)

        operation = await coordinator.execute_rollback(target_state="v1.2.3")

        assert operation.status == RollbackStatus.COMPLETED
        assert "stop" in custom_calls
        assert "restore" in custom_calls

    @pytest.mark.asyncio
    async def test_rollback_step_verification_failure(self, coordinator):
        """Test rollback fails when step verification fails."""
        # Create a custom step handler that succeeds but we'll override verification
        operation = await coordinator.create_rollback_operation(
            target_state="v1.2.3",
        )

        # Manually set up the operation with a step that will fail verification
        async def failing_verify(step, op):
            return {"success": False, "error": "Verification failed"}

        # Replace the verification method temporarily
        original_verify = coordinator._verify_step
        coordinator._verify_step = failing_verify

        try:
            operation = await coordinator.execute_rollback(target_state="v1.2.3")
            assert operation.status == RollbackStatus.FAILED
            assert "verification" in operation.error_message.lower()
        finally:
            coordinator._verify_step = original_verify

    @pytest.mark.asyncio
    async def test_rollback_sla_exceeded(self, coordinator):
        """Test rollback failure when SLA is exceeded."""

        # Create a very slow step handler
        def slow_handler():
            time.sleep(2)  # This will exceed SLA when accumulated
            return {"success": True, "message": "Slow but done"}

        # Register slow handlers for all steps
        for action in [
            "stop_new_operations",
            "drain_in_flight_operations",
            "restore_state",
            "verify_health",
            "resume_operations",
        ]:
            coordinator.register_step_handler(action, slow_handler)

        # Temporarily reduce SLA for testing
        original_sla = coordinator.ROLLBACK_SLA_SECONDS
        coordinator.ROLLBACK_SLA_SECONDS = 1.0  # 1 second SLA

        try:
            operation = await coordinator.execute_rollback(target_state="v1.2.3")
            # Operation should fail due to SLA
            assert operation.status == RollbackStatus.FAILED
            assert "SLA" in operation.error_message or operation.duration_seconds > 1.0
        finally:
            coordinator.ROLLBACK_SLA_SECONDS = original_sla

    @pytest.mark.asyncio
    async def test_rollback_timeout_per_step(self, coordinator):
        """Test step timeout handling."""

        def slow_handler():
            time.sleep(10)  # Longer than default timeout
            return {"success": True, "message": "Too slow"}

        coordinator.register_step_handler("stop_new_operations", slow_handler)

        operation = await coordinator.execute_rollback(target_state="v1.2.3")

        assert operation.status == RollbackStatus.FAILED
        assert any(
            "timed out" in step.error_message.lower()
            for step in operation.steps
            if step.error_message
        )


class TestRollbackWithIncidentManager:
    """Integration tests for RollbackCoordinator + IncidentManager."""

    @pytest.mark.asyncio
    async def test_incident_creation_on_validation_failure(self):
        """Test P1 incident created on validation failure."""
        incident_manager = IncidentManager()
        coordinator = RollbackCoordinator(incident_manager=incident_manager)

        # Register a failing validation checker
        def failing_checker():
            from src.autonomous_control_plane.models.rollback import (
                ValidationCheck,
            )

            check = ValidationCheck(name="failing", description="Failing check")
            check.mark_fail("Validation failed")
            return check

        coordinator._validator.register_checker("failing", failing_checker)

        operation = await coordinator.execute_rollback(target_state="v1.2.3")

        assert operation.status == RollbackStatus.FAILED

        # Check incident was created
        incidents = await incident_manager.list_incidents()
        rollback_incidents = [i for i in incidents if "rollback" in i.title.lower()]
        assert len(rollback_incidents) >= 1

    @pytest.mark.asyncio
    async def test_incident_severity_for_rollback_failure(self):
        """Test that rollback failures create P1 incidents."""
        incident_manager = IncidentManager()
        coordinator = RollbackCoordinator(incident_manager=incident_manager)

        # Cause a rollback failure
        coordinator.register_step_handler(
            "restore_state",
            lambda: {"success": False, "error": "Critical failure"},
        )

        await coordinator.execute_rollback(target_state="v1.2.3")

        incidents = await incident_manager.list_incidents()
        rollback_incidents = [i for i in incidents if "rollback" in i.title.lower()]

        assert len(rollback_incidents) >= 1
        assert rollback_incidents[0].severity == Severity.P1


class TestRollbackStoreIntegration:
    """Integration tests for rollback store."""

    @pytest.mark.asyncio
    async def test_store_persists_operations(self, coordinator):
        """Test that store persists rollback operations."""
        operation = await coordinator.execute_rollback(target_state="v1.2.3")

        # Retrieve from store
        retrieved = await coordinator.get_operation(operation.operation_id)

        assert retrieved is not None
        assert retrieved.operation_id == operation.operation_id
        assert retrieved.status == operation.status
        assert len(retrieved.steps) == len(operation.steps)

    @pytest.mark.asyncio
    async def test_store_list_operations(self, coordinator):
        """Test listing operations from store."""
        await coordinator.execute_rollback(target_state="v1.2.3")
        await coordinator.execute_rollback(target_state="v1.2.2")

        operations = await coordinator.list_operations()

        assert len(operations) == 2

    @pytest.mark.asyncio
    async def test_store_filter_by_status(self, coordinator):
        """Test filtering operations by status."""
        # Successful operation
        await coordinator.execute_rollback(target_state="v1.2.3")

        # Failed operation
        coordinator.register_step_handler(
            "restore_state",
            lambda: {"success": False, "error": "Failed"},
        )
        await coordinator.execute_rollback(target_state="v1.2.2")

        completed = await coordinator.list_operations(status=RollbackStatus.COMPLETED)
        failed = await coordinator.list_operations(status=RollbackStatus.FAILED)

        assert len(completed) == 1
        assert len(failed) == 1


class TestRollbackAPIIntegration:
    """Integration tests for rollback API routes."""

    @pytest.mark.asyncio
    async def test_api_validate_endpoint(self):
        """Test the validate API endpoint."""
        from src.autonomous_control_plane.api.v1.rollback import (
            set_coordinator,
            validate_rollback,
        )

        coordinator = RollbackCoordinator()
        set_coordinator(coordinator)

        result = await validate_rollback("v1.2.3", force=False)

        assert result["valid"] is True
        assert len(result["checks"]) > 0

    @pytest.mark.asyncio
    async def test_api_execute_endpoint(self):
        """Test the execute API endpoint."""
        from src.autonomous_control_plane.api.v1.rollback import (
            execute_rollback,
            set_coordinator,
        )

        coordinator = RollbackCoordinator()
        set_coordinator(coordinator)

        result = await execute_rollback("v1.2.3", force=False, initiated_by="api_test")

        assert result["status"] == "completed"
        assert result["target_state"] == "v1.2.3"
        assert result["initiated_by"] == "api_test"

    @pytest.mark.asyncio
    async def test_api_emergency_endpoint(self):
        """Test the emergency API endpoint."""
        from src.autonomous_control_plane.api.v1.rollback import (
            emergency_rollback,
            set_coordinator,
        )

        coordinator = RollbackCoordinator()
        set_coordinator(coordinator)

        result = await emergency_rollback("v1.2.3", initiated_by="api_emergency")

        assert result["status"] == "completed"
        assert result["force"] is True

    @pytest.mark.asyncio
    async def test_api_get_status_endpoint(self):
        """Test the get status API endpoint."""
        from src.autonomous_control_plane.api.v1.rollback import (
            get_rollback_status,
            set_coordinator,
        )

        coordinator = RollbackCoordinator()
        set_coordinator(coordinator)

        operation = await coordinator.execute_rollback(target_state="v1.2.3")
        result = await get_rollback_status(operation.operation_id)

        assert result["operation_id"] == operation.operation_id
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_api_history_endpoint(self):
        """Test the history API endpoint."""
        from src.autonomous_control_plane.api.v1.rollback import (
            get_rollback_history,
            set_coordinator,
        )

        coordinator = RollbackCoordinator()
        set_coordinator(coordinator)

        await coordinator.execute_rollback(target_state="v1.2.3")
        await coordinator.execute_rollback(target_state="v1.2.3")

        result = await get_rollback_history(target_state="v1.2.3", limit=10)

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_api_metrics_endpoint(self):
        """Test the metrics API endpoint."""
        from src.autonomous_control_plane.api.v1.rollback import (
            get_rollback_metrics,
            set_coordinator,
        )

        coordinator = RollbackCoordinator()
        set_coordinator(coordinator)

        await coordinator.execute_rollback(target_state="v1.2.3")

        result = await get_rollback_metrics()

        assert result["total_operations"] == 1
        assert result["successful"] == 1


# ==================== ST-SAFETY-003: Rollback Automation Integration Tests ====================

from autonomous_control_plane.components.rollback_automation import (
    RollbackAutomationCoordinator,
)
from autonomous_control_plane.models.rollback import (
    RollbackTemplateType,
)


class TestRollbackAutomationIntegration:
    """Integration tests for Rollback Automation (ST-SAFETY-003)."""

    @pytest.fixture
    def automation_coordinator(self):
        """Create automation coordinator."""
        base_coordinator = RollbackCoordinator()
        return RollbackAutomationCoordinator(base_coordinator)

    @pytest.mark.asyncio
    async def test_full_automation_pipeline(self, automation_coordinator):
        """Test complete automation pipeline from trigger to validation."""
        # Create default triggers
        triggers = automation_coordinator.create_default_triggers(
            target_state="v1.2.3",
            sensitivity="medium",
        )
        assert len(triggers) == 3

        # Analyze impact
        analysis = await automation_coordinator.analyze_rollback_impact(
            target_state="v1.2.3",
            services=["api", "worker"],
        )
        assert hasattr(analysis, "risk_score")

        # Execute rollback with automation
        result = await automation_coordinator.execute_rollback_with_automation(
            target_state="v1.2.3",
            skip_impact_analysis=True,
        )
        assert "target_state" in result

    @pytest.mark.asyncio
    async def test_coordinated_rollback_integration(self, automation_coordinator):
        """Test coordinated multi-service rollback."""
        from autonomous_control_plane.models.rollback import CoordinatedRollbackConfig

        config = CoordinatedRollbackConfig(
            service_order=["api", "worker", "scheduler"],
            parallel_groups=[["api", "worker"], ["scheduler"]],
        )

        results = await automation_coordinator.execute_coordinated_rollback(
            config=config,
            target_state="v1.2.3",
        )

        assert len(results) == 3
        for service, operation in results.items():
            assert operation.status == RollbackStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_post_rollback_validation_integration(self, automation_coordinator):
        """Test post-rollback validation suite."""
        # Execute rollback first
        result = await automation_coordinator.execute_rollback_with_automation(
            target_state="v1.2.3",
            skip_impact_analysis=True,
        )

        operation_id = result.get("operation", {}).get("operation_id", "test-op-id")

        # Run validation
        validation = await automation_coordinator.run_post_rollback_validation(
            operation_id=operation_id,
            services=["api"],
        )

        assert validation.operation_id == operation_id
        assert validation.completed_at is not None

    @pytest.mark.asyncio
    async def test_template_library_integration(self, automation_coordinator):
        """Test template library with built-in templates."""
        templates = automation_coordinator.list_templates()
        assert len(templates) >= 3

        # Get full deployment template
        full_template = automation_coordinator.get_template_by_type(
            RollbackTemplateType.FULL_DEPLOYMENT
        )
        assert full_template is not None
        assert full_template.template_type == RollbackTemplateType.FULL_DEPLOYMENT

    @pytest.mark.asyncio
    async def test_impact_analysis_risk_scoring(self, automation_coordinator):
        """Test impact analysis with risk scoring."""
        # Low risk scenario
        low_analysis = await automation_coordinator.analyze_rollback_impact(
            target_state="v1.2.3",
            services=["api"],
            template_type=RollbackTemplateType.CONFIGURATION,
        )

        # High risk scenario
        high_analysis = await automation_coordinator.analyze_rollback_impact(
            target_state="v1.2.3",
            services=["api", "worker", "scheduler", "database", "cache"],
            template_type=RollbackTemplateType.FULL_DEPLOYMENT,
        )

        # High risk should require confirmation
        if high_analysis.risk_score.value in ("medium", "high"):
            assert high_analysis.confirmation_required is True


class TestRollbackAutomationAPIIntegration:
    """API integration tests for rollback automation."""

    @pytest.mark.asyncio
    async def test_api_automated_execute_endpoint(self):
        """Test the automated execute API endpoint."""
        from src.autonomous_control_plane.api.v1.rollback import (
            execute_automated_rollback,
            set_automation_coordinator,
        )
        from autonomous_control_plane.components.rollback_automation import (
            RollbackAutomationCoordinator,
        )

        base_coordinator = RollbackCoordinator()
        automation_coordinator = RollbackAutomationCoordinator(base_coordinator)
        set_automation_coordinator(automation_coordinator)

        result = await execute_automated_rollback(
            target_state="v1.2.3",
            skip_impact_analysis=True,
        )

        assert result["target_state"] == "v1.2.3"

    @pytest.mark.asyncio
    async def test_api_impact_analysis_endpoint(self):
        """Test the impact analysis API endpoint."""
        from src.autonomous_control_plane.api.v1.rollback import (
            analyze_rollback_impact,
            set_automation_coordinator,
        )
        from autonomous_control_plane.components.rollback_automation import (
            RollbackAutomationCoordinator,
        )

        base_coordinator = RollbackCoordinator()
        automation_coordinator = RollbackAutomationCoordinator(base_coordinator)
        set_automation_coordinator(automation_coordinator)

        result = await analyze_rollback_impact(
            target_state="v1.2.3",
            services=["api", "worker"],
        )

        assert "estimated_affected_users" in result
        assert "risk_score" in result

    @pytest.mark.asyncio
    async def test_api_templates_endpoint(self):
        """Test the templates API endpoint."""
        from src.autonomous_control_plane.api.v1.rollback import (
            list_rollback_templates,
            set_automation_coordinator,
        )
        from autonomous_control_plane.components.rollback_automation import (
            RollbackAutomationCoordinator,
        )

        base_coordinator = RollbackCoordinator()
        automation_coordinator = RollbackAutomationCoordinator(base_coordinator)
        set_automation_coordinator(automation_coordinator)

        result = await list_rollback_templates()

        assert len(result) >= 3
        assert any(t["template_type"] == "full_deployment" for t in result)

    @pytest.mark.asyncio
    async def test_api_triggers_endpoint(self):
        """Test the triggers API endpoint."""
        from src.autonomous_control_plane.api.v1.rollback import (
            create_default_triggers,
            list_rollback_triggers,
            set_automation_coordinator,
        )
        from autonomous_control_plane.components.rollback_automation import (
            RollbackAutomationCoordinator,
        )

        base_coordinator = RollbackCoordinator()
        automation_coordinator = RollbackAutomationCoordinator(base_coordinator)
        set_automation_coordinator(automation_coordinator)

        # Create default triggers
        await create_default_triggers(target_state="v1.2.3", sensitivity="medium")

        # List triggers
        result = await list_rollback_triggers()

        assert len(result) == 3
        assert all(t["enabled"] for t in result)

    @pytest.mark.asyncio
    async def test_api_coordinated_rollback_endpoint(self):
        """Test the coordinated rollback API endpoint."""
        from src.autonomous_control_plane.api.v1.rollback import (
            execute_coordinated_rollback,
            set_automation_coordinator,
        )
        from autonomous_control_plane.components.rollback_automation import (
            RollbackAutomationCoordinator,
        )

        base_coordinator = RollbackCoordinator()
        automation_coordinator = RollbackAutomationCoordinator(base_coordinator)
        set_automation_coordinator(automation_coordinator)

        result = await execute_coordinated_rollback(
            target_state="v1.2.3",
            services=["api", "worker"],
            parallel_groups=[["api", "worker"]],
        )

        assert "api" in result
        assert "worker" in result
        assert result["api"]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_api_validation_endpoint(self):
        """Test the post-rollback validation API endpoint."""
        from src.autonomous_control_plane.api.v1.rollback import (
            run_post_rollback_validation,
            set_automation_coordinator,
        )
        from autonomous_control_plane.components.rollback_automation import (
            RollbackAutomationCoordinator,
        )

        base_coordinator = RollbackCoordinator()
        automation_coordinator = RollbackAutomationCoordinator(base_coordinator)
        set_automation_coordinator(automation_coordinator)

        result = await run_post_rollback_validation(
            operation_id="test-op-id",
            services=["api"],
        )

        assert result["operation_id"] == "test-op-id"
        assert "validation_report" in result
