"""
Test Health Scorer - Unit tests for health scoring functionality (ST-GOV-008).

Story: ST-GOV-008
"""

from datetime import datetime

from src.governance.health.scorer import (
    DEFAULT_DIMENSIONS,
    AgentHealthScore,
    DimensionConfig,
    HealthScorer,
    HealthStatus,
)


class TestHealthScorer:
    """Tests for HealthScorer class."""

    def test_scorer_initialization(self):
        """Test scorer initializes with default dimensions."""
        scorer = HealthScorer()
        assert scorer.dimensions == DEFAULT_DIMENSIONS
        assert len(scorer.dimensions) == 4

    def test_scorer_custom_dimensions(self):
        """Test scorer with custom dimensions."""
        custom = {
            "custom_dim": DimensionConfig(
                name="custom_dim",
                weight=1.0,
                metrics=["metric1"],
            )
        }
        scorer = HealthScorer(dimensions=custom)
        assert "custom_dim" in scorer.dimensions

    def test_score_agent_perfect_metrics(self):
        """Test scoring with perfect metrics."""
        scorer = HealthScorer()
        metrics = {
            "performance": {
                "task_completion_time": 15,  # <30min = 100
                "pr_merge_time": 0.5,  # <1hr = 100
                "ci_duration": 3,  # <5min = 100
            },
            "quality": {
                "bug_escape_rate": 0,  # 0% = 100
                "review_rejection_rate": 0,  # 0% = 100
                "rollback_frequency": 0,  # 0 = 100
            },
            "reliability": {
                "uptime": 99.99,  # >=99.9% = 100
                "error_rate": 0,  # 0% = 100
                "recovery_time": 0.5,  # <1min = 100
            },
            "collaboration": {
                "conflict_rate": 0,  # 0 = 100
                "handoff_success": 100,  # 100% = 100
                "knowledge_sharing": 100,
            },
        }

        score = scorer.score_agent("test-agent", metrics)

        assert score.agent_id == "test-agent"
        assert score.overall_score >= 95  # Should be very high
        assert score.status == HealthStatus.HEALTHY
        assert score.trend == "stable"

    def test_score_agent_poor_metrics(self):
        """Test scoring with poor metrics."""
        scorer = HealthScorer()
        metrics = {
            "performance": {
                "task_completion_time": 180,  # >2hr = low score
                "pr_merge_time": 48,  # >24hr = low score
                "ci_duration": 30,  # >20min = low score
            },
            "quality": {
                "bug_escape_rate": 20,  # >=10% = 50-
                "review_rejection_rate": 40,  # >=25% = 50-
                "rollback_frequency": 5,  # >=3 = low score
            },
            "reliability": {
                "uptime": 90,  # <95% = 50
                "error_rate": 10,  # >=5% = low score
                "recovery_time": 30,  # >=15min = low score
            },
            "collaboration": {
                "conflict_rate": 10,  # >=5 = low score
                "handoff_success": 50,  # <75% = 40
                "knowledge_sharing": 20,
            },
        }

        score = scorer.score_agent("test-agent", metrics)

        assert score.overall_score < 50
        assert score.status in (HealthStatus.UNHEALTHY, HealthStatus.CRITICAL)

    def test_score_agent_partial_metrics(self):
        """Test scoring with partial metrics (some dimensions missing)."""
        scorer = HealthScorer()
        metrics = {
            "performance": {"task_completion_time": 30},
            "quality": {"bug_escape_rate": 0},
            # Missing reliability and collaboration
        }

        score = scorer.score_agent("test-agent", metrics)

        # Should still work, using defaults for missing metrics
        assert isinstance(score, AgentHealthScore)
        assert "performance" in score.dimensions
        assert "quality" in score.dimensions
        assert "reliability" in score.dimensions  # Default score
        assert "collaboration" in score.dimensions  # Default score

    def test_score_agent_trend_improving(self):
        """Test trend detection when score improves."""
        scorer = HealthScorer()

        # First score
        poor_metrics = {
            "performance": {"task_completion_time": 120},
            "quality": {"bug_escape_rate": 10},
            "reliability": {"uptime": 95},
            "collaboration": {"conflict_rate": 5},
        }
        first_score = scorer.score_agent("test-agent", poor_metrics)

        # Second score with better metrics
        good_metrics = {
            "performance": {"task_completion_time": 15},
            "quality": {"bug_escape_rate": 0},
            "reliability": {"uptime": 99.9},
            "collaboration": {"conflict_rate": 0},
        }
        second_score = scorer.score_agent(
            "test-agent",
            good_metrics,
            previous_score=first_score.overall_score,
        )

        assert second_score.trend == "improving"
        assert second_score.previous_score == first_score.overall_score

    def test_score_agent_trend_declining(self):
        """Test trend detection when score declines."""
        scorer = HealthScorer()

        good_metrics = {
            "performance": {"task_completion_time": 15},
            "quality": {"bug_escape_rate": 0},
            "reliability": {"uptime": 99.9},
            "collaboration": {"conflict_rate": 0},
        }
        first_score = scorer.score_agent("test-agent", good_metrics)

        poor_metrics = {
            "performance": {"task_completion_time": 120},
            "quality": {"bug_escape_rate": 10},
            "reliability": {"uptime": 95},
            "collaboration": {"conflict_rate": 5},
        }
        second_score = scorer.score_agent(
            "test-agent",
            poor_metrics,
            previous_score=first_score.overall_score,
        )

        assert second_score.trend == "declining"

    def test_classify_status(self):
        """Test health status classification."""
        scorer = HealthScorer()

        assert scorer._classify_status(85) == HealthStatus.HEALTHY
        assert scorer._classify_status(80) == HealthStatus.HEALTHY
        assert scorer._classify_status(79) == HealthStatus.DEGRADED
        assert scorer._classify_status(60) == HealthStatus.DEGRADED
        assert scorer._classify_status(59) == HealthStatus.UNHEALTHY
        assert scorer._classify_status(40) == HealthStatus.UNHEALTHY
        assert scorer._classify_status(39) == HealthStatus.CRITICAL
        assert scorer._classify_status(0) == HealthStatus.CRITICAL

    def test_is_healthy(self):
        """Test is_healthy helper method."""
        score = AgentHealthScore(
            agent_id="test",
            overall_score=75,
            status=HealthStatus.DEGRADED,
            dimensions={},
            timestamp=datetime.utcnow(),
        )
        assert score.is_healthy() is True  # >= 70

        score = AgentHealthScore(
            agent_id="test",
            overall_score=65,
            status=HealthStatus.DEGRADED,
            dimensions={},
            timestamp=datetime.utcnow(),
        )
        assert score.is_healthy() is False  # < 70


