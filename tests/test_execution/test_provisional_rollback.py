"""
Tests for Provisional Rollback Procedures (ST-ICT-036)

These tests verify the rollback capabilities for the bos_choch feature flag
when deployed in provisional mode.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from src.execution.paper.provisional_rollback import (
    ProvisionalRollback,
    RollbackResult,
    create_provisional_rollback,
)


class TestRollbackResult:
    """Tests for the RollbackResult dataclass."""

    def test_rollback_result_success(self):
        """Test successful rollback result creation."""
        result = RollbackResult(success=True, duration_seconds=2.5, steps_completed=3)

        assert result.success is True
        assert result.duration_seconds == 2.5
        assert result.steps_completed == 3
        assert result.errors == []
        assert isinstance(result.timestamp, datetime)

    def test_rollback_result_with_errors(self):
        """Test rollback result with errors."""
        errors = ["Step 1 failed: connection timeout"]
        result = RollbackResult(
            success=False, duration_seconds=5.0, steps_completed=1, errors=errors
        )

        assert result.success is False
        assert result.steps_completed == 1
        assert len(result.errors) == 1
        assert "connection timeout" in result.errors[0]


class TestProvisionalRollback:
    """Tests for the ProvisionalRollback class."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        with patch("redis.Redis") as mock_redis_class:
            mock_client = MagicMock()
            mock_redis_class.return_value = mock_client
            yield mock_client

    @pytest.fixture
    def rollback(self, mock_redis):
        """Create a ProvisionalRollback instance with mocked Redis."""
        instance = ProvisionalRollback(
            redis_host="localhost", redis_port=6379, redis_db=0
        )
        instance._redis_client = mock_redis
        return instance

    def test_init_default_values(self):
        """Test initialization with default values."""
        rollback = ProvisionalRollback()

        assert rollback.redis_host == "host.docker.internal"
        assert rollback.redis_port == 6380
        assert rollback.redis_db == 1
        assert rollback.feature_flag_key == "ict:bos_choch:enabled"

    def test_init_custom_values(self):
        """Test initialization with custom values."""
        rollback = ProvisionalRollback(
            redis_host="custom-host",
            redis_port=6381,
            redis_db=2,
            feature_flag_key="custom:feature:flag",
        )

        assert rollback.redis_host == "custom-host"
        assert rollback.redis_port == 6381
        assert rollback.redis_db == 2
        assert rollback.feature_flag_key == "custom:feature:flag"

    def test_disable_bos_choch_success(self, rollback, mock_redis):
        """Test successful feature flag disable."""
        mock_redis.set.return_value = True

        result = rollback.disable_bos_choch()

        assert result is True
        mock_redis.set.assert_called_once_with("ict:bos_choch:enabled", "false")

    def test_disable_bos_choch_failure(self, rollback, mock_redis):
        """Test feature flag disable failure."""
        mock_redis.set.return_value = False

        result = rollback.disable_bos_choch()

        assert result is False

    def test_disable_bos_choch_exception(self, rollback, mock_redis):
        """Test feature flag disable with exception."""
        mock_redis.set.side_effect = Exception("Redis connection failed")

        with pytest.raises(RuntimeError, match="Redis error during disable"):
            rollback.disable_bos_choch()

    def test_rollback_in_30_seconds_success(self, rollback, mock_redis):
        """Test successful rollback within time limit."""
        mock_redis.set.return_value = True

        result = rollback.rollback_in_30_seconds()

        assert result.success is True
        assert result.duration_seconds < 30.0
        assert result.steps_completed >= 1

    def test_rollback_in_30_seconds_failure(self, rollback, mock_redis):
        """Test rollback when disable fails."""
        mock_redis.set.side_effect = Exception("Redis error")

        result = rollback.rollback_in_30_seconds()

        assert result.success is False
        assert len(result.errors) > 0

    def test_verify_rollback_success(self, rollback, mock_redis):
        """Test successful rollback verification."""
        mock_redis.get.return_value = "false"

        verification = rollback.verify_rollback()

        assert verification["flag_disabled"] is True
        assert verification["all_checks_passed"] is True
        assert "verification_timestamp" in verification

    def test_verify_rollback_not_disabled(self, rollback, mock_redis):
        """Test rollback verification when flag is not disabled."""
        mock_redis.get.return_value = "true"

        verification = rollback.verify_rollback()

        assert verification["flag_disabled"] is False
        assert verification["all_checks_passed"] is False

    def test_verify_rollback_error(self, rollback, mock_redis):
        """Test rollback verification with Redis error."""
        mock_redis.get.side_effect = Exception("Connection lost")

        verification = rollback.verify_rollback()

        assert verification["all_checks_passed"] is False
        assert "error" in verification

    def test_check_rollback_decision_criteria(self, rollback):
        """Test rollback decision criteria check."""
        criteria = rollback.check_rollback_decision_criteria()

        assert "criteria_met" in criteria
        assert "reason" in criteria
        assert "documentation" in criteria
        assert criteria["documentation"]["rollback_time_limit"] == "30 seconds maximum"

    def test_get_rollback_status(self, rollback, mock_redis):
        """Test getting rollback status."""
        mock_redis.get.return_value = "false"

        status = rollback.get_rollback_status()

        assert status["feature_flag_key"] == "ict:bos_choch:enabled"
        assert status["redis_connection"] == "connected"
        assert status["current_flag_state"] == "false"

    def test_get_rollback_status_connection_error(self, rollback, mock_redis):
        """Test rollback status with connection error."""
        mock_redis.get.side_effect = Exception("Connection refused")

        status = rollback.get_rollback_status()

        assert "error" in status["redis_connection"]

    def test_create_provisional_rollback_factory(self):
        """Test factory function creates correct instance."""
        rollback = create_provisional_rollback()

        assert isinstance(rollback, ProvisionalRollback)
        assert rollback.feature_flag_key == "ict:bos_choch:enabled"


class TestRollbackIntegration:
    """Integration tests for rollback procedures."""

    @patch("redis.Redis")
    def test_full_rollback_flow(self, mock_redis_class):
        """Test complete rollback flow from start to finish."""
        mock_client = MagicMock()
        mock_redis_class.return_value = mock_client
        mock_client.set.return_value = True
        mock_client.get.return_value = "false"

        # Create rollback instance
        rollback = ProvisionalRollback()
        rollback._redis_client = mock_client

        # Execute rollback
        result = rollback.rollback_in_30_seconds()
        assert result.success is True

        # Verify
        verification = rollback.verify_rollback()
        assert verification["all_checks_passed"] is True

        # Get status
        status = rollback.get_rollback_status()
        assert status["current_flag_state"] == "false"
