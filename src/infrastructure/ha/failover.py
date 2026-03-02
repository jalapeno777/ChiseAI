"""Failover Manager for High Availability Infrastructure (NFR-006)."""

import asyncio
import contextlib
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from src.infrastructure.ha.health_check import HealthStatus

logger = logging.getLogger(__name__)


class FailoverState(Enum):
    PRIMARY_ACTIVE = "primary_active"
    FAILOVER_IN_PROGRESS = "failover_in_progress"
    SECONDARY_ACTIVE = "secondary_active"
    UNAVAILABLE = "unavailable"


@dataclass
class InstanceInfo:
    id: str
    host: str
    port: int
    priority: int = 0
    weight: int = 100
    is_primary: bool = False
    is_active: bool = False
    last_check: datetime | None = None
    health_status: HealthStatus = HealthStatus.UNKNOWN
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "host": self.host,
            "port": self.port,
            "priority": self.priority,
            "weight": self.weight,
            "is_primary": self.is_primary,
            "is_active": self.is_active,
            "last_check": self.last_check.isoformat() if self.last_check else None,
            "health_status": self.health_status.value,
            "metadata": self.metadata,
        }


@dataclass
class FailoverConfig:
    health_check_interval_seconds: float = 10.0
    failure_threshold: int = 3
    recovery_threshold: int = 2
    failover_timeout_seconds: float = 30.0
    auto_failback: bool = True
    failback_delay_seconds: float = 60.0
    cooldown_seconds: float = 30.0