class TestSwarmHealthScoring:
    """Tests for swarm-level health scoring."""

    def test_score_swarm_empty(self):
        """Test swarm scoring with no agents."""
        scorer = HealthScorer()
        swarm = scorer.score_swarm([])

        assert swarm.overall_score == 0.0
        assert swarm.status == HealthStatus.CRITICAL
        assert swarm.agent_count == 0

    def test_score_swarm_single_agent(self):
        """Test swarm scoring with single agent."""
        scorer = HealthScorer()

        metrics = {
            "performance": {"task_completion_time": 15},
            "quality": {"bug_escape_rate": 0},
            "reliability": {"uptime": 99.9},
            "collaboration": {"conflict_rate": 0},
        }
        agent_score = scorer.score_agent("agent-1", metrics)
        swarm = scorer.score_swarm([agent_score])

        assert swarm.agent_count == 1
        assert swarm.healthy_count == 1
        assert swarm.overall_score == agent_score.overall_score

    def test_score_swarm_multiple_agents(self):
        """Test swarm scoring with multiple agents."""
        scorer = HealthScorer()

        # Create multiple agent scores
        good_metrics = {
            "performance": {"task_completion_time": 15},
            "quality": {"bug_escape_rate": 0},
            "reliability": {"uptime": 99.9},
            "collaboration": {"conflict_rate": 0},
        }

        poor_metrics = {
            "performance": {"task_completion_time": 120},
            "quality": {"bug_escape_rate": 10},
            "reliability": {"uptime": 95},
            "collaboration": {"conflict_rate": 5},
        }

        agent1 = scorer.score_agent("agent-1", good_metrics)
        agent2 = scorer.score_agent("agent-2", good_metrics)
        agent3 = scorer.score_agent("agent-3", poor_metrics)

        swarm = scorer.score_swarm([agent1, agent2, agent3])

        assert swarm.agent_count == 3
        assert swarm.healthy_count == 2
        # Average should be between the two scores
        min_score = min(agent1.overall_score, agent3.overall_score)
        max_score = max(agent1.overall_score, agent3.overall_score)
        assert min_score <= swarm.overall_score <= max_score

    def test_score_swarm_status_distribution(self):
        """Test swarm correctly counts status distribution."""
        scorer = HealthScorer()

        # Create mock agent scores with different statuses
        def create_score(status, score):
            return AgentHealthScore(
                agent_id="test",
                overall_score=score,
                status=status,
                dimensions={},
                timestamp=datetime.utcnow(),
            )

        agents = [
            create_score(HealthStatus.HEALTHY, 85),
            create_score(HealthStatus.HEALTHY, 82),
            create_score(HealthStatus.DEGRADED, 70),
            create_score(HealthStatus.UNHEALTHY, 50),
            create_score(HealthStatus.CRITICAL, 30),
        ]

        swarm = scorer.score_swarm(agents)

        assert swarm.healthy_count == 2
        assert swarm.degraded_count == 1
        assert swarm.unhealthy_count == 1
        assert swarm.critical_count == 1


