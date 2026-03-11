"""Tests for kill-switch bootstrap module.

For ST-AUTONOMY-BURNIN-001-A: Kill-Switch Bootstrap/Initialization Guard
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from execution.kill_switch.bootstrap import (
    DEFAULT_ENABLED,
    DEFAULT_TRIGGERED,
    ENABLED_FIELD,
    INITIALIZED_AT_FIELD,
    INITIALIZED_BY_FIELD,
    TRIGGERED_FIELD,
    _get_redis_client,
    bootstrap_kill_switch,
    get_kill_switch_status,
    is_kill_switch_initialized,
)


class TestBootstrapKillSwitch:
    """Test bootstrap_kill_switch function."""

    def test_initialization_creates_correct_keys(self):
        """Test that bootstrap creates all required Redis keys."""
        mock_redis = MagicMock()
        mock_redis.hget.return_value = None  # Not initialized yet

        result = bootstrap_kill_switch(mock_redis)

        assert result is True
        # Should call hsetnx for each field
        assert mock_redis.hsetnx.call_count == 4

        # Check that all required fields are set
        calls = mock_redis.hsetnx.call_args_list
        fields_set = {call[0][1] for call in calls}
        assert ENABLED_FIELD in fields_set
        assert TRIGGERED_FIELD in fields_set
        assert INITIALIZED_AT_FIELD in fields_set
        assert INITIALIZED_BY_FIELD in fields_set

    def test_initialization_values(self):
        """Test that bootstrap sets correct default values."""
        mock_redis = MagicMock()
        mock_redis.hget.return_value = None  # Not initialized yet

        bootstrap_kill_switch(mock_redis)

        # Find the calls for enabled and triggered
        calls = mock_redis.hsetnx.call_args_list
        values = {call[0][1]: call[0][2] for call in calls}

        assert values[ENABLED_FIELD] == DEFAULT_ENABLED  # "1"
        assert values[TRIGGERED_FIELD] == DEFAULT_TRIGGERED  # "0"
        assert values[INITIALIZED_BY_FIELD] == "bootstrap"
        # initialized_at should be a timestamp (ISO format)
        assert isinstance(values[INITIALIZED_AT_FIELD], str)
        assert "T" in values[INITIALIZED_AT_FIELD]  # ISO format has 'T'

    def test_idempotency_already_initialized(self):
        """Test that bootstrap is idempotent - doesn't overwrite existing keys."""
        mock_redis = MagicMock()
        # Simulate already initialized
        mock_redis.hget.side_effect = lambda key, field: {
            ENABLED_FIELD: "1",
            TRIGGERED_FIELD: "0",
        }.get(field)

        result = bootstrap_kill_switch(mock_redis)

        assert result is True
        # Should NOT call hsetnx since already initialized
        mock_redis.hsetnx.assert_not_called()

    def test_idempotency_partial_initialization(self):
        """Test bootstrap handles partial initialization gracefully."""
        mock_redis = MagicMock()
        # Simulate partial initialization (enabled set but not triggered)
        mock_redis.hget.side_effect = lambda key, field: {
            ENABLED_FIELD: "1",
            TRIGGERED_FIELD: None,
        }.get(field)

        result = bootstrap_kill_switch(mock_redis)

        # Should still try to initialize (since not fully initialized)
        assert result is True
        # Should call hsetnx for fields that don't exist
        mock_redis.hsetnx.assert_called()

    def test_redis_connection_failure(self):
        """Test bootstrap handles Redis connection failure gracefully."""
        mock_redis = MagicMock()
        # Simulate failure during the hsetnx calls (after is_kill_switch_initialized returns False)
        mock_redis.hget.return_value = None  # Not initialized
        mock_redis.hsetnx.side_effect = Exception("Connection refused")

        result = bootstrap_kill_switch(mock_redis)

        assert result is False

    def test_uses_provided_redis_client(self):
        """Test that bootstrap uses provided Redis client."""
        mock_redis = MagicMock()
        mock_redis.hget.return_value = None

        with patch(
            "execution.kill_switch.bootstrap._get_redis_client"
        ) as mock_get_client:
            bootstrap_kill_switch(mock_redis)
            # Should NOT try to create a new client
            mock_get_client.assert_not_called()

    def test_creates_own_client_when_none_provided(self):
        """Test that bootstrap creates Redis client when none provided."""
        mock_redis = MagicMock()
        mock_redis.hget.return_value = None

        with patch(
            "execution.kill_switch.bootstrap._get_redis_client", return_value=mock_redis
        ) as mock_get_client:
            bootstrap_kill_switch(None)
            # Should try to create a new client
            mock_get_client.assert_called_once()


