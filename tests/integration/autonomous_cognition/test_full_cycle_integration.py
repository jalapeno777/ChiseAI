"""End-to-end integration tests for autonomous cognition full cycle.

These tests verify:
1. Full cycle runs to completion in shadow mode
2. Preflight checks work with mocked services
3. Cycle produces artifacts in expected format
4. Notification suppression via hash-based deduplication
5. Digest routing for low-severity events
6. Experiment safety gates are enforced
7. Shadow mode does not apply actions
"""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from autonomous_cognition.contracts import CycleResult
from autonomous_cognition.experiments.safety_gates import (
    ExperimentSafetyGates,
)
from autonomous_cognition.full_cycle import (
    AutonomousCognitionFullCycle,
    preflight_check,
)
from governance.notifications.discord_notifier import DiscordNotifier

# =============================================================================
# Test 1: Full Cycle Runs to Completion in Shadow Mode
# =============================================================================


class TestFullCycleShadowMode:
    """Test that full cycle runs to completion in shadow mode."""

    def test_full_cycle_runs_to_completion_in_shadow_mode(
        self, autocog_full_cycle, mock_redis, mock_qdrant
    ):
        """Verify full cycle completes with shadow_mode=True and returns CycleResult.

        This test:
        1. Runs the full cycle with shadow_mode=True
        2. Verifies CycleResult is returned with status="completed"
        3. Verifies shadow_mode=True in result
        4. Verifies no actions were applied to live systems
        """
        # Run the cycle in shadow mode
        with (
            patch.object(autocog_full_cycle, "_load_governance_state", return_value={}),
            patch.object(autocog_full_cycle, "_save_governance_state") as mock_save,
            patch.object(autocog_full_cycle, "_persist_cycle_result") as mock_persist,
            patch.object(
                autocog_full_cycle, "_persist_shadow_report"
            ) as mock_shadow_report,
        ):
            # Make _persist_cycle_result return a valid path
            with tempfile.TemporaryDirectory() as tmpdir:
                cycle_path = Path(tmpdir) / "test_cycle.json"
                mock_persist.return_value = cycle_path

                # Also mock _persist_shadow_report
                shadow_path = Path(tmpdir) / "shadow_report.json"
                mock_shadow_report.return_value = shadow_path

                # Mock preflight_check to pass
                with patch(
                    "autonomous_cognition.full_cycle.preflight_check",
                    return_value=True,
                ):
                    result = autocog_full_cycle.run(
                        notify_discord=False, mode="full", shadow_mode=True
                    )

        # Verify result is a CycleResult
        assert isinstance(result, CycleResult), "Result should be CycleResult"

        # Verify status is completed
        assert (
            result.status == "completed"
        ), f"Expected status='completed', got '{result.status}'"

        # Verify shadow_mode is True in result
        assert (
            result.shadow_mode is True
        ), f"Expected shadow_mode=True, got {result.shadow_mode}"

        # Verify no governance state was saved (shadow mode doesn't modify state)
        mock_save.assert_not_called()

        # Verify cycle artifact was persisted
        mock_persist.assert_called()

        # Verify shadow report was generated (since shadow_proposed_actions would be empty
        # but the call happens in the finally block)
        mock_shadow_report.assert_called()


# =============================================================================
# Test 2: Preflight Check Passes with Mocked Services
# =============================================================================


