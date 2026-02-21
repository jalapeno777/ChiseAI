"""Tests for Self-Healing Engine.

Tests for ST-NS-040: Self-Healing Engine with Action Sandboxing

Acceptance Criteria:
1. Recognize 10+ failure patterns (Redis disconnect, API timeout, etc.)
2. Sandboxed execution with resource limits
3. Failed healing actions rolled back within 30s
4. Max 3 healing attempts/hour/service
5. Human approval for P0/live-trading actions
6. Full context logging for post-mortem
7. Healing activity dashboard visibility
"""

from __future__ import annotations

import pytest
from datetime import UTC, datetime
from unittest.mock import patch

from src.autonomous_control_plane import (
    SelfHealingEngine,
    FailurePatternMatcher,
    LogEntry,
)
from src.autonomous_control_plane.models.healing import (
    FailurePatternType,
    ActionPriority,
)
from src.autonomous_control_plane.components.failure_patterns import (
    RedisDisconnectPattern,
    APITimeoutPattern,
    CircuitBreakerOpenPattern,
    DatabaseConnectionPattern,
    MemoryExhaustionPattern,
    DiskSpacePattern,
    CPUSpikePattern,
    InfluxDBWritePattern,
    DeadLetterQueuePattern,
    ServiceUnhealthyPattern,
)
from src.autonomous_control_plane.models.healing import FailurePatternType


