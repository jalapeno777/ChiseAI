"""Unit tests for Rollback Automation Coordinator.

Tests for ST-SAFETY-003: Rollback Automation

Acceptance Criteria:
1. Automated rollback triggers (circuit breaker, retry budget, error rate, health check)
2. Rollback templates with built-in and custom support
3. Rollback impact analysis with risk scoring
4. Coordinated multi-service rollback with dependency ordering
5. Post-rollback automated validation suite
6. Integration with circuit breaker groups from ST-SAFETY-001
7. Integration with retry budget pools from ST-SAFETY-002
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autonomous_control_plane.components.rollback_automation import (
    CoordinatedRollbackExecutor,
    PostRollbackValidator,
    RollbackAutomationCoordinator,
    RollbackImpactAnalyzer,
    RollbackTemplateLibrary,
    RollbackTriggerManager,
)
from autonomous_control_plane.models.rollback import (
    CoordinatedRollbackConfig,
    PostRollbackValidationResult,
    RollbackCheckpoint,
    RollbackImpactAnalysis,
    RollbackOperation,
    RollbackRiskLevel,
    RollbackStatus,
    RollbackTemplate,
    RollbackTemplateStep,
    RollbackTemplateType,
    RollbackTrigger,
    RollbackTriggerType,
)


class TestRollbackTemplateLibrary:
    """Tests for RollbackTemplateLibrary."""

    def test_builtin_templates_registered(self):
        """AC2: Built-in templates are registered on initialization."""
        library = RollbackTemplateLibrary()
        templates = library.list_templates()

        assert len(templates) >= 3

        # Check for expected built-in types
        template_types = [t.template_type for t in templates]
        assert RollbackTemplateType.FULL_DEPLOYMENT in template_types
        assert RollbackTemplateType.PARTIAL_SERVICE in template_types
        assert RollbackTemplateType.CONFIGURATION in template_types

    def test_get_template_by_id(self):
        """AC2: Can retrieve template by ID."""
        library = RollbackTemplateLibrary()
        templates = library.list_templates()

        template = library.get_template(templates[0].template_id)
        assert template is not None
        assert template.template_id == templates[0].template_id

    def test_get_template_by_type(self):
        """AC2: Can retrieve template by type."""
        library = RollbackTemplateLibrary()

        template = library.get_template_by_type(RollbackTemplateType.FULL_DEPLOYMENT)
        assert template is not None
        assert template.template_type == RollbackTemplateType.FULL_DEPLOYMENT

    def test_add_custom_template(self):
        """AC2: Can add custom templates."""
        library = RollbackTemplateLibrary()

        custom_template = RollbackTemplate(
            template_type=RollbackTemplateType.CUSTOM,
            name="Custom Template",
            description="A custom rollback template",
        )
        custom_template.add_step(
            RollbackTemplateStep(
                name="custom_step",
                description="A custom step",
                action="custom_action",
            )
        )

        library.add_template(custom_template)

        retrieved = library.get_template(custom_template.template_id)
        assert retrieved is not None
        assert retrieved.name == "Custom Template"

    def test_template_validation(self):
        """AC2: Template validation catches invalid templates."""
        library = RollbackTemplateLibrary()

        # Template with no steps is invalid
        invalid_template = RollbackTemplate(
            template_type=RollbackTemplateType.CUSTOM,
            name="Invalid Template",
        )

        with pytest.raises(ValueError) as exc_info:
            library.add_template(invalid_template)

        assert "at least one step" in str(exc_info.value)

    def test_template_usage_tracking(self):
        """AC2: Template usage is tracked."""
        library = RollbackTemplateLibrary()
        template = library.get_template_by_type(RollbackTemplateType.FULL_DEPLOYMENT)

        initial_count = template.usage_count
        template.mark_used()
        assert template.usage_count == initial_count + 1


class TestRollbackTriggerManager:
    """Tests for RollbackTriggerManager."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create mock rollback coordinator."""
        return AsyncMock()

    @pytest.fixture
    def trigger_manager(self, mock_coordinator):
        """Create trigger manager with mock coordinator."""
        return RollbackTriggerManager(mock_coordinator)

    def test_register_trigger(self, trigger_manager):
        """AC1: Can register triggers."""
        trigger = RollbackTrigger(
            trigger_type=RollbackTriggerType.CIRCUIT_BREAKER_GROUP,
            name="Test Trigger",
            target_state="v1.2.3",
            template_id="template-123",
        )

        trigger_manager.register_trigger(trigger)

        retrieved = trigger_manager.get_trigger(trigger.trigger_id)
        assert retrieved is not None
        assert retrieved.name == "Test Trigger"

    def test_unregister_trigger(self, trigger_manager):
        """AC1: Can unregister triggers."""
        trigger = RollbackTrigger(
            trigger_type=RollbackTriggerType.ERROR_RATE_THRESHOLD,
            name="Test Trigger",
            target_state="v1.2.3",
            template_id="template-123",
        )

        trigger_manager.register_trigger(trigger)
        result = trigger_manager.unregister_trigger(trigger.trigger_id)

        assert result is True
        assert trigger_manager.get_trigger(trigger.trigger_id) is None

    def test_list_triggers(self, trigger_manager):
        """AC1: Can list all triggers."""
        trigger1 = RollbackTrigger(
            trigger_type=RollbackTriggerType.CIRCUIT_BREAKER_GROUP,
            name="Trigger 1",
            target_state="v1.2.3",
            template_id="template-123",
            enabled=True,
        )
        trigger2 = RollbackTrigger(
            trigger_type=RollbackTriggerType.ERROR_RATE_THRESHOLD,
            name="Trigger 2",
            target_state="v1.2.3",
            template_id="template-123",
            enabled=False,
        )

        trigger_manager.register_trigger(trigger1)
        trigger_manager.register_trigger(trigger2)

        all_triggers = trigger_manager.list_triggers()
        assert len(all_triggers) == 2

        enabled_triggers = trigger_manager.list_triggers(enabled_only=True)
        assert len(enabled_triggers) == 1

    def test_create_default_triggers(self, trigger_manager):
        """AC1: Can create default triggers with standard configurations."""
        triggers = trigger_manager.create_default_triggers(
            target_state="v1.2.3",
            template_id="template-123",
            sensitivity="medium",
        )

        assert len(triggers) == 3

        # Check trigger types
        trigger_types = [t.trigger_type for t in triggers]
        assert RollbackTriggerType.CIRCUIT_BREAKER_GROUP in trigger_types
        assert RollbackTriggerType.ERROR_RATE_THRESHOLD in trigger_types
        assert RollbackTriggerType.HEALTH_CHECK_CASCADE in trigger_types

    def test_sensitivity_configurations(self, trigger_manager):
        """AC1: Different sensitivity levels have different thresholds."""
        low_triggers = trigger_manager.create_default_triggers(
            target_state="v1.2.3",
            template_id="template-123",
            sensitivity="low",
        )
        high_triggers = trigger_manager.create_default_triggers(
            target_state="v1.2.3",
            template_id="template-123",
            sensitivity="high",
        )

        # High sensitivity should have lower thresholds
        low_cb = next(
            t
            for t in low_triggers
            if t.trigger_type == RollbackTriggerType.CIRCUIT_BREAKER_GROUP
        )
        high_cb = next(
            t
            for t in high_triggers
            if t.trigger_type == RollbackTriggerType.CIRCUIT_BREAKER_GROUP
        )

        assert low_cb.conditions["threshold"] > high_cb.conditions["threshold"]

    @pytest.mark.asyncio
    async def test_trigger_fired_callback(self, trigger_manager, mock_coordinator):
        """AC1: Trigger firing calls registered callbacks."""
        callback_mock = MagicMock()
        trigger_manager.on_trigger_fired(callback_mock)

        trigger = RollbackTrigger(
            trigger_type=RollbackTriggerType.MANUAL,
            name="Manual Trigger",
            target_state="v1.2.3",
            template_id="template-123",
            require_confirmation=False,
        )
        trigger_manager.register_trigger(trigger)

        # Mock the coordinator to return an operation
        mock_operation = RollbackOperation(target_state="v1.2.3")
        mock_coordinator.execute_rollback.return_value = mock_operation

        # Fire the trigger
        await trigger_manager._fire_trigger(trigger)

        # Verify callback was called
        callback_mock.assert_called_once()
        assert callback_mock.call_args[0][0] == trigger


