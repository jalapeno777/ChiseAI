"""Failure injection framework for chaos engineering.

Provides injectors for simulating various failure scenarios:
- Network partitions (dropped connections)
- Service failures (process termination)
- Latency injection (delayed responses)
- Error injection (forced exceptions)

For PAPER-003-002: E2E Integration Testing with Chaos Engineering
"""

from __future__ import annotations

import asyncio
import logging
import random
import socket
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol, TypeVar, runtime_checkable
from unittest.mock import patch

logger = logging.getLogger(__name__)

T = TypeVar("T")


@runtime_checkable
class Injectable(Protocol):
    """Protocol for objects that can have failures injected."""

    def inject_failure(self, failure_type: str, **kwargs: Any) -> None:
        """Inject a failure into the object."""
        ...

    def reset(self) -> None:
        """Reset the object to normal operation."""
        ...


@dataclass
class InjectionEvent:
    """Records a single failure injection event."""

    injector_type: str
    target: str
    failure_type: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    details: dict[str, Any] = field(default_factory=dict)
    recovered: bool = False
    recovery_time: datetime | None = None

    def mark_recovered(self) -> None:
        """Mark this injection event as recovered."""
        self.recovered = True
        self.recovery_time = datetime.now(UTC)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "injector_type": self.injector_type,
            "target": self.target,
            "failure_type": self.failure_type,
            "timestamp": self.timestamp.isoformat(),
            "details": self.details,
            "recovered": self.recovered,
            "recovery_time": self.recovery_time.isoformat()
            if self.recovery_time
            else None,
        }


class FailureInjector(ABC):
    """Abstract base class for failure injectors.

    Provides common functionality for all failure injection types
    including event tracking and recovery management.

    Attributes:
        name: Unique identifier for this injector
        events: List of injection events
        is_active: Whether injector is currently active
    """

    def __init__(self, name: str) -> None:
        """Initialize failure injector.

        Args:
            name: Unique identifier for this injector
        """
        self.name = name
        self._events: list[InjectionEvent] = []
        self._is_active = False
        self._patches: list[Any] = []

    @property
    def is_active(self) -> bool:
        """Check if injector is active."""
        return self._is_active

    @abstractmethod
    async def inject(self, target: str, **kwargs: Any) -> InjectionEvent:
        """Inject a failure into the target.

        Args:
            target: Target to inject failure into
            **kwargs: Additional injection parameters

        Returns:
            InjectionEvent recording the injection
        """
        pass

    @abstractmethod
    async def recover(self, event: InjectionEvent) -> bool:
        """Recover from an injected failure.

        Args:
            event: The injection event to recover from

        Returns:
            True if recovery was successful
        """
        pass

    def get_events(self, include_recovered: bool = False) -> list[InjectionEvent]:
        """Get injection events.

        Args:
            include_recovered: Whether to include recovered events

        Returns:
            List of injection events
        """
        if include_recovered:
            return self._events.copy()
        return [e for e in self._events if not e.recovered]

    def _record_event(
        self,
        injector_type: str,
        target: str,
        failure_type: str,
        details: dict[str, Any] | None = None,
    ) -> InjectionEvent:
        """Record an injection event.

        Args:
            injector_type: Type of injector
            target: Target that was injected
            failure_type: Type of failure injected
            details: Additional details

        Returns:
            The recorded event
        """
        event = InjectionEvent(
            injector_type=injector_type,
            target=target,
            failure_type=failure_type,
            details=details or {},
        )
        self._events.append(event)
        logger.info(f"[{injector_type}] Injected {failure_type} into {target}")
        return event

    def reset(self) -> None:
        """Reset the injector, clearing all events and patches."""
        self._events.clear()
        self._is_active = False
        for p in self._patches:
            with suppress(Exception):
                p.stop()
        self._patches.clear()


