"""Trigger Service for bridging LogMonitor to SelfHealingEngine.

Filters log entries, rate-limits triggers, and dispatches to the healing engine
for automated failure recovery.

For PM-BATCH-2 CF-1: Log Monitor + Trigger Service
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from autonomous_control_plane.components.log_monitor import LogMonitor
from autonomous_control_plane.components.self_healing_engine import (
    SelfHealingEngine,
)
from autonomous_control_plane.models.healing import LogEntry

logger = logging.getLogger(__name__)


@dataclass
class TriggerStats:
    """Statistics for trigger service."""

    total_entries_received: int = 0
    entries_filtered: int = 0
    triggers_attempted: int = 0
    triggers_rate_limited: int = 0
    triggers_failed: int = 0
    last_trigger_time: datetime | None = None


class HealingTriggerService:
    """Bridges LogMonitor to SelfHealingEngine.

    Features:
    - Filters log entries by level (ERROR, WARN, etc.)
    - Rate limits triggers (max 10/minute)
    - Batches and dispatches to SelfHealingEngine
    - Comprehensive statistics tracking

    Example:
        service = HealingTriggerService(log_monitor, healing_engine)
        await service.start()
        # Service automatically processes ERROR/WARN logs
        await service.stop()
    """

    # Maximum triggers per minute (rate limit)
    MAX_TRIGGERS_PER_MINUTE = 10

    # Log levels that trigger healing
    TRIGGER_LEVELS = {"ERROR", "WARN", "WARNING", "CRITICAL", "FATAL"}

    def __init__(
        self,
        log_monitor: LogMonitor,
        healing_engine: SelfHealingEngine,
    ):
        """Initialize healing trigger service.

        Args:
            log_monitor: LogMonitor instance to subscribe to
            healing_engine: SelfHealingEngine to dispatch triggers to
        """
        self._log_monitor = log_monitor
        self._healing_engine = healing_engine
        self._running = False
        self._trigger_times: list[datetime] = []
        self._lock = asyncio.Lock()
        self._stats = TriggerStats()

    async def start(self) -> None:
        """Start the trigger service.

        Subscribes to LogMonitor and begins processing log entries.

        Raises:
            RuntimeError: If already running
        """
        if self._running:
            raise RuntimeError("HealingTriggerService is already running")

        self._running = True
        self._log_monitor.subscribe(self._on_log_entry)
        logger.info("HealingTriggerService started")

    async def stop(self) -> None:
        """Stop the trigger service.

        Unsubscribes from LogMonitor and stops processing.
        """
        if not self._running:
            return

        self._running = False
        self._log_monitor.unsubscribe(self._on_log_entry)
        logger.info("HealingTriggerService stopped")

    async def _on_log_entry(self, entry: LogEntry) -> None:
        """Process a log entry and trigger healing if needed.

        Args:
            entry: Log entry to process
        """
        if not self._running:
            return

        self._stats.total_entries_received += 1

        # Filter by level
        if entry.level.upper() not in self.TRIGGER_LEVELS:
            return

        self._stats.entries_filtered += 1

        # Check rate limit
        if not await self._check_rate_limit():
            self._stats.triggers_rate_limited += 1
            if self._stats.triggers_rate_limited % 10 == 1:
                logger.warning(
                    f"Trigger rate limit exceeded ({self.MAX_TRIGGERS_PER_MINUTE}/min), "
                    f"skipping: {entry.message[:50]}..."
                )
            return

        # Trigger healing
        try:
            result = await self._healing_engine.process_log_entry(entry)
            if result:
                logger.info(
                    f"Healing triggered for {entry.source}: {result.action_type}"
                )
                self._stats.last_trigger_time = datetime.now(UTC)
            else:
                logger.debug(f"No healing pattern matched for {entry.source}")
        except Exception as e:
            self._stats.triggers_failed += 1
            logger.error(f"Healing trigger failed: {e}")

    async def _check_rate_limit(self) -> bool:
        """Check if we're within rate limits.

        Returns:
            True if trigger can proceed, False if rate limited
        """
        async with self._lock:
            now = datetime.now(UTC)
            cutoff = now - timedelta(minutes=1)

            # Remove old triggers outside the window
            self._trigger_times = [t for t in self._trigger_times if t > cutoff]

            # Check limit
            if len(self._trigger_times) >= self.MAX_TRIGGERS_PER_MINUTE:
                return False

            # Record this trigger
            self._trigger_times.append(now)
            self._stats.triggers_attempted += 1
            return True

    def get_stats(self) -> dict:
        """Get trigger service statistics.

        Returns:
            Dictionary with trigger counts and status
        """
        return {
            "running": self._running,
            "triggers_last_minute": len(self._trigger_times),
            "max_triggers_per_minute": self.MAX_TRIGGERS_PER_MINUTE,
            "total_entries_received": self._stats.total_entries_received,
            "entries_filtered": self._stats.entries_filtered,
            "triggers_attempted": self._stats.triggers_attempted,
            "triggers_rate_limited": self._stats.triggers_rate_limited,
            "triggers_failed": self._stats.triggers_failed,
            "last_trigger_time": (
                self._stats.last_trigger_time.isoformat()
                if self._stats.last_trigger_time
                else None
            ),
        }
