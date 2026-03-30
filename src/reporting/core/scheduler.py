"""Report scheduler for the core report generation engine.

Provides daily/weekly/monthly trigger support for report generation.
Integrates with the existing ReportScheduler from src.reporting.scheduler.

For ST-NS-023-T1: Core Report Generation Engine
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ReportPeriod(Enum):
    """Report period types."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


@dataclass
class ReportTrigger:
    """Configuration for a report trigger.

    Attributes:
        period: The reporting period (daily, weekly, monthly)
        hour: Hour of day to trigger (0-23)
        minute: Minute to trigger (0-59)
        enabled: Whether the trigger is active
        callback: Async callback to execute when triggered
        name: Human-readable name for this trigger
    """

    period: ReportPeriod
    hour: int = 9
    minute: int = 0
    enabled: bool = True
    callback: Callable[[], Coroutine[Any, Any, None]] | None = None
    name: str = ""
    last_run: datetime | None = None

    def __post_init__(self) -> None:
        """Set default name if not provided."""
        if not self.name:
            self.name = f"{self.period.value}_report"

    def should_run(self, now: datetime) -> bool:
        """Check if this trigger should run at the given time.

        Args:
            now: Current datetime

        Returns:
            True if trigger should run
        """
        if not self.enabled:
            return False

        # Check time match
        if now.hour != self.hour or now.minute != self.minute:
            return False

        # Check if already run for this period
        if self.last_run is None:
            return True

        if self.period == ReportPeriod.DAILY:
            return self.last_run.date() < now.date()
        elif self.period == ReportPeriod.WEEKLY:
            # Weekly reports run on Monday (weekday 0)
            if now.weekday() != 0:  # Not Monday
                return False
            return self.last_run.isocalendar()[1] < now.isocalendar()[1]
        elif self.period == ReportPeriod.MONTHLY:
            # Monthly reports run on the 1st of the month
            if now.day != 1:  # Not 1st of month
                return False
            return self.last_run.month < now.month or self.last_run.year < now.year

        return False


@dataclass
class ScheduledReport:
    """Represents a scheduled report execution.

    Attributes:
        trigger: The trigger configuration
        report_data: Generated report data
        generated_at: When the report was generated
        period_start: Start of the reporting period
        period_end: End of the reporting period
    """

    trigger: ReportTrigger
    report_data: dict[str, Any]
    generated_at: datetime
    period_start: datetime
    period_end: datetime


