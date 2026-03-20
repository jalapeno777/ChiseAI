"""Main ingestion service for Binance market data."""

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime

from exchange_data.binance.client import BinanceClient
from exchange_data.binance.config import BinanceConfig
from exchange_data.binance.liquidity import LiquidityCalculator, LiquidityMetrics
from exchange_data.binance.open_interest import (
    OpenInterestAggregator,
    OpenInterestData,
)
from exchange_data.binance.orderbook import (
    OrderBookLevel,
    OrderBookSnapshot,
    OrderBookTracker,
)
from exchange_data.binance.validator import DataQualityReport, DataQualityValidator

logger = logging.getLogger(__name__)


class IngestionMetrics:
    """Metrics tracking for ingestion performance."""

    def __init__(self) -> None:
        """Initialize metrics."""
        self.snapshots_ingested = 0
        self.snapshots_failed = 0
        self.total_latency_ms = 0.0
        self.last_ingest_time: datetime | None = None
        self.alert_callbacks: list[Callable[[str, dict], None]] = []

    def record_success(self, latency_ms: float) -> None:
        """Record successful ingestion.

        Args:
            latency_ms: Request latency in milliseconds
        """
        self.snapshots_ingested += 1
        self.total_latency_ms += latency_ms
        self.last_ingest_time = datetime.now(UTC)

    def record_failure(self, error: str) -> None:
        """Record failed ingestion.

        Args:
            error: Error message
        """
        self.snapshots_failed += 1
        self._trigger_alert("ingest_failure", {"error": error})

    def get_average_latency_ms(self) -> float:
        """Get average ingestion latency."""
        if self.snapshots_ingested == 0:
            return 0.0
        return self.total_latency_ms / self.snapshots_ingested

    def get_p95_latency_ms(self, recent_latencies: list[float]) -> float:
        """Calculate 95th percentile latency.

        Args:
            recent_latencies: List of recent latency measurements

        Returns:
            95th percentile latency
        """
        if not recent_latencies:
            return 0.0
        sorted_latencies = sorted(recent_latencies)
        idx = int(len(sorted_latencies) * 0.95)
        return sorted_latencies[min(idx, len(sorted_latencies) - 1)]

    def register_alert_callback(self, callback: Callable[[str, dict], None]) -> None:
        """Register callback for alert events.

        Args:
            callback: Function to call on alert (alert_type, data)
        """
        self.alert_callbacks.append(callback)

    def _trigger_alert(self, alert_type: str, data: dict) -> None:
        """Trigger alert callbacks.

        Args:
            alert_type: Type of alert
            data: Alert data
        """
        for callback in self.alert_callbacks:
            try:
                callback(alert_type, data)
            except Exception as e:
                logger.error(f"Alert callback failed: {e}")


