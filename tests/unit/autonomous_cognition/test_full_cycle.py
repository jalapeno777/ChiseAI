"""Unit tests for _store_aria_briefing in full_cycle.py."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from autonomous_cognition.contracts import CycleResult
from autonomous_cognition.full_cycle import AutonomousCognitionFullCycle


class TestStoreAriaBriefing:
    """Tests for _store_aria_briefing method."""

    def _make_cycle_result(
        self,
        run_id: str = "autocog-test-001",
        status: str = "completed",
        completed_at: str = "2026-03-29T12:00:00+00:00",
    ) -> CycleResult:
        """Create a CycleResult for testing."""
        result = CycleResult.create(run_id=run_id)
        result.status = status
        result.completed_at = completed_at
        result.self_assessment_status = "ok"
        result.belief_conflicts = 0
        result.belief_revisions = 0
        result.experiments_run = 2
        result.promotions = 1
        result.rejections = 1
        result.constitution_violations = 0
        result.autonomy_level_after = "bounded"
        result.metrics = {}
        return result

    def _make_mock_assessment(
        self,
        overall_score: float = 0.85,
        status: str = "ok",
    ) -> MagicMock:
        """Create a mock assessment object."""
        mock_assessment = MagicMock()
        mock_assessment.overall_score = overall_score
        mock_assessment.status = status
        return mock_assessment

    def test_stores_briefing_in_redis_with_correct_key(self) -> None:
        """Briefing is stored in Redis at autocog:aria_briefing:current."""
        mock_redis = MagicMock()
        mock_controller = MagicMock()
        mock_controller._redis_client = mock_redis

        cycle = AutonomousCognitionFullCycle(controller=mock_controller)
        result = self._make_cycle_result()
        actions = [
            "daily self assessment",
            "belief consistency check",
            "strategy improvement",
        ]
        mock_assessment = self._make_mock_assessment()
        governance_state = {"belief_registry": {"__global__": {}}}

        cycle._store_aria_briefing(
            redis_client=mock_redis,
            result=result,
            mode="full",
            shadow_mode=True,
            actions=actions,
            assessment=mock_assessment,
            governance_state=governance_state,
        )

        # Verify redis.set was called with correct key
        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        assert call_args[0][0] == "autocog:aria_briefing:current"

    def test_stores_briefing_with_24_hour_ttl(self) -> None:
        """Briefing is stored with 24-hour (86400 second) TTL."""
        mock_redis = MagicMock()
        mock_controller = MagicMock()
        mock_controller._redis_client = mock_redis

        cycle = AutonomousCognitionFullCycle(controller=mock_controller)
        result = self._make_cycle_result()
        mock_assessment = self._make_mock_assessment()
        governance_state = {"belief_registry": {"__global__": {}}}

        cycle._store_aria_briefing(
            redis_client=mock_redis,
            result=result,
            mode="full",
            shadow_mode=True,
            actions=[],
            assessment=mock_assessment,
            governance_state=governance_state,
        )

        call_args = mock_redis.set.call_args
        assert call_args[1]["ex"] == 86400  # 24 hours in seconds

    def test_briefing_contains_required_fields(self) -> None:
        """Briefing JSON contains all required fields."""
        mock_redis = MagicMock()
        mock_controller = MagicMock()
        mock_controller._redis_client = mock_redis

        cycle = AutonomousCognitionFullCycle(controller=mock_controller)
        result = self._make_cycle_result()
        result.experiments_run = 3
        result.promotions = 1
        result.rejections = 2
        actions = ["action1", "action2", "action3", "action4", "action5", "action6"]
        mock_assessment = self._make_mock_assessment(overall_score=0.92)

        governance_state = {
            "belief_registry": {
                "__global__": {"next_check_after": "2026-03-30T12:00:00+00:00"}
            }
        }

        cycle._store_aria_briefing(
            redis_client=mock_redis,
            result=result,
            mode="full",
            shadow_mode=True,
            actions=actions,
            assessment=mock_assessment,
            governance_state=governance_state,
        )

        # Extract the briefing JSON that was stored
        stored_json = mock_redis.set.call_args[0][1]
        briefing = json.loads(stored_json)

        # Verify all required fields are present
        assert "last_cycle_timestamp" in briefing
        assert "last_cycle_mode" in briefing
        assert "last_cycle_result" in briefing
        assert "self_assessment_score" in briefing
        assert "runtime_mode" in briefing
        assert "active_experiments" in briefing
        assert "recent_actions" in briefing
        assert "errors_or_warnings" in briefing
        assert "next_scheduled_cycle" in briefing

    def test_runtime_mode_is_shadow_when_shadow_mode_true(self) -> None:
        """Runtime mode is 'shadow' when shadow_mode=True."""
        mock_redis = MagicMock()
        mock_controller = MagicMock()
        mock_controller._redis_client = mock_redis

        cycle = AutonomousCognitionFullCycle(controller=mock_controller)
        result = self._make_cycle_result()

        cycle._store_aria_briefing(
            redis_client=mock_redis,
            result=result,
            mode="full",
            shadow_mode=True,
            actions=[],
            assessment=None,
            governance_state={},
        )

        stored_json = mock_redis.set.call_args[0][1]
        briefing = json.loads(stored_json)
        assert briefing["runtime_mode"] == "shadow"

    def test_runtime_mode_is_canary_when_mode_is_canary(self) -> None:
        """Runtime mode is 'canary' when mode='canary' and shadow_mode=False."""
        mock_redis = MagicMock()
        mock_controller = MagicMock()
        mock_controller._redis_client = mock_redis

        cycle = AutonomousCognitionFullCycle(controller=mock_controller)
        result = self._make_cycle_result()

        cycle._store_aria_briefing(
            redis_client=mock_redis,
            result=result,
            mode="canary",
            shadow_mode=False,
            actions=[],
            assessment=None,
            governance_state={},
        )

        stored_json = mock_redis.set.call_args[0][1]
        briefing = json.loads(stored_json)
        assert briefing["runtime_mode"] == "canary"

    def test_runtime_mode_is_live_for_normal_mode(self) -> None:
        """Runtime mode is 'live' when mode is non-canary and shadow_mode=False."""
        mock_redis = MagicMock()
        mock_controller = MagicMock()
        mock_controller._redis_client = mock_redis

        cycle = AutonomousCognitionFullCycle(controller=mock_controller)
        result = self._make_cycle_result()

        cycle._store_aria_briefing(
            redis_client=mock_redis,
            result=result,
            mode="full",
            shadow_mode=False,
            actions=[],
            assessment=None,
            governance_state={},
        )

        stored_json = mock_redis.set.call_args[0][1]
        briefing = json.loads(stored_json)
        assert briefing["runtime_mode"] == "live"

    def test_recent_actions_limited_to_last_5(self) -> None:
        """Recent actions are limited to the last 5 actions."""
        mock_redis = MagicMock()
        mock_controller = MagicMock()
        mock_controller._redis_client = mock_redis

        cycle = AutonomousCognitionFullCycle(controller=mock_controller)
        result = self._make_cycle_result()
        actions = ["a1", "a2", "a3", "a4", "a5", "a6", "a7", "a8"]

        cycle._store_aria_briefing(
            redis_client=mock_redis,
            result=result,
            mode="full",
            shadow_mode=True,
            actions=actions,
            assessment=None,
            governance_state={},
        )

        stored_json = mock_redis.set.call_args[0][1]
        briefing = json.loads(stored_json)
        assert len(briefing["recent_actions"]) == 5
        assert briefing["recent_actions"] == ["a4", "a5", "a6", "a7", "a8"]

    def test_active_experiments_contains_count_and_status(self) -> None:
        """Active experiments summary contains count and promotion/rejection counts."""
        mock_redis = MagicMock()
        mock_controller = MagicMock()
        mock_controller._redis_client = mock_redis

        cycle = AutonomousCognitionFullCycle(controller=mock_controller)
        result = self._make_cycle_result()
        result.experiments_run = 5
        result.promotions = 2
        result.rejections = 3

        cycle._store_aria_briefing(
            redis_client=mock_redis,
            result=result,
            mode="full",
            shadow_mode=True,
            actions=[],
            assessment=None,
            governance_state={},
        )

        stored_json = mock_redis.set.call_args[0][1]
        briefing = json.loads(stored_json)
        assert briefing["active_experiments"]["count"] == 5
        assert briefing["active_experiments"]["promotions"] == 2
        assert briefing["active_experiments"]["rejections"] == 3

    def test_active_experiments_status_is_failed_when_result_failed(self) -> None:
        """Experiments status is 'failed' when cycle result status is 'failed'."""
        mock_redis = MagicMock()
        mock_controller = MagicMock()
        mock_controller._redis_client = mock_redis

        cycle = AutonomousCognitionFullCycle(controller=mock_controller)
        result = self._make_cycle_result(status="failed")

        cycle._store_aria_briefing(
            redis_client=mock_redis,
            result=result,
            mode="full",
            shadow_mode=True,
            actions=[],
            assessment=None,
            governance_state={},
        )

        stored_json = mock_redis.set.call_args[0][1]
        briefing = json.loads(stored_json)
        assert briefing["active_experiments"]["status"] == "failed"

    def test_captures_budget_warnings_in_errors(self) -> None:
        """Budget exceeded warnings are captured in errors_or_warnings."""
        mock_redis = MagicMock()
        mock_controller = MagicMock()
        mock_controller._redis_client = mock_redis

        cycle = AutonomousCognitionFullCycle(controller=mock_controller)
        result = self._make_cycle_result()
        result.metrics = {
            "budget_warning_cycle": "cycle_budget_exceeded",
            "budget_warning_self_assessment": "phase_budget_exceeded",
        }

        cycle._store_aria_briefing(
            redis_client=mock_redis,
            result=result,
            mode="full",
            shadow_mode=True,
            actions=[],
            assessment=None,
            governance_state={},
        )

        stored_json = mock_redis.set.call_args[0][1]
        briefing = json.loads(stored_json)
        assert "cycle_budget_exceeded" in briefing["errors_or_warnings"]
        assert "self_assessment_phase_budget_exceeded" in briefing["errors_or_warnings"]

    def test_captures_cycle_error_in_errors(self) -> None:
        """Cycle error is captured in errors_or_warnings."""
        mock_redis = MagicMock()
        mock_controller = MagicMock()
        mock_controller._redis_client = mock_redis

        cycle = AutonomousCognitionFullCycle(controller=mock_controller)
        result = self._make_cycle_result()
        result.metrics = {"error": "Redis connection timeout"}

        cycle._store_aria_briefing(
            redis_client=mock_redis,
            result=result,
            mode="full",
            shadow_mode=True,
            actions=[],
            assessment=None,
            governance_state={},
        )

        stored_json = mock_redis.set.call_args[0][1]
        briefing = json.loads(stored_json)
        assert "cycle_error: Redis connection timeout" in briefing["errors_or_warnings"]

    def test_next_scheduled_cycle_from_governance_state(self) -> None:
        """Next scheduled cycle is read from governance state."""
        mock_redis = MagicMock()
        mock_controller = MagicMock()
        mock_controller._redis_client = mock_redis

        cycle = AutonomousCognitionFullCycle(controller=mock_controller)
        result = self._make_cycle_result()
        governance_state = {
            "belief_registry": {
                "__global__": {"next_check_after": "2026-03-30T18:00:00+00:00"}
            }
        }

        cycle._store_aria_briefing(
            redis_client=mock_redis,
            result=result,
            mode="full",
            shadow_mode=True,
            actions=[],
            assessment=None,
            governance_state=governance_state,
        )

        stored_json = mock_redis.set.call_args[0][1]
        briefing = json.loads(stored_json)
        assert briefing["next_scheduled_cycle"] == "2026-03-30T18:00:00+00:00"

    def test_next_scheduled_cycle_is_none_when_not_set(self) -> None:
        """Next scheduled cycle is None when not set in governance state."""
        mock_redis = MagicMock()
        mock_controller = MagicMock()
        mock_controller._redis_client = mock_redis

        cycle = AutonomousCognitionFullCycle(controller=mock_controller)
        result = self._make_cycle_result()
        governance_state = {"belief_registry": {"__global__": {}}}

        cycle._store_aria_briefing(
            redis_client=mock_redis,
            result=result,
            mode="full",
            shadow_mode=True,
            actions=[],
            assessment=None,
            governance_state=governance_state,
        )

        stored_json = mock_redis.set.call_args[0][1]
        briefing = json.loads(stored_json)
        assert briefing["next_scheduled_cycle"] is None

    def test_skips_when_redis_client_is_none(self) -> None:
        """No error when redis_client is None (graceful degradation)."""
        mock_controller = MagicMock()
        mock_controller._redis_client = None

        cycle = AutonomousCognitionFullCycle(controller=mock_controller)
        result = self._make_cycle_result()

        # Should not raise, just log warning
        cycle._store_aria_briefing(
            redis_client=None,
            result=result,
            mode="full",
            shadow_mode=True,
            actions=[],
            assessment=None,
            governance_state={},
        )

        # If we get here without error, the test passes

    def test_handles_redis_failure_gracefully(self) -> None:
        """Redis set failure does not raise exception."""
        mock_redis = MagicMock()
        mock_redis.set.side_effect = ConnectionError("Redis unavailable")
        mock_controller = MagicMock()
        mock_controller._redis_client = mock_redis

        cycle = AutonomousCognitionFullCycle(controller=mock_controller)
        result = self._make_cycle_result()

        # Should not raise - caught by try/except in _store_aria_briefing
        cycle._store_aria_briefing(
            redis_client=mock_redis,
            result=result,
            mode="full",
            shadow_mode=True,
            actions=[],
            assessment=None,
            governance_state={},
        )

    def test_self_assessment_score_is_rounded_to_4_decimals(self) -> None:
        """Self assessment score is rounded to 4 decimal places."""
        mock_redis = MagicMock()
        mock_controller = MagicMock()
        mock_controller._redis_client = mock_redis

        cycle = AutonomousCognitionFullCycle(controller=mock_controller)
        result = self._make_cycle_result()
        mock_assessment = self._make_mock_assessment(overall_score=0.923456789)

        cycle._store_aria_briefing(
            redis_client=mock_redis,
            result=result,
            mode="full",
            shadow_mode=True,
            actions=[],
            assessment=mock_assessment,
            governance_state={},
        )

        stored_json = mock_redis.set.call_args[0][1]
        briefing = json.loads(stored_json)
        assert briefing["self_assessment_score"] == 0.9235

    def test_self_assessment_score_is_none_when_assessment_is_none(self) -> None:
        """Self assessment score is None when assessment is None."""
        mock_redis = MagicMock()
        mock_controller = MagicMock()
        mock_controller._redis_client = mock_redis

        cycle = AutonomousCognitionFullCycle(controller=mock_controller)
        result = self._make_cycle_result()

        cycle._store_aria_briefing(
            redis_client=mock_redis,
            result=result,
            mode="full",
            shadow_mode=True,
            actions=[],
            assessment=None,
            governance_state={},
        )

        stored_json = mock_redis.set.call_args[0][1]
        briefing = json.loads(stored_json)
        assert briefing["self_assessment_score"] is None

    def test_self_assessment_score_is_none_when_score_is_none(self) -> None:
        """Self assessment score is None when assessment.overall_score is None."""
        mock_redis = MagicMock()
        mock_controller = MagicMock()
        mock_controller._redis_client = mock_redis

        cycle = AutonomousCognitionFullCycle(controller=mock_controller)
        result = self._make_cycle_result()
        mock_assessment = self._make_mock_assessment()
        mock_assessment.overall_score = None

        cycle._store_aria_briefing(
            redis_client=mock_redis,
            result=result,
            mode="full",
            shadow_mode=True,
            actions=[],
            assessment=mock_assessment,
            governance_state={},
        )

        stored_json = mock_redis.set.call_args[0][1]
        briefing = json.loads(stored_json)
        assert briefing["self_assessment_score"] is None

    def test_briefing_includes_all_result_metrics(self) -> None:
        """Briefing includes constitution_violations, belief_conflicts, belief_revisions."""
        mock_redis = MagicMock()
        mock_controller = MagicMock()
        mock_controller._redis_client = mock_redis

        cycle = AutonomousCognitionFullCycle(controller=mock_controller)
        result = self._make_cycle_result()
        result.constitution_violations = 2
        result.belief_conflicts = 3
        result.belief_revisions = 1
        result.autonomy_level_after = "high"

        cycle._store_aria_briefing(
            redis_client=mock_redis,
            result=result,
            mode="full",
            shadow_mode=True,
            actions=[],
            assessment=None,
            governance_state={},
        )

        stored_json = mock_redis.set.call_args[0][1]
        briefing = json.loads(stored_json)
        assert briefing["constitution_violations"] == 2
        assert briefing["belief_conflicts"] == 3
        assert briefing["belief_revisions"] == 1
        assert briefing["autonomy_level_after"] == "high"

    def test_briefing_includes_run_id(self) -> None:
        """Briefing includes the run_id for traceability."""
        mock_redis = MagicMock()
        mock_controller = MagicMock()
        mock_controller._redis_client = mock_redis

        cycle = AutonomousCognitionFullCycle(controller=mock_controller)
        result = self._make_cycle_result(run_id="autocog-20260329-120000-abc123")

        cycle._store_aria_briefing(
            redis_client=mock_redis,
            result=result,
            mode="full",
            shadow_mode=True,
            actions=[],
            assessment=None,
            governance_state={},
        )

        stored_json = mock_redis.set.call_args[0][1]
        briefing = json.loads(stored_json)
        assert briefing["run_id"] == "autocog-20260329-120000-abc123"