class TestIsKillSwitchInitialized:
    """Test is_kill_switch_initialized function."""

    def test_returns_true_when_initialized(self):
        """Test returns True when both enabled and triggered fields exist."""
        mock_redis = MagicMock()
        mock_redis.hget.side_effect = lambda key, field: {
            ENABLED_FIELD: "1",
            TRIGGERED_FIELD: "0",
        }.get(field)

        result = is_kill_switch_initialized(mock_redis)

        assert result is True

    def test_returns_false_when_not_initialized(self):
        """Test returns False when fields don't exist."""
        mock_redis = MagicMock()
        mock_redis.hget.return_value = None

        result = is_kill_switch_initialized(mock_redis)

        assert result is False

    def test_returns_false_when_partially_initialized(self):
        """Test returns False when only one field exists."""
        mock_redis = MagicMock()
        mock_redis.hget.side_effect = lambda key, field: {
            ENABLED_FIELD: "1",
            TRIGGERED_FIELD: None,
        }.get(field)

        result = is_kill_switch_initialized(mock_redis)

        assert result is False

    def test_returns_false_on_redis_error(self):
        """Test returns False when Redis connection fails."""
        mock_redis = MagicMock()
        mock_redis.hget.side_effect = Exception("Connection refused")

        result = is_kill_switch_initialized(mock_redis)

        assert result is False


class TestGetKillSwitchStatus:
    """Test get_kill_switch_status function."""

    def test_returns_full_status_when_initialized(self):
        """Test returns complete status when kill-switch is initialized."""
        mock_redis = MagicMock()
        mock_redis.hgetall.return_value = {
            ENABLED_FIELD: "1",
            TRIGGERED_FIELD: "0",
            INITIALIZED_AT_FIELD: "2024-01-15T12:00:00+00:00",
            INITIALIZED_BY_FIELD: "bootstrap",
        }

        status = get_kill_switch_status(mock_redis)

        assert status["initialized"] is True
        assert status["enabled"] is True
        assert status["triggered"] is False
        assert status["initialized_at"] == "2024-01-15T12:00:00+00:00"
        assert status["initialized_by"] == "bootstrap"
        assert status["error"] is None

    def test_returns_status_when_disabled(self):
        """Test returns correct status when kill-switch is disabled."""
        mock_redis = MagicMock()
        mock_redis.hgetall.return_value = {
            ENABLED_FIELD: "0",
            TRIGGERED_FIELD: "0",
            INITIALIZED_AT_FIELD: "2024-01-15T12:00:00+00:00",
            INITIALIZED_BY_FIELD: "bootstrap",
        }

        status = get_kill_switch_status(mock_redis)

        assert status["initialized"] is True
        assert status["enabled"] is False
        assert status["triggered"] is False

    def test_returns_status_when_triggered(self):
        """Test returns correct status when kill-switch is triggered."""
        mock_redis = MagicMock()
        mock_redis.hgetall.return_value = {
            ENABLED_FIELD: "1",
            TRIGGERED_FIELD: "1",
            INITIALIZED_AT_FIELD: "2024-01-15T12:00:00+00:00",
            INITIALIZED_BY_FIELD: "bootstrap",
        }

        status = get_kill_switch_status(mock_redis)

        assert status["initialized"] is True
        assert status["enabled"] is True
        assert status["triggered"] is True

    def test_returns_not_initialized_when_empty(self):
        """Test returns not initialized when hash doesn't exist."""
        mock_redis = MagicMock()
        mock_redis.hgetall.return_value = {}

        status = get_kill_switch_status(mock_redis)

        assert status["initialized"] is False
        assert status["enabled"] is False
        assert status["triggered"] is False
        assert status["initialized_at"] is None
        assert status["initialized_by"] is None
        assert status["error"] is None

    def test_returns_error_on_redis_failure(self):
        """Test returns error status when Redis fails."""
        mock_redis = MagicMock()
        mock_redis.hgetall.side_effect = Exception("Connection refused")

        status = get_kill_switch_status(mock_redis)

        assert status["initialized"] is False
        assert status["error"] is not None
        assert "Connection refused" in status["error"]


