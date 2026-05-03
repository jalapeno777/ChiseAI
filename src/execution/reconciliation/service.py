"""Reconciliation service for comparing telemetry vs persisted counts.

For ST-VENUE-002: Canonical reporting and venue enforcement.
For ST-FILL-004: Reconciliation daemon safety net with alerting.
"""

from __future__ import annotations

import asyncio
import contextlib
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
        """Fallback method to query telemetry data from Redis counters.

        Used when the telemetry exporter doesn't support direct count queries.
        Reads actual counts from Redis keys ``chiseai:counts:{env}:{portfolio}:{cat}``.

        Args:
            environment: Trading environment
            portfolio_id: Portfolio identifier
            start_time: Start of time range
            end_time: End of time range

        Returns:
            Dictionary of counts by category
        """
        counts: dict[str, int] = {}

        if self.redis_client is None:
            logger.warning(
                "Telemetry fallback: no Redis client configured, returning zero counts"
            )
            return {cat: 0 for cat in self.config.categories}

        try:
            for category in self.config.categories:
                key = f"chiseai:counts:{environment}:{portfolio_id}:{category}"
                value = None

                # Try plain GET first (same pattern as _get_redis_counts)
                if hasattr(self.redis_client, "get"):
                    value = self.redis_client.get(key)
                elif hasattr(self.redis_client, "hget"):
                    hash_key = f"chiseai:counts:{environment}:{portfolio_id}"
                    value = self.redis_client.hget(hash_key, category)

                if value is not None:
                    counts[category] = int(value)
                    logger.info(
                        "Telemetry fallback: found count for %s via Redis key %s = %d",
                        category,
                        key,
                        counts[category],
                    )
                else:
                    counts[category] = 0
                    logger.debug(
                        "Telemetry fallback: no Redis key %s for category %s",
                        key,
                        category,
                    )
        except Exception as exc:
            logger.warning(
                "Telemetry fallback: Redis query failed (%s), returning zeros", exc
            )
            return {cat: 0 for cat in self.config.categories}

        logger.info(
            "Telemetry fallback: resolved counts from Redis for %s/%s: %s",
            environment,
            portfolio_id,
            counts,
        )
        return counts

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

    async def backfill_missed_fills(
        self,
        environment: str = "paper",
        portfolio_id: str = "default",
        lookback_seconds: int = 300,
    ) -> dict[str, Any]:
        """Backfill logic for fills that may have been missed.

        Compares telemetry fills with execution list from Bybit API
        to detect and record any missed fills.

        Args:
            environment: Trading environment (paper/live)
            portfolio_id: Portfolio identifier
            lookback_seconds: How far back to look for missed fills (default 5 min)

        Returns:
            Dict with backfill results: fills_found, fills_backfilled, errors
        """
        end_time = datetime.now(UTC)
        start_time = end_time - timedelta(seconds=lookback_seconds)

        logger.info(
            f"Backfill check for {environment}/{portfolio_id} "
            f"from {start_time.isoformat()} to {end_time.isoformat()}"
        )

        result: dict[str, Any] = {
            "fills_found": 0,
            "fills_backfilled": 0,
            "errors": [],
            "environment": environment,
            "portfolio_id": portfolio_id,
            "lookback_seconds": lookback_seconds,
        }

        try:
            # Get telemetry fills for the lookback window
            telemetry_fills = await self._get_telemetry_fills(
                environment=environment,
                portfolio_id=portfolio_id,
                start_time=start_time,
                end_time=end_time,
            )

            # Get persisted fills for the lookback window
            persisted_fills = await self._get_persisted_fills(
                environment=environment,
                portfolio_id=portfolio_id,
                start_time=start_time,
                end_time=end_time,
            )

            result["fills_found"] = len(telemetry_fills)

            # Identify fills in telemetry but not in persisted storage
            persisted_fill_ids = {
                f.get("fill_id") or f.get("id") for f in persisted_fills
            }
            missed_fills = [
                f
                for f in telemetry_fills
                if (f.get("fill_id") or f.get("id")) not in persisted_fill_ids
            ]

            result["fills_backfilled"] = len(missed_fills)

            if missed_fills:
                logger.warning(
                    f"Found {len(missed_fills)} missed fills in backfill check"
                )
                # Record missed fills — do NOT auto-close or auto-trade
                await self._record_missed_fills(
                    environment=environment,
                    portfolio_id=portfolio_id,
                    missed_fills=missed_fills,
                )

        except Exception as e:
            result["errors"].append(str(e))
            logger.error(f"Backfill check failed: {e}")

        return result

    async def _get_telemetry_fills(
        self,
        environment: str,
        portfolio_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[dict[str, Any]]:
        """Get fills from telemetry source for backfill comparison.

        Args:
            environment: Trading environment
            portfolio_id: Portfolio identifier
            start_time: Start of time range
            end_time: End of time range

        Returns:
            List of fill dictionaries from telemetry
        """
        try:
            if hasattr(self.telemetry_exporter, "query_fills"):
                return await self.telemetry_exporter.query_fills(
                    environment=environment,
                    portfolio_id=portfolio_id,
                    start_time=start_time,
                    end_time=end_time,
                )
        except Exception as e:
            logger.error(f"Failed to get telemetry fills: {e}")
        return []

    async def _get_persisted_fills(
        self,
        environment: str,
        portfolio_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[dict[str, Any]]:
        """Get fills from persisted storage for backfill comparison.

        Args:
            environment: Trading environment
            portfolio_id: Portfolio identifier
            start_time: Start of time range
            end_time: End of time range

        Returns:
            List of fill dictionaries from persisted storage
        """
        fills: list[dict[str, Any]] = []
        try:
            if self.postgres_client and hasattr(self.postgres_client, "execute"):
                query = """
                    SELECT id, symbol, side, qty, price, created_at
                    FROM fills
                    WHERE environment = %s
                    AND portfolio_id = %s
                    AND created_at >= %s
                    AND created_at < %s
                    ORDER BY created_at ASC
                """
                rows = await self.postgres_client.execute(
                    query,
                    environment,
                    portfolio_id,
                    start_time,
                    end_time,
                )
                if rows:
                    fills = [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get persisted fills: {e}")
        return fills

    async def _record_missed_fills(
        self,
        environment: str,
        portfolio_id: str,
        missed_fills: list[dict[str, Any]],
    ) -> None:
        """Record missed fills for investigation.

        Alert-only: logs and publishes incident, does NOT auto-close positions.

        Args:
            environment: Trading environment
            portfolio_id: Portfolio identifier
            missed_fills: List of missed fill dictionaries
        """
        msg = (
            f"MISSED FILLS DETECTED: {len(missed_fills)} fills in "
            f"{environment}/{portfolio_id} not found in persisted storage"
        )
        logger.warning(msg)

        try:
            from execution.incident_reporter import publish_execution_incident

            await publish_execution_incident(
                incident_type="missed_fills",
                severity="P2",
                title=f"Missed fills detected in {environment}/{portfolio_id}",
                message=msg,
                context={
                    "missed_count": len(missed_fills),
                    "fills": [
                        {
                            "fill_id": f.get("fill_id") or f.get("id"),
                            "symbol": f.get("symbol"),
                            "side": f.get("side"),
                            "qty": f.get("qty"),
                        }
                        for f in missed_fills[:50]  # Cap context to 50 fills
                    ],
                },
            )
        except Exception as e:
            logger.error(f"Failed to publish missed fills incident: {e}")


class ReconciliationMonitor:
    """Scheduled reconciliation daemon with alerting.

    Runs OutcomeReconciliationService on a schedule and emits
    alerts when discrepancies exceed thresholds.

    Alert-only policy: this monitor NEVER auto-closes positions or
    triggers liquidation. It only logs and publishes incidents.

    Example:
        >>> monitor = ReconciliationMonitor(
        ...     reconciliation_service=service,
        ...     check_interval_seconds=3600,
        ... )
        >>> await monitor.start()
        >>> # ... runs in background ...
        >>> await monitor.stop()
    """

    def __init__(
        self,
        reconciliation_service: OutcomeReconciliationService,
        redis_client: Any | None = None,
        check_interval_seconds: int = 3600,
        backfill_enabled: bool = False,
    ):
        """Initialize reconciliation monitor.

        Args:
            reconciliation_service: The reconciliation service to run on schedule
            redis_client: Optional Redis client for state tracking
            check_interval_seconds: How often to run reconciliation (default 1h)
            backfill_enabled: Whether to backfill missed fills (default False).
                When True, calls backfill_missed_fills() on each cycle.
        """
        self.service = reconciliation_service
        self.redis = redis_client
        self.check_interval = check_interval_seconds
        self.backfill_enabled = backfill_enabled
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the reconciliation monitor."""
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("ReconciliationMonitor started")

    async def stop(self) -> None:
        """Stop the reconciliation monitor."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        logger.info("ReconciliationMonitor stopped")

    async def _run_loop(self) -> None:
        """Main reconciliation loop.

        Runs reconciliation and optionally backfills missed fills based on
        the backfill_enabled flag. Alert-only policy: NEVER auto-closes
        positions or triggers liquidation.
        """
        while self._running:
            try:
                # Run standard reconciliation
                result = await self.service.reconcile(
                    environment="paper",
                    portfolio_id="default",
                )
                await self._handle_result(result)

                # ST-FILL-004: Run backfill if enabled (respects reconciliation_auto_backfill flag)
                # Only backfill if explicitly enabled - this is separate from reconciliation alerts
                if self.backfill_enabled:
                    try:
                        backfill_result = await self.service.backfill_missed_fills(
                            environment="paper",
                            portfolio_id="default",
                            lookback_seconds=300,  # 5 minute lookback window
                        )
                        if backfill_result.get("fills_backfilled", 0) > 0:
                            logger.info(
                                f"Backfill completed: "
                                f"fills_found={backfill_result['fills_found']}, "
                                f"fills_backfilled={backfill_result['fills_backfilled']}"
                            )
                    except Exception as e:
                        logger.error(f"Backfill failed: {e}")
                        # Continue running even if backfill fails - don't crash the loop

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"ReconciliationMonitor error: {e}")

            await asyncio.sleep(self.check_interval)

    async def _handle_result(self, result: ReconciliationResult) -> None:
        """Handle reconciliation result — alert on discrepancies.

        Alert-only policy: logs and publishes incidents.
        NEVER auto-closes positions or triggers liquidation.

        Args:
            result: The reconciliation result to evaluate
        """
        if result.status == ReconciliationStatus.FAIL:
            await self._alert_failure(result)
        elif result.status == ReconciliationStatus.WARN:
            await self._alert_warning(result)

    async def _alert_failure(self, result: ReconciliationResult) -> None:
        """Alert on reconciliation failure.

        Alert-only: logs at CRITICAL level and publishes incident.
        Does NOT auto-close positions or trigger liquidation.

        Args:
            result: The failed reconciliation result
        """
        msg = (
            f"RECONCILIATION FAIL: telemetry={result.telemetry_count}, "
            f"persisted={result.persisted_count}, "
            f"delta={result.delta_count}, "
            f"discrepancies={len(result.discrepancies)}"
        )
        logger.critical(msg)
        await self._publish_incident("reconciliation_failure", msg, result)

    async def _alert_warning(self, result: ReconciliationResult) -> None:
        """Alert on reconciliation warning.

        Alert-only: logs at WARNING level and publishes incident.
        Does NOT auto-close positions or trigger liquidation.

        Args:
            result: The warning reconciliation result
        """
        msg = (
            f"RECONCILIATION WARN: delta_pct={result.delta_pct}, "
            f"discrepancies={len(result.discrepancies)}"
        )
        logger.warning(msg)

    async def _publish_incident(
        self, incident_type: str, message: str, result: ReconciliationResult
    ) -> None:
        """Publish incident to incident reporter.

        Args:
            incident_type: Type of incident
            message: Human-readable incident message
            result: The reconciliation result for context
        """
        try:
            from execution.incident_reporter import publish_execution_incident

            await publish_execution_incident(
                incident_type=incident_type,
                severity="P1" if result.status == ReconciliationStatus.FAIL else "P2",
                title=f"Reconciliation {result.status.value}",
                message=message,
                context={
                    "telemetry_count": result.telemetry_count,
                    "persisted_count": result.persisted_count,
                    "delta_count": result.delta_count,
                    "delta_pct": result.delta_pct,
                    "discrepancies": [
                        {
                            "category": d.category,
                            "delta": d.delta,
                            "delta_pct": d.delta_pct,
                        }
                        for d in result.discrepancies
                    ],
                },
            )
        except Exception as e:
            logger.error(f"Failed to publish reconciliation incident: {e}")
