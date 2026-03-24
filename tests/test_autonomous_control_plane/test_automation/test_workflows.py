"""Tests for remediation workflows.

For ST-CONTROL-002: Self-Healing Automation
"""

import pytest

from autonomous_control_plane.automation import RunbookEngine
from autonomous_control_plane.automation.workflows import RemediationWorkflows
from autonomous_control_plane.models.healing import FailurePatternType


class TestRemediationWorkflows:
    """Test suite for RemediationWorkflows."""

    @pytest.fixture
    def engine(self):
        """Create runbook engine fixture."""
        return RunbookEngine(trading_mode="paper")

    @pytest.fixture
    def workflows(self, engine):
        """Create workflows fixture."""
        return RemediationWorkflows(engine)

    def test_workflows_initialization(self, workflows):
        """Test workflows initialization."""
        assert workflows._engine is not None

    def test_create_redis_recovery_runbook(self, workflows):
        """Test creating Redis recovery runbook."""
        runbook = workflows.create_redis_recovery_runbook("redis")

        assert runbook.name == "Redis Connection Recovery"
        assert len(runbook.steps) == 5
        assert runbook.tags == ["redis", "connection", "recovery"]

        # Check steps
        step_names = [s.name for s in runbook.steps]
        assert "Check Redis Status" in step_names
        assert "Flush Connection Pool" in step_names
        assert "Restart Redis Client" in step_names
        assert "Verify Connectivity" in step_names
        assert "Run Health Checks" in step_names

    def test_create_api_timeout_remediation_runbook(self, workflows):
        """Test creating API timeout remediation runbook."""
        runbook = workflows.create_api_timeout_remediation_runbook(
            endpoint="/api/v1/test",
            service_name="api_service",
        )

        assert runbook.name == "API Timeout Remediation"
        assert len(runbook.steps) == 5
        assert runbook.tags == ["api", "timeout", "remediation"]

        step_names = [s.name for s in runbook.steps]
        assert "Check API Status" in step_names
        assert "Retry with Backoff" in step_names
        assert "Clear Request Cache" in step_names

    def test_create_circuit_breaker_reset_runbook(self, workflows):
        """Test creating circuit breaker reset runbook."""
        runbook = workflows.create_circuit_breaker_reset_runbook("api_circuit")

        assert runbook.name == "Circuit Breaker Reset Sequence"
        assert len(runbook.steps) == 5
        assert runbook.tags == ["circuit_breaker", "reset", "stability"]

        step_names = [s.name for s in runbook.steps]
        assert "Check Circuit State" in step_names
        assert "Reset Circuit Breaker" in step_names
        assert "Verify Reset" in step_names

        # Check that reset step requires approval
        reset_step = next(s for s in runbook.steps if "Reset Circuit Breaker" in s.name)
        assert reset_step.requires_approval is True

    def test_create_service_restart_runbook(self, workflows):
        """Test creating service restart runbook."""
        runbook = workflows.create_service_restart_runbook(
            service_name="my_service",
            health_check_endpoint="/health",
        )

        assert runbook.name == "Service Restart: my_service"
        assert len(runbook.steps) == 7

        step_names = [s.name for s in runbook.steps]
        assert "Pre-Restart Health Check" in step_names
        assert "Graceful Shutdown" in step_names
        assert "Restart Service" in step_names
        assert "Post-Restart Health Check" in step_names

        # Check that shutdown requires approval
        shutdown_step = next(s for s in runbook.steps if "Graceful Shutdown" in s.name)
        assert shutdown_step.requires_approval is True

    def test_create_database_recovery_runbook(self, workflows):
        """Test creating database recovery runbook."""
        runbook = workflows.create_database_recovery_runbook(
            db_name="postgres",
            service_name="database",
        )

        assert runbook.name == "Database Connection Recovery"
        assert len(runbook.steps) == 5
        assert runbook.tags == ["database", "connection", "recovery"]

        step_names = [s.name for s in runbook.steps]
        assert "Check Database Connectivity" in step_names
        assert "Reset Connection Pool" in step_names
        assert "Run Database Health Checks" in step_names

    def test_create_memory_exhaustion_runbook(self, workflows):
        """Test creating memory exhaustion runbook."""
        runbook = workflows.create_memory_exhaustion_runbook("app_service")

        assert runbook.name == "Memory Exhaustion Remediation"
        assert len(runbook.steps) == 6
        assert runbook.tags == ["memory", "exhaustion", "remediation"]

        step_names = [s.name for s in runbook.steps]
        assert "Analyze Memory Usage" in step_names
        assert "Clear Caches" in step_names
        assert "Trigger Garbage Collection" in step_names

    def test_create_disk_space_cleanup_runbook(self, workflows):
        """Test creating disk space cleanup runbook."""
        runbook = workflows.create_disk_space_cleanup_runbook("system")

        assert runbook.name == "Disk Space Cleanup"
        assert len(runbook.steps) == 5
        assert runbook.tags == ["disk", "cleanup", "space"]

        step_names = [s.name for s in runbook.steps]
        assert "Analyze Disk Usage" in step_names
        assert "Clean Temporary Files" in step_names
        assert "Rotate Logs" in step_names

    def test_create_cpu_spike_mitigation_runbook(self, workflows):
        """Test creating CPU spike mitigation runbook."""
        runbook = workflows.create_cpu_spike_mitigation_runbook("app_service")

        assert runbook.name == "CPU Spike Mitigation"
        assert len(runbook.steps) == 5
        assert runbook.tags == ["cpu", "spike", "mitigation"]

        step_names = [s.name for s in runbook.steps]
        assert "Analyze CPU Usage" in step_names
        assert "Throttle Processes" in step_names
        assert "Monitor CPU" in step_names

    def test_create_influxdb_recovery_runbook(self, workflows):
        """Test creating InfluxDB recovery runbook."""
        runbook = workflows.create_influxdb_recovery_runbook("influxdb")

        assert runbook.name == "InfluxDB Write Recovery"
        assert len(runbook.steps) == 5
        assert runbook.tags == ["influxdb", "write", "recovery"]

        step_names = [s.name for s in runbook.steps]
        assert "Check InfluxDB Status" in step_names
        assert "Flush Write Buffer" in step_names
        assert "Verify Writes Succeeding" in step_names

    def test_create_dead_letter_queue_runbook(self, workflows):
        """Test creating dead letter queue runbook."""
        runbook = workflows.create_dead_letter_queue_runbook("dlq")

        assert runbook.name == "Dead Letter Queue Processing"
        assert len(runbook.steps) == 5
        assert runbook.tags == ["dlq", "queue", "processing"]

        step_names = [s.name for s in runbook.steps]
        assert "Analyze DLQ Contents" in step_names
        assert "Retry Retryable Messages" in step_names
        assert "Archive Failed Messages" in step_names

    def test_create_service_health_recovery_runbook(self, workflows):
        """Test creating service health recovery runbook."""
        runbook = workflows.create_service_health_recovery_runbook("my_service")

        assert runbook.name == "Service Health Recovery: my_service"
        assert len(runbook.steps) == 5
        assert runbook.tags == ["service", "health", "recovery"]

        step_names = [s.name for s in runbook.steps]
        assert "Comprehensive Health Check" in step_names
        assert "Identify Unhealthy Components" in step_names
        assert "Verify Health Restored" in step_names

    def test_create_configuration_reload_runbook(self, workflows):
        """Test creating configuration reload runbook."""
        runbook = workflows.create_configuration_reload_runbook("my_service")

        assert runbook.name == "Configuration Reload: my_service"
        assert len(runbook.steps) == 5
        assert runbook.tags == ["config", "reload", "validation"]

        step_names = [s.name for s in runbook.steps]
        assert "Validate New Configuration" in step_names
        assert "Backup Current Configuration" in step_names
        assert "Apply New Configuration" in step_names

        # Check that apply step requires approval
        apply_step = next(
            s for s in runbook.steps if "Apply New Configuration" in s.name
        )
        assert apply_step.requires_approval is True

    def test_get_all_workflow_templates(self, workflows):
        """Test getting all workflow templates."""
        templates = workflows.get_all_workflow_templates()

        assert len(templates) == 12
        assert "redis_recovery" in templates
        assert "api_timeout_remediation" in templates
        assert "circuit_breaker_reset" in templates
        assert "service_restart" in templates
        assert "database_recovery" in templates
        assert "memory_exhaustion" in templates
        assert "disk_space_cleanup" in templates
        assert "cpu_spike_mitigation" in templates
        assert "influxdb_recovery" in templates
        assert "dead_letter_queue" in templates
        assert "service_health_recovery" in templates
        assert "configuration_reload" in templates

    def test_create_workflow_for_pattern_redis(self, workflows):
        """Test creating workflow for Redis pattern."""
        runbook = workflows.create_workflow_for_pattern(
            FailurePatternType.REDIS_DISCONNECT
        )

        assert runbook is not None
        assert "Redis" in runbook.name

    def test_create_workflow_for_pattern_api_timeout(self, workflows):
        """Test creating workflow for API timeout pattern."""
        runbook = workflows.create_workflow_for_pattern(FailurePatternType.API_TIMEOUT)

        assert runbook is not None
        assert "API Timeout" in runbook.name

    def test_create_workflow_for_pattern_circuit_breaker(self, workflows):
        """Test creating workflow for circuit breaker pattern."""
        runbook = workflows.create_workflow_for_pattern(
            FailurePatternType.CIRCUIT_BREAKER_OPEN
        )

        assert runbook is not None
        assert "Circuit Breaker" in runbook.name

    def test_create_workflow_for_pattern_no_match(self, workflows):
        """Test creating workflow for pattern with no matching workflow."""
        # Test with a pattern that doesn't have a specific workflow
        # (all patterns should have workflows)
        runbook = workflows.create_workflow_for_pattern(
            FailurePatternType.DATABASE_CONNECTION
        )

        # Should still return a runbook
        assert runbook is not None

    def test_workflow_step_dependencies(self, workflows):
        """Test that workflow steps have proper dependencies."""
        runbook = workflows.create_redis_recovery_runbook("redis")

        # Find steps with dependencies
        steps_with_deps = [s for s in runbook.steps if s.depends_on]

        # At least some steps should have dependencies
        assert len(steps_with_deps) >= 2

        # Verify dependencies reference actual steps
        all_step_ids = {s.step_id for s in runbook.steps}
        for step in steps_with_deps:
            for dep_id in step.depends_on:
                assert dep_id in all_step_ids

    def test_workflow_rollback_actions(self, workflows):
        """Test that critical steps have rollback actions."""
        runbook = workflows.create_redis_recovery_runbook("redis")

        # Find steps with rollback actions
        steps_with_rollback = [s for s in runbook.steps if s.rollback_action]

        # Critical steps should have rollback
        assert len(steps_with_rollback) >= 1

    def test_workflow_step_timeouts(self, workflows):
        """Test that steps have appropriate timeouts."""
        runbook = workflows.create_service_restart_runbook("service")

        for step in runbook.steps:
            assert step.timeout_seconds > 0
            # Service restart/shutdown action steps (not health checks or waits) should have longer timeouts
            step_name_lower = step.name.lower()
            is_action_step = step.action_type in ["shell", "python"]
            is_restart_action = (
                ("restart" in step_name_lower or "shutdown" in step_name_lower)
                and "health" not in step_name_lower
                and "check" not in step_name_lower
                and "wait" not in step_name_lower
            )
            if is_restart_action and is_action_step:
                assert (
                    step.timeout_seconds >= 30
                ), f"Step '{step.name}' should have timeout >= 30s"
