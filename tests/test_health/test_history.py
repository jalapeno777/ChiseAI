"""Additional tests for health history module.

For PAPER-003-001: Unified Health Monitoring System
"""

import pytest
from datetime import datetime, UTC, timedelta

from src.health.history import HealthHistory, HealthSnapshot, TrendAnalysis
from src.health.score_calculator import HealthScore, ComponentScore
from src.health import ComponentType


class TestHealthSnapshot:
    """Tests for HealthSnapshot."""

    def test_snapshot_creation(self):
        """Test creating a snapshot."""
        snapshot = HealthSnapshot(
            score=85.0,
            status="yellow",
            timestamp=datetime.now(UTC),
            component_scores={"redis": 90.0},
        )
        assert snapshot.score == 85.0
        assert snapshot.status == "yellow"

    def test_snapshot_to_dict(self):
        """Test snapshot to_dict."""
        snapshot = HealthSnapshot(
            score=85.0,
            status="yellow",
            timestamp=datetime.now(UTC),
            component_scores={"redis": 90.0},
        )
        result = snapshot.to_dict()
        assert result["score"] == 85.0
        assert result["status"] == "yellow"
        assert "timestamp" in result


class TestTrendAnalysis:
    """Tests for TrendAnalysis."""

    def test_trend_creation(self):
        """Test creating trend analysis."""
        trend = TrendAnalysis(
            direction="improving",
            change_1h=5.0,
            change_24h=10.0,
            volatility=2.5,
            avg_score=85.0,
            min_score=80.0,
            max_score=90.0,
        )
        assert trend.direction == "improving"
        assert trend.change_1h == 5.0

    def test_trend_to_dict(self):
        """Test trend to_dict."""
        trend = TrendAnalysis(
            direction="stable",
            change_1h=0.0,
            change_24h=0.0,
            volatility=1.0,
            avg_score=85.0,
            min_score=80.0,
            max_score=90.0,
        )
        result = trend.to_dict()
        assert result["direction"] == "stable"
        assert result["change_1h"] == 0.0