class NetworkPartitionInjector(FailureInjector):
    """Injector for simulating network partitions and connection failures.

    Can simulate:
    - Complete network partitions (all connections dropped)
    - Partial partitions (specific hosts unreachable)
    - Connection timeouts
    - DNS failures

    Attributes:
        partition_duration: Duration of partition in seconds
        affected_hosts: List of hosts affected by partition
    """

    def __init__(
        self,
        name: str = "network_partition",
        partition_duration: float = 5.0,
    ) -> None:
        """Initialize network partition injector.

        Args:
            name: Unique identifier
            partition_duration: Default partition duration in seconds
        """
        super().__init__(name)
        self.partition_duration = partition_duration
        self._original_socket = socket.socket
        self._blocked_hosts: set[str] = set()
        self._partition_active = False

    async def inject(
        self,
        target: str,
        partition_type: str = "complete",
        duration: float | None = None,
        hosts: list[str] | None = None,
    ) -> InjectionEvent:
        """Inject a network partition.

        Args:
            target: Target service or connection
            partition_type: Type of partition (complete, partial, timeout, dns)
            duration: Override default partition duration
            hosts: Specific hosts to block (for partial partition)

        Returns:
            InjectionEvent recording the partition
        """
        duration = duration or self.partition_duration
        self._is_active = True

        if partition_type == "complete":
            await self._inject_complete_partition(target, duration)
        elif partition_type == "partial":
            await self._inject_partial_partition(target, hosts or [], duration)
        elif partition_type == "timeout":
            await self._inject_timeout(target, duration)
        elif partition_type == "dns":
            await self._inject_dns_failure(target, duration)

        return self._record_event(
            injector_type="NetworkPartitionInjector",
            target=target,
            failure_type=f"partition:{partition_type}",
            details={
                "duration": duration,
                "hosts": hosts,
                "partition_type": partition_type,
            },
        )

    async def _inject_complete_partition(self, target: str, duration: float) -> None:
        """Inject complete network partition."""
        self._partition_active = True

        def blocking_socket(*args, **kwargs):
            raise OSError("Network is unreachable")

        patcher = patch("socket.socket", blocking_socket)
        self._patches.append(patcher)
        patcher.start()

        logger.warning(f"Network partition injected for {target} ({duration}s)")

    async def _inject_partial_partition(
        self, target: str, hosts: list[str], duration: float
    ) -> None:
        """Inject partial network partition for specific hosts."""
        self._blocked_hosts.update(hosts)

        original_connect = socket.socket.connect

        def partial_connect(sock_self, address):
            host, port = address
            if any(blocked in host for blocked in self._blocked_hosts):
                raise OSError(f"Host {host} is unreachable")
            return original_connect(sock_self, address)

        patcher = patch.object(socket.socket, "connect", partial_connect)
        self._patches.append(patcher)
        patcher.start()

        logger.warning(f"Partial partition for {hosts} on {target} ({duration}s)")

    async def _inject_timeout(self, target: str, duration: float) -> None:
        """Inject connection timeouts."""

        def timeout_socket(*args, **kwargs):
            class TimeoutSocket:
                def connect(self, *args, **kwargs):
                    time.sleep(duration + 1)  # Force timeout
                    raise TimeoutError("Connection timed out")

                def __getattr__(self, name):
                    return lambda *args, **kwargs: None

            return TimeoutSocket()

        patcher = patch("socket.socket", timeout_socket)
        self._patches.append(patcher)
        patcher.start()

        logger.warning(f"Connection timeout injected for {target} ({duration}s)")

    async def _inject_dns_failure(self, target: str, duration: float) -> None:
        """Inject DNS resolution failures."""

        def failing_getaddrinfo(*args, **kwargs):
            raise socket.gaierror("Name or service not known")

        patcher = patch("socket.getaddrinfo", failing_getaddrinfo)
        self._patches.append(patcher)
        patcher.start()

        logger.warning(f"DNS failure injected for {target} ({duration}s)")

    async def recover(self, event: InjectionEvent) -> bool:
        """Recover from network partition."""
        try:
            for patcher in self._patches:
                patcher.stop()
            self._patches.clear()
            self._blocked_hosts.clear()
            self._partition_active = False
            self._is_active = False
            event.mark_recovered()
            logger.info(f"Network partition recovered for {event.target}")
            return True
        except Exception as e:
            logger.error(f"Failed to recover network partition: {e}")
            return False


