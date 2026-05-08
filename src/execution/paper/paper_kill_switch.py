"""Paper Trading Kill Switch Manager.

Redis-based kill switch for paper trading that stops signal processing
and trade execution when activated.

Uses Redis key `paper:kill_switch` with TTL-based auto-expiry.
Default TTL: 1 hour (3600 seconds), configurable via KILL_SWITCH_TTL_SECONDS.

For PAPER-009: Emergency kill switch for paper trading
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from execution.paper.redis_config import (
    get_redis_client as _get_async_redis_client,
)
from execution.paper.redis_config import (
    get_redis_client_sync,
)

logger = logging.getLogger(__name__)

# Redis key for paper trading kill switch
PAPER_KILL_SWITCH_KEY = "paper:kill_switch"

# Default TTL in seconds (1 hour)
DEFAULT_TTL_SECONDS = int(os.getenv("KILL_SWITCH_TTL_SECONDS", "3600"))


@dataclass
class PaperKillSwitchStatus:
    """Status of the paper trading kill switch.

    Attributes:
        active: Whether kill switch is currently active
        reason: Reason for activation (empty if not active)
        activated_at: ISO timestamp when activated (None if not active)
        activated_by: Who/what activated the kill switch (empty if not active)
        ttl_remaining: Seconds until auto-expiry (None if not active)
    """

    active: bool = False
    reason: str = ""
    activated_at: str | None = None
    activated_by: str = ""
    ttl_remaining: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "active": self.active,
            "reason": self.reason,
            "activated_at": self.activated_at,
            "activated_by": self.activated_by,
            "ttl_remaining": self.ttl_remaining,
        }

    def __str__(self) -> str:
        """Human-readable string representation."""
        if not self.active:
            return "Paper kill switch: INACTIVE (processing enabled)"
        return (
            f"Paper kill switch: ACTIVE\n"
            f"  Reason: {self.reason}\n"
            f"  Activated by: {self.activated_by}\n"
            f"  Activated at: {self.activated_at}\n"
            f"  TTL remaining: {self.ttl_remaining}s"
        )


class PaperKillSwitchManager:
    """Manager for paper trading kill switch.

    Provides a Redis-based kill switch that can stop paper trading
    without closing positions. Unlike the live trading kill switch
    (KillSwitchExecutor), this simply blocks new signal processing
    and trade execution.

    Attributes:
        redis_client: Redis client instance
        default_ttl: Default TTL in seconds for kill switch activation
    """

    CACHE_TTL_SECONDS: float = 30.0

    def __init__(
        self,
        redis_client: Any | None = None,
        default_ttl: int = DEFAULT_TTL_SECONDS,
    ):
        """Initialize paper kill switch manager.

        Args:
            redis_client: Redis client (async). If None, creates new connection.
            default_ttl: Default TTL in seconds for kill switch activation.
        """
        self._redis = redis_client
        self._owns_redis = redis_client is None
        self.default_ttl = default_ttl
        self._status_cache: PaperKillSwitchStatus | None = None
        self._status_cache_time: float | None = None

    def _invalidate_cache(self) -> None:
        """Invalidate the status cache."""
        self._status_cache = None
        self._status_cache_time = None

    async def _get_redis(self) -> Any:
        """Get or create Redis client."""
        if self._redis is None:
            self._redis = _get_async_redis_client(decode_responses=True)
        return self._redis

    async def close(self) -> None:
        """Close Redis connection if we own it."""
        if self._owns_redis and self._redis:
            await self._redis.close()
            self._redis = None

    async def get_status(self) -> PaperKillSwitchStatus:
        """Get current kill switch status.

        Returns cached status if within CACHE_TTL_SECONDS, otherwise
        fetches fresh status from Redis.

        Returns:
            PaperKillSwitchStatus with current state
        """
        # Return cached status if still fresh
        if (
            self._status_cache is not None
            and self._status_cache_time is not None
            and time.time() - self._status_cache_time < self.CACHE_TTL_SECONDS
        ):
            return self._status_cache

        try:
            redis = await self._get_redis()
            data = await redis.hgetall(PAPER_KILL_SWITCH_KEY)

            if not data:
                # Fallback: check if activated via simple SET command
                # (wrong key type but rescue it)
                try:
                    simple_val = await redis.get("paper:kill_switch:global")
                    if simple_val and (
                        simple_val.decode()
                        if isinstance(simple_val, bytes)
                        else simple_val
                    ) in ("true", "1", "yes"):
                        logger.warning(
                            "Kill switch activated via SET key fallback "
                            "(paper:kill_switch:global)"
                        )
                        fallback_status = PaperKillSwitchStatus(
                            active=True,
                            reason="emergency_manual_activation",
                            activated_at=datetime.now(UTC).isoformat(),
                            activated_by="manual_redis_set",
                        )
                        self._status_cache = fallback_status
                        self._status_cache_time = time.time()
                        return fallback_status
                except Exception as fallback_exc:
                    logger.debug(
                        "Kill switch SET fallback check failed: %s", fallback_exc
                    )

                status = PaperKillSwitchStatus(active=False)
                self._status_cache = status
                self._status_cache_time = time.time()
                return status

            # Get TTL for remaining time
            ttl = await redis.ttl(PAPER_KILL_SWITCH_KEY)
            if ttl < 0:
                # Key doesn't exist or has no TTL
                status = PaperKillSwitchStatus(active=False)
                self._status_cache = status
                self._status_cache_time = time.time()
                return status

            status = PaperKillSwitchStatus(
                active=True,
                reason=data.get("reason", ""),
                activated_at=data.get("activated_at"),
                activated_by=data.get("activated_by", ""),
                ttl_remaining=ttl,
            )
            self._status_cache = status
            self._status_cache_time = time.time()
            return status

        except Exception as e:
            logger.error(f"Failed to get kill switch status: {e}")
            # Fail safe: treat as inactive to not block trading
            return PaperKillSwitchStatus(active=False)

    async def is_active(self) -> bool:
        """Check if kill switch is currently active.

        Returns:
            True if kill switch is active, False otherwise
        """
        status = await self.get_status()
        return status.active

    async def activate(
        self,
        reason: str,
        activated_by: str = "manual",
        ttl: int | None = None,
    ) -> bool:
        """Activate the paper trading kill switch.

        Args:
            reason: Reason for activation
            activated_by: Who/what is activating (default: "manual")
            ttl: TTL in seconds (default: self.default_ttl)

        Returns:
            True if successfully activated, False otherwise
        """
        if ttl is None:
            ttl = self.default_ttl

        try:
            redis = await self._get_redis()
            activated_at = datetime.now(UTC).isoformat()

            # Build the data structure
            data = {
                "active": "true",
                "reason": reason,
                "activated_at": activated_at,
                "activated_by": activated_by,
            }

            # Use pipeline for atomic set + expire
            async with redis.pipeline(transaction=True) as pipe:
                await pipe.hset(PAPER_KILL_SWITCH_KEY, mapping=data)
                await pipe.expire(PAPER_KILL_SWITCH_KEY, ttl)
                await pipe.execute()

            logger.warning(
                f"PAPER KILL SWITCH ACTIVATED: {reason} (by={activated_by}, ttl={ttl}s)"
            )

            # Invalidate cache and set to new active status
            self._status_cache = PaperKillSwitchStatus(
                active=True,
                reason=reason,
                activated_at=activated_at,
                activated_by=activated_by,
                ttl_remaining=ttl,
            )
            self._status_cache_time = time.time()

            return True

        except Exception as e:
            logger.error(f"Failed to activate kill switch: {e}")
            return False

    async def deactivate(self) -> bool:
        """Deactivate the paper trading kill switch.

        Returns:
            True if successfully deactivated (or was already inactive), False on error
        """
        try:
            redis = await self._get_redis()
            await redis.delete(PAPER_KILL_SWITCH_KEY)

            logger.info("Paper kill switch deactivated")
            self._invalidate_cache()
            return True

        except Exception as e:
            logger.error(f"Failed to deactivate kill switch: {e}")
            return False

    async def check_and_raise_if_active(self) -> None:
        """Check kill switch and raise exception if active.

        Raises:
            PaperKillSwitchActiveError: If kill switch is active
        """
        status = await self.get_status()
        if status.active:
            raise PaperKillSwitchActiveError(
                f"Paper kill switch is active: {status.reason}"
            )


class PaperKillSwitchActiveError(Exception):
    """Raised when paper trading kill switch is active."""

    def __init__(self, message: str = "Paper kill switch is active"):
        self.message = message
        super().__init__(self.message)


# Convenience functions for synchronous contexts (CLI scripts)
def get_redis_client() -> Any:  # noqa: D401 — kept for backward compat
    """Get a synchronous Redis client for CLI scripts."""
    return get_redis_client_sync(decode_responses=True)


# Module-level cache for sync convenience functions
_sync_status_cache: PaperKillSwitchStatus | None = None
_sync_status_cache_time: float | None = None


def _invalidate_sync_cache() -> None:
    """Invalidate the module-level sync status cache."""
    global _sync_status_cache, _sync_status_cache_time
    _sync_status_cache = None
    _sync_status_cache_time = None


def get_status_sync() -> PaperKillSwitchStatus:
    """Get current kill switch status (synchronous).

    Returns cached status if within CACHE_TTL_SECONDS, otherwise
    fetches fresh status from Redis.

    Returns:
        PaperKillSwitchStatus with current state
    """
    global _sync_status_cache, _sync_status_cache_time

    # Return cached status if still fresh
    if (
        _sync_status_cache is not None
        and _sync_status_cache_time is not None
        and time.time() - _sync_status_cache_time
        < PaperKillSwitchManager.CACHE_TTL_SECONDS
    ):
        return _sync_status_cache

    try:
        redis = get_redis_client()
        data = redis.hgetall(PAPER_KILL_SWITCH_KEY)

        if not data:
            # Fallback: check if activated via simple SET command
            try:
                simple_val = redis.get("paper:kill_switch:global")
                if simple_val and (
                    simple_val.decode() if isinstance(simple_val, bytes) else simple_val
                ) in ("true", "1", "yes"):
                    logger.warning(
                        "Kill switch activated via SET key fallback (sync) "
                        "(paper:kill_switch:global)"
                    )
                    fallback_status = PaperKillSwitchStatus(
                        active=True,
                        reason="emergency_manual_activation",
                        activated_at=datetime.now(UTC).isoformat(),
                        activated_by="manual_redis_set",
                    )
                    _sync_status_cache = fallback_status
                    _sync_status_cache_time = time.time()
                    return fallback_status
            except Exception as fallback_exc:
                logger.debug(
                    "Kill switch SET fallback check (sync) failed: %s",
                    fallback_exc,
                )

            _sync_status_cache = PaperKillSwitchStatus(active=False)
            _sync_status_cache_time = time.time()
            return _sync_status_cache

        ttl = redis.ttl(PAPER_KILL_SWITCH_KEY)
        if ttl < 0:
            _sync_status_cache = PaperKillSwitchStatus(active=False)
            _sync_status_cache_time = time.time()
            return _sync_status_cache

        status = PaperKillSwitchStatus(
            active=True,
            reason=data.get("reason", ""),
            activated_at=data.get("activated_at"),
            activated_by=data.get("activated_by", ""),
            ttl_remaining=ttl,
        )
        _sync_status_cache = status
        _sync_status_cache_time = time.time()
        return status

    except Exception as e:
        logger.error(f"Failed to get kill switch status: {e}")
        return PaperKillSwitchStatus(active=False)


def activate_sync(
    reason: str,
    activated_by: str = "manual",
    ttl: int | None = None,
) -> bool:
    """Activate the paper trading kill switch (synchronous).

    Args:
        reason: Reason for activation
        activated_by: Who/what is activating (default: "manual")
        ttl: TTL in seconds (default: from DEFAULT_TTL_SECONDS)

    Returns:
        True if successfully activated, False otherwise
    """
    if ttl is None:
        ttl = DEFAULT_TTL_SECONDS

    try:
        redis = get_redis_client()
        from datetime import UTC as dt_UTC

        activated_at = datetime.now(dt_UTC).isoformat()

        data = {
            "active": "true",
            "reason": reason,
            "activated_at": activated_at,
            "activated_by": activated_by,
        }

        pipe = redis.pipeline(transaction=True)
        pipe.hset(PAPER_KILL_SWITCH_KEY, mapping=data)
        pipe.expire(PAPER_KILL_SWITCH_KEY, ttl)
        pipe.execute()

        logger.warning(
            f"PAPER KILL SWITCH ACTIVATED: {reason} (by={activated_by}, ttl={ttl}s)"
        )

        # Invalidate cache and set to new active status
        global _sync_status_cache, _sync_status_cache_time
        _sync_status_cache = PaperKillSwitchStatus(
            active=True,
            reason=reason,
            activated_at=activated_at,
            activated_by=activated_by,
            ttl_remaining=ttl,
        )
        _sync_status_cache_time = time.time()

        return True

    except Exception as e:
        logger.error(f"Failed to activate kill switch: {e}")
        return False


def deactivate_sync() -> bool:
    """Deactivate the paper trading kill switch (synchronous).

    Returns:
        True if successfully deactivated, False otherwise
    """
    try:
        redis = get_redis_client()
        redis.delete(PAPER_KILL_SWITCH_KEY)

        logger.info("Paper kill switch deactivated")
        _invalidate_sync_cache()
        return True

    except Exception as e:
        logger.error(f"Failed to deactivate kill switch: {e}")
        return False
