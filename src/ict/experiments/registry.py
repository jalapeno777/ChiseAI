"""Experiment Registry.

Manages experiment lifecycle and persistence in Redis,
providing CRUD operations for experiment tracking.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import redis

from src.ict.experiments.key_schema import ExperimentKey

logger = logging.getLogger(__name__)


class ExperimentRegistry:
    """Registry for managing ICT experiments in Redis.

    This registry:
    - Registers new experiments with Redis persistence
    - Tracks active experiments
    - Provides experiment status queries
    - Supports experiment completion/closing

    Attributes:
        _redis: Redis client for persistence
    """

    def __init__(self, redis_client: redis.Redis | None = None) -> None:
        """Initialize the experiment registry.

        Args:
            redis_client: Optional Redis client. If not provided,
                         creates one from environment or localhost.
        """
        self._redis = redis_client

    def _get_redis(self) -> redis.Redis:
        """Get or create Redis client.

        Returns:
            Redis client instance
        """
        if self._redis is None:
            import redis as redis_lib

            host = os.environ.get("REDIS_HOST", "localhost")
            port = int(os.environ.get("REDIS_PORT", "6379"))
            self._redis = redis_lib.Redis(host=host, port=port, decode_responses=True)
        return self._redis

    def register_experiment(self, key: ExperimentKey) -> bool:
        """Register a new experiment.

        Args:
            key: Experiment key to register

        Returns:
            True if registered successfully, False if already exists
        """
        redis_client = self._get_redis()
        registry_key = f"ict:exp:registry:{key.experiment_id}:{key.variant}"

        # Check if already exists
        if redis_client.exists(registry_key):
            logger.warning(f"Experiment already registered: {key}")
            return False

        # Store experiment metadata
        data = {
            "experiment_id": key.experiment_id,
            "variant": key.variant,
            "started_at": key.started_at.isoformat(),
            "status": "active",
        }
        redis_client.hset(registry_key, mapping=data)
        redis_client.expire(registry_key, 86400 * 30)  # 30 day TTL

        # Add to active experiments set
        redis_client.sadd("ict:exp:active", registry_key)

        logger.info(f"Registered experiment: {key}")
        return True

    def get_active_experiments(self) -> list[dict[str, Any]]:
        """Get all active experiments.

        Returns:
            List of active experiment metadata dictionaries
        """
        redis_client = self._get_redis()
        active_keys = redis_client.smembers("ict:exp:active")

        experiments = []
        for key in active_keys:
            if isinstance(key, bytes):
                key = key.decode("utf-8")
            data = redis_client.hgetall(key)
            if data:
                experiments.append(data)

        return experiments

    def is_experiment_active(
        self, experiment_id: str, variant: str | None = None
    ) -> bool:
        """Check if an experiment is active.

        Args:
            experiment_id: Experiment identifier
            variant: Optional variant to check

        Returns:
            True if experiment is active
        """
        redis_client = self._get_redis()

        if variant:
            registry_key = f"ict:exp:registry:{experiment_id}:{variant}"
            return redis_client.exists(registry_key) == 1

        # Check any variant of this experiment
        pattern = f"ict:exp:registry:{experiment_id}:*"
        keys = redis_client.keys(pattern)
        return len(keys) > 0

    def close_experiment(self, key: ExperimentKey) -> bool:
        """Mark an experiment as completed.

        Args:
            key: Experiment key to close

        Returns:
            True if closed successfully, False if not found
        """
        redis_client = self._get_redis()
        registry_key = f"ict:exp:registry:{key.experiment_id}:{key.variant}"

        # Check if exists
        if not redis_client.exists(registry_key):
            logger.warning(f"Experiment not found: {key}")
            return False

        # Update status
        redis_client.hset(registry_key, "status", "completed")
        redis_client.hset(registry_key, "ended_at", datetime.now(UTC).isoformat())

        # Remove from active set
        redis_client.srem("ict:exp:active", registry_key)

        logger.info(f"Closed experiment: {key}")
        return True

    def get_experiment_status(
        self, experiment_id: str, variant: str
    ) -> dict[str, Any] | None:
        """Get status of a specific experiment.

        Args:
            experiment_id: Experiment identifier
            variant: Experiment variant

        Returns:
            Experiment metadata or None if not found
        """
        redis_client = self._get_redis()
        registry_key = f"ict:exp:registry:{experiment_id}:{variant}"

        data = redis_client.hgetall(registry_key)
        return data if data else None
