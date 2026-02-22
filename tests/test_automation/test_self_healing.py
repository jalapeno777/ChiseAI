"""Tests for self-healing automation system.

Tests for:
- RecoveryOrchestrator
- SelfHealingEngine
- EventHandlers

Target: 80%+ coverage
"""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.automation import (
    EventType,
    HealingAction,
    HealingStatus,
    HealthEvent,
    RecoveryAttempt,
    RecoveryContext,
    RecoveryOrchestrator,
    RecoveryResult,
    RecoveryState,
    RecoveryType,
    SelfHealingEngine,
    SelfHealingResult,
)
from src.automation.event_handlers import (
    EventRouter,
    OnHealthCritical,
    OnHealthWarning,
    OnRecoveryFailure,
    OnRecoverySuccess,
    create_health_event_from_datasource_alert,
    create_health_event_from_execution_alert,
)
from src.automation.recovery_orchestrator import HealthLevel
from src.automation.self_healing_engine import (
    DeploymentHealth,
    ExchangeFailover,
    RedisReconnector,
)

# ============================================================================
# Fixtures
# ============================================================================


# orchestrator fixture now in conftest.py


@pytest.fixture
def healing_engine():
    """Create a self-healing engine."""
    return SelfHealingEngine()


@pytest.fixture
def event_router(orchestrator, healing_engine):
    """Create an event router."""
    return EventRouter(orchestrator, healing_engine)


@pytest.fixture
def sample_recovery_context():
    """Create a sample recovery context."""
    return RecoveryContext(
        source="test_service",
        recovery_type=RecoveryType.REDIS_RECONNECT,
        trigger_event="health_critical",
        metadata={"test": True},
    )


@pytest.fixture
def sample_health_event():
    """Create a sample health event."""
    return HealthEvent(
        event_type=EventType.HEALTH_CRITICAL,
        source="test_service",
        severity=HealthLevel.CRITICAL,
        message="Test health event",
        metadata={"test": True},
    )


# ============================================================================
# RecoveryOrchestrator Tests
# ============================================================================


class TestRecoveryOrchestrator:
    """Tests for RecoveryOrchestrator."""

    @pytest.mark.asyncio
    async def test_initialization(self):
        """Test orchestrator initialization."""
        orch = RecoveryOrchestrator(max_attempts=5)

        assert orch.max_attempts == 5
        assert orch._recovery_actions == {}
        assert orch._active_recoveries == {}

    @pytest.mark.asyncio
    async def test_register_recovery_action(self, orchestrator):
        """Test registering a recovery action."""
        mock_action = AsyncMock(return_value={"success": True})

        orchestrator.register_recovery_action(
            RecoveryType.REDIS_RECONNECT,
            mock_action,
        )

        assert RecoveryType.REDIS_RECONNECT in orchestrator._recovery_actions

    @pytest.mark.asyncio
    async def test_trigger_recovery_success(
        self, orchestrator, sample_recovery_context
    ):
        """Test successful recovery trigger."""
        mock_action = AsyncMock(return_value={"success": True})
        orchestrator.register_recovery_action(
            RecoveryType.REDIS_RECONNECT,
            mock_action,
        )

        result = await orchestrator.trigger_recovery(
            sample_recovery_context,
            priority=HealthLevel.CRITICAL,
        )

        assert result.success is True
        assert result.attempt.state == RecoveryState.SUCCEEDED
        assert result.escalation_required is False
        mock_action.assert_called_once()

    @pytest.mark.asyncio
    async def test_trigger_recovery_failure(
        self, orchestrator, sample_recovery_context
    ):
        """Test failed recovery trigger."""
        mock_action = AsyncMock(side_effect=Exception("Test error"))
        orchestrator.register_recovery_action(
            RecoveryType.REDIS_RECONNECT,
            mock_action,
        )

        result = await orchestrator.trigger_recovery(
            sample_recovery_context,
            priority=HealthLevel.CRITICAL,
        )

        assert result.success is False
        assert result.attempt.state == RecoveryState.FAILED
        assert result.attempt.error_message == "Test error"

    @pytest.mark.asyncio
    async def test_max_attempts_limit(self, orchestrator, sample_recovery_context):
        """Test max attempts enforcement."""
        orchestrator.max_attempts = 2

        mock_action = AsyncMock(return_value={"success": True})
        orchestrator.register_recovery_action(
            RecoveryType.REDIS_RECONNECT,
            mock_action,
        )

        # First two attempts
        await orchestrator.trigger_recovery(sample_recovery_context)
        await orchestrator.trigger_recovery(sample_recovery_context)

        # Third attempt should be blocked
        result = await orchestrator.trigger_recovery(sample_recovery_context)

        assert result.success is False
        assert result.attempt.state == RecoveryState.MAX_ATTEMPTS_REACHED
        assert result.escalation_required is True

    @pytest.mark.asyncio
    async def test_recovery_timeout(self, orchestrator, sample_recovery_context):
        """Test recovery timeout."""
        orchestrator.recovery_timeout_seconds = 0.1

        async def slow_action(ctx):
            await asyncio.sleep(1.0)
            return {"success": True}

        orchestrator.register_recovery_action(
            RecoveryType.REDIS_RECONNECT,
            slow_action,
        )

        result = await orchestrator.trigger_recovery(sample_recovery_context)

        assert result.success is False
        assert result.attempt.state == RecoveryState.FAILED
        assert "timed out" in result.attempt.error_message.lower()

    @pytest.mark.asyncio
    async def test_success_handler_called(self, orchestrator, sample_recovery_context):
        """Test success handler is called."""
        mock_handler = AsyncMock()
        orchestrator.add_success_handler(mock_handler)

        mock_action = AsyncMock(return_value={"success": True})
        orchestrator.register_recovery_action(
            RecoveryType.REDIS_RECONNECT,
            mock_action,
        )

        await orchestrator.trigger_recovery(sample_recovery_context)

        mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_recovery_stats(self, orchestrator, sample_recovery_context):
        """Test getting recovery statistics."""
        mock_action = AsyncMock(return_value={"success": True})
        orchestrator.register_recovery_action(
            RecoveryType.REDIS_RECONNECT,
            mock_action,
        )

        await orchestrator.trigger_recovery(sample_recovery_context)

        stats = orchestrator.get_recovery_stats()

        assert stats["total_attempts"] == 1
        assert stats["successful"] == 1
        assert stats["failed"] == 0
        assert stats["success_rate"] == 1.0

    @pytest.mark.asyncio
    async def test_clear_history(self, orchestrator, sample_recovery_context):
        """Test clearing recovery history."""
        mock_action = AsyncMock(return_value={"success": True})
        orchestrator.register_recovery_action(
            RecoveryType.REDIS_RECONNECT,
            mock_action,
        )

        await orchestrator.trigger_recovery(sample_recovery_context)

        assert len(orchestrator._recovery_history) > 0

        orchestrator.clear_history()

        assert len(orchestrator._recovery_history) == 0


