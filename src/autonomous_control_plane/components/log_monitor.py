"""Log Monitor for tailing and monitoring log files.

Monitors multiple log sources concurrently, parses entries, and dispatches
to registered subscribers with rate limiting and queue management.

For PM-BATCH-2 CF-1: Log Monitor + Trigger Service
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from src.autonomous_control_plane.components.log_parsers import (
    BaseLogParser,
    SimpleLogParser,
)
from src.autonomous_control_plane.models.healing import LogEntry

logger = logging.getLogger(__name__)


@dataclass
class LogWatcherConfig:
    """Configuration for a log watcher.

    Attributes:
        name: Unique identifier for this watcher
        path: Path to the log file to monitor
        parser: Parser instance for log entries
        max_entries_per_second: Rate limit for this source
        poll_interval: Seconds between file checks
    """

    name: str
    path: str
    parser: BaseLogParser
    max_entries_per_second: int = 1000
    poll_interval: float = 1.0


class LogMonitor:
    """Monitors multiple log sources and feeds entries to subscribers.

    Features:
    - Multiple concurrent log file watchers
    - Async queue with overflow protection
    - Subscriber callback pattern for extensibility
    - Rate limiting per source
    - Queue overflow drops oldest with metric alert

    Example:
        monitor = LogMonitor()
        monitor.add_watcher("app", "/var/log/app.log", JSONLogParser())
        monitor.subscribe(my_callback)
        await monitor.start()
    """

    MAX_QUEUE_SIZE = 10000

    def __init__(self):
        """Initialize log monitor."""
        self._watchers: dict[str, LogWatcher] = {}
        self._queue: asyncio.Queue[LogEntry] = asyncio.Queue(
            maxsize=self.MAX_QUEUE_SIZE
        )
        self._subscribers: list[Callable[[LogEntry], Awaitable[None]]] = []
        self._running = False
        self._dispatch_task: asyncio.Task | None = None
        self._overflow_count = 0
        self._processed_count = 0

    def add_watcher(
        self, name: str, path: str, parser: BaseLogParser | None = None
    ) -> None:
        """Add a log file watcher.

        Args:
            name: Unique identifier for this watcher
            path: Path to the log file
            parser: Parser instance (defaults to SimpleLogParser)

        Raises:
            RuntimeError: If monitor is already running
        """
        if self._running:
            raise RuntimeError("Cannot add watcher while monitor is running")

        config = LogWatcherConfig(
            name=name,
            path=path,
            parser=parser or SimpleLogParser(),
        )
        self._watchers[name] = LogWatcher(config, self._queue)
        logger.info(f"Added log watcher '{name}' for {path}")

    def remove_watcher(self, name: str) -> None:
        """Remove a log file watcher.

        Args:
            name: Name of the watcher to remove

        Raises:
            RuntimeError: If monitor is already running
            KeyError: If watcher not found
        """
        if self._running:
            raise RuntimeError("Cannot remove watcher while monitor is running")

        if name not in self._watchers:
            raise KeyError(f"Watcher '{name}' not found")

        del self._watchers[name]
        logger.info(f"Removed log watcher '{name}'")

    def subscribe(self, callback: Callable[[LogEntry], Awaitable[None]]) -> None:
        """Subscribe to log entries.

        Args:
            callback: Async callback function that receives LogEntry

        Raises:
            RuntimeError: If monitor is already running
        """
        if self._running:
            raise RuntimeError("Cannot subscribe while monitor is running")

        self._subscribers.append(callback)
        logger.info(f"Added subscriber, total: {len(self._subscribers)}")

    def unsubscribe(self, callback: Callable[[LogEntry], Awaitable[None]]) -> bool:
        """Unsubscribe from log entries.

        Args:
            callback: Callback to remove

        Returns:
            True if unsubscribed, False if not found
        """
        if callback in self._subscribers:
            self._subscribers.remove(callback)
            logger.info(f"Removed subscriber, total: {len(self._subscribers)}")
            return True
        return False

    async def start(self) -> None:
        """Start all watchers and dispatch loop.

        Raises:
            RuntimeError: If already running
        """
        if self._running:
            raise RuntimeError("LogMonitor is already running")

        self._running = True
        logger.info("Starting LogMonitor...")

        # Start all watchers
        start_tasks = []
        for watcher in self._watchers.values():
            start_tasks.append(watcher.start())

        if start_tasks:
            await asyncio.gather(*start_tasks, return_exceptions=True)

        # Start dispatch loop
        self._dispatch_task = asyncio.create_task(
            self._dispatch_loop(), name="log-monitor-dispatch"
        )

        logger.info(
            f"LogMonitor started with {len(self._watchers)} watchers, "
            f"{len(self._subscribers)} subscribers"
        )

    async def stop(self) -> None:
        """Stop all watchers and dispatch loop."""
        if not self._running:
            return

        self._running = False
        logger.info("Stopping LogMonitor...")

        # Stop dispatch loop first
        if self._dispatch_task:
            self._dispatch_task.cancel()
            try:
                await self._dispatch_task
            except asyncio.CancelledError:
                pass
            self._dispatch_task = None

        # Stop all watchers concurrently
        stop_tasks = []
        for watcher in self._watchers.values():
            stop_tasks.append(watcher.stop())

        if stop_tasks:
            results = await asyncio.gather(*stop_tasks, return_exceptions=True)
            for watcher, result in zip(self._watchers.values(), results):
                if isinstance(result, Exception):
                    logger.error(
                        f"Error stopping watcher '{watcher.config.name}': {result}"
                    )

        # Clear queue
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except asyncio.QueueEmpty:
                break

        logger.info("LogMonitor stopped")

    async def _dispatch_loop(self) -> None:
        """Dispatch log entries to subscribers."""
        while self._running:
            try:
                # Wait for entry with timeout to allow checking _running
                entry = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                self._processed_count += 1

                # Dispatch to all subscribers concurrently
                if self._subscribers:
                    dispatch_tasks = [
                        self._safe_subscriber_call(subscriber, entry)
                        for subscriber in self._subscribers
                    ]
                    await asyncio.gather(*dispatch_tasks, return_exceptions=True)

                self._queue.task_done()

            except TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Dispatch loop error: {e}")

    async def _safe_subscriber_call(
        self, subscriber: Callable[[LogEntry], Awaitable[None]], entry: LogEntry
    ) -> None:
        """Safely call a subscriber with error handling."""
        try:
            await subscriber(entry)
        except Exception as e:
            logger.error(f"Subscriber error: {e}")

    def get_stats(self) -> dict:
        """Get monitor statistics.

        Returns:
            Dictionary with queue size, processed count, overflow count, etc.
        """
        return {
            "running": self._running,
            "watchers": len(self._watchers),
            "subscribers": len(self._subscribers),
            "queue_size": self._queue.qsize(),
            "queue_max": self.MAX_QUEUE_SIZE,
            "processed_count": self._processed_count,
            "overflow_count": self._overflow_count,
            "watchers_detail": {
                name: watcher.get_stats() for name, watcher in self._watchers.items()
            },
        }


class LogWatcher:
    """Watches a single log file and feeds entries to the queue.

    Uses polling-based file watching for simplicity and portability.
    Rate limits entries to prevent overwhelming the queue.
    """

    def __init__(self, config: LogWatcherConfig, queue: asyncio.Queue[LogEntry]):
        """Initialize log watcher.

        Args:
            config: Watcher configuration
            queue: Queue to feed entries to
        """
        self.config = config
        self._queue = queue
        self._running = False
        self._watch_task: asyncio.Task | None = None
        self._last_position = 0
        self._entries_count = 0
        self._entries_dropped = 0
        self._rate_limit_tokens = config.max_entries_per_second
        self._last_rate_limit_reset = asyncio.get_event_loop().time()

    async def start(self) -> None:
        """Start watching the log file."""
        if self._running:
            return

        self._running = True

        # Check if file exists and get initial position
        path = Path(self.config.path)
        if path.exists():
            self._last_position = path.stat().st_size
            logger.info(
                f"Started watcher '{self.config.name}' for {self.config.path} "
                f"(starting at position {self._last_position})"
            )
        else:
            logger.warning(
                f"Started watcher '{self.config.name}' for {self.config.path} "
                f"(file does not exist yet, will wait)"
            )

        self._watch_task = asyncio.create_task(
            self._watch_loop(), name=f"log-watcher-{self.config.name}"
        )

    async def stop(self) -> None:
        """Stop watching."""
        if not self._running:
            return

        self._running = False

        if self._watch_task:
            self._watch_task.cancel()
            try:
                await self._watch_task
            except asyncio.CancelledError:
                pass
            self._watch_task = None

        logger.info(f"Stopped watcher '{self.config.name}'")

    async def _watch_loop(self) -> None:
        """Main watch loop using polling."""
        path = Path(self.config.path)

        while self._running:
            try:
                if path.exists():
                    # Read new lines
                    await self._read_new_lines(path)

                # Wait before next check
                await asyncio.sleep(self.config.poll_interval)

            except Exception as e:
                logger.error(f"Watch error for {self.config.name}: {e}")
                await asyncio.sleep(5.0)  # Back off on error

    async def _read_new_lines(self, path: Path) -> None:
        """Read new lines from the file.

        Args:
            path: Path to the log file
        """
        try:
            # Get current file size
            current_size = path.stat().st_size

            # Check if file was truncated
            if current_size < self._last_position:
                logger.warning(f"Log file {path} was truncated, resetting to beginning")
                self._last_position = 0

            # Check if there's new content
            if current_size <= self._last_position:
                return

            # Read new content
            async with asyncio.Lock():  # Prevent concurrent reads
                with open(path, encoding="utf-8", errors="replace") as f:
                    f.seek(self._last_position)

                    for line in f:
                        line = line.rstrip("\n\r")
                        if line:
                            await self._process_line(line)

                    self._last_position = f.tell()

        except OSError as e:
            logger.error(f"Error reading log file {path}: {e}")

    async def _process_line(self, line: str) -> None:
        """Process a single log line.

        Args:
            line: Log line to process
        """
        # Check rate limit
        if not await self._check_rate_limit():
            self._entries_dropped += 1
            if self._entries_dropped % 100 == 1:
                logger.warning(
                    f"Rate limit exceeded for {self.config.name}, "
                    f"dropped {self._entries_dropped} entries"
                )
            return

        # Parse the line
        entry = self.config.parser.parse(line)
        if not entry:
            return

        # Add source metadata
        entry.metadata["watcher_name"] = self.config.name
        entry.metadata["log_path"] = self.config.path

        # Try to add to queue
        try:
            self._queue.put_nowait(entry)
            self._entries_count += 1
        except asyncio.QueueFull:
            # Queue is full, drop oldest entry and add new one
            try:
                dropped = self._queue.get_nowait()
                self._queue.task_done()
                logger.warning(
                    f"Log queue full, dropped oldest entry from {dropped.source}"
                )
                self._queue.put_nowait(entry)
                self._entries_count += 1
            except asyncio.QueueEmpty:
                pass

    async def _check_rate_limit(self) -> bool:
        """Check if we're within rate limits.

        Returns:
            True if entry can be processed, False if rate limited
        """
        now = asyncio.get_event_loop().time()

        # Reset tokens every second
        if now - self._last_rate_limit_reset >= 1.0:
            self._rate_limit_tokens = self.config.max_entries_per_second
            self._last_rate_limit_reset = now

        if self._rate_limit_tokens > 0:
            self._rate_limit_tokens -= 1
            return True

        return False

    def get_stats(self) -> dict:
        """Get watcher statistics.

        Returns:
            Dictionary with entry counts and status
        """
        return {
            "path": self.config.path,
            "running": self._running,
            "entries_processed": self._entries_count,
            "entries_dropped": self._entries_dropped,
            "last_position": self._last_position,
            "rate_limit": self.config.max_entries_per_second,
        }
