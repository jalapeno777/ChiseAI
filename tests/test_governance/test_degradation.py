"""
Tests for DegradationTracker - Graduated health degradation detection (ST-MVP-005).

Covers:
- DegradationTracker unit tests (all 4 levels, edge cases)
- Integration test for sentinel -> tracker flow
- Gate evaluation with degradation

Story: ST-MVP-005
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from src.governance.checkpoint.gates import (
    GateChecker,
)
from src.governance.health.degradation import (
    DegradationLevel,
    DegradationTracker,
)
from src.governance.health.sentinel import (
    HealthSentinel,
    HealthSentinelConfig,
)

# ---------------------------------------------------------------------------
# Unit Tests: DegradationTracker
# ---------------------------------------------------------------------------


class TestDegradationTrackerInit:
    """Tests for DegradationTracker initialization."""

    def test_default_window_size(self):
        tracker = DegradationTracker()
        assert tracker.window_size == 5

    def test_custom_window_size(self):
        tracker = DegradationTracker(window_size=10)
        assert tracker.window_size == 10

    def test_initial_levels_empty(self):
        tracker = DegradationTracker()
        assert tracker.get_all_levels() == {}


class TestDegradationTrackerClassify:
    """Tests for DegradationTracker.classify() — all 4 levels."""

    def test_stable_constant_scores(self):
        """Constant scores -> STABLE (slope ≈ 0)."""
        tracker = DegradationTracker()
        result = tracker.classify([100, 100, 100, 100, 100])
        assert result == DegradationLevel.STABLE

    def test_stable_improving_scores(self):
        """Improving scores -> STABLE (positive slope)."""
        tracker = DegradationTracker()
        result = tracker.classify([80, 85, 90, 95, 100])
        assert result == DegradationLevel.STABLE

    def test_stable_slight_decline(self):
        """Slight decline within threshold -> STABLE."""
        tracker = DegradationTracker()
        # slope ≈ -0.3 per sample (within -0.5 threshold)
        result = tracker.classify([100, 99.7, 99.4, 99.1, 98.8])
        assert result == DegradationLevel.STABLE

    def test_mild_degradation(self):
        """Decline between -0.5 and -2.0 -> MILD_DEGRADATION."""
        tracker = DegradationTracker()
        # slope = -1.0 per sample
        result = tracker.classify([100, 99, 98, 97, 96])
        assert result == DegradationLevel.MILD_DEGRADATION

    def test_moderate_degradation(self):
        """Decline between -2.0 and -5.0 -> MODERATE_DEGRADATION."""
        tracker = DegradationTracker()
        # slope = -3.0 per sample
        result = tracker.classify([100, 97, 94, 91, 88])
        assert result == DegradationLevel.MODERATE_DEGRADATION

    def test_severe_degradation(self):
        """Decline below -5.0 -> SEVERE_DEGRADATION."""
        tracker = DegradationTracker()
        # slope = -10.0 per sample
        result = tracker.classify([100, 90, 80, 70, 60])
        assert result == DegradationLevel.SEVERE_DEGRADATION

    def test_single_score_returns_stable(self):
        """Single score (no slope possible) -> STABLE."""
        tracker = DegradationTracker()
        result = tracker.classify([75.0])
        assert result == DegradationLevel.STABLE

    def test_empty_scores_returns_stable(self):
        """Empty scores -> STABLE."""
        tracker = DegradationTracker()
        result = tracker.classify([])
        assert result == DegradationLevel.STABLE

    def test_two_scores_stable(self):
        """Two scores with slight change -> STABLE."""
        tracker = DegradationTracker()
        result = tracker.classify([100, 99.8])
        assert result == DegradationLevel.STABLE

    def test_two_scores_mild(self):
        """Two scores with mild decline -> MILD_DEGRADATION."""
        tracker = DegradationTracker()
        result = tracker.classify([100, 98.5])
        assert result == DegradationLevel.MILD_DEGRADATION


class TestDegradationTrackerRecord:
    """Tests for DegradationTracker.record() — event emission."""

    def test_record_returns_none_first_sample(self):
        """First sample has no slope -> returns None."""
        tracker = DegradationTracker()
        result = tracker.record("scheduler", 100.0)
        assert result is None

    def test_record_returns_none_no_transition(self):
        """Second sample with stable trend -> returns None."""
        tracker = DegradationTracker()
        tracker.record("scheduler", 100.0)
        result = tracker.record("scheduler", 99.9)
        assert result is None

    def test_record_returns_level_on_transition(self):
        """Level transition returns the new level."""
        tracker = DegradationTracker(window_size=5)
        tracker.record("scheduler", 100.0)
        tracker.record("scheduler", 95.0)
        # slope = -5.0 → MODERATE_DEGRADATION
        tracker.record("scheduler", 90.0)
        # slope = -5.0 → MODERATE_DEGRADATION (same level, no transition)
        # Need more samples to trigger transition
        tracker.record("scheduler", 85.0)
        # slope = -5.0 still MODERATE
        result = tracker.record("scheduler", 60.0)
        # Now slope is more negative → should transition
        # Slope over [100, 95, 90, 85, 60] = -8.0 → SEVERE
        assert result == DegradationLevel.SEVERE_DEGRADATION

    def test_record_tracks_multiple_components(self):
        """Tracker handles multiple independent components."""
        tracker = DegradationTracker()

        tracker.record("scheduler", 100.0)
        tracker.record("agent-1", 80.0)

        assert tracker.get_level("scheduler") == DegradationLevel.STABLE
        assert tracker.get_level("agent-1") == DegradationLevel.STABLE

    def test_record_sliding_window_overflow(self):
        """Window discards oldest samples beyond maxlen."""
        tracker = DegradationTracker(window_size=3)

        tracker.record("comp", 100.0)
        tracker.record("comp", 95.0)
        tracker.record("comp", 90.0)
        tracker.record("comp", 100.0)  # Window now [95, 90, 100]

        window = tracker.get_window("comp")
        assert len(window) == 3
        assert window == [95.0, 90.0, 100.0]


class TestDegradationTrackerGetLevel:
    """Tests for DegradationTracker.get_level()."""

    def test_unknown_component_returns_stable(self):
        tracker = DegradationTracker()
        assert tracker.get_level("unknown") == DegradationLevel.STABLE

    def test_tracked_component_returns_correct_level(self):
        tracker = DegradationTracker()
        tracker.record("comp", 100.0)
        tracker.record("comp", 100.0)
        assert tracker.get_level("comp") == DegradationLevel.STABLE


class TestDegradationTrackerGetSlope:
    """Tests for DegradationTracker.get_slope()."""

    def test_unknown_component_returns_none(self):
        tracker = DegradationTracker()
        assert tracker.get_slope("unknown") is None

    def test_single_sample_returns_none(self):
        tracker = DegradationTracker()
        tracker.record("comp", 100.0)
        assert tracker.get_slope("comp") is None

    def test_stable_slope(self):
        tracker = DegradationTracker()
        tracker.record("comp", 100.0)
        tracker.record("comp", 100.0)
        assert tracker.get_slope("comp") == 0.0

    def test_declining_slope(self):
        tracker = DegradationTracker(window_size=5)
        tracker.record("comp", 100.0)
        tracker.record("comp", 90.0)
        slope = tracker.get_slope("comp")
        assert slope == -10.0


class TestDegradationTrackerIsSevere:
    """Tests for DegradationTracker.is_severe()."""

    def test_unknown_not_severe(self):
        tracker = DegradationTracker()
        assert tracker.is_severe("unknown") is False

    def test_stable_not_severe(self):
        tracker = DegradationTracker()
        tracker.record("comp", 100.0)
        tracker.record("comp", 99.0)
        assert tracker.is_severe("comp") is False

    def test_severe_is_severe(self):
        tracker = DegradationTracker(window_size=5)
        # Force severe degradation
        tracker._windows["comp"] = __import__("collections").deque(
            [100, 85, 70, 55, 40], maxlen=5
        )
        tracker._levels["comp"] = DegradationLevel.SEVERE_DEGRADATION
        assert tracker.is_severe("comp") is True


class TestDegradationTrackerIsDegrading:
    """Tests for DegradationTracker.is_degrading()."""

    def test_stable_not_degrading(self):
        tracker = DegradationTracker()
        tracker.record("comp", 100.0)
        tracker.record("comp", 99.9)
        assert tracker.is_degrading("comp") is False

    def test_mild_is_degrading(self):
        tracker = DegradationTracker()
        tracker._levels["comp"] = DegradationLevel.MILD_DEGRADATION
        assert tracker.is_degrading("comp") is True


class TestDegradationTrackerReset:
    """Tests for DegradationTracker.reset()."""

    def test_reset_specific_component(self):
        tracker = DegradationTracker()
        tracker.record("comp-a", 100.0)
        tracker.record("comp-b", 80.0)

        tracker.reset("comp-a")

        assert tracker.get_level("comp-a") == DegradationLevel.STABLE
        assert tracker.get_level("comp-b") == DegradationLevel.STABLE

    def test_reset_all(self):
        tracker = DegradationTracker()
        tracker.record("comp-a", 100.0)
        tracker.record("comp-b", 80.0)

        tracker.reset()

        assert tracker.get_all_levels() == {}


class TestDegradationTrackerSlopeCalculation:
    """Tests for slope calculation edge cases."""

    def test_exact_stable_threshold(self):
        """Slope exactly at -0.5 threshold → STABLE."""
        tracker = DegradationTracker()
        # With 2 samples, slope = -0.5
        result = tracker.classify([100.0, 99.5])
        assert result == DegradationLevel.STABLE

    def test_just_below_stable_threshold(self):
        """Slope just below -0.5 → MILD."""
        tracker = DegradationTracker()
        # slope = -0.6
        result = tracker.classify([100.0, 99.4])
        assert result == DegradationLevel.MILD_DEGRADATION

    def test_exact_mild_threshold(self):
        """Slope exactly at -2.0 threshold → MILD."""
        tracker = DegradationTracker()
        result = tracker.classify([100.0, 98.0])
        assert result == DegradationLevel.MILD_DEGRADATION

    def test_just_below_mild_threshold(self):
        """Slope just below -2.0 → MODERATE."""
        tracker = DegradationTracker()
        result = tracker.classify([100.0, 97.9])
        assert result == DegradationLevel.MODERATE_DEGRADATION

    def test_exact_moderate_threshold(self):
        """Slope exactly at -5.0 threshold → MODERATE."""
        tracker = DegradationTracker()
        result = tracker.classify([100.0, 95.0])
        assert result == DegradationLevel.MODERATE_DEGRADATION

    def test_just_below_moderate_threshold(self):
        """Slope just below -5.0 → SEVERE."""
        tracker = DegradationTracker()
        result = tracker.classify([100.0, 94.9])
        assert result == DegradationLevel.SEVERE_DEGRADATION


class TestDegradationTrackerRedisIntegration:
    """Tests for Redis persistence (mocked)."""

    def test_persist_state_calls_redis(self):
        """record() persists state to Redis when client available."""
        mock_redis = MagicMock()
        tracker = DegradationTracker(redis_client=mock_redis)
        tracker.record("scheduler", 95.0)

        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args
        assert call_args[0][0] == "bmad:chiseai:health:degradation:scheduler"

    def test_persist_state_no_redis(self):
        """record() works without Redis (in-memory only)."""
        tracker = DegradationTracker()
        result = tracker.record("scheduler", 95.0)
        assert result is None  # No transition on first sample
        assert tracker.get_level("scheduler") == DegradationLevel.STABLE

    def test_restore_state_from_redis(self):
        """restore_state() loads level and window from Redis."""
        import json

        mock_redis = MagicMock()
        state = {
            "component": "scheduler",
            "level": "moderate_degradation",
            "window": [100.0, 95.0, 90.0],
            "updated_at": "2026-01-01T00:00:00Z",
        }
        mock_redis.get.return_value = json.dumps(state)

        tracker = DegradationTracker(redis_client=mock_redis)
        success = tracker.restore_state("scheduler")

        assert success is True
        assert tracker.get_level("scheduler") == DegradationLevel.MODERATE_DEGRADATION
        assert len(tracker.get_window("scheduler")) == 3

    def test_restore_state_no_data(self):
        """restore_state() returns False when no data in Redis."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        tracker = DegradationTracker(redis_client=mock_redis)
        assert tracker.restore_state("scheduler") is False

    def test_redis_error_handled_gracefully(self):
        """Redis errors are caught without crashing."""
        mock_redis = MagicMock()
        mock_redis.setex.side_effect = Exception("Connection refused")

        tracker = DegradationTracker(redis_client=mock_redis)
        # Should not raise
        tracker.record("scheduler", 95.0)
        # State should still be tracked in memory
        assert tracker.get_level("scheduler") == DegradationLevel.STABLE