# ============================================================================
# SelfHealingEngine Tests
# ============================================================================


class TestSelfHealingEngine:
    """Tests for SelfHealingEngine."""

    @pytest.mark.asyncio
    async def test_initialization(self):
        """Test engine initialization."""
        engine = SelfHealingEngine()

        assert engine._healing_history == []
        assert engine._max_history == 1000

    @pytest.mark.asyncio
    async def test_heal_redis_success(self, healing_engine):
        """Test Redis healing."""
        # Mock the reconnector
        with patch.object(
            healing_engine._redis_reconnector,
            "reconnect",
            new_callable=AsyncMock,
            return_value=SelfHealingResult(
                action=HealingAction.REDIS_RECONNECT,
                status=HealingStatus.SUCCEEDED,
                source="redis",
                details={"attempts": 1},
            ),
        ):
            result = await healing_engine.heal_redis()

            assert result.action == HealingAction.REDIS_RECONNECT
            assert result.status == HealingStatus.SUCCEEDED

    @pytest.mark.asyncio
    async def test_heal_service_restart(self, healing_engine):
        """Test service restart healing."""
        with patch.object(
            healing_engine._service_restarter,
            "restart",
            new_callable=AsyncMock,
            return_value=SelfHealingResult(
                action=HealingAction.SERVICE_RESTART,
                status=HealingStatus.SUCCEEDED,
                source="test-service",
                details={"method": "docker-compose"},
            ),
        ):
            result = await healing_engine.heal_service_restart("test-service")

            assert result.action == HealingAction.SERVICE_RESTART
            assert result.source == "test-service"

    @pytest.mark.asyncio
    async def test_heal_exchange_failover(self, healing_engine):
        """Test exchange failover healing."""
        with patch.object(
            healing_engine._exchange_failover,
            "failover",
            new_callable=AsyncMock,
            return_value=SelfHealingResult(
                action=HealingAction.EXCHANGE_FAILOVER,
                status=HealingStatus.SUCCEEDED,
                source="bybit",
                details={"to_exchange": "bitget"},
            ),
        ):
            result = await healing_engine.heal_exchange_failover("bybit")

            assert result.action == HealingAction.EXCHANGE_FAILOVER
            assert result.source == "bybit"

    @pytest.mark.asyncio
    async def test_get_healing_stats(self, healing_engine):
        """Test getting healing statistics."""
        # Add some healing results
        healing_engine._healing_history = [
            SelfHealingResult(
                action=HealingAction.REDIS_RECONNECT,
                status=HealingStatus.SUCCEEDED,
                source="redis",
            ),
            SelfHealingResult(
                action=HealingAction.SERVICE_RESTART,
                status=HealingStatus.FAILED,
                source="api",
            ),
        ]

        stats = healing_engine.get_healing_stats()

        assert stats["total_healing_actions"] == 2

    @pytest.mark.asyncio
    async def test_deployment_registration(self, healing_engine):
        """Test deployment registration."""
        deployment = healing_engine.register_deployment(
            "deploy-123",
            "v1.2.3",
        )

        assert deployment.deployment_id == "deploy-123"
        assert deployment.version == "v1.2.3"
        assert deployment.current_health_score == 100.0

    @pytest.mark.asyncio
    async def test_deployment_health_tracking(self, healing_engine):
        """Test deployment health tracking."""
        deployment = healing_engine.register_deployment("deploy-123", "v1.2.3")

        healing_engine.record_deployment_health("deploy-123", 80.0)
        healing_engine.record_deployment_health("deploy-123", 60.0)
        healing_engine.record_deployment_health("deploy-123", 40.0)

        assert deployment.current_health_score == 40.0
        assert deployment.is_healthy is False

    @pytest.mark.asyncio
    async def test_deployment_rollback_needed(self, healing_engine):
        """Test rollback detection."""
        deployment = healing_engine.register_deployment("deploy-123", "v1.2.3")

        # Simulate being unhealthy for 5+ minutes
        old_time = datetime.now(UTC) - timedelta(minutes=6)
        deployment.deployed_at = old_time
        deployment.last_healthy_at = old_time
        healing_engine.record_deployment_health("deploy-123", 30.0)

        assert deployment.needs_rollback is True
        assert healing_engine.check_deployment_rollback_needed("deploy-123") is True


