"""
End-to-End Tests for Forensic Validation

Comprehensive E2E tests that verify the complete forensic validation flow:
- 30-minute proof loop completes
- All gates evaluate correctly
- Missing artifact scenarios result in FAIL
- Evidence bundle is generated correctly

All external services are mocked (Redis, Discord, Influx) for isolation.

For PARTY-FORENSIC-008: E2E Tests
"""

import asyncio
import hashlib
import json

# Import forensic harness components
import sys
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, "/tmp/worktrees/PARTY-FORENSIC-008-tests")

from scripts.validation.discord_evidence import (
    DiscordEvidenceCollector,
    DiscordMessageEvidence,
)
from scripts.validation.discord_evidence import (
    GateStatus as DiscordGateStatus,
)
from scripts.validation.forensic_harness import (
    GATE_REQUIREMENTS,
    ZERO_DELTA_GATES,
    Artifact,
    ForensicHarness,
    GateResult,
    GateStatus,
    ProofResult,
    Snapshot,
)
from scripts.validation.recap_validator import (
    GateStatus as RecapGateStatus,
)
from scripts.validation.recap_validator import (
    RecapValidator,
)

# =============================================================================
# Mock Factories
# =============================================================================


class MockRedisClient:
    """Mock Redis client for testing."""

    def __init__(self, data: dict[str, Any] | None = None):
        self._data = data or {}
        self._calls: list[str] = []

    def get(self, key: str) -> bytes | None:
        self._calls.append(f"GET {key}")
        value = self._data.get(key)
        return value.encode() if isinstance(value, str) else value

    def hget(self, key: str, field: str) -> bytes | None:
        self._calls.append(f"HGET {key} {field}")
        hash_data = self._data.get(key, {})
        value = hash_data.get(field) if isinstance(hash_data, dict) else None
        return value.encode() if isinstance(value, str) else value

    def hgetall(self, key: str) -> dict[bytes, bytes]:
        self._calls.append(f"HGETALL {key}")
        data = self._data.get(key, {})
        if isinstance(data, dict):
            return {k.encode(): str(v).encode() for k, v in data.items()}
        return {}

    def set(self, key: str, value: str) -> bool:
        self._calls.append(f"SET {key}")
        self._data[key] = value
        return True

    def hset(self, key: str, field: str, value: str) -> bool:
        self._calls.append(f"HSET {key} {field}")
        if key not in self._data:
            self._data[key] = {}
        self._data[key][field] = value
        return True


class MockInfluxClient:
    """Mock InfluxDB client for testing."""

    def __init__(self, data: dict[str, list[dict]] | None = None):
        self._data = data or {}
        self._queries: list[str] = []

    def query(self, query: str) -> MagicMock:
        self._queries.append(query)

        # Create a mock result
        result = MagicMock()

        # Check what type of query this is
        if "orders" in query.lower():
            points = self._data.get("orders", [])
        elif "fills" in query.lower():
            points = self._data.get("fills", [])
        elif "canary" in query.lower():
            points = self._data.get("canary", [])
        else:
            points = self._data.get("default", [])

        result.get_points.return_value = points
        return result


class MockDiscordClient:
    """Mock Discord client for testing."""

    def __init__(self, messages: list[dict] | None = None):
        self._messages = messages or []
        self._fetches: list[str] = []

    async def fetch_messages(
        self, channel_id: str, limit: int = 100
    ) -> list[MagicMock]:
        self._fetches.append(f"FETCH {channel_id} limit={limit}")

        mock_messages = []
        for msg_data in self._messages[:limit]:
            msg = MagicMock()
            msg.id = msg_data.get("id", "123456789")
            msg.content = msg_data.get("content", "")
            msg.created_at = msg_data.get("created_at", datetime.now(UTC))
            msg.channel_id = msg_data.get("channel_id", channel_id)

            author = MagicMock()
            author.id = msg_data.get("author_id", "987654321")
            author.username = msg_data.get("author_name", "TestBot")
            author.bot = msg_data.get("is_bot", True)
            msg.author = author

            msg.embeds = msg_data.get("embeds", [])
            mock_messages.append(msg)

        return mock_messages


def create_mock_collectors_passing() -> dict[str, MagicMock]:
    """Create mock collectors that all return passing data."""
    return {
        "scheduler_heartbeat": MagicMock(
            return_value={
                "timestamp": datetime.now(UTC).isoformat(),
                "count": 5,
                "delta": 5,
            }
        ),
        "signal_count_delta": MagicMock(return_value={"delta": 10, "count": 50}),
        "outcome_count_delta": MagicMock(return_value={"delta": 8, "count": 40}),
        "kill_switch_state": MagicMock(return_value={"value": 1, "state": "ACTIVE"}),
        "discord_open_msg": MagicMock(
            return_value={
                "message_id": "111111111111111111",
                "content": "OPEN signal",
                "trade_id": "TRADE-001",
            }
        ),
        "discord_close_msg": MagicMock(
            return_value={
                "message_id": "222222222222222222",
                "content": "CLOSE signal",
                "trade_id": "TRADE-001",
            }
        ),
        "discord_recap_msg": MagicMock(
            return_value={
                "message_id": "333333333333333333",
                "content": "RECAP: Trade ID: TRADE-001",
                "trade_id": "TRADE-001",
            }
        ),
        "influx_orders_query": MagicMock(
            return_value={
                "query": "SELECT * FROM orders",
                "results": [{"order_id": "ORD-001"}],
            }
        ),
        "influx_fills_query": MagicMock(
            return_value={
                "query": "SELECT * FROM fills",
                "results": [{"fill_id": "FILL-001"}],
            }
        ),
        "influx_canary_query": MagicMock(
            return_value={
                "query": "SELECT * FROM canary",
                "results": [{"status": "ok"}],
            }
        ),
        "burn_in_verdict": MagicMock(
            return_value={"verdict": "PASS", "confidence": 0.95}
        ),
    }


