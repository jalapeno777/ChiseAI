"""
Redis-based idempotency checker for autocog jobs.

Prevents duplicate job runs within the same cadence window using Redis
with automatic TTL based on cadence type.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any

import redis

logger = logging.getLogger(__name__)

# Cadence to TTL mapping in seconds
CADENCE_TTL_SECONDS = {
    "hourly": 3600,  # 1 hour
    "6hourly": 21600,  # 6 hours
    "daily": 86400,  # 24 hours
    "weekly": 604800,  # 7 days
    "monthly": 2592000,  # 30 days
}


class IdempotencyChecker:
    """
    Redis-based idempotency system for autocog jobs.

    Prevents duplicate job runs within the same cadence window by tracking
    job completions with automatic TTL expiration.
    """

    def __init__(
        self, redis_client: redis.Redis | None = None, key_prefix: str = "autocog:job"
    ):
        """
        Initialize the idempotency checker.

        Args:
            redis_client: Optional Redis client instance. If None, creates a new client.
            key_prefix: Prefix for Redis keys. Default: "autocog:job"
        """
        self.key_prefix = key_prefix
        if redis_client is not None:
            self._redis = redis_client
        else:
            try:
                self._redis = redis.Redis(
                    host="localhost", port=6379, db=0, decode_responses=True
                )
                # Test connection
                self._redis.ping()
            except redis.ConnectionError as e:
                logger.warning(
                    f"Failed to connect to Redis: {e}. Idempotency will be disabled (fail-open)."
                )
                self._redis = None

    def _get_time_vars(self) -> dict[str, Any]:
        """
        Get current time variables for template rendering.

        Returns:
            Dictionary with time variables: date, hour, week, month, 6h_bucket
        """
        now = datetime.now(timezone.utc)

        # ISO week (YYYY-WNN format)
        iso_calendar = now.isocalendar()
        week = f"{iso_calendar.year}-W{iso_calendar.week:02d}"

        # 6-hour bucket (0-3)
        hour = now.hour
        six_hour_bucket = hour // 6

        return {
            "date": now.strftime("%Y-%m-%d"),
            "hour": hour,
            "week": week,
            "month": now.strftime("%Y-%m"),
            "6h_bucket": six_hour_bucket,
            "year": now.year,
        }

    def render_key(self, job_id: str, idempotency_key_template: str) -> str:
        """
        Render an idempotency key template with current time variables.

        Supported template variables:
            {date} - Current date in YYYY-MM-DD format
            {hour} - Current hour (0-23)
            {week} - Current ISO week in YYYY-WNN format
            {month} - Current month in YYYY-MM format
            {6h_bucket} - Current 6-hour bucket (0-3)

        Args:
            job_id: Unique identifier for the job
            idempotency_key_template: Template string with time variable placeholders

        Returns:
            Rendered key with time variables substituted

        Example:
            >>> checker = IdempotencyChecker()
            >>> checker.render_key("daily_eval", "autocog.improvement_cycle.daily:{date}")
            'autocog:job:daily_eval:autocog.improvement_cycle.daily:2026-03-29'
        """
        time_vars = self._get_time_vars()

        # Replace template variables
        rendered = idempotency_key_template
        for var_name, var_value in time_vars.items():
            rendered = rendered.replace(f"{{{var_name}}}", str(var_value))

        return f"{self.key_prefix}:{job_id}:{rendered}"

    def _get_cadence_ttl(self, cadence: str) -> int:
        """
        Get TTL in seconds for a given cadence type.

        Args:
            cadence: Cadence type (hourly, 6hourly, daily, weekly, monthly)

        Returns:
            TTL in seconds, defaulting to 3600 if unknown cadence
        """
        return CADENCE_TTL_SECONDS.get(cadence, 3600)

    def should_run(
        self, job_id: str, idempotency_key_template: str, cadence: str
    ) -> bool:
        """
        Check if a job should run based on idempotency.

        Returns True if:
            - Redis is unavailable (fail-open)
            - The job has not been recorded in the current cadence window
            - A previous run failed (allows retry)

        Returns False if:
            - The job successfully completed in the current cadence window

        Args:
            job_id: Unique identifier for the job
            idempotency_key_template: Template string for the idempotency key
            cadence: Cadence type for TTL determination (hourly, 6hourly, daily, weekly, monthly)

        Returns:
            True if the job should run, False if it should be skipped
        """
        if self._redis is None:
            logger.warning("Redis unavailable, allowing job run (fail-open)")
            return True

        try:
            key = self.render_key(job_id, idempotency_key_template)
            exists = self._redis.exists(key)

            if not exists:
                return True

            # Key exists - check if previous run was successful
            data_str = self._redis.get(key)
            if data_str is None:
                # Key expired between exists() and get(), allow run
                return True

            data = json.loads(data_str)

            # If previous run failed, allow retry
            if not data.get("success", True):
                logger.info(f"Previous run of {job_id} failed, allowing retry")
                return True

            logger.info(
                f"Job {job_id} already completed successfully in this cadence window"
            )
            return False

        except redis.RedisError as e:
            logger.warning(
                f"Redis error during idempotency check: {e}. Allowing job run (fail-open)."
            )
            return True
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse idempotency data: {e}. Allowing job run.")
            return True

    def record_completion(
        self,
        job_id: str,
        idempotency_key_template: str,
        success: bool,
        error: str | None = None,
    ) -> bool:
        """
        Record a job completion for idempotency tracking.

        Args:
            job_id: Unique identifier for the job
            idempotency_key_template: Template string for the idempotency key
            success: Whether the job completed successfully
            error: Optional error message if job failed

        Returns:
            True if recording succeeded, False otherwise
        """
        if self._redis is None:
            logger.warning("Redis unavailable, cannot record completion")
            return False

        try:
            key = self.render_key(job_id, idempotency_key_template)
            cadence = self._infer_cadence(idempotency_key_template)
            ttl = self._get_cadence_ttl(cadence)

            data = {
                "timestamp": datetime.now(timezone.utc).timestamp(),
                "success": success,
                "error": error,
            }

            self._redis.setex(key, ttl, json.dumps(data))
            logger.debug(
                f"Recorded completion for {job_id}: success={success}, TTL={ttl}s"
            )
            return True

        except redis.RedisError as e:
            logger.error(f"Failed to record completion: {e}")
            return False

    def get_last_run(self, job_id: str, idempotency_key_template: str) -> float | None:
        """
        Get the timestamp of the last run for a job.

        Args:
            job_id: Unique identifier for the job
            idempotency_key_template: Template string for the idempotency key

        Returns:
            Unix timestamp of last run, or None if no run recorded
        """
        if self._redis is None:
            return None

        try:
            key = self.render_key(job_id, idempotency_key_template)
            data_str = self._redis.get(key)

            if data_str is None:
                return None

            data = json.loads(data_str)
            return data.get("timestamp")

        except redis.RedisError as e:
            logger.warning(f"Redis error getting last run: {e}")
            return None
        except json.JSONDecodeError:
            return None

    def _infer_cadence(self, idempotency_key_template: str) -> str:
        """
        Infer cadence type from idempotency key template.

        Args:
            idempotency_key_template: Template string to analyze

        Returns:
            Inferred cadence type (hourly, 6hourly, daily, weekly, monthly)
        """
        template_lower = idempotency_key_template.lower()

        if "{6h_bucket}" in template_lower:
            return "6hourly"
        elif "{hour}" in template_lower:
            return "hourly"
        elif "{date}" in template_lower:
            return "daily"
        elif "{week}" in template_lower:
            return "weekly"
        elif "{month}" in template_lower:
            return "monthly"
        else:
            return "hourly"  # Default to hourly for unknown patterns