# ============================================================================
# EventHandler Tests
# ============================================================================


class TestEventHandlers:
    """Tests for event handlers."""

    @pytest.mark.asyncio
    async def test_on_health_critical(
        self, orchestrator, healing_engine, sample_health_event
    ):
        """Test critical health handler."""
        handler = OnHealthCritical(orchestrator, healing_engine)

        # Mock the orchestrator
        with patch.object(
            orchestrator,
            "trigger_recovery",
            new_callable=AsyncMock,
            return_value=RecoveryResult(
                success=True,
                attempt=RecoveryAttempt(
                    attempt_id="test-123",
                    context=RecoveryContext(
                        source="test",
                        recovery_type=RecoveryType.REDIS_RECONNECT,
                        trigger_event="test",
                    ),
                    state=RecoveryState.SUCCEEDED,
                ),
            ),
        ):
            result = await handler.handle(sample_health_event)

            assert result.success is True

    @pytest.mark.asyncio
    async def test_on_health_warning_immediate(self, orchestrator, healing_engine):
        """Test warning handler with immediate recovery."""
        handler = OnHealthWarning(orchestrator, healing_engine)

        event = HealthEvent(
            event_type=EventType.HEALTH_WARNING,
            source="test_service",
            severity=HealthLevel.WARNING,
            message="Warning event",
            metadata={"health_score": 30},  # Low score triggers immediate
        )

        with patch.object(
            orchestrator,
            "trigger_recovery",
            new_callable=AsyncMock,
            return_value=RecoveryResult(
                success=True,
                attempt=MagicMock(),
            ),
        ):
            result = await handler.handle(event)

            assert result is not None

    @pytest.mark.asyncio
    async def test_on_recovery_success(self, orchestrator, healing_engine):
        """Test recovery success handler."""
        mock_restorer = AsyncMock()
        handler = OnRecoverySuccess(
            orchestrator,
            healing_engine,
            health_score_restorer=mock_restorer,
        )

        event = HealthEvent(
            event_type=EventType.RECOVERY_SUCCESS,
            source="test_service",
            severity=HealthLevel.INFO,
            message="Recovery succeeded",
            metadata={"health_score": 85.0},
        )

        result = await handler.handle(event)

        assert result is not None
        mock_restorer.assert_called_once_with("test_service", 85.0)

    @pytest.mark.asyncio
    async def test_on_recovery_failure(self, orchestrator, healing_engine):
        """Test recovery failure handler."""
        mock_escalation = AsyncMock()
        handler = OnRecoveryFailure(orchestrator, healing_engine)
        handler.add_escalation_handler(mock_escalation)

        event = HealthEvent(
            event_type=EventType.RECOVERY_FAILURE,
            source="test_service",
            severity=HealthLevel.CRITICAL,
            message="Recovery failed",
            metadata={"attempt_count": 3},
        )

        await handler.handle(event)

        mock_escalation.assert_called_once()

    @pytest.mark.asyncio
    async def test_event_router_route(self, orchestrator, healing_engine):
        """Test event router."""
        router = EventRouter(orchestrator, healing_engine)

        event = HealthEvent(
            event_type=EventType.HEALTH_CRITICAL,
            source="test",
            severity=HealthLevel.CRITICAL,
            message="Critical",
        )

        with patch.object(
            router._critical_handler,
            "handle",
            new_callable=AsyncMock,
            return_value=RecoveryResult(success=True, attempt=MagicMock()),
        ):
            result = await router.route(event)

            assert result.success is True

    @pytest.mark.asyncio
    async def test_event_router_from_monitoring_alert(
        self, orchestrator, healing_engine
    ):
        """Test routing from monitoring alert."""
        router = EventRouter(orchestrator, healing_engine)

        with patch.object(
            router,
            "route",
            new_callable=AsyncMock,
            return_value=RecoveryResult(success=True, attempt=MagicMock()),
        ) as mock_route:
            result = await router.route_from_monitoring_alert(
                source="redis",
                severity="critical",
                message="Redis disconnected",
            )

            assert result.success is True
            mock_route.assert_called_once()


