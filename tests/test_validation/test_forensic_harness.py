"""
Tests for Forensic Validation Harness

Comprehensive test suite covering:
- Harness initialization
- Snapshot capture at intervals
- Gate evaluation (PASS/FAIL scenarios)
- Monotonic timestamp validation
- Bundle generation
- Fail-safe mechanisms
"""

import asyncio
import json
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, AsyncMock, patch
from typing import Dict, Any

# Import the harness classes
import sys

sys.path.insert(0, "/home/tacopants/projects/ChiseAI")

from scripts.validation.forensic_harness import (
    ForensicHarness,
    Artifact,
    Snapshot,
    GateResult,
    ProofResult,
    EvidenceBundle,
    GateStatus,
    ArtifactType,
    GATE_REQUIREMENTS,
    ZERO_DELTA_GATES,
    create_redis_collector,
    create_discord_collector,
    create_influx_collector,
)


class TestForensicHarnessInitialization:
    """Tests for harness initialization."""

    def test_harness_initializes_with_defaults(self):
        """Test harness initializes with default parameters."""
        harness = ForensicHarness()

        assert harness.duration == 30
        assert harness.interval == 5
        assert harness.snapshots == []
        assert harness.start_time is None
        assert harness._running is False

    def test_harness_initializes_with_custom_params(self):
        """Test harness initializes with custom parameters."""
        harness = ForensicHarness(duration_minutes=60, snapshot_interval_minutes=10)

        assert harness.duration == 60
        assert harness.interval == 10

    def test_harness_initializes_with_collectors(self):
        """Test harness initializes with artifact collectors."""
        mock_collector = MagicMock(return_value={"test": "data"})
        collectors = {"test_artifact": mock_collector}

        harness = ForensicHarness(artifact_collectors=collectors)

        assert "test_artifact" in harness._artifact_collectors
        assert harness._artifact_collectors["test_artifact"] == mock_collector

    def test_generate_snapshot_labels_default(self):
        """Test snapshot label generation with default 30-min duration."""
        harness = ForensicHarness(duration_minutes=30, snapshot_interval_minutes=5)
        labels = harness._generate_snapshot_labels()

        expected = ["T0", "T5", "T10", "T15", "T20", "T25", "T30"]
        assert labels == expected

    def test_generate_snapshot_labels_custom(self):
        """Test snapshot label generation with custom parameters."""
        harness = ForensicHarness(duration_minutes=15, snapshot_interval_minutes=5)
        labels = harness._generate_snapshot_labels()

        expected = ["T0", "T5", "T10", "T15"]
        assert labels == expected


class TestSnapshotCapture:
    """Tests for snapshot capture functionality."""

    @pytest.fixture
    def mock_collectors(self):
        """Create mock artifact collectors."""
        return {
            "scheduler_heartbeat": MagicMock(
                return_value={
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "status": "healthy",
                }
            ),
            "signal_count_delta": MagicMock(return_value={"delta": 5, "total": 100}),
        }

    @pytest.mark.asyncio
    async def test_snapshot_capture_creates_artifacts(self, mock_collectors):
        """Test that snapshot capture creates artifacts from collectors."""
        harness = ForensicHarness(artifact_collectors=mock_collectors)

        artifacts = await harness._collect_artifacts_for_snapshot("T0")

        assert "scheduler_heartbeat" in artifacts
        assert "signal_count_delta" in artifacts
        assert artifacts["scheduler_heartbeat"].gate == "G1"
        assert artifacts["signal_count_delta"].gate == "G2"

    @pytest.mark.asyncio
    async def test_snapshot_capture_handles_async_collectors(self):
        """Test that snapshot capture handles async collectors."""
        async_collector = AsyncMock(return_value={"async": "data"})
        collectors = {"async_artifact": async_collector}

        harness = ForensicHarness(artifact_collectors=collectors)
        artifacts = await harness._collect_artifacts_for_snapshot("T0")

        assert "async_artifact" in artifacts
        assert artifacts["async_artifact"].data == {"async": "data"}

    @pytest.mark.asyncio
    async def test_snapshot_capture_handles_collector_errors(self):
        """Test that snapshot capture handles collector errors gracefully."""
        error_collector = MagicMock(side_effect=Exception("Collection failed"))
        collectors = {"error_artifact": error_collector}

        harness = ForensicHarness(artifact_collectors=collectors)
        artifacts = await harness._collect_artifacts_for_snapshot("T0")

        assert "error_artifact" in artifacts
        assert "error" in artifacts["error_artifact"].data
        assert artifacts["error_artifact"].data["collected"] is False

    @pytest.mark.asyncio
    async def test_run_proof_loop_creates_snapshots(self):
        """Test that proof loop creates the expected number of snapshots."""
        mock_collectors = {
            "scheduler_heartbeat": MagicMock(return_value={"status": "healthy"}),
        }

        harness = ForensicHarness(
            duration_minutes=5,
            snapshot_interval_minutes=5,
            artifact_collectors=mock_collectors,
        )

        # Mock sleep to speed up test
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await harness.run_proof_loop()

        # Should have T0 and T5 snapshots
        assert len(result.snapshots) == 2
        assert result.snapshots[0].label == "T0"
        assert result.snapshots[1].label == "T5"

    @pytest.mark.asyncio
    async def test_proof_loop_sets_start_and_end_times(self):
        """Test that proof loop sets start and end times correctly."""
        harness = ForensicHarness(
            duration_minutes=5, snapshot_interval_minutes=5, artifact_collectors={}
        )

        before_start = datetime.now(timezone.utc)

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await harness.run_proof_loop()

        after_end = datetime.now(timezone.utc)

        start_time = datetime.fromisoformat(result.start_time)
        end_time = datetime.fromisoformat(result.end_time)

        assert before_start <= start_time <= after_end
        assert start_time <= end_time <= after_end