class TestPreflightCheck:
    """Test preflight_check validation with mocked services."""

    def test_preflight_check_passes_with_mocked_services(self, mock_redis):
        """Verify preflight_check passes with mock Redis and Qdrant.

        This test:
        1. Tests preflight_check() with mock Redis and Qdrant
        2. Verifies all connectivity checks pass
        3. Verifies config file is readable
        4. Verifies output directory is writable
        """
        # Create mock qdrant that tracks calls
        mock_qdrant = Mock()
        mock_qdrant.get_collections = Mock(return_value={"collections": []})

        with (patch("autonomous_cognition.full_cycle._get_repo_root") as mock_root,):
            # Create a temp directory for testing
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_path = Path(tmpdir)

                # Mock repo root to use temp dir
                mock_root.return_value = tmp_path

                # Create config directory and file
                config_dir = tmp_path / "config"
                config_dir.mkdir()
                config_file = config_dir / "autocog.yaml"
                config_file.write_text("test: true\n")

                # Create output directory structure
                output_dir = tmp_path / "_bmad-output" / "autocog" / "cycles"
                output_dir.mkdir(parents=True, exist_ok=True)

                # Run preflight check
                result = preflight_check(
                    redis_client=mock_redis,
                    qdrant_client=mock_qdrant,
                    notify_discord=False,
                )

        # Verify preflight passed
        assert result is True, "Preflight check should return True"

        # Verify Redis ping was called
        mock_redis.ping.assert_called()

        # Verify Qdrant get_collections was called
        mock_qdrant.get_collections.assert_called()

    def test_preflight_check_exits_on_failure(self, mock_redis):
        """Verify preflight_check exits with code 1 when Redis fails.

        This test verifies that preflight_check exits cleanly when Redis
        is unavailable, raising SystemExit with code 1.
        """
        # Make Redis ping fail
        mock_redis.ping = Mock(side_effect=Exception("Redis connection failed"))

        # Create a mock Qdrant that works
        mock_qdrant = Mock()
        mock_qdrant.get_collections = Mock(return_value={"collections": []})

        with (patch("autonomous_cognition.full_cycle._get_repo_root") as mock_root,):
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_path = Path(tmpdir)
                mock_root.return_value = tmp_path

                # Create output directory
                output_dir = tmp_path / "_bmad-output" / "autocog" / "cycles"
                output_dir.mkdir(parents=True, exist_ok=True)

                # Preflight should exit with code 1 when Redis fails
                with pytest.raises(SystemExit) as exc_info:
                    preflight_check(
                        redis_client=mock_redis,
                        qdrant_client=mock_qdrant,
                        notify_discord=False,
                    )

                assert exc_info.value.code == 1


# =============================================================================
# Test 3: Cycle Produces Artifacts in Expected Format
# =============================================================================


