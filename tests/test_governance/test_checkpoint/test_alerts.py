"""Tests for checkpoint alert system.

Tests the ActionableZeroAlert class and alert integration with gates.

Story: BATCH3-ACTIONABLE-ZERO-002
"""

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from src.governance.checkpoint.alerts import ActionableZeroAlert, AlertResult
from src.governance.checkpoint.gates import GateChecker


class TestAlertResult:
    """Tests for AlertResult dataclass."""

    def test_alert_result_creation(self):
        """Test creating an AlertResult."""
        now = datetime.now(UTC)
        result = AlertResult(
            alert_name="actionable_zero",
            triggered=True,
            suppressed=False,
            message="Test alert",
            severity="CRITICAL",
            metadata={"key": "value"},
            timestamp=now,
        )

        assert result.alert_name == "actionable_zero"
        assert result.triggered is True
        assert result.suppressed is False
        assert result.message == "Test alert"
        assert result.severity == "CRITICAL"
        assert result.metadata == {"key": "value"}
        assert result.timestamp == now

    def test_alert_result_default_timestamp(self):
        """Test AlertResult with default timestamp."""
        before = datetime.now(UTC)
        result = AlertResult(
            alert_name="actionable_zero",
            triggered=False,
        )
        after = datetime.now(UTC)

        assert result.timestamp is not None
        assert before <= result.timestamp  # type: ignore
        assert result.timestamp <= after

    def test_alert_result_defaults(self):
        """Test AlertResult default values."""
        result = AlertResult(
            alert_name="actionable_zero",
            triggered=True,
        )

        assert result.suppressed is False
        assert result.message == ""
        assert result.severity == "INFO"
        assert result.metadata == {}


class TestActionableZeroAlertInitialization:
    """Tests for ActionableZeroAlert initialization."""

    def test_default_initialization(self):
        """Test ActionableZeroAlert with default values."""
        alert = ActionableZeroAlert()

        assert alert._redis is None
        assert alert._redis_host is not None
        assert alert._redis_port is not None
        assert alert._consecutive_windows == 3
        assert alert._suppression_hours == 1

    def test_with_redis_client(self, mock_redis_client):
        """Test ActionableZeroAlert with provided Redis client."""
        alert = ActionableZeroAlert(redis_client=mock_redis_client)

        assert alert._redis == mock_redis_client

    def test_with_custom_thresholds(self):
        """Test ActionableZeroAlert with custom thresholds."""
        alert = ActionableZeroAlert(
            consecutive_windows=5,
            suppression_hours=2,
        )

        assert alert._consecutive_windows == 5
        assert alert._suppression_hours == 2

    def test_with_env_vars(self, monkeypatch):
        """Test ActionableZeroAlert with environment variables."""
        monkeypatch.setenv("ACTIONABLE_ZERO_CONSECUTIVE_WINDOWS", "4")
        monkeypatch.setenv("ACTIONABLE_ZERO_SUPPRESSION_HOURS", "2")

        alert = ActionableZeroAlert()

        assert alert._consecutive_windows == 4
        assert alert._suppression_hours == 2