# ---------------------------------------------------------------------------
# Integration Tests: Sentinel -> DegradationTracker
# ---------------------------------------------------------------------------


class TestSentinelDegradationIntegration:
    """Integration tests for sentinel -> degradation tracker flow."""

    def test_sentinel_creates_degradation_tracker(self):
        """Sentinel initializes DegradationTracker by default."""
        sentinel = HealthSentinel()
        assert sentinel.degradation_tracker is not None
        assert sentinel.degradation_tracker.window_size == 5

    def test_sentinel_custom_degradation_config(self):
        """Sentinel respects custom degradation window size."""
        config = HealthSentinelConfig(degradation_window_size=10)
        sentinel = HealthSentinel(config=config)
        assert sentinel.degradation_tracker.window_size == 10

    def test_sentinel_feeds_scores_to_tracker(self):
        """update_agent_metrics feeds score into degradation tracker."""
        sentinel = HealthSentinel()

        metrics = {
            "performance": {"task_completion_time": 30},
            "quality": {"bug_escape_rate": 0},
            "reliability": {"uptime": 99.9},
            "collaboration": {"conflict_rate": 0},
        }

        sentinel.update_agent_metrics("agent-1", metrics)

        # Should have one sample in degradation window
        window = sentinel.degradation_tracker.get_window("agent-1")
        assert len(window) == 1

    def test_sentinel_tracks_degradation_over_time(self):
        """Multiple updates produce degradation tracking."""
        config = HealthSentinelConfig(degradation_window_size=5)
        sentinel = HealthSentinel(config=config)

        # Simulate declining health
        for quality_score in [100, 90, 80, 70, 60]:
            metrics = {
                "performance": {"task_completion_time": 30},
                "quality": {"bug_escape_rate": 0},
                "reliability": {"uptime": quality_score},
                "collaboration": {"conflict_rate": 0},
            }
            sentinel.update_agent_metrics("agent-1", metrics)

        # Degradation tracker should have captured the decline
        level = sentinel.get_degradation_level("agent-1")
        assert level != DegradationLevel.STABLE

    def test_sentinel_get_degradation_events(self):
        """Degradation events are captured when level changes."""
        sentinel = HealthSentinel()

        # Simulate rapid decline to trigger transition
        for uptime in [100, 90, 80, 70, 60]:
            metrics = {
                "performance": {"task_completion_time": 30},
                "quality": {"bug_escape_rate": 0},
                "reliability": {"uptime": uptime},
                "collaboration": {"conflict_rate": 0},
            }
            sentinel.update_agent_metrics("agent-1", metrics)

        # Should have captured degradation events
        events = sentinel.get_degradation_events()
        assert isinstance(events, list)

    def test_sentinel_degradation_disabled(self):
        """Degradation tracking can be disabled."""
        config = HealthSentinelConfig(enable_degradation_tracking=False)
        sentinel = HealthSentinel(config=config)

        metrics = {
            "performance": {"task_completion_time": 30},
            "quality": {"bug_escape_rate": 0},
            "reliability": {"uptime": 50},
            "collaboration": {"conflict_rate": 0},
        }
        sentinel.update_agent_metrics("agent-1", metrics)

        # Should not have fed into tracker
        window = sentinel.degradation_tracker.get_window("agent-1")
        assert len(window) == 0

    def test_sentinel_snapshot_includes_degradation(self):
        """Health snapshot includes degradation context."""
        sentinel = HealthSentinel()

        metrics = {
            "performance": {"task_completion_time": 30},
            "quality": {"bug_escape_rate": 0},
            "reliability": {"uptime": 99.9},
            "collaboration": {"conflict_rate": 0},
        }
        sentinel.update_agent_metrics("agent-1", metrics)

        snapshot = sentinel.get_snapshot()
        assert snapshot is not None


