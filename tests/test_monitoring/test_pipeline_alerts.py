"""Tests for pipeline alerting system."""

from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest
from scripts.monitoring.pipeline_alerts import AlertSeverity, PipelineAlertManager


class TestPipelineAlertManager:
    """Test pipeline alert manager."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        return Mock()

    @pytest.fixture
    def alert_manager(self, mock_redis):
        """Create alert manager with mock Redis."""
        return PipelineAlertManager(redis_client=mock_redis)

    def test_stale_pipeline_alert(self, alert_manager, mock_redis):
        """Test alert is sent when pipeline is stale."""
        # Arrange
        mock_redis.hgetall.return_value = {
            "pipeline_status": "stale",
            "signals_15m": "0",
            "consumer_backlog": "0",
            "latest_signal_age_m": "10.5",
        }

        with patch.object(alert_manager, "_send_alert") as mock_send:
            # Act
            alert_manager.check_and_alert()

            # Assert
            mock_send.assert_called_once()
            call_args = mock_send.call_args
            assert call_args[1]["severity"] == AlertSeverity.CRITICAL
            assert "Pipeline Stale" in call_args[1]["title"]

    def test_recovery_alert(self, alert_manager, mock_redis):
        """Test recovery alert sent when pipeline becomes healthy."""
        # Arrange - was stale, now healthy
        mock_redis.hgetall.side_effect = [
            {  # heartbeat
                "pipeline_status": "healthy",
                "signals_15m": "10",
                "consumer_backlog": "0",
                "latest_signal_age_m": "2.0",
            },
            {  # last alert state
                "last_alert_type": "stale_pipeline",
                "last_alert_time": (datetime.now() - timedelta(minutes=10)).isoformat(),
            },
        ]

        with patch.object(alert_manager, "_send_alert") as mock_send:
            # Act
            alert_manager.check_and_alert()

            # Assert
            mock_send.assert_called_once()
            call_args = mock_send.call_args
            assert call_args[1]["severity"] == AlertSeverity.INFO
            assert "Recovered" in call_args[1]["title"]

    def test_alert_cooldown(self, alert_manager, mock_redis):
        """Test alerts respect cooldown period."""
        # Arrange
        mock_redis.hgetall.return_value = {
            "pipeline_status": "stale",
            "signals_15m": "0",
            "consumer_backlog": "0",
            "latest_signal_age_m": "10.0",
        }

        alert_manager.last_alert_time = datetime.now() - timedelta(minutes=5)

        with patch.object(alert_manager, "_send_alert") as mock_send:
            # Act
            alert_manager.check_and_alert()

            # Assert - should not alert due to cooldown
            mock_send.assert_not_called()

    def test_high_backlog_alert(self, alert_manager, mock_redis):
        """Test alert sent for high consumer backlog."""
        # Arrange
        mock_redis.hgetall.return_value = {
            "pipeline_status": "healthy",
            "signals_15m": "5",
            "consumer_backlog": "15",
            "latest_signal_age_m": "2.0",
        }

        with patch.object(alert_manager, "_send_alert") as mock_send:
            # Act
            alert_manager.check_and_alert()

            # Assert - should send backlog alert
            assert mock_send.call_count == 1
            call_args = mock_send.call_args
            assert call_args[1]["severity"] == AlertSeverity.WARNING
            assert "Backlog" in call_args[1]["title"]

    def test_no_alert_when_healthy_and_no_previous_alert(
        self, alert_manager, mock_redis
    ):
        """Test no alert when healthy and no previous alert state."""
        # Arrange
        mock_redis.hgetall.side_effect = [
            {  # heartbeat
                "pipeline_status": "healthy",
                "signals_15m": "10",
                "consumer_backlog": "0",
                "latest_signal_age_m": "2.0",
            },
            {},  # no previous alert state
        ]

        with patch.object(alert_manager, "_send_alert") as mock_send:
            # Act
            alert_manager.check_and_alert()

            # Assert - no alert should be sent
            mock_send.assert_not_called()

    def test_stale_threshold_respected(self, alert_manager, mock_redis):
        """Test stale alert only triggers above threshold."""
        # Arrange - stale but below threshold
        mock_redis.hgetall.return_value = {
            "pipeline_status": "stale",
            "signals_15m": "0",
            "consumer_backlog": "0",
            "latest_signal_age_m": "3.0",  # Below 5 minute threshold
        }

        with patch.object(alert_manager, "_send_alert") as mock_send:
            # Act
            alert_manager.check_and_alert()

            # Assert - should not alert below threshold
            mock_send.assert_not_called()

    def test_record_alert_state(self, alert_manager, mock_redis):
        """Test alert state is recorded in Redis."""
        # Act
        alert_manager._record_alert("stale_pipeline")

        # Assert
        mock_redis.hset.assert_called_once()
        call_args = mock_redis.hset.call_args
        assert call_args[1]["mapping"]["last_alert_type"] == "stale_pipeline"

    def test_get_last_alert_state(self, alert_manager, mock_redis):
        """Test retrieval of last alert state."""
        # Arrange
        mock_redis.hgetall.return_value = {
            "last_alert_type": "stale_pipeline",
            "last_alert_time": datetime.now().isoformat(),
        }

        # Act
        result = alert_manager._get_last_alert_state()

        # Assert
        assert result == "stale_pipeline"

    def test_send_alert_logs_to_logger(self, alert_manager):
        """Test alert is logged appropriately."""
        with patch("scripts.monitoring.pipeline_alerts.logger") as mock_logger:
            # Act
            alert_manager._send_alert(
                severity=AlertSeverity.CRITICAL,
                title="Test Alert",
                message="Test message",
                fields={"key": "value"},
            )

            # Assert
            mock_logger.error.assert_called_once()
            assert "ALERT [CRITICAL]" in mock_logger.error.call_args[0][0]

    def test_no_heartbeat_found_logs_warning(self, alert_manager, mock_redis):
        """Test warning logged when no heartbeat found."""
        # Arrange
        mock_redis.hgetall.return_value = {}

        with patch("scripts.monitoring.pipeline_alerts.logger") as mock_logger:
            # Act
            alert_manager.check_and_alert()

            # Assert
            mock_logger.warning.assert_called_once_with("No heartbeat found")

    def test_error_handling_graceful(self, alert_manager, mock_redis):
        """Test errors are handled gracefully."""
        # Arrange
        mock_redis.hgetall.side_effect = Exception("Redis error")

        with patch("scripts.monitoring.pipeline_alerts.logger") as mock_logger:
            # Act - should not raise
            alert_manager.check_and_alert()

            # Assert
            mock_logger.exception.assert_called_once()