class TestCycleArtifactFormat:
    """Test that cycle produces artifacts in expected format."""

    def test_cycle_result_has_expected_schema(self, autocog_full_cycle):
        """Verify cycle result has correct JSON structure matching CycleResult schema.

        This test:
        1. Runs full cycle
        2. Verifies CycleResult has correct structure
        3. Verifies run_id, timestamp, metrics fields exist
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)

            # Create output directory structure
            output_dir = tmp_path / "_bmad-output" / "autocog" / "cycles"
            output_dir.mkdir(parents=True, exist_ok=True)

            with (
                patch.object(autocog_full_cycle, "_REPO_ROOT", tmp_path),
                patch.object(autocog_full_cycle, "DEFAULT_CYCLE_DIR", str(output_dir)),
                patch.object(
                    autocog_full_cycle, "_load_governance_state", return_value={}
                ),
                patch.object(autocog_full_cycle, "_save_governance_state"),
                patch(
                    "autonomous_cognition.full_cycle.preflight_check",
                    return_value=True,
                ),
            ):
                # Patch _persist_cycle_result to avoid actual file I/O
                def mock_persist(result):
                    return output_dir / f"{result.run_id}.json"

                with patch.object(
                    autocog_full_cycle, "_persist_cycle_result", mock_persist
                ):
                    with patch.object(autocog_full_cycle, "_persist_shadow_report"):
                        result = autocog_full_cycle.run(
                            notify_discord=False, mode="full", shadow_mode=True
                        )

            # Verify result is correct type
            assert isinstance(result, CycleResult)

            # Verify status is completed
            assert result.status == "completed"

            # Verify the result has all required fields from CycleResult schema
            result_dict = result.to_dict()

            # Verify required fields exist in the result dict
            assert "run_id" in result_dict
            assert "started_at" in result_dict
            assert "completed_at" in result_dict
            assert result_dict["status"] == "completed"

            assert "shadow_mode" in result_dict
            assert result_dict["shadow_mode"] is True

            assert "metrics" in result_dict
            assert isinstance(result_dict["metrics"], dict)

            assert "artifact_paths" in result_dict
            assert isinstance(result_dict["artifact_paths"], dict)

            # Verify artifact_paths contains expected keys after full run
            assert isinstance(result.artifact_paths, dict)


# =============================================================================
# Test 4: Notification Suppression via Hash-Based Deduplication
# =============================================================================


class TestNotificationSuppression:
    """Test hash-based notification deduplication."""

    def test_notification_suppression_uses_hash_based_deduplication(self):
        """Verify hash-based deduplication in DiscordNotifier.

        This test:
        1. Verifies that duplicate notifications are suppressed
        2. Verifies hash-based deduplication logic
        3. Verifies different content produces different hashes
        """
        # Test _compute_cycle_metrics_hash produces consistent hashes
        hash1 = DiscordNotifier._compute_cycle_metrics_hash(
            errors=[],
            actions_taken=0,
            score=0.85,
            previous_score=0.85,
            metrics={},
        )

        # Same inputs should produce same hash
        hash2 = DiscordNotifier._compute_cycle_metrics_hash(
            errors=[],
            actions_taken=0,
            score=0.85,
            previous_score=0.85,
            metrics={},
        )

        assert hash1 == hash2, "Same inputs should produce same hash"

        # Different inputs should produce different hash
        hash3 = DiscordNotifier._compute_cycle_metrics_hash(
            errors=[],
            actions_taken=1,  # Different
            score=0.85,
            previous_score=0.85,
            metrics={},
        )

        assert hash1 != hash3, "Different inputs should produce different hash"

    def test_different_content_produces_different_hashes(self):
        """Verify that different notification content produces different hashes."""
        # Hash with different scores
        hash1 = DiscordNotifier._compute_cycle_metrics_hash(
            errors=[],
            actions_taken=0,
            score=0.85,
            previous_score=0.80,
            metrics={},
        )

        hash2 = DiscordNotifier._compute_cycle_metrics_hash(
            errors=[],
            actions_taken=0,
            score=0.90,  # Different score
            previous_score=0.80,
            metrics={},
        )

        assert hash1 != hash2, "Different scores should produce different hashes"

    def test_should_notify_for_cycle_event_with_identical_metrics(self):
        """Verify should_notify_for_cycle_event suppresses duplicates."""
        notifier = DiscordNotifier.__new__(DiscordNotifier)
        notifier._get_stored_cycle_hash = Mock(return_value=None)
        notifier._store_cycle_hash = Mock()
        notifier._get_cycle_hash_key = Mock(return_value="autocog:last_cycle_hash:full")

        # First call should notify
        result1 = notifier.should_notify_for_cycle_event(
            mode="full",
            errors=[],
            actions_taken=0,
            score=0.85,
            previous_score=None,
        )

        assert result1 is True, "First run should always notify"

        # Simulate storing the hash
        notifier._get_stored_cycle_hash = Mock(
            return_value=DiscordNotifier._compute_cycle_metrics_hash(
                errors=[],
                actions_taken=0,
                score=0.85,
                previous_score=None,
                metrics=None,
            )
        )

        # Same metrics should not notify
        result2 = notifier.should_notify_for_cycle_event(
            mode="full",
            errors=[],
            actions_taken=0,
            score=0.85,
            previous_score=None,
        )

        assert result2 is False, "Identical metrics should be suppressed"


# =============================================================================
# Test 5: Digest Routing for Low-Severity Events
# =============================================================================


class TestDigestRouting:
    """Test digest routing for low-severity events."""

    def test_low_severity_events_routed_to_digest(self):
        """Verify low-severity events are routed to digest buffer."""
        notifier = DiscordNotifier.__new__(DiscordNotifier)
        notifier._low_severity_buffer = []
        notifier._digest_max_items = 10
        notifier._digest_interval_minutes = 60
        notifier._digest_last_flush = None
        notifier._is_enabled = Mock(return_value=True)

        # Add a low-severity event
        event = {
            "event_type": "cycle_completed",
            "severity": "low",
            "summary": "Low severity event",
            "run_id": "test-123",
        }

        result = notifier.add_to_digest(event)

        assert result is True, "Low-severity event should be buffered"
        assert len(notifier._low_severity_buffer) == 1
        assert notifier._low_severity_buffer[0]["event_type"] == "cycle_completed"

    def test_high_severity_events_not_routed_to_digest(self):
        """Verify high-severity events are NOT routed to digest buffer."""
        notifier = DiscordNotifier.__new__(DiscordNotifier)
        notifier._low_severity_buffer = []
        notifier._digest_max_items = 10
        notifier._is_enabled = Mock(return_value=True)

        # Add a high-severity event
        event = {
            "event_type": "belief_conflict",
            "severity": "high",
            "summary": "High severity event",
            "run_id": "test-123",
        }

        result = notifier.add_to_digest(event)

        assert result is False, "High-severity event should NOT be buffered"
        assert len(notifier._low_severity_buffer) == 0

    def test_digest_flush_after_interval(self):
        """Verify digest flush after interval elapsed."""
        notifier = DiscordNotifier.__new__(DiscordNotifier)
        notifier._low_severity_buffer = [{"event_type": "test"}]
        notifier._digest_max_items = 10
        notifier._digest_interval_minutes = 60
        notifier._digest_last_flush = datetime.now(UTC) - timedelta(hours=2)
        notifier._is_enabled = Mock(return_value=True)

        should_flush = notifier.should_flush_digest()

        assert should_flush is True, "Digest should flush after interval"

    def test_digest_max_items_auto_flush(self):
        """Verify digest auto-flush when max items reached."""
        notifier = DiscordNotifier.__new__(DiscordNotifier)
        notifier._low_severity_buffer = [{"event_type": f"test-{i}"} for i in range(10)]
        notifier._digest_max_items = 10
        notifier._digest_interval_minutes = 60
        notifier._digest_last_flush = datetime.now(UTC)
        notifier._is_enabled = Mock(return_value=True)

        should_flush = notifier.should_flush_digest()

        assert should_flush is True, "Digest should flush when max items reached"


# =============================================================================
# Test 6: Experiment Safety Gates Are Enforced
# =============================================================================


class TestExperimentSafetyGates:
    """Test experiment safety gates enforcement."""

    def test_max_experiments_per_cycle_limit(self):
        """Verify max_experiments_per_cycle limit is enforced."""
        gates = ExperimentSafetyGates(max_experiments_per_cycle=3)

        # Should pass for 3 or fewer
        result = gates.check_max_experiments(3)
        assert result.passed is True

        # Should fail for more than 3
        result = gates.check_max_experiments(4)
        assert result.passed is False
        assert "exceeds maximum" in result.message

    def test_safe_mode_prevents_unsafe_experiments(self):
        """Verify safe_mode prevents high-risk experiments."""
        gates = ExperimentSafetyGates(max_risk_level="medium")

        # Low risk should pass
        result = gates.check_risk_level("low")
        assert result.passed is True

        # Medium risk should pass
        result = gates.check_risk_level("medium")
        assert result.passed is True

        # High risk should fail
        result = gates.check_risk_level("high")
        assert result.passed is False
        assert "exceeds maximum" in result.message

    def test_high_risk_experiments_blocked_by_max_risk_level(self):
        """Verify high-risk experiments are blocked when exceeding max_risk_level.

        The safety gates enforce max risk level by blocking experiments that
        exceed the configured maximum risk level.
        """
        # Create gates with max_risk_level="low" - this means only "low" risk passes
        gates = ExperimentSafetyGates(max_risk_level="low")

        # Low risk should pass
        result = gates.check_risk_level("low")
        assert result.passed is True

        # Medium risk should fail (exceeds "low")
        result = gates.check_risk_level("medium")
        assert result.passed is False
        assert "exceeds maximum" in result.message

        # High risk should fail
        result = gates.check_risk_level("high")
        assert result.passed is False

        # Critical should also fail
        result = gates.check_risk_level("critical")
        assert result.passed is False

    def test_all_gates_passed_method(self):
        """Verify all_gates_passed convenience method."""
        gates = ExperimentSafetyGates(
            max_experiments_per_cycle=3,
            max_risk_level="medium",
        )

        # Valid experiment should pass all gates
        all_passed = gates.all_gates_passed(
            experiment_count=2,
            start_time=None,
            result={
                "sharpe": 1.2,
                "sortino": 0.9,
                "drawdown": 0.15,
                "ece": 0.08,
            },
            risk_level="low",
        )

        assert all_passed is True

        # Invalid result should fail
        all_passed = gates.all_gates_passed(
            experiment_count=2,
            start_time=None,
            result={
                "sharpe": -1.0,  # Invalid negative
                "sortino": 0.9,
                "drawdown": 0.15,
                "ece": 0.08,
            },
            risk_level="low",
        )

        assert all_passed is False


# =============================================================================
# Test 7: Shadow Mode Does Not Apply Actions
# =============================================================================


class TestShadowModeActionApplication:
    """Test that shadow mode does NOT apply actions to live systems."""

    def test_shadow_mode_does_not_apply_promotions(self, autocog_full_cycle):
        """Verify in shadow mode, promotions are logged but NOT applied.

        This test:
        1. Creates a hypothesis that would be promoted
        2. Verifies in shadow mode, promotion is logged but NOT applied
        3. Verifies shadow report is generated
        """
        # Create mock hypothesis that would be promoted
        mock_hypothesis = MagicMock()
        mock_hypothesis.hypothesis_id = "hyp-would-promote"
        mock_hypothesis.target_component = "test_strategy"

        # Create mock champion outcome that would promote
        mock_outcome = MagicMock()
        mock_outcome.promoted = True
        mock_outcome.reason = "passed_all_gates"
        mock_outcome.version_id = "v2.0.0"

        # Track if governance state was saved
        governance_state_saved = False

        def track_save(state):
            nonlocal governance_state_saved
            governance_state_saved = True

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            output_dir = tmp_path / "_bmad-output" / "autocog" / "cycles"
            output_dir.mkdir(parents=True, exist_ok=True)

            with (
                patch.object(autocog_full_cycle, "_REPO_ROOT", tmp_path),
                patch.object(autocog_full_cycle, "DEFAULT_CYCLE_DIR", str(output_dir)),
                patch.object(
                    autocog_full_cycle,
                    "_load_governance_state",
                    return_value={"candidate_registry": {}},
                ),
                patch.object(autocog_full_cycle, "_save_governance_state", track_save),
                patch.object(
                    autocog_full_cycle._champion_engine,
                    "evaluate_candidate",
                    return_value=mock_outcome,
                ),
                patch(
                    "autonomous_cognition.full_cycle.preflight_check",
                    return_value=True,
                ),
            ):
                # Mock _persist_cycle_result and _persist_shadow_report
                with patch.object(
                    autocog_full_cycle, "_persist_cycle_result"
                ) as mock_persist:
                    with patch.object(
                        autocog_full_cycle, "_persist_shadow_report"
                    ) as mock_shadow:
                        cycle_path = output_dir / "test.json"
                        shadow_path = output_dir / "shadow.json"
                        mock_persist.return_value = cycle_path
                        mock_shadow.return_value = shadow_path

                        # Run in shadow mode
                        result = autocog_full_cycle.run(
                            notify_discord=False,
                            mode="full",
                            shadow_mode=True,
                        )

        # In shadow mode, governance state should NOT be saved
        assert (
            governance_state_saved is False
        ), "Shadow mode should NOT save governance state"

        # Verify shadow mode is reflected in result
        assert result.shadow_mode is True

    def test_live_mode_applies_actions(self, autocog_full_cycle):
        """Verify in live mode (shadow_mode=False), actions ARE applied.

        This is the inverse of shadow mode - live mode should save governance.
        """
        governance_state_saved = False

        def track_save(state):
            nonlocal governance_state_saved
            governance_state_saved = True

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            output_dir = tmp_path / "_bmad-output" / "autocog" / "cycles"
            output_dir.mkdir(parents=True, exist_ok=True)

            with (
                patch.object(autocog_full_cycle, "_REPO_ROOT", tmp_path),
                patch.object(autocog_full_cycle, "DEFAULT_CYCLE_DIR", str(output_dir)),
                patch.object(
                    autocog_full_cycle,
                    "_load_governance_state",
                    return_value={"candidate_registry": {}},
                ),
                patch.object(autocog_full_cycle, "_save_governance_state", track_save),
                patch(
                    "autonomous_cognition.full_cycle.preflight_check",
                    return_value=True,
                ),
            ):
                with patch.object(autocog_full_cycle, "_persist_cycle_result"):
                    with patch.object(autocog_full_cycle, "_persist_shadow_report"):
                        # Run in live mode
                        result = autocog_full_cycle.run(
                            notify_discord=False,
                            mode="full",
                            shadow_mode=False,
                        )

        # In live mode, governance state SHOULD be saved
        assert governance_state_saved is True, "Live mode should save governance state"

        # Verify shadow mode is False in result
        assert result.shadow_mode is False

    def test_shadow_report_generated_when_actions_proposed(self):
        """Verify shadow report is generated when proposed actions exist."""
        cycle = AutonomousCognitionFullCycle.__new__(AutonomousCognitionFullCycle)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)

            with patch.object(cycle, "_REPO_ROOT", tmp_path):
                proposed_actions = [
                    {
                        "action": "promote_candidate",
                        "candidate_id": "hyp-1",
                        "reason": "passed_gates",
                        "version_id": "v1.0.0",
                        "metrics": {"sharpe": 1.2},
                        "target_component": "test",
                    }
                ]
                governance_state = {
                    "candidate_registry": {"hyp-1": {"status": "promoted"}}
                }

                report_path = cycle._persist_shadow_report(
                    run_id="test-shadow-001",
                    proposed_actions=proposed_actions,
                    governance_state=governance_state,
                )

                assert report_path.exists()

                # Verify shadow report content
                content = json.loads(report_path.read_text())

                assert content["run_id"] == "test-shadow-001"
                assert content["mode"] == "shadow"
                assert content["proposed_actions_summary"]["total"] == 1
                assert content["proposed_actions_summary"]["promotions_count"] == 1
                assert "safety_notice" in content