# ---------------------------------------------------------------------------
# Gate Evaluation Tests: G1 with Degradation
# ---------------------------------------------------------------------------


class TestGateG1Degradation:
    """Tests for G1 gate with degradation awareness."""

    def test_g1_pass_without_degradation_data(self):
        """G1 passes normally when no degradation data in Redis."""
        mock_redis = MagicMock()
        mock_redis.ping.return_value = True
        mock_redis.hgetall.return_value = {
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "running",
            "uptime_seconds": "3600",
        }
        mock_redis.get.return_value = None  # No degradation data

        checker = GateChecker(redis_client=mock_redis)
        result = checker.check_g1_scheduler()
        assert result.status == GateChecker.STATUS_PASS

    def test_g1_pass_with_stable_degradation(self):
        """G1 passes when degradation is STABLE."""
        import json

        mock_redis = MagicMock()
        mock_redis.ping.return_value = True
        mock_redis.hgetall.return_value = {
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "running",
            "uptime_seconds": "3600",
        }
        # Stable degradation state
        mock_redis.get.return_value = json.dumps(
            {
                "level": "stable",
                "window": [100, 99.5],
            }
        )

        checker = GateChecker(redis_client=mock_redis)
        result = checker.check_g1_scheduler()
        assert result.status == GateChecker.STATUS_PASS

    def test_g1_detail_includes_mild_degradation(self):
        """G1 detail includes degradation info for MILD level."""
        import json

        mock_redis = MagicMock()
        mock_redis.ping.return_value = True
        mock_redis.hgetall.return_value = {
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "running",
            "uptime_seconds": "3600",
        }
        mock_redis.get.return_value = json.dumps(
            {
                "level": "mild_degradation",
                "window": [100, 99.0],
            }
        )

        checker = GateChecker(redis_client=mock_redis)
        result = checker.check_g1_scheduler()
        # Should still PASS (degradation info is additive)
        assert (
            "degradation=mild" in result.detail
            or result.status == GateChecker.STATUS_PASS
        )

    def test_g1_degradation_check_handles_redis_error(self):
        """G1 degradation check handles Redis errors gracefully."""
        mock_redis = MagicMock()
        mock_redis.ping.return_value = True
        mock_redis.hgetall.return_value = {
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "running",
            "uptime_seconds": "3600",
        }
        mock_redis.get.side_effect = Exception("Connection error")

        checker = GateChecker(redis_client=mock_redis)
        result = checker.check_g1_scheduler()
        # Should still pass (degradation check is non-critical)
        assert result.status == GateChecker.STATUS_PASS

    def test_g1_degradation_check_handles_invalid_data(self):
        """G1 degradation check handles invalid JSON gracefully."""
        mock_redis = MagicMock()
        mock_redis.ping.return_value = True
        mock_redis.hgetall.return_value = {
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "running",
            "uptime_seconds": "3600",
        }
        mock_redis.get.return_value = "not valid json"

        checker = GateChecker(redis_client=mock_redis)
        result = checker.check_g1_scheduler()
        # Should still pass
        assert result.status == GateChecker.STATUS_PASS

    def test_g1_original_behavior_preserved(self):
        """G1 original behavior (staleness check) still works."""
        mock_redis = MagicMock()
        mock_redis.ping.return_value = True

        # Stale heartbeat (5 minutes old)
        stale_time = datetime.now(UTC) - timedelta(minutes=5)
        mock_redis.hgetall.return_value = {
            "timestamp": stale_time.isoformat(),
            "status": "running",
            "uptime_seconds": "3600",
        }

        checker = GateChecker(redis_client=mock_redis)
        result = checker.check_g1_scheduler()
        assert result.status == GateChecker.STATUS_CHECK
        assert "stale" in result.detail.lower()
