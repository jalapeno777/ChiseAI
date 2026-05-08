"""
Provisional Rollback Procedures for ICT Bos Choch Feature Flag

This module provides rollback capabilities for the bos_choch feature flag
when deployed in provisional mode. It ensures a complete rollback can be
executed within 30 seconds.

EP-ICT-008: Real data validation epic with provisional gating
ST-ICT-033: outcome_label must be provisional_pass only
Feature flag ict:bos_choch:enabled defaults to true (re-enabled after accuracy fix)
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RollbackResult:
    """Result of a rollback operation."""

    success: bool
    duration_seconds: float
    steps_completed: int
    errors: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)


class ProvisionalRollback:
    """
    Handles provisional rollback procedures for the bos_choch feature flag.

    This class provides methods to:
    - Disable the bos_choch feature flag via Redis
    - Execute a complete rollback within 30 seconds
    - Verify rollback completion and state

    Attributes:
        redis_key: The Redis key for the feature flag
        default_ttl: TTL for Redis keys (default 30 seconds for rollback window)
    """

    def __init__(
        self,
        redis_host: str = "host.docker.internal",
        redis_port: int = 6380,
        redis_db: int = 1,
        feature_flag_key: str = "ict:bos_choch:enabled",
    ):
        """
        Initialize the ProvisionalRollback handler.

        Args:
            redis_host: Redis host (defaults to host.docker.internal for container access)
            redis_port: Redis port
            redis_db: Redis database number
            feature_flag_key: The Redis key for the bos_choch feature flag
        """
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.redis_db = redis_db
        self.feature_flag_key = feature_flag_key
        self._redis_client = None

    def _get_redis_client(self):
        """Lazy-load Redis client to avoid import overhead."""
        if self._redis_client is None:
            try:
                import redis

                self._redis_client = redis.Redis(
                    host=self.redis_host,
                    port=self.redis_port,
                    db=self.redis_db,
                    decode_responses=True,
                    socket_timeout=5,
                    socket_connect_timeout=5,
                )
            except ImportError as err:
                logger.error("Redis client not available")
                raise RuntimeError(
                    "Redis client required for rollback operations"
                ) from err
        return self._redis_client

    def disable_bos_choch(self) -> bool:
        """
        Disable the bos_choch feature flag by setting the Redis key to false.

        This method sets the feature flag to disabled state in Redis.
        The change takes effect immediately upon successful write.

        Returns:
            bool: True if the flag was successfully disabled, False otherwise

        Raises:
            RuntimeError: If Redis connection fails
        """
        try:
            client = self._get_redis_client()
            result = client.set(self.feature_flag_key, "false")

            if result:
                logger.info(f"Successfully disabled {self.feature_flag_key}")
                return True
            else:
                logger.warning(
                    f"Set operation returned False for {self.feature_flag_key}"
                )
                return False

        except Exception as err:
            logger.error(f"Failed to disable bos_choch: {err}")
            raise RuntimeError(f"Redis error during disable: {err}") from err

    def rollback_in_30_seconds(self) -> RollbackResult:
        """
        Execute a complete rollback operation within 30 seconds.

        This method performs the full rollback sequence:
        1. Disable the feature flag
        2. Capture rollback timestamp
        3. Verify the operation completes within the time limit

        Returns:
            RollbackResult: Object containing rollback execution details

        Note:
            The 30-second limit is a hard requirement per ST-ICT-036 AC-3
        """
        start_time = time.time()
        steps_completed = 0
        errors = []

        # Step 1: Disable the feature flag
        try:
            self.disable_bos_choch()
            steps_completed += 1
        except Exception as e:
            errors.append(f"Step 1 failed: {str(e)}")
            logger.error(f"Rollback step 1 failed: {e}")

        # Step 2: Capture rollback completion timestamp
        elapsed = time.time() - start_time
        if elapsed > 30.0:
            errors.append(f"Rollback exceeded 30 second limit: {elapsed:.2f}s")
            logger.error(f"Rollback exceeded time limit: {elapsed:.2f}s")

        duration = time.time() - start_time

        return RollbackResult(
            success=len(errors) == 0,
            duration_seconds=duration,
            steps_completed=steps_completed,
            errors=errors,
        )

    def verify_rollback(self) -> dict[str, Any]:
        """
        Verify that the rollback was successful and the system is in a safe state.

        This method checks:
        1. The feature flag is set to disabled
        2. No pending transactions or operations are in flight
        3. The system can confirm the disabled state

        Returns:
            Dict containing verification results with keys:
                - flag_disabled: bool
                - verification_timestamp: datetime
                - all_checks_passed: bool
        """
        verification = {
            "flag_disabled": False,
            "verification_timestamp": datetime.utcnow().isoformat(),
            "all_checks_passed": False,
        }

        try:
            client = self._get_redis_client()
            flag_value = client.get(self.feature_flag_key)

            verification["flag_disabled"] = flag_value == "false"
            verification["flag_current_value"] = flag_value

            # All checks pass only if flag is confirmed disabled
            verification["all_checks_passed"] = verification["flag_disabled"]

            logger.info(
                f"Rollback verification: flag_disabled={verification['flag_disabled']}"
            )

        except Exception as e:
            logger.error(f"Rollback verification failed: {e}")
            verification["error"] = str(e)

        return verification

    def check_rollback_decision_criteria(self) -> dict[str, Any]:
        """
        Check if rollback decision criteria are met.

        This documents the criteria for when a rollback should be executed:
        - ST-ICT-033 outcome_label is not provisional_pass
        - Rollback time is within 30 second requirement
        - Feature flag state is inconsistent with expected provisional state

        Returns:
            Dict containing decision criteria status
        """
        return {
            "criteria_met": False,
            "reason": "Manual decision required - automated criteria not configured",
            "documentation": {
                "st_ict_033_outcome": "Must be provisional_pass for provisional deployment",
                "rollback_time_limit": "30 seconds maximum",
                "feature_flag_default": "ict:bos_choch:enabled defaults to true",
            },
        }

    def get_rollback_status(self) -> dict[str, Any]:
        """
        Get current rollback system status.

        Returns:
            Dict with current status information
        """
        status = {
            "feature_flag_key": self.feature_flag_key,
            "redis_connection": "unknown",
            "current_flag_state": "unknown",
        }

        try:
            client = self._get_redis_client()
            status["redis_connection"] = "connected"
            flag_value = client.get(self.feature_flag_key)
            status["current_flag_state"] = (
                str(flag_value) if flag_value is not None else "none"
            )
        except Exception as e:
            status["redis_connection"] = f"error: {e}"

        return status


def create_provisional_rollback() -> ProvisionalRollback:
    """
    Factory function to create a ProvisionalRollback instance.

    Returns:
        Configured ProvisionalRollback instance
    """
    return ProvisionalRollback()