# ============================================================================
# Helper Function Tests
# ============================================================================


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_create_health_event_from_datasource_alert_critical(self):
        """Test creating health event from critical datasource alert."""
        from src.monitoring.datasource_health import (
            AlertSeverity,
            DatasourceHealthAlert,
            DataSourceType,
        )

        alert = DatasourceHealthAlert(
            alert_type="disconnected",
            source_type=DataSourceType.INFLUXDB,
            source_name="test-db",
            message="Database disconnected",
            severity=AlertSeverity.CRITICAL,
        )

        event = create_health_event_from_datasource_alert(alert)

        assert event.event_type == EventType.HEALTH_CRITICAL
        assert event.severity == HealthLevel.CRITICAL
        assert "disconnected" in event.message.lower()

    def test_create_health_event_from_execution_alert(self):
        """Test creating health event from execution alert."""
        from src.execution.health_monitor import AlertSeverity, DataGapAlert

        alert = DataGapAlert(
            source="bybit",
            symbol="BTCUSDT",
            gap_start=1234567890.0,
            gap_end=1234567950.0,
            duration_seconds=65.0,  # > 60s triggers CRITICAL
            severity=AlertSeverity.CRITICAL,
        )

        event = create_health_event_from_execution_alert(alert)

        assert event.event_type == EventType.DATA_GAP_DETECTED
        assert event.severity == HealthLevel.CRITICAL
        assert "bybit" in event.source.lower()


# ============================================================================
# Component Tests
# ============================================================================


class TestRedisReconnector:
    """Tests for RedisReconnector."""

    @pytest.mark.asyncio
    async def test_reconnect_success(self):
        """Test successful Redis reconnection."""
        reconnector = RedisReconnector()

        with patch("asyncio.wait_for", new_callable=AsyncMock):
            result = await reconnector.reconnect()

            assert result.action == HealingAction.REDIS_RECONNECT
            assert result.status in [HealingStatus.SUCCEEDED, HealingStatus.FAILED]


class TestExchangeFailover:
    """Tests for ExchangeFailover."""

    @pytest.mark.asyncio
    async def test_failover_success(self):
        """Test successful exchange failover."""
        mock_connector = AsyncMock()
        mock_connector.health_check = AsyncMock(return_value={"healthy": True})

        failover = ExchangeFailover(
            current_exchange="bybit",
            exchange_connectors={"bitget": mock_connector},
        )

        result = await failover.failover("bybit")

        assert result.action == HealingAction.EXCHANGE_FAILOVER
        mock_connector.health_check.assert_called_once()

    @pytest.mark.asyncio
    async def test_failover_no_backups(self):
        """Test failover with no available backups."""
        failover = ExchangeFailover(
            current_exchange="bybit",
            exchange_connectors={},
        )

        result = await failover.failover("bybit")

        assert result.action == HealingAction.EXCHANGE_FAILOVER
        assert result.status == HealingStatus.FAILED


