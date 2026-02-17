"""Signal-to-Order pipeline for paper trading.

Provides a streamlined pipeline for converting signals into orders
with latency monitoring and error handling.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from execution.paper.orchestrator import PaperTradingOrchestrator
    from signal_generation.models import Signal

from execution.paper.models import PaperTradeResult, TradeStatus

logger = logging.getLogger(__name__)


@dataclass
class PipelineMetrics:
    """Metrics for pipeline performance.

    Attributes:
        signals_received: Total signals received
        signals_processed: Signals successfully processed
        signals_rejected: Signals rejected by risk
        signals_failed: Signals that failed during processing
        avg_latency_ms: Average processing latency
        max_latency_ms: Maximum observed latency
        last_processed_at: Timestamp of last processed signal
    """

    signals_received: int = 0
    signals_processed: int = 0
    signals_rejected: int = 0
    signals_failed: int = 0
    avg_latency_ms: float = 0.0
    max_latency_ms: float = 0.0
    last_processed_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            "signals_received": self.signals_received,
            "signals_processed": self.signals_processed,
            "signals_rejected": self.signals_rejected,
            "signals_failed": self.signals_failed,
            "avg_latency_ms": round(self.avg_latency_ms, 3),
            "max_latency_ms": round(self.max_latency_ms, 3),
            "last_processed_at": self.last_processed_at,
        }


class SignalToOrderPipeline:
    """Pipeline for processing signals into orders.

    Provides a simpler interface than the full orchestrator
    for batch signal processing with monitoring.

    Example:
        pipeline = SignalToOrderPipeline(orchestrator)
        results = await pipeline.process_signals(signals)
    """

    def __init__(self, orchestrator: PaperTradingOrchestrator):
        """Initialize pipeline.

        Args:
            orchestrator: Paper trading orchestrator instance
        """
        self.orchestrator = orchestrator
        self.metrics = PipelineMetrics()
        self._latencies: list[float] = []
        self._max_latency_window = 100  # Keep last 100 latencies for avg

        logger.info("SignalToOrderPipeline initialized")

    async def process_signal(self, signal: Signal) -> PaperTradeResult:
        """Process a single signal through the pipeline.

        Args:
            signal: Trading signal to process

        Returns:
            PaperTradeResult with execution details
        """
        self.metrics.signals_received += 1
        start_time = time.perf_counter()

        try:
            # Process through orchestrator
            result = await self.orchestrator.process_signal(signal)

            # Update metrics based on result
            latency_ms = (time.perf_counter() - start_time) * 1000
            self._update_metrics(result.status, latency_ms)

            return result

        except Exception as e:
            logger.error(f"Pipeline error processing signal: {e}")

            latency_ms = (time.perf_counter() - start_time) * 1000
            self._update_metrics(TradeStatus.FAILED, latency_ms)

            # Return failed result
            from execution.paper.models import PaperTradeResult

            return PaperTradeResult(
                signal=signal,
                status=TradeStatus.FAILED,
                reject_reason=[str(e)],
                latency_ms=latency_ms,
            )

    async def process_signals(self, signals: list[Signal]) -> list[PaperTradeResult]:
        """Process multiple signals through the pipeline.

        Args:
            signals: List of trading signals

        Returns:
            List of PaperTradeResults
        """
        results = []

        for signal in signals:
            result = await self.process_signal(signal)
            results.append(result)

        return results

    async def process_signals_batch(
        self,
        signals: list[Signal],
        max_concurrent: int = 5,
    ) -> list[PaperTradeResult]:
        """Process signals with limited concurrency.

        Args:
            signals: List of trading signals
            max_concurrent: Maximum concurrent processing

        Returns:
            List of PaperTradeResults
        """
        import asyncio

        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_with_limit(signal: Signal) -> PaperTradeResult:
            async with semaphore:
                return await self.process_signal(signal)

        # Process all signals concurrently with limit
        tasks = [process_with_limit(s) for s in signals]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to failed results
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Batch processing error: {result}")
                from execution.paper.models import PaperTradeResult

                final_results.append(
                    PaperTradeResult(
                        signal=signals[i],
                        status=TradeStatus.FAILED,
                        reject_reason=[str(result)],
                    )
                )
            else:
                final_results.append(result)

        return final_results

    def _update_metrics(self, status: TradeStatus, latency_ms: float) -> None:
        """Update pipeline metrics.

        Args:
            status: Trade execution status
            latency_ms: Processing latency
        """
        from datetime import datetime

        # Update counters
        if status == TradeStatus.EXECUTED:
            self.metrics.signals_processed += 1
        elif status == TradeStatus.REJECTED:
            self.metrics.signals_rejected += 1
        elif status == TradeStatus.FAILED:
            self.metrics.signals_failed += 1

        # Update latency tracking
        self._latencies.append(latency_ms)
        if len(self._latencies) > self._max_latency_window:
            self._latencies.pop(0)

        # Update metrics
        self.metrics.avg_latency_ms = sum(self._latencies) / len(self._latencies)
        self.metrics.max_latency_ms = max(self.metrics.max_latency_ms, latency_ms)
        self.metrics.last_processed_at = datetime.now().isoformat()

    def get_metrics(self) -> PipelineMetrics:
        """Get current pipeline metrics.

        Returns:
            PipelineMetrics instance
        """
        return self.metrics

    def reset_metrics(self) -> None:
        """Reset pipeline metrics."""
        self.metrics = PipelineMetrics()
        self._latencies.clear()
        logger.info("Pipeline metrics reset")

    def get_success_rate(self) -> float:
        """Calculate success rate.

        Returns:
            Success rate as percentage (0.0-100.0)
        """
        if self.metrics.signals_received == 0:
            return 0.0

        return (self.metrics.signals_processed / self.metrics.signals_received) * 100

    def get_summary(self) -> dict[str, Any]:
        """Get pipeline summary.

        Returns:
            Dictionary with summary statistics
        """
        return {
            "metrics": self.metrics.to_dict(),
            "success_rate_pct": round(self.get_success_rate(), 2),
            "is_healthy": self.metrics.avg_latency_ms < 2000,  # < 2s target
        }
