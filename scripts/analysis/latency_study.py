#!/usr/bin/env python3
"""Phase D: Analysis Latency Study for LLM-PROVIDER-FIX-001-LATENCY.

Runs N>=15 live analysis attempts to measure LLM provider latency.
Timeout ceiling: 300000ms (5 minutes) for study phase.

Captures: duration, provider, success/fallback, error class
Outputs: JSON results with statistics (avg/p50/p90/p95/p99/max)

Usage:
    python scripts/analysis/latency_study.py --attempts 15 --timeout 300000
    python scripts/analysis/latency_study.py --check-credentials-only

Environment Variables Required:
    KIMI_API_KEY - Valid Kimi API key
    ZAI_API_KEY - Valid Z.ai API key
    ZHIPU_API_KEY - Valid Zhipu API key with available quota

Note: This script requires valid credentials to run. Phase B showed all
providers failing due to credential issues. Run credential check first.
"""

from __future__ import annotations

import argparse
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

# Add src to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))


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
    credential_status: dict[str, Any] = field(default_factory=dict)


class CredentialChecker:
    """Checks LLM provider credentials before running study."""

    REQUIRED_ENV_VARS = {
        "KIMI_API_KEY": {
            "description": "Kimi (Moonshot) API key",
            "test_endpoint": "https://api.moonshot.cn/v1/models",
            "min_length": 20,
        },
        "ZAI_API_KEY": {
            "description": "Z.ai API key",
            "test_endpoint": "https://api.z.ai/api/coding/paas/v4/models",
            "min_length": 20,
        },
        "ZHIPU_API_KEY": {
            "description": "Zhipu (BigModel) API key",
            "test_endpoint": "https://open.bigmodel.cn/api/paas/v4/models",
            "min_length": 20,
        },
    }

    def __init__(self) -> None:
        self.results: dict[str, Any] = {}

    def check_all(self) -> tuple[bool, dict[str, Any]]:
        """Check all required credentials.

        Returns:
            Tuple of (all_valid, detailed_results)
        """
        all_valid = True

        for var_name, config in self.REQUIRED_ENV_VARS.items():
            result = self._check_credential(var_name, config)
            self.results[var_name] = result
            if not result["valid"]:
                all_valid = False

        return all_valid, self.results

    def _check_credential(self, var_name: str, config: dict) -> dict[str, Any]:
        """Check a single credential."""
        result = {
            "var_name": var_name,
            "description": config["description"],
            "valid": False,
            "set": False,
            "length": 0,
            "error": None,
        }

        value = os.getenv(var_name)

        if not value:
            result["error"] = f"Environment variable {var_name} is not set"
            return result

        result["set"] = True
        result["length"] = len(value)

        if len(value) < config["min_length"]:
            result["error"] = f"API key too short (min {config['min_length']} chars)"
            return result

        # Basic format check - most API keys are alphanumeric with some special chars
        if not all(c.isalnum() or c in "_-./=" for c in value):
            result["error"] = "API key contains invalid characters"
            return result

        result["valid"] = True
        return result

    def print_report(self) -> None:
        """Print credential check report."""
        print("\n" + "=" * 60)
        print("CREDENTIAL CHECK REPORT")
        print("=" * 60)

        for var_name, result in self.results.items():
            status = "✓ VALID" if result["valid"] else "✗ INVALID"
            print(f"\n{var_name}: {status}")
            print(f"  Description: {result['description']}")
            print(f"  Set: {result['set']}")
            if result["length"] > 0:
                print(f"  Length: {result['length']} chars")
            if result["error"]:
                print(f"  Error: {result['error']}")

        all_valid = all(r["valid"] for r in self.results.values())
        print("\n" + "-" * 60)
        if all_valid:
            print("RESULT: All credentials valid - study can proceed")
        else:
            print("RESULT: Some credentials invalid - study CANNOT proceed")
            print("\nTo obtain valid credentials:")
            print("  1. Kimi: https://platform.moonshot.cn/ - Create API key")
            print("  2. Z.ai: https://z.ai/ - Request API access")
            print("  3. Zhipu: https://open.bigmodel.cn/ - Register and create key")
        print("=" * 60)


