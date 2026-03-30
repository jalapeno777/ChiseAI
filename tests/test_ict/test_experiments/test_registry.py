"""Tests for experiment registry."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest
from src.ict.experiments.key_schema import ExperimentKey
from src.ict.experiments.registry import ExperimentRegistry


class TestExperimentRegistry:
    """Tests for ExperimentRegistry class."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        mock = MagicMock()
        mock.exists = MagicMock(return_value=False)
        mock.hset = MagicMock(return_value=True)
        mock.expire = MagicMock(return_value=True)
        mock.sadd = MagicMock(return_value=1)
        mock.smembers = MagicMock(return_value=set())
        mock.hgetall = MagicMock(return_value={})
        mock.keys = MagicMock(return_value=[])
        mock.srem = MagicMock(return_value=1)
        return mock

    @pytest.fixture
    def registry(self, mock_redis):
        """Create registry with mock Redis."""
        return ExperimentRegistry(redis_client=mock_redis)

    @pytest.fixture
    def sample_key(self):
        """Create a sample experiment key."""
        return ExperimentKey(
            experiment_id="ICT-B1",
            variant="baseline",
            started_at=datetime(2026, 3, 29),
        )

    def test_register_experiment(self, registry, mock_redis, sample_key):
        """Test registering a new experiment."""
        result = registry.register_experiment(sample_key)
        assert result is True
        assert mock_redis.hset.called
        assert mock_redis.sadd.called

    def test_register_duplicate_experiment(self, registry, mock_redis, sample_key):
        """Test registering duplicate experiment fails."""
        mock_redis.exists.return_value = True
        result = registry.register_experiment(sample_key)
        assert result is False

    def test_get_active_experiments_empty(self, registry, mock_redis):
        """Test getting active experiments when none exist."""
        mock_redis.smembers.return_value = set()
        result = registry.get_active_experiments()
        assert result == []

    def test_get_active_experiments(self, registry, mock_redis):
        """Test getting active experiments."""
        mock_redis.smembers.return_value = {b"ict:exp:registry:ICT-B1:baseline"}
        mock_redis.hgetall.return_value = {
            "experiment_id": "ICT-B1",
            "variant": "baseline",
            "status": "active",
        }
        result = registry.get_active_experiments()
        assert len(result) == 1

    def test_is_experiment_active_true(self, registry, mock_redis):
        """Test checking if experiment is active."""
        mock_redis.exists.return_value = True
        result = registry.is_experiment_active("ICT-B1", "baseline")
        assert result is True

    def test_is_experiment_active_false(self, registry, mock_redis):
        """Test checking if experiment is not active."""
        mock_redis.exists.return_value = False
        result = registry.is_experiment_active("ICT-B1", "baseline")
        assert result is False

    def test_is_experiment_active_any_variant(self, registry, mock_redis):
        """Test checking if any variant of experiment is active."""
        mock_redis.keys.return_value = ["key1"]
        result = registry.is_experiment_active("ICT-B1")
        assert result is True

    def test_close_experiment(self, registry, mock_redis, sample_key):
        """Test closing an experiment."""
        mock_redis.exists.return_value = True
        result = registry.close_experiment(sample_key)
        assert result is True
        assert mock_redis.srem.called

    def test_close_experiment_not_found(self, registry, mock_redis, sample_key):
        """Test closing non-existent experiment."""
        mock_redis.exists.return_value = False
        result = registry.close_experiment(sample_key)
        assert result is False

    def test_get_experiment_status(self, registry, mock_redis):
        """Test getting experiment status."""
        mock_redis.hgetall.return_value = {
            "experiment_id": "ICT-B1",
            "variant": "baseline",
            "status": "active",
        }
        result = registry.get_experiment_status("ICT-B1", "baseline")
        assert result is not None
        assert result["experiment_id"] == "ICT-B1"

    def test_get_experiment_status_not_found(self, registry, mock_redis):
        """Test getting status for non-existent experiment."""
        mock_redis.hgetall.return_value = {}
        result = registry.get_experiment_status("ICT-B99", "nonexistent")
        assert result is None