class TestGetRedisClient:
    """Test _get_redis_client function."""

    @patch("redis.Redis")
    @patch("os.getenv")
    def test_uses_environment_variables(self, mock_getenv, mock_redis_class):
        """Test that Redis client uses environment variables."""
        mock_getenv.side_effect = lambda key, default: {
            "REDIS_HOST": "test-host",
            "REDIS_PORT": "1234",
        }.get(key, default)

        mock_client = MagicMock()
        mock_redis_class.return_value = mock_client

        result = _get_redis_client()

        assert result is not None
        mock_redis_class.assert_called_once()
        call_kwargs = mock_redis_class.call_args[1]
        assert call_kwargs["host"] == "test-host"
        assert call_kwargs["port"] == 1234

    @patch("redis.Redis")
    def test_returns_none_on_connection_failure(self, mock_redis_class):
        """Test returns None when Redis connection fails."""
        mock_client = MagicMock()
        mock_client.ping.side_effect = Exception("Connection refused")
        mock_redis_class.return_value = mock_client

        result = _get_redis_client()

        assert result is None

    @patch("redis.Redis")
    def test_uses_default_host_and_port(self, mock_redis_class):
        """Test uses default host.docker.internal:6380 when env vars not set."""
        mock_client = MagicMock()
        mock_redis_class.return_value = mock_client

        def mock_getenv(key, default=None):
            return default  # Return default for all keys

        with patch("os.getenv", side_effect=mock_getenv):
            result = _get_redis_client()

        assert result is not None
        call_kwargs = mock_redis_class.call_args[1]
        assert call_kwargs["host"] == "host.docker.internal"
        assert call_kwargs["port"] == 6380


class TestIntegration:
    """Integration-style tests for the bootstrap module."""

    def test_full_bootstrap_flow(self):
        """Test the complete bootstrap flow from uninitialized to initialized."""
        mock_redis = MagicMock()

        # First call - not initialized
        mock_redis.hget.return_value = None
        mock_redis.hgetall.return_value = {}

        # Check initial state
        assert is_kill_switch_initialized(mock_redis) is False
        status = get_kill_switch_status(mock_redis)
        assert status["initialized"] is False

        # Bootstrap
        result = bootstrap_kill_switch(mock_redis)
        assert result is True

        # Simulate Redis now having the values
        mock_redis.hget.side_effect = lambda key, field: {
            ENABLED_FIELD: "1",
            TRIGGERED_FIELD: "0",
        }.get(field)
        mock_redis.hgetall.return_value = {
            ENABLED_FIELD: "1",
            TRIGGERED_FIELD: "0",
            INITIALIZED_AT_FIELD: "2024-01-15T12:00:00+00:00",
            INITIALIZED_BY_FIELD: "bootstrap",
        }

        # Check state after bootstrap
        assert is_kill_switch_initialized(mock_redis) is True
        status = get_kill_switch_status(mock_redis)
        assert status["initialized"] is True
        assert status["enabled"] is True
        assert status["triggered"] is False

        # Bootstrap again - should be idempotent
        result = bootstrap_kill_switch(mock_redis)
        assert result is True
        # hsetnx should not be called again since already initialized
        # (hget is checked first in is_kill_switch_initialized)

    def test_check_kill_switch_returns_correct_status_after_bootstrap(self):
        """Test that hourly health check would get correct status after bootstrap."""
        mock_redis = MagicMock()

        # Simulate bootstrapped state
        mock_redis.hgetall.return_value = {
            ENABLED_FIELD: "1",
            TRIGGERED_FIELD: "0",
            INITIALIZED_AT_FIELD: "2024-01-15T12:00:00+00:00",
            INITIALIZED_BY_FIELD: "bootstrap",
        }

        status = get_kill_switch_status(mock_redis)

        # This simulates what check_kill_switch would return
        if status.get("error"):
            check_result = {
                "status": "❌",
                "armed": False,
                "detail": f"Error: {status['error']}",
            }
        elif not status.get("initialized"):
            check_result = {"status": "⚠️", "armed": False, "detail": "Not configured"}
        elif status.get("triggered"):
            check_result = {"status": "🚨", "armed": False, "detail": "TRIGGERED"}
        elif status.get("enabled"):
            check_result = {"status": "✅", "armed": True, "detail": "Armed"}
        else:
            check_result = {"status": "⚠️", "armed": False, "detail": "Disabled"}

        assert check_result["status"] == "✅"
        assert check_result["armed"] is True
        assert check_result["detail"] == "Armed"
