"""Reconciliation service for comparing telemetry vs persisted counts.

For ST-VENUE-002: Canonical reporting and venue enforcement.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from execution.reconciliation.config import (
    ReconciliationConfig,
    ReconciliationTimingConfig,
)
from execution.reconciliation.models import (
    CountDiscrepancy,
    ReconciliationResult,
    ReconciliationStatus,
)

if TYPE_CHECKING:
    from execution.telemetry.exporter import ExecutionTelemetryExporter

logger = logging.getLogger(__name__)


class OutcomeReconciliationService:
    """Service for reconciling telemetry data with persisted counts.

    Compares counts from InfluxDB telemetry against Redis/PostgreSQL
    persisted data to detect discrepancies and data integrity issues.

    Example:
        >>> service = OutcomeReconciliationService(
        ...     telemetry_exporter=exporter,
        ...     redis_client=redis_client,
        ...     postgres_client=postgres_client,
        ... )
        >>> result = await service.reconcile(
        ...     environment="paper",
        ...     portfolio_id="test-portfolio",
        ... )
        >>> print(result.get_summary())
    """

    def __init__(
        self,
        telemetry_exporter: ExecutionTelemetryExporter,
        redis_client: Any | None = None,
        postgres_client: Any | None = None,
        config: ReconciliationConfig | None = None,
    ):
        """Initialize reconciliation service.

        Args:
            telemetry_exporter: Exporter for reading telemetry data from InfluxDB
            redis_client: Redis client for reading persisted counts
            postgres_client: PostgreSQL client for reading persisted counts
            config: Reconciliation configuration
        """
        self.telemetry_exporter = telemetry_exporter
        self.redis_client = redis_client
        self.postgres_client = postgres_client
        self.config = config or ReconciliationConfig()

    async def reconcile(
        self,
        environment: str = "paper",
        portfolio_id: str = "default",
        time_range: timedelta | None = None,
        interval_seconds: int | None = None,
    ) -> ReconciliationResult:
        """Perform reconciliation between telemetry and persisted counts.

        Args:
            environment: Trading environment (paper/live)
            portfolio_id: Portfolio identifier
            time_range: Time range to reconcile (overrides interval_seconds)
            interval_seconds: Lookback interval in seconds (3600=1h, 86400=24h).
                Uses config default if not specified.

        Returns:
            ReconciliationResult with comparison details
        """
        if time_range is None:
            if interval_seconds is not None:
                time_range = timedelta(seconds=interval_seconds)
            else:
                time_range = self.config.timing.default_time_range

        end_time = datetime.now(UTC)
        start_time = end_time - time_range

        logger.info(
            f"Starting reconciliation for {environment}/{portfolio_id} "
            f"from {start_time.isoformat()} to {end_time.isoformat()}"
        )

        # Fetch counts from both sources
        telemetry_counts = await self._get_telemetry_counts(
            environment=environment,
            portfolio_id=portfolio_id,
            start_time=start_time,
            end_time=end_time,
        )
        persisted_counts = await self._get_persisted_counts(
            environment=environment,
            portfolio_id=portfolio_id,
            start_time=start_time,
            end_time=end_time,
        )

        # Calculate deltas
        delta_count, delta_pct = self.calculate_delta(
            telemetry_counts,
            persisted_counts,
        )

        # Determine status and discrepancies
        status, discrepancies = self.get_reconciliation_status(
            delta_pct=delta_pct,
            telemetry_counts=telemetry_counts,
            persisted_counts=persisted_counts,
        )

        result = ReconciliationResult(
            telemetry_count=telemetry_counts,
            persisted_count=persisted_counts,
            delta_count=delta_count,
            delta_pct=delta_pct,
            status=status,
            discrepancies=discrepancies,
            environment=environment,
            portfolio_id=portfolio_id,
        )

        logger.info(f"Reconciliation complete: {result.status.value}")
        if discrepancies:
            logger.warning(f"Found {len(discrepancies)} discrepancies")

        return result

    async def reconcile_hourly(
        self,
        environment: str = "paper",
        portfolio_id: str = "default",
    ) -> ReconciliationResult:
        """Run reconciliation for last hour (3600s).

        Convenience method for hourly reconciliation.

        Args:
            environment: Trading environment (paper/live)
            portfolio_id: Portfolio identifier

        Returns:
            ReconciliationResult with comparison details
        """
        return await self.reconcile(
            environment=environment,
            portfolio_id=portfolio_id,
            interval_seconds=ReconciliationTimingConfig.INTERVAL_HOURLY,
        )

    async def reconcile_daily(
        self,
        environment: str = "paper",
        portfolio_id: str = "default",
    ) -> ReconciliationResult:
        """Run reconciliation for last 24 hours (86400s).

        Convenience method for daily reconciliation.

        Args:
            environment: Trading environment (paper/live)
            portfolio_id: Portfolio identifier

        Returns:
            ReconciliationResult with comparison details
        """
        return await self.reconcile(
            environment=environment,
            portfolio_id=portfolio_id,
            interval_seconds=ReconciliationTimingConfig.INTERVAL_DAILY,
        )

    def calculate_delta(
        self,
        telemetry_counts: dict[str, int],
        persisted_counts: dict[str, int],
    ) -> tuple[dict[str, int], dict[str, float]]:
        """Calculate delta between telemetry and persisted counts.

        Args:
            telemetry_counts: Counts from telemetry source
            persisted_counts: Counts from persisted source

        Returns:
            Tuple of (delta_counts, delta_percentages)
        """
        delta_count: dict[str, int] = {}
        delta_pct: dict[str, float] = {}

        all_categories = set(telemetry_counts.keys()) | set(persisted_counts.keys())

        for category in all_categories:
            tel_count = telemetry_counts.get(category, 0)
            per_count = persisted_counts.get(category, 0)

            delta = tel_count - per_count
            delta_count[category] = delta

            # Calculate percentage based on persisted count (avoid div by zero)
            if per_count > 0:
                pct = (delta / per_count) * 100
            elif tel_count > 0:
                # Persisted is 0 but telemetry has data = 100% discrepancy
                pct = 100.0
            else:
                pct = 0.0

            delta_pct[category] = round(pct, 2)

        return delta_count, delta_pct

    def get_reconciliation_status(
        self,
        delta_pct: dict[str, float],
        telemetry_counts: dict[str, int],
        persisted_counts: dict[str, int],
    ) -> tuple[ReconciliationStatus, list[CountDiscrepancy]]:
        """Determine reconciliation status based on delta percentages.

        Args:
            delta_pct: Percentage deltas by category
            telemetry_counts: Counts from telemetry source
            persisted_counts: Counts from persisted source

        Returns:
            Tuple of (status, list of discrepancies)
        """
        discrepancies: list[CountDiscrepancy] = []
        max_pct = 0.0
        has_missing_data = False

        for category in self.config.categories:
            tel_count = telemetry_counts.get(category, 0)
            per_count = persisted_counts.get(category, 0)
            pct = delta_pct.get(category, 0.0)

            # Track max percentage for status determination
            max_pct = max(max_pct, abs(pct))

            # Check for missing data (both sources empty for expected category)
            if tel_count == 0 and per_count == 0:
                has_missing_data = True

            # Record discrepancy if exceeds warning threshold
            if abs(pct) > self.config.warn_threshold_pct:
                discrepancies.append(
                    CountDiscrepancy(
                        category=category,
                        telemetry_count=tel_count,
                        persisted_count=per_count,
                        delta=tel_count - per_count,
                        delta_pct=pct,
                    )
                )

        # Determine status
        if (
            has_missing_data
            and not telemetry_counts
            and not persisted_counts
            or max_pct >= self.config.fail_threshold_pct
        ):
            status = ReconciliationStatus.FAIL
        elif max_pct >= self.config.warn_threshold_pct:
            status = ReconciliationStatus.WARN
        else:
            status = ReconciliationStatus.OK

        return status, discrepancies

    async def _get_telemetry_counts(
        self,
        environment: str,
        portfolio_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> dict[str, int]:
        """Get counts from telemetry source (InfluxDB).

        Args:
            environment: Trading environment
            portfolio_id: Portfolio identifier
            start_time: Start of time range
            end_time: End of time range

        Returns:
            Dictionary of counts by category
        """
        counts: dict[str, int] = {}

        try:
            # Query telemetry exporter for counts
            if hasattr(self.telemetry_exporter, "query_counts"):
                counts = await self.telemetry_exporter.query_counts(
                    environment=environment,
                    portfolio_id=portfolio_id,
                    start_time=start_time,
                    end_time=end_time,
                    categories=self.config.categories,
                )
            else:
                # Fallback: try to get from metrics
                logger.debug(
                    "Telemetry exporter does not support query_counts, using fallback"
                )
                counts = await self._query_telemetry_fallback(
                    environment=environment,
                    portfolio_id=portfolio_id,
                    start_time=start_time,
                    end_time=end_time,
                )
        except Exception as e:
            logger.error(f"Failed to get telemetry counts: {e}")
            # Return empty counts on error
            counts = {cat: 0 for cat in self.config.categories}

        return counts

    async def _get_persisted_counts(
        self,
        environment: str,
        portfolio_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> dict[str, int]:
        """Get counts from persisted sources (Redis/PostgreSQL).

        Args:
            environment: Trading environment
            portfolio_id: Portfolio identifier
            start_time: Start of time range
            end_time: End of time range

        Returns:
            Dictionary of counts by category
        """
        counts: dict[str, int] = {}

        try:
            # Try Redis first
            if self.redis_client:
                counts = await self._get_redis_counts(
                    environment=environment,
                    portfolio_id=portfolio_id,
                    start_time=start_time,
                    end_time=end_time,
                )

            # Supplement with PostgreSQL if available
            if self.postgres_client:
                pg_counts = await self._get_postgres_counts(
                    environment=environment,
                    portfolio_id=portfolio_id,
                    start_time=start_time,
                    end_time=end_time,
                )
                # Merge counts (prefer PostgreSQL for outcomes)
                if pg_counts:
                    counts.update(pg_counts)

        except Exception as e:
            logger.error(f"Failed to get persisted counts: {e}")
            # Return empty counts on error
            counts = {cat: 0 for cat in self.config.categories}

        return counts

    async def _query_telemetry_fallback(
        self,
        environment: str,
        portfolio_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> dict[str, int]:
        """Fallback method to query telemetry data.

        This is used when the telemetry exporter doesn't support
        direct count queries.

        Args:
            environment: Trading environment
            portfolio_id: Portfolio identifier
            start_time: Start of time range
            end_time: End of time range

        Returns:
            Dictionary of counts by category
        """
        # Default implementation returns zeros
        # Subclasses or specific implementations should override this
        logger.warning("Using default telemetry fallback - returning zero counts")
        return {cat: 0 for cat in self.config.categories}

    async def _get_redis_counts(
        self,
        environment: str,
        portfolio_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> dict[str, int]:
        """Get counts from Redis.

        Args:
            environment: Trading environment
            portfolio_id: Portfolio identifier
            start_time: Start of time range
            end_time: End of time range

        Returns:
            Dictionary of counts by category
        """
        counts: dict[str, int] = {}

        try:
            # Query Redis for count keys
            # Key pattern: chiseai:counts:{environment}:{portfolio_id}:{category}
            for category in self.config.categories:
                key = f"chiseai:counts:{environment}:{portfolio_id}:{category}"
                if hasattr(self.redis_client, "get"):
                    value = self.redis_client.get(key)
                    counts[category] = int(value) if value else 0
                elif hasattr(self.redis_client, "hget"):
                    # Alternative: use hash storage
                    hash_key = f"chiseai:counts:{environment}:{portfolio_id}"
                    value = self.redis_client.hget(hash_key, category)
                    counts[category] = int(value) if value else 0
        except Exception as e:
            logger.error(f"Failed to get Redis counts: {e}")

        return counts

    async def _get_postgres_counts(
        self,
        environment: str,
        portfolio_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> dict[str, int]:
        """Get counts from PostgreSQL.

        Args:
            environment: Trading environment
            portfolio_id: Portfolio identifier
            start_time: Start of time range
            end_time: End of time range

        Returns:
            Dictionary of counts by category
        """
        counts: dict[str, int] = {}

        try:
            # Query PostgreSQL for counts
            # This would typically query signal_outcome, orders, fills tables
            if hasattr(self.postgres_client, "execute"):
                # Example query structure (would be adapted to actual schema)
                for category in self.config.categories:
                    table_map = {
                        "signals": "signals",
                        "orders": "orders",
                        "fills": "fills",
                        "outcomes": "signal_outcomes",
                    }
                    table = table_map.get(category, category)

                    query = f"""
                        SELECT COUNT(*) as count
                        FROM {table}
                        WHERE environment = %s
                        AND portfolio_id = %s
                        AND created_at >= %s
                        AND created_at < %s
                    """
                    result = await self.postgres_client.execute(
                        query,
                        environment,
                        portfolio_id,
                        start_time,
                        end_time,
                    )
                    if result:
                        counts[category] = result[0].get("count", 0)
        except Exception as e:
            logger.error(f"Failed to get PostgreSQL counts: {e}")

        return counts

    async def health_check(self) -> dict[str, Any]:
        """Perform health check on reconciliation service.

        Returns:
            Dictionary with health status of each component
        """
        health: dict[str, Any] = {
            "status": "healthy",
            "components": {},
        }

        # Check telemetry exporter
        try:
            if hasattr(self.telemetry_exporter, "health_check"):
                health["components"][
                    "telemetry"
                ] = await self.telemetry_exporter.health_check()
            else:
                health["components"]["telemetry"] = "available"
        except Exception as e:
            health["components"]["telemetry"] = f"error: {e}"
            health["status"] = "degraded"

        # Check Redis
        if self.redis_client:
            try:
                if hasattr(self.redis_client, "ping"):
                    self.redis_client.ping()
                    health["components"]["redis"] = "connected"
                else:
                    health["components"]["redis"] = "available"
            except Exception as e:
                health["components"]["redis"] = f"error: {e}"
                health["status"] = "degraded"
        else:
            health["components"]["redis"] = "not_configured"

        # Check PostgreSQL
        if self.postgres_client:
            try:
                if hasattr(self.postgres_client, "execute"):
                    await self.postgres_client.execute("SELECT 1")
                    health["components"]["postgres"] = "connected"
                else:
                    health["components"]["postgres"] = "available"
            except Exception as e:
                health["components"]["postgres"] = f"error: {e}"
                health["status"] = "degraded"
        else:
            health["components"]["postgres"] = "not_configured"

        return health
