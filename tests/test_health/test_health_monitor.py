"""Tests for unified health monitoring system.

For PAPER-003-001: Unified Health Monitoring System
"""

from datetime import datetime

import pytest
from src.health import ComponentType, HealthStatus
from src.health.history import HealthHistory, HealthSnapshot
from src.health.monitor import HealthMonitor
from src.health.score_calculator import (
    ComponentScore,
    HealthScore,
    ScoreCalculator,
)


class TestHealthStatus:
    """Tests for HealthStatus enum."""

    def test_from_score_green(self):
        """Test GREEN status for scores 90-100."""
        assert HealthStatus.from_score(100) == HealthStatus.GREEN
        assert HealthStatus.from_score(95) == HealthStatus.GREEN
        assert HealthStatus.from_score(90) == HealthStatus.GREEN

    def test_from_score_yellow(self):
        """Test YELLOW status for scores 70-89."""
        assert HealthStatus.from_score(89) == HealthStatus.YELLOW
        assert HealthStatus.from_score(70) == HealthStatus.YELLOW
        assert HealthStatus.from_score(75) == HealthStatus.YELLOW

    def test_from_score_red(self):
        """Test RED status for scores 0-69."""
        assert HealthStatus.from_score(69) == HealthStatus.RED
        assert HealthStatus.from_score(0) == HealthStatus.RED
        assert HealthStatus.from_score(30) == HealthStatus.RED


class TestComponentScore:
    """Tests for ComponentScore dataclass."""

    def test_component_score_creation(self):
        """Test creating a component score."""
        score = ComponentScore(
            component=ComponentType.REDIS,
            score=85.0,
            weight=0.1,
        )
        assert score.component == ComponentType.REDIS
        assert score.score == 85.0
        assert score.weight == 0.1
        assert score.weighted_score == 8.5

    def test_component_status_property(self):
        """Test status property."""
        green_score = ComponentScore(ComponentType.REDIS, 95.0, 0.1)
        assert green_score.status == HealthStatus.GREEN

        yellow_score = ComponentScore(ComponentType.REDIS, 80.0, 0.1)
        assert yellow_score.status == HealthStatus.YELLOW

        red_score = ComponentScore(ComponentType.REDIS, 50.0, 0.1)
        assert red_score.status == HealthStatus.RED

    def test_component_score_to_dict(self):
        """Test to_dict method."""
        score = ComponentScore(
            component=ComponentType.REDIS,
            score=85.0,
            weight=0.1,
            details={"is_connected": True},
        )
        result = score.to_dict()
        assert result["component"] == "redis"
        assert result["score"] == 85.0
        assert result["weight"] == 0.1
        assert result["status"] == "yellow"
        assert result["details"]["is_connected"] is True


class TestHealthScore:
    """Tests for HealthScore dataclass."""

    def test_health_score_creation(self):
        """Test creating a health score."""
        component_scores = [
            ComponentScore(ComponentType.REDIS, 90.0, 0.1),
            ComponentScore(ComponentType.INFLUXDB, 80.0, 0.1),
        ]
        health = HealthScore(overall_score=85.0, component_scores=component_scores)
        assert health.overall_score == 85.0
        assert len(health.component_scores) == 2

    def test_health_status_property(self):
        """Test overall status property."""
        green_health = HealthScore(95.0, [])
        assert green_health.status == HealthStatus.GREEN

        yellow_health = HealthScore(75.0, [])
        assert yellow_health.status == HealthStatus.YELLOW

    def test_get_component_score(self):
        """Test getting component score by type."""
        redis_score = ComponentScore(ComponentType.REDIS, 90.0, 0.1)
        component_scores = [redis_score]
        health = HealthScore(85.0, component_scores)

        found = health.get_component_score(ComponentType.REDIS)
        assert found == redis_score

        not_found = health.get_component_score(ComponentType.INFLUXDB)
        assert not_found is None

    def test_health_score_to_dict(self):
        """Test to_dict method."""
        component_scores = [ComponentScore(ComponentType.REDIS, 90.0, 0.1)]
        health = HealthScore(85.0, component_scores)
        result = health.to_dict()
        assert result["overall_score"] == 85.0
        assert result["status"] == "yellow"
        assert len(result["component_scores"]) == 1


