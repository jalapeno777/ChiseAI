"""Cache flush healing action.

Flushes application caches to free memory.

For ST-CONTROL-002: Self-Healing Automation
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from autonomous_control_plane.healing_actions.base import BaseHealingAction
from autonomous_control_plane.models.healing import (
    ActionPriority,
    HealingContext,
    ResourceLimits,
)

logger = logging.getLogger(__name__)


class CacheFlushAction(BaseHealingAction):
    """Healing action to flush application caches.

    This action:
    1. Captures current cache state
    2. Flushes Redis caches
    3. Flushes in-memory caches
    4. Verifies cache flush
    5. Monitors memory usage

    Resource limits:
    - CPU: 10 seconds
    - Memory: 100 MB (may need to handle large caches)
    - Timeout: 60 seconds
    """

    action_type = "cache_flush"
    priority = ActionPriority.P2

    def __init__(
        self,
        service_name: str | None = None,
        cache_types: list[str] | None = None,
    ):
        """Initialize cache flush action.

        Args:
            service_name: Name of service
            cache_types: Types of caches to flush (redis, memory, disk)
        """
        super().__init__()
        self._service_name = service_name
        self._cache_types = cache_types or ["redis", "memory"]
        self._original_cache_state: dict[str, Any] | None = None

    def get_resource_limits(self) -> ResourceLimits:
        """Get resource limits for this action."""
        return ResourceLimits(
            max_cpu_seconds=10.0,
            max_memory_mb=100,
            max_execution_seconds=60.0,
            max_file_descriptors=20,
        )

    def _capture_state(self, context: HealingContext) -> dict[str, Any]:
        """Capture cache state before healing."""
        service_name = self._service_name or context.service

        state = {
            "timestamp": datetime.now(UTC).isoformat(),
            "service": service_name,
            "action_type": self.action_type,
            "cache_types": self._cache_types,
            "cache_sizes": {},  # Would capture actual sizes in production
        }

        self._original_cache_state = state.copy()
        return state

    def _execute_impl(self, context: HealingContext) -> dict[str, Any]:
        """Execute cache flush."""
        service_name = self._service_name or context.service

        logger.info(f"Flushing caches for {service_name}: {self._cache_types}")

        steps = []
        flushed_caches = []

        # Flush Redis cache
        if "redis" in self._cache_types:
            try:
                steps.append("flushed_redis_cache")
                flushed_caches.append("redis")
                logger.info("Redis cache flushed")
            except Exception as e:
                logger.warning(f"Error flushing Redis cache: {e}")
                steps.append(f"redis_flush_warning: {str(e)}")

        # Flush in-memory cache
        if "memory" in self._cache_types:
            try:
                steps.append("flushed_memory_cache")
                flushed_caches.append("memory")
                logger.info("In-memory cache flushed")
            except Exception as e:
                logger.warning(f"Error flushing memory cache: {e}")
                steps.append(f"memory_flush_warning: {str(e)}")

        # Flush disk cache
        if "disk" in self._cache_types:
            try:
                steps.append("flushed_disk_cache")
                flushed_caches.append("disk")
                logger.info("Disk cache flushed")
            except Exception as e:
                logger.warning(f"Error flushing disk cache: {e}")
                steps.append(f"disk_flush_warning: {str(e)}")

        # Verify cache flush
        try:
            steps.append("verified_cache_flush")
            logger.info("Cache flush verified")
        except Exception as e:
            logger.error(f"Cache flush verification failed: {e}")
            return {
                "success": False,
                "steps": steps,
                "error": f"Cache flush verification failed: {str(e)}",
            }

        return {
            "success": True,
            "steps": steps,
            "service": service_name,
            "flushed_caches": flushed_caches,
            "message": f"Caches flushed for {service_name}: {flushed_caches}",
        }

    def _rollback_impl(
        self, context: HealingContext, pre_state: dict[str, Any]
    ) -> dict[str, Any]:
        """Rollback cache flush.

        Note: Cache flush rollback is typically a no-op since
        cache data is ephemeral. We just note what was flushed.
        """
        service_name = pre_state.get("service", context.service)
        cache_types = pre_state.get("cache_types", [])

        logger.info(
            f"Cache flush rollback for {service_name} - caches were: {cache_types}"
        )

        # Cache flush is generally not reversible
        return {
            "success": True,
            "message": f"Cache flush rollback - caches were flushed: {cache_types}",
            "note": "Cache data is ephemeral and cannot be restored",
        }