class ServiceFailureInjector(FailureInjector):
    """Injector for simulating service failures and process termination.

    Can simulate:
    - Service crashes (process termination)
    - Service restarts
    - Resource exhaustion (OOM, CPU)
    - Graceful shutdowns

    Attributes:
        services: Dictionary of tracked services
    """

    def __init__(self, name: str = "service_failure") -> None:
        """Initialize service failure injector.

        Args:
            name: Unique identifier
        """
        super().__init__(name)
        self._services: dict[str, dict[str, Any]] = {}
        self._failed_services: set[str] = set()

    async def inject(
        self,
        target: str,
        failure_type: str = "crash",
        recovery_time: float = 2.0,
        **kwargs: Any,
    ) -> InjectionEvent:
        """Inject a service failure.

        Args:
            target: Service to fail
            failure_type: Type of failure (crash, restart, oom, graceful)
            recovery_time: Time before auto-recovery (0 for no auto-recovery)
            **kwargs: Additional parameters

        Returns:
            InjectionEvent recording the failure
        """
        self._is_active = True
        self._services[target] = {
            "failure_type": failure_type,
            "recovery_time": recovery_time,
            "state": "failed",
            "kwargs": kwargs,
        }
        self._failed_services.add(target)

        # Simulate the failure
        if failure_type == "crash":
            await self._simulate_crash(target)
        elif failure_type == "restart":
            await self._simulate_restart(target)
        elif failure_type == "oom":
            await self._simulate_oom(target)
        elif failure_type == "graceful":
            await self._simulate_graceful_shutdown(target)

        return self._record_event(
            injector_type="ServiceFailureInjector",
            target=target,
            failure_type=failure_type,
            details={
                "recovery_time": recovery_time,
                "service_state": "failed",
                **kwargs,
            },
        )

    async def _simulate_crash(self, target: str) -> None:
        """Simulate a service crash."""
        logger.critical(f"Service {target} crashed!")
        # In real implementation, this would terminate the process
        # For testing, we track the failure state

    async def _simulate_restart(self, target: str) -> None:
        """Simulate a service restart."""
        logger.warning(f"Service {target} restarting...")
        await asyncio.sleep(0.5)  # Simulate restart delay

    async def _simulate_oom(self, target: str) -> None:
        """Simulate out-of-memory condition."""
        logger.critical(f"Service {target} ran out of memory!")

    async def _simulate_graceful_shutdown(self, target: str) -> None:
        """Simulate graceful shutdown."""
        logger.info(f"Service {target} shutting down gracefully...")

    def is_service_available(self, service_name: str) -> bool:
        """Check if a service is available.

        Args:
            service_name: Name of the service

        Returns:
            True if service is available
        """
        return service_name not in self._failed_services

    async def recover(self, event: InjectionEvent) -> bool:
        """Recover a failed service."""
        try:
            target = event.target
            if target in self._failed_services:
                self._failed_services.remove(target)
                self._services[target]["state"] = "recovered"
                logger.info(f"Service {target} recovered")
            event.mark_recovered()
            if not self._failed_services:
                self._is_active = False
            return True
        except Exception as e:
            logger.error(f"Failed to recover service: {e}")
            return False

    async def recover_all(self) -> list[InjectionEvent]:
        """Recover all failed services.

        Returns:
            List of recovered events
        """
        recovered = []
        for event in self.get_events():
            if await self.recover(event):
                recovered.append(event)
        return recovered