class TestActionableZeroAlertStateManagement:
    """Tests for ActionableZeroAlert state management."""

    def test_load_state_empty(self, mock_redis_client):
        """Test loading state when no state exists."""
        mock_redis_client.hgetall.return_value = {}

        alert = ActionableZeroAlert(redis_client=mock_redis_client)
        state = alert._load_state()

        assert state == {}

    def test_load_state_with_data(self, mock_redis_client):
        """Test loading state with existing data."""
        mock_redis_client.hgetall.return_value = {
            "consecutive_windows": "2",
            "last_alert_time": "2024-03-11T12:00:00+00:00",
            "window_signals": "[5, 3, 4]",
        }

        alert = ActionableZeroAlert(redis_client=mock_redis_client)
        state = alert._load_state()

        assert state["consecutive_windows"] == 2
        assert state["last_alert_time"] == "2024-03-11T12:00:00+00:00"
        assert state["window_signals"] == [5, 3, 4]

    def test_load_state_invalid_json(self, mock_redis_client):
        """Test loading state with invalid JSON."""
        mock_redis_client.hgetall.return_value = {
            "window_signals": "invalid json",
        }

        alert = ActionableZeroAlert(redis_client=mock_redis_client)
        state = alert._load_state()

        assert state["window_signals"] == []

    def test_save_state(self, mock_redis_client):
        """Test saving state."""
        alert = ActionableZeroAlert(redis_client=mock_redis_client)

        state = {
            "consecutive_windows": 2,
            "window_signals": [5, 3],
            "last_check_time": "2024-03-11T12:00:00+00:00",
        }

        result = alert._save_state(state)

        assert result is True
        mock_redis_client.hset.assert_called_once()
        call_args = mock_redis_client.hset.call_args
        assert call_args[0][0] == ActionableZeroAlert.REDIS_KEY
        # Check that window_signals was converted to JSON
        assert "window_signals" in call_args[1]["mapping"]

    def test_get_state(self, mock_redis_client):
        """Test get_state public method."""
        mock_redis_client.hgetall.return_value = {
            "consecutive_windows": "3",
            "last_alert_time": "2024-03-11T12:00:00+00:00",
        }

        alert = ActionableZeroAlert(redis_client=mock_redis_client)
        state = alert.get_state()

        assert state["consecutive_windows"] == 3

    def test_reset_state(self, mock_redis_client):
        """Test reset_state method."""
        alert = ActionableZeroAlert(redis_client=mock_redis_client)

        result = alert.reset_state()

        assert result is True
        mock_redis_client.delete.assert_called_once_with(ActionableZeroAlert.REDIS_KEY)

    def test_manual_suppression_clear(self, mock_redis_client):
        """Test manual_suppression_clear method."""
        mock_redis_client.hgetall.return_value = {
            "consecutive_windows": "3",
            "last_alert_time": "2024-03-11T12:00:00+00:00",
        }

        alert = ActionableZeroAlert(redis_client=mock_redis_client)
        result = alert.manual_suppression_clear()

        assert result is True
        # Verify last_alert_time was removed from saved state
        call_args = mock_redis_client.hset.call_args
        assert "last_alert_time" not in call_args[1]["mapping"]