class TestRollbackImpactAnalyzer:
    """Tests for RollbackImpactAnalyzer."""

    @pytest.fixture
    def analyzer(self):
        """Create impact analyzer."""
        return RollbackImpactAnalyzer()

    @pytest.mark.asyncio
    async def test_analyze_impact_returns_analysis(self, analyzer):
        """AC3: Impact analysis returns structured results."""
        analysis = await analyzer.analyze_impact(
            target_state="v1.2.3",
            services=["api", "worker"],
        )

        assert isinstance(analysis, RollbackImpactAnalysis)
        assert analysis.estimated_affected_users >= 0
        assert analysis.estimated_affected_requests >= 0
        assert analysis.estimated_downtime_seconds >= 0

    @pytest.mark.asyncio
    async def test_risk_score_calculation(self, analyzer):
        """AC3: Risk score is calculated based on impact factors."""
        # Low impact scenario
        low_impact = RollbackImpactAnalysis(
            estimated_affected_users=50,
            estimated_affected_requests=500,
            estimated_downtime_seconds=10,
            affected_services=["api"],
            affected_dependencies=["database"],
        )
        score, factors = analyzer._calculate_risk_score(low_impact)
        assert score == RollbackRiskLevel.LOW

        # High impact scenario
        high_impact = RollbackImpactAnalysis(
            estimated_affected_users=5000,
            estimated_affected_requests=50000,
            estimated_downtime_seconds=300,
            affected_services=["api", "worker", "scheduler"],
            affected_dependencies=["database", "cache", "queue", "auth"],
        )
        score, factors = analyzer._calculate_risk_score(high_impact)
        assert score == RollbackRiskLevel.HIGH

    @pytest.mark.asyncio
    async def test_confirmation_required_for_high_risk(self, analyzer):
        """AC3: High risk rollbacks require confirmation."""
        analysis = await analyzer.analyze_impact(
            target_state="v1.2.3",
            services=["api", "worker", "scheduler"] * 10,  # Many services = high impact
        )

        if analysis.risk_score in (RollbackRiskLevel.MEDIUM, RollbackRiskLevel.HIGH):
            assert analysis.confirmation_required is True

    @pytest.mark.asyncio
    async def test_downtime_estimation_by_template(self, analyzer):
        """AC3: Downtime estimated based on template type."""
        config_downtime = analyzer._estimate_downtime(
            service_count=3,
            template_type=RollbackTemplateType.CONFIGURATION,
        )
        full_downtime = analyzer._estimate_downtime(
            service_count=3,
            template_type=RollbackTemplateType.FULL_DEPLOYMENT,
        )

        # Configuration rollback should be faster
        assert config_downtime < full_downtime