class TestHealthHistoryExtended:
    """Extended tests for HealthHistory."""

    @pytest.fixture
    def history(self):
        """Create a health history instance."""
        return HealthHistory(max_history_minutes=10)

    def test_initialization(self):
        """Test history initialization."""
        history = HealthHistory()
        assert history.max_history_minutes == 1440
        assert len(history._history) == 0

        history_custom = HealthHistory(max_history_minutes=60)
        assert history_custom.max_history_minutes == 60

    @pytest.mark.asyncio
    async def test_rate_limited_snapshots(self, history):
        """Test that snapshots are rate limited."""
        score = HealthScore(
            overall_score=85.0,
            component_scores=[],
        )

        # First snapshot should be recorded
        await history.record_snapshot(score)
        assert len(history._history) == 1

        # Immediate second snapshot should be rate limited
        await history.record_snapshot(score)
        assert len(history._history) == 1  # Should still be 1

    @pytest.mark.asyncio
    async def test_get_recent_history_with_component_filter(self, history):
        """Test getting history filtered by component."""
        # Add snapshots with different components
        now = datetime.now(UTC)
        for i in range(3):
            snapshot = HealthSnapshot(
                score=80.0 + i,
                status="green",
                timestamp=now - timedelta(minutes=i),
                component_scores={
                    "redis": 90.0,
                    "influxdb": 85.0,
                },
            )
            history._history.append(snapshot)

        # Get all history
        all_history = await history.get_recent_history(minutes=10)
        assert len(all_history) == 3

        # Filter by component
        redis_history = await history.get_recent_history(minutes=10, component="redis")
        assert len(redis_history) == 3
        for h in redis_history:
            assert "redis" in h.component_scores

    @pytest.mark.asyncio
    async def test_get_recent_history_old_data_filtered(self, history):
        """Test that old data is filtered out."""
        now = datetime.now(UTC)

        # Add old snapshot
        old_snapshot = HealthSnapshot(
            score=80.0,
            status="green",
            timestamp=now - timedelta(minutes=20),  # 20 minutes ago
            component_scores={},
        )
        history._history.append(old_snapshot)

        # Add recent snapshot
        recent_snapshot = HealthSnapshot(
            score=90.0,
            status="green",
            timestamp=now - timedelta(minutes=2),  # 2 minutes ago
            component_scores={},
        )
        history._history.append(recent_snapshot)

        # Get history for last 10 minutes
        recent = await history.get_recent_history(minutes=10)
        assert len(recent) == 1  # Only recent snapshot
        assert recent[0].score == 90.0

    @pytest.mark.asyncio
    async def test_calculate_trend_stable(self, history):
        """Test stable trend calculation."""
        now = datetime.now(UTC)

        # Add stable scores
        for i in range(5):
            snapshot = HealthSnapshot(
                score=85.0,  # Same score
                status="green",
                timestamp=now - timedelta(hours=4 - i),
                component_scores={},
            )
            history._history.append(snapshot)

        trend = await history.calculate_trend(hours=24)
        assert trend is not None
        assert trend.direction == "stable"
        assert abs(trend.change_24h) < 5  # Minimal change

    @pytest.mark.asyncio
    async def test_calculate_trend_degrading(self, history):
        """Test degrading trend calculation."""
        now = datetime.now(UTC)

        # Add degrading scores
        for i in range(5):
            snapshot = HealthSnapshot(
                score=90.0 - i * 5,  # Decreasing
                status="yellow" if i > 2 else "green",
                timestamp=now - timedelta(hours=4 - i),
                component_scores={},
            )
            history._history.append(snapshot)

        trend = await history.calculate_trend(hours=24)
        assert trend is not None
        assert trend.direction == "degrading"
        assert trend.change_24h < -5  # Negative change

    @pytest.mark.asyncio
    async def test_get_alert_history_filtered(self, history):
        """Test alert history with filters."""
        # Record alerts
        await history.record_alert("redis", "warning", "Slow")
        await history.record_alert("redis", "critical", "Down")
        await history.record_alert("bybit", "warning", "Latency")

        # Filter by severity
        warnings = await history.get_alert_history(hours=1, severity="warning")
        assert len(warnings) == 2

        # Filter by component and severity
        redis_critical = await history.get_alert_history(
            hours=1, component="redis", severity="critical"
        )
        assert len(redis_critical) == 1
        assert redis_critical[0]["message"] == "Down"

    @pytest.mark.asyncio
    async def test_get_alert_history_old_alerts_filtered(self, history):
        """Test that old alerts are filtered."""
        # Add recent alert
        await history.record_alert("redis", "warning", "Recent")

        # Add old alert manually (simulating old data)
        old_alert = {
            "component": "bybit",
            "severity": "critical",
            "message": "Old",
            "timestamp": (datetime.now(UTC) - timedelta(hours=25)).isoformat(),
            "details": {},
        }
        history._alert_history.append(old_alert)

        # Get alerts for last 24 hours
        alerts = await history.get_alert_history(hours=24)
        assert len(alerts) == 1
        assert alerts[0]["message"] == "Recent"

    def test_get_stats_with_data(self, history):
        """Test stats with data."""
        now = datetime.now(UTC)

        # Add snapshots
        for i in range(3):
            snapshot = HealthSnapshot(
                score=80.0 + i,
                status="green",
                timestamp=now - timedelta(minutes=i),
                component_scores={},
            )
            history._history.append(snapshot)

        stats = history.get_stats()
        assert stats["total_snapshots"] == 3
        assert stats["oldest_snapshot"] is not None
        assert stats["newest_snapshot"] is not None

    def test_to_dict(self):
        """Test history to_dict."""
        # Use default history with larger maxlen
        history = HealthHistory()
        now = datetime.now(UTC)

        # Add more than 100 snapshots (to test the limit)
        for i in range(150):
            snapshot = HealthSnapshot(
                score=80.0,
                status="green",
                timestamp=now - timedelta(minutes=i),
                component_scores={},
            )
            history._history.append(snapshot)

        result = history.to_dict()
        assert len(result["snapshots"]) == 100  # Should be limited to 100
        assert "stats" in result