class TestGateEvaluationPass:
    """Tests for gate evaluation PASS scenarios."""

    def test_gate_passes_with_all_required_artifacts(self):
        """Test that gate PASSES when all required artifacts are present."""
        harness = ForensicHarness()

        # Create snapshot with required G1 artifact
        artifact = Artifact(
            gate="G1",
            artifact_type="scheduler_heartbeat",
            data={"status": "healthy", "count": 1},
            source_path="redis://test",
        )

        harness.snapshots = [
            Snapshot(
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                label="T0",
                artifacts={"scheduler_heartbeat": artifact},
            )
        ]

        result = harness.evaluate_gate("G1", ["scheduler_heartbeat"])

        assert result.status == GateStatus.PASS
        assert "scheduler_heartbeat" in result.artifacts_found
        assert result.artifacts_missing == []

    def test_gate_passes_with_multiple_artifacts(self):
        """Test that gate PASSES with multiple required artifacts."""
        harness = ForensicHarness()

        harness.snapshots = [
            Snapshot(
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                label="T0",
                artifacts={
                    "discord_open_msg": Artifact(
                        gate="G5",
                        artifact_type="discord_message",
                        data={"message_id": "12345", "content": "Open"},
                        source_path="discord://test",
                    ),
                    "discord_close_msg": Artifact(
                        gate="G5",
                        artifact_type="discord_message",
                        data={"message_id": "12346", "content": "Close"},
                        source_path="discord://test",
                    ),
                    "discord_recap_msg": Artifact(
                        gate="G5",
                        artifact_type="discord_message",
                        data={"message_id": "12347", "content": "Recap"},
                        source_path="discord://test",
                    ),
                },
            )
        ]

        result = harness.evaluate_gate(
            "G5", ["discord_open_msg", "discord_close_msg", "discord_recap_msg"]
        )

        assert result.status == GateStatus.PASS
        assert len(result.artifacts_found) == 3

    def test_gate_passes_with_non_zero_delta(self):
        """Test that G1-G4 gates PASS with non-zero delta."""
        harness = ForensicHarness()

        harness.snapshots = [
            Snapshot(
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                label="T0",
                artifacts={
                    "signal_count_delta": Artifact(
                        gate="G2",
                        artifact_type="signal_count_delta",
                        data={"delta": 5, "count": 10},
                        source_path="redis://test",
                    ),
                },
            )
        ]

        result = harness.evaluate_gate("G2", ["signal_count_delta"])

        assert result.status == GateStatus.PASS

    def test_gate_passes_with_influx_results(self):
        """Test that G6-G7 gates PASS with influx query results."""
        harness = ForensicHarness()

        harness.snapshots = [
            Snapshot(
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                label="T0",
                artifacts={
                    "influx_orders_query": Artifact(
                        gate="G6",
                        artifact_type="influx_query",
                        data={
                            "query": "SELECT * FROM orders",
                            "results": [{"order_id": 1}, {"order_id": 2}],
                        },
                        source_path="influxdb://test",
                    ),
                },
            )
        ]

        result = harness.evaluate_gate("G6", ["influx_orders_query"])

        assert result.status == GateStatus.PASS


