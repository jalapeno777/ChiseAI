"""Error handler for Discord bot with exponential backoff and ops notifications.

Handles:
- Global error handling for bot events
- Exponential backoff for API failures
- Ops notification integration via webhook
- Graceful degradation
"""

from __future__ import annotations

import asyncio
import logging
import traceback
from collections import defaultdict
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ErrorSeverity(Enum):
    """Severity levels for errors."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DiscordError(Exception):
    """Base exception for Discord operations."""

    def __init__(self, message: str, severity: ErrorSeverity = ErrorSeverity.MEDIUM):
        self.message = message
        self.severity = severity
        super().__init__(message)


class RateLimitError(DiscordError):
    """Raised when Discord API rate limit is hit."""

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message, ErrorSeverity.HIGH)
        self.retry_after = retry_after


class APIError(DiscordError):
    """Raised when Discord API returns an error."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message, ErrorSeverity.HIGH)
        self.status_code = status_code


class AuthenticationError(DiscordError):
    """Raised when Discord authentication fails."""

    def __init__(self, message: str):
        super().__init__(message, ErrorSeverity.CRITICAL)


class PermissionError(DiscordError):
    """Raised when bot lacks required permissions."""

    def __init__(self, message: str):
        super().__init__(message, ErrorSeverity.HIGH)