class FailoverManager:
    def __init__(self, config: FailoverConfig | None = None):
        self.config = config or FailoverConfig()
        self._instances: dict[str, InstanceInfo] = {}
        self._state = FailoverState.UNAVAILABLE
        self._active_instance_id: str | None = None
        self._consecutive_failures: dict[str, int] = {}
        self._consecutive_successes: dict[str, int] = {}
        self._last_failover_time: datetime | None = None
        self._failover_count = 0
        self._callbacks: list[Callable[[str, str], None]] = []
        self._running = False
        self._monitor_task: asyncio.Task | None = None

    @property
    def state(self) -> FailoverState:
        return self._state

    @property
    def active_instance(self) -> InstanceInfo | None:
        return (
            self._instances.get(self._active_instance_id)
            if self._active_instance_id
            else None
        )

    def register_instance(self, instance: InstanceInfo) -> None:
        self._instances[instance.id] = instance
        self._consecutive_failures[instance.id] = 0
        self._consecutive_successes[instance.id] = 0
        logger.info(f"Registered instance: {instance.id}")
        # Activate primary if it's the first or only primary
        if instance.is_primary and (
            len(self._instances) == 1 or self._state == FailoverState.UNAVAILABLE
        ):
            self._activate_instance(instance.id)

    def unregister_instance(self, instance_id: str) -> bool:
        if instance_id in self._instances:
            was_active = self._active_instance_id == instance_id
            del self._instances[instance_id]
            del self._consecutive_failures[instance_id]
            del self._consecutive_successes[instance_id]
            if was_active:
                self._active_instance_id = None
                self._state = FailoverState.UNAVAILABLE
            return True
        return False

    def update_instance_health(
        self, instance_id: str, status: HealthStatus
    ) -> FailoverState | None:
        if instance_id not in self._instances:
            return None
        instance = self._instances[instance_id]
        instance.health_status = status
        instance.last_check = datetime.now(UTC)

        if status == HealthStatus.UNHEALTHY:
            self._consecutive_failures[instance_id] += 1
            self._consecutive_successes[instance_id] = 0
        elif status == HealthStatus.HEALTHY:
            self._consecutive_successes[instance_id] += 1
            self._consecutive_failures[instance_id] = 0

        # Check for failover
        if self._active_instance_id == instance_id and self._should_failover(
            instance_id
        ):
            self._perform_failover()

        # Check for failback
        if self.config.auto_failback and self._state == FailoverState.SECONDARY_ACTIVE:
            primary = self._get_primary_instance()
            if primary and self._should_failback(primary.id):
                self._perform_failback()

        return self._state

    def _should_failover(self, instance_id: str) -> bool:
        if self._last_failover_time:
            elapsed = (datetime.now(UTC) - self._last_failover_time).total_seconds()
            if elapsed < self.config.cooldown_seconds:
                return False
        return (
            self._consecutive_failures.get(instance_id, 0)
            >= self.config.failure_threshold
        )

    def _should_failback(self, instance_id: str) -> bool:
        if not self._last_failover_time:
            return False
        elapsed = (datetime.now(UTC) - self._last_failover_time).total_seconds()
        if elapsed < self.config.failback_delay_seconds:
            return False
        return (
            self._consecutive_successes.get(instance_id, 0)
            >= self.config.recovery_threshold
        )

    def _perform_failover(self) -> bool:
        logger.warning("Initiating failover...")
        backup = self._get_best_backup_instance()
        if not backup:
            logger.error("No healthy backup available")
            self._state = FailoverState.UNAVAILABLE
            self._notify_callbacks("failover_failed", "no_backup")
            return False

        self._state = FailoverState.FAILOVER_IN_PROGRESS
        self._notify_callbacks("failover_start", backup.id)

        if self._active_instance_id and self._active_instance_id in self._instances:
            self._instances[self._active_instance_id].is_active = False

        self._activate_instance(backup.id)
        self._state = FailoverState.SECONDARY_ACTIVE
        self._last_failover_time = datetime.now(UTC)
        self._failover_count += 1
        self._notify_callbacks("failover_complete", backup.id)
        logger.warning(f"Failover complete: now using {backup.id}")
        return True

    def _perform_failback(self) -> bool:
        primary = self._get_primary_instance()
        if not primary or primary.health_status != HealthStatus.HEALTHY:
            return False

        logger.info("Initiating failback to primary...")
        self._notify_callbacks("failback_start", primary.id)

        if self._active_instance_id and self._active_instance_id in self._instances:
            self._instances[self._active_instance_id].is_active = False

        self._activate_instance(primary.id)
        self._state = FailoverState.PRIMARY_ACTIVE
        self._notify_callbacks("failback_complete", primary.id)
        logger.info(f"Failback complete: now using primary {primary.id}")
        return True

    def _activate_instance(self, instance_id: str) -> None:
        instance = self._instances.get(instance_id)
        if instance:
            instance.is_active = True
            self._active_instance_id = instance_id
            if instance.is_primary:
                self._state = FailoverState.PRIMARY_ACTIVE
            logger.info(f"Activated instance: {instance_id}")

    def _get_primary_instance(self) -> InstanceInfo | None:
        for inst in self._instances.values():
            if inst.is_primary:
                return inst
        return None

    def _get_best_backup_instance(self) -> InstanceInfo | None:
        candidates = [
            i
            for i in self._instances.values()
            if not i.is_primary and i.health_status == HealthStatus.HEALTHY
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda x: (x.priority, -x.weight))

    def add_callback(self, callback: Callable[[str, str], None]) -> None:
        self._callbacks.append(callback)

    def _notify_callbacks(self, event_type: str, data: str) -> None:
        for cb in self._callbacks:
            try:
                cb(event_type, data)
            except Exception:
                logger.exception("Callback error")

    def force_failover(self, target_instance_id: str | None = None) -> bool:
        if target_instance_id:
            target = self._instances.get(target_instance_id)
            if not target or target.health_status != HealthStatus.HEALTHY:
                return False
            if self._active_instance_id and self._active_instance_id in self._instances:
                self._instances[self._active_instance_id].is_active = False
            self._activate_instance(target_instance_id)
            self._last_failover_time = datetime.now(UTC)
            self._failover_count += 1
            return True
        return self._perform_failover()

    async def start_monitoring(self) -> None:
        if self._running:
            return
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("Started failover monitoring")

    async def stop_monitoring(self) -> None:
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._monitor_task
            self._monitor_task = None
        logger.info("Stopped failover monitoring")

    async def _monitor_loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(self.config.health_check_interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in monitor loop")

    def get_status(self) -> dict[str, Any]:
        return {
            "state": self._state.value,
            "active_instance": (
                self.active_instance.to_dict() if self.active_instance else None
            ),
            "failover_count": self._failover_count,
            "last_failover": (
                self._last_failover_time.isoformat()
                if self._last_failover_time
                else None
            ),
            "instances": {id: inst.to_dict() for id, inst in self._instances.items()},
        }