class TestActionableZeroAlertCheckLogic:
    """Tests for ActionableZeroAlert check logic."""

    def test_check_no_signals_no_actionable(self, mock_redis_client):
        """Test check when no signals and no actionable (healthy idle)."""
        mock_redis_client.hgetall.return_value = {}

        alert = ActionableZeroAlert(redis_client=mock_redis_client)
        result = alert.check(signals_15m=0, actionable_15m=0)

        assert result.triggered is False
        assert result.severity == "INFO"
        assert "not present" in result.message

    def test_check_signals_with_actionable(self, mock_redis_client):
        """Test check when signals and actionable present (healthy)."""
        mock_redis_client.hgetall.return_value = {
            "consecutive_windows": "2",
            "window_signals": "[5, 3]",
        }

        alert = ActionableZeroAlert(redis_client=mock_redis_client)
        result = alert.check(signals_15m=5, actionable_15m=2)

        assert result.triggered is False
        assert result.severity == "INFO"
        assert result.metadata["previous_consecutive"] == 2
        assert result.metadata["consecutive_windows"] == 0

    def test_check_first_actionable_zero_window(self, mock_redis_client):
        """Test check on first actionable-zero window."""
        mock_redis_client.hgetall.return_value = {}

        alert = ActionableZeroAlert(redis_client=mock_redis_client)
        result = alert.check(signals_15m=5, actionable_15m=0)

        assert result.triggered is False
        assert result.severity == "INFO"
        assert result.metadata["consecutive_windows"] == 1
        assert "count: 1/3" in result.message

    def test_check_second_actionable_zero_window(self, mock_redis_client):
        """Test check on second consecutive actionable-zero window."""
        mock_redis_client.hgetall.return_value = {
            "consecutive_windows": "1",
            "window_signals": "[5]",
        }

        alert = ActionableZeroAlert(redis_client=mock_redis_client)
        result = alert.check(signals_15m=3, actionable_15m=0)

        assert result.triggered is False
        assert result.severity == "INFO"
        assert result.metadata["consecutive_windows"] == 2
        assert "count: 2/3" in result.message

    def test_check_third_actionable_zero_window_triggers_alert(self, mock_redis_client):
        """Test check on third consecutive actionable-zero window triggers alert."""
        mock_redis_client.hgetall.return_value = {
            "consecutive_windows": "2",
            "window_signals": "[5, 3]",
        }

        alert = ActionableZeroAlert(redis_client=mock_redis_client)
        result = alert.check(signals_15m=4, actionable_15m=0)

        assert result.triggered is True
        assert result.suppressed is False
        assert result.severity == "CRITICAL"
        assert "🚨 ACTIONABLE-ZERO ALERT" in result.message
        assert "45+ minutes" in result.message
        assert result.metadata["consecutive_windows"] == 3
        assert result.metadata["duration_minutes"] == 45

    def test_check_alert_suppression(self, mock_redis_client):
        """Test that alert is suppressed when already fired recently."""
        recent_time = (datetime.now(UTC) - timedelta(minutes=30)).isoformat()
        mock_redis_client.hgetall.return_value = {
            "consecutive_windows": "3",
            "window_signals": "[5, 3, 4]",
            "last_alert_time": recent_time,
        }

        alert = ActionableZeroAlert(redis_client=mock_redis_client)
        result = alert.check(signals_15m=6, actionable_15m=0)

        assert result.triggered is True
        assert result.suppressed is True
        assert result.severity == "WARNING"
        assert "suppressed" in result.message

    def test_check_alert_after_suppression_window(self, mock_redis_client):
        """Test that alert fires again after suppression window."""
        old_time = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
        mock_redis_client.hgetall.return_value = {
            "consecutive_windows": "3",
            "window_signals": "[5, 3, 4]",
            "last_alert_time": old_time,
        }

        alert = ActionableZeroAlert(redis_client=mock_redis_client)
        result = alert.check(signals_15m=6, actionable_15m=0)

        assert result.triggered is True
        assert result.suppressed is False
        assert result.severity == "CRITICAL"

    def test_check_reset_on_actionable_signals(self, mock_redis_client):
        """Test that consecutive counter resets when actionable signals detected."""
        mock_redis_client.hgetall.return_value = {
            "consecutive_windows": "2",
            "window_signals": "[5, 3]",
        }

        alert = ActionableZeroAlert(redis_client=mock_redis_client)
        result = alert.check(signals_15m=5, actionable_15m=2)

        assert result.triggered is False
        assert result.metadata["consecutive_windows"] == 0
        assert result.metadata["previous_consecutive"] == 2

    def test_check_window_signals_tracking(self, mock_redis_client):
        """Test that window signals are tracked correctly."""
        mock_redis_client.hgetall.return_value = {
            "consecutive_windows": "1",
            "window_signals": "[5]",
        }

        alert = ActionableZeroAlert(redis_client=mock_redis_client)
        result = alert.check(signals_15m=3, actionable_15m=0)

        assert result.metadata["consecutive_windows"] == 2
        # Verify state was saved with updated window_signals
        call_args = mock_redis_client.hset.call_args
        saved_state = call_args[1]["mapping"]
        assert "window_signals" in saved_state
        # Parse the JSON to verify it was updated
        signals = json.loads(saved_state["window_signals"])
        assert len(signals) == 2
        assert signals[-1] == 3

    def test_check_window_signals_limit(self, mock_redis_client):
        """Test that window signals list is limited to last 10 entries."""
        mock_redis_client.hgetall.return_value = {
            "consecutive_windows": "10",
            "window_signals": json.dumps([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]),
        }

        alert = ActionableZeroAlert(redis_client=mock_redis_client)
        result = alert.check(signals_15m=11, actionable_15m=0)

        # Verify state was saved with trimmed window_signals
        call_args = mock_redis_client.hset.call_args
        saved_state = call_args[1]["mapping"]
        signals = json.loads(saved_state["window_signals"])
        assert len(signals) == 10
        assert signals[0] == 2  # First element removed
        assert signals[-1] == 11  # New element added