class ErrorHandler:
    """Handles errors for Discord bot with retry logic and ops notifications.

    Features:
    - Exponential backoff for transient failures
    - Configurable retry limits
    - Ops channel notifications for critical errors
    - Error history tracking
    - Graceful degradation
    """

    DEFAULT_MAX_RETRIES = 3
    DEFAULT_INITIAL_BACKOFF = 1.0
    DEFAULT_MAX_BACKOFF = 60.0
    DEFAULT_BACKOFF_MULTIPLIER = 2.0

    def __init__(
        self,
        max_retries: int = DEFAULT_MAX_RETRIES,
        initial_backoff: float = DEFAULT_INITIAL_BACKOFF,
        max_backoff: float = DEFAULT_MAX_BACKOFF,
        backoff_multiplier: float = DEFAULT_BACKOFF_MULTIPLIER,
        ops_webhook_url: str | None = None,
        ops_channel_id: str | None = None,
    ):
        """Initialize error handler.

        Args:
            max_retries: Maximum number of retry attempts.
            initial_backoff: Initial backoff delay in seconds.
            max_backoff: Maximum backoff delay in seconds.
            backoff_multiplier: Multiplier for exponential backoff.
            ops_webhook_url: Webhook URL for ops notifications.
            ops_channel_id: Channel ID for ops notifications.
        """
        self._max_retries = max_retries
        self._initial_backoff = initial_backoff
        self._max_backoff = max_backoff
        self._backoff_multiplier = backoff_multiplier

        self._ops_webhook_url = ops_webhook_url
        self._ops_channel_id = ops_channel_id

        # Error history for monitoring
        self._error_history: list[dict[str, Any]] = []
        self._max_history_size = 100

        # Track consecutive failures per error type
        self._consecutive_failures: dict[str, int] = defaultdict(int)

    def _calculate_backoff(self, attempt: int) -> float:
        """Calculate backoff delay for given attempt.

        Args:
            attempt: Current retry attempt (0-indexed).

        Returns:
            Backoff delay in seconds.
        """
        backoff = self._initial_backoff * (self._backoff_multiplier**attempt)
        return min(backoff, self._max_backoff)

    async def with_retry(
        self,
        operation: str,
        coro,
        *args,
        retryable_exceptions: tuple = (RateLimitError, APIError, asyncio.TimeoutError),
        **kwargs,
    ) -> Any:
        """Execute an async operation with retry logic.

        Args:
            operation: Name of the operation for logging.
            coro: Coroutine to execute.
            *args: Positional arguments for coro.
            retryable_exceptions: Exceptions that trigger retry.
            **kwargs: Keyword arguments for coro.

        Returns:
            Result of the coroutine.

        Raises:
            The last exception if all retries fail.
        """
        last_exception = None

        for attempt in range(self._max_retries + 1):
            try:
                result = await coro(*args, **kwargs)
                if attempt > 0:
                    logger.info("%s succeeded on retry attempt %d", operation, attempt)
                return result

            except retryable_exceptions as e:
                last_exception = e
                self._consecutive_failures[operation] += 1

                if attempt < self._max_retries:
                    backoff = self._calculate_backoff(attempt)
                    logger.warning(
                        "%s failed (attempt %d/%d): %s. Retrying in %.1fs",
                        operation,
                        attempt + 1,
                        self._max_retries + 1,
                        str(e),
                        backoff,
                    )

                    # Special handling for rate limits
                    if isinstance(e, RateLimitError) and e.retry_after:
                        backoff = max(backoff, e.retry_after)
                        logger.info("Using rate limit retry_after: %.1fs", backoff)

                    await asyncio.sleep(backoff)
                else:
                    logger.error(
                        "%s failed after %d attempts: %s",
                        operation,
                        self._max_retries + 1,
                        str(e),
                    )

            except Exception as e:
                # Non-retryable exception
                last_exception = e
                self._record_error(
                    operation=operation,
                    error=str(e),
                    severity=ErrorSeverity.HIGH,
                    exc_info=True,
                )
                raise

        # All retries failed
        self._record_error(
            operation=operation,
            error=str(last_exception),
            severity=ErrorSeverity.HIGH,
        )
        raise last_exception

    def _record_error(
        self,
        operation: str,
        error: str,
        severity: ErrorSeverity,
        exc_info: bool = False,
    ) -> None:
        """Record an error in history.

        Args:
            operation: Name of the operation that failed.
            error: Error message.
            severity: Error severity level.
            exc_info: Whether to include traceback.
        """
        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "operation": operation,
            "error": error,
            "severity": severity.value,
            "traceback": traceback.format_exc() if exc_info else None,
        }

        self._error_history.append(entry)

        # Trim history if needed
        if len(self._error_history) > self._max_history_size:
            self._error_history = self._error_history[-self._max_history_size :]

        # Log based on severity
        if severity == ErrorSeverity.CRITICAL:
            logger.critical("CRITICAL Discord error in %s: %s", operation, error)
        elif severity == ErrorSeverity.HIGH:
            logger.error("Discord error in %s: %s", operation, error)
        elif severity == ErrorSeverity.MEDIUM:
            logger.warning("Discord warning in %s: %s", operation, error)
        else:
            logger.info("Discord info in %s: %s", operation, error)

    async def handle_event_error(
        self,
        event: str,
        error: Exception,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Handle an error from a Discord event.

        Args:
            event: Name of the event (e.g., 'on_message', 'on_ready').
            error: The exception that occurred.
            context: Additional context about the error.
        """
        # Determine severity
        if isinstance(error, AuthenticationError):
            severity = ErrorSeverity.CRITICAL
        elif isinstance(error, (PermissionError, RateLimitError)):
            severity = ErrorSeverity.HIGH
        elif isinstance(error, APIError):
            severity = ErrorSeverity.MEDIUM
        else:
            severity = ErrorSeverity.MEDIUM

        context_str = ""
        if context:
            context_str = f" | Context: {context}"

        self._record_error(
            operation=f"event:{event}",
            error=f"{type(error).__name__}: {str(error)}{context_str}",
            severity=severity,
            exc_info=True,
        )

        # Send ops notification for high severity errors
        if severity in (ErrorSeverity.HIGH, ErrorSeverity.CRITICAL):
            await self._send_ops_notification(
                event=event,
                error=error,
                severity=severity,
                context=context,
            )

    async def _send_ops_notification(
        self,
        event: str,
        error: Exception,
        severity: ErrorSeverity,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Send notification to ops channel about critical error.

        Args:
            event: Name of the event.
            error: The exception.
            severity: Error severity.
            context: Additional context.
        """
        if not self._ops_webhook_url and not self._ops_channel_id:
            logger.debug("No ops channel configured, skipping notification")
            return

        try:
            import aiohttp

            severity_emoji = {
                ErrorSeverity.HIGH: "🔴",
                ErrorSeverity.CRITICAL: "🚨",
            }.get(severity, "⚠️")

            embed = {
                "title": f"{severity_emoji} Discord Bot Error - {severity.value.upper()}",
                "color": 0xFF0000 if severity == ErrorSeverity.CRITICAL else 0xFF8800,
                "fields": [
                    {"name": "Event", "value": event, "inline": True},
                    {
                        "name": "Error Type",
                        "value": type(error).__name__,
                        "inline": True,
                    },
                    {"name": "Error Message", "value": str(error)[:1024]},
                ],
                "timestamp": datetime.now(UTC).isoformat(),
            }

            if context:
                context_str = "\n".join(f"• {k}: {v}" for k, v in context.items())
                embed["fields"].append({"name": "Context", "value": context_str[:1024]})

            # Add traceback for critical errors
            if severity == ErrorSeverity.CRITICAL:
                tb = traceback.format_exc()
                if len(tb) < 1024:
                    embed["fields"].append(
                        {"name": "Traceback", "value": f"```\n{tb}\n```"}
                    )

            payload = {"embeds": [embed]}

            if self._ops_webhook_url:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        self._ops_webhook_url,
                        json=payload,
                        headers={"Content-Type": "application/json"},
                    ) as resp:
                        if resp.status in (200, 204):
                            logger.info("Ops notification sent successfully")
                        else:
                            logger.warning(
                                "Ops notification failed with status %d", resp.status
                            )

        except Exception as e:
            logger.error("Failed to send ops notification: %s", str(e))

    def get_error_summary(self) -> dict[str, Any]:
        """Get summary of recent errors.

        Returns:
            Dictionary with error statistics.
        """
        if not self._error_history:
            return {
                "total_errors": 0,
                "by_severity": {},
                "by_operation": {},
                "recent_errors": [],
                "consecutive_failures": dict(self._consecutive_failures),
            }

        by_severity: dict[str, int] = {}
        by_operation: dict[str, int] = {}

        for entry in self._error_history:
            severity = entry["severity"]
            operation = entry["operation"]
            by_severity[severity] = by_severity.get(severity, 0) + 1
            by_operation[operation] = by_operation.get(operation, 0) + 1

        return {
            "total_errors": len(self._error_history),
            "by_severity": by_severity,
            "by_operation": by_operation,
            "recent_errors": self._error_history[-10:],
            "consecutive_failures": dict(self._consecutive_failures),
        }

    def get_recent_errors(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get recent errors.

        Args:
            limit: Maximum number of errors to return.

        Returns:
            List of recent error entries.
        """
        return self._error_history[-limit:]