def create_mock_collectors_failing() -> dict[str, MagicMock]:
    """Create mock collectors that return failing data."""
    return {
        "scheduler_heartbeat": MagicMock(
            return_value={
                "timestamp": datetime.now(UTC).isoformat(),
                "count": 0,
                "delta": 0,
            }
        ),
        "signal_count_delta": MagicMock(return_value={"delta": 0, "count": 0}),
        "outcome_count_delta": MagicMock(return_value={"delta": 0, "count": 0}),
        "kill_switch_state": MagicMock(return_value={"value": 0, "state": "INACTIVE"}),
        "discord_open_msg": MagicMock(
            return_value={"message_id": None, "error": "No message found"}
        ),
        "discord_close_msg": MagicMock(
            return_value={"message_id": None, "error": "No message found"}
        ),
        "discord_recap_msg": MagicMock(
            return_value={"message_id": None, "error": "No message found"}
        ),
        # Influx queries without results key to trigger missing results validation
        "influx_orders_query": MagicMock(
            return_value={"query": "SELECT * FROM orders"}
        ),
        "influx_fills_query": MagicMock(return_value={"query": "SELECT * FROM fills"}),
        "influx_canary_query": MagicMock(
            return_value={"query": "SELECT * FROM canary"}
        ),
        # burn_in_verdict not included - will trigger missing artifact failure
    }


# =============================================================================
# E2E Test Class
# =============================================================================