class TestActionableZeroAlertSuppression:
    """Tests for ActionableZeroAlert suppression logic."""

    def test_is_suppressed_no_last_alert(self, mock_redis_client):
        """Test suppression check when no last alert time."""
        alert = ActionableZeroAlert(redis_client=mock_redis_client)
        state = {"consecutive_windows": "3"}

        assert alert._is_suppressed(state) is False

    def test_is_suppressed_within_window(self, mock_redis_client):
        """Test suppression when within suppression window."""
        recent_time = (datetime.now(UTC) - timedelta(minutes=30)).isoformat()
        alert = ActionableZeroAlert(redis_client=mock_redis_client)
        state = {"last_alert_time": recent_time}

        assert alert._is_suppressed(state) is True

    def test_is_suppressed_outside_window(self, mock_redis_client):
        """Test no suppression when outside suppression window."""
        old_time = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
        alert = ActionableZeroAlert(redis_client=mock_redis_client)
        state = {"last_alert_time": old_time}

        assert alert._is_suppressed(state) is False

    def test_is_suppressed_exactly_at_window_boundary(self, mock_redis_client):
        """Test suppression at exact window boundary (should not suppress)."""
        boundary_time = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        alert = ActionableZeroAlert(redis_client=mock_redis_client)
        state = {"last_alert_time": boundary_time}

        assert alert._is_suppressed(state) is False

    def test_is_suppressed_invalid_timestamp(self, mock_redis_client):
        """Test suppression with invalid timestamp."""
        alert = ActionableZeroAlert(redis_client=mock_redis_client)
        state = {"last_alert_time": "invalid-timestamp"}

        assert alert._is_suppressed(state) is False


class TestActionableZeroAlertMessage:
    """Tests for ActionableZeroAlert message formatting."""

    def test_build_alert_message(self, mock_redis_client):
        """Test alert message formatting."""
        alert = ActionableZeroAlert(redis_client=mock_redis_client)
        message = alert._build_alert_message(
            signals_15m=10,
            consecutive_windows=3,
            duration_minutes=45,
        )

        assert "🚨 ACTIONABLE-ZERO ALERT" in message
        assert "Signals generated: 10" in message
        assert "Actionable signals: 0" in message
        assert "45+ minutes" in message
        assert "Confidence thresholds too high" in message
        assert "Market conditions not matching strategy criteria" in message
        assert "Signal filtering logic issue" in message

    def test_build_alert_message_extended_duration(self, mock_redis_client):
        """Test alert message with extended duration."""
        alert = ActionableZeroAlert(redis_client=mock_redis_client)
        message = alert._build_alert_message(
            signals_15m=25,
            consecutive_windows=5,
            duration_minutes=75,
        )

        assert "Signals generated: 25" in message
        assert "75+ minutes" in message


