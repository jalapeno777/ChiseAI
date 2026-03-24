"""Predefined remediation workflows for common failures.

Provides 10+ predefined workflows for:
- Redis connection recovery
- API timeout remediation
- Circuit breaker reset sequence
- Service restart with health checks
- Database connection recovery
- Memory exhaustion remediation
- And more...

For ST-CONTROL-002: Self-Healing Automation
"""

from __future__ import annotations

import logging

from autonomous_control_plane.automation.runbook_engine import (
    Runbook,
    RunbookEngine,
    RunbookStep,
)
from autonomous_control_plane.models.healing import FailurePatternType

logger = logging.getLogger(__name__)


class RemediationWorkflows:
    """Factory for predefined remediation workflows.

    Provides 10+ predefined workflows for common failure scenarios:
    1. Redis Connection Recovery
    2. API Timeout Remediation
    3. Circuit Breaker Reset Sequence
    4. Service Restart with Health Checks
    5. Database Connection Recovery
    6. Memory Exhaustion Remediation
    7. Disk Space Cleanup
    8. CPU Spike Mitigation
    9. InfluxDB Write Recovery
    10. Dead Letter Queue Processing
    11. Service Health Recovery
    12. Configuration Reload

    Example:
        >>> engine = RunbookEngine()
        >>> workflows = RemediationWorkflows(engine)
        >>> runbook = workflows.create_redis_recovery_runbook()
        >>> execution = await engine.execute_runbook(runbook)
    """

    def __init__(self, engine: RunbookEngine):
        """Initialize workflows factory.

        Args:
            engine: Runbook engine for creating runbooks
        """
        self._engine = engine

    def create_redis_recovery_runbook(self, service_name: str = "redis") -> Runbook:
        """Create Redis connection recovery runbook.

        Steps:
        1. Check Redis connectivity
        2. Flush connection pool
        3. Restart Redis client
        4. Verify connectivity
        5. Run health checks

        Args:
            service_name: Name of the Redis service

        Returns:
            Configured runbook
        """
        runbook = self._engine.create_runbook(
            name="Redis Connection Recovery",
            description=f"Recover Redis connections for {service_name}",
            tags=["redis", "connection", "recovery"],
        )

        # Step 1: Check current status
        runbook.add_step(
            RunbookStep(
                name="Check Redis Status",
                description="Check current Redis connectivity",
                action="check_redis_status",
                action_type="python",
                parameters={"service": service_name},
                timeout_seconds=10,
            )
        )

        # Step 2: Flush connection pool
        runbook.add_step(
            RunbookStep(
                name="Flush Connection Pool",
                description="Flush existing Redis connection pool",
                action="flush_redis_pool",
                action_type="python",
                parameters={"service": service_name},
                timeout_seconds=15,
                rollback_action="restore_redis_pool",
            )
        )

        # Step 3: Restart Redis client
        runbook.add_step(
            RunbookStep(
                name="Restart Redis Client",
                description="Restart Redis client with fresh connections",
                action="restart_redis_client",
                action_type="python",
                parameters={"service": service_name},
                timeout_seconds=30,
                rollback_action="stop_redis_client",
            )
        )

        # Step 4: Verify connectivity
        runbook.add_step(
            RunbookStep(
                name="Verify Connectivity",
                description="Verify Redis connectivity after restart",
                action="verify_redis_connectivity",
                action_type="check",
                parameters={"service": service_name, "type": "redis"},
                timeout_seconds=10,
                depends_on=[runbook.steps[-1].step_id] if runbook.steps else [],
            )
        )

        # Step 5: Health check
        runbook.add_step(
            RunbookStep(
                name="Run Health Checks",
                description="Run comprehensive Redis health checks",
                action="redis_health_check",
                action_type="check",
                parameters={"service": service_name, "type": "redis"},
                timeout_seconds=15,
                depends_on=[runbook.steps[-1].step_id] if runbook.steps else [],
            )
        )

        logger.info(f"Created Redis recovery runbook for {service_name}")
        return runbook

    def create_api_timeout_remediation_runbook(
        self, endpoint: str = "api", service_name: str = "api_service"
    ) -> Runbook:
        """Create API timeout remediation runbook.

        Steps:
        1. Check API endpoint status
        2. Retry with exponential backoff
        3. Clear request cache
        4. Adjust timeout settings
        5. Verify API responsiveness

        Args:
            endpoint: API endpoint name
            service_name: Name of the API service

        Returns:
            Configured runbook
        """
        runbook = self._engine.create_runbook(
            name="API Timeout Remediation",
            description=f"Remediate API timeouts for {endpoint}",
            tags=["api", "timeout", "remediation"],
        )

        # Step 1: Check status
        step1 = runbook.add_step(
            RunbookStep(
                name="Check API Status",
                description=f"Check status of {endpoint}",
                action="check_api_status",
                action_type="api",
                parameters={"endpoint": endpoint, "service": service_name},
                timeout_seconds=10,
            )
        )

        # Step 2: Retry with backoff
        runbook.add_step(
            RunbookStep(
                name="Retry with Backoff",
                description="Retry API calls with exponential backoff",
                action="retry_api_with_backoff",
                action_type="python",
                parameters={
                    "endpoint": endpoint,
                    "service": service_name,
                    "max_retries": 5,
                    "backoff_delays": [1, 2, 5, 10, 30],
                },
                timeout_seconds=60,
                max_retries=2,
                depends_on=[step1.step_id],
            )
        )

        # Step 3: Clear cache
        runbook.add_step(
            RunbookStep(
                name="Clear Request Cache",
                description="Clear stale request cache entries",
                action="clear_api_cache",
                action_type="python",
                parameters={"service": service_name},
                timeout_seconds=10,
            )
        )

        # Step 4: Adjust timeouts
        runbook.add_step(
            RunbookStep(
                name="Adjust Timeout Settings",
                description="Temporarily increase timeout thresholds",
                action="adjust_timeout_settings",
                action_type="python",
                parameters={
                    "service": service_name,
                    "timeout_multiplier": 2.0,
                },
                timeout_seconds=5,
                rollback_action="restore_timeout_settings",
            )
        )

        # Step 5: Verify
        runbook.add_step(
            RunbookStep(
                name="Verify API Responsiveness",
                description="Verify API is responsive",
                action="verify_api_responsive",
                action_type="check",
                parameters={"endpoint": endpoint, "type": "api"},
                timeout_seconds=15,
            )
        )

        logger.info(f"Created API timeout remediation runbook for {endpoint}")
        return runbook

    def create_circuit_breaker_reset_runbook(
        self, circuit_name: str = "default"
    ) -> Runbook:
        """Create circuit breaker reset sequence runbook.

        Steps:
        1. Check circuit breaker state
        2. Analyze failure pattern
        3. Reset circuit breaker
        4. Verify reset
        5. Monitor for stability

        Args:
            circuit_name: Name of the circuit breaker

        Returns:
            Configured runbook
        """
        runbook = self._engine.create_runbook(
            name="Circuit Breaker Reset Sequence",
            description=f"Reset circuit breaker {circuit_name}",
            tags=["circuit_breaker", "reset", "stability"],
        )

        # Step 1: Check state
        step1 = runbook.add_step(
            RunbookStep(
                name="Check Circuit State",
                description=f"Check current state of {circuit_name}",
                action="check_circuit_state",
                action_type="python",
                parameters={"circuit_name": circuit_name},
                timeout_seconds=5,
            )
        )

        # Step 2: Analyze failures
        runbook.add_step(
            RunbookStep(
                name="Analyze Failure Pattern",
                description="Analyze recent failure patterns",
                action="analyze_failure_pattern",
                action_type="python",
                parameters={"circuit_name": circuit_name},
                timeout_seconds=10,
                depends_on=[step1.step_id],
            )
        )

        # Step 3: Reset (requires approval in production)
        runbook.add_step(
            RunbookStep(
                name="Reset Circuit Breaker",
                description=f"Reset {circuit_name} to CLOSED state",
                action="reset_circuit_breaker",
                action_type="python",
                parameters={"circuit_name": circuit_name},
                timeout_seconds=10,
                requires_approval=True,
                rollback_action="restore_circuit_state",
            )
        )

        # Step 4: Verify reset
        runbook.add_step(
            RunbookStep(
                name="Verify Reset",
                description="Verify circuit breaker is CLOSED",
                action="verify_circuit_closed",
                action_type="check",
                parameters={"circuit_name": circuit_name, "type": "circuit_breaker"},
                timeout_seconds=5,
            )
        )

        # Step 5: Monitor
        runbook.add_step(
            RunbookStep(
                name="Monitor Stability",
                description="Monitor circuit breaker for stability",
                action="monitor_circuit_stability",
                action_type="wait",
                parameters={"seconds": 30},
                timeout_seconds=35,
            )
        )

        logger.info(f"Created circuit breaker reset runbook for {circuit_name}")
        return runbook

    def create_service_restart_runbook(
        self, service_name: str, health_check_endpoint: str = "/health"
    ) -> Runbook:
        """Create service restart with health checks runbook.

        Steps:
        1. Pre-restart health check
        2. Graceful service shutdown
        3. Service restart
        4. Wait for startup
        5. Post-restart health check
        6. Verify all endpoints

        Args:
            service_name: Name of the service to restart
            health_check_endpoint: Health check endpoint path

        Returns:
            Configured runbook
        """
        runbook = self._engine.create_runbook(
            name=f"Service Restart: {service_name}",
            description=f"Restart {service_name} with health checks",
            tags=["service", "restart", "health_check"],
        )

        # Step 1: Pre-restart check
        step1 = runbook.add_step(
            RunbookStep(
                name="Pre-Restart Health Check",
                description=f"Check {service_name} health before restart",
                action="health_check",
                action_type="check",
                parameters={
                    "service": service_name,
                    "endpoint": health_check_endpoint,
                    "type": "service",
                },
                timeout_seconds=15,
            )
        )

        # Step 2: Graceful shutdown (requires approval in production)
        step2 = runbook.add_step(
            RunbookStep(
                name="Graceful Shutdown",
                description=f"Gracefully shutdown {service_name}",
                action="graceful_shutdown",
                action_type="shell",
                parameters={"service": service_name},
                timeout_seconds=30,
                requires_approval=True,
                rollback_action="start_service",
                depends_on=[step1.step_id],
            )
        )

        # Step 3: Wait for shutdown
        runbook.add_step(
            RunbookStep(
                name="Wait for Shutdown",
                description="Wait for service to fully shutdown",
                action="wait_shutdown",
                action_type="wait",
                parameters={"seconds": 10},
                timeout_seconds=15,
                depends_on=[step2.step_id],
            )
        )

        # Step 4: Restart service
        step4 = runbook.add_step(
            RunbookStep(
                name="Restart Service",
                description=f"Restart {service_name}",
                action="restart_service",
                action_type="shell",
                parameters={"service": service_name},
                timeout_seconds=60,
                depends_on=[step2.step_id],
            )
        )

        # Step 5: Wait for startup
        runbook.add_step(
            RunbookStep(
                name="Wait for Startup",
                description="Wait for service to start",
                action="wait_startup",
                action_type="wait",
                parameters={"seconds": 15},
                timeout_seconds=20,
                depends_on=[step4.step_id],
            )
        )

        # Step 6: Post-restart health check
        runbook.add_step(
            RunbookStep(
                name="Post-Restart Health Check",
                description=f"Verify {service_name} is healthy",
                action="health_check",
                action_type="check",
                parameters={
                    "service": service_name,
                    "endpoint": health_check_endpoint,
                    "type": "service",
                },
                timeout_seconds=30,
            )
        )

        # Step 7: Verify endpoints
        runbook.add_step(
            RunbookStep(
                name="Verify All Endpoints",
                description="Verify all service endpoints are accessible",
                action="verify_endpoints",
                action_type="api",
                parameters={"service": service_name},
                timeout_seconds=20,
            )
        )

        logger.info(f"Created service restart runbook for {service_name}")
        return runbook

    def create_database_recovery_runbook(
        self, db_name: str = "postgres", service_name: str = "database"
    ) -> Runbook:
        """Create database connection recovery runbook.

        Steps:
        1. Check database connectivity
        2. Analyze connection pool
        3. Reset connection pool
        4. Verify connectivity
        5. Run database health checks

        Args:
            db_name: Database name
            service_name: Database service name

        Returns:
            Configured runbook
        """
        runbook = self._engine.create_runbook(
            name="Database Connection Recovery",
            description=f"Recover database connections for {db_name}",
            tags=["database", "connection", "recovery"],
        )

        # Step 1: Check connectivity
        step1 = runbook.add_step(
            RunbookStep(
                name="Check Database Connectivity",
                description=f"Check connectivity to {db_name}",
                action="check_db_connectivity",
                action_type="python",
                parameters={"db_name": db_name},
                timeout_seconds=10,
            )
        )

        # Step 2: Analyze pool
        runbook.add_step(
            RunbookStep(
                name="Analyze Connection Pool",
                description="Analyze connection pool status",
                action="analyze_connection_pool",
                action_type="python",
                parameters={"service": service_name},
                timeout_seconds=10,
                depends_on=[step1.step_id],
            )
        )

        # Step 3: Reset pool
        runbook.add_step(
            RunbookStep(
                name="Reset Connection Pool",
                description="Reset database connection pool",
                action="reset_connection_pool",
                action_type="python",
                parameters={"service": service_name},
                timeout_seconds=20,
                rollback_action="restore_pool_settings",
            )
        )

        # Step 4: Verify
        runbook.add_step(
            RunbookStep(
                name="Verify Connectivity",
                description="Verify database connectivity after reset",
                action="verify_db_connectivity",
                action_type="check",
                parameters={"db_name": db_name, "type": "database"},
                timeout_seconds=10,
            )
        )

        # Step 5: Health check
        runbook.add_step(
            RunbookStep(
                name="Run Database Health Checks",
                description="Run comprehensive database health checks",
                action="db_health_check",
                action_type="check",
                parameters={"db_name": db_name, "type": "database"},
                timeout_seconds=15,
            )
        )

        logger.info(f"Created database recovery runbook for {db_name}")
        return runbook

    def create_memory_exhaustion_runbook(self, service_name: str = "app") -> Runbook:
        """Create memory exhaustion remediation runbook.

        Steps:
        1. Analyze memory usage
        2. Clear caches
        3. Trigger garbage collection
        4. Restart if necessary
        5. Monitor memory

        Args:
            service_name: Service experiencing memory issues

        Returns:
            Configured runbook
        """
        runbook = self._engine.create_runbook(
            name="Memory Exhaustion Remediation",
            description=f"Remediate memory exhaustion for {service_name}",
            tags=["memory", "exhaustion", "remediation"],
        )

        # Step 1: Analyze memory
        step1 = runbook.add_step(
            RunbookStep(
                name="Analyze Memory Usage",
                description=f"Analyze memory usage for {service_name}",
                action="analyze_memory_usage",
                action_type="python",
                parameters={"service": service_name},
                timeout_seconds=10,
            )
        )

        # Step 2: Clear caches
        runbook.add_step(
            RunbookStep(
                name="Clear Caches",
                description="Clear application caches",
                action="clear_caches",
                action_type="python",
                parameters={"service": service_name},
                timeout_seconds=15,
            )
        )

        # Step 3: Garbage collection
        runbook.add_step(
            RunbookStep(
                name="Trigger Garbage Collection",
                description="Trigger garbage collection",
                action="trigger_gc",
                action_type="python",
                parameters={"service": service_name},
                timeout_seconds=30,
            )
        )

        # Step 4: Check if restart needed
        runbook.add_step(
            RunbookStep(
                name="Evaluate Memory Status",
                description="Check if memory usage is acceptable",
                action="evaluate_memory",
                action_type="check",
                parameters={"service": service_name, "type": "memory"},
                timeout_seconds=10,
                condition="context.memory_critical",
            )
        )

        # Step 5: Restart if critical (conditional)
        runbook.add_step(
            RunbookStep(
                name="Restart Service",
                description=f"Restart {service_name} to free memory",
                action="restart_service",
                action_type="shell",
                parameters={"service": service_name},
                timeout_seconds=60,
                requires_approval=True,
                condition="context.memory_critical",
            )
        )

        # Step 6: Monitor
        runbook.add_step(
            RunbookStep(
                name="Monitor Memory",
                description="Monitor memory usage post-remediation",
                action="monitor_memory",
                action_type="wait",
                parameters={"seconds": 60},
                timeout_seconds=65,
            )
        )

        logger.info(f"Created memory exhaustion runbook for {service_name}")
        return runbook

    def create_disk_space_cleanup_runbook(
        self, service_name: str = "system"
    ) -> Runbook:
        """Create disk space cleanup runbook.

        Steps:
        1. Analyze disk usage
        2. Clean temporary files
        3. Rotate logs
        4. Clean old artifacts
        5. Verify space freed

        Args:
            service_name: Service with disk space issues

        Returns:
            Configured runbook
        """
        runbook = self._engine.create_runbook(
            name="Disk Space Cleanup",
            description=f"Clean up disk space for {service_name}",
            tags=["disk", "cleanup", "space"],
        )

        # Step 1: Analyze
        step1 = runbook.add_step(
            RunbookStep(
                name="Analyze Disk Usage",
                description="Analyze disk usage patterns",
                action="analyze_disk_usage",
                action_type="shell",
                parameters={"service": service_name},
                timeout_seconds=15,
            )
        )

        # Step 2: Clean temp files
        runbook.add_step(
            RunbookStep(
                name="Clean Temporary Files",
                description="Remove temporary files",
                action="clean_temp_files",
                action_type="shell",
                parameters={"service": service_name},
                timeout_seconds=30,
            )
        )

        # Step 3: Rotate logs
        runbook.add_step(
            RunbookStep(
                name="Rotate Logs",
                description="Rotate and compress old logs",
                action="rotate_logs",
                action_type="shell",
                parameters={"service": service_name},
                timeout_seconds=30,
            )
        )

        # Step 4: Clean artifacts
        runbook.add_step(
            RunbookStep(
                name="Clean Old Artifacts",
                description="Remove old build artifacts",
                action="clean_artifacts",
                action_type="shell",
                parameters={"service": service_name},
                timeout_seconds=30,
            )
        )

        # Step 5: Verify
        runbook.add_step(
            RunbookStep(
                name="Verify Space Freed",
                description="Verify sufficient disk space is available",
                action="verify_disk_space",
                action_type="check",
                parameters={"service": service_name, "type": "disk"},
                timeout_seconds=10,
            )
        )

        logger.info(f"Created disk space cleanup runbook for {service_name}")
        return runbook

    def create_cpu_spike_mitigation_runbook(self, service_name: str = "app") -> Runbook:
        """Create CPU spike mitigation runbook.

        Steps:
        1. Analyze CPU usage
        2. Identify high CPU processes
        3. Throttle if possible
        4. Restart if necessary
        5. Monitor CPU

        Args:
            service_name: Service experiencing CPU spikes

        Returns:
            Configured runbook
        """
        runbook = self._engine.create_runbook(
            name="CPU Spike Mitigation",
            description=f"Mitigate CPU spikes for {service_name}",
            tags=["cpu", "spike", "mitigation"],
        )

        # Step 1: Analyze
        step1 = runbook.add_step(
            RunbookStep(
                name="Analyze CPU Usage",
                description="Analyze CPU usage patterns",
                action="analyze_cpu_usage",
                action_type="python",
                parameters={"service": service_name},
                timeout_seconds=10,
            )
        )

        # Step 2: Identify processes
        runbook.add_step(
            RunbookStep(
                name="Identify High CPU Processes",
                description="Identify processes consuming high CPU",
                action="identify_high_cpu_processes",
                action_type="shell",
                parameters={"service": service_name},
                timeout_seconds=10,
                depends_on=[step1.step_id],
            )
        )

        # Step 3: Throttle
        runbook.add_step(
            RunbookStep(
                name="Throttle Processes",
                description="Throttle non-critical processes",
                action="throttle_processes",
                action_type="shell",
                parameters={"service": service_name},
                timeout_seconds=15,
            )
        )

        # Step 4: Restart if needed
        runbook.add_step(
            RunbookStep(
                name="Restart Service",
                description=f"Restart {service_name} if CPU still high",
                action="restart_service",
                action_type="shell",
                parameters={"service": service_name},
                timeout_seconds=60,
                requires_approval=True,
                condition="context.cpu_critical",
            )
        )

        # Step 5: Monitor
        runbook.add_step(
            RunbookStep(
                name="Monitor CPU",
                description="Monitor CPU usage post-mitigation",
                action="monitor_cpu",
                action_type="wait",
                parameters={"seconds": 60},
                timeout_seconds=65,
            )
        )

        logger.info(f"Created CPU spike mitigation runbook for {service_name}")
        return runbook

    def create_influxdb_recovery_runbook(
        self, service_name: str = "influxdb"
    ) -> Runbook:
        """Create InfluxDB write recovery runbook.

        Steps:
        1. Check InfluxDB status
        2. Analyze write queue
        3. Flush write buffer
        4. Retry failed writes
        5. Verify writes succeeding

        Args:
            service_name: InfluxDB service name

        Returns:
            Configured runbook
        """
        runbook = self._engine.create_runbook(
            name="InfluxDB Write Recovery",
            description=f"Recover InfluxDB writes for {service_name}",
            tags=["influxdb", "write", "recovery"],
        )

        # Step 1: Check status
        step1 = runbook.add_step(
            RunbookStep(
                name="Check InfluxDB Status",
                description="Check InfluxDB service status",
                action="check_influxdb_status",
                action_type="api",
                parameters={"service": service_name},
                timeout_seconds=10,
            )
        )

        # Step 2: Analyze queue
        runbook.add_step(
            RunbookStep(
                name="Analyze Write Queue",
                description="Analyze write queue status",
                action="analyze_write_queue",
                action_type="python",
                parameters={"service": service_name},
                timeout_seconds=10,
                depends_on=[step1.step_id],
            )
        )

        # Step 3: Flush buffer
        runbook.add_step(
            RunbookStep(
                name="Flush Write Buffer",
                description="Flush pending write buffer",
                action="flush_write_buffer",
                action_type="python",
                parameters={"service": service_name},
                timeout_seconds=15,
            )
        )

        # Step 4: Retry writes
        runbook.add_step(
            RunbookStep(
                name="Retry Failed Writes",
                description="Retry failed write operations",
                action="retry_failed_writes",
                action_type="python",
                parameters={"service": service_name},
                timeout_seconds=30,
            )
        )

        # Step 5: Verify
        runbook.add_step(
            RunbookStep(
                name="Verify Writes Succeeding",
                description="Verify write operations are succeeding",
                action="verify_writes",
                action_type="check",
                parameters={"service": service_name, "type": "influxdb"},
                timeout_seconds=15,
            )
        )

        logger.info(f"Created InfluxDB recovery runbook for {service_name}")
        return runbook

    def create_dead_letter_queue_runbook(self, queue_name: str = "dlq") -> Runbook:
        """Create dead letter queue processing runbook.

        Steps:
        1. Analyze DLQ contents
        2. Categorize messages
        3. Retry retryable messages
        4. Archive failed messages
        5. Monitor DLQ

        Args:
            queue_name: Dead letter queue name

        Returns:
            Configured runbook
        """
        runbook = self._engine.create_runbook(
            name="Dead Letter Queue Processing",
            description=f"Process dead letter queue {queue_name}",
            tags=["dlq", "queue", "processing"],
        )

        # Step 1: Analyze
        step1 = runbook.add_step(
            RunbookStep(
                name="Analyze DLQ Contents",
                description="Analyze dead letter queue contents",
                action="analyze_dlq",
                action_type="python",
                parameters={"queue_name": queue_name},
                timeout_seconds=15,
            )
        )

        # Step 2: Categorize
        runbook.add_step(
            RunbookStep(
                name="Categorize Messages",
                description="Categorize messages by failure type",
                action="categorize_messages",
                action_type="python",
                parameters={"queue_name": queue_name},
                timeout_seconds=15,
                depends_on=[step1.step_id],
            )
        )

        # Step 3: Retry
        runbook.add_step(
            RunbookStep(
                name="Retry Retryable Messages",
                description="Retry messages that can be retried",
                action="retry_messages",
                action_type="python",
                parameters={"queue_name": queue_name},
                timeout_seconds=60,
            )
        )

        # Step 4: Archive
        runbook.add_step(
            RunbookStep(
                name="Archive Failed Messages",
                description="Archive permanently failed messages",
                action="archive_messages",
                action_type="python",
                parameters={"queue_name": queue_name},
                timeout_seconds=30,
            )
        )

        # Step 5: Monitor
        runbook.add_step(
            RunbookStep(
                name="Monitor DLQ",
                description="Monitor dead letter queue status",
                action="monitor_dlq",
                action_type="wait",
                parameters={"seconds": 30},
                timeout_seconds=35,
            )
        )

        logger.info(f"Created DLQ processing runbook for {queue_name}")
        return runbook

    def create_service_health_recovery_runbook(self, service_name: str) -> Runbook:
        """Create service health recovery runbook.

        Steps:
        1. Comprehensive health check
        2. Identify unhealthy components
        3. Restart unhealthy components
        4. Verify health restored
        5. Continuous monitoring

        Args:
            service_name: Service to recover

        Returns:
            Configured runbook
        """
        runbook = self._engine.create_runbook(
            name=f"Service Health Recovery: {service_name}",
            description=f"Recover health for {service_name}",
            tags=["service", "health", "recovery"],
        )

        # Step 1: Health check
        step1 = runbook.add_step(
            RunbookStep(
                name="Comprehensive Health Check",
                description=f"Run comprehensive health check on {service_name}",
                action="comprehensive_health_check",
                action_type="check",
                parameters={"service": service_name, "type": "service"},
                timeout_seconds=20,
            )
        )

        # Step 2: Identify issues
        runbook.add_step(
            RunbookStep(
                name="Identify Unhealthy Components",
                description="Identify unhealthy service components",
                action="identify_unhealthy_components",
                action_type="python",
                parameters={"service": service_name},
                timeout_seconds=15,
                depends_on=[step1.step_id],
            )
        )

        # Step 3: Restart components
        runbook.add_step(
            RunbookStep(
                name="Restart Unhealthy Components",
                description="Restart unhealthy service components",
                action="restart_unhealthy_components",
                action_type="shell",
                parameters={"service": service_name},
                timeout_seconds=60,
                requires_approval=True,
            )
        )

        # Step 4: Verify
        runbook.add_step(
            RunbookStep(
                name="Verify Health Restored",
                description="Verify service health is restored",
                action="verify_health_restored",
                action_type="check",
                parameters={"service": service_name, "type": "service"},
                timeout_seconds=20,
            )
        )

        # Step 5: Monitor
        runbook.add_step(
            RunbookStep(
                name="Continuous Monitoring",
                description="Enable continuous health monitoring",
                action="enable_monitoring",
                action_type="python",
                parameters={"service": service_name},
                timeout_seconds=10,
            )
        )

        logger.info(f"Created service health recovery runbook for {service_name}")
        return runbook

    def create_configuration_reload_runbook(self, service_name: str) -> Runbook:
        """Create configuration reload runbook.

        Steps:
        1. Validate new configuration
        2. Backup current configuration
        3. Apply new configuration
        4. Verify configuration applied
        5. Rollback if issues detected

        Args:
            service_name: Service to reload configuration for

        Returns:
            Configured runbook
        """
        runbook = self._engine.create_runbook(
            name=f"Configuration Reload: {service_name}",
            description=f"Reload configuration for {service_name}",
            tags=["config", "reload", "validation"],
        )

        # Step 1: Validate
        step1 = runbook.add_step(
            RunbookStep(
                name="Validate New Configuration",
                description="Validate new configuration before applying",
                action="validate_config",
                action_type="python",
                parameters={"service": service_name},
                timeout_seconds=15,
            )
        )

        # Step 2: Backup
        runbook.add_step(
            RunbookStep(
                name="Backup Current Configuration",
                description="Backup current configuration",
                action="backup_config",
                action_type="shell",
                parameters={"service": service_name},
                timeout_seconds=10,
                depends_on=[step1.step_id],
            )
        )

        # Step 3: Apply
        step3 = runbook.add_step(
            RunbookStep(
                name="Apply New Configuration",
                description="Apply new configuration",
                action="apply_config",
                action_type="shell",
                parameters={"service": service_name},
                timeout_seconds=20,
                requires_approval=True,
                rollback_action="restore_config_backup",
            )
        )

        # Step 4: Verify
        runbook.add_step(
            RunbookStep(
                name="Verify Configuration Applied",
                description="Verify configuration was applied successfully",
                action="verify_config_applied",
                action_type="check",
                parameters={"service": service_name, "type": "config"},
                timeout_seconds=15,
                depends_on=[step3.step_id],
            )
        )

        # Step 5: Health check
        runbook.add_step(
            RunbookStep(
                name="Post-Config Health Check",
                description="Run health check after configuration change",
                action="health_check",
                action_type="check",
                parameters={"service": service_name, "type": "service"},
                timeout_seconds=20,
            )
        )

        logger.info(f"Created configuration reload runbook for {service_name}")
        return runbook

    def get_all_workflow_templates(self) -> dict[str, callable]:
        """Get all workflow template creators.

        Returns:
            Dictionary mapping workflow names to creator functions
        """
        return {
            "redis_recovery": self.create_redis_recovery_runbook,
            "api_timeout_remediation": self.create_api_timeout_remediation_runbook,
            "circuit_breaker_reset": self.create_circuit_breaker_reset_runbook,
            "service_restart": self.create_service_restart_runbook,
            "database_recovery": self.create_database_recovery_runbook,
            "memory_exhaustion": self.create_memory_exhaustion_runbook,
            "disk_space_cleanup": self.create_disk_space_cleanup_runbook,
            "cpu_spike_mitigation": self.create_cpu_spike_mitigation_runbook,
            "influxdb_recovery": self.create_influxdb_recovery_runbook,
            "dead_letter_queue": self.create_dead_letter_queue_runbook,
            "service_health_recovery": self.create_service_health_recovery_runbook,
            "configuration_reload": self.create_configuration_reload_runbook,
        }

    def create_workflow_for_pattern(
        self, pattern_type: FailurePatternType, **kwargs
    ) -> Runbook | None:
        """Create appropriate workflow for a failure pattern.

        Args:
            pattern_type: Type of failure pattern
            **kwargs: Additional arguments for workflow creation

        Returns:
            Configured runbook or None if no workflow available
        """
        mapping = {
            FailurePatternType.REDIS_DISCONNECT: self.create_redis_recovery_runbook,
            FailurePatternType.API_TIMEOUT: self.create_api_timeout_remediation_runbook,
            FailurePatternType.CIRCUIT_BREAKER_OPEN: self.create_circuit_breaker_reset_runbook,
            FailurePatternType.DATABASE_CONNECTION: self.create_database_recovery_runbook,
            FailurePatternType.MEMORY_EXHAUSTION: self.create_memory_exhaustion_runbook,
            FailurePatternType.DISK_SPACE: self.create_disk_space_cleanup_runbook,
            FailurePatternType.CPU_SPIKE: self.create_cpu_spike_mitigation_runbook,
            FailurePatternType.INFLUXDB_WRITE: self.create_influxdb_recovery_runbook,
            FailurePatternType.DEAD_LETTER_QUEUE: self.create_dead_letter_queue_runbook,
            FailurePatternType.SERVICE_UNHEALTHY: self.create_service_health_recovery_runbook,
        }

        creator = mapping.get(pattern_type)
        if creator:
            return creator(**kwargs)

        logger.warning(f"No workflow available for pattern {pattern_type.value}")
        return None