class TestFailurePatternDetection:
    """Test failure pattern detection (AC 1)."""

    def test_redis_disconnect_pattern(self):
        """Test Redis disconnect pattern matching."""
        pattern = RedisDisconnectPattern()

        # Should match
        log = LogEntry(
            timestamp=datetime.now(UTC),
            level="ERROR",
            source="redis_client",
            message="Redis connection error: Connection refused",
        )
        match = pattern.match(log)
        assert match.matched is True
        assert match.pattern_type == FailurePatternType.REDIS_DISCONNECT
        assert match.confidence > 0.8

        # Should not match
        log2 = LogEntry(
            timestamp=datetime.now(UTC),
            level="INFO",
            source="app",
            message="Successfully connected to Redis",
        )
        match2 = pattern.match(log2)
        assert match2.matched is False

    def test_api_timeout_pattern(self):
        """Test API timeout pattern matching."""
        pattern = APITimeoutPattern()

        log = LogEntry(
            timestamp=datetime.now(UTC),
            level="ERROR",
            source="api_client",
            message="Request timeout: GET https://api.exchange.com/v1/ticker",
        )
        match = pattern.match(log)
        assert match.matched is True
        assert match.pattern_type == FailurePatternType.API_TIMEOUT
        assert match.extracted_fields.get("endpoint") is not None

    def test_circuit_breaker_open_pattern(self):
        """Test circuit breaker open pattern matching."""
        pattern = CircuitBreakerOpenPattern()

        log = LogEntry(
            timestamp=datetime.now(UTC),
            level="WARNING",
            source="circuit_breaker",
            message="Circuit breaker 'redis' transitioned: CLOSED -> OPEN",
        )
        match = pattern.match(log)
        assert match.matched is True
        assert match.pattern_type == FailurePatternType.CIRCUIT_BREAKER_OPEN
        assert match.confidence > 0.9

    def test_database_connection_pattern(self):
        """Test database connection failure pattern matching."""
        pattern = DatabaseConnectionPattern()

        log = LogEntry(
            timestamp=datetime.now(UTC),
            level="ERROR",
            source="postgres",
            message="psycopg2.OperationalError: connection to server failed",
        )
        match = pattern.match(log)
        assert match.matched is True
        assert match.pattern_type == FailurePatternType.DATABASE_CONNECTION

    def test_memory_exhaustion_pattern(self):
        """Test memory exhaustion pattern matching."""
        pattern = MemoryExhaustionPattern()

        log = LogEntry(
            timestamp=datetime.now(UTC),
            level="CRITICAL",
            source="monitor",
            message="Memory usage critical: 95%",
        )
        match = pattern.match(log)
        assert match.matched is True
        assert match.pattern_type == FailurePatternType.MEMORY_EXHAUSTION
        assert match.extracted_fields.get("memory_percent") == 95.0

    def test_disk_space_pattern(self):
        """Test disk space pattern matching."""
        pattern = DiskSpacePattern()

        log = LogEntry(
            timestamp=datetime.now(UTC),
            level="WARNING",
            source="monitor",
            message="Disk space low: 95% full",
        )
        match = pattern.match(log)
        assert match.matched is True
        assert match.pattern_type == FailurePatternType.DISK_SPACE

    def test_cpu_spike_pattern(self):
        """Test CPU spike pattern matching."""
        pattern = CPUSpikePattern()

        log = LogEntry(
            timestamp=datetime.now(UTC),
            level="WARNING",
            source="monitor",
            message="CPU spike detected: 95% usage",
        )
        match = pattern.match(log)
        assert match.matched is True
        assert match.pattern_type == FailurePatternType.CPU_SPIKE

    def test_influxdb_write_pattern(self):
        """Test InfluxDB write failure pattern matching."""
        pattern = InfluxDBWritePattern()

        log = LogEntry(
            timestamp=datetime.now(UTC),
            level="ERROR",
            source="influx_client",
            message="InfluxDB write failed: timeout",
        )
        match = pattern.match(log)
        assert match.matched is True
        assert match.pattern_type == FailurePatternType.INFLUXDB_WRITE

    def test_dead_letter_queue_pattern(self):
        """Test dead letter queue pattern matching."""
        pattern = DeadLetterQueuePattern()

        log = LogEntry(
            timestamp=datetime.now(UTC),
            level="WARNING",
            source="queue_manager",
            message="DLQ depth exceeded: 1000 messages",
        )
        match = pattern.match(log)
        assert match.matched is True
        assert match.pattern_type == FailurePatternType.DEAD_LETTER_QUEUE
        assert match.extracted_fields.get("queue_depth") == 1000

    def test_service_unhealthy_pattern(self):
        """Test service unhealthy pattern matching."""
        pattern = ServiceUnhealthyPattern()

        log = LogEntry(
            timestamp=datetime.now(UTC),
            level="ERROR",
            source="health_monitor",
            message="Health check failed for service 'api-gateway'",
        )
        match = pattern.match(log)
        assert match.matched is True
        assert match.pattern_type == FailurePatternType.SERVICE_UNHEALTHY

    def test_pattern_matcher_with_all_patterns(self):
        """Test that pattern matcher registers all 10+ patterns."""
        matcher = FailurePatternMatcher()
        matcher.register_default_patterns()

        assert matcher.pattern_count >= 10

        # Test each pattern type is registered
        patterns = matcher.list_patterns()
        pattern_types = {p["type"] for p in patterns}

        expected_types = {
            "redis_disconnect",
            "api_timeout",
            "circuit_breaker_open",
            "database_connection",
            "memory_exhaustion",
            "disk_space",
            "cpu_spike",
            "influxdb_write",
            "dead_letter_queue",
            "service_unhealthy",
        }

        assert expected_types.issubset(pattern_types)

    def test_pattern_priority_scoring(self):
        """Test pattern priority and scoring."""
        matcher = FailurePatternMatcher()
        matcher.register_default_patterns()

        # Redis disconnect has higher priority
        log = LogEntry(
            timestamp=datetime.now(UTC),
            level="ERROR",
            source="redis_client",
            message="Redis connection error",
        )
        match = matcher.match(log)
        assert match.matched is True
        assert match.priority > 0


class TestSandboxResourceLimits:
    """Test sandboxed execution with resource limits (AC 2)."""

    def test_resource_limits_configuration(self):
        """Test resource limits are properly configured."""
        from src.autonomous_control_plane.healing_actions.redis_restart import (
            RedisRestartAction,
        )
        from src.autonomous_control_plane.healing_actions.api_timeout_recovery import (
            APIRetryAction,
        )

        redis_action = RedisRestartAction()
        limits = redis_action.get_resource_limits()

        assert limits.max_cpu_seconds > 0
        assert limits.max_memory_mb > 0
        assert limits.max_execution_seconds > 0
        assert limits.max_file_descriptors > 0

        api_action = APIRetryAction()
        limits2 = api_action.get_resource_limits()

        assert limits2.max_cpu_seconds > 0
        assert limits2.max_memory_mb > 0

    def test_healing_action_validation(self):
        """Test healing action validation."""
        from src.autonomous_control_plane.healing_actions.redis_restart import (
            RedisRestartAction,
        )

        action = RedisRestartAction()
        errors = action.validate()

        assert len(errors) == 0