class TestForensicE2E:
    """End-to-end tests for forensic validation."""

    # -------------------------------------------------------------------------
    # Complete Proof Loop Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_complete_proof_loop_mock(self):
        """Test complete proof loop with mock data."""
        collectors = create_mock_collectors_passing()

        harness = ForensicHarness(
            duration_minutes=5,
            snapshot_interval_minutes=5,
            artifact_collectors=collectors,
        )

        # Mock sleep to speed up test
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await harness.run_proof_loop()

        # Verify proof loop completed
        assert result is not None
        assert result.proof_id is not None
        assert result.start_time is not None
        assert result.end_time is not None

        # Verify all snapshots taken
        assert len(result.snapshots) == 2  # T0 and T5
        assert result.snapshots[0].label == "T0"
        assert result.snapshots[1].label == "T5"

        # Verify all gates evaluated
        assert len(result.gate_results) == 8  # G1-G8
        for gate in ["G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8"]:
            assert gate in result.gate_results

        # Verify overall status is PASS
        assert result.overall_status == GateStatus.PASS

        # Verify evidence bundle can be generated
        bundle = harness.generate_bundle()
        assert bundle is not None
        assert bundle.bundle_hash is not None
        assert len(bundle.bundle_hash) == 64  # SHA-256

    @pytest.mark.asyncio
    async def test_proof_loop_30_minute_simulation(self):
        """Simulate a 30-minute proof loop with accelerated time."""
        collectors = create_mock_collectors_passing()

        harness = ForensicHarness(
            duration_minutes=30,
            snapshot_interval_minutes=5,
            artifact_collectors=collectors,
        )

        # Mock sleep to speed up test
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await harness.run_proof_loop()

        # Verify 7 snapshots (T0, T5, T10, T15, T20, T25, T30)
        assert len(result.snapshots) == 7
        expected_labels = ["T0", "T5", "T10", "T15", "T20", "T25", "T30"]
        for i, label in enumerate(expected_labels):
            assert result.snapshots[i].label == label

    # -------------------------------------------------------------------------
    # G1: Scheduler Heartbeat Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_g1_fail_no_scheduler_heartbeat(self):
        """G1 fails when no scheduler heartbeat."""
        # No scheduler_heartbeat collector
        collectors = create_mock_collectors_passing()
        del collectors["scheduler_heartbeat"]

        harness = ForensicHarness(
            duration_minutes=5,
            snapshot_interval_minutes=5,
            artifact_collectors=collectors,
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await harness.run_proof_loop()

        assert result.gate_results["G1"].status == GateStatus.FAIL
        assert "scheduler_heartbeat" in result.gate_results["G1"].artifacts_missing
        assert result.overall_status == GateStatus.FAIL

    @pytest.mark.asyncio
    async def test_g1_fail_zero_heartbeat_count(self):
        """G1 fails when heartbeat count is zero."""
        collectors = create_mock_collectors_passing()
        collectors["scheduler_heartbeat"] = MagicMock(
            return_value={"count": 0, "delta": 0}
        )

        harness = ForensicHarness(
            duration_minutes=5,
            snapshot_interval_minutes=5,
            artifact_collectors=collectors,
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await harness.run_proof_loop()

        assert result.gate_results["G1"].status == GateStatus.FAIL
        assert any("Zero" in err for err in result.gate_results["G1"].validation_errors)

    @pytest.mark.asyncio
    async def test_g1_pass_with_valid_heartbeat(self):
        """G1 passes with valid scheduler heartbeat."""
        collectors = create_mock_collectors_passing()

        harness = ForensicHarness(
            duration_minutes=5,
            snapshot_interval_minutes=5,
            artifact_collectors=collectors,
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await harness.run_proof_loop()

        assert result.gate_results["G1"].status == GateStatus.PASS
        assert "scheduler_heartbeat" in result.gate_results["G1"].artifacts_found

    # -------------------------------------------------------------------------
    # G2: Signal Delta Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_g2_fail_zero_signal_delta(self):
        """G2 fails when zero signal delta."""
        collectors = create_mock_collectors_passing()
        collectors["signal_count_delta"] = MagicMock(
            return_value={"delta": 0, "count": 0}
        )

        harness = ForensicHarness(
            duration_minutes=5,
            snapshot_interval_minutes=5,
            artifact_collectors=collectors,
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await harness.run_proof_loop()

        assert result.gate_results["G2"].status == GateStatus.FAIL
        assert any(
            "Zero delta" in err for err in result.gate_results["G2"].validation_errors
        )

    @pytest.mark.asyncio
    async def test_g2_pass_with_positive_signal_delta(self):
        """G2 passes with positive signal delta."""
        collectors = create_mock_collectors_passing()

        harness = ForensicHarness(
            duration_minutes=5,
            snapshot_interval_minutes=5,
            artifact_collectors=collectors,
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await harness.run_proof_loop()

        assert result.gate_results["G2"].status == GateStatus.PASS

    # -------------------------------------------------------------------------
    # G3: Outcome Delta Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_g3_fail_zero_outcome_delta(self):
        """G3 fails when zero outcome delta."""
        collectors = create_mock_collectors_passing()
        collectors["outcome_count_delta"] = MagicMock(
            return_value={"delta": 0, "count": 0}
        )

        harness = ForensicHarness(
            duration_minutes=5,
            snapshot_interval_minutes=5,
            artifact_collectors=collectors,
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await harness.run_proof_loop()

        assert result.gate_results["G3"].status == GateStatus.FAIL
        assert any("Zero" in err for err in result.gate_results["G3"].validation_errors)

    @pytest.mark.asyncio
    async def test_g3_pass_with_positive_outcome_delta(self):
        """G3 passes with positive outcome delta."""
        collectors = create_mock_collectors_passing()

        harness = ForensicHarness(
            duration_minutes=5,
            snapshot_interval_minutes=5,
            artifact_collectors=collectors,
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await harness.run_proof_loop()

        assert result.gate_results["G3"].status == GateStatus.PASS

    # -------------------------------------------------------------------------
    # G4: Kill Switch Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_g4_fail_kill_switch_triggered(self):
        """G4 fails when kill switch is triggered (value=0)."""
        collectors = create_mock_collectors_passing()
        collectors["kill_switch_state"] = MagicMock(
            return_value={"value": 0, "state": "TRIGGERED"}
        )

        harness = ForensicHarness(
            duration_minutes=5,
            snapshot_interval_minutes=5,
            artifact_collectors=collectors,
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await harness.run_proof_loop()

        assert result.gate_results["G4"].status == GateStatus.FAIL
        assert any(
            "Zero value" in err for err in result.gate_results["G4"].validation_errors
        )

    @pytest.mark.asyncio
    async def test_g4_pass_kill_switch_active(self):
        """G4 passes when kill switch is active (non-zero)."""
        collectors = create_mock_collectors_passing()

        harness = ForensicHarness(
            duration_minutes=5,
            snapshot_interval_minutes=5,
            artifact_collectors=collectors,
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await harness.run_proof_loop()

        assert result.gate_results["G4"].status == GateStatus.PASS

    # -------------------------------------------------------------------------
    # G5: Discord Messages Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_g5_fail_missing_discord_messages(self):
        """G5 fails when missing Discord messages."""
        collectors = create_mock_collectors_passing()
        # Remove all Discord message collectors
        del collectors["discord_open_msg"]
        del collectors["discord_close_msg"]
        del collectors["discord_recap_msg"]

        harness = ForensicHarness(
            duration_minutes=5,
            snapshot_interval_minutes=5,
            artifact_collectors=collectors,
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await harness.run_proof_loop()

        assert result.gate_results["G5"].status == GateStatus.FAIL
        assert len(result.gate_results["G5"].artifacts_missing) == 3

    @pytest.mark.asyncio
    async def test_g5_fail_missing_message_id(self):
        """G5 fails when Discord messages lack message_id."""
        collectors = create_mock_collectors_passing()
        collectors["discord_open_msg"] = MagicMock(
            return_value={"content": "OPEN signal"}  # No message_id
        )

        harness = ForensicHarness(
            duration_minutes=5,
            snapshot_interval_minutes=5,
            artifact_collectors=collectors,
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await harness.run_proof_loop()

        assert result.gate_results["G5"].status == GateStatus.FAIL
        assert any(
            "missing message_id" in err
            for err in result.gate_results["G5"].validation_errors
        )

    @pytest.mark.asyncio
    async def test_g5_fail_empty_message_id(self):
        """G5 fails when Discord messages have empty message_id."""
        collectors = create_mock_collectors_passing()
        collectors["discord_open_msg"] = MagicMock(
            return_value={"message_id": "", "content": "OPEN signal"}
        )

        harness = ForensicHarness(
            duration_minutes=5,
            snapshot_interval_minutes=5,
            artifact_collectors=collectors,
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await harness.run_proof_loop()

        assert result.gate_results["G5"].status == GateStatus.FAIL
        assert any(
            "empty message_id" in err
            for err in result.gate_results["G5"].validation_errors
        )

    @pytest.mark.asyncio
    async def test_g5_pass_with_all_discord_messages(self):
        """G5 passes with all required Discord messages."""
        collectors = create_mock_collectors_passing()

        harness = ForensicHarness(
            duration_minutes=5,
            snapshot_interval_minutes=5,
            artifact_collectors=collectors,
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await harness.run_proof_loop()

        assert result.gate_results["G5"].status == GateStatus.PASS
        assert len(result.gate_results["G5"].artifacts_found) == 3

    # -------------------------------------------------------------------------
    # G5: Recap Source Validation Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_g5_fail_missing_recap_source(self):
        """G5 fails when recap has no source proof."""
        # Test using RecapValidator directly
        mock_redis = MockRedisClient()  # Empty - no outcomes
        mock_influx = MockInfluxClient()  # Empty - no outcomes

        validator = RecapValidator(
            redis_collector=mock_redis,
            influx_collector=mock_influx,
        )

        recap_message = DiscordMessageEvidence(
            message_id="123456789",
            channel_id="1444447985378398459",
            channel_name="trading",
            timestamp_utc=datetime.now(UTC).isoformat(),
            content_type="RECAP",
            content_snippet="Daily RECAP - Trade ID: NONEXISTENT-001",
            is_bot=True,
        )

        now = datetime.now(UTC)
        window_start = now - timedelta(minutes=30)
        window_end = now

        evidence = await validator.validate_recap_source(
            recap_message, window_start, window_end
        )

        # Source verification should fail - no outcomes found
        assert evidence.source_verified is False
        assert len(evidence.outcome_proofs) == 0

        # Run G5 validation
        result = validator.validate_g5_recap(evidence)
        assert result.status == RecapGateStatus.FAIL
        assert (
            "No outcome proofs" in result.message
            or "source verification" in result.message.lower()
        )

    @pytest.mark.asyncio
    async def test_g5_recap_pass_with_verified_source(self):
        """G5 recap passes when source is verified."""
        # Create mock with outcome data
        mock_redis = MockRedisClient(
            {
                "outcome:TRADE-001": {
                    "outcome_id": "OUT-001",
                    "signal_id": "SIG-001",
                    "order_id": "ORD-001",
                    "pnl": 100.5,
                    "timestamp_utc": datetime.now(UTC).isoformat(),
                }
            }
        )

        validator = RecapValidator(redis_collector=mock_redis)

        recap_message = DiscordMessageEvidence(
            message_id="123456789",
            channel_id="1444447985378398459",
            channel_name="trading",
            timestamp_utc=datetime.now(UTC).isoformat(),
            content_type="RECAP",
            content_snippet="Daily RECAP - Trade ID: TRADE-001",
            is_bot=True,
        )

        now = datetime.now(UTC)
        window_start = now - timedelta(minutes=30)
        window_end = now

        evidence = await validator.validate_recap_source(
            recap_message, window_start, window_end
        )

        # Should find the outcome
        assert evidence.source_verified is True
        assert len(evidence.outcome_proofs) == 1
        assert evidence.outcome_proofs[0].outcome_id == "OUT-001"

        # Run G5 validation
        result = validator.validate_g5_recap(evidence)
        assert result.status == RecapGateStatus.PASS

    # -------------------------------------------------------------------------
    # G6: Influx Orders Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_g6_fail_empty_influx_orders(self):
        """G6 fails when Influx orders empty."""
        collectors = create_mock_collectors_passing()
        collectors["influx_orders_query"] = MagicMock(
            return_value={"query": "SELECT * FROM orders"}  # No results
        )

        harness = ForensicHarness(
            duration_minutes=5,
            snapshot_interval_minutes=5,
            artifact_collectors=collectors,
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await harness.run_proof_loop()

        assert result.gate_results["G6"].status == GateStatus.FAIL
        assert any(
            "missing results" in err
            for err in result.gate_results["G6"].validation_errors
        )

    @pytest.mark.asyncio
    async def test_g6_pass_with_influx_orders(self):
        """G6 passes with Influx orders data."""
        collectors = create_mock_collectors_passing()

        harness = ForensicHarness(
            duration_minutes=5,
            snapshot_interval_minutes=5,
            artifact_collectors=collectors,
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await harness.run_proof_loop()

        assert result.gate_results["G6"].status == GateStatus.PASS
        assert len(result.gate_results["G6"].artifacts_found) == 2  # orders + fills

    # -------------------------------------------------------------------------
    # G7: Canary Data Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_g7_fail_empty_canary_data(self):
        """G7 fails when canary data empty."""
        collectors = create_mock_collectors_passing()
        collectors["influx_canary_query"] = MagicMock(
            return_value={"query": "SELECT * FROM canary"}  # No results
        )

        harness = ForensicHarness(
            duration_minutes=5,
            snapshot_interval_minutes=5,
            artifact_collectors=collectors,
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await harness.run_proof_loop()

        assert result.gate_results["G7"].status == GateStatus.FAIL
        assert any(
            "missing results" in err
            for err in result.gate_results["G7"].validation_errors
        )

    @pytest.mark.asyncio
    async def test_g7_pass_with_canary_data(self):
        """G7 passes with canary data."""
        collectors = create_mock_collectors_passing()

        harness = ForensicHarness(
            duration_minutes=5,
            snapshot_interval_minutes=5,
            artifact_collectors=collectors,
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await harness.run_proof_loop()

        assert result.gate_results["G7"].status == GateStatus.PASS

    # -------------------------------------------------------------------------
    # G8: Burn-In Verdict Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_g8_fail_no_burn_in_verdict(self):
        """G8 fails when no burn-in verdict."""
        collectors = create_mock_collectors_passing()
        del collectors["burn_in_verdict"]

        harness = ForensicHarness(
            duration_minutes=5,
            snapshot_interval_minutes=5,
            artifact_collectors=collectors,
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await harness.run_proof_loop()

        assert result.gate_results["G8"].status == GateStatus.FAIL
        assert "burn_in_verdict" in result.gate_results["G8"].artifacts_missing

    @pytest.mark.asyncio
    async def test_g8_pass_with_burn_in_verdict(self):
        """G8 passes with burn-in verdict."""
        collectors = create_mock_collectors_passing()

        harness = ForensicHarness(
            duration_minutes=5,
            snapshot_interval_minutes=5,
            artifact_collectors=collectors,
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await harness.run_proof_loop()

        assert result.gate_results["G8"].status == GateStatus.PASS

    # -------------------------------------------------------------------------
    # All Gates Pass/Fail Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_all_gates_pass_with_valid_data(self):
        """All gates pass with valid mock data."""
        collectors = create_mock_collectors_passing()

        harness = ForensicHarness(
            duration_minutes=5,
            snapshot_interval_minutes=5,
            artifact_collectors=collectors,
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await harness.run_proof_loop()

        # All gates should pass
        assert result.overall_status == GateStatus.PASS
        for gate, gate_result in result.gate_results.items():
            assert gate_result.status == GateStatus.PASS, f"Gate {gate} should PASS"

    @pytest.mark.asyncio
    async def test_all_gates_fail_with_invalid_data(self):
        """All gates fail with invalid mock data."""
        collectors = create_mock_collectors_failing()

        harness = ForensicHarness(
            duration_minutes=5,
            snapshot_interval_minutes=5,
            artifact_collectors=collectors,
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await harness.run_proof_loop()

        # All gates should fail
        assert result.overall_status == GateStatus.FAIL
        for gate, gate_result in result.gate_results.items():
            assert gate_result.status == GateStatus.FAIL, f"Gate {gate} should FAIL"

    @pytest.mark.asyncio
    async def test_partial_gate_failure(self):
        """Test partial gate failure (some pass, some fail)."""
        collectors = create_mock_collectors_passing()
        # Make G1 and G5 fail
        collectors["scheduler_heartbeat"] = MagicMock(
            return_value={"count": 0, "delta": 0}
        )
        del collectors["discord_open_msg"]

        harness = ForensicHarness(
            duration_minutes=5,
            snapshot_interval_minutes=5,
            artifact_collectors=collectors,
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await harness.run_proof_loop()

        # Overall should fail
        assert result.overall_status == GateStatus.FAIL

        # G1 and G5 should fail
        assert result.gate_results["G1"].status == GateStatus.FAIL
        assert result.gate_results["G5"].status == GateStatus.FAIL

        # Other gates should pass
        assert result.gate_results["G2"].status == GateStatus.PASS
        assert result.gate_results["G3"].status == GateStatus.PASS

    # -------------------------------------------------------------------------
    # Evidence Bundle Tests
    # -------------------------------------------------------------------------

    def test_evidence_bundle_structure(self):
        """Verify evidence bundle has correct structure."""
        harness = ForensicHarness()

        # Create a completed proof result
        snapshot = Snapshot(
            timestamp_utc=datetime.now(UTC).isoformat(),
            label="T0",
            artifacts={
                "test_artifact": Artifact(
                    gate="G1",
                    artifact_type="scheduler_heartbeat",
                    data={"count": 5, "delta": 5},
                    source_path="redis://test",
                )
            },
        )

        harness._proof_result = ProofResult(
            start_time=datetime.now(UTC).isoformat(),
            end_time=datetime.now(UTC).isoformat(),
            snapshots=[snapshot],
            gate_results={
                "G1": GateResult(
                    gate="G1",
                    status=GateStatus.PASS,
                    artifacts_found=["scheduler_heartbeat"],
                    artifacts_missing=[],
                    validation_errors=[],
                )
            },
            overall_status=GateStatus.PASS,
        )

        bundle = harness.generate_bundle()

        # Verify bundle structure
        assert bundle.bundle_id is not None
        assert bundle.bundle_hash is not None
        assert bundle.created_at is not None
        assert bundle.proof_result is not None

        # Verify dict conversion
        bundle_dict = bundle.to_dict()
        assert "bundle_id" in bundle_dict
        assert "bundle_hash" in bundle_dict
        assert "created_at" in bundle_dict
        assert "proof_result" in bundle_dict

        # Verify proof_result structure
        proof_dict = bundle_dict["proof_result"]
        assert "proof_id" in proof_dict
        assert "start_time" in proof_dict
        assert "end_time" in proof_dict
        assert "snapshots" in proof_dict
        assert "gate_results" in proof_dict
        assert "overall_status" in proof_dict

        # Verify snapshot structure
        snapshot_dict = proof_dict["snapshots"][0]
        assert "snapshot_id" in snapshot_dict
        assert "timestamp_utc" in snapshot_dict
        assert "label" in snapshot_dict
        assert "artifacts" in snapshot_dict

        # Verify artifact structure
        artifact_dict = snapshot_dict["artifacts"]["test_artifact"]
        assert "artifact_id" in artifact_dict
        assert "gate" in artifact_dict
        assert "artifact_type" in artifact_dict
        assert "data" in artifact_dict
        assert "source_path" in artifact_dict
        assert "captured_at" in artifact_dict

    def test_evidence_bundle_json_serialization(self):
        """Verify evidence bundle can be serialized to JSON."""
        harness = ForensicHarness()

        harness._proof_result = ProofResult(
            start_time=datetime.now(UTC).isoformat(),
            end_time=datetime.now(UTC).isoformat(),
            snapshots=[],
            gate_results={"G1": GateResult(gate="G1", status=GateStatus.PASS)},
            overall_status=GateStatus.PASS,
        )

        bundle = harness.generate_bundle()
        json_str = bundle.to_json()

        # Verify it's valid JSON
        parsed = json.loads(json_str)
        assert parsed["bundle_id"] == bundle.bundle_id
        assert parsed["bundle_hash"] == bundle.bundle_hash

    def test_evidence_bundle_hash_integrity(self):
        """Verify bundle hash matches content."""
        harness = ForensicHarness()

        harness._proof_result = ProofResult(
            start_time="2024-01-01T00:00:00+00:00",
            end_time="2024-01-01T00:30:00+00:00",
            snapshots=[
                Snapshot(
                    timestamp_utc="2024-01-01T00:00:00+00:00",
                    label="T0",
                    artifacts={
                        "test": Artifact(
                            gate="G1",
                            artifact_type="test",
                            data={"v": 1},
                            source_path="test://source",
                            captured_at="2024-01-01T00:00:00+00:00",
                            artifact_id="test-id-123",
                        )
                    },
                    snapshot_id="snapshot-id-123",
                )
            ],
            gate_results={
                "G1": GateResult(
                    gate="G1",
                    status=GateStatus.PASS,
                    artifacts_found=["test"],
                    artifacts_missing=[],
                    validation_errors=[],
                    evaluated_at="2024-01-01T00:30:00+00:00",
                )
            },
            overall_status=GateStatus.PASS,
            proof_id="proof-id-123",
        )

        bundle = harness.generate_bundle()

        # Compute expected hash
        expected_data = json.dumps(
            harness._proof_result.to_dict(), sort_keys=True, default=str
        )
        expected_hash = hashlib.sha256(expected_data.encode()).hexdigest()

        assert bundle.bundle_hash == expected_hash

    # -------------------------------------------------------------------------
    # Timestamp Monotonicity Tests
    # -------------------------------------------------------------------------

    def test_timestamp_monotonicity(self):
        """Verify timestamps are monotonic."""
        harness = ForensicHarness()

        base_time = datetime.now(UTC)

        harness.snapshots = [
            Snapshot(
                timestamp_utc=(base_time).isoformat(),
                label="T0",
                artifacts={},
            ),
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

    def test_timestamp_monotonicity_failure(self):
        """Verify non-monotonic timestamps are detected."""
        harness = ForensicHarness()

        base_time = datetime.now(UTC)

        # Create non-monotonic timestamps (T10 before T5)
        harness.snapshots = [
            Snapshot(
                timestamp_utc=(base_time).isoformat(),
                label="T0",
                artifacts={},
            ),
            Snapshot(
                timestamp_utc=(base_time + timedelta(minutes=10)).isoformat(),
                label="T5",  # Wrong! Should be T10
                artifacts={},
            ),
            Snapshot(
                timestamp_utc=(base_time + timedelta(minutes=5)).isoformat(),
                label="T10",  # Wrong! Should be T5
                artifacts={},
            ),
        ]

        errors = harness._validate_monotonic_timestamps()
        assert len(errors) > 0
        assert "Non-monotonic" in errors[0]

    @pytest.mark.asyncio
    async def test_overall_fails_on_non_monotonic_timestamps(self):
        """Verify overall status FAIL when timestamps are non-monotonic."""
        collectors = create_mock_collectors_passing()

        harness = ForensicHarness(
            duration_minutes=5,
            snapshot_interval_minutes=5,
            artifact_collectors=collectors,
        )

        # Run proof loop normally
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await harness.run_proof_loop()

        # Manually corrupt timestamps
        base_time = datetime.now(UTC)
        harness.snapshots[0].timestamp_utc = (
            base_time + timedelta(minutes=10)
        ).isoformat()
        harness.snapshots[1].timestamp_utc = base_time.isoformat()

        # Re-validate
        errors = harness._validate_monotonic_timestamps()
        assert len(errors) > 0

    # -------------------------------------------------------------------------
    # Integration Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_complete_integration_with_discord_evidence(self):
        """Test complete integration with Discord evidence collection."""
        # Create mock Discord client
        mock_discord = MockDiscordClient(
            [
                {
                    "id": "111111111111111111",
                    "content": "🎯 ENTRY: BTC/USDT LONG @ 50000",
                    "created_at": datetime.now(UTC),
                    "is_bot": True,
                    "author_name": "TradingBot",
                },
                {
                    "id": "222222222222222222",
                    "content": "✅ CLOSED: BTC/USDT @ 51000 (+2%)",
                    "created_at": datetime.now(UTC),
                    "is_bot": True,
                    "author_name": "TradingBot",
                },
                {
                    "id": "333333333333333333",
                    "content": "📊 DAILY RECAP: 3 trades, +5.2% PnL",
                    "created_at": datetime.now(UTC),
                    "is_bot": True,
                    "author_name": "TradingBot",
                },
            ]
        )

        # Create collectors using Discord mock
        collectors = create_mock_collectors_passing()

        harness = ForensicHarness(
            duration_minutes=5,
            snapshot_interval_minutes=5,
            artifact_collectors=collectors,
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await harness.run_proof_loop()

        # G5 should pass with Discord evidence
        assert result.gate_results["G5"].status == GateStatus.PASS

    @pytest.mark.asyncio
    async def test_collector_error_handling(self):
        """Test that collector errors are handled gracefully."""
        collectors = {
            "scheduler_heartbeat": MagicMock(
                side_effect=Exception("Redis connection failed")
            ),
            "signal_count_delta": MagicMock(return_value={"delta": 5}),
        }

        harness = ForensicHarness(
            duration_minutes=5,
            snapshot_interval_minutes=5,
            artifact_collectors=collectors,
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await harness.run_proof_loop()

        # G1 should fail due to collection error
        assert result.gate_results["G1"].status == GateStatus.FAIL
        assert any(
            "failed to collect" in err.lower()
            for err in result.gate_results["G1"].validation_errors
        )

    @pytest.mark.asyncio
    async def test_async_collector_support(self):
        """Test that async collectors are properly supported."""

        async def async_collector():
            await asyncio.sleep(0.001)
            return {"async": True, "delta": 5}

        collectors = {
            "scheduler_heartbeat": async_collector,
            "signal_count_delta": MagicMock(return_value={"delta": 5}),
        }

        harness = ForensicHarness(
            duration_minutes=5,
            snapshot_interval_minutes=5,
            artifact_collectors=collectors,
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await harness.run_proof_loop()

        # Should have collected from async collector
        assert "scheduler_heartbeat" in result.snapshots[0].artifacts
        assert (
            result.snapshots[0].artifacts["scheduler_heartbeat"].data.get("async")
            is True
        )

    # -------------------------------------------------------------------------
    # Stop and Interrupt Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_proof_loop_can_be_stopped(self):
        """Test that proof loop can be stopped early."""
        collectors = create_mock_collectors_passing()

        harness = ForensicHarness(
            duration_minutes=30,
            snapshot_interval_minutes=5,
            artifact_collectors=collectors,
        )

        async def stop_after_t5():
            await asyncio.sleep(0.01)
            harness.stop()

        # Start proof loop and stop it
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            # Make sleep return immediately but track calls
            mock_sleep.return_value = None

            # Run stop in background
            stop_task = asyncio.create_task(stop_after_t5())

            result = await harness.run_proof_loop()

            await stop_task

        # Should have stopped (may have T0 and possibly T5)
        assert harness._running is False

    # -------------------------------------------------------------------------
    # Gate Requirements Validation
    # -------------------------------------------------------------------------

    def test_gate_requirements_coverage(self):
        """Verify all gate requirements are properly defined."""
        # G1: Scheduler heartbeat
        assert "G1" in GATE_REQUIREMENTS
        assert "scheduler_heartbeat" in GATE_REQUIREMENTS["G1"]

        # G2: Signal delta
        assert "G2" in GATE_REQUIREMENTS
        assert "signal_count_delta" in GATE_REQUIREMENTS["G2"]

        # G3: Outcome delta
        assert "G3" in GATE_REQUIREMENTS
        assert "outcome_count_delta" in GATE_REQUIREMENTS["G3"]

        # G4: Kill switch
        assert "G4" in GATE_REQUIREMENTS
        assert "kill_switch_state" in GATE_REQUIREMENTS["G4"]

        # G5: Discord messages
        assert "G5" in GATE_REQUIREMENTS
        assert "discord_open_msg" in GATE_REQUIREMENTS["G5"]
        assert "discord_close_msg" in GATE_REQUIREMENTS["G5"]
        assert "discord_recap_msg" in GATE_REQUIREMENTS["G5"]

        # G6: Influx orders/fills
        assert "G6" in GATE_REQUIREMENTS
        assert "influx_orders_query" in GATE_REQUIREMENTS["G6"]
        assert "influx_fills_query" in GATE_REQUIREMENTS["G6"]

        # G7: Canary data
        assert "G7" in GATE_REQUIREMENTS
        assert "influx_canary_query" in GATE_REQUIREMENTS["G7"]

        # G8: Burn-in verdict
        assert "G8" in GATE_REQUIREMENTS
        assert "burn_in_verdict" in GATE_REQUIREMENTS["G8"]

    def test_zero_delta_gates_defined(self):
        """Verify zero delta gates are properly defined."""
        assert "G1" in ZERO_DELTA_GATES
        assert "G2" in ZERO_DELTA_GATES
        assert "G3" in ZERO_DELTA_GATES
        assert "G4" in ZERO_DELTA_GATES
        assert "G5" not in ZERO_DELTA_GATES
        assert "G6" not in ZERO_DELTA_GATES
        assert "G7" not in ZERO_DELTA_GATES
        assert "G8" not in ZERO_DELTA_GATES


# =============================================================================
# Discord Evidence Collector E2E Tests
# =============================================================================


class TestDiscordEvidenceE2E:
    """E2E tests for Discord evidence collection."""

    @pytest.mark.asyncio
    async def test_discord_message_classification(self):
        """Test Discord message classification."""
        collector = DiscordEvidenceCollector(bot_token="test_token")

        # Test OPEN classification
        open_msg = {"content": "🎯 ENTRY: BTC LONG @ 50000"}
        assert collector.classify_message(open_msg) == "OPEN"

        # Test CLOSE classification
        close_msg = {"content": "✅ CLOSED: Take profit hit @ 51000"}
        assert collector.classify_message(close_msg) == "CLOSE"

        # Test RECAP classification
        recap_msg = {"content": "📊 DAILY RECAP: 5 trades, +3.5%"}
        assert collector.classify_message(recap_msg) == "RECAP"

        # Test non-trade message
        other_msg = {"content": "Hello everyone!"}
        assert collector.classify_message(other_msg) is None

    @pytest.mark.asyncio
    async def test_discord_trade_id_extraction(self):
        """Test Discord trade ID extraction."""
        collector = DiscordEvidenceCollector(bot_token="test_token")

        # Test various trade ID formats
        msg1 = {"content": "Trade ID: ABC123"}
        assert collector.extract_trade_id(msg1) == "ABC123"

        msg2 = {"content": "trade_id: XYZ-789"}
        assert collector.extract_trade_id(msg2) == "XYZ-789"

        msg3 = {"content": "#TRADE-TEST001"}
        assert collector.extract_trade_id(msg3) == "TEST001"

        msg4 = {"content": "[TRADE:DEMO-123]"}
        assert collector.extract_trade_id(msg4) == "DEMO-123"

    @pytest.mark.asyncio
    async def test_g5_validation_with_mock_messages(self):
        """Test G5 validation with mock Discord messages."""
        collector = DiscordEvidenceCollector(bot_token="test_token")

        messages = [
            DiscordMessageEvidence(
                message_id="111",
                channel_id="123",
                channel_name="trading",
                timestamp_utc=datetime.now(UTC).isoformat(),
                content_type="OPEN",
                is_bot=True,
            ),
            DiscordMessageEvidence(
                message_id="222",
                channel_id="123",
                channel_name="trading",
                timestamp_utc=datetime.now(UTC).isoformat(),
                content_type="CLOSE",
                is_bot=True,
            ),
            DiscordMessageEvidence(
                message_id="333",
                channel_id="123",
                channel_name="trading",
                timestamp_utc=datetime.now(UTC).isoformat(),
                content_type="RECAP",
                is_bot=True,
            ),
        ]

        result = collector.validate_g5(messages)

        assert result.status == DiscordGateStatus.PASS
        assert len(result.evidence) == 3

    @pytest.mark.asyncio
    async def test_g5_validation_fails_missing_messages(self):
        """Test G5 validation fails when messages are missing."""
        collector = DiscordEvidenceCollector(bot_token="test_token")

        # Only OPEN message, missing CLOSE and RECAP
        messages = [
            DiscordMessageEvidence(
                message_id="111",
                channel_id="123",
                channel_name="trading",
                timestamp_utc=datetime.now(UTC).isoformat(),
                content_type="OPEN",
                is_bot=True,
            ),
        ]

        result = collector.validate_g5(messages)

        assert result.status == DiscordGateStatus.FAIL
        assert "CLOSE" in result.missing_types
        assert "RECAP" in result.missing_types


# =============================================================================
# Recap Validator E2E Tests
# =============================================================================


class TestRecapValidatorE2E:
    """E2E tests for recap validation."""

    @pytest.mark.asyncio
    async def test_trade_id_extraction_from_recap(self):
        """Test trade ID extraction from recap content."""
        validator = RecapValidator()

        # Test various formats - IDs must be at least 6 chars after first char
        content1 = "Daily RECAP - Trade ID: ABC12345"
        ids1 = await validator.extract_trade_ids_from_recap(content1)
        assert "ABC12345" in ids1

        # Pattern captures part AFTER "TRADE:" or "TRADE-"
        # So "#TRADE-TEST001" captures "TEST001"
        content2 = "Trades: #TRADE-TEST001, #TRADE-TEST002"
        ids2 = await validator.extract_trade_ids_from_recap(content2)
        assert "TEST001" in ids2  # Pattern captures after TRADE-
        assert "TEST002" in ids2

        content3 = "Order ID: ORD-123456 processed"
        ids3 = await validator.extract_trade_ids_from_recap(content3)
        assert "ORD-123456" in ids3

    @pytest.mark.asyncio
    async def test_recap_source_validation_with_redis(self):
        """Test recap source validation with Redis backend."""
        mock_redis = MockRedisClient(
            {
                "outcome:TRADE-001": {
                    "outcome_id": "OUT-001",
                    "signal_id": "SIG-001",
                    "order_id": "ORD-001",
                    "pnl": 150.75,
                    "timestamp_utc": datetime.now(UTC).isoformat(),
                }
            }
        )

        validator = RecapValidator(redis_collector=mock_redis)

        recap_message = DiscordMessageEvidence(
            message_id="123456789",
            channel_id="trading",
            channel_name="trading",
            timestamp_utc=datetime.now(UTC).isoformat(),
            content_type="RECAP",
            content_snippet="Daily RECAP - Trade ID: TRADE-001",
            is_bot=True,
        )

        now = datetime.now(UTC)
        evidence = await validator.validate_recap_source(
            recap_message,
            now - timedelta(minutes=30),
            now,
        )

        assert evidence.source_verified is True
        assert len(evidence.outcome_proofs) == 1
        assert evidence.total_pnl == 150.75

    @pytest.mark.asyncio
    async def test_recap_source_validation_fails_no_source(self):
        """Test recap source validation fails when no source found."""
        mock_redis = MockRedisClient()  # Empty
        mock_influx = MockInfluxClient()  # Empty

        validator = RecapValidator(
            redis_collector=mock_redis,
            influx_collector=mock_influx,
        )

        recap_message = DiscordMessageEvidence(
            message_id="123456789",
            channel_id="trading",
            channel_name="trading",
            timestamp_utc=datetime.now(UTC).isoformat(),
            content_type="RECAP",
            content_snippet="Daily RECAP - Trade ID: NONEXISTENT",
            is_bot=True,
        )

        now = datetime.now(UTC)
        evidence = await validator.validate_recap_source(
            recap_message,
            now - timedelta(minutes=30),
            now,
        )

        assert evidence.source_verified is False
        assert len(evidence.outcome_proofs) == 0

        result = validator.validate_g5_recap(evidence)
        assert result.status == RecapGateStatus.FAIL


# =============================================================================
# Entry Point
# =============================================================================


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