class TestGateEvaluationFail:
    """Tests for gate evaluation FAIL scenarios."""

    def test_gate_fails_with_missing_artifacts(self):
        """Test that gate FAILS when required artifacts are missing."""
        harness = ForensicHarness()
        harness.snapshots = []  # No snapshots

        result = harness.evaluate_gate("G1", ["scheduler_heartbeat"])

        assert result.status == GateStatus.FAIL
        assert "scheduler_heartbeat" in result.artifacts_missing
        assert (
            "Missing required artifact: scheduler_heartbeat" in result.validation_errors
        )

    def test_gate_fails_with_partial_artifacts(self):
        """Test that gate FAILS when only some required artifacts present."""
        harness = ForensicHarness()

        harness.snapshots = [
            Snapshot(
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                label="T0",
                artifacts={
                    "discord_open_msg": Artifact(
                        gate="G5",
                        artifact_type="discord_message",
                        data={"message_id": "12345"},
                        source_path="discord://test",
                    ),
                    # Missing discord_close_msg and discord_recap_msg
                },
            )
        ]

        result = harness.evaluate_gate(
            "G5", ["discord_open_msg", "discord_close_msg", "discord_recap_msg"]
        )

        assert result.status == GateStatus.FAIL
        assert "discord_open_msg" in result.artifacts_found
        assert "discord_close_msg" in result.artifacts_missing
        assert "discord_recap_msg" in result.artifacts_missing

    def test_gate_fails_with_zero_delta_g1(self):
        """Test that G1 FAILS with zero delta."""
        harness = ForensicHarness()

        harness.snapshots = [
            Snapshot(
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                label="T0",
                artifacts={
                    "scheduler_heartbeat": Artifact(
                        gate="G1",
                        artifact_type="scheduler_heartbeat",
                        data={"delta": 0, "count": 0},
                        source_path="redis://test",
                    ),
                },
            )
        ]

        result = harness.evaluate_gate("G1", ["scheduler_heartbeat"])

        assert result.status == GateStatus.FAIL
        assert any("Zero delta" in err for err in result.validation_errors)

    def test_gate_fails_with_zero_delta_g2(self):
        """Test that G2 FAILS with zero signal count delta."""
        harness = ForensicHarness()

        harness.snapshots = [
            Snapshot(
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                label="T0",
                artifacts={
                    "signal_count_delta": Artifact(
                        gate="G2",
                        artifact_type="signal_count_delta",
                        data={"delta": 0, "count": 100},
                        source_path="redis://test",
                    ),
                },
            )
        ]

        result = harness.evaluate_gate("G2", ["signal_count_delta"])

        assert result.status == GateStatus.FAIL
        assert any("Zero delta" in err for err in result.validation_errors)

    def test_gate_fails_with_zero_delta_g3(self):
        """Test that G3 FAILS with zero outcome count delta."""
        harness = ForensicHarness()

        harness.snapshots = [
            Snapshot(
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                label="T0",
                artifacts={
                    "outcome_count_delta": Artifact(
                        gate="G3",
                        artifact_type="outcome_count_delta",
                        data={"delta": 0},
                        source_path="redis://test",
                    ),
                },
            )
        ]

        result = harness.evaluate_gate("G3", ["outcome_count_delta"])

        assert result.status == GateStatus.FAIL

    def test_gate_fails_with_zero_delta_g4(self):
        """Test that G4 FAILS with zero kill switch state."""
        harness = ForensicHarness()

        harness.snapshots = [
            Snapshot(
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                label="T0",
                artifacts={
                    "kill_switch_state": Artifact(
                        gate="G4",
                        artifact_type="kill_switch_state",
                        data={"value": 0},
                        source_path="redis://test",
                    ),
                },
            )
        ]

        result = harness.evaluate_gate("G4", ["kill_switch_state"])

        assert result.status == GateStatus.FAIL

    def test_g5_fails_without_message_id(self):
        """Test that G5 FAILS when discord messages lack message_id."""
        harness = ForensicHarness()

        harness.snapshots = [
            Snapshot(
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                label="T0",
                artifacts={
                    "discord_open_msg": Artifact(
                        gate="G5",
                        artifact_type="discord_message",
                        data={"content": "Open"},  # Missing message_id
                        source_path="discord://test",
                    ),
                },
            )
        ]

        result = harness.evaluate_gate("G5", ["discord_open_msg"])

        assert result.status == GateStatus.FAIL
        assert any("missing message_id" in err for err in result.validation_errors)

    def test_g5_fails_with_empty_message_id(self):
        """Test that G5 FAILS when discord messages have empty message_id."""
        harness = ForensicHarness()

        harness.snapshots = [
            Snapshot(
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                label="T0",
                artifacts={
                    "discord_open_msg": Artifact(
                        gate="G5",
                        artifact_type="discord_message",
                        data={"message_id": "", "content": "Open"},
                        source_path="discord://test",
                    ),
                },
            )
        ]

        result = harness.evaluate_gate("G5", ["discord_open_msg"])

        assert result.status == GateStatus.FAIL
        assert any("empty message_id" in err for err in result.validation_errors)

    def test_g6_fails_without_influx_results(self):
        """Test that G6 FAILS when influx queries lack results."""
        harness = ForensicHarness()

        harness.snapshots = [
            Snapshot(
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                label="T0",
                artifacts={
                    "influx_orders_query": Artifact(
                        gate="G6",
                        artifact_type="influx_query",
                        data={"query": "SELECT * FROM orders"},  # Missing results
                        source_path="influxdb://test",
                    ),
                },
            )
        ]

        result = harness.evaluate_gate("G6", ["influx_orders_query"])

        assert result.status == GateStatus.FAIL
        assert any("missing results" in err for err in result.validation_errors)

    def test_g7_fails_without_influx_results(self):
        """Test that G7 FAILS when canary query lacks results."""
        harness = ForensicHarness()

        harness.snapshots = [
            Snapshot(
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                label="T0",
                artifacts={
                    "influx_canary_query": Artifact(
                        gate="G7",
                        artifact_type="influx_query",
                        data={"query": "SELECT * FROM canary"},
                        source_path="influxdb://test",
                    ),
                },
            )
        ]

        result = harness.evaluate_gate("G7", ["influx_canary_query"])

        assert result.status == GateStatus.FAIL

    def test_gate_fails_with_collector_error(self):
        """Test that gate FAILS when artifact collection had errors."""
        harness = ForensicHarness()

        harness.snapshots = [
            Snapshot(
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                label="T0",
                artifacts={
                    "scheduler_heartbeat": Artifact(
                        gate="G1",
                        artifact_type="scheduler_heartbeat",
                        data={"error": "Redis connection failed", "collected": False},
                        source_path="redis://test",
                    ),
                },
            )
        ]

        result = harness.evaluate_gate("G1", ["scheduler_heartbeat"])

        assert result.status == GateStatus.FAIL
        assert any("failed to collect" in err for err in result.validation_errors)