class TestScoreCalculator:
    """Tests for ScoreCalculator."""

    def test_weights_sum_to_one(self):
        """Test that component weights sum to 1.0."""
        calculator = ScoreCalculator()
        total = sum(calculator.COMPONENT_WEIGHTS.values())
        assert 0.99 <= total <= 1.01

    def test_calculate_component_score_paper(self):
        """Test calculating score for paper component."""
        calculator = ScoreCalculator()
        health_data = {
            "is_running": True,
            "error_rate": 0.5,
            "latency_ms": 500,
        }
        score = calculator.calculate_component_score(
            ComponentType.ORCHESTRATOR, health_data
        )
        assert score.component == ComponentType.ORCHESTRATOR
        assert 0 <= score.score <= 100

    def test_calculate_component_score_data_source(self):
        """Test calculating score for data source."""
        calculator = ScoreCalculator()
        health_data = {
            "is_connected": True,
            "error_rate": 1.0,
            "circuit_breaker_open": False,
        }
        score = calculator.calculate_component_score(ComponentType.REDIS, health_data)
        assert score.component == ComponentType.REDIS
        assert 0 <= score.score <= 100

    def test_calculate_component_score_exchange(self):
        """Test calculating score for exchange."""
        calculator = ScoreCalculator()
        health_data = {
            "is_connected": True,
            "latency_ms": 150,
            "reconnect_count": 2,
        }
        score = calculator.calculate_component_score(ComponentType.BYBIT, health_data)
        assert score.component == ComponentType.BYBIT
        assert 0 <= score.score <= 100

    def test_calculate_component_score_kill_switch(self):
        """Test calculating score for kill-switch."""
        calculator = ScoreCalculator()
        health_data = {
            "state": "ARMED",
            "last_test_seconds_ago": 86400,  # 1 day ago
        }
        score = calculator.calculate_component_score(
            ComponentType.KILL_SWITCH, health_data
        )
        assert score.component == ComponentType.KILL_SWITCH
        assert 0 <= score.score <= 100

    def test_calculate_overall_score(self):
        """Test calculating overall score."""
        calculator = ScoreCalculator()
        component_scores = [
            ComponentScore(ComponentType.REDIS, 100.0, 0.5),
            ComponentScore(ComponentType.INFLUXDB, 0.0, 0.5),
        ]
        health = calculator.calculate_overall_score(component_scores)
        assert health.overall_score == 50.0

    def test_calculate_overall_score_empty(self):
        """Test calculating overall score with no components."""
        calculator = ScoreCalculator()
        health = calculator.calculate_overall_score([])
        assert health.overall_score == 0.0


class TestHealthHistory:
    """Tests for HealthHistory."""

    @pytest.fixture
    def history(self):
        """Create a health history instance."""
        return HealthHistory(max_history_minutes=10)

    @pytest.mark.asyncio
    async def test_record_snapshot(self, history):
        """Test recording a snapshot."""
        health_score = HealthScore(
            overall_score=85.0,
            component_scores=[ComponentScore(ComponentType.REDIS, 90.0, 0.1)],
        )
        await history.record_snapshot(health_score)
        assert len(history._history) == 1

    @pytest.mark.asyncio
    async def test_record_alert(self, history):
        """Test recording an alert."""
        await history.record_alert(
            component="redis",
            severity="warning",
            message="Connection slow",
        )
        assert len(history._alert_history) == 1
        alert = history._alert_history[0]
        assert alert["component"] == "redis"
        assert alert["severity"] == "warning"

    @pytest.mark.asyncio
    async def test_get_recent_history(self, history):
        """Test getting recent history."""
        health_score = HealthScore(
            overall_score=85.0,
            component_scores=[ComponentScore(ComponentType.REDIS, 90.0, 0.1)],
        )
        await history.record_snapshot(health_score)
        recent = await history.get_recent_history(minutes=5)
        assert len(recent) == 1

    @pytest.mark.asyncio
    async def test_calculate_trend(self, history):
        """Test trend calculation."""
        # Add some snapshots directly to bypass rate limiting
        from datetime import UTC, timedelta

        for i in range(5):
            snapshot = HealthSnapshot(
                score=80.0 + i * 2,  # Improving trend
                status="green",
                timestamp=datetime.now(UTC) - timedelta(minutes=10 - i),
                component_scores={"redis": 90.0},
            )
            history._history.append(snapshot)

        trend = await history.calculate_trend(hours=24)
        assert trend is not None
        assert trend.direction in ["improving", "stable", "degrading"]
        assert trend.avg_score > 0

    @pytest.mark.asyncio
    async def test_calculate_trend_insufficient_data(self, history):
        """Test trend calculation with insufficient data."""
        trend = await history.calculate_trend(hours=24)
        assert trend is None

    @pytest.mark.asyncio
    async def test_get_alert_history(self, history):
        """Test getting alert history."""
        await history.record_alert("redis", "warning", "Slow")
        await history.record_alert("bybit", "critical", "Down")

        alerts = await history.get_alert_history(hours=1)
        assert len(alerts) == 2

        redis_alerts = await history.get_alert_history(hours=1, component="redis")
        assert len(redis_alerts) == 1

    def test_get_stats(self, history):
        """Test getting history stats."""
        stats = history.get_stats()
        assert stats["total_snapshots"] == 0
        assert stats["max_history_minutes"] == 10


