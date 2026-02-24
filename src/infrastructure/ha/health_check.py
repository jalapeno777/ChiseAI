"""Health Check System for High Availability Infrastructure (NFR-006)."""
import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

class HealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"

@dataclass
class HealthCheckResult:
    name: str
    status: HealthStatus
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    message: str = ""
    latency_ms: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "status": self.status.value, "timestamp": self.timestamp.isoformat(),
                "message": self.message, "latency_ms": self.latency_ms, "details": self.details}

@dataclass
class HealthCheckConfig:
    name: str
    check_func: Callable[[], bool]
    interval_seconds: float = 30.0
    timeout_seconds: float = 5.0
    unhealthy_threshold: int = 3
    healthy_threshold: int = 2
    critical: bool = False
    tags: list[str] = field(default_factory=list)

class HealthChecker:
    def __init__(self, config: HealthCheckConfig):
        self.config = config
        self._consecutive_failures = 0
        self._consecutive_successes = 0
        self._last_result: HealthCheckResult | None = None
        self._running = False
        self._task: asyncio.Task | None = None

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def is_healthy(self) -> bool:
        return self._last_result is not None and self._last_result.status in (HealthStatus.HEALTHY, HealthStatus.DEGRADED)

    @property
    def is_critical(self) -> bool:
        return self.config.critical

    async def check(self) -> HealthCheckResult:
        start_time = time.perf_counter()
        status, message, details = HealthStatus.UNKNOWN, "", {}
        try:
            result = await asyncio.wait_for(self._run_check(), timeout=self.config.timeout_seconds)
            if result:
                status, message = HealthStatus.HEALTHY, "Check passed"
                self._consecutive_successes += 1
                self._consecutive_failures = 0
            else:
                status, message = HealthStatus.UNHEALTHY, "Check failed"
                self._consecutive_failures += 1
                self._consecutive_successes = 0
        except TimeoutError:
            status, message = HealthStatus.UNHEALTHY, f"Check timed out after {self.config.timeout_seconds}s"
            self._consecutive_failures += 1
            self._consecutive_successes = 0
            details["timeout"] = True
        except Exception as e:
            status, message = HealthStatus.UNHEALTHY, f"Check exception: {e}"
            self._consecutive_failures += 1
            self._consecutive_successes = 0
            details["exception"] = str(e)

        if self._consecutive_failures >= self.config.unhealthy_threshold:
            status = HealthStatus.UNHEALTHY
        elif self._consecutive_successes >= self.config.healthy_threshold:
            status = HealthStatus.HEALTHY
        elif self._consecutive_failures > 0 and self._consecutive_successes > 0:
            status = HealthStatus.DEGRADED

        self._last_result = HealthCheckResult(name=self.config.name, status=status, message=message,
                                               latency_ms=(time.perf_counter() - start_time) * 1000, details=details)
        return self._last_result

    async def _run_check(self) -> bool:
        if asyncio.iscoroutinefunction(self.config.check_func):
            return await self.config.check_func()
        return self.config.check_func()

    async def start_periodic(self) -> None:
        if self._running: return
        self._running = True
        self._task = asyncio.create_task(self._periodic_check_loop())
        logger.info(f"Started periodic health check: {self.config.name}")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try: await self._task
            except asyncio.CancelledError: pass
            self._task = None
        logger.info(f"Stopped health check: {self.config.name}")

    async def _periodic_check_loop(self) -> None:
        while self._running:
            try: await self.check()
            except Exception: logger.exception(f"Error in periodic check for {self.config.name}")
            await asyncio.sleep(self.config.interval_seconds)

    def get_last_result(self) -> HealthCheckResult | None:
        return self._last_result

class HealthCheckRegistry:
    def __init__(self):
        self._checkers: dict[str, HealthChecker] = {}
        self._callbacks: list[Callable[[str, HealthCheckResult], None]] = []

    def register(self, config: HealthCheckConfig) -> HealthChecker:
        if config.name in self._checkers:
            raise ValueError(f"Health check '{config.name}' already registered")
        self._checkers[config.name] = HealthChecker(config)
        logger.info(f"Registered health check: {config.name}")
        return self._checkers[config.name]

    def unregister(self, name: str) -> bool:
        if name in self._checkers:
            del self._checkers[name]
            return True
        return False

    def get(self, name: str) -> HealthChecker | None:
        return self._checkers.get(name)

    def get_all(self) -> dict[str, HealthChecker]:
        return dict(self._checkers)

    def get_critical(self) -> list[HealthChecker]:
        return [c for c in self._checkers.values() if c.is_critical]

    async def check_all(self) -> dict[str, HealthCheckResult]:
        results = {}
        for name, checker in self._checkers.items():
            results[name] = await checker.check()
            for cb in self._callbacks:
                try: cb(name, results[name])
                except Exception: logger.exception("Callback error")
        return results

    async def check_parallel(self) -> dict[str, HealthCheckResult]:
        tasks = {name: checker.check() for name, checker in self._checkers.items()}
        results_list = await asyncio.gather(*tasks.values(), return_exceptions=True)
        results = {}
        for (name, _), result in zip(tasks.items(), results_list):
            if isinstance(result, Exception):
                results[name] = HealthCheckResult(name=name, status=HealthStatus.UNHEALTHY, message=f"Check exception: {result}")
            else:
                results[name] = result
            for cb in self._callbacks:
                try: cb(name, results[name])
                except Exception: logger.exception("Callback error")
        return results

    async def start_all(self) -> None:
        for checker in self._checkers.values():
            await checker.start_periodic()

    async def stop_all(self) -> None:
        for checker in self._checkers.values():
            await checker.stop()

    def add_callback(self, callback: Callable[[str, HealthCheckResult], None]) -> None:
        self._callbacks.append(callback)

    def remove_callback(self, callback: Callable[[str, HealthCheckResult], None]) -> None:
        if callback in self._callbacks: self._callbacks.remove(callback)

    def get_overall_status(self) -> HealthStatus:
        if not self._checkers: return HealthStatus.UNKNOWN
        statuses = [c._last_result.status for c in self._checkers.values() if c._last_result]
        if not statuses: return HealthStatus.UNKNOWN
        for c in self._checkers.values():
            if c.is_critical and c._last_result and c._last_result.status == HealthStatus.UNHEALTHY:
                return HealthStatus.UNHEALTHY
        if HealthStatus.UNHEALTHY in statuses: return HealthStatus.DEGRADED
        if HealthStatus.DEGRADED in statuses: return HealthStatus.DEGRADED
        if all(s == HealthStatus.HEALTHY for s in statuses): return HealthStatus.HEALTHY
        return HealthStatus.UNKNOWN

    def to_dict(self) -> dict[str, Any]:
        return {"overall_status": self.get_overall_status().value,
                "checks": {n: c.get_last_result().to_dict() if c.get_last_result() else None for n, c in self._checkers.items()},
                "timestamp": datetime.now(UTC).isoformat()}

_registry: HealthCheckRegistry | None = None

def get_registry() -> HealthCheckRegistry:
    global _registry
    if _registry is None: _registry = HealthCheckRegistry()
    return _registry

def reset_registry() -> None:
    global _registry
    _registry = None