class TestMonotonicTimestampValidation:
    """Tests for monotonic timestamp validation."""

    def test_validates_monotonic_timestamps(self):
        """Test that timestamps are validated as monotonically increasing."""
        harness = ForensicHarness()

        base_time = datetime.now(timezone.utc)

        harness.snapshots = [
            Snapshot(timestamp_utc=(base_time).isoformat(), label="T0", artifacts={}),
            Snapshot(
                timestamp_utc=(base_time + timedelta(minutes=5)).isoformat(),
                label="T5",
                artifacts={},
            ),
            Snapshot(
                timestamp_utc=(base_time + timedelta(minutes=10)).isoformat(),
                label="T10",
                artifacts={},
            ),
        ]

        errors = harness._validate_monotonic_timestamps()

        assert errors == []

    def test_detects_non_monotonic_timestamps(self):
        """Test that non-monotonic timestamps are detected."""
        harness = ForensicHarness()

        base_time = datetime.now(timezone.utc)

        harness.snapshots = [
            Snapshot(
                timestamp_utc=(base_time + timedelta(minutes=10)).isoformat(),
                label="T10",
                artifacts={},
            ),
            Snapshot(
                timestamp_utc=(base_time + timedelta(minutes=5)).isoformat(),
                label="T5",
                artifacts={},
            ),
        ]

        errors = harness._validate_monotonic_timestamps()

        assert len(errors) == 1
        assert "Non-monotonic timestamp" in errors[0]

    def test_detects_equal_timestamps(self):
        """Test that equal timestamps are detected as non-monotonic."""
        harness = ForensicHarness()

        same_time = datetime.now(timezone.utc).isoformat()

        harness.snapshots = [
            Snapshot(timestamp_utc=same_time, label="T0", artifacts={}),
            Snapshot(timestamp_utc=same_time, label="T5", artifacts={}),
        ]

        errors = harness._validate_monotonic_timestamps()

        assert len(errors) == 1

    @pytest.mark.asyncio
    async def test_overall_status_fails_on_non_monotonic(self):
        """Test that overall status is FAIL when timestamps are non-monotonic."""
        harness = ForensicHarness(
            duration_minutes=5,
            snapshot_interval_minutes=5,
            artifact_collectors={"test": MagicMock(return_value={})},
        )

        # Manually create snapshots with non-monotonic timestamps
        base_time = datetime.now(timezone.utc)
        harness.snapshots = [
            Snapshot(
                timestamp_utc=(base_time + timedelta(minutes=10)).isoformat(),
                label="T0",
                artifacts={"test": Artifact("G1", "test", {}, "test")},
            ),
            Snapshot(
                timestamp_utc=base_time.isoformat(),
                label="T5",
                artifacts={"test": Artifact("G1", "test", {}, "test")},
            ),
        ]

        # Manually set proof result with non-monotonic timestamps
        harness._proof_result = ProofResult(
            start_time=base_time.isoformat(),
            end_time=base_time.isoformat(),
            snapshots=harness.snapshots,
            gate_results={"G1": GateResult("G1", GateStatus.PASS)},
            overall_status=GateStatus.PASS,
        )

        # Validate timestamps
        errors = harness._validate_monotonic_timestamps()
        assert len(errors) > 0