class ReportScheduler:
    """Schedule and manage automated report generation.

    Provides:
    - Daily/weekly/monthly trigger support
    - Configurable report types and timing
    - Integration with existing reporting infrastructure
    - Async/await for scheduler operations

    Attributes:
        triggers: List of configured report triggers
        check_interval: Seconds between schedule checks
        output_dir: Directory for report archival
    """

    def __init__(
        self,
        output_dir: str = "./reports",
        check_interval: int = 60,
    ) -> None:
        """Initialize report scheduler.

        Args:
            output_dir: Directory for report archival
            check_interval: Seconds between schedule checks (default: 60)
        """
        self._triggers: list[ReportTrigger] = []
        self._output_dir = output_dir
        self._check_interval = check_interval
        self._running = False
        self._scheduler_task: asyncio.Task | None = None
        self._pending_reports: list[ScheduledReport] = []

        logger.info(
            f"ReportScheduler initialized: output_dir={output_dir}, "
            f"check_interval={check_interval}s"
        )

    @property
    def triggers(self) -> list[ReportTrigger]:
        """Get all configured triggers.

        Returns:
            List of ReportTrigger objects
        """
        return self._triggers.copy()

    def add_trigger(
        self,
        period: ReportPeriod,
        hour: int = 9,
        minute: int = 0,
        enabled: bool = True,
        callback: Callable[[], Coroutine[Any, Any, None]] | None = None,
        name: str | None = None,
    ) -> ReportTrigger:
        """Add a new report trigger.

        Args:
            period: The reporting period (daily, weekly, monthly)
            hour: Hour of day to trigger (0-23, default: 9)
            minute: Minute to trigger (0-59, default: 0)
            enabled: Whether the trigger is active (default: True)
            callback: Optional async callback to execute
            name: Optional human-readable name

        Returns:
            Created ReportTrigger
        """
        trigger = ReportTrigger(
            period=period,
            hour=hour,
            minute=minute,
            enabled=enabled,
            callback=callback,
            name=name or f"{period.value}_report",
        )

        self._triggers.append(trigger)
        logger.info(
            f"Added trigger: {trigger.name} ({period.value}) at {hour:02d}:{minute:02d}"
        )

        return trigger

    def remove_trigger(self, name: str) -> bool:
        """Remove a trigger by name.

        Args:
            name: Trigger name to remove

        Returns:
            True if removed, False if not found
        """
        for i, trigger in enumerate(self._triggers):
            if trigger.name == name:
                self._triggers.pop(i)
                logger.info(f"Removed trigger: {name}")
                return True
        return False

    def get_trigger(self, name: str) -> ReportTrigger | None:
        """Get a trigger by name.

        Args:
            name: Trigger name

        Returns:
            ReportTrigger if found, None otherwise
        """
        for trigger in self._triggers:
            if trigger.name == name:
                return trigger
        return None

    def schedule_daily(
        self,
        hour: int = 9,
        minute: int = 0,
        callback: Callable[[], Coroutine[Any, Any, None]] | None = None,
        name: str | None = None,
    ) -> ReportTrigger:
        """Add a daily report trigger.

        Args:
            hour: Hour of day to trigger (default: 9)
            minute: Minute to trigger (default: 0)
            callback: Optional async callback
            name: Optional trigger name

        Returns:
            Created ReportTrigger
        """
        return self.add_trigger(
            period=ReportPeriod.DAILY,
            hour=hour,
            minute=minute,
            callback=callback,
            name=name,
        )

    def schedule_weekly(
        self,
        hour: int = 9,
        minute: int = 0,
        callback: Callable[[], Coroutine[Any, Any, None]] | None = None,
        name: str | None = None,
    ) -> ReportTrigger:
        """Add a weekly report trigger.

        Weekly reports run on Mondays at the specified time.

        Args:
            hour: Hour of day to trigger (default: 9)
            minute: Minute to trigger (default: 0)
            callback: Optional async callback
            name: Optional trigger name

        Returns:
            Created ReportTrigger
        """
        return self.add_trigger(
            period=ReportPeriod.WEEKLY,
            hour=hour,
            minute=minute,
            callback=callback,
            name=name,
        )

    def schedule_monthly(
        self,
        hour: int = 9,
        minute: int = 0,
        callback: Callable[[], Coroutine[Any, Any, None]] | None = None,
        name: str | None = None,
    ) -> ReportTrigger:
        """Add a monthly report trigger.

        Monthly reports run on the 1st of each month at the specified time.

        Args:
            hour: Hour of day to trigger (default: 9)
            minute: Minute to trigger (default: 0)
            callback: Optional async callback
            name: Optional trigger name

        Returns:
            Created ReportTrigger
        """
        return self.add_trigger(
            period=ReportPeriod.MONTHLY,
            hour=hour,
            minute=minute,
            callback=callback,
            name=name,
        )

    async def start(self) -> None:
        """Start the scheduler loop."""
        if self._running:
            logger.warning("Scheduler already running")
            return

        self._running = True
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        logger.info("Report scheduler started")

    async def stop(self) -> None:
        """Stop the scheduler loop."""
        if not self._running:
            return

        self._running = False

        if self._scheduler_task and not self._scheduler_task.done():
            self._scheduler_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._scheduler_task

        logger.info("Report scheduler stopped")

    async def _scheduler_loop(self) -> None:
        """Main scheduler loop."""
        while self._running:
            try:
                await self._check_triggers()
                await asyncio.sleep(self._check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scheduler loop error: {e}")
                await asyncio.sleep(self._check_interval)

    async def _check_triggers(self) -> None:
        """Check all triggers and execute due reports."""
        now = datetime.now(UTC)

        for trigger in self._triggers:
            if trigger.should_run(now):
                try:
                    await self._execute_trigger(trigger, now)
                except Exception as e:
                    logger.error(f"Error executing trigger {trigger.name}: {e}")

    async def _execute_trigger(
        self,
        trigger: ReportTrigger,
        now: datetime,
    ) -> None:
        """Execute a trigger.

        Args:
            trigger: Trigger to execute
            now: Current datetime
        """
        logger.info(f"Executing trigger: {trigger.name}")

        # Update last run time
        trigger.last_run = now

        # Calculate period boundaries
        period_start, period_end = self._calculate_period(trigger.period, now)

        # Execute callback if provided
        if trigger.callback:
            try:
                await trigger.callback()
            except Exception as e:
                logger.error(f"Callback error for {trigger.name}: {e}")

        # Create scheduled report record
        scheduled_report = ScheduledReport(
            trigger=trigger,
            report_data={},
            generated_at=now,
            period_start=period_start,
            period_end=period_end,
        )

        self._pending_reports.append(scheduled_report)

    def _calculate_period(
        self,
        period: ReportPeriod,
        now: datetime,
    ) -> tuple[datetime, datetime]:
        """Calculate period boundaries for a report.

        Args:
            period: The reporting period
            now: Current datetime

        Returns:
            Tuple of (period_start, period_end)
        """
        if period == ReportPeriod.DAILY:
            period_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            period_end = period_start + timedelta(days=1)
        elif period == ReportPeriod.WEEKLY:
            # Start of week (Monday)
            days_since_monday = now.weekday()
            period_start = (now - timedelta(days=days_since_monday)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            period_end = period_start + timedelta(days=7)
        else:  # MONTHLY
            period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            # First day of next month
            if now.month == 12:
                period_end = now.replace(year=now.year + 1, month=1, day=1)
            else:
                period_end = now.replace(month=now.month + 1, day=1)
            # Handle edge case for last day of month
            if period_end <= period_start:
                period_end = period_start + timedelta(days=31)

        return period_start, period_end

    def get_pending_reports(self) -> list[ScheduledReport]:
        """Get pending reports.

        Returns:
            List of pending ScheduledReport objects
        """
        return self._pending_reports.copy()

    def clear_pending_reports(self) -> None:
        """Clear pending reports."""
        self._pending_reports.clear()

    def get_next_run_time(self, trigger: ReportTrigger) -> datetime | None:
        """Calculate next run time for a trigger.

        Args:
            trigger: The trigger to calculate for

        Returns:
            Next run datetime, or None if trigger is disabled
        """
        if not trigger.enabled:
            return None

        now = datetime.now(UTC)
        next_run = now.replace(
            hour=trigger.hour, minute=trigger.minute, second=0, microsecond=0
        )

        if trigger.period == ReportPeriod.DAILY:
            if next_run <= now:
                next_run += timedelta(days=1)
        elif trigger.period == ReportPeriod.WEEKLY:
            # Find next Monday
            days_until_monday = (7 - now.weekday()) % 7
            if days_until_monday == 0 and next_run <= now:
                days_until_monday = 7
            next_run = (now + timedelta(days=days_until_monday)).replace(
                hour=trigger.hour, minute=trigger.minute, second=0, microsecond=0
            )
        elif trigger.period == ReportPeriod.MONTHLY:
            if now.day >= trigger.hour or (now.day == trigger.hour and next_run <= now):
                # Move to next month
                if now.month == 12:
                    next_run = now.replace(year=now.year + 1, month=1, day=1)
                else:
                    next_run = now.replace(month=now.month + 1, day=1)
            else:
                next_run = now.replace(day=1)
            next_run = next_run.replace(hour=trigger.hour, minute=trigger.minute)

        return next_run

    async def trigger_now(self, name: str) -> bool:
        """Manually trigger a report by name.

        Args:
            name: Trigger name

        Returns:
            True if triggered successfully
        """
        trigger = self.get_trigger(name)
        if not trigger:
            logger.warning(f"Trigger not found: {name}")
            return False

        now = datetime.now(UTC)
        try:
            await self._execute_trigger(trigger, now)
            return True
        except Exception as e:
            logger.error(f"Manual trigger error for {name}: {e}")
            return False
