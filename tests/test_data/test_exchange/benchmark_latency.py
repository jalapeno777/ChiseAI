"""Latency benchmark for connection pooling.

Benchmark script for ST-NS-026: Connection Pooling for Exchange APIs

Usage:
    python -m tests.test_data.test_exchange.benchmark_latency

This script benchmarks the latency improvements from connection pooling.
"""

from __future__ import annotations

import asyncio
import statistics
import time
from typing import Any

from data.exchange.pooling import (
    ExchangeConnectionPool,
)


class LatencyBenchmark:
    """Benchmark connection pool latency."""

    def __init__(self):
        self.results: dict[str, list[float]] = {}

    async def benchmark_pool_initialization(self) -> dict[str, Any]:
        """Benchmark pool initialization time."""
        print("\n=== Pool Initialization Benchmark ===")

        times = []
        for pool_size in [5, 10, 20]:
            pool = ExchangeConnectionPool(
                exchange="test", pool_size=pool_size, max_connections=pool_size * 2
            )

            start = time.monotonic()
            await pool.initialize()
            elapsed = (time.monotonic() - start) * 1000

            times.append(elapsed)
            print(f"  Pool size {pool_size}: {elapsed:.2f}ms")

            await pool.close_all()

        return {
            "operation": "pool_initialization",
            "times_ms": times,
            "avg_ms": statistics.mean(times),
            "min_ms": min(times),
            "max_ms": max(times),
        }

    async def benchmark_connection_acquisition(self) -> dict[str, Any]:
        """Benchmark connection acquisition time."""
        print("\n=== Connection Acquisition Benchmark ===")

        pool = ExchangeConnectionPool(exchange="test", pool_size=10, max_connections=20)
        await pool.initialize()

        # Warm up
        async with pool.get_connection():
            pass

        # Benchmark
        times = []
        for _ in range(100):
            start = time.monotonic()
            async with pool.get_connection():
                pass
            elapsed = (time.monotonic() - start) * 1000
            times.append(elapsed)

        await pool.close_all()

        result = {
            "operation": "connection_acquisition",
            "times_ms": times,
            "avg_ms": statistics.mean(times),
            "min_ms": min(times),
            "max_ms": max(times),
            "p95_ms": sorted(times)[int(len(times) * 0.95)],
            "p99_ms": sorted(times)[int(len(times) * 0.99)],
        }

        print(f"  Average: {result['avg_ms']:.2f}ms")
        print(f"  Min: {result['min_ms']:.2f}ms")
        print(f"  Max: {result['max_ms']:.2f}ms")
        print(f"  P95: {result['p95_ms']:.2f}ms")
        print(f"  P99: {result['p99_ms']:.2f}ms")

        return result

    async def benchmark_concurrent_requests(self) -> dict[str, Any]:
        """Benchmark concurrent request handling."""
        print("\n=== Concurrent Requests Benchmark ===")

        pool = ExchangeConnectionPool(exchange="test", pool_size=10, max_connections=20)
        await pool.initialize()

        async def make_request() -> float:
            start = time.monotonic()
            async with pool.get_connection():
                # Simulate minimal API work
                await asyncio.sleep(0.001)
            return (time.monotonic() - start) * 1000

        # Test different concurrency levels
        results = {}
        for concurrency in [1, 5, 10, 20, 50]:
            tasks = [make_request() for _ in range(concurrency)]
            times = await asyncio.gather(*tasks)

            avg_time = statistics.mean(times)
            results[f"concurrency_{concurrency}"] = {
                "avg_ms": avg_time,
                "total_ms": sum(times),
                "throughput_rps": concurrency / (sum(times) / 1000 / concurrency),
            }

            print(
                f"  Concurrency {concurrency}: {avg_time:.2f}ms avg, "
                f"{results[f'concurrency_{concurrency}']['throughput_rps']:.1f} req/s"
            )

        await pool.close_all()

        return {
            "operation": "concurrent_requests",
            "results": results,
        }

    async def benchmark_rate_limiting(self) -> dict[str, Any]:
        """Benchmark rate limiting behavior."""
        print("\n=== Rate Limiting Benchmark ===")

        # Bybit config: 120 RPM = 2 RPS
        pool = ExchangeConnectionPool(
            exchange="test",
            pool_size=5,
            max_connections=10,
            rate_limit={"requests_per_minute": 120, "burst_size": 10},
        )
        await pool.initialize()

        # Make 15 requests (should trigger rate limiting after burst)
        times = []
        start_total = time.monotonic()

        for _ in range(15):
            start = time.monotonic()
            async with pool.get_connection():
                pass
            elapsed = (time.monotonic() - start) * 1000
            times.append(elapsed)

        total_elapsed = (time.monotonic() - start_total) * 1000

        await pool.close_all()

        # With 120 RPM (2 RPS) and burst of 10:
        # - First 10 requests should be instant (burst)
        # - Remaining 5 should be rate limited (~500ms each)
        burst_count = sum(1 for t in times if t < 50)
        limited_count = sum(1 for t in times if t >= 50)

        result = {
            "operation": "rate_limiting",
            "times_ms": times,
            "total_time_ms": total_elapsed,
            "burst_requests": burst_count,
            "limited_requests": limited_count,
            "rate_limiter_metrics": pool.rate_limiter.get_metrics(),
        }

        print(f"  Burst requests: {burst_count}")
        print(f"  Rate limited requests: {limited_count}")
        print(f"  Total time: {total_elapsed:.2f}ms")
        print(f"  Avg time: {statistics.mean(times):.2f}ms")

        return result

    async def benchmark_pool_vs_no_pool(self) -> dict[str, Any]:
        """Compare pooled vs non-pooled performance."""
        print("\n=== Pool vs No Pool Comparison ===")

        import aiohttp

        # Pooled approach
        pool = ExchangeConnectionPool(exchange="test", pool_size=5, max_connections=10)
        await pool.initialize()

        async def pooled_request() -> float:
            start = time.monotonic()
            async with pool.get_connection() as conn:
                # Simulate request
                pass
            return (time.monotonic() - start) * 1000

        # Non-pooled approach (new session each time)
        async def non_pooled_request() -> float:
            start = time.monotonic()
            async with aiohttp.ClientSession() as session:
                # Simulate request setup
                pass
            return (time.monotonic() - start) * 1000

        # Benchmark pooled
        pooled_times = []
        for _ in range(20):
            pooled_times.append(await pooled_request())

        # Benchmark non-pooled
        non_pooled_times = []
        for _ in range(20):
            non_pooled_times.append(await non_pooled_request())

        await pool.close_all()

        pooled_avg = statistics.mean(pooled_times)
        non_pooled_avg = statistics.mean(non_pooled_times)
        improvement = ((non_pooled_avg - pooled_avg) / non_pooled_avg) * 100

        result = {
            "operation": "pool_comparison",
            "pooled_avg_ms": pooled_avg,
            "non_pooled_avg_ms": non_pooled_avg,
            "improvement_percent": improvement,
            "pooled_times_ms": pooled_times,
            "non_pooled_times_ms": non_pooled_times,
        }

        print(f"  Pooled avg: {pooled_avg:.2f}ms")
        print(f"  Non-pooled avg: {non_pooled_avg:.2f}ms")
        print(f"  Improvement: {improvement:.1f}%")

        return result

    async def run_all(self) -> dict[str, Any]:
        """Run all benchmarks."""
        print("=" * 60)
        print("Connection Pooling Latency Benchmark")
        print("=" * 60)

        results = {
            "initialization": await self.benchmark_pool_initialization(),
            "acquisition": await self.benchmark_connection_acquisition(),
            "concurrent": await self.benchmark_concurrent_requests(),
            "rate_limiting": await self.benchmark_rate_limiting(),
            "comparison": await self.benchmark_pool_vs_no_pool(),
        }

        # Summary
        print("\n" + "=" * 60)
        print("Benchmark Summary")
        print("=" * 60)

        acquisition_avg = results["acquisition"]["avg_ms"]
        target = 1000.0  # 1 second target

        print(f"\nConnection Acquisition:")
        print(f"  Average: {acquisition_avg:.2f}ms")
        print(f"  Target: <{target:.0f}ms")
        print(f"  Status: {'PASS' if acquisition_avg < target else 'FAIL'}")

        comparison = results["comparison"]
        print(f"\nPool vs Non-Pool:")
        print(f"  Improvement: {comparison['improvement_percent']:.1f}%")
        print(f"  Target: >50% improvement")
        print(
            f"  Status: {'PASS' if comparison['improvement_percent'] > 50 else 'FAIL'}"
        )

        # Overall status
        all_pass = acquisition_avg < target and comparison["improvement_percent"] > 50

        print(f"\nOverall: {'PASS' if all_pass else 'FAIL'}")

        return results


def main():
    """Run benchmarks."""
    benchmark = LatencyBenchmark()
    results = asyncio.run(benchmark.run_all())

    # Save results to file
    import json

    with open("/tmp/pool_benchmark_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)

    print("\nResults saved to /tmp/pool_benchmark_results.json")


if __name__ == "__main__":
    main()