class BinanceIngestionService:
    """Main service for ingesting Binance market data.

    Coordinates order book snapshots, liquidity metrics,
    open interest data, and data quality validation.
    """

    def __init__(
        self,
        config: BinanceConfig | None = None,
        alert_callback: Callable[[str, dict], None] | None = None,
    ) -> None:
        """Initialize ingestion service.

        Args:
            config: Binance configuration
            alert_callback: Optional callback for alerts
        """
        self.config = config or BinanceConfig()
        self.client = BinanceClient(self.config)
        self.tracker = OrderBookTracker()
        self.liquidity_calc = LiquidityCalculator()
        self.oi_aggregator = OpenInterestAggregator()
        self.validator = DataQualityValidator(self.config)
        self.metrics = IngestionMetrics()

        if alert_callback:
            self.metrics.register_alert_callback(alert_callback)

        self._running = False
        self._tasks: list[asyncio.Task] = []
        self._recent_latencies: list[float] = []
        self._max_latency_history = 1000

    async def start(self) -> None:
        """Start the ingestion service."""
        if self._running:
            return

        self._running = True
        await self.client.connect()

        # Start ingestion tasks
        for token in self.config.tokens:
            task = asyncio.create_task(self._ingest_loop(token), name=f"ingest_{token}")
            self._tasks.append(task)

        # Start OI aggregation task
        oi_task = asyncio.create_task(self._oi_ingest_loop(), name="oi_ingest")
        self._tasks.append(oi_task)

        logger.info(f"Started ingestion service for {len(self.config.tokens)} tokens")

    async def stop(self) -> None:
        """Stop the ingestion service."""
        self._running = False

        # Cancel all tasks
        for task in self._tasks:
            task.cancel()

        # Wait for tasks to complete
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        await self.client.close()
        self._tasks.clear()
        logger.info("Stopped ingestion service")

    async def _ingest_loop(self, token: str) -> None:
        """Main ingestion loop for a token.

        Args:
            token: Token symbol to ingest
        """
        while self._running:
            try:
                start_time = asyncio.get_event_loop().time()

                # Fetch order book
                ob_data = await self.client.get_order_book(
                    token, limit=self.config.orderbook_depth
                )

                # Parse snapshot
                snapshot = self._parse_orderbook(token, ob_data)

                # Calculate latency
                latency_ms = (asyncio.get_event_loop().time() - start_time) * 1000
                snapshot.latency_ms = latency_ms

                # Track latency
                self._recent_latencies.append(latency_ms)
                if len(self._recent_latencies) > self._max_latency_history:
                    self._recent_latencies.pop(0)

                # Add to tracker
                self.tracker.add_snapshot(snapshot)

                # Record success
                self.metrics.record_success(latency_ms)

                # Check latency threshold
                if latency_ms > self.config.max_latency_ms:
                    self.metrics._trigger_alert(
                        "high_latency",
                        {"token": token, "latency_ms": latency_ms},
                    )

            except Exception as e:
                logger.error(f"Ingestion error for {token}: {e}")
                self.metrics.record_failure(str(e))

                # Trigger alert within 10 seconds of failure
                self.metrics._trigger_alert(
                    "ingest_failure",
                    {"token": token, "error": str(e)},
                )

            # Wait for next interval
            await asyncio.sleep(self.config.snapshot_interval_ms / 1000)

    async def _oi_ingest_loop(self) -> None:
        """Open interest ingestion loop."""
        while self._running:
            try:
                for token in self.config.tokens:
                    try:
                        oi_data = await self.client.get_open_interest(token)
                        oi = self._parse_oi(token, oi_data)
                        self.oi_aggregator.add(oi)
                    except Exception as e:
                        logger.error(f"OI fetch error for {token}: {e}")

                # OI updates every minute typically
                await asyncio.sleep(60)

            except Exception as e:
                logger.error(f"OI ingestion error: {e}")
                await asyncio.sleep(10)

    def _parse_orderbook(self, symbol: str, data: dict) -> OrderBookSnapshot:
        """Parse order book API response.

        Args:
            symbol: Trading pair symbol
            data: API response data

        Returns:
            Order book snapshot
        """
        bids = [
            OrderBookLevel(price=float(p), quantity=float(q))
            for p, q in data.get("bids", [])
        ]
        asks = [
            OrderBookLevel(price=float(p), quantity=float(q))
            for p, q in data.get("asks", [])
        ]

        # Sort bids descending, asks ascending
        bids.sort(key=lambda x: x.price, reverse=True)
        asks.sort(key=lambda x: x.price)

        return OrderBookSnapshot(
            symbol=symbol,
            timestamp=datetime.now(UTC),
            last_update_id=data.get("lastUpdateId", 0),
            bids=bids,
            asks=asks,
        )

    def _parse_oi(self, symbol: str, data: dict) -> OpenInterestData:
        """Parse open interest API response.

        Args:
            symbol: Trading pair symbol
            data: API response data

        Returns:
            Open interest data
        """
        oi = float(data.get("openInterest", 0))
        # Get price from latest order book if available
        latest_snapshot = self.tracker.get_latest(symbol)
        price = latest_snapshot.mid_price if latest_snapshot else 0.0

        return OpenInterestData(
            symbol=symbol,
            timestamp=datetime.now(UTC),
            open_interest=oi,
            price=price,
            open_interest_usd=oi * price if price > 0 else 0,
        )

    def get_liquidity_metrics(self, symbol: str) -> LiquidityMetrics | None:
        """Get liquidity metrics for a symbol.

        Args:
            symbol: Trading pair symbol

        Returns:
            Liquidity metrics or None
        """
        snapshot = self.tracker.get_latest(symbol)
        if snapshot:
            return self.liquidity_calc.calculate(snapshot)
        return None

    def get_quality_report(self) -> DataQualityReport:
        """Generate data quality report.

        Returns:
            Data quality report
        """
        # Get recent snapshots for all symbols
        recent_snapshots: list[OrderBookSnapshot] = []
        for symbol in self.config.tokens:
            snapshot = self.tracker.get_latest(symbol)
            if snapshot:
                recent_snapshots.append(snapshot)

        return self.validator.generate_report(self.tracker, recent_snapshots)

    def get_metrics(self) -> dict:
        """Get ingestion metrics.

        Returns:
            Dictionary of metrics
        """
        return {
            "snapshots_ingested": self.metrics.snapshots_ingested,
            "snapshots_failed": self.metrics.snapshots_failed,
            "avg_latency_ms": self.metrics.get_average_latency_ms(),
            "p95_latency_ms": self.metrics.get_p95_latency_ms(self._recent_latencies),
            "last_ingest_time": (
                self.metrics.last_ingest_time.isoformat()
                if self.metrics.last_ingest_time
                else None
            ),
        }

    def is_healthy(self) -> bool:
        """Check if ingestion service is healthy.

        Returns:
            True if service is healthy
        """
        if not self._running:
            return False

        # Check if we've ingested recently
        if self.metrics.last_ingest_time is None:
            return False

        time_since_last = (
            datetime.now(UTC) - self.metrics.last_ingest_time
        ).total_seconds()
        if time_since_last > self.config.freshness_threshold_sec * 2:
            return False

        # Check P95 latency
        p95 = self.metrics.get_p95_latency_ms(self._recent_latencies)
        return not p95 > self.config.max_latency_ms