class TestBundleGeneration:
    """Tests for evidence bundle generation."""

    @pytest.fixture
    def completed_harness(self):
        """Create a harness with a completed proof loop."""
        harness = ForensicHarness()

        harness.snapshots = [
            Snapshot(
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                label="T0",
                artifacts={
                    "scheduler_heartbeat": Artifact(
                        gate="G1",
                        artifact_type="scheduler_heartbeat",
                        data={"status": "healthy"},
                        source_path="redis://test",
                    ),
                },
            )
        ]

        harness._proof_result = ProofResult(
            start_time=datetime.now(timezone.utc).isoformat(),
            end_time=datetime.now(timezone.utc).isoformat(),
            snapshots=harness.snapshots,
            gate_results={"G1": GateResult("G1", GateStatus.PASS)},
            overall_status=GateStatus.PASS,
        )

        return harness

    def test_bundle_generation_requires_proof_loop(self):
        """Test that bundle generation requires proof loop to be run."""
        harness = ForensicHarness()

        with pytest.raises(RuntimeError, match="Proof loop must be run"):
            harness.generate_bundle()

    def test_bundle_contains_proof_result(self, completed_harness):
        """Test that bundle contains the complete proof result."""
        bundle = completed_harness.generate_bundle()

        assert bundle.proof_result is not None
        assert bundle.proof_result.overall_status == GateStatus.PASS
        assert len(bundle.proof_result.snapshots) == 1

    def test_bundle_has_hash(self, completed_harness):
        """Test that bundle has a SHA-256 hash."""
        bundle = completed_harness.generate_bundle()

        assert bundle.bundle_hash is not None
        assert len(bundle.bundle_hash) == 64  # SHA-256 hex length
        assert all(c in "0123456789abcdef" for c in bundle.bundle_hash)

    def test_bundle_has_timestamp(self, completed_harness):
        """Test that bundle has creation timestamp."""
        bundle = completed_harness.generate_bundle()

        assert bundle.created_at is not None
        # Should be valid ISO format
        datetime.fromisoformat(bundle.created_at)

    def test_bundle_has_unique_id(self, completed_harness):
        """Test that bundle has unique identifier."""
        bundle = completed_harness.generate_bundle()

        assert bundle.bundle_id is not None
        assert len(bundle.bundle_id) > 0

    def test_bundle_to_dict(self, completed_harness):
        """Test that bundle can be converted to dictionary."""
        bundle = completed_harness.generate_bundle()
        data = bundle.to_dict()

        assert "bundle_id" in data
        assert "bundle_hash" in data
        assert "created_at" in data
        assert "proof_result" in data

    def test_bundle_to_json(self, completed_harness):
        """Test that bundle can be converted to JSON."""
        bundle = completed_harness.generate_bundle()
        json_str = bundle.to_json()

        # Should be valid JSON
        data = json.loads(json_str)
        assert "bundle_id" in data
        assert "bundle_hash" in data

    def test_bundle_hash_is_deterministic(self, completed_harness):
        """Test that bundle hash is deterministic for same data."""
        bundle1 = completed_harness.generate_bundle()
        bundle2 = completed_harness.generate_bundle()

        assert bundle1.bundle_hash == bundle2.bundle_hash