class LatencyInjector(FailureInjector):
    """Injector for adding artificial latency and delays.

    Can simulate:
    - Fixed delays
    - Random delays within a range
    - Percentile-based delays (P50, P95, P99)
    - Jitter (variable delay)

    Attributes:
        base_delay_ms: Base delay in milliseconds
        jitter_ms: Jitter range in milliseconds
    """

    def __init__(
        self,
        name: str = "latency",
        base_delay_ms: float = 100.0,
        jitter_ms: float = 50.0,
    ) -> None:
        """Initialize latency injector.

        Args:
            name: Unique identifier
            base_delay_ms: Base delay in milliseconds
            jitter_ms: Jitter range in milliseconds
        """
        super().__init__(name)
        self.base_delay_ms = base_delay_ms
        self.jitter_ms = jitter_ms
        self._active_delays: dict[str, float] = {}

    async def inject(
        self,
        target: str,
        delay_type: str = "fixed",
        delay_ms: float | None = None,
        percentile: str | None = None,
        **kwargs: Any,
    ) -> InjectionEvent:
        """Inject latency into operations.

        Args:
            target: Target operation or service
            delay_type: Type of delay (fixed, random, percentile, jitter)
            delay_ms: Delay in milliseconds (for fixed type)
            percentile: Percentile to simulate (P50, P95, P99)
            **kwargs: Additional parameters

        Returns:
            InjectionEvent recording the latency injection
        """
        self._is_active = True
        delay_ms = delay_ms or self.base_delay_ms

        if delay_type == "fixed":
            actual_delay = delay_ms
        elif delay_type == "random":
            min_delay = kwargs.get("min_ms", 0)
            max_delay = kwargs.get("max_ms", delay_ms * 2)
            actual_delay = random.uniform(min_delay, max_delay)
        elif delay_type == "percentile":
            actual_delay = self._get_percentile_delay(percentile or "P50", delay_ms)
        elif delay_type == "jitter":
            jitter = random.uniform(-self.jitter_ms, self.jitter_ms)
            actual_delay = max(0, delay_ms + jitter)
        else:
            actual_delay = delay_ms

        self._active_delays[target] = actual_delay

        return self._record_event(
            injector_type="LatencyInjector",
            target=target,
            failure_type=f"latency:{delay_type}",
            details={
                "delay_ms": actual_delay,
                "delay_type": delay_type,
                "percentile": percentile,
            },
        )

    def _get_percentile_delay(self, percentile: str, base_delay: float) -> float:
        """Get delay for a specific percentile.

        Args:
            percentile: Percentile string (P50, P95, P99)
            base_delay: Base delay in ms

        Returns:
            Delay in ms for the percentile
        """
        multipliers = {
            "P50": 1.0,
            "P95": 2.0,
            "P99": 3.0,
        }
        return base_delay * multipliers.get(percentile, 1.0)

    async def apply_delay(self, target: str | None = None) -> float:
        """Apply configured delay.

        Args:
            target: Specific target to delay for

        Returns:
            Actual delay applied in seconds
        """
        if target and target in self._active_delays:
            delay_ms = self._active_delays[target]
        elif self._active_delays:
            delay_ms = max(self._active_delays.values())
        else:
            return 0.0

        delay_sec = delay_ms / 1000.0
        await asyncio.sleep(delay_sec)
        return delay_sec

    async def recover(self, event: InjectionEvent) -> bool:
        """Remove latency injection."""
        try:
            target = event.target
            if target in self._active_delays:
                del self._active_delays[target]
            event.mark_recovered()
            if not self._active_delays:
                self._is_active = False
            logger.info(f"Latency injection removed for {target}")
            return True
        except Exception as e:
            logger.error(f"Failed to remove latency injection: {e}")
            return False

    @contextmanager
    def inject_delay(self, delay_ms: float):
        """Context manager for temporary delay injection.

        Args:
            delay_ms: Delay in milliseconds

        Yields:
            None
        """
        original_sleep = asyncio.sleep

        async def delayed_sleep(delay, *args, **kwargs):
            await original_sleep(delay + delay_ms / 1000.0, *args, **kwargs)

        try:
            asyncio.sleep = delayed_sleep
            yield
        finally:
            asyncio.sleep = original_sleep