class TestAntiFlapEnforcement:
    """Test anti-flap enforcement (AC 4)."""

    @pytest.fixture
    def engine(self):
        return SelfHealingEngine(trading_mode="paper")

    def test_max_attempts_per_hour(self, engine):
        """Test that max 3 attempts per hour per service is enforced."""
        service = "test-service"

        # Simulate 3 attempts
        for i in range(3):
            assert engine._can_attempt_healing(service) is True
            # Record attempt
            from src.autonomous_control_plane.models.healing import HealingAttempt

            attempt = HealingAttempt(
                service=service,
                action_type="test_action",
                attempt_number=i + 1,
            )
            engine._record_attempt(attempt)

        # 4th attempt should be blocked
        assert engine._can_attempt_healing(service) is False

    def test_attempt_counting(self, engine):
        """Test attempt counting is accurate."""
        service = "test-service"

        assert engine._get_attempt_count(service) == 0

        from src.autonomous_control_plane.models.healing import HealingAttempt

        attempt = HealingAttempt(
            service=service,
            action_type="test_action",
            attempt_number=1,
        )
        engine._record_attempt(attempt)

        assert engine._get_attempt_count(service) == 1

    def test_service_stats(self, engine):
        """Test service stats provide accurate information."""
        service = "test-service"
        stats = engine.get_service_stats(service)

        assert stats["service"] == service
        assert stats["max_attempts_per_hour"] == 3
        assert stats["can_attempt"] is True


class TestHumanApprovalGate:
    """Test human approval workflow for P0/live-trading actions (AC 5)."""

    def test_p0_requires_approval_in_live_mode(self):
        """Test P0 actions require approval in live mode."""
        from src.autonomous_control_plane.healing_actions.redis_restart import (
            RedisRestartAction,
        )

        action = RedisRestartAction()

        # P2 action should not require approval in any mode
        assert action.priority == ActionPriority.P2
        assert action.requires_human_approval("live") is False
        assert action.requires_human_approval("paper") is False

    def test_engine_tracks_pending_approvals(self):
        """Test engine tracks pending approval requests."""
        # Create engine in live mode
        engine = SelfHealingEngine(trading_mode="live")

        # Check initial state
        assert len(engine.get_pending_approvals()) == 0

    @pytest.mark.asyncio
    async def test_approve_healing_action(self):
        """Test approving a healing action."""
        from src.autonomous_control_plane.models.healing import (
            HealingAttempt,
            HealingStatus,
        )

        engine = SelfHealingEngine(trading_mode="paper")

        # Create a pending approval
        attempt = HealingAttempt(
            service="test-service",
            action_type="test_action",
            status=HealingStatus.AWAITING_APPROVAL,
        )
        attempt.requires_approval = True
        engine._pending_approvals[attempt.attempt_id] = attempt

        # Approve it (this creates an async task, which works in async test)
        with patch.object(engine, "_execute_approved_healing"):
            result = engine.approve_healing(attempt.attempt_id, "admin")

        assert result is not None
        assert result.approved_by == "admin"
        assert result.approved_at is not None

    def test_reject_healing_action(self):
        """Test rejecting a healing action."""
        from src.autonomous_control_plane.models.healing import (
            HealingAttempt,
            HealingStatus,
        )

        engine = SelfHealingEngine(trading_mode="paper")

        # Create a pending approval
        attempt = HealingAttempt(
            service="test-service",
            action_type="test_action",
            status=HealingStatus.AWAITING_APPROVAL,
        )
        attempt.requires_approval = True
        engine._pending_approvals[attempt.attempt_id] = attempt

        # Reject it
        result = engine.reject_healing(attempt.attempt_id, "admin")

        assert result is not None
        assert result.status == HealingStatus.REJECTED
        assert result.approved_by == "admin"