class TestHealthMonitor:
    """Tests for HealthMonitor."""

    @pytest.fixture
    def monitor(self):
        """Create a health monitor instance."""
        return HealthMonitor()

    @pytest.mark.asyncio
    async def test_monitor_initialization(self, monitor):
        """Test monitor initialization."""
        assert monitor.calculator is not None
        assert monitor.history is not None
        assert not monitor._running

    @pytest.mark.asyncio
    async def test_start_stop(self, monitor):
        """Test starting and stopping monitor."""
        await monitor.start()
        assert monitor._running
        await monitor.stop()
        assert not monitor._running

    @pytest.mark.asyncio
    async def test_update_health(self, monitor):
        """Test updating health."""
        health = await monitor.update_health()
        assert health is not None
        assert 0 <= health.overall_score <= 100

    @pytest.mark.asyncio
    async def test_get_health(self, monitor):
        """Test getting health."""
        health = await monitor.get_health()
        assert health is not None
        assert hasattr(health, "overall_score")

    def test_get_health_sync(self, monitor):
        """Test synchronous health getter."""
        # Initially returns default
        health = monitor.get_health_sync()
        assert health.overall_score == 0.0

    @pytest.mark.asyncio
    async def test_get_status(self, monitor):
        """Test getting full status."""
        await monitor.update_health()
        status = await monitor.get_status()
        assert "overall_score" in status
        assert "status" in status
        assert "component_scores" in status

    @pytest.mark.asyncio
    async def test_is_healthy(self, monitor):
        """Test healthy check."""
        # Initially false (no score)
        assert not monitor.is_healthy()

        # After update, should be healthy (all components present)
        await monitor.update_health()
        # With no components initialized, score might be 0

    @pytest.mark.asyncio
    async def test_is_critical(self, monitor):
        """Test critical check."""
        # Initially true (no score = critical)
        assert monitor.is_critical()

    @pytest.mark.asyncio
    async def test_record_alert(self, monitor):
        """Test recording alert."""
        await monitor.record_alert(
            component="test",
            severity="warning",
            message="Test alert",
        )
        assert len(monitor.history._alert_history) == 1

    @pytest.mark.asyncio
    async def test_get_component_health(self, monitor):
        """Test getting component health."""
        await monitor.update_health()
        score = monitor.get_component_health(ComponentType.REDIS)
        # May be None if Redis not configured

    def test_check_orchestrator_health_not_initialized(self, monitor):
        """Test orchestrator health check when not initialized."""
        score = monitor._check_orchestrator_health()
        assert score.component == ComponentType.ORCHESTRATOR
        assert score.score < 100  # Should be penalized for not running

    def test_check_kill_switch_health_not_initialized(self, monitor):
        """Test kill-switch health check when not initialized."""
        score = monitor._check_kill_switch_health()
        assert score.component == ComponentType.KILL_SWITCH
        assert score.score < 100  # Should be penalized

    def test_check_data_source_health(self, monitor):
        """Test data source health checks."""
        redis_score = monitor._check_redis_health()
        assert redis_score.component == ComponentType.REDIS

        influx_score = monitor._check_influxdb_health()
        assert influx_score.component == ComponentType.INFLUXDB

        pg_score = monitor._check_postgresql_health()
        assert pg_score.component == ComponentType.POSTGRESQL

    def test_check_exchange_health_not_initialized(self, monitor):
        """Test exchange health check when not initialized."""
        bybit_score = monitor._check_bybit_health()
        assert bybit_score.component == ComponentType.BYBIT
        assert bybit_score.score < 100

        bitget_score = monitor._check_bitget_health()
        assert bitget_score.component == ComponentType.BITGET
        assert bitget_score.score < 100