class TestCoordinatedRollbackExecutor:
    """Tests for CoordinatedRollbackExecutor."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create mock rollback coordinator."""
        coordinator = AsyncMock()
        operation = RollbackOperation(target_state="v1.2.3")
        operation.mark_completed()
        coordinator.execute_rollback.return_value = operation
        return coordinator

    @pytest.fixture
    def executor(self, mock_coordinator):
        """Create coordinated executor."""
        return CoordinatedRollbackExecutor(mock_coordinator)

    @pytest.mark.asyncio
    async def test_execute_coordinated_rollback(self, executor, mock_coordinator):
        """AC4: Can execute coordinated rollback across multiple services."""
        config = CoordinatedRollbackConfig(
            service_order=["api", "worker", "scheduler"],
        )

        results = await executor.execute_coordinated_rollback(
            config=config,
            target_state="v1.2.3",
        )

        assert len(results) == 3
        assert "api" in results
        assert "worker" in results
        assert "scheduler" in results

    @pytest.mark.asyncio
    async def test_parallel_execution(self, executor, mock_coordinator):
        """AC4: Services in parallel groups execute concurrently."""
        config = CoordinatedRollbackConfig(
            service_order=["api", "worker", "db"],
            parallel_groups=[["api", "worker"], ["db"]],
        )

        results = await executor.execute_coordinated_rollback(
            config=config,
            target_state="v1.2.3",
        )

        assert len(results) == 3

    def test_dependency_ordering(self, executor):
        """AC4: Services ordered by dependencies for rollback."""
        services = ["api", "worker", "database"]
        dependencies = {
            "api": ["database"],
            "worker": ["database"],
        }

        ordered = executor._order_by_dependencies(services, dependencies)

        # Database should come first (it's a dependency of others)
        assert ordered[0] == "database"