class ErrorInjector(FailureInjector):
    """Injector for forcing errors and exceptions.

    Can simulate:
    - Specific exception types
    - Random errors
    - Conditional errors (based on call count, time, etc.)
    - HTTP status code errors

    Attributes:
        error_rate: Probability of error (0-1)
        error_types: Types of errors to inject
    """

    def __init__(
        self,
        name: str = "error",
        error_rate: float = 0.1,
    ) -> None:
        """Initialize error injector.

        Args:
            name: Unique identifier
            error_rate: Default error probability (0-1)
        """
        super().__init__(name)
        self.error_rate = error_rate
        self._error_configs: dict[str, dict[str, Any]] = {}
        self._call_counts: dict[str, int] = {}

    async def inject(
        self,
        target: str,
        error_type: str = "exception",
        error_rate: float | None = None,
        exception_class: type[Exception] = Exception,
        condition: str | None = None,
        **kwargs: Any,
    ) -> InjectionEvent:
        """Inject errors into operations.

        Args:
            target: Target function or method
            error_type: Type of error (exception, http, timeout, random)
            error_rate: Probability of error (0-1)
            exception_class: Exception class to raise
            condition: Condition for error (every_n, after_n, random)
            **kwargs: Additional parameters

        Returns:
            InjectionEvent recording the error injection
        """
        self._is_active = True
        rate = error_rate if error_rate is not None else self.error_rate

        self._error_configs[target] = {
            "error_type": error_type,
            "error_rate": rate,
            "exception_class": exception_class,
            "condition": condition,
            "kwargs": kwargs,
        }

        return self._record_event(
            injector_type="ErrorInjector",
            target=target,
            failure_type=f"error:{error_type}",
            details={
                "error_rate": rate,
                "exception_class": exception_class.__name__,
                "condition": condition,
                **kwargs,
            },
        )

    def should_error(self, target: str) -> bool:
        """Check if an error should be triggered for target.

        Args:
            target: Target being called

        Returns:
            True if error should be triggered
        """
        if target not in self._error_configs:
            return False

        config = self._error_configs[target]
        self._call_counts[target] = self._call_counts.get(target, 0) + 1
        count = self._call_counts[target]

        condition = config.get("condition")
        if condition == "every_n":
            n = config["kwargs"].get("n", 1)
            return count % n == 0
        elif condition == "after_n":
            n = config["kwargs"].get("n", 0)
            return count > n
        else:
            return random.random() < config["error_rate"]

    def get_error(self, target: str) -> Exception:
        """Get the error to raise for target.

        Args:
            target: Target being called

        Returns:
            Exception instance to raise
        """
        config = self._error_configs.get(target, {})
        error_type = config.get("error_type", "exception")

        if error_type == "http":
            status = config["kwargs"].get("status_code", 500)
            return Exception(f"HTTP {status}")
        elif error_type == "timeout":
            return TimeoutError("Operation timed out")
        else:
            exc_class = config.get("exception_class", Exception)
            return exc_class(f"Injected error for {target}")

    async def maybe_raise_error(self, target: str) -> None:
        """Maybe raise an error for the target.

        Args:
            target: Target being called

        Raises:
            Exception: If error condition is met
        """
        if self.should_error(target):
            raise self.get_error(target)

    async def recover(self, event: InjectionEvent) -> bool:
        """Remove error injection."""
        try:
            target = event.target
            if target in self._error_configs:
                del self._error_configs[target]
            if target in self._call_counts:
                del self._call_counts[target]
            event.mark_recovered()
            if not self._error_configs:
                self._is_active = False
            logger.info(f"Error injection removed for {target}")
            return True
        except Exception as e:
            logger.error(f"Failed to remove error injection: {e}")
            return False

    def wrap_function(
        self, func: Callable[..., T], error_rate: float | None = None
    ) -> Callable[..., T]:
        """Wrap a function to inject errors.

        Args:
            func: Function to wrap
            error_rate: Override error rate

        Returns:
            Wrapped function
        """
        target = f"{func.__module__}.{func.__name__}"

        def wrapper(*args, **kwargs):
            config = self._error_configs.get(target, {})
            rate = error_rate if error_rate is not None else config.get("error_rate", 0)
            if random.random() < rate:
                raise self.get_error(target)
            return func(*args, **kwargs)

        return wrapper
