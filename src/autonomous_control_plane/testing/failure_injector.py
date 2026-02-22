"""Synthetic failure injection for testing auto-healing.

Provides controlled failure scenarios to validate:
- Pattern matching accuracy
- Healing action execution
- Incident creation
- Rollback behavior

For testing purposes only - DO NOT USE IN PRODUCTION.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Callable

from src.autonomous_control_plane.models.healing import FailurePatternType, LogEntry

logger = logging.getLogger(__name__)


class FailureScenario(StrEnum):
    """Available failure scenarios."""

    REDIS_DISCONNECT = "redis_disconnect"
    API_TIMEOUT = "api_timeout"
    CIRCUIT_BREAKER_OPEN = "circuit_breaker_open"
    DATABASE_CONNECTION = "database_connection"
    MEMORY_EXHAUSTION = "memory_exhaustion"
    DISK_SPACE = "disk_space"
    CPU_SPIKE = "cpu_spike"
    INFLUXDB_WRITE = "influxdb_write"
    SERVICE_UNHEALTHY = "service_unhealthy"


@dataclass
class InjectedFailure:
    """Record of an injected failure."""

    failure_id: str
    scenario: FailureScenario
    timestamp: datetime
    service: str
    message: str
    expected_pattern: FailurePatternType
    log_entry: LogEntry


class FailureInjector:
    """Injects synthetic failures for testing auto-healing.

    Example:
        >>> injector = FailureInjector(healing_engine)
        >>> failure = await injector.inject_redis_disconnect()
        >>> # Wait for healing to trigger
        >>> result = await injector.wait_for_healing(failure, timeout=30)
        >>> assert result.healing_triggered
    """

    def __init__(self, healing_engine, incident_manager=None):
        """Initialize failure injector.

        Args:
            healing_engine: SelfHealingEngine instance
            incident_manager: Optional IncidentManager for validation
        """
        self._healing_engine = healing_engine
        self._incident_manager = incident_manager
        self._injected_failures: list[InjectedFailure] = []
        self._healing_callbacks: list[Callable] = []
        self._failure_counter = 0

    async def inject_failure(
        self,
        scenario: FailureScenario,
        service: str = "test_service",
        delay_seconds: float = 0.0,
    ) -> InjectedFailure:
        """Inject a synthetic failure.

        Args:
            scenario: Type of failure to inject
            service: Service name to attribute failure to
            delay_seconds: Delay before injection

        Returns:
            InjectedFailure record
        """
        if delay_seconds > 0:
            await asyncio.sleep(delay_seconds)

        self._failure_counter += 1
        failure_id = f"injected_{scenario.value}_{self._failure_counter}"

        # Generate appropriate log message for scenario
        message = self._generate_failure_message(scenario, service)
        expected_pattern = self._get_expected_pattern(scenario)

        log_entry = LogEntry(
            timestamp=datetime.utcnow(),
            level="ERROR",
            source=service,
            message=message,
            metadata={"injected": True, "failure_id": failure_id},
        )

        injected = InjectedFailure(
            failure_id=failure_id,
            scenario=scenario,
            timestamp=datetime.utcnow(),
            service=service,
            message=message,
            expected_pattern=expected_pattern,
            log_entry=log_entry,
        )

        self._injected_failures.append(injected)

        # Send to healing engine
        result = await self._healing_engine.process_log_entry(log_entry)

        logger.info(f"Injected failure {failure_id}: {scenario.value}")
        if result:
            logger.info(f"Healing triggered: {result.action_type}")

        return injected

    async def inject_redis_disconnect(
        self, service: str = "test_service"
    ) -> InjectedFailure:
        """Inject Redis disconnect failure."""
        return await self.inject_failure(FailureScenario.REDIS_DISCONNECT, service)

    async def inject_api_timeout(
        self, service: str = "test_service"
    ) -> InjectedFailure:
        """Inject API timeout failure."""
        return await self.inject_failure(FailureScenario.API_TIMEOUT, service)

    async def inject_circuit_breaker_open(
        self, service: str = "test_service"
    ) -> InjectedFailure:
        """Inject circuit breaker open failure."""
        return await self.inject_failure(FailureScenario.CIRCUIT_BREAKER_OPEN, service)

    async def inject_database_connection_failure(
        self, service: str = "test_service"
    ) -> InjectedFailure:
        """Inject database connection failure."""
        return await self.inject_failure(FailureScenario.DATABASE_CONNECTION, service)

    def _generate_failure_message(self, scenario: FailureScenario, service: str) -> str:
        """Generate realistic failure message for scenario."""
        messages = {
            FailureScenario.REDIS_DISCONNECT: "Redis connection error: Connection refused to redis://localhost:6379",
            FailureScenario.API_TIMEOUT: "API timeout after 30s: POST /api/v1/orders",
            FailureScenario.CIRCUIT_BREAKER_OPEN: "Circuit breaker 'order_service' is OPEN after 5 failures",
            FailureScenario.DATABASE_CONNECTION: "Database connection failed: could not connect to postgres://db:5432",
            FailureScenario.MEMORY_EXHAUSTION: "Memory usage critical: 95% of 8GB limit exceeded",
            FailureScenario.DISK_SPACE: "Disk space low: 98% of 100GB used",
            FailureScenario.CPU_SPIKE: "CPU usage spike: 95% sustained for 60s",
            FailureScenario.INFLUXDB_WRITE: "InfluxDB write failed: rate limit exceeded",
            FailureScenario.SERVICE_UNHEALTHY: f"Health check failed for service '{service}'",
        }
        return messages.get(scenario, f"Unknown failure: {scenario.value}")

    def _get_expected_pattern(self, scenario: FailureScenario) -> FailurePatternType:
        """Get expected pattern type for scenario."""
        mapping = {
            FailureScenario.REDIS_DISCONNECT: FailurePatternType.REDIS_DISCONNECT,
            FailureScenario.API_TIMEOUT: FailurePatternType.API_TIMEOUT,
            FailureScenario.CIRCUIT_BREAKER_OPEN: FailurePatternType.CIRCUIT_BREAKER_OPEN,
            FailureScenario.DATABASE_CONNECTION: FailurePatternType.DATABASE_CONNECTION,
            FailureScenario.MEMORY_EXHAUSTION: FailurePatternType.MEMORY_EXHAUSTION,
            FailureScenario.DISK_SPACE: FailurePatternType.DISK_SPACE,
            FailureScenario.CPU_SPIKE: FailurePatternType.CPU_SPIKE,
            FailureScenario.INFLUXDB_WRITE: FailurePatternType.INFLUXDB_WRITE,
            FailureScenario.SERVICE_UNHEALTHY: FailurePatternType.SERVICE_UNHEALTHY,
        }
        return mapping.get(scenario, FailurePatternType.SERVICE_UNHEALTHY)

    async def wait_for_healing(
        self,
        failure: InjectedFailure,
        timeout_seconds: float = 30.0,
    ) -> dict[str, Any]:
        """Wait for healing to complete for injected failure.

        Args:
            failure: Injected failure to wait for
            timeout_seconds: Max time to wait

        Returns:
            Dict with healing results
        """
        start = datetime.utcnow()

        while (datetime.utcnow() - start).total_seconds() < timeout_seconds:
            # Check if healing was triggered by looking at engine history
            history = self._healing_engine.get_healing_history(
                service=failure.service,
                limit=10,
            )

            for attempt in history:
                # Check if this attempt matches our injected failure
                if attempt.started_at >= failure.timestamp:
                    return {
                        "healing_triggered": True,
                        "attempt_id": attempt.attempt_id,
                        "action_type": attempt.action_type,
                        "status": attempt.status.value,
                        "wait_time_seconds": (
                            datetime.utcnow() - start
                        ).total_seconds(),
                    }

            await asyncio.sleep(0.5)

        return {
            "healing_triggered": False,
            "timeout": True,
            "wait_time_seconds": timeout_seconds,
        }

    def get_injection_stats(self) -> dict[str, Any]:
        """Get statistics on injected failures."""
        return {
            "total_injected": len(self._injected_failures),
            "by_scenario": {},
            "recent_injections": [
                {
                    "failure_id": f.failure_id,
                    "scenario": f.scenario.value,
                    "timestamp": f.timestamp.isoformat(),
                }
                for f in self._injected_failures[-10:]
            ],
        }


class FailureInjectionSuite:
    """Pre-built failure injection scenarios for testing."""

    def __init__(self, injector: FailureInjector):
        self.injector = injector

    async def run_connectivity_test(self) -> list[InjectedFailure]:
        """Test all connectivity-related failures."""
        scenarios = [
            FailureScenario.REDIS_DISCONNECT,
            FailureScenario.DATABASE_CONNECTION,
            FailureScenario.API_TIMEOUT,
        ]

        results = []
        for scenario in scenarios:
            failure = await self.injector.inject_failure(scenario)
            results.append(failure)
            await asyncio.sleep(1)  # Brief delay between injections

        return results

    async def run_resource_exhaustion_test(self) -> list[InjectedFailure]:
        """Test resource exhaustion failures."""
        scenarios = [
            FailureScenario.MEMORY_EXHAUSTION,
            FailureScenario.DISK_SPACE,
            FailureScenario.CPU_SPIKE,
        ]

        results = []
        for scenario in scenarios:
            failure = await self.injector.inject_failure(scenario)
            results.append(failure)
            await asyncio.sleep(1)

        return results