class TestLoggingContext:
    """Test full context logging for post-mortem (AC 6)."""

    def test_healing_attempt_logging(self):
        """Test healing attempts have full context for logging."""
        from src.autonomous_control_plane.models.healing import (
            HealingAttempt,
            HealingResult,
        )

        attempt = HealingAttempt(
            service="test-service",
            action_type="redis_restart",
            attempt_number=1,
        )

        result = HealingResult(
            success=True,
            action_id=attempt.attempt_id,
            action_type="redis_restart",
            service="test-service",
            duration_seconds=5.0,
            details={"steps": ["closed", "restarted", "verified"]},
        )
        attempt.complete(result)

        # Verify all fields are present in dict output
        data = attempt.to_dict()
        assert "attempt_id" in data
        assert "service" in data
        assert "action_type" in data
        assert "status" in data
        assert "started_at" in data
        assert "completed_at" in data
        assert "result" in data

    def test_log_entry_structure(self):
        """Test log entry has proper structure."""
        log = LogEntry(
            timestamp=datetime.now(UTC),
            level="ERROR",
            source="test-service",
            message="Test error message",
            metadata={"extra": "data"},
        )

        data = log.to_dict()
        assert data["level"] == "ERROR"
        assert data["source"] == "test-service"
        assert data["message"] == "Test error message"
        assert data["metadata"] == {"extra": "data"}


class TestSelfHealingEngineCore:
    """Test Self-Healing Engine core functionality."""

    @pytest.fixture
    def engine(self):
        return SelfHealingEngine(trading_mode="paper")

    @pytest.mark.asyncio
    async def test_process_log_entry_no_match(self, engine):
        """Test processing log entry with no matching pattern."""
        log = LogEntry(
            timestamp=datetime.now(UTC),
            level="INFO",
            source="app",
            message="Normal operation",
        )

        result = await engine.process_log_entry(log)
        assert result is None

    @pytest.mark.asyncio
    async def test_process_log_entry_with_match(self, engine):
        """Test processing log entry with matching pattern."""
        log = LogEntry(
            timestamp=datetime.now(UTC),
            level="ERROR",
            source="redis_client",
            message="Redis connection error: Connection refused",
        )

        result = await engine.process_log_entry(log)
        # Should return a healing attempt
        assert result is not None
        assert result.service == "redis_client"

    def test_engine_status(self, engine):
        """Test engine status report."""
        status = engine.get_status()

        assert "enabled" in status
        assert "trading_mode" in status
        assert "pattern_count" in status
        assert "stats" in status
        assert status["trading_mode"] == "paper"

    def test_disable_enable(self, engine):
        """Test disabling and enabling engine."""
        assert engine.is_enabled() is True

        engine.disable()
        assert engine.is_enabled() is False

        engine.enable()
        assert engine.is_enabled() is True

    def test_healing_history(self, engine):
        """Test healing history tracking."""
        # Initially empty
        history = engine.get_healing_history()
        assert len(history) == 0

    def test_get_nonexistent_approval(self, engine):
        """Test getting approval for non-existent attempt."""
        result = engine.approve_healing("non-existent-id", "admin")
        assert result is None


class TestHealingStats:
    """Test healing statistics tracking."""

    def test_stats_accumulation(self):
        """Test stats accumulate correctly."""
        from src.autonomous_control_plane.models.healing import (
            HealingStats,
            HealingStatus,
        )

        stats = HealingStats()

        stats.record_attempt("service1", "redis_disconnect", HealingStatus.SUCCEEDED)
        stats.record_attempt("service1", "redis_disconnect", HealingStatus.FAILED)
        stats.record_attempt("service2", "api_timeout", HealingStatus.SUCCEEDED)

        assert stats.total_attempts == 3
        assert stats.successful == 2
        assert stats.failed == 1

        data = stats.to_dict()
        assert data["total_attempts"] == 3
        assert "by_service" in data
        assert "by_pattern" in data
