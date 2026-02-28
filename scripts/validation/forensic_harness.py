"""
Forensic Validation Harness

A fail-safe validation harness where gates can ONLY pass with required
runtime-generated artifacts. Auto-captures raw artifacts at T0/T5/T10/T15/T20/T25/T30
and evaluates PASS/FAIL strictly from those artifacts.

Fail-Safe Mechanism:
1. Any missing required artifact = auto-FAIL
2. Zero delta for G1-G4 = FAIL
3. Gate evaluator has no manual override capability
4. All timestamps are monotonic UTC
"""

import asyncio
import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Callable
from enum import Enum
import uuid


class GateStatus(Enum):
    """Gate evaluation status."""

    PASS = "PASS"
    FAIL = "FAIL"
    PENDING = "PENDING"


class ArtifactType(Enum):
    """Types of artifacts that can be captured."""

    REDIS_DELTA = "redis_delta"
    DISCORD_MESSAGE = "discord_message"
    INFLUX_QUERY = "influx_query"
    SCHEDULER_HEARTBEAT = "scheduler_heartbeat"
    SIGNAL_COUNT_DELTA = "signal_count_delta"
    OUTCOME_COUNT_DELTA = "outcome_count_delta"
    KILL_SWITCH_STATE = "kill_switch_state"
    BURN_IN_VERDICT = "burn_in_verdict"


@dataclass
class Artifact:
    """
    A captured artifact containing evidence data.

    Attributes:
        gate: The gate this artifact belongs to (e.g., "G1", "G2")
        artifact_type: Type of artifact (e.g., "redis_delta", "discord_message")
        data: The actual evidence data
        source_path: Where this artifact came from (e.g., "redis://chiseai-redis:6380")
        captured_at: ISO format UTC timestamp when captured
        artifact_id: Unique identifier for this artifact
    """

    gate: str
    artifact_type: str
    data: Dict[str, Any]
    source_path: str
    captured_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    artifact_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> Dict[str, Any]:
        """Convert artifact to dictionary."""
        return asdict(self)


@dataclass
class Snapshot:
    """
    A snapshot in time containing multiple artifacts.

    Attributes:
        timestamp_utc: ISO format UTC timestamp
        label: Label like "T0", "T5", "T10", etc.
        artifacts: Dictionary mapping artifact names to Artifact objects
        snapshot_id: Unique identifier for this snapshot
    """

    timestamp_utc: str
    label: str
    artifacts: Dict[str, Artifact] = field(default_factory=dict)
    snapshot_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> Dict[str, Any]:
        """Convert snapshot to dictionary."""
        return {
            "snapshot_id": self.snapshot_id,
            "timestamp_utc": self.timestamp_utc,
            "label": self.label,
            "artifacts": {name: art.to_dict() for name, art in self.artifacts.items()},
        }