class TestPostRollbackValidator:
    """Tests for PostRollbackValidator."""

    @pytest.fixture
    def validator(self):
        """Create post-rollback validator."""
        return PostRollbackValidator()

    @pytest.mark.asyncio
    async def test_run_validation_returns_result(self, validator):
        """AC5: Validation returns structured result."""
        result = await validator.run_validation(
            operation_id="op-123",
            services=["api", "worker"],
        )

        assert isinstance(result, PostRollbackValidationResult)
        assert result.operation_id == "op-123"
        assert result.completed_at is not None

    @pytest.mark.asyncio
    async def test_validation_report_structure(self, validator):
        """AC5: Validation report contains all check types."""
        result = await validator.run_validation(
            operation_id="op-123",
            services=["api"],
        )

        report = result.validation_report
        assert "checks" in report
        assert "health_checks" in report["checks"]
        assert "smoke_tests" in report["checks"]
        assert "circuit_breakers" in report["checks"]
        assert "retry_budgets" in report["checks"]

    def test_all_passed_check(self):
        """AC5: all_passed() returns True only when all checks pass."""
        result = PostRollbackValidationResult(operation_id="op-123")

        # Initially all False
        assert result.all_passed() is False

        # Set all to True
        result.health_checks_passed = True
        result.smoke_tests_passed = True
        result.circuit_breaker_states_verified = True
        result.retry_budgets_reset = True

        assert result.all_passed() is True


