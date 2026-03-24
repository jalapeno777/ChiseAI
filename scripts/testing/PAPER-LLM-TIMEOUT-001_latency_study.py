#!/usr/bin/env python3
"""Phase 2: Live LLM Latency Study for PAPER-LLM-TIMEOUT-001 (Optimized).

Runs N=10 repeated live LLM analysis attempts with shorter timeout to gather data efficiently.
Uses timeout ceiling of 120000ms (2 minutes) during study.

Saves raw latency table to docs/tempmemories/PAPER-LLM-TIMEOUT-001-latency-study.json
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))


@dataclass
class LatencyAttempt:
    """Single latency measurement attempt."""

    attempt_number: int
    start_ts: str
    end_ts: str
    duration_ms: float
    provider_tried: str
    success: bool
    fallback_used: bool
    error_category: str | None
    error_details: str | None = None


@dataclass
class LatencyStudy:
    """Complete latency study results."""

    study_id: str
    story_id: str
    n_attempts: int
    timeout_ceiling_ms: int
    start_time: str
    end_time: str | None = None
    attempts: list[LatencyAttempt] = field(default_factory=list)
    statistics: dict[str, Any] = field(default_factory=dict)
    errors: list[dict] = field(default_factory=list)


class LLMLatencyStudy:
    """Runs live LLM latency study with real market data."""

    def __init__(self, n_attempts: int = 10, timeout_ms: int = 120000) -> None:
        """Initialize latency study.

        Args:
            n_attempts: Number of attempts to run (default: 10)
            timeout_ms: Timeout ceiling in milliseconds (default: 120000 = 2 min)
        """
        self.n_attempts = n_attempts
        self.timeout_ms = timeout_ms
        self.study = LatencyStudy(
            study_id=f"PAPER-LLM-TIMEOUT-001-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}",
            story_id="PAPER-LLM-TIMEOUT-001",
            n_attempts=n_attempts,
            timeout_ceiling_ms=timeout_ms,
            start_time=datetime.now(UTC).isoformat(),
        )
        self.enhancer = None

    async def run(self) -> LatencyStudy:
        """Execute full latency study."""
        logger.info(f"=== LLM Latency Study Started: {self.study.study_id} ===")
        logger.info(f"Configuration: n={self.n_attempts}, timeout={self.timeout_ms}ms")

        try:
            # Initialize enhancer with study timeout
            from execution.llm.trade_decision_enhancer import TradeDecisionEnhancer

            # Force enable LLM and set study timeout
            os.environ["USE_LLM_TRADE_DECISIONS"] = "true"
            os.environ["LLM_DECISION_TIMEOUT_MS"] = str(self.timeout_ms)

            self.enhancer = TradeDecisionEnhancer(
                enabled=True,
                timeout_ms=self.timeout_ms,
            )

            logger.info(f"Enhancer initialized: timeout={self.enhancer.timeout_ms}ms")

            # Run N attempts
            for i in range(1, self.n_attempts + 1):
                await self._run_attempt(i)
                # Brief pause between attempts
                if i < self.n_attempts:
                    await asyncio.sleep(1)

            # Compute statistics
            self._compute_statistics()

        except Exception as e:
            logger.error(f"Latency study failed: {e}")
            self.study.errors.append(
                {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "error": str(e),
                    "type": type(e).__name__,
                }
            )
            raise

        self.study.end_time = datetime.now(UTC).isoformat()
        await self._save_evidence()

        logger.info(f"=== LLM Latency Study Complete: {self.study.study_id} ===")
        return self.study

    async def _run_attempt(self, attempt_number: int) -> None:
        """Run a single latency measurement attempt."""
        logger.info(f"Attempt {attempt_number}/{self.n_attempts}...")

        start_time = time.time()
        start_ts = datetime.now(UTC).isoformat()

        # Create a mock signal for testing
        mock_signal = self._create_mock_signal()

        # Market context
        market_context = {
            "price": 85000.0,
            "change_24h": "+2.5%",
            "volume": "1.2B",
        }

        try:
            # Call enhancer with timeout
            decision = await asyncio.wait_for(
                self.enhancer.enhance_decision(mock_signal, market_context),
                timeout=self.timeout_ms / 1000.0,
            )

            end_time = time.time()
            end_ts = datetime.now(UTC).isoformat()
            duration_ms = (end_time - start_time) * 1000

            attempt = LatencyAttempt(
                attempt_number=attempt_number,
                start_ts=start_ts,
                end_ts=end_ts,
                duration_ms=round(duration_ms, 2),
                provider_tried=decision.provider,
                success=True,
                fallback_used=decision.fallback_used,
                error_category=None,
                error_details=None,
            )

            logger.info(
                f"  Attempt {attempt_number}: {duration_ms:.2f}ms, "
                f"provider={decision.provider}, fallback={decision.fallback_used}"
            )

        except TimeoutError:
            end_time = time.time()
            end_ts = datetime.now(UTC).isoformat()
            duration_ms = (end_time - start_time) * 1000

            attempt = LatencyAttempt(
                attempt_number=attempt_number,
                start_ts=start_ts,
                end_ts=end_ts,
                duration_ms=round(duration_ms, 2),
                provider_tried="timeout",
                success=False,
                fallback_used=True,
                error_category="TIMEOUT",
                error_details=f"Exceeded {self.timeout_ms}ms timeout",
            )

            logger.warning(
                f"  Attempt {attempt_number}: TIMEOUT after {duration_ms:.2f}ms"
            )

        except Exception as e:
            end_time = time.time()
            end_ts = datetime.now(UTC).isoformat()
            duration_ms = (end_time - start_time) * 1000

            error_category = self._categorize_error(e)

            attempt = LatencyAttempt(
                attempt_number=attempt_number,
                start_ts=start_ts,
                end_ts=end_ts,
                duration_ms=round(duration_ms, 2),
                provider_tried="error",
                success=False,
                fallback_used=True,
                error_category=error_category,
                error_details=str(e)[:200],
            )

            logger.error(
                f"  Attempt {attempt_number}: ERROR ({error_category}) after {duration_ms:.2f}ms: {e}"
            )

        self.study.attempts.append(attempt)

    def _create_mock_signal(self) -> Any:
        """Create a mock trading signal for testing."""

        class MockSignal:
            def __init__(self) -> None:
                self.token = "BTCUSDT"
                self.symbol = "BTCUSDT"
                self.direction = "long"
                self.confidence = 0.75
                self.base_score = 0.8
                self.contributing_factors = [
                    {"name": "momentum", "score": 0.85},
                    {"name": "volume", "score": 0.7},
                    {"name": "trend", "score": 0.8},
                ]

        return MockSignal()

    def _categorize_error(self, error: Exception) -> str:
        """Categorize error type."""
        error_str = str(error).lower()

        if "timeout" in error_str or "timed out" in error_str:
            return "TIMEOUT"
        elif "connection" in error_str or "connect" in error_str:
            return "CONNECTION"
        elif "auth" in error_str or "key" in error_str or "credential" in error_str:
            return "AUTH"
        elif "rate" in error_str or "limit" in error_str:
            return "RATE_LIMIT"
        elif "provider" in error_str or "llm" in error_str:
            return "PROVIDER"
        else:
            return "UNKNOWN"

    def _compute_statistics(self) -> None:
        """Compute distribution statistics from attempts."""
        if not self.study.attempts:
            return

        durations = [a.duration_ms for a in self.study.attempts]
        successful = [a for a in self.study.attempts if a.success]
        failed = [a for a in self.study.attempts if not a.success]

        # Sort for percentile calculation
        sorted_durations = sorted(durations)
        n = len(sorted_durations)

        def percentile(p: float) -> float:
            """Calculate percentile."""
            k = (n - 1) * p / 100.0
            f = int(k)
            c = f + 1 if f + 1 < n else f
            return sorted_durations[f] + (k - f) * (
                sorted_durations[c] - sorted_durations[f]
            )

        self.study.statistics = {
            "count": n,
            "success_count": len(successful),
            "failure_count": len(failed),
            "success_rate": round(len(successful) / n * 100, 2) if n > 0 else 0,
            "avg_ms": round(sum(durations) / n, 2) if n > 0 else 0,
            "p50_ms": round(percentile(50), 2),
            "p90_ms": round(percentile(90), 2),
            "p95_ms": round(percentile(95), 2),
            "p99_ms": (
                round(percentile(99), 2)
                if n >= 100
                else round(sorted_durations[-1] if sorted_durations else 0, 2)
            ),
            "min_ms": round(min(durations), 2) if durations else 0,
            "max_ms": round(max(durations), 2) if durations else 0,
            "std_dev_ms": (
                round(
                    (sum((d - sum(durations) / n) ** 2 for d in durations) / n) ** 0.5,
                    2,
                )
                if n > 0
                else 0
            ),
        }

        # Provider breakdown
        provider_counts: dict[str, int] = {}
        error_categories: dict[str, int] = {}

        for attempt in self.study.attempts:
            provider = attempt.provider_tried
            provider_counts[provider] = provider_counts.get(provider, 0) + 1

            if attempt.error_category:
                error_categories[attempt.error_category] = (
                    error_categories.get(attempt.error_category, 0) + 1
                )

        self.study.statistics["provider_breakdown"] = provider_counts
        self.study.statistics["error_breakdown"] = error_categories

        logger.info("Statistics computed:")
        logger.info(f"  Count: {self.study.statistics['count']}")
        logger.info(f"  Success rate: {self.study.statistics['success_rate']}%")
        logger.info(f"  Avg: {self.study.statistics['avg_ms']}ms")
        logger.info(f"  P50: {self.study.statistics['p50_ms']}ms")
        logger.info(f"  P90: {self.study.statistics['p90_ms']}ms")
        logger.info(f"  P95: {self.study.statistics['p95_ms']}ms")
        logger.info(f"  Max: {self.study.statistics['max_ms']}ms")

    async def _save_evidence(self) -> None:
        """Save evidence to file."""
        evidence_path = Path(
            "docs/tempmemories/PAPER-LLM-TIMEOUT-001-latency-study.json"
        )
        evidence_path.parent.mkdir(parents=True, exist_ok=True)

        # Convert to serializable dict
        data = {
            "study_id": self.study.study_id,
            "story_id": self.study.story_id,
            "n_attempts": self.study.n_attempts,
            "timeout_ceiling_ms": self.study.timeout_ceiling_ms,
            "start_time": self.study.start_time,
            "end_time": self.study.end_time,
            "attempts": [
                {
                    "attempt_number": a.attempt_number,
                    "start_ts": a.start_ts,
                    "end_ts": a.end_ts,
                    "duration_ms": a.duration_ms,
                    "provider_tried": a.provider_tried,
                    "success": a.success,
                    "fallback_used": a.fallback_used,
                    "error_category": a.error_category,
                    "error_details": a.error_details,
                }
                for a in self.study.attempts
            ],
            "statistics": self.study.statistics,
            "errors": self.study.errors,
        }

        with open(evidence_path, "w") as f:
            json.dump(data, f, indent=2)

        logger.info(f"Evidence saved to: {evidence_path}")


async def main() -> int:
    """Main entry point."""
    try:
        study = LLMLatencyStudy(n_attempts=10, timeout_ms=120000)
        result = await study.run()

        # Print summary
        print("\n" + "=" * 60)
        print("LLM LATENCY STUDY SUMMARY")
        print("=" * 60)
        print(f"Study ID: {result.study_id}")
        print(f"Attempts: {result.n_attempts}")
        print(f"Timeout Ceiling: {result.timeout_ceiling_ms}ms")
        print("\nStatistics:")
        print(f"  Count: {result.statistics.get('count')}")
        print(f"  Success Rate: {result.statistics.get('success_rate')}%")
        print(f"  Avg: {result.statistics.get('avg_ms')}ms")
        print(f"  P50: {result.statistics.get('p50_ms')}ms")
        print(f"  P90: {result.statistics.get('p90_ms')}ms")
        print(f"  P95: {result.statistics.get('p95_ms')}ms")
        print(f"  Max: {result.statistics.get('max_ms')}ms")

        if result.statistics.get("provider_breakdown"):
            print("\nProvider Breakdown:")
            for provider, count in result.statistics["provider_breakdown"].items():
                print(f"  {provider}: {count}")

        if result.statistics.get("error_breakdown"):
            print("\nError Breakdown:")
            for error, count in result.statistics["error_breakdown"].items():
                print(f"  {error}: {count}")

        print(
            "\nEvidence saved to: docs/tempmemories/PAPER-LLM-TIMEOUT-001-latency-study.json"
        )
        print("=" * 60)

        return 0

    except Exception as e:
        logger.error(f"Latency study failed: {e}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
