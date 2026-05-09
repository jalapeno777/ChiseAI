"""Background health monitor for LLM providers.

Runs periodic health checks on all configured providers and updates
circuit breaker state based on results. Can be started/stopped
independently of the provider chain.

For ST-MVP-007: LLM Provider Redundancy Enhancement
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from llm.circuit_breaker import CircuitBreaker
    from llm.health_check import ProviderHealthChecker

logger = logging.getLogger(__name__)


class HealthMonitor:
    """Background health monitor for LLM providers.

    Periodically checks all configured providers and updates circuit breaker
    state based on health check results. Runs in a background daemon thread.

    Usage:
        from llm.circuit_breaker import CircuitBreaker
        from llm.health_check import ProviderHealthChecker

        cb = CircuitBreaker()
        hc = ProviderHealthChecker()
        monitor = HealthMonitor(circuit_breaker=cb, health_checker=hc)

        monitor.start()  # Starts background thread
        # ... application runs ...
        monitor.stop()   # Stops background thread
    """

    def __init__(
        self,
        circuit_breaker: CircuitBreaker,
        health_checker: ProviderHealthChecker,
        check_interval_seconds: float = 120.0,
        providers: list[str] | None = None,
    ):
        """Initialize the health monitor.

        Args:
            circuit_breaker: CircuitBreaker instance to update
            health_checker: ProviderHealthChecker instance to use for checks
            check_interval_seconds: Interval between health check rounds
            providers: List of provider names to monitor, or None for defaults
        """
        self._circuit_breaker = circuit_breaker
        self._health_checker = health_checker
        self._check_interval = check_interval_seconds
        self._providers = providers or [
            "kimi_compat",
            "kimi",
            "zai",
            "zhipu",
            "minimax",
        ]
        self._running = False
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._last_check_results: dict[str, str] = {}

    def start(self) -> None:
        """Start the background health monitoring thread.

        Safe to call multiple times - no-op if already running.
        """
        if self._running:
            logger.debug("Health monitor already running")
            return

        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._monitor_loop,
            name="llm-health-monitor",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "Health monitor started (interval=%.0fs, providers=%s)",
            self._check_interval,
            self._providers,
        )

    def stop(self) -> None:
        """Stop the background health monitoring thread.

        Safe to call multiple times - no-op if not running.
        """
        if not self._running:
            return

        self._running = False
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
        logger.info("Health monitor stopped")

    def check_now(self) -> dict[str, str]:
        """Run an immediate health check on all monitored providers.

        Returns:
            Dictionary mapping provider names to health status names
        """
        results = {}
        for provider in self._providers:
            result = self._health_checker.check_health(provider)
            results[provider] = result.status.name

            # Update circuit breaker based on health
            self._update_circuit_from_health(provider, result.status.name)

        self._last_check_results = results
        return results

    def get_last_results(self) -> dict[str, str]:
        """Get results from the last health check round.

        Returns:
            Dictionary mapping provider names to health status names
        """
        return dict(self._last_check_results)

    @property
    def is_running(self) -> bool:
        """Check if the monitor is currently running."""
        return self._running

    def _update_circuit_from_health(self, provider: str, status: str) -> None:
        """Update circuit breaker based on health check result.

        Args:
            provider: Provider name
            status: HealthStatus name string
        """
        from llm.health_check import HealthStatus

        try:
            health_status = HealthStatus[status]
        except (KeyError, ValueError):
            return

        if health_status == HealthStatus.HEALTHY:
            # Record success to potentially close a half-open circuit
            self._circuit_breaker.record_success(provider)
        elif health_status == HealthStatus.UNAVAILABLE:
            # Record failure to potentially open a closed circuit
            self._circuit_breaker.record_failure(provider)
            logger.warning(
                "Health monitor: %s is UNAVAILABLE, recording failure to circuit breaker",
                provider,
            )
        # DEGRADED and UNKNOWN: don't update circuit state

    def _monitor_loop(self) -> None:
        """Main monitoring loop running in background thread."""
        logger.info("Health monitor loop started")

        while not self._stop_event.is_set():
            try:
                results = self.check_now()
                logger.info(
                    "Health monitor check complete: %s",
                    ", ".join(f"{p}={s}" for p, s in results.items()),
                )
            except Exception as e:
                logger.error("Health monitor check failed: %s", e)

            # Wait for next interval, checking stop event
            self._stop_event.wait(timeout=self._check_interval)

        logger.info("Health monitor loop stopped")


__all__ = [
    "HealthMonitor",
]
