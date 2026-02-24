"""Latency model for paper trading execution simulation.

Provides realistic latency simulation for order submission and fill notifications.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@dataclass
class LatencyConfig:
    """Configuration for latency model.

    Attributes:
        submission_mean_ms: Mean latency for order submission in milliseconds
        submission_std_ms: Standard deviation for submission latency
        fill_mean_ms: Mean latency for fill notification in milliseconds
        fill_std_ms: Standard deviation for fill notification latency
        min_latency_ms: Minimum latency floor in milliseconds
        network_jitter_ms: Additional network jitter
    """

    submission_mean_ms: float = 50.0
    submission_std_ms: float = 15.0
    fill_mean_ms: float = 100.0
    fill_std_ms: float = 30.0
    min_latency_ms: float = 5.0
    network_jitter_ms: float = 5.0


class LatencyModel:
    """Models realistic network and processing latency for paper trading.

    Simulates latency for order submission and fill notifications using
    normal distributions with configurable parameters per exchange.
    """

    def __init__(self, config: LatencyConfig | None = None, seed: int | None = None):
        """Initialize latency model.

        Args:
            config: Latency model configuration
            seed: Random seed for reproducible latency
        """
        self.config = config or LatencyConfig()
        self._rng = random.Random(seed)

        logger.info(
            f"LatencyModel initialized: submission_mean={self.config.submission_mean_ms}ms, "
            f"fill_mean={self.config.fill_mean_ms}ms, seed={seed}"
        )

    def simulate_order_submission_latency(self) -> float:
        """Simulate order submission latency.

        Uses normal distribution with configurable mean and std deviation.

        Returns:
            Latency in milliseconds
        """
        # Generate normally distributed latency
        latency = self._rng.gauss(
            self.config.submission_mean_ms,
            self.config.submission_std_ms,
        )

        # Add network jitter
        jitter = self._rng.uniform(0, self.config.network_jitter_ms)
        latency += jitter

        # Apply minimum floor
        latency = max(latency, self.config.min_latency_ms)

        logger.debug(f"Order submission latency: {latency:.2f}ms")
        return latency

    def simulate_fill_notification_latency(self) -> float:
        """Simulate fill notification latency.

        Uses normal distribution with configurable mean and std deviation.

        Returns:
            Latency in milliseconds
        """
        # Generate normally distributed latency
        latency = self._rng.gauss(
            self.config.fill_mean_ms,
            self.config.fill_std_ms,
        )

        # Add network jitter
        jitter = self._rng.uniform(0, self.config.network_jitter_ms)
        latency += jitter

        # Apply minimum floor
        latency = max(latency, self.config.min_latency_ms)

        logger.debug(f"Fill notification latency: {latency:.2f}ms")
        return latency

    def simulate_total_latency(self) -> float:
        """Simulate total latency (submission + fill notification).

        Returns:
            Total latency in milliseconds
        """
        submission_latency = self.simulate_order_submission_latency()
        fill_latency = self.simulate_fill_notification_latency()
        total = submission_latency + fill_latency

        logger.debug(f"Total latency: {total:.2f}ms")
        return total

    def simulate_batch_latency(self, batch_size: int) -> list[float]:
        """Simulate latency for a batch of orders.

        Args:
            batch_size: Number of orders in batch

        Returns:
            List of latencies in milliseconds
        """
        latencies = []
        for _ in range(batch_size):
            latencies.append(self.simulate_order_submission_latency())

        logger.debug(
            f"Batch latency for {batch_size} orders: mean={sum(latencies) / len(latencies):.2f}ms"
        )
        return latencies

    def get_config(self) -> LatencyConfig:
        """Get current configuration.

        Returns:
            Current latency configuration
        """
        return self.config

    def update_config(self, config: LatencyConfig) -> None:
        """Update configuration.

        Args:
            config: New latency configuration
        """
        self.config = config
        logger.info(
            f"LatencyModel config updated: submission_mean={config.submission_mean_ms}ms, "
            f"fill_mean={config.fill_mean_ms}ms"
        )

    def reset_seed(self, seed: int) -> None:
        """Reset random seed for reproducible latency.

        Args:
            seed: New random seed
        """
        self._rng = random.Random(seed)
        logger.debug(f"LatencyModel seed reset to {seed}")

    def get_statistics(self, samples: int = 10000) -> dict:
        """Calculate latency statistics from samples.

        Args:
            samples: Number of samples to generate

        Returns:
            Dictionary with latency statistics
        """
        submission_latencies = [
            self.simulate_order_submission_latency() for _ in range(samples)
        ]
        fill_latencies = [
            self.simulate_fill_notification_latency() for _ in range(samples)
        ]
        total_latencies = [
            s + f for s, f in zip(submission_latencies, fill_latencies, strict=False)
        ]

        def calc_stats(data: list[float]) -> dict:
            mean = sum(data) / len(data)
            variance = sum((x - mean) ** 2 for x in data) / len(data)
            std = variance**0.5
            sorted_data = sorted(data)
            p50 = sorted_data[int(len(data) * 0.5)]
            p95 = sorted_data[int(len(data) * 0.95)]
            p99 = sorted_data[int(len(data) * 0.99)]
            return {
                "mean": mean,
                "std": std,
                "min": min(data),
                "max": max(data),
                "p50": p50,
                "p95": p95,
                "p99": p99,
            }

        return {
            "submission": calc_stats(submission_latencies),
            "fill_notification": calc_stats(fill_latencies),
            "total": calc_stats(total_latencies),
        }
