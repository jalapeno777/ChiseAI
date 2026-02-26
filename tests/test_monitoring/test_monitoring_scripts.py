"""Tests for monitoring scripts."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone, timedelta


class TestPagerAlerts:
    """Test pager alert functionality."""

    def test_kill_switch_triggered(self):
        """Test kill switch detection when triggered."""
        import sys

        sys.path.insert(0, "/home/tacopants/projects/ChiseAI")
        from scripts.monitoring.pager_alerts import check_kill_switch_triggered

        mock_redis = Mock()
        mock_redis.hget.return_value = "1"  # Triggered

        result = check_kill_switch_triggered(mock_redis)
        assert result is not None
        assert "KILL SWITCH TRIGGERED" in result
        assert "CRITICAL" in result

    def test_kill_switch_not_triggered(self):
        """Test kill switch detection when not triggered."""
        import sys

        sys.path.insert(0, "/home/tacopants/projects/ChiseAI")
        from scripts.monitoring.pager_alerts import check_kill_switch_triggered

        mock_redis = Mock()
        mock_redis.hget.return_value = "0"  # Not triggered

        result = check_kill_switch_triggered(mock_redis)
        assert result is None

    def test_kill_switch_redis_error(self):
        """Test kill switch detection handles Redis errors gracefully."""
        import sys

        sys.path.insert(0, "/home/tacopants/projects/ChiseAI")
        from scripts.monitoring.pager_alerts import check_kill_switch_triggered

        mock_redis = Mock()
        mock_redis.hget.side_effect = Exception("Redis connection error")

        result = check_kill_switch_triggered(mock_redis)
        assert result is None

    def test_scheduler_down_detection(self):
        """Test scheduler down detection when down for >5 min."""
        import sys

        sys.path.insert(0, "/home/tacopants/projects/ChiseAI")
        from scripts.monitoring.pager_alerts import check_scheduler_down

        mock_redis = Mock()
        # Last seen 10 minutes ago
        last_seen = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        mock_redis.hget.return_value = last_seen

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(stdout="", returncode=0)
            result = check_scheduler_down(mock_redis)

        assert result is not None
        assert "Scheduler down" in result or "down for" in result.lower()

    def test_scheduler_running(self):
        """Test scheduler detection when running."""
        import sys

        sys.path.insert(0, "/home/tacopants/projects/ChiseAI")
        from scripts.monitoring.pager_alerts import check_scheduler_down

        mock_redis = Mock()

        with patch("subprocess.run") as mock_run:
            # Simulate scheduler process running
            mock_run.return_value = Mock(
                stdout="user 1234 0.0 0.1 12345 1234 ? S 00:00 trading_activity_scheduler",
                returncode=0,
            )
            result = check_scheduler_down(mock_redis)

        assert result is None


class TestSignalGrowthDetector:
    """Test signal growth detector."""

    def test_no_growth_warning(self):
        """Test warning when no growth for 2+ hours."""
        import sys

        sys.path.insert(0, "/home/tacopants/projects/ChiseAI")
        from scripts.monitoring.signal_growth_detector import check_signal_growth

        mock_redis = Mock()
        mock_redis.keys.return_value = ["signal1", "signal2"]  # 2 signals
        mock_redis.get.side_effect = [
            "2",  # last_count = 2
            (
                datetime.now(timezone.utc) - timedelta(hours=3)
            ).isoformat(),  # last_alert 3h ago
        ]

        result = check_signal_growth(mock_redis)
        assert result is not None
        assert "No signal growth" in result
        assert "2+" in result or "2" in result

    def test_growth_detected_no_warning(self):
        """Test no warning when growth detected."""
        import sys

        sys.path.insert(0, "/home/tacopants/projects/ChiseAI")
        from scripts.monitoring.signal_growth_detector import check_signal_growth

        mock_redis = Mock()
        mock_redis.keys.return_value = [
            "signal1",
            "signal2",
            "signal3",
        ]  # 3 signals now
        mock_redis.get.side_effect = [
            "2",  # last_count = 2
            None,  # No previous alert
        ]

        result = check_signal_growth(mock_redis)
        assert result is None

    def test_first_run_stores_count(self):
        """Test first run stores signal count."""
        import sys

        sys.path.insert(0, "/home/tacopants/projects/ChiseAI")
        from scripts.monitoring.signal_growth_detector import check_signal_growth

        mock_redis = Mock()
        mock_redis.keys.return_value = ["signal1", "signal2"]
        mock_redis.get.return_value = None  # No previous count

        result = check_signal_growth(mock_redis)
        assert result is None
        mock_redis.set.assert_called_with(
            "bmad:chiseai:monitoring:signal_growth:last_count", 2
        )


class TestDailyExecutiveSummary:
    """Test daily executive summary."""

    def test_calculate_pnl_with_trades(self):
        """Test PnL calculation with trades."""
        import sys

        sys.path.insert(0, "/home/tacopants/projects/ChiseAI")
        from scripts.monitoring.daily_executive_summary import calculate_pnl

        mock_redis = Mock()
        mock_redis.smembers.return_value = ["trade1", "trade2"]
        mock_redis.hgetall.side_effect = [
            {"entry_price": "100", "fill_price": "110", "direction": "LONG"},  # Win +10
            {
                "entry_price": "200",
                "fill_price": "190",
                "direction": "SHORT",
            },  # Win +10
        ]

        result = calculate_pnl(mock_redis)

        assert result["wins"] == 2
        assert result["losses"] == 0
        assert result["total_trades"] == 2
        assert result["win_rate"] == 100.0

    def test_calculate_pnl_no_trades(self):
        """Test PnL calculation with no trades."""
        import sys

        sys.path.insert(0, "/home/tacopants/projects/ChiseAI")
        from scripts.monitoring.daily_executive_summary import calculate_pnl

        mock_redis = Mock()
        mock_redis.smembers.return_value = set()

        result = calculate_pnl(mock_redis)

        assert result["total_trades"] == 0
        assert result["win_rate"] == 0

    def test_format_executive_summary(self):
        """Test summary formatting."""
        import sys

        sys.path.insert(0, "/home/tacopants/projects/ChiseAI")
        from scripts.monitoring.daily_executive_summary import format_executive_summary

        pnl = {
            "pnl": 1234.56,
            "wins": 10,
            "losses": 5,
            "win_rate": 66.7,
            "total_trades": 15,
        }
        drawdown = 100.0
        ece = "Within bounds"
        incidents = 2

        result = format_executive_summary(pnl, drawdown, ece, incidents)

        assert "Daily Executive Summary" in result
        assert "$1,234.56" in result or "1234.56" in result
        assert "66.7%" in result or "66.70%" in result
        assert "Within bounds" in result
        assert "2" in result


class TestBurninCompletion:
    """Test burn-in completion."""

    def test_format_completion_message(self):
        """Test completion message formatting."""
        import sys

        sys.path.insert(0, "/home/tacopants/projects/ChiseAI")
        from scripts.monitoring.burnin_completion import format_completion_message

        result = format_completion_message()

        assert "BURN-IN COMPLETE" in result
        assert "24-Hour Burn-in" in result
        assert "All gates validated" in result
        assert "Bybit demo trading" in result
        assert "Next Steps" in result


class TestEnvironmentVariables:
    """Test environment variable handling."""

    def test_default_redis_host(self):
        """Test default Redis host is host.docker.internal."""
        import sys

        sys.path.insert(0, "/home/tacopants/projects/ChiseAI")

        # Clear env vars to test defaults
        with patch.dict("os.environ", {}, clear=True):
            # Re-import to get fresh defaults
            if "scripts.monitoring.pager_alerts" in sys.modules:
                del sys.modules["scripts.monitoring.pager_alerts"]
            from scripts.monitoring.pager_alerts import REDIS_HOST, REDIS_PORT

            assert REDIS_HOST == "host.docker.internal"
            assert REDIS_PORT == 6380

    def test_env_override(self):
        """Test environment variables can be overridden."""
        import sys

        sys.path.insert(0, "/home/tacopants/projects/ChiseAI")

        with patch.dict(
            "os.environ",
            {"REDIS_HOST": "custom.redis.host", "REDIS_PORT": "1234"},
            clear=True,
        ):
            if "scripts.monitoring.pager_alerts" in sys.modules:
                del sys.modules["scripts.monitoring.pager_alerts"]
            from scripts.monitoring.pager_alerts import REDIS_HOST, REDIS_PORT

            assert REDIS_HOST == "custom.redis.host"
            assert REDIS_PORT == 1234