class LLMLatencyStudy:
    """Runs live LLM latency study with real market data."""

    def __init__(
        self,
        n_attempts: int = 15,
        timeout_ms: int = 300000,
        output_dir: str | None = None,
    ) -> None:
        """Initialize latency study.

        Args:
            n_attempts: Number of attempts to run (default: 15)
            timeout_ms: Timeout ceiling in milliseconds (default: 300000 = 5 min)
            output_dir: Directory for output files (default: docs/tempmemories/)
        """
        self.n_attempts = n_attempts
        self.timeout_ms = timeout_ms
        self.output_dir = Path(output_dir) if output_dir else Path("docs/tempmemories")

        self.study = LatencyStudy(
            study_id=f"LLM-PROVIDER-FIX-001-LATENCY-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}",
            story_id="LLM-PROVIDER-FIX-001-LATENCY",
            n_attempts=n_attempts,
            timeout_ceiling_ms=timeout_ms,
            start_time=datetime.now(UTC).isoformat(),
        )
        self.enhancer = None

    async def run(self) -> LatencyStudy:
        """Execute full latency study."""
        logger.info(f"=== LLM Latency Study Started: {self.study.study_id} ===")
        logger.info(f"Configuration: n={self.n_attempts}, timeout={self.timeout_ms}ms")

        # Check credentials first
        credential_checker = CredentialChecker()
        all_valid, cred_results = credential_checker.check_all()
        self.study.credential_status = cred_results

        if not all_valid:
            logger.error("Credential check failed - cannot proceed with study")
            credential_checker.print_report()
            self.study.errors.append(
                {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "error": "Credential check failed",
                    "type": "CREDENTIAL_ERROR",
                    "details": cred_results,
                }
            )
            self.study.end_time = datetime.now(UTC).isoformat()
            await self._save_evidence()
            return self.study

        logger.info("Credential check passed - proceeding with study")

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
        elif "quota" in error_str or "balance" in error_str or "exhausted" in error_str:
            return "QUOTA_EXHAUSTED"
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
            """Calculate percentile using linear interpolation."""
            if n == 0:
                return 0.0
            k = (n - 1) * p / 100.0
            f = int(k)
            c = min(f + 1, n - 1)
            return sorted_durations[f] + (k - f) * (
                sorted_durations[c] - sorted_durations[f]
            )

        self.study.statistics = {
            "count": n,
            "success_count": len(successful),
            "failure_count": len(failed),
            "success_rate": round(len(successful) / n * 100, 2) if n > 0 else 0,
            "fallback_rate": (
                round(
                    len([a for a in self.study.attempts if a.fallback_used]) / n * 100,
                    2,
                )
                if n > 0
                else 0
            ),
            "avg_ms": round(sum(durations) / n, 2) if n > 0 else 0,
            "p50_ms": round(percentile(50), 2),
            "p90_ms": round(percentile(90), 2),
            "p95_ms": round(percentile(95), 2),
            "p99_ms": round(percentile(99), 2),
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
        logger.info(f"  Fallback rate: {self.study.statistics['fallback_rate']}%")
        logger.info(f"  Avg: {self.study.statistics['avg_ms']}ms")
        logger.info(f"  P50: {self.study.statistics['p50_ms']}ms")
        logger.info(f"  P90: {self.study.statistics['p90_ms']}ms")
        logger.info(f"  P95: {self.study.statistics['p95_ms']}ms")
        logger.info(f"  P99: {self.study.statistics['p99_ms']}ms")
        logger.info(f"  Max: {self.study.statistics['max_ms']}ms")

    async def _save_evidence(self) -> None:
        """Save evidence to file."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        evidence_path = self.output_dir / f"{self.study.story_id}-latency-study.json"

        # Convert to serializable dict
        data = {
            "study_id": self.study.study_id,
            "story_id": self.study.story_id,
            "n_attempts": self.study.n_attempts,
            "timeout_ceiling_ms": self.study.timeout_ceiling_ms,
            "start_time": self.study.start_time,
            "end_time": self.study.end_time,
            "credential_status": self.study.credential_status,
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


def print_summary(result: LatencyStudy) -> None:
    """Print study summary."""
    print("\n" + "=" * 60)
    print("LLM LATENCY STUDY SUMMARY")
    print("=" * 60)
    print(f"Study ID: {result.study_id}")
    print(f"Attempts: {result.n_attempts}")
    print(f"Timeout Ceiling: {result.timeout_ceiling_ms}ms")
    print("\nStatistics:")
    print(f"  Count: {result.statistics.get('count', 0)}")
    print(f"  Success Rate: {result.statistics.get('success_rate', 0)}%")
    print(f"  Fallback Rate: {result.statistics.get('fallback_rate', 0)}%")
    print(f"  Avg: {result.statistics.get('avg_ms', 0)}ms")
    print(f"  P50: {result.statistics.get('p50_ms', 0)}ms")
    print(f"  P90: {result.statistics.get('p90_ms', 0)}ms")
    print(f"  P95: {result.statistics.get('p95_ms', 0)}ms")
    print(f"  P99: {result.statistics.get('p99_ms', 0)}ms")
    print(f"  Max: {result.statistics.get('max_ms', 0)}ms")

    if result.statistics.get("provider_breakdown"):
        print("\nProvider Breakdown:")
        for provider, count in result.statistics["provider_breakdown"].items():
            print(f"  {provider}: {count}")

    if result.statistics.get("error_breakdown"):
        print("\nError Breakdown:")
        for error, count in result.statistics["error_breakdown"].items():
            print(f"  {error}: {count}")

    print(
        f"\nEvidence saved to: docs/tempmemories/{result.story_id}-latency-study.json"
    )
    print("=" * 60)


async def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run LLM latency study for LLM-PROVIDER-FIX-001-LATENCY"
    )
    parser.add_argument(
        "--attempts",
        type=int,
        default=15,
        help="Number of attempts to run (default: 15)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300000,
        help="Timeout ceiling in ms (default: 300000 = 5 min)",
    )
    parser.add_argument(
        "--check-credentials-only",
        action="store_true",
        help="Only check credentials, don't run study",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory for results (default: docs/tempmemories/)",
    )

    args = parser.parse_args()

    # Check credentials first
    if args.check_credentials_only:
        checker = CredentialChecker()
        all_valid, _ = checker.check_all()
        checker.print_report()
        return 0 if all_valid else 1

    # Run full study
    try:
        study = LLMLatencyStudy(
            n_attempts=args.attempts,
            timeout_ms=args.timeout,
            output_dir=args.output_dir,
        )
        result = await study.run()

        # Check if credentials were the issue
        if result.errors and any(
            e.get("type") == "CREDENTIAL_ERROR" for e in result.errors
        ):
            print("\n⚠️  Study could not run due to credential issues.")
            print("Run with --check-credentials-only for details.")
            return 2  # Special exit code for credential failure

        print_summary(result)
        return 0

    except Exception as e:
        logger.error(f"Latency study failed: {e}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