class TestMetricNormalization:
    """Tests for metric normalization logic."""

    def test_task_completion_time_normalization(self):
        """Test task_completion_time metric normalization."""
        scorer = HealthScorer()
        config = DEFAULT_DIMENSIONS["performance"]

        # Test various values
        assert scorer._normalize_metric("task_completion_time", 15, config) == 100.0
        assert scorer._normalize_metric("task_completion_time", 30, config) == 100.0
        assert scorer._normalize_metric("task_completion_time", 45, config) == 80.0
        assert scorer._normalize_metric("task_completion_time", 90, config) == 60.0

    def test_uptime_normalization(self):
        """Test uptime metric normalization."""
        scorer = HealthScorer()
        config = DEFAULT_DIMENSIONS["reliability"]

        assert scorer._normalize_metric("uptime", 99.99, config) == 100.0
        assert scorer._normalize_metric("uptime", 99.5, config) == 90.0
        assert scorer._normalize_metric("uptime", 97.0, config) == 70.0
        assert scorer._normalize_metric("uptime", 90.0, config) == 45.0

    def test_error_rate_normalization(self):
        """Test error_rate metric normalization."""
        scorer = HealthScorer()
        config = DEFAULT_DIMENSIONS["reliability"]

        assert scorer._normalize_metric("error_rate", 0, config) == 100.0
        assert scorer._normalize_metric("error_rate", 0.5, config) == 90.0
        assert scorer._normalize_metric("error_rate", 3, config) == 70.0
        assert scorer._normalize_metric("error_rate", 10, config) == 20.0


class TestHistoryManagement:
    """Tests for score history management."""

    def test_score_history_stored(self):
        """Test that scores are stored in history."""
        scorer = HealthScorer()

        metrics = {
            "performance": {"task_completion_time": 30},
            "quality": {"bug_escape_rate": 0},
            "reliability": {"uptime": 99.9},
            "collaboration": {"conflict_rate": 0},
        }

        # Score the same agent multiple times
        for _i in range(5):
            scorer.score_agent("test-agent", metrics)

        history = scorer.get_agent_history("test-agent")
        assert len(history) == 5

    def test_history_pruned_by_time(self):
        """Test that old history is pruned."""
        scorer = HealthScorer(history_window_hours=0)  # Immediate expiration

        metrics = {
            "performance": {"task_completion_time": 30},
            "quality": {"bug_escape_rate": 0},
            "reliability": {"uptime": 99.9},
            "collaboration": {"conflict_rate": 0},
        }

        scorer.score_agent("test-agent", metrics)
        history = scorer.get_agent_history("test-agent")

        # History should be empty due to time-based pruning
        assert len(history) == 0