class TestDeploymentHealth:
    """Tests for DeploymentHealth."""

    def test_current_health_score(self):
        """Test getting current health score."""
        deployment = DeploymentHealth(
            deployment_id="test-123",
            version="v1.0",
            deployed_at=datetime.now(UTC),
            health_scores=[
                (datetime.now(UTC), 80.0),
                (datetime.now(UTC), 70.0),
                (datetime.now(UTC), 60.0),
            ],
        )

        assert deployment.current_health_score == 60.0

    def test_needs_rollback_true(self):
        """Test rollback detection when needed."""
        old_time = datetime.now(UTC) - timedelta(minutes=6)

        deployment = DeploymentHealth(
            deployment_id="test-123",
            version="v1.0",
            deployed_at=old_time,
            last_healthy_at=old_time,
            health_scores=[(datetime.now(UTC), 30.0)],
        )

        assert deployment.needs_rollback is True

    def test_needs_rollback_false_healthy(self):
        """Test rollback detection when healthy."""
        deployment = DeploymentHealth(
            deployment_id="test-123",
            version="v1.0",
            deployed_at=datetime.now(UTC),
            health_scores=[(datetime.now(UTC), 80.0)],
        )

        assert deployment.needs_rollback is False


# ============================================================================
# Integration Tests
# ============================================================================


class TestIntegration:
    """Integration tests for the self-healing system."""

    @pytest.mark.asyncio
    async def test_full_recovery_flow(self):
        """Test full recovery flow from event to healing."""
        orchestrator = RecoveryOrchestrator(max_attempts=3)
        healing_engine = SelfHealingEngine()
        router = EventRouter(orchestrator, healing_engine)

        # Register a mock recovery action
        async def mock_recovery(ctx):
            return {"success": True, "source": ctx.source}

        orchestrator.register_recovery_action(
            RecoveryType.REDIS_RECONNECT,
            mock_recovery,
        )

        # Create and route a critical event
        event = HealthEvent(
            event_type=EventType.HEALTH_CRITICAL,
            source="redis_test",
            severity=HealthLevel.CRITICAL,
            message="Redis connection lost",
        )

        result = await router.route(event)

        assert result.success is True
        assert result.attempt.state == RecoveryState.SUCCEEDED

    @pytest.mark.asyncio
    async def test_cascading_failure_prevention(self):
        """Test that cascading failures are prevented."""
        orchestrator = RecoveryOrchestrator(max_attempts=2)
        SelfHealingEngine()

        # Register a failing recovery action
        async def failing_recovery(ctx):
            raise Exception("Recovery failed")

        orchestrator.register_recovery_action(
            RecoveryType.REDIS_RECONNECT,
            failing_recovery,
        )

        # Trigger multiple recoveries
        context = RecoveryContext(
            source="test",
            recovery_type=RecoveryType.REDIS_RECONNECT,
            trigger_event="test",
        )

        # First two attempts should fail but not escalate
        result1 = await orchestrator.trigger_recovery(context)
        result2 = await orchestrator.trigger_recovery(context)

        assert result1.success is False
        assert result2.success is False

        # Third attempt should trigger escalation (max attempts reached)
        result3 = await orchestrator.trigger_recovery(context)

        assert result3.escalation_required is True

    @pytest.mark.asyncio
    async def test_concurrent_recovery_prevention(self):
        """Test that concurrent recoveries for same source are prevented."""
        orchestrator = RecoveryOrchestrator()

        recovery_started = asyncio.Event()

        async def slow_recovery(ctx):
            recovery_started.set()
            await asyncio.sleep(0.2)
            return {"success": True}

        orchestrator.register_recovery_action(
            RecoveryType.REDIS_RECONNECT,
            slow_recovery,
        )

        context = RecoveryContext(
            source="concurrent_test",
            recovery_type=RecoveryType.REDIS_RECONNECT,
            trigger_event="test",
        )

        # Start first recovery
        task1 = asyncio.create_task(orchestrator.trigger_recovery(context))

        # Wait for first recovery to actually start
        await asyncio.wait_for(recovery_started.wait(), timeout=1.0)

        # Immediately try second recovery (should be blocked)
        result2 = await orchestrator.trigger_recovery(context)

        # Wait for first to complete
        result1 = await task1

        assert result1.success is True
        assert result2.success is False  # Blocked
        assert result2.next_action == "wait"
