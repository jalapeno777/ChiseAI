"""Tests for monitoring scripts."""

from unittest.mock import Mock, patch


class TestHourlyHealthCheck:
    """Test hourly health check formatting and parsing."""

    def test_format_hourly_message(self):
        """Test message formatting."""
        from scripts.monitoring.hourly_health_check import format_hourly_message

        scheduler = {"status": "✅", "detail": "Process active"}
        kill_switch = {"status": "✅", "detail": "Armed"}
        daily_loss = {"status": "✅", "detail": "Limit: 2.0%"}
        metrics = {"signals": 5, "outcomes": 3, "keys": 487}

        message = format_hourly_message(scheduler, kill_switch, daily_loss, metrics)

        assert "🔥 Burn-in Hourly Check" in message
        assert "Process active" in message
        assert "Armed" in message
        assert "Signals: 5" in message
        assert "Outcomes: 3" in message

    def test_check_scheduler_health_running(self):
        """Test scheduler check when running."""
        from scripts.monitoring.hourly_health_check import check_scheduler_health

        mock_output = "trading_activity --daemon"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(stdout=mock_output, returncode=0)
            result = check_scheduler_health()

        assert result["running"] is True
        assert result["status"] == "✅"

    def test_check_kill_switch_armed(self):
        """Test kill switch check when armed."""
        from scripts.monitoring.hourly_health_check import check_kill_switch

        mock_redis = Mock()
        mock_redis.hget.side_effect = lambda key, field: {
            ("bmad:chiseai:kill_switch", "enabled"): "1",
            ("bmad:chiseai:kill_switch", "triggered"): "0",
        }.get((key, field))

        result = check_kill_switch(mock_redis)

        assert result["armed"] is True
        assert result["status"] == "✅"

    def test_check_kill_switch_triggered(self):
        """Test kill switch check when triggered."""
        from scripts.monitoring.hourly_health_check import check_kill_switch

        mock_redis = Mock()
        mock_redis.hget.side_effect = lambda key, field: {
            ("bmad:chiseai:kill_switch", "enabled"): "1",
            ("bmad:chiseai:kill_switch", "triggered"): "1",
        }.get((key, field))

        result = check_kill_switch(mock_redis)

        assert result["armed"] is False
        assert result["status"] == "🚨"


class TestCheckpointGateAudit:
    """Test checkpoint audit formatting and parsing."""

    def test_format_checkpoint_message(self):
        """Test checkpoint message formatting."""
        from scripts.monitoring.checkpoint_gate_audit import format_checkpoint_message

        checks = [
            {"gate": "G1", "status": "✅ PASS", "detail": "Running"},
            {"gate": "G2", "status": "⚠️ CHECK", "detail": "No signals"},
            {"gate": "G3", "status": "✅ PASS", "detail": "3 outcomes"},
        ]

        message = format_checkpoint_message(checks)

        assert "📊 Burn-in Checkpoint" in message
        assert "2 ✅" in message  # pass count
        assert "1 ⚠️" in message  # check count
        assert "G1:" in message
        assert "G2:" in message

    def test_run_all_checks_redis_fail(self):
        """Test when Redis unavailable."""
        from scripts.monitoring.checkpoint_gate_audit import run_all_checks

        with patch("scripts.monitoring.checkpoint_gate_audit.get_redis") as mock_get:
            mock_get.return_value = None
            result = run_all_checks()

        assert len(result) == 1
        assert result[0]["gate"] == "ALL"
        assert "FAIL" in result[0]["status"]


class TestEnvironmentHandling:
    """Test environment variable handling."""

    def test_discord_config_missing(self):
        """Test behavior when Discord not configured."""
        import importlib
        import os

        # Clear env vars
        old_channel = os.environ.pop("DISCORD_DEVELOPMENT_CHANNEL_ID", None)
        old_token = os.environ.pop("DISCORD_BOT_TOKEN", None)

        try:
            # Need to reload module to pick up new env vars
            from scripts.monitoring import hourly_health_check

            importlib.reload(hourly_health_check)

            # Should use empty strings as defaults
            assert hourly_health_check.DISCORD_CHANNEL_ID == ""
            assert hourly_health_check.DISCORD_BOT_TOKEN == ""
        finally:
            # Restore
            if old_channel:
                os.environ["DISCORD_DEVELOPMENT_CHANNEL_ID"] = old_channel
            if old_token:
                os.environ["DISCORD_BOT_TOKEN"] = old_token