class TestHelperFunctions:
    """Tests for helper collector functions."""

    def test_create_redis_collector(self):
        """Test Redis collector creation."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = b"test_value"

        collector = create_redis_collector(mock_redis, "test_key")
        result = collector()

        assert result["key"] == "test_key"
        assert result["value"] == "test_value"
        assert "timestamp" in result

    def test_create_redis_collector_with_field(self):
        """Test Redis collector with hash field."""
        mock_redis = MagicMock()
        mock_redis.hget.return_value = b"field_value"

        collector = create_redis_collector(mock_redis, "test_hash", "test_field")
        result = collector()

        assert result["key"] == "test_hash"
        assert result["field"] == "test_field"
        assert result["value"] == "field_value"

    @pytest.mark.asyncio
    async def test_create_discord_collector(self):
        """Test Discord collector creation."""
        mock_discord = AsyncMock()
        mock_message = MagicMock()
        mock_message.id = "12345"
        mock_message.content = "Open message"
        mock_message.created_at = datetime.now(timezone.utc)
        mock_discord.fetch_messages.return_value = [mock_message]

        collector = create_discord_collector(mock_discord, "channel_123", "open")
        result = await collector()

        assert result["message_id"] == "12345"
        assert "Open message" in result["content"]

    def test_create_influx_collector(self):
        """Test InfluxDB collector creation."""
        mock_influx = MagicMock()
        mock_result = MagicMock()
        mock_result.get_points.return_value = [{"value": 100}]
        mock_influx.query.return_value = mock_result

        collector = create_influx_collector(mock_influx, "SELECT * FROM test")
        result = collector()

        assert result["query"] == "SELECT * FROM test"
        assert len(result["results"]) == 1
        assert result["results"][0]["value"] == 100


class TestGateRequirements:
    """Tests for gate requirements constants."""

    def test_g1_requirements(self):
        """Test G1 requires scheduler_heartbeat."""
        assert "G1" in GATE_REQUIREMENTS
        assert "scheduler_heartbeat" in GATE_REQUIREMENTS["G1"]

    def test_g2_requirements(self):
        """Test G2 requires signal_count_delta."""
        assert "G2" in GATE_REQUIREMENTS
        assert "signal_count_delta" in GATE_REQUIREMENTS["G2"]

    def test_g3_requirements(self):
        """Test G3 requires outcome_count_delta."""
        assert "G3" in GATE_REQUIREMENTS
        assert "outcome_count_delta" in GATE_REQUIREMENTS["G3"]

    def test_g4_requirements(self):
        """Test G4 requires kill_switch_state."""
        assert "G4" in GATE_REQUIREMENTS
        assert "kill_switch_state" in GATE_REQUIREMENTS["G4"]

    def test_g5_requirements(self):
        """Test G5 requires all discord messages."""
        assert "G5" in GATE_REQUIREMENTS
        assert "discord_open_msg" in GATE_REQUIREMENTS["G5"]
        assert "discord_close_msg" in GATE_REQUIREMENTS["G5"]
        assert "discord_recap_msg" in GATE_REQUIREMENTS["G5"]

    def test_g6_requirements(self):
        """Test G6 requires influx queries."""
        assert "G6" in GATE_REQUIREMENTS
        assert "influx_orders_query" in GATE_REQUIREMENTS["G6"]
        assert "influx_fills_query" in GATE_REQUIREMENTS["G6"]

    def test_g7_requirements(self):
        """Test G7 requires canary query."""
        assert "G7" in GATE_REQUIREMENTS
        assert "influx_canary_query" in GATE_REQUIREMENTS["G7"]

    def test_g8_requirements(self):
        """Test G8 requires burn_in_verdict."""
        assert "G8" in GATE_REQUIREMENTS
        assert "burn_in_verdict" in GATE_REQUIREMENTS["G8"]

    def test_zero_delta_gates(self):
        """Test that G1-G4 are in zero delta gates."""
        assert "G1" in ZERO_DELTA_GATES
        assert "G2" in ZERO_DELTA_GATES
        assert "G3" in ZERO_DELTA_GATES
        assert "G4" in ZERO_DELTA_GATES
        assert "G5" not in ZERO_DELTA_GATES
        assert "G6" not in ZERO_DELTA_GATES


class TestHarnessUtilityMethods:
    """Tests for harness utility methods."""

    def test_get_gate_for_artifact(self):
        """Test artifact to gate mapping."""
        harness = ForensicHarness()

        assert harness._get_gate_for_artifact("scheduler_heartbeat") == "G1"
        assert harness._get_gate_for_artifact("signal_count_delta") == "G2"
        assert harness._get_gate_for_artifact("discord_open_msg") == "G5"
        assert harness._get_gate_for_artifact("unknown_artifact") == "UNKNOWN"

    def test_get_artifact_type(self):
        """Test artifact type determination."""
        harness = ForensicHarness()

        assert (
            harness._get_artifact_type("scheduler_heartbeat")
            == ArtifactType.SCHEDULER_HEARTBEAT.value
        )
        assert (
            harness._get_artifact_type("discord_open_msg")
            == ArtifactType.DISCORD_MESSAGE.value
        )
        assert (
            harness._get_artifact_type("influx_orders_query")
            == ArtifactType.INFLUX_QUERY.value
        )

    def test_get_source_path(self):
        """Test source path determination."""
        harness = ForensicHarness()

        assert "redis://" in harness._get_source_path("scheduler_heartbeat")
        assert "discord://" in harness._get_source_path("discord_open_msg")
        assert "influxdb://" in harness._get_source_path("influx_orders_query")

    def test_get_snapshot_at(self):
        """Test retrieving snapshot by label."""
        harness = ForensicHarness()

        harness.snapshots = [
            Snapshot(
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                label="T0",
                artifacts={},
            ),
            Snapshot(
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                label="T5",
                artifacts={},
            ),
        ]

        snapshot = harness.get_snapshot_at("T5")
        assert snapshot is not None
        assert snapshot.label == "T5"

        missing = harness.get_snapshot_at("T99")
        assert missing is None

    def test_get_artifact_history(self):
        """Test retrieving artifact history across snapshots."""
        harness = ForensicHarness()

        art1 = Artifact("G1", "test", {"v": 1}, "test")
        art2 = Artifact("G1", "test", {"v": 2}, "test")

        harness.snapshots = [
            Snapshot(
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                label="T0",
                artifacts={"test_art": art1},
            ),
            Snapshot(
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                label="T5",
                artifacts={"test_art": art2},
            ),
        ]

        history = harness.get_artifact_history("test_art")
        assert len(history) == 2
        assert history[0].data["v"] == 1
        assert history[1].data["v"] == 2

    def test_stop_proof_loop(self):
        """Test stopping proof loop early."""
        harness = ForensicHarness()
        harness._running = True

        harness.stop()

        assert harness._running is False


class TestDataClassConversions:
    """Tests for dataclass to dictionary conversions."""

    def test_artifact_to_dict(self):
        """Test Artifact to_dict method."""
        artifact = Artifact(
            gate="G1",
            artifact_type="test",
            data={"key": "value"},
            source_path="test://source",
        )

        data = artifact.to_dict()

        assert data["gate"] == "G1"
        assert data["artifact_type"] == "test"
        assert data["data"] == {"key": "value"}
        assert data["source_path"] == "test://source"
        assert "artifact_id" in data
        assert "captured_at" in data

    def test_snapshot_to_dict(self):
        """Test Snapshot to_dict method."""
        artifact = Artifact("G1", "test", {}, "test")
        snapshot = Snapshot(
            timestamp_utc="2024-01-01T00:00:00+00:00",
            label="T0",
            artifacts={"test": artifact},
        )

        data = snapshot.to_dict()

        assert data["label"] == "T0"
        assert data["timestamp_utc"] == "2024-01-01T00:00:00+00:00"
        assert "test" in data["artifacts"]

    def test_gate_result_to_dict(self):
        """Test GateResult to_dict method."""
        result = GateResult(
            gate="G1",
            status=GateStatus.PASS,
            artifacts_found=["art1"],
            artifacts_missing=[],
            validation_errors=[],
        )

        data = result.to_dict()

        assert data["gate"] == "G1"
        assert data["status"] == "PASS"
        assert data["artifacts_found"] == ["art1"]

    def test_proof_result_to_dict(self):
        """Test ProofResult to_dict method."""
        snapshot = Snapshot("2024-01-01T00:00:00+00:00", "T0", {})
        gate_result = GateResult("G1", GateStatus.PASS)

        result = ProofResult(
            start_time="2024-01-01T00:00:00+00:00",
            end_time="2024-01-01T00:30:00+00:00",
            snapshots=[snapshot],
            gate_results={"G1": gate_result},
            overall_status=GateStatus.PASS,
        )

        data = result.to_dict()

        assert data["start_time"] == "2024-01-01T00:00:00+00:00"
        assert data["end_time"] == "2024-01-01T00:30:00+00:00"
        assert data["overall_status"] == "PASS"
        assert len(data["snapshots"]) == 1
        assert "G1" in data["gate_results"]


class TestIntegrationScenarios:
    """Integration-style tests for complete workflows."""

    @pytest.mark.asyncio
    async def test_full_proof_loop_all_gates_pass(self):
        """Test complete proof loop where all gates pass."""
        collectors = {
            "scheduler_heartbeat": MagicMock(return_value={"count": 1, "delta": 1}),
            "signal_count_delta": MagicMock(return_value={"count": 5, "delta": 5}),
            "outcome_count_delta": MagicMock(return_value={"count": 3, "delta": 3}),
            "kill_switch_state": MagicMock(return_value={"value": 1, "delta": 1}),
            "discord_open_msg": MagicMock(
                return_value={"message_id": "123", "content": "Open"}
            ),
            "discord_close_msg": MagicMock(
                return_value={"message_id": "124", "content": "Close"}
            ),
            "discord_recap_msg": MagicMock(
                return_value={"message_id": "125", "content": "Recap"}
            ),
            "influx_orders_query": MagicMock(return_value={"results": [{"id": 1}]}),
            "influx_fills_query": MagicMock(return_value={"results": [{"id": 2}]}),
            "influx_canary_query": MagicMock(
                return_value={"results": [{"status": "ok"}]}
            ),
            "burn_in_verdict": MagicMock(return_value={"verdict": "PASS"}),
        }

        harness = ForensicHarness(
            duration_minutes=5,
            snapshot_interval_minutes=5,
            artifact_collectors=collectors,
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await harness.run_proof_loop()

        assert result.overall_status == GateStatus.PASS
        assert len(result.gate_results) == 8  # G1-G8

        for gate, gate_result in result.gate_results.items():
            assert gate_result.status == GateStatus.PASS, f"Gate {gate} should PASS"

    @pytest.mark.asyncio
    async def test_full_proof_loop_some_gates_fail(self):
        """Test complete proof loop where some gates fail."""
        collectors = {
            "scheduler_heartbeat": MagicMock(
                return_value={"count": 0, "delta": 0}
            ),  # FAIL
            "signal_count_delta": MagicMock(return_value={"count": 5, "delta": 5}),
            "outcome_count_delta": MagicMock(return_value={"count": 3, "delta": 3}),
            "kill_switch_state": MagicMock(return_value={"value": 1}),
            # Missing G5 discord messages
            "influx_orders_query": MagicMock(return_value={"results": [{"id": 1}]}),
            "influx_fills_query": MagicMock(return_value={"results": [{"id": 2}]}),
            "influx_canary_query": MagicMock(
                return_value={"results": [{"status": "ok"}]}
            ),
            "burn_in_verdict": MagicMock(return_value={"verdict": "PASS"}),
        }

        harness = ForensicHarness(
            duration_minutes=5,
            snapshot_interval_minutes=5,
            artifact_collectors=collectors,
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await harness.run_proof_loop()

        assert result.overall_status == GateStatus.FAIL
        assert result.gate_results["G1"].status == GateStatus.FAIL  # Zero delta
        assert result.gate_results["G5"].status == GateStatus.FAIL  # Missing artifacts

    def test_bundle_integrity_verification(self):
        """Test that bundle hash can verify integrity."""
        import hashlib

        harness = ForensicHarness()
        harness.snapshots = [
            Snapshot(
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                label="T0",
                artifacts={"test": Artifact("G1", "test", {"v": 1}, "test")},
            )
        ]

        harness._proof_result = ProofResult(
            start_time=datetime.now(timezone.utc).isoformat(),
            end_time=datetime.now(timezone.utc).isoformat(),
            snapshots=harness.snapshots,
            gate_results={"G1": GateResult("G1", GateStatus.PASS)},
            overall_status=GateStatus.PASS,
        )

        bundle = harness.generate_bundle()

        # Verify hash matches recomputed hash
        bundle_data = json.dumps(
            harness._proof_result.to_dict(), sort_keys=True, default=str
        )
        expected_hash = hashlib.sha256(bundle_data.encode()).hexdigest()

        assert bundle.bundle_hash == expected_hash


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