class TestGateCheckerActionableZeroIntegration:
    """Tests for GateChecker integration with ActionableZeroAlert."""

    def test_check_actionable_zero_no_redis(self):
        """Test actionable-zero check when Redis unavailable."""
        checker = GateChecker()
        with patch.object(checker, "_get_redis", return_value=None):
            result = checker.check_actionable_zero_alert()

        assert result.gate == "AZ"
        assert result.status == GateChecker.STATUS_FAIL
        assert "Redis unavailable" in result.detail

    def test_check_actionable_zero_healthy(self, mock_redis_client):
        """Test actionable-zero check when healthy."""
        mock_redis_client.hgetall.return_value = {
            "signals_15m": "5",
            "actionable_15m": "2",
        }

        checker = GateChecker(redis_client=mock_redis_client)
        result = checker.check_actionable_zero_alert()

        assert result.gate == "AZ"
        assert result.status == GateChecker.STATUS_PASS
        assert "No actionable-zero" in result.detail

    def test_check_actionable_zero_building(self, mock_redis_client):
        """Test actionable-zero check when condition building up (1-2 windows)."""
        # Pre-populate alert state with 1 consecutive window
        # After this check with signals > 0 and actionable = 0, it becomes 2 windows
        mock_redis_client.hgetall.side_effect = [
            {  # First call for heartbeat
                "signals_15m": "5",
                "actionable_15m": "0",
            },
            {  # Second call for alert state
                "consecutive_windows": "1",
                "window_signals": "[5]",
            },
        ]

        checker = GateChecker(redis_client=mock_redis_client)
        result = checker.check_actionable_zero_alert()

        assert result.gate == "AZ"
        assert result.status == GateChecker.STATUS_CHECK
        assert "2/3" in result.detail

    def test_check_actionable_zero_alert_triggered(self, mock_redis_client):
        """Test actionable-zero check when alert triggered."""
        mock_redis_client.hgetall.side_effect = [
            {  # First call for heartbeat
                "signals_15m": "5",
                "actionable_15m": "0",
            },
            {  # Second call for alert state
                "consecutive_windows": "3",
                "window_signals": "[5, 3, 4]",
            },
        ]

        checker = GateChecker(redis_client=mock_redis_client)
        result = checker.check_actionable_zero_alert()

        assert result.gate == "AZ"
        assert result.status == GateChecker.STATUS_ALERT
        assert "🚨" in result.detail

    def test_check_actionable_zero_suppressed(self, mock_redis_client):
        """Test actionable-zero check when alert suppressed."""
        recent_time = (datetime.now(UTC) - timedelta(minutes=30)).isoformat()
        mock_redis_client.hgetall.side_effect = [
            {  # First call for heartbeat
                "signals_15m": "5",
                "actionable_15m": "0",
            },
            {  # Second call for alert state
                "consecutive_windows": "3",
                "window_signals": "[5, 3, 4]",
                "last_alert_time": recent_time,
            },
        ]

        checker = GateChecker(redis_client=mock_redis_client)
        result = checker.check_actionable_zero_alert()

        assert result.gate == "AZ"
        assert result.status == GateChecker.STATUS_CHECK
        assert "suppressed" in result.detail

    def test_check_actionable_zero_exception(self, mock_redis_client):
        """Test actionable-zero check when exception occurs."""
        mock_redis_client.hgetall.side_effect = Exception("Redis error")

        checker = GateChecker(redis_client=mock_redis_client)
        result = checker.check_actionable_zero_alert()

        assert result.gate == "AZ"
        assert result.status == GateChecker.STATUS_FAIL
        assert "Exception" in result.detail


class TestActionableZeroAlertRedisErrors:
    """Tests for ActionableZeroAlert Redis error handling."""

    def test_load_state_redis_error(self, mock_redis_client):
        """Test load_state when Redis raises exception."""
        mock_redis_client.hgetall.side_effect = Exception("Connection error")

        alert = ActionableZeroAlert(redis_client=mock_redis_client)
        state = alert._load_state()

        assert state == {}

    def test_save_state_redis_error(self, mock_redis_client):
        """Test save_state when Redis raises exception."""
        mock_redis_client.hset.side_effect = Exception("Connection error")

        alert = ActionableZeroAlert(redis_client=mock_redis_client)
        result = alert._save_state({"test": "data"})

        assert result is False

    def test_check_no_redis_connection(self):
        """Test check when Redis is not available."""
        alert = ActionableZeroAlert()
        with patch.object(alert, "_get_redis", return_value=None):
            result = alert.check(signals_15m=5, actionable_15m=0)

        # Should still return a result, but state won't persist
        assert isinstance(result, AlertResult)
        assert result.alert_name == "actionable_zero"

    def test_reset_state_redis_error(self, mock_redis_client):
        """Test reset_state when Redis raises exception."""
        mock_redis_client.delete.side_effect = Exception("Connection error")

        alert = ActionableZeroAlert(redis_client=mock_redis_client)
        result = alert.reset_state()

        assert result is False