@dataclass
class GateResult:
    """
    Result of evaluating a single gate.

    Attributes:
        gate: Gate identifier (e.g., "G1", "G2")
        status: PASS or FAIL
        artifacts_found: List of artifact names found
        artifacts_missing: List of required artifact names that were missing
        validation_errors: List of validation error messages
        evaluated_at: ISO format UTC timestamp
    """

    gate: str
    status: GateStatus
    artifacts_found: List[str] = field(default_factory=list)
    artifacts_missing: List[str] = field(default_factory=list)
    validation_errors: List[str] = field(default_factory=list)
    evaluated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert gate result to dictionary."""
        return {
            "gate": self.gate,
            "status": self.status.value,
            "artifacts_found": self.artifacts_found,
            "artifacts_missing": self.artifacts_missing,
            "validation_errors": self.validation_errors,
            "evaluated_at": self.evaluated_at,
        }


@dataclass
class ProofResult:
    """
    Result of the entire proof loop.

    Attributes:
        start_time: ISO format UTC when proof loop started
        end_time: ISO format UTC when proof loop ended
        snapshots: List of all snapshots taken
        gate_results: Dictionary mapping gate IDs to GateResult
        overall_status: PASS only if ALL gates PASS
        proof_id: Unique identifier for this proof run
    """

    start_time: str
    end_time: str
    snapshots: List[Snapshot]
    gate_results: Dict[str, GateResult]
    overall_status: GateStatus
    proof_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> Dict[str, Any]:
        """Convert proof result to dictionary."""
        return {
            "proof_id": self.proof_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "snapshots": [s.to_dict() for s in self.snapshots],
            "gate_results": {
                gate: result.to_dict() for gate, result in self.gate_results.items()
            },
            "overall_status": self.overall_status.value,
        }


@dataclass
class EvidenceBundle:
    """
    Immutable evidence bundle containing all proof artifacts.

    Attributes:
        proof_result: The complete proof result
        bundle_hash: SHA-256 hash of the bundle for integrity
        created_at: ISO format UTC timestamp
        bundle_id: Unique identifier for this bundle
    """

    proof_result: ProofResult
    bundle_hash: str
    created_at: str
    bundle_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> Dict[str, Any]:
        """Convert evidence bundle to dictionary."""
        return {
            "bundle_id": self.bundle_id,
            "bundle_hash": self.bundle_hash,
            "created_at": self.created_at,
            "proof_result": self.proof_result.to_dict(),
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert evidence bundle to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, default=str)


# Gate requirements definition
GATE_REQUIREMENTS: Dict[str, List[str]] = {
    "G1": ["scheduler_heartbeat"],
    "G2": ["signal_count_delta"],
    "G3": ["outcome_count_delta"],
    "G4": ["kill_switch_state"],
    "G5": ["discord_open_msg", "discord_close_msg", "discord_recap_msg"],
    "G6": ["influx_orders_query", "influx_fills_query"],
    "G7": ["influx_canary_query"],
    "G8": ["burn_in_verdict"],
}

# Gates that require non-zero delta validation
ZERO_DELTA_GATES = ["G1", "G2", "G3", "G4"]


class ForensicHarness:
    """
    Forensic validation harness for automated evidence collection and gate evaluation.

    This harness enforces a fail-safe mechanism where:
    - Gates can ONLY pass if ALL required artifacts are present
    - Any missing artifact = auto-FAIL
    - Zero delta for G1-G4 = FAIL
    - No manual override capability exists
    - All timestamps are monotonic UTC

    Usage:
        harness = ForensicHarness(duration_minutes=30, snapshot_interval_minutes=5)
        result = await harness.run_proof_loop()
        bundle = harness.generate_bundle()
    """

    def __init__(
        self,
        duration_minutes: int = 30,
        snapshot_interval_minutes: int = 5,
        artifact_collectors: Optional[Dict[str, Callable]] = None,
    ):
        """
        Initialize the forensic harness.

        Args:
            duration_minutes: Total duration of the proof loop (default: 30)
            snapshot_interval_minutes: Interval between snapshots (default: 5)
            artifact_collectors: Optional dict mapping artifact types to collector functions
        """
        self.duration = duration_minutes
        self.interval = snapshot_interval_minutes
        self.snapshots: List[Snapshot] = []
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self._running = False
        self._artifact_collectors = artifact_collectors or {}
        self._proof_result: Optional[ProofResult] = None

    def _generate_snapshot_labels(self) -> List[str]:
        """Generate snapshot labels (T0, T5, T10, etc.)."""
        labels = ["T0"]  # Always start with T0
        current = self.interval
        while current <= self.duration:
            labels.append(f"T{current}")
            current += self.interval
        return labels

    def _validate_monotonic_timestamps(self) -> List[str]:
        """
        Validate that all snapshot timestamps are monotonically increasing.

        Returns:
            List of error messages (empty if valid)
        """
        errors = []
        if len(self.snapshots) < 2:
            return errors

        for i in range(1, len(self.snapshots)):
            prev_ts = datetime.fromisoformat(self.snapshots[i - 1].timestamp_utc)
            curr_ts = datetime.fromisoformat(self.snapshots[i].timestamp_utc)
            if curr_ts <= prev_ts:
                errors.append(
                    f"Non-monotonic timestamp at snapshot {i}: "
                    f"{self.snapshots[i].timestamp_utc} <= {self.snapshots[i - 1].timestamp_utc}"
                )
        return errors

    async def _collect_artifacts_for_snapshot(self, label: str) -> Dict[str, Artifact]:
        """
        Collect all artifacts for a snapshot.

        This method calls registered artifact collectors to gather evidence.

        Args:
            label: Snapshot label (e.g., "T0", "T5")

        Returns:
            Dictionary mapping artifact names to Artifact objects
        """
        artifacts: Dict[str, Artifact] = {}
        timestamp = datetime.now(timezone.utc).isoformat()

        # Collect artifacts from registered collectors
        for artifact_name, collector in self._artifact_collectors.items():
            try:
                if asyncio.iscoroutinefunction(collector):
                    data = await collector()
                else:
                    data = collector()

                # Determine which gate this artifact belongs to
                gate = self._get_gate_for_artifact(artifact_name)

                artifacts[artifact_name] = Artifact(
                    gate=gate,
                    artifact_type=self._get_artifact_type(artifact_name),
                    data=data if isinstance(data, dict) else {"value": data},
                    source_path=self._get_source_path(artifact_name),
                    captured_at=timestamp,
                )
            except Exception as e:
                # Failed collection results in no artifact (will cause gate FAIL)
                artifacts[artifact_name] = Artifact(
                    gate=self._get_gate_for_artifact(artifact_name),
                    artifact_type=self._get_artifact_type(artifact_name),
                    data={"error": str(e), "collected": False},
                    source_path=self._get_source_path(artifact_name),
                    captured_at=timestamp,
                )

        return artifacts

    def _get_gate_for_artifact(self, artifact_name: str) -> str:
        """Determine which gate an artifact belongs to."""
        for gate, artifacts in GATE_REQUIREMENTS.items():
            if artifact_name in artifacts:
                return gate
        return "UNKNOWN"

    def _get_artifact_type(self, artifact_name: str) -> str:
        """Determine the artifact type from the name."""
        type_mapping = {
            "scheduler_heartbeat": ArtifactType.SCHEDULER_HEARTBEAT.value,
            "signal_count_delta": ArtifactType.SIGNAL_COUNT_DELTA.value,
            "outcome_count_delta": ArtifactType.OUTCOME_COUNT_DELTA.value,
            "kill_switch_state": ArtifactType.KILL_SWITCH_STATE.value,
            "burn_in_verdict": ArtifactType.BURN_IN_VERDICT.value,
            "discord_open_msg": ArtifactType.DISCORD_MESSAGE.value,
            "discord_close_msg": ArtifactType.DISCORD_MESSAGE.value,
            "discord_recap_msg": ArtifactType.DISCORD_MESSAGE.value,
            "influx_orders_query": ArtifactType.INFLUX_QUERY.value,
            "influx_fills_query": ArtifactType.INFLUX_QUERY.value,
            "influx_canary_query": ArtifactType.INFLUX_QUERY.value,
        }
        return type_mapping.get(artifact_name, "unknown")

    def _get_source_path(self, artifact_name: str) -> str:
        """Determine the source path for an artifact."""
        source_mapping = {
            "scheduler_heartbeat": "redis://chiseai-redis:6380/scheduler:heartbeat",
            "signal_count_delta": "redis://chiseai-redis:6380/signals:count",
            "outcome_count_delta": "redis://chiseai-redis:6380/outcomes:count",
            "kill_switch_state": "redis://chiseai-redis:6380/killswitch:state",
            "burn_in_verdict": "redis://chiseai-redis:6380/burnin:verdict",
            "discord_open_msg": "discord://channel/open",
            "discord_close_msg": "discord://channel/close",
            "discord_recap_msg": "discord://channel/recap",
            "influx_orders_query": "influxdb://chiseai-influxdb:18087/orders",
            "influx_fills_query": "influxdb://chiseai-influxdb:18087/fills",
            "influx_canary_query": "influxdb://chiseai-influxdb:18087/canary",
        }
        return source_mapping.get(artifact_name, "unknown://source")

    async def run_proof_loop(self) -> ProofResult:
        """
        Run the proof loop, collecting snapshots at regular intervals.

        This method runs for the configured duration, taking snapshots
        at each interval boundary (T0, T5, T10, etc.).

        Returns:
            ProofResult containing all snapshots and gate evaluations
        """
        self.start_time = datetime.now(timezone.utc)
        self.snapshots = []
        self._running = True

        labels = self._generate_snapshot_labels()

        # Take T0 snapshot immediately
        t0_artifacts = await self._collect_artifacts_for_snapshot("T0")
        self.snapshots.append(
            Snapshot(
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                label="T0",
                artifacts=t0_artifacts,
            )
        )

        # Wait for intervals and take remaining snapshots
        for i, label in enumerate(labels[1:], 1):
            if not self._running:
                break

            # Calculate wait time
            elapsed = (datetime.now(timezone.utc) - self.start_time).total_seconds()
            target_elapsed = i * self.interval * 60
            wait_seconds = max(0, target_elapsed - elapsed)

            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)

            if not self._running:
                break

            artifacts = await self._collect_artifacts_for_snapshot(label)
            self.snapshots.append(
                Snapshot(
                    timestamp_utc=datetime.now(timezone.utc).isoformat(),
                    label=label,
                    artifacts=artifacts,
                )
            )

        self.end_time = datetime.now(timezone.utc)
        self._running = False

        # Validate monotonic timestamps
        timestamp_errors = self._validate_monotonic_timestamps()

        # Evaluate all gates
        gate_results = {}
        for gate in GATE_REQUIREMENTS.keys():
            gate_results[gate] = self.evaluate_gate(gate, GATE_REQUIREMENTS[gate])

        # Overall status is PASS only if ALL gates PASS
        overall_status = GateStatus.PASS
        if timestamp_errors:
            overall_status = GateStatus.FAIL
        else:
            for result in gate_results.values():
                if result.status == GateStatus.FAIL:
                    overall_status = GateStatus.FAIL
                    break

        self._proof_result = ProofResult(
            start_time=self.start_time.isoformat(),
            end_time=self.end_time.isoformat(),
            snapshots=self.snapshots,
            gate_results=gate_results,
            overall_status=overall_status,
        )

        return self._proof_result

    def stop(self):
        """Stop the proof loop early."""
        self._running = False

    def evaluate_gate(self, gate: str, required_artifacts: List[str]) -> GateResult:
        """
        Evaluate a gate - PASS only if ALL required artifacts present and valid.

        Fail-Safe Rules:
        1. Any missing required artifact = auto-FAIL
        2. Zero delta for G1-G4 = FAIL
        3. Discord messages must have message IDs
        4. Influx queries must have results

        Args:
            gate: Gate identifier (e.g., "G1", "G2")
            required_artifacts: List of required artifact names

        Returns:
            GateResult with PASS or FAIL status
        """
        artifacts_found = []
        artifacts_missing = []
        validation_errors = []

        # Check all snapshots for required artifacts
        all_artifacts: Dict[str, List[Artifact]] = {}
        for snapshot in self.snapshots:
            for art_name, artifact in snapshot.artifacts.items():
                if art_name not in all_artifacts:
                    all_artifacts[art_name] = []
                all_artifacts[art_name].append(artifact)

        # Check each required artifact
        for req_art in required_artifacts:
            if req_art not in all_artifacts:
                artifacts_missing.append(req_art)
                validation_errors.append(f"Missing required artifact: {req_art}")
            else:
                artifacts_found.append(req_art)

                # Validate artifact content
                for artifact in all_artifacts[req_art]:
                    error = self._validate_artifact_content(gate, req_art, artifact)
                    if error:
                        validation_errors.append(error)

        # Determine status
        status = GateStatus.PASS
        if artifacts_missing:
            status = GateStatus.FAIL
        if validation_errors:
            status = GateStatus.FAIL

        return GateResult(
            gate=gate,
            status=status,
            artifacts_found=artifacts_found,
            artifacts_missing=artifacts_missing,
            validation_errors=validation_errors,
        )

    def _validate_artifact_content(
        self, gate: str, artifact_name: str, artifact: Artifact
    ) -> Optional[str]:
        """
        Validate the content of a specific artifact.

        Args:
            gate: Gate identifier
            artifact_name: Name of the artifact
            artifact: The artifact to validate

        Returns:
            Error message if validation fails, None if valid
        """
        data = artifact.data

        # Check for collection errors
        if data.get("error") and not data.get("collected", True):
            return f"Artifact {artifact_name} failed to collect: {data.get('error')}"

        # G1-G4: Zero delta check
        if gate in ZERO_DELTA_GATES:
            if "delta" in data and data["delta"] == 0:
                return f"Gate {gate}: Zero delta detected for {artifact_name}"
            if "value" in data and data["value"] == 0:
                return f"Gate {gate}: Zero value detected for {artifact_name}"
            if "count" in data and data["count"] == 0:
                return f"Gate {gate}: Zero count detected for {artifact_name}"

        # G5: Discord messages must have message IDs
        if gate == "G5":
            if "message_id" not in data:
                return f"Gate G5: Discord message {artifact_name} missing message_id"
            if not data.get("message_id"):
                return f"Gate G5: Discord message {artifact_name} has empty message_id"

        # G6-G7: Influx queries must have results
        if gate in ["G6", "G7"]:
            if "results" not in data and "result" not in data:
                return f"Gate {gate}: Influx query {artifact_name} missing results"

        return None

    def generate_bundle(self) -> EvidenceBundle:
        """
        Generate immutable evidence bundle.

        Creates a cryptographically verifiable bundle containing:
        - All snapshots with artifacts
        - All gate evaluation results
        - Integrity hash

        Returns:
            EvidenceBundle with complete proof evidence

        Raises:
            RuntimeError: If proof loop hasn't been run yet
        """
        if self._proof_result is None:
            raise RuntimeError("Proof loop must be run before generating bundle")

        import hashlib

        # Create deterministic JSON representation
        bundle_data = json.dumps(
            self._proof_result.to_dict(),
            sort_keys=True,
            default=str,
        )

        # Generate hash
        bundle_hash = hashlib.sha256(bundle_data.encode()).hexdigest()

        return EvidenceBundle(
            proof_result=self._proof_result,
            bundle_hash=bundle_hash,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def get_snapshot_at(self, label: str) -> Optional[Snapshot]:
        """Get snapshot by label (e.g., "T0", "T5")."""
        for snapshot in self.snapshots:
            if snapshot.label == label:
                return snapshot
        return None

    def get_artifact_history(self, artifact_name: str) -> List[Artifact]:
        """Get all instances of an artifact across snapshots."""
        history = []
        for snapshot in self.snapshots:
            if artifact_name in snapshot.artifacts:
                history.append(snapshot.artifacts[artifact_name])
        return history


# Convenience functions for creating collectors


def create_redis_collector(
    redis_client, key: str, field: Optional[str] = None
) -> Callable:
    """
    Create an artifact collector for Redis data.

    Args:
        redis_client: Redis client instance
        key: Redis key to fetch
        field: Optional hash field to fetch

    Returns:
        Collector function
    """

    def collector():
        if field:
            value = redis_client.hget(key, field)
        else:
            value = redis_client.get(key)
        return {
            "key": key,
            "field": field,
            "value": value.decode() if isinstance(value, bytes) else value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    return collector


def create_discord_collector(
    discord_client, channel_id: str, message_type: str
) -> Callable:
    """
    Create an artifact collector for Discord messages.

    Args:
        discord_client: Discord client instance
        channel_id: Discord channel ID
        message_type: Type of message to collect

    Returns:
        Collector function
    """

    async def collector():
        # This is a placeholder - actual implementation would use discord client
        messages = await discord_client.fetch_messages(channel_id, limit=10)
        for msg in messages:
            if message_type in msg.content.lower():
                return {
                    "message_id": msg.id,
                    "channel_id": channel_id,
                    "content": msg.content,
                    "timestamp": msg.created_at.isoformat(),
                }
        return {"message_id": None, "error": f"No {message_type} message found"}

    return collector


def create_influx_collector(influx_client, query: str) -> Callable:
    """
    Create an artifact collector for InfluxDB queries.

    Args:
        influx_client: InfluxDB client instance
        query: InfluxQL query to execute

    Returns:
        Collector function
    """

    def collector():
        result = influx_client.query(query)
        return {
            "query": query,
            "results": list(result.get_points()) if result else [],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    return collector


if __name__ == "__main__":
    # Example usage
    async def example():
        """Example of using the forensic harness."""
        harness = ForensicHarness(duration_minutes=30, snapshot_interval_minutes=5)

        # Run proof loop
        result = await harness.run_proof_loop()

        # Print results
        print(f"Proof ID: {result.proof_id}")
        print(f"Overall Status: {result.overall_status.value}")
        print(f"Snapshots taken: {len(result.snapshots)}")

        for gate, gate_result in result.gate_results.items():
            print(f"\n{gate}: {gate_result.status.value}")
            if gate_result.artifacts_missing:
                print(f"  Missing: {gate_result.artifacts_missing}")
            if gate_result.validation_errors:
                print(f"  Errors: {gate_result.validation_errors}")

        # Generate bundle
        bundle = harness.generate_bundle()
        print(f"\nBundle Hash: {bundle.bundle_hash}")

    asyncio.run(example())


# Import all collectors for integrated harness
try:
    from scripts.validation.discord_evidence import DiscordEvidenceCollector
    from scripts.validation.redis_deltas import RedisDeltaCollector
    from scripts.validation.influx_evidence import InfluxEvidenceCollector
    from scripts.validation.recap_validator import RecapValidator

    COLLECTORS_AVAILABLE = True
except ImportError:
    COLLECTORS_AVAILABLE = False


class IntegratedForensicHarness(ForensicHarness):
    """Harness with all collectors integrated.

    This harness provides a complete 30-minute proof loop with automatic
    collection from all evidence sources:
    - Redis (G1-G4): Scheduler heartbeat, signals, outcomes, kill switch
    - Discord (G5): OPEN, CLOSE, RECAP messages
    - InfluxDB (G6-G7): Orders, fills, canary deployment
    - Recap Validator: Source verification for G5

    Usage:
        harness = IntegratedForensicHarness(duration_minutes=30)
        result = await harness.run_integrated_proof_loop()
        bundle = harness.generate_bundle()
    """

    def __init__(self, duration_minutes: int = 30):
        """Initialize the integrated forensic harness.

        Args:
            duration_minutes: Total duration of the proof loop (default: 30)

        Raises:
            RuntimeError: If collector modules are not available
        """
        if not COLLECTORS_AVAILABLE:
            raise RuntimeError(
                "Collector modules not available. "
                "Ensure all validation modules are installed."
            )

        super().__init__(
            duration_minutes=duration_minutes,
            snapshot_interval_minutes=5,
        )

        # Initialize collectors
        self.redis_collector = RedisDeltaCollector()
        self.discord_collector = DiscordEvidenceCollector(
            bot_token=os.getenv("DISCORD_BOT_TOKEN"),
            trading_channel_id=os.getenv("TRADING_CHANNEL_ID", "1444447985378398459"),
        )
        self.influx_collector = InfluxEvidenceCollector()
        self.recap_validator = RecapValidator(
            redis_collector=self.redis_collector, influx_collector=self.influx_collector
        )

        # Track baseline and final states
        self._baseline_captured = False
        self._final_captured = False

    async def capture_baseline(self) -> Dict[str, Any]:
        """Capture baseline state (T0) from all collectors.

        Returns:
            Dictionary containing baseline evidence from all sources
        """
        baseline = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "label": "T0",
        }

        # Capture Redis baseline
        try:
            redis_baseline = await self.redis_collector.capture_baseline()
            baseline["redis"] = redis_baseline
        except Exception as e:
            baseline["redis_error"] = str(e)

        # Capture Discord baseline (messages before proof window)
        try:
            now = datetime.now(timezone.utc)
            discord_messages = await self.discord_collector.collect_messages(
                since=now - timedelta(minutes=30), until=now
            )
            baseline["discord"] = {
                "message_count": len(discord_messages),
                "messages": [m.to_dict() for m in discord_messages],
            }
        except Exception as e:
            baseline["discord_error"] = str(e)

        # Capture InfluxDB baseline
        try:
            orders = await self.influx_collector.query_orders(
                since=datetime.now(timezone.utc) - timedelta(hours=1)
            )
            fills = await self.influx_collector.query_fills(
                since=datetime.now(timezone.utc) - timedelta(hours=1)
            )
            baseline["influx"] = {
                "orders": orders.to_dict() if hasattr(orders, "to_dict") else orders,
                "fills": fills.to_dict() if hasattr(fills, "to_dict") else fills,
            }
        except Exception as e:
            baseline["influx_error"] = str(e)

        self._baseline_captured = True
        return baseline

    async def capture_snapshot(self, label: str) -> Dict[str, Any]:
        """Capture a snapshot at the given label.

        Args:
            label: Snapshot label (e.g., "T5", "T10")

        Returns:
            Dictionary containing snapshot evidence
        """
        snapshot: Dict[str, Any] = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "label": label,
        }

        # Capture Redis snapshot - use get_kill_switch_state for current state
        try:
            kill_switch_state = await self.redis_collector.get_kill_switch_state()
            snapshot["redis"] = {
                "kill_switch": kill_switch_state,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            snapshot["redis_error"] = str(e)

        # Capture Discord snapshot
        try:
            now = datetime.now(timezone.utc)
            discord_messages = await self.discord_collector.collect_messages(
                since=now - timedelta(minutes=5), until=now
            )
            snapshot["discord"] = {
                "message_count": len(discord_messages),
                "messages": [m.to_dict() for m in discord_messages],
            }
        except Exception as e:
            snapshot["discord_error"] = str(e)

        # Capture InfluxDB snapshot
        try:
            orders = await self.influx_collector.query_orders(
                since=datetime.now(timezone.utc) - timedelta(minutes=5)
            )
            fills = await self.influx_collector.query_fills(
                since=datetime.now(timezone.utc) - timedelta(minutes=5)
            )
            snapshot["influx"] = {
                "orders": orders.to_dict() if hasattr(orders, "to_dict") else orders,
                "fills": fills.to_dict() if hasattr(fills, "to_dict") else fills,
            }
        except Exception as e:
            snapshot["influx_error"] = str(e)

        return snapshot

    async def capture_final(self, baseline: Dict[str, Any]) -> Dict[str, Any]:
        """Capture final state and compute deltas.

        Args:
            baseline: The baseline state captured at T0

        Returns:
            Dictionary containing final state and deltas
        """
        final: Dict[str, Any] = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "label": "T30",
        }

        # Capture Redis final state and compute deltas
        try:
            redis_baseline = baseline.get("redis", {})
            if redis_baseline:
                redis_final = await self.redis_collector.capture_final(redis_baseline)
                # Compute deltas from the evidence list
                deltas: Dict[str, Any] = {}
                for evidence in redis_final:
                    deltas[evidence.index_name] = evidence.delta
                final["redis"] = {
                    "final_state": [e.to_dict() for e in redis_final],
                    "deltas": deltas,
                }
            else:
                final["redis"] = {"final_state": [], "deltas": {}}
        except Exception as e:
            final["redis_error"] = str(e)

        # Capture Discord final state
        try:
            now = datetime.now(timezone.utc)
            discord_messages = await self.discord_collector.collect_messages(
                since=now - timedelta(minutes=30), until=now
            )
            final["discord"] = {
                "message_count": len(discord_messages),
                "messages": [m.to_dict() for m in discord_messages],
            }

            # Validate G5: Check for OPEN, CLOSE, RECAP messages
            open_msgs = [m for m in discord_messages if m.content_type == "OPEN"]
            close_msgs = [m for m in discord_messages if m.content_type == "CLOSE"]
            recap_msgs = [m for m in discord_messages if m.content_type == "RECAP"]

            final["discord_validation"] = {
                "has_open": len(open_msgs) > 0,
                "has_close": len(close_msgs) > 0,
                "has_recap": len(recap_msgs) > 0,
                "open_count": len(open_msgs),
                "close_count": len(close_msgs),
                "recap_count": len(recap_msgs),
            }
        except Exception as e:
            final["discord_error"] = str(e)

        # Capture InfluxDB final state
        try:
            orders = await self.influx_collector.query_orders(
                since=datetime.now(timezone.utc) - timedelta(minutes=30)
            )
            fills = await self.influx_collector.query_fills(
                since=datetime.now(timezone.utc) - timedelta(minutes=30)
            )
            canary = await self.influx_collector.query_canary(
                since=datetime.now(timezone.utc) - timedelta(minutes=30)
            )
            final["influx"] = {
                "orders": orders.to_dict() if hasattr(orders, "to_dict") else orders,
                "fills": fills.to_dict() if hasattr(fills, "to_dict") else fills,
                "canary": canary.to_dict() if hasattr(canary, "to_dict") else canary,
            }
        except Exception as e:
            final["influx_error"] = str(e)

        self._final_captured = True
        return final

    async def run_integrated_proof_loop(self) -> ProofResult:
        """Run 30-minute proof loop with all collectors.

        This method runs the complete proof loop:
        1. Capture baseline (T0) from all collectors
        2. Every 5 minutes: capture snapshot
        3. At T30: capture final, evaluate all gates
        4. Generate evidence bundle

        Returns:
            ProofResult with all evidence and gate evaluations
        """
        self.start_time = datetime.now(timezone.utc)
        self.snapshots = []
        self._running = True

        # Step 1: Capture baseline (T0)
        baseline = await self.capture_baseline()
        t0_artifacts = await self._convert_baseline_to_artifacts(baseline)
        self.snapshots.append(
            Snapshot(
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                label="T0",
                artifacts=t0_artifacts,
            )
        )

        # Step 2: Capture snapshots every 5 minutes
        labels = ["T5", "T10", "T15", "T20", "T25"]
        for i, label in enumerate(labels):
            if not self._running:
                break

            # Calculate wait time
            elapsed = (datetime.now(timezone.utc) - self.start_time).total_seconds()
            target_elapsed = (i + 1) * 5 * 60  # 5 minutes per interval
            wait_seconds = max(0, target_elapsed - elapsed)

            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)

            if not self._running:
                break

            snapshot_data = await self.capture_snapshot(label)
            artifacts = await self._convert_snapshot_to_artifacts(snapshot_data)
            self.snapshots.append(
                Snapshot(
                    timestamp_utc=datetime.now(timezone.utc).isoformat(),
                    label=label,
                    artifacts=artifacts,
                )
            )

        # Step 3: Capture final state (T30)
        if self._running:
            elapsed = (datetime.now(timezone.utc) - self.start_time).total_seconds()
            target_elapsed = self.duration * 60
            wait_seconds = max(0, target_elapsed - elapsed)

            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)

            final_data = await self.capture_final(baseline)
            final_artifacts = await self._convert_final_to_artifacts(final_data)
            self.snapshots.append(
                Snapshot(
                    timestamp_utc=datetime.now(timezone.utc).isoformat(),
                    label="T30",
                    artifacts=final_artifacts,
                )
            )

        self.end_time = datetime.now(timezone.utc)
        self._running = False

        # Step 4: Evaluate all gates
        timestamp_errors = self._validate_monotonic_timestamps()
        gate_results = {}
        for gate in GATE_REQUIREMENTS.keys():
            gate_results[gate] = self.evaluate_gate(gate, GATE_REQUIREMENTS[gate])

        # Overall status is PASS only if ALL gates PASS
        overall_status = GateStatus.PASS
        if timestamp_errors:
            overall_status = GateStatus.FAIL
        else:
            for result in gate_results.values():
                if result.status == GateStatus.FAIL:
                    overall_status = GateStatus.FAIL
                    break

        self._proof_result = ProofResult(
            start_time=self.start_time.isoformat(),
            end_time=self.end_time.isoformat(),
            snapshots=self.snapshots,
            gate_results=gate_results,
            overall_status=overall_status,
        )

        return self._proof_result

    async def _convert_baseline_to_artifacts(
        self, baseline: Dict[str, Any]
    ) -> Dict[str, Artifact]:
        """Convert baseline data to artifacts."""
        artifacts = {}
        timestamp = baseline.get(
            "timestamp_utc", datetime.now(timezone.utc).isoformat()
        )

        # Redis artifacts (G1-G4)
        if "redis" in baseline:
            redis_data = baseline["redis"]
            artifacts["scheduler_heartbeat"] = Artifact(
                gate="G1",
                artifact_type=ArtifactType.SCHEDULER_HEARTBEAT.value,
                data=redis_data.get("heartbeat", {}),
                source_path="redis://chiseai-redis:6380/scheduler:heartbeat",
                captured_at=timestamp,
            )
            artifacts["signal_count_delta"] = Artifact(
                gate="G2",
                artifact_type=ArtifactType.SIGNAL_COUNT_DELTA.value,
                data={"count": redis_data.get("signal_count", 0)},
                source_path="redis://chiseai-redis:6380/signals:count",
                captured_at=timestamp,
            )
            artifacts["outcome_count_delta"] = Artifact(
                gate="G3",
                artifact_type=ArtifactType.OUTCOME_COUNT_DELTA.value,
                data={"count": redis_data.get("outcome_count", 0)},
                source_path="redis://chiseai-redis:6380/outcomes:count",
                captured_at=timestamp,
            )
            artifacts["kill_switch_state"] = Artifact(
                gate="G4",
                artifact_type=ArtifactType.KILL_SWITCH_STATE.value,
                data=redis_data.get("kill_switch", {}),
                source_path="redis://chiseai-redis:6380/killswitch:state",
                captured_at=timestamp,
            )

        return artifacts

    async def _convert_snapshot_to_artifacts(
        self, snapshot: Dict[str, Any]
    ) -> Dict[str, Artifact]:
        """Convert snapshot data to artifacts."""
        artifacts = {}
        timestamp = snapshot.get(
            "timestamp_utc", datetime.now(timezone.utc).isoformat()
        )

        # Redis artifacts
        if "redis" in snapshot:
            redis_data = snapshot["redis"]
            artifacts["scheduler_heartbeat"] = Artifact(
                gate="G1",
                artifact_type=ArtifactType.SCHEDULER_HEARTBEAT.value,
                data=redis_data.get("heartbeat", {}),
                source_path="redis://chiseai-redis:6380/scheduler:heartbeat",
                captured_at=timestamp,
            )

        # Discord artifacts
        if "discord" in snapshot:
            discord_data = snapshot["discord"]
            messages = discord_data.get("messages", [])
            for msg in messages:
                content_type = msg.get("content_type", "").lower()
                if content_type == "open":
                    artifacts["discord_open_msg"] = Artifact(
                        gate="G5",
                        artifact_type=ArtifactType.DISCORD_MESSAGE.value,
                        data=msg,
                        source_path=f"discord://channel/{msg.get('channel_id', 'unknown')}/open",
                        captured_at=timestamp,
                    )
                elif content_type == "close":
                    artifacts["discord_close_msg"] = Artifact(
                        gate="G5",
                        artifact_type=ArtifactType.DISCORD_MESSAGE.value,
                        data=msg,
                        source_path=f"discord://channel/{msg.get('channel_id', 'unknown')}/close",
                        captured_at=timestamp,
                    )
                elif content_type == "recap":
                    artifacts["discord_recap_msg"] = Artifact(
                        gate="G5",
                        artifact_type=ArtifactType.DISCORD_MESSAGE.value,
                        data=msg,
                        source_path=f"discord://channel/{msg.get('channel_id', 'unknown')}/recap",
                        captured_at=timestamp,
                    )

        # InfluxDB artifacts
        if "influx" in snapshot:
            influx_data = snapshot["influx"]
            artifacts["influx_orders_query"] = Artifact(
                gate="G6",
                artifact_type=ArtifactType.INFLUX_QUERY.value,
                data=influx_data.get("orders", {}),
                source_path="influxdb://chiseai-influxdb:18087/orders",
                captured_at=timestamp,
            )
            artifacts["influx_fills_query"] = Artifact(
                gate="G6",
                artifact_type=ArtifactType.INFLUX_QUERY.value,
                data=influx_data.get("fills", {}),
                source_path="influxdb://chiseai-influxdb:18087/fills",
                captured_at=timestamp,
            )

        return artifacts

    async def _convert_final_to_artifacts(
        self, final: Dict[str, Any]
    ) -> Dict[str, Artifact]:
        """Convert final data to artifacts."""
        artifacts = {}
        timestamp = final.get("timestamp_utc", datetime.now(timezone.utc).isoformat())

        # Redis artifacts with deltas
        if "redis" in final:
            redis_data = final["redis"]
            deltas = redis_data.get("deltas", {})

            artifacts["scheduler_heartbeat"] = Artifact(
                gate="G1",
                artifact_type=ArtifactType.SCHEDULER_HEARTBEAT.value,
                data={
                    "delta": deltas.get("heartbeat_delta", 0),
                    **redis_data.get("final_state", {}).get("heartbeat", {}),
                },
                source_path="redis://chiseai-redis:6380/scheduler:heartbeat",
                captured_at=timestamp,
            )
            artifacts["signal_count_delta"] = Artifact(
                gate="G2",
                artifact_type=ArtifactType.SIGNAL_COUNT_DELTA.value,
                data={
                    "delta": deltas.get("signal_delta", 0),
                    "count": redis_data.get("final_state", {}).get("signal_count", 0),
                },
                source_path="redis://chiseai-redis:6380/signals:count",
                captured_at=timestamp,
            )
            artifacts["outcome_count_delta"] = Artifact(
                gate="G3",
                artifact_type=ArtifactType.OUTCOME_COUNT_DELTA.value,
                data={
                    "delta": deltas.get("outcome_delta", 0),
                    "count": redis_data.get("final_state", {}).get("outcome_count", 0),
                },
                source_path="redis://chiseai-redis:6380/outcomes:count",
                captured_at=timestamp,
            )
            artifacts["kill_switch_state"] = Artifact(
                gate="G4",
                artifact_type=ArtifactType.KILL_SWITCH_STATE.value,
                data={
                    "delta": deltas.get("kill_switch_delta", 0),
                    **redis_data.get("final_state", {}).get("kill_switch", {}),
                },
                source_path="redis://chiseai-redis:6380/killswitch:state",
                captured_at=timestamp,
            )

        # Discord artifacts
        if "discord" in final:
            discord_data = final["discord"]
            messages = discord_data.get("messages", [])
            validation = final.get("discord_validation", {})

            for msg in messages:
                content_type = msg.get("content_type", "").lower()
                if content_type == "open":
                    artifacts["discord_open_msg"] = Artifact(
                        gate="G5",
                        artifact_type=ArtifactType.DISCORD_MESSAGE.value,
                        data={**msg, "validated": validation.get("has_open", False)},
                        source_path=f"discord://channel/{msg.get('channel_id', 'unknown')}/open",
                        captured_at=timestamp,
                    )
                elif content_type == "close":
                    artifacts["discord_close_msg"] = Artifact(
                        gate="G5",
                        artifact_type=ArtifactType.DISCORD_MESSAGE.value,
                        data={**msg, "validated": validation.get("has_close", False)},
                        source_path=f"discord://channel/{msg.get('channel_id', 'unknown')}/close",
                        captured_at=timestamp,
                    )
                elif content_type == "recap":
                    artifacts["discord_recap_msg"] = Artifact(
                        gate="G5",
                        artifact_type=ArtifactType.DISCORD_MESSAGE.value,
                        data={**msg, "validated": validation.get("has_recap", False)},
                        source_path=f"discord://channel/{msg.get('channel_id', 'unknown')}/recap",
                        captured_at=timestamp,
                    )

        # InfluxDB artifacts
        if "influx" in final:
            influx_data = final["influx"]
            artifacts["influx_orders_query"] = Artifact(
                gate="G6",
                artifact_type=ArtifactType.INFLUX_QUERY.value,
                data=influx_data.get("orders", {}),
                source_path="influxdb://chiseai-influxdb:18087/orders",
                captured_at=timestamp,
            )
            artifacts["influx_fills_query"] = Artifact(
                gate="G6",
                artifact_type=ArtifactType.INFLUX_QUERY.value,
                data=influx_data.get("fills", {}),
                source_path="influxdb://chiseai-influxdb:18087/fills",
                captured_at=timestamp,
            )
            if "canary" in influx_data:
                artifacts["influx_canary_query"] = Artifact(
                    gate="G7",
                    artifact_type=ArtifactType.INFLUX_QUERY.value,
                    data=influx_data.get("canary", {}),
                    source_path="influxdb://chiseai-influxdb:18087/canary",
                    captured_at=timestamp,
                )

        return artifacts

    async def close(self):
        """Close all collectors and release resources."""
        # Close Discord collector (has close method)
        try:
            await self.discord_collector.close()
        except Exception:
            pass

        # Redis and Influx collectors don't have close methods - they use
        # connection pooling that cleans up automatically
