#!/usr/bin/env python3
"""
Redis Delta Collector for G1-G4 Validation.

Captures pre/post deltas on canonical Redis indexes for paper trading
validation gates. Provides correlation proof: signal_id -> order_id -> fill_id -> outcome_id.

Usage:
    python3 scripts/validation/redis_deltas.py

Gates:
    G1: Scheduler continuity - heartbeat delta > 0
    G2: Signal cadence - signal delta > 0
    G3: Outcome flow - outcome delta > 0
    G4: Kill switch - enabled and not triggered

Exit codes:
    0 - All gates passed
    1 - One or more gates failed
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class GateStatus(Enum):
    """Status of validation gate results."""

    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"
    SKIP = "skip"


@dataclass
class GateResult:
    """Result of a single validation gate.

    Attributes:
        name: Gate name (G1, G2, G3, G4)
        status: Pass/fail/error/skip
        message: Human-readable message
        evidence: Supporting evidence data
        timestamp_utc: When validation occurred
    """

    name: str
    status: GateStatus
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)
    timestamp_utc: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "evidence": self.evidence,
            "timestamp_utc": self.timestamp_utc,
        }


@dataclass
class RedisDeltaEvidence:
    """Evidence of delta change in a Redis index.

    Attributes:
        index_name: Name of the Redis index/key
        start_count: Count at baseline capture
        end_count: Count at final capture
        delta: Change in count (end - start)
        sample_ids: IDs of new records created since baseline
        timestamp_start_utc: When baseline was captured
        timestamp_end_utc: When final was captured
    """

    index_name: str
    start_count: int
    end_count: int
    delta: int
    sample_ids: list[str]
    timestamp_start_utc: str
    timestamp_end_utc: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "index_name": self.index_name,
            "start_count": self.start_count,
            "end_count": self.end_count,
            "delta": self.delta,
            "sample_ids": self.sample_ids,
            "timestamp_start_utc": self.timestamp_start_utc,
            "timestamp_end_utc": self.timestamp_end_utc,
        }


@dataclass
class CorrelationEvidence:
    """Evidence of correlation chain from signal to outcome.

    Attributes:
        signal_id: Original signal ID
        order_id: Associated order ID
        fill_id: Associated fill ID (same as order_id for fills)
        outcome_id: Final outcome ID
        correlation_chain: List of chain steps ["signal", "order", "fill", "outcome"]
        data: Full data from each step
    """

    signal_id: str
    order_id: str
    fill_id: str
    outcome_id: str
    correlation_chain: list[str] = field(
        default_factory=lambda: ["signal", "order", "fill", "outcome"]
    )
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "signal_id": self.signal_id,
            "order_id": self.order_id,
            "fill_id": self.fill_id,
            "outcome_id": self.outcome_id,
            "correlation_chain": self.correlation_chain,
            "data": self.data,
        }


@dataclass
class ValidationReport:
    """Complete validation report for G1-G4 gates.

    Attributes:
        execution_id: Unique ID for this validation run
        timestamp_utc: When validation occurred
        gate_results: Results for each gate
        delta_evidence: Delta evidence for each index
        correlation_evidence: Correlation chains found
        overall_passed: Whether all gates passed
        errors: Any errors encountered
    """

    execution_id: str = field(default_factory=lambda: str(uuid4())[:8])
    timestamp_utc: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    gate_results: list[GateResult] = field(default_factory=list)
    delta_evidence: list[RedisDeltaEvidence] = field(default_factory=list)
    correlation_evidence: list[CorrelationEvidence] = field(default_factory=list)
    overall_passed: bool = False
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "execution_id": self.execution_id,
            "timestamp_utc": self.timestamp_utc,
            "gate_results": [g.to_dict() for g in self.gate_results],
            "delta_evidence": [d.to_dict() for d in self.delta_evidence],
            "correlation_evidence": [c.to_dict() for c in self.correlation_evidence],
            "overall_passed": self.overall_passed,
            "errors": self.errors,
        }


class RedisDeltaCollector:
    """Collector for Redis delta evidence on canonical indexes.

    Monitors the following canonical indexes:
    - paper:index:signals (or paper:signal:* pattern)
    - paper:index:orders (or paper:order:* pattern)
    - paper:index:fills (or paper:fill:* pattern)
    - paper:index:outcomes (or paper:outcome:* pattern)
    - bmad:chiseai:scheduler:heartbeat
    - bmad:chiseai:kill_switch

    Attributes:
        redis_host: Redis host (default: host.docker.internal)
        redis_port: Redis port (default: 6380)
    """

    # Canonical index keys
    SIGNAL_INDEX_KEY = "paper:index:signals"
    ORDER_INDEX_KEY = "paper:index:orders"
    FILL_INDEX_KEY = "paper:index:fills"
    OUTCOME_INDEX_KEY = "paper:index:outcomes"
    HEARTBEAT_KEY = "bmad:chiseai:scheduler:heartbeat"
    KILL_SWITCH_KEY = "bmad:chiseai:kill_switch"

    # Key patterns for data retrieval
    SIGNAL_PATTERN = "paper:signal:*"
    ORDER_PATTERN = "paper:order:*"
    FILL_PATTERN = "paper:fill:*"
    OUTCOME_PATTERN = "paper:outcome:*"

    def __init__(
        self, redis_host: str = "host.docker.internal", redis_port: int = 6380
    ):
        """Initialize the Redis Delta Collector.

        Args:
            redis_host: Redis host address
            redis_port: Redis port
        """
        self.redis_host = redis_host
        self.redis_port = redis_port
        self._redis: Any = None
        self._baseline_timestamp: datetime | None = None

        logger.info(f"RedisDeltaCollector initialized: {redis_host}:{redis_port}")

    def _get_redis(self) -> Any:
        """Get or create Redis client."""
        if self._redis is None:
            try:
                import redis as redis_lib

                self._redis = redis_lib.Redis(
                    host=self.redis_host,
                    port=self.redis_port,
                    decode_responses=True,
                )
                # Test connection
                self._redis.ping()
                logger.debug(
                    f"Connected to Redis at {self.redis_host}:{self.redis_port}"
                )
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {e}")
                raise
        return self._redis

    async def capture_baseline(self) -> dict[str, int]:
        """Capture baseline counts for all indexes.

        Returns:
            Dictionary mapping index names to counts
        """
        redis = self._get_redis()
        self._baseline_timestamp = datetime.now(UTC)

        baseline: dict[str, int] = {}

        try:
            # Get counts for sorted set indexes (ZCARD)
            for index_key in [
                self.SIGNAL_INDEX_KEY,
                self.ORDER_INDEX_KEY,
                self.FILL_INDEX_KEY,
                self.OUTCOME_INDEX_KEY,
            ]:
                try:
                    count = redis.zcard(index_key)
                    baseline[index_key] = count
                    logger.debug(f"Baseline {index_key}: {count}")
                except Exception:
                    # Key might not exist
                    baseline[index_key] = 0
                    logger.debug(f"Baseline {index_key}: 0 (not found)")

            # Get heartbeat timestamp (if exists)
            try:
                heartbeat = redis.get(self.HEARTBEAT_KEY)
                baseline[self.HEARTBEAT_KEY] = 1 if heartbeat else 0
            except Exception:
                baseline[self.HEARTBEAT_KEY] = 0

            logger.info(f"Baseline captured at {self._baseline_timestamp.isoformat()}")
            return baseline

        except Exception as e:
            logger.error(f"Failed to capture baseline: {e}")
            raise

    async def capture_final(self, baseline: dict[str, int]) -> list[RedisDeltaEvidence]:
        """Capture final counts and calculate deltas.

        Args:
            baseline: Baseline counts from capture_baseline()

        Returns:
            List of RedisDeltaEvidence for each index
        """
        redis = self._get_redis()
        final_timestamp = datetime.now(UTC)
        evidence_list: list[RedisDeltaEvidence] = []

        try:
            for index_key, start_count in baseline.items():
                try:
                    if index_key == self.HEARTBEAT_KEY:
                        # Heartbeat is a simple key, not a sorted set
                        heartbeat = redis.get(self.HEARTBEAT_KEY)
                        end_count = 1 if heartbeat else 0
                    elif index_key == self.KILL_SWITCH_KEY:
                        # Kill switch is a hash
                        kill_switch = redis.hgetall(self.KILL_SWITCH_KEY)
                        end_count = 1 if kill_switch else 0
                    else:
                        # Sorted set indexes
                        end_count = redis.zcard(index_key)
                except Exception:
                    end_count = 0

                delta = end_count - start_count

                # Get sample IDs of new records
                sample_ids = await self.get_new_ids(index_key, self._baseline_timestamp)

                evidence = RedisDeltaEvidence(
                    index_name=index_key,
                    start_count=start_count,
                    end_count=end_count,
                    delta=delta,
                    sample_ids=sample_ids[:10],  # Limit to 10 samples
                    timestamp_start_utc=(
                        self._baseline_timestamp.isoformat()
                        if self._baseline_timestamp
                        else ""
                    ),
                    timestamp_end_utc=final_timestamp.isoformat(),
                )
                evidence_list.append(evidence)
                logger.info(
                    f"Delta for {index_key}: {start_count} -> {end_count} (delta={delta})"
                )

            return evidence_list

        except Exception as e:
            logger.error(f"Failed to capture final: {e}")
            raise

    async def get_new_ids(self, index_name: str, since: datetime | None) -> list[str]:
        """Get IDs of records created since baseline.

        Args:
            index_name: Name of the index/key
            since: Baseline timestamp

        Returns:
            List of new record IDs
        """
        if since is None:
            return []

        redis = self._get_redis()
        new_ids: list[str] = []

        try:
            if index_name in [
                self.SIGNAL_INDEX_KEY,
                self.ORDER_INDEX_KEY,
                self.FILL_INDEX_KEY,
                self.OUTCOME_INDEX_KEY,
            ]:
                # Get members added since baseline timestamp
                min_score = since.timestamp()
                # Use ZRANGEBYSCORE to get members added after baseline
                new_ids = redis.zrangebyscore(index_name, min_score, "+inf")
                logger.debug(f"Found {len(new_ids)} new IDs in {index_name}")

        except Exception as e:
            logger.warning(f"Failed to get new IDs for {index_name}: {e}")

        return new_ids

    async def build_correlation_proof(
        self, signal_ids: list[str]
    ) -> list[CorrelationEvidence]:
        """Build correlation chain: signal -> order -> fill -> outcome.

        Args:
            signal_ids: List of signal IDs to trace

        Returns:
            List of CorrelationEvidence for each complete chain found
        """
        redis = self._get_redis()
        evidence_list: list[CorrelationEvidence] = []

        for signal_id in signal_ids[:5]:  # Limit to 5 signals
            try:
                # Get signal data
                signal_keys = redis.keys(f"paper:signal:*:{signal_id}")
                if not signal_keys:
                    # Try alternate pattern
                    signal_keys = redis.keys(f"paper:signal:*{signal_id}*")

                if not signal_keys:
                    continue

                signal_key = signal_keys[0]
                signal_data_raw = redis.get(signal_key)
                if not signal_data_raw:
                    continue

                signal_data = json.loads(signal_data_raw)

                # Find orders with this signal_id
                order_keys = []
                all_order_keys = redis.keys(self.ORDER_PATTERN.replace("*", "*"))
                for order_key in all_order_keys[:100]:  # Limit scan
                    order_data_raw = redis.get(order_key)
                    if order_data_raw:
                        order_data = json.loads(order_data_raw)
                        if order_data.get("signal_id") == signal_id:
                            order_keys.append(order_key)
                            break

                if not order_keys:
                    continue

                order_key = order_keys[0]
                order_data_raw = redis.get(order_key)
                order_data = json.loads(order_data_raw) if order_data_raw else {}
                order_id = order_data.get("order_id", "")

                # Find fills with this order_id
                fill_keys = redis.keys(f"paper:fill:*:{order_id}")
                if not fill_keys:
                    fill_keys = redis.keys(f"paper:fill:*{order_id}*")

                fill_data: dict[str, Any] = {}
                fill_id = order_id  # Fill ID is typically same as order_id

                if fill_keys:
                    fill_data_raw = redis.get(fill_keys[0])
                    fill_data = json.loads(fill_data_raw) if fill_data_raw else {}

                # Find outcomes with this signal_id
                outcome_keys = []
                all_outcome_keys = redis.keys(self.OUTCOME_PATTERN.replace("*", "*"))
                for outcome_key in all_outcome_keys[:100]:  # Limit scan
                    outcome_data_raw = redis.get(outcome_key)
                    if outcome_data_raw:
                        outcome_data = json.loads(outcome_data_raw)
                        if outcome_data.get("signal_id") == signal_id:
                            outcome_keys.append(outcome_key)
                            break

                outcome_id = ""
                outcome_data = {}

                if outcome_keys:
                    outcome_data_raw = redis.get(outcome_keys[0])
                    outcome_data = (
                        json.loads(outcome_data_raw) if outcome_data_raw else {}
                    )
                    outcome_id = outcome_data.get("outcome_id", "")

                # Only create evidence if we have a complete chain
                if signal_id and order_id:
                    evidence = CorrelationEvidence(
                        signal_id=signal_id,
                        order_id=order_id,
                        fill_id=fill_id,
                        outcome_id=outcome_id,
                        correlation_chain=["signal", "order", "fill", "outcome"],
                        data={
                            "signal": signal_data,
                            "order": order_data,
                            "fill": fill_data,
                            "outcome": outcome_data,
                        },
                    )
                    evidence_list.append(evidence)
                    logger.info(
                        f"Built correlation chain: {signal_id} -> {order_id} -> {fill_id} -> {outcome_id}"
                    )

            except Exception as e:
                logger.warning(
                    f"Failed to build correlation for signal {signal_id}: {e}"
                )

        return evidence_list

    def validate_g1(self, evidence: RedisDeltaEvidence) -> GateResult:
        """G1: Scheduler continuity - check heartbeat.

        Validates that the scheduler heartbeat is present and updating.

        Args:
            evidence: Delta evidence for heartbeat

        Returns:
            GateResult with pass/fail status
        """
        if evidence.index_name != self.HEARTBEAT_KEY:
            return GateResult(
                name="G1",
                status=GateStatus.ERROR,
                message=f"Invalid index for G1: {evidence.index_name}",
            )

        if evidence.end_count == 0:
            return GateResult(
                name="G1",
                status=GateStatus.FAIL,
                message="Scheduler heartbeat not found - scheduler not running",
                evidence=evidence.to_dict(),
            )

        return GateResult(
            name="G1",
            status=GateStatus.PASS,
            message="Scheduler heartbeat present - scheduler running",
            evidence=evidence.to_dict(),
        )

    def validate_g2(self, evidence: RedisDeltaEvidence) -> GateResult:
        """G2: Signal cadence - delta > 0.

        Validates that new signals are being generated during the validation window.

        Args:
            evidence: Delta evidence for signals index

        Returns:
            GateResult with pass/fail status
        """
        if evidence.index_name != self.SIGNAL_INDEX_KEY:
            return GateResult(
                name="G2",
                status=GateStatus.ERROR,
                message=f"Invalid index for G2: {evidence.index_name}",
            )

        if evidence.delta == 0:
            return GateResult(
                name="G2",
                status=GateStatus.FAIL,
                message="No new signals generated during validation window (delta=0)",
                evidence=evidence.to_dict(),
            )

        return GateResult(
            name="G2",
            status=GateStatus.PASS,
            message=f"Signal generation active: {evidence.delta} new signals",
            evidence=evidence.to_dict(),
        )

    def validate_g3(self, evidence: RedisDeltaEvidence) -> GateResult:
        """G3: Outcome flow - delta > 0.

        Validates that outcomes are being produced during the validation window.

        Args:
            evidence: Delta evidence for outcomes index

        Returns:
            GateResult with pass/fail status
        """
        if evidence.index_name != self.OUTCOME_INDEX_KEY:
            return GateResult(
                name="G3",
                status=GateStatus.ERROR,
                message=f"Invalid index for G3: {evidence.index_name}",
            )

        if evidence.delta == 0:
            return GateResult(
                name="G3",
                status=GateStatus.FAIL,
                message="No new outcomes produced during validation window (delta=0)",
                evidence=evidence.to_dict(),
            )

        return GateResult(
            name="G3",
            status=GateStatus.PASS,
            message=f"Outcome flow active: {evidence.delta} new outcomes",
            evidence=evidence.to_dict(),
        )

    def validate_g4(self, kill_switch_state: dict[str, Any] | None) -> GateResult:
        """G4: Kill switch - enabled and not triggered.

        Validates that the kill switch is properly configured and not in triggered state.

        Args:
            kill_switch_state: Current kill switch state from Redis

        Returns:
            GateResult with pass/fail status
        """
        if kill_switch_state is None:
            return GateResult(
                name="G4",
                status=GateStatus.ERROR,
                message="Kill switch state not found in Redis",
                evidence={"state": None},
            )

        # Check if kill switch is enabled (configured)
        is_enabled = kill_switch_state.get("enabled", "false").lower() == "true"

        # Check if kill switch has been triggered
        is_triggered = kill_switch_state.get("triggered", "false").lower() == "true"

        if is_triggered:
            return GateResult(
                name="G4",
                status=GateStatus.FAIL,
                message="Kill switch has been triggered - trading halted",
                evidence=kill_switch_state,
            )

        if not is_enabled:
            return GateResult(
                name="G4",
                status=GateStatus.FAIL,
                message="Kill switch not enabled - safety mechanism inactive",
                evidence=kill_switch_state,
            )

        return GateResult(
            name="G4",
            status=GateStatus.PASS,
            message="Kill switch enabled and not triggered - safety active",
            evidence=kill_switch_state,
        )

    async def get_kill_switch_state(self) -> dict[str, Any] | None:
        """Get current kill switch state from Redis.

        Returns:
            Dictionary with kill switch state or None if not found
        """
        redis = self._get_redis()

        try:
            state = redis.hgetall(self.KILL_SWITCH_KEY)
            return state if state else None
        except Exception as e:
            logger.warning(f"Failed to get kill switch state: {e}")
            return None

    async def run_validation(
        self, validation_window_seconds: int = 60
    ) -> ValidationReport:
        """Run complete G1-G4 validation.

        Args:
            validation_window_seconds: Seconds to wait between baseline and final capture

        Returns:
            ValidationReport with all gate results and evidence
        """
        report = ValidationReport()

        try:
            # Capture baseline
            logger.info("Capturing baseline counts...")
            baseline = await self.capture_baseline()

            # Wait for validation window
            logger.info(
                f"Waiting {validation_window_seconds}s for validation window..."
            )
            await asyncio.sleep(validation_window_seconds)

            # Capture final counts
            logger.info("Capturing final counts...")
            delta_evidence = await self.capture_final(baseline)
            report.delta_evidence = delta_evidence

            # Build evidence map for easy lookup
            evidence_map = {e.index_name: e for e in delta_evidence}

            # Validate G1: Scheduler continuity
            if self.HEARTBEAT_KEY in evidence_map:
                g1_result = self.validate_g1(evidence_map[self.HEARTBEAT_KEY])
            else:
                g1_result = GateResult(
                    name="G1",
                    status=GateStatus.ERROR,
                    message="No heartbeat evidence captured",
                )
            report.gate_results.append(g1_result)

            # Validate G2: Signal cadence
            if self.SIGNAL_INDEX_KEY in evidence_map:
                g2_result = self.validate_g2(evidence_map[self.SIGNAL_INDEX_KEY])
            else:
                g2_result = GateResult(
                    name="G2",
                    status=GateStatus.ERROR,
                    message="No signal evidence captured",
                )
            report.gate_results.append(g2_result)

            # Validate G3: Outcome flow
            if self.OUTCOME_INDEX_KEY in evidence_map:
                g3_result = self.validate_g3(evidence_map[self.OUTCOME_INDEX_KEY])
            else:
                g3_result = GateResult(
                    name="G3",
                    status=GateStatus.ERROR,
                    message="No outcome evidence captured",
                )
            report.gate_results.append(g3_result)

            # Validate G4: Kill switch
            kill_switch_state = await self.get_kill_switch_state()
            g4_result = self.validate_g4(kill_switch_state)
            report.gate_results.append(g4_result)

            # Build correlation proofs if we have new signals
            if self.SIGNAL_INDEX_KEY in evidence_map:
                new_signal_ids = evidence_map[self.SIGNAL_INDEX_KEY].sample_ids
                if new_signal_ids:
                    logger.info(
                        f"Building correlation proofs for {len(new_signal_ids)} signals..."
                    )
                    correlation_evidence = await self.build_correlation_proof(
                        new_signal_ids
                    )
                    report.correlation_evidence = correlation_evidence

            # Determine overall pass/fail
            report.overall_passed = all(
                r.status == GateStatus.PASS for r in report.gate_results
            )

            logger.info(
                f"Validation complete: {'PASSED' if report.overall_passed else 'FAILED'}"
            )

        except Exception as e:
            logger.error(f"Validation failed with error: {e}")
            report.errors.append(str(e))
            report.overall_passed = False

        return report


async def main() -> int:
    """Main entry point for CLI execution."""
    # Get configuration from environment
    redis_host = os.getenv("REDIS_HOST", "host.docker.internal")
    redis_port = int(os.getenv("REDIS_PORT", "6380"))
    validation_window = int(os.getenv("VALIDATION_WINDOW_SECONDS", "60"))

    # Create collector
    collector = RedisDeltaCollector(redis_host=redis_host, redis_port=redis_port)

    try:
        # Run validation
        report = await collector.run_validation(
            validation_window_seconds=validation_window
        )

        # Print report
        print("\n" + "=" * 60)
        print("REDIS DELTA VALIDATION REPORT")
        print("=" * 60)
        print(f"Execution ID: {report.execution_id}")
        print(f"Timestamp: {report.timestamp_utc}")
        print(f"Overall: {'PASSED' if report.overall_passed else 'FAILED'}")
        print("-" * 60)

        print("\nGate Results:")
        for gate in report.gate_results:
            icon = "✓" if gate.status == GateStatus.PASS else "✗"
            print(f"  {icon} {gate.name}: {gate.status.value} - {gate.message}")

        print("\nDelta Evidence:")
        for delta in report.delta_evidence:
            print(
                f"  {delta.index_name}: {delta.start_count} -> {delta.end_count} (delta={delta.delta})"
            )

        if report.correlation_evidence:
            print(f"\nCorrelation Chains: {len(report.correlation_evidence)}")
            for corr in report.correlation_evidence[:3]:
                print(
                    f"  {corr.signal_id} -> {corr.order_id} -> {corr.fill_id} -> {corr.outcome_id}"
                )

        if report.errors:
            print(f"\nErrors: {report.errors}")

        print("=" * 60)

        # Write JSON report
        report_path = f"docs/evidence/redis_delta_report_{report.execution_id}.json"
        os.makedirs(os.path.dirname(report_path), exist_ok=True)
        with open(report_path, "w") as f:
            json.dump(report.to_dict(), f, indent=2)
        print(f"\nReport written to: {report_path}")

        return 0 if report.overall_passed else 1

    except Exception as e:
        logger.error(f"Validation failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
