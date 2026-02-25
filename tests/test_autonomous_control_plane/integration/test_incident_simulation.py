"""Integration tests for ACP End-to-End Incident Simulation.

Tests for EP-NS-008 Batch 2: Incident Simulation

Acceptance Criteria:
- At least 3 incident scenarios executed
- Detection time <5 seconds for all scenarios
- Self-healing triggered automatically
- Incidents logged with full context
- Rollback path verified available
- SLA target <60s met or documented
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch

import pytest

from src.autonomous_control_plane import SelfHealingEngine
from src.autonomous_control_plane.components.incident_manager import IncidentManager
from src.autonomous_control_plane.components.rollback_coordinator import (
    RollbackCoordinator,
)
from src.autonomous_control_plane.models.healing import (
    HealingStatus,
    LogEntry,
)
from src.autonomous_control_plane.models.incidents import (
    IncidentEvent,
    Severity,
)
from src.common.circuit_breaker import CircuitBreakerRegistry


class TestIncidentScenarioA:
    """Test Scenario A: Redis connectivity failure → auto-restart."""

    @pytest.fixture
    async def simulator(self):
        """Create incident simulator with all components."""
        healing_engine = SelfHealingEngine(
            trading_mode="paper",
            enable_approval_gates=False,
        )
        healing_engine.enable_test_mode()

        incident_manager = IncidentManager()
        rollback_coordinator = RollbackCoordinator(incident_manager=incident_manager)

        yield {
            "healing_engine": healing_engine,
            "incident_manager": incident_manager,
            "rollback_coordinator": rollback_coordinator,
            "cb_registry": CircuitBreakerRegistry(),
        }

    @pytest.mark.asyncio
    async def test_scenario_a_detection_time_under_5_seconds(self, simulator):
        """AC: Detection time <5 seconds for Redis failure scenario."""
        healing_engine = simulator["healing_engine"]

        # Create Redis failure log entry
        log_entry = LogEntry(
            timestamp=datetime.now(UTC),
            level="ERROR",
            source="redis-connection-pool",
            message="ConnectionError: Error 111 connecting to host.docker.internal:6380. Connection refused.",
            metadata={
                "injected": True,
                "scenario": "redis_failure",
                "service": "redis",
            },
        )

        # Measure detection time
        start_time = time.time()
        attempt = await healing_engine.process_log_entry(log_entry)
        detection_time = time.time() - start_time

        # Assert detection time is under 5 seconds
        assert detection_time < 5.0, (
            f"Detection took {detection_time:.2f}s, exceeding 5s limit"
        )
        assert attempt is not None, "Healing attempt should have been created"

    @pytest.mark.asyncio
    async def test_scenario_a_self_healing_triggered(self, simulator):
        """AC: Self-healing triggered automatically for Redis failure."""
        healing_engine = simulator["healing_engine"]

        log_entry = LogEntry(
            timestamp=datetime.now(UTC),
            level="ERROR",
            source="redis-connection-pool",
            message="ConnectionError: Error 111 connecting to host.docker.internal:6380. Connection refused.",
            metadata={
                "injected": True,
                "scenario": "redis_failure",
                "service": "redis",
            },
        )

        attempt = await healing_engine.process_log_entry(log_entry)

        # Verify healing was triggered
        assert attempt is not None, "Healing attempt should have been created"
        assert attempt.action_type == "redis_restart", (
            f"Expected redis_restart, got {attempt.action_type}"
        )
        assert attempt.status in [HealingStatus.COMPLETED, HealingStatus.IN_PROGRESS], (
            f"Unexpected status: {attempt.status}"
        )

    @pytest.mark.asyncio
    async def test_scenario_a_incident_logged_with_context(self, simulator):
        """AC: Incident logged with full context for Redis failure."""
        healing_engine = simulator["healing_engine"]
        incident_manager = simulator["incident_manager"]

        log_entry = LogEntry(
            timestamp=datetime.now(UTC),
            level="ERROR",
            source="redis-connection-pool",
            message="ConnectionError: Error 111 connecting to host.docker.internal:6380. Connection refused.",
            metadata={
                "injected": True,
                "scenario": "redis_failure",
                "service": "redis",
            },
        )

        attempt = await healing_engine.process_log_entry(log_entry)

        # Create incident
        incident_event = IncidentEvent(
            event_type="redis_connection_failed",
            source="redis-connection-pool",
            message="Redis connection failure detected and healing triggered",
            severity_hint=Severity.P2,
            metadata={
                "healing_attempt_id": attempt.attempt_id if attempt else "test-id",
                "action_type": attempt.action_type if attempt else "redis_restart",
                "scenario": "redis_failure",
            },
        )

        incident = await incident_manager.create_incident(incident_event)

        # Verify incident was logged with full context
        assert incident is not None, "Incident should have been created"
        assert incident.incident_id is not None, "Incident should have an ID"
        assert incident.source == "redis-connection-pool", (
            f"Unexpected source: {incident.source}"
        )
        assert incident.severity == Severity.P2, (
            f"Expected P2 severity, got {incident.severity}"
        )
        assert "healing_attempt_id" in incident.metadata, (
            "Incident should reference healing attempt"
        )

    @pytest.mark.asyncio
    async def test_scenario_a_sla_under_60_seconds(self, simulator):
        """AC: Total scenario time <60 seconds."""
        healing_engine = simulator["healing_engine"]
        incident_manager = simulator["incident_manager"]

        start_time = time.time()

        # Inject failure
        log_entry = LogEntry(
            timestamp=datetime.now(UTC),
            level="ERROR",
            source="redis-connection-pool",
            message="ConnectionError: Error 111 connecting to host.docker.internal:6380. Connection refused.",
            metadata={
                "injected": True,
                "scenario": "redis_failure",
                "service": "redis",
            },
        )

        attempt = await healing_engine.process_log_entry(log_entry)

        # Create incident
        incident_event = IncidentEvent(
            event_type="redis_connection_failed",
            source="redis-connection-pool",
            message="Redis connection failure detected and healing triggered",
            severity_hint=Severity.P2,
            metadata={
                "healing_attempt_id": attempt.attempt_id if attempt else "test-id",
                "action_type": attempt.action_type if attempt else "redis_restart",
                "scenario": "redis_failure",
            },
        )

        await incident_manager.create_incident(incident_event)

        total_time = time.time() - start_time

        # Assert total time is under 60 seconds
        assert total_time < 60.0, (
            f"Total scenario time {total_time:.2f}s exceeded 60s SLA"
        )


class TestIncidentScenarioB:
    """Test Scenario B: API timeout → circuit breaker trip → retry."""

    @pytest.fixture
    async def simulator(self):
        """Create incident simulator with all components."""
        healing_engine = SelfHealingEngine(
            trading_mode="paper",
            enable_approval_gates=False,
        )
        healing_engine.enable_test_mode()

        incident_manager = IncidentManager()
        rollback_coordinator = RollbackCoordinator(incident_manager=incident_manager)

        yield {
            "healing_engine": healing_engine,
            "incident_manager": incident_manager,
            "rollback_coordinator": rollback_coordinator,
            "cb_registry": CircuitBreakerRegistry(),
        }

    @pytest.mark.asyncio
    async def test_scenario_b_circuit_breaker_reset(self, simulator):
        """AC: Circuit breaker is reset to CLOSED state."""
        healing_engine = simulator["healing_engine"]
        cb_registry = simulator["cb_registry"]

        # Create and open circuit breaker
        circuit_name = "test-api-circuit"
        cb = cb_registry.get_or_create(circuit_name)
        cb.force_open("test_setup")

        assert cb.get_state_dict()["state"] == "OPEN", "Circuit should be OPEN"

        # Create API timeout log entry
        log_entry = LogEntry(
            timestamp=datetime.now(UTC),
            level="ERROR",
            source="bybit-connector",
            message="API timeout after 30s waiting for response",
            metadata={
                "injected": True,
                "scenario": "api_timeout",
                "service": "bybit-api",
                "circuit_name": circuit_name,
            },
        )

        attempt = await healing_engine.process_log_entry(log_entry)

        # Verify healing was triggered
        assert attempt is not None, "Healing attempt should have been created"
        assert attempt.action_type == "circuit_breaker_reset", (
            f"Expected circuit_breaker_reset, got {attempt.action_type}"
        )

        # Verify circuit breaker was reset
        final_state = cb.get_state_dict()
        assert final_state["state"] == "CLOSED", (
            f"Circuit should be CLOSED, got {final_state['state']}"
        )

    @pytest.mark.asyncio
    async def test_scenario_b_detection_time_under_5_seconds(self, simulator):
        """AC: Detection time <5 seconds for API timeout scenario."""
        healing_engine = simulator["healing_engine"]

        log_entry = LogEntry(
            timestamp=datetime.now(UTC),
            level="ERROR",
            source="bybit-connector",
            message="API timeout after 30s waiting for response",
            metadata={
                "injected": True,
                "scenario": "api_timeout",
                "service": "bybit-api",
                "circuit_name": "test-circuit",
            },
        )

        start_time = time.time()
        attempt = await healing_engine.process_log_entry(log_entry)
        detection_time = time.time() - start_time

        assert detection_time < 5.0, (
            f"Detection took {detection_time:.2f}s, exceeding 5s limit"
        )
        assert attempt is not None, "Healing attempt should have been created"

    @pytest.mark.asyncio
    async def test_scenario_b_incident_logged_with_circuit_context(self, simulator):
        """AC: Incident logged with circuit breaker context."""
        healing_engine = simulator["healing_engine"]
        incident_manager = simulator["incident_manager"]
        cb_registry = simulator["cb_registry"]

        circuit_name = "test-circuit-context"
        cb = cb_registry.get_or_create(circuit_name)
        cb.force_open("test")

        log_entry = LogEntry(
            timestamp=datetime.now(UTC),
            level="ERROR",
            source="bybit-connector",
            message="API timeout after 30s waiting for response",
            metadata={
                "injected": True,
                "scenario": "api_timeout",
                "service": "bybit-api",
                "circuit_name": circuit_name,
            },
        )

        attempt = await healing_engine.process_log_entry(log_entry)

        incident_event = IncidentEvent(
            event_type="api_timeout",
            source="bybit-connector",
            message="API timeout detected, circuit breaker reset triggered",
            severity_hint=Severity.P2,
            metadata={
                "healing_attempt_id": attempt.attempt_id if attempt else "test-id",
                "circuit_name": circuit_name,
                "circuit_state_before": "OPEN",
                "circuit_state_after": "CLOSED",
                "scenario": "api_timeout",
            },
        )

        incident = await incident_manager.create_incident(incident_event)

        # Verify incident has circuit breaker context
        assert incident is not None
        assert "circuit_name" in incident.metadata, (
            "Incident should reference circuit name"
        )
        assert "circuit_state_before" in incident.metadata, (
            "Incident should record before state"
        )
        assert "circuit_state_after" in incident.metadata, (
            "Incident should record after state"
        )


class TestIncidentScenarioC:
    """Test Scenario C: Service degradation → incident logged → rollback available."""

    @pytest.fixture
    async def simulator(self):
        """Create incident simulator with all components."""
        healing_engine = SelfHealingEngine(
            trading_mode="paper",
            enable_approval_gates=False,
        )
        healing_engine.enable_test_mode()

        incident_manager = IncidentManager()
        rollback_coordinator = RollbackCoordinator(incident_manager=incident_manager)

        yield {
            "healing_engine": healing_engine,
            "incident_manager": incident_manager,
            "rollback_coordinator": rollback_coordinator,
            "cb_registry": CircuitBreakerRegistry(),
        }

    @pytest.mark.asyncio
    async def test_scenario_c_rollback_path_available(self, simulator):
        """AC: Rollback path verified available."""
        rollback_coordinator = simulator["rollback_coordinator"]

        # Create rollback operation
        target_state = "v1.2.3-stable"
        rollback_op = await rollback_coordinator.create_rollback_operation(
            target_state=target_state,
            initiated_by="test",
            metadata={"scenario": "service_degradation"},
        )

        # Verify rollback path is available
        validation_result = await rollback_coordinator.validate_rollback(target_state)

        assert validation_result.valid, "Rollback path should be available"
        assert rollback_op.operation_id is not None, (
            "Rollback operation should have an ID"
        )

    @pytest.mark.asyncio
    async def test_scenario_c_incident_with_severity_classification(self, simulator):
        """AC: Incident logged with proper severity classification."""
        healing_engine = simulator["healing_engine"]
        incident_manager = simulator["incident_manager"]

        log_entry = LogEntry(
            timestamp=datetime.now(UTC),
            level="WARNING",
            source="order-simulator",
            message="Service degradation detected: response time > 5000ms, error rate > 5%",
            metadata={
                "injected": True,
                "scenario": "service_degradation",
                "service": "order-simulator",
                "response_time_ms": 5200,
                "error_rate": 0.06,
            },
        )

        attempt = await healing_engine.process_log_entry(log_entry)

        incident_event = IncidentEvent(
            event_type="service_degraded",
            source="order-simulator",
            message="Service degradation detected: high latency and error rate",
            severity_hint=Severity.P1,
            metadata={
                "healing_attempt_id": attempt.attempt_id if attempt else None,
                "response_time_ms": 5200,
                "error_rate": 0.06,
                "scenario": "service_degradation",
            },
        )

        incident = await incident_manager.create_incident(incident_event)

        # Verify incident has proper severity
        assert incident is not None
        assert incident.severity == Severity.P1, (
            f"Expected P1 severity, got {incident.severity}"
        )
        assert "response_time_ms" in incident.metadata, (
            "Incident should include performance data"
        )
        assert "error_rate" in incident.metadata, "Incident should include error rate"

    @pytest.mark.asyncio
    async def test_scenario_c_rollback_path_timing_under_sla(self, simulator):
        """AC: Rollback path verification completes within SLA."""
        rollback_coordinator = simulator["rollback_coordinator"]

        target_state = "v1.2.3-stable"

        # Create rollback operation first
        await rollback_coordinator.create_rollback_operation(
            target_state=target_state,
            initiated_by="test",
        )

        # Measure rollback path verification time
        start_time = time.time()
        validation_result = await rollback_coordinator.validate_rollback(target_state)
        rollback_path_time = time.time() - start_time

        # Rollback path check should be fast (part of the 60s SLA)
        assert rollback_path_time < 10.0, (
            f"Rollback path check took {rollback_path_time:.2f}s, should be <10s"
        )
        assert validation_result.valid, "Rollback path should be valid"


class TestTimingAndSLA:
    """Test overall timing and SLA compliance."""

    @pytest.mark.asyncio
    async def test_all_scenarios_complete_within_60_seconds(self):
        """AC: All 3 scenarios complete within 60 seconds each."""
        # This is a meta-test that runs all scenarios and checks total timing
        healing_engine = SelfHealingEngine(
            trading_mode="paper",
            enable_approval_gates=False,
        )
        healing_engine.enable_test_mode()
        incident_manager = IncidentManager()
        rollback_coordinator = RollbackCoordinator(incident_manager=incident_manager)
        cb_registry = CircuitBreakerRegistry()

        scenario_times = []

        # Scenario A: Redis failure
        start = time.time()
        log_entry_a = LogEntry(
            timestamp=datetime.now(UTC),
            level="ERROR",
            source="redis-connection-pool",
            message="ConnectionError: Error 111 connecting to host.docker.internal:6380. Connection refused.",
            metadata={
                "injected": True,
                "scenario": "redis_failure",
                "service": "redis",
            },
        )
        await healing_engine.process_log_entry(log_entry_a)
        scenario_times.append(("A", time.time() - start))

        # Scenario B: API timeout
        start = time.time()
        cb = cb_registry.get_or_create("test-circuit")
        cb.force_open("test")
        log_entry_b = LogEntry(
            timestamp=datetime.now(UTC),
            level="ERROR",
            source="bybit-connector",
            message="API timeout after 30s waiting for response",
            metadata={
                "injected": True,
                "scenario": "api_timeout",
                "service": "bybit-api",
                "circuit_name": "test-circuit",
            },
        )
        await healing_engine.process_log_entry(log_entry_b)
        scenario_times.append(("B", time.time() - start))

        # Scenario C: Service degradation with rollback
        start = time.time()
        await rollback_coordinator.create_rollback_operation(
            target_state="v1.2.3-stable",
            initiated_by="test",
        )
        log_entry_c = LogEntry(
            timestamp=datetime.now(UTC),
            level="WARNING",
            source="order-simulator",
            message="Service degradation detected",
            metadata={
                "injected": True,
                "scenario": "service_degradation",
                "service": "order-simulator",
            },
        )
        await healing_engine.process_log_entry(log_entry_c)
        await rollback_coordinator.validate_rollback("v1.2.3-stable")
        scenario_times.append(("C", time.time() - start))

        # Verify all scenarios completed within 60 seconds
        for scenario, duration in scenario_times:
            assert duration < 60.0, (
                f"Scenario {scenario} took {duration:.2f}s, exceeding 60s SLA"
            )

    @pytest.mark.asyncio
    async def test_detection_times_under_5_seconds(self):
        """AC: All detection times are under 5 seconds."""
        healing_engine = SelfHealingEngine(
            trading_mode="paper",
            enable_approval_gates=False,
        )
        healing_engine.enable_test_mode()

        detection_times = []

        # Test multiple log entries
        test_entries = [
            LogEntry(
                timestamp=datetime.now(UTC),
                level="ERROR",
                source="redis-connection-pool",
                message="ConnectionError: Error 111 connecting to host.docker.internal:6380. Connection refused.",
                metadata={"injected": True, "service": "redis"},
            ),
            LogEntry(
                timestamp=datetime.now(UTC),
                level="ERROR",
                source="bybit-connector",
                message="API timeout after 30s waiting for response",
                metadata={
                    "injected": True,
                    "service": "bybit-api",
                    "circuit_name": "test-circuit",
                },
            ),
            LogEntry(
                timestamp=datetime.now(UTC),
                level="WARNING",
                source="order-simulator",
                message="Service degradation detected",
                metadata={"injected": True, "service": "order-simulator"},
            ),
        ]

        for entry in test_entries:
            start = time.time()
            await healing_engine.process_log_entry(entry)
            detection_time = time.time() - start
            detection_times.append(detection_time)

        # All detection times should be under 5 seconds
        for i, dt in enumerate(detection_times):
            assert dt < 5.0, f"Detection {i} took {dt:.2f}s, exceeding 5s limit"


class TestIntegrationFlow:
    """Test complete integration flow across all components."""

    @pytest.mark.asyncio
    async def test_end_to_end_flow_detection_to_logging(self):
        """Test complete flow from detection through incident logging."""
        healing_engine = SelfHealingEngine(
            trading_mode="paper",
            enable_approval_gates=False,
        )
        healing_engine.enable_test_mode()
        incident_manager = IncidentManager()

        # Inject failure
        log_entry = LogEntry(
            timestamp=datetime.now(UTC),
            level="ERROR",
            source="redis-connection-pool",
            message="ConnectionError: Error 111 connecting to host.docker.internal:6380. Connection refused.",
            metadata={
                "injected": True,
                "scenario": "integration_test",
                "service": "redis",
            },
        )

        # Detection
        attempt = await healing_engine.process_log_entry(log_entry)
        assert attempt is not None, "Detection should trigger healing attempt"

        # Healing
        assert attempt.action_type is not None, "Healing action should be determined"

        # Incident logging
        incident_event = IncidentEvent(
            event_type="redis_connection_failed",
            source="redis-connection-pool",
            message="Redis connection failure detected",
            severity_hint=Severity.P2,
            metadata={
                "healing_attempt_id": attempt.attempt_id,
                "action_type": attempt.action_type,
                "scenario": "integration_test",
            },
        )

        incident = await incident_manager.create_incident(incident_event)
        assert incident is not None, "Incident should be created"
        assert incident.incident_id is not None, "Incident should have ID"

        # Verify incident can be retrieved
        retrieved = await incident_manager.get_incident(incident.incident_id)
        assert retrieved is not None, "Incident should be retrievable"
        assert retrieved.incident_id == incident.incident_id, (
            "Retrieved incident should match"
        )

    @pytest.mark.asyncio
    async def test_rollback_coordinator_integration_with_incident_manager(self):
        """Test rollback coordinator properly integrates with incident manager."""
        incident_manager = IncidentManager()
        rollback_coordinator = RollbackCoordinator(incident_manager=incident_manager)

        # Create rollback operation
        rollback_op = await rollback_coordinator.create_rollback_operation(
            target_state="v1.0.0-stable",
            initiated_by="test_integration",
        )

        assert rollback_op is not None, "Rollback operation should be created"
        assert rollback_op.operation_id is not None, "Operation should have ID"

        # Validate rollback
        validation = await rollback_coordinator.validate_rollback("v1.0.0-stable")
        assert validation is not None, "Validation should return result"
        assert validation.valid, "Validation should pass"