class TestRollbackAutomationCoordinator:
    """Integration tests for RollbackAutomationCoordinator."""

    @pytest.fixture
    def mock_base_coordinator(self):
        """Create mock base coordinator."""
        coordinator = AsyncMock()
        operation = RollbackOperation(target_state="v1.2.3")
        operation.mark_completed()
        coordinator.execute_rollback.return_value = operation
        return coordinator

    @pytest.fixture
    def automation_coordinator(self, mock_base_coordinator):
        """Create automation coordinator."""
        return RollbackAutomationCoordinator(mock_base_coordinator)

    def test_initialization(self, automation_coordinator):
        """Coordinator initializes all sub-components."""
        assert automation_coordinator._template_library is not None
        assert automation_coordinator._trigger_manager is not None
        assert automation_coordinator._impact_analyzer is not None
        assert automation_coordinator._coordinated_executor is not None
        assert automation_coordinator._post_rollback_validator is not None

    @pytest.mark.asyncio
    async def test_execute_rollback_with_automation(self, automation_coordinator):
        """Full automation pipeline executes correctly."""
        result = await automation_coordinator.execute_rollback_with_automation(
            target_state="v1.2.3",
            template_type=RollbackTemplateType.FULL_DEPLOYMENT,
            skip_impact_analysis=True,  # Skip to avoid confirmation requirement
        )

        assert "target_state" in result
        assert "completed_at" in result

    @pytest.mark.asyncio
    async def test_awaiting_confirmation_for_high_risk(self, automation_coordinator):
        """High risk rollbacks return awaiting_confirmation status."""
        # Mock impact analysis to return high risk
        with patch.object(
            automation_coordinator._impact_analyzer,
            "analyze_impact",
            return_value=RollbackImpactAnalysis(
                estimated_affected_users=5000,
                estimated_affected_requests=50000,
                estimated_downtime_seconds=300,
                affected_services=["api"] * 10,
                affected_dependencies=["db"] * 5,
                risk_score=RollbackRiskLevel.HIGH,
                confirmation_required=True,
            ),
        ):
            result = await automation_coordinator.execute_rollback_with_automation(
                target_state="v1.2.3",
            )

        assert result["status"] == "awaiting_confirmation"

    @pytest.mark.asyncio
    async def test_force_bypasses_confirmation(self, automation_coordinator):
        """Force flag bypasses confirmation requirement."""
        # Mock impact analysis to return high risk
        with patch.object(
            automation_coordinator._impact_analyzer,
            "analyze_impact",
            return_value=RollbackImpactAnalysis(
                estimated_affected_users=5000,
                risk_score=RollbackRiskLevel.HIGH,
                confirmation_required=True,
            ),
        ):
            result = await automation_coordinator.execute_rollback_with_automation(
                target_state="v1.2.3",
                force=True,
            )

        # Should proceed with rollback, not await confirmation
        assert result.get("status") != "awaiting_confirmation"


class TestCircuitBreakerIntegration:
    """Tests for integration with circuit breaker groups (ST-SAFETY-001)."""

    @pytest.mark.asyncio
    async def test_circuit_breaker_trigger_evaluation(self):
        """AC6: Circuit breaker group failures trigger rollback."""
        mock_cb_registry = MagicMock()
        mock_cb_registry.list_groups.return_value = ["critical-services"]

        # Mock group metrics showing multiple open breakers
        mock_metrics = MagicMock()
        mock_metrics.open_count = 5  # 5 breakers open
        mock_cb_registry.get_group_metrics.return_value = mock_metrics

        mock_coordinator = AsyncMock()
        trigger_manager = RollbackTriggerManager(
            mock_coordinator,
            circuit_breaker_registry=mock_cb_registry,
        )

        trigger = RollbackTrigger(
            trigger_type=RollbackTriggerType.CIRCUIT_BREAKER_GROUP,
            name="CB Group Trigger",
            conditions={"threshold": 3, "groups": ["critical-services"]},
            target_state="v1.2.3",
            template_id="template-123",
        )

        should_trigger = await trigger_manager._evaluate_circuit_breaker_trigger(
            trigger
        )
        assert should_trigger is True


class TestRetryBudgetIntegration:
    """Tests for integration with retry budget pools (ST-SAFETY-002)."""

    @pytest.mark.asyncio
    async def test_retry_budget_trigger_evaluation(self):
        """AC7: Retry budget pool exhaustion triggers rollback."""
        mock_budget_manager = MagicMock()
        mock_budget_manager.get_pool_status.return_value = {
            "total_budget": 1000,
            "used_budget": 1000,  # Fully exhausted
        }

        mock_coordinator = AsyncMock()
        trigger_manager = RollbackTriggerManager(
            mock_coordinator,
            retry_budget_manager=mock_budget_manager,
        )

        trigger = RollbackTrigger(
            trigger_type=RollbackTriggerType.RETRY_BUDGET_POOL,
            name="Budget Pool Trigger",
            conditions={"pool_ids": ["critical-pool"]},
            target_state="v1.2.3",
            template_id="template-123",
        )

        should_trigger = await trigger_manager._evaluate_retry_budget_trigger(trigger)
        assert should_trigger is True
