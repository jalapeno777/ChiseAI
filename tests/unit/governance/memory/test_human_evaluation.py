"""
Unit tests for human_evaluation.py

Tests AC1: store_human_evaluation() and get_latest_evaluation() work
Tests AC3: get_evaluation_summary() returns mean scores

Note: AC2 (Redis key pattern verification) requires integration test
since it verifies actual Redis key existence.
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from src.governance.memory.human_evaluation import (
    HumanEvaluationResult,
    _build_key,
    get_evaluation_summary,
    get_latest_evaluation,
    store_human_evaluation,
)


class TestHumanEvaluationResult:
    """Test HumanEvaluationResult dataclass."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        now = datetime(2026, 4, 9, 12, 0, 0, tzinfo=UTC)
        result = HumanEvaluationResult(
            accuracy=4.0,
            completeness=3.5,
            actionability=4.0,
            non_redundancy=3.5,
            evaluator_id="test-evaluator",
            story_id="ST-TEST",
            observation_id="obs-001",
            evaluated_at=now,
        )
        data = result.to_dict()
        assert data["accuracy"] == "4.0"
        assert data["completeness"] == "3.5"
        assert data["actionability"] == "4.0"
        assert data["non_redundancy"] == "3.5"
        assert data["evaluator_id"] == "test-evaluator"
        assert data["story_id"] == "ST-TEST"
        assert data["observation_id"] == "obs-001"
        assert data["evaluated_at"] == now.isoformat()

    def test_from_dict(self):
        """Test creation from dictionary."""
        now = datetime(2026, 4, 9, 12, 0, 0, tzinfo=UTC)
        data = {
            "accuracy": "4.0",
            "completeness": "3.5",
            "actionability": "4.0",
            "non_redundancy": "3.5",
            "evaluator_id": "test-evaluator",
            "story_id": "ST-TEST",
            "observation_id": "obs-001",
            "evaluated_at": now.isoformat(),
        }
        result = HumanEvaluationResult.from_dict(data)
        assert result.accuracy == 4.0
        assert result.completeness == 3.5
        assert result.actionability == 4.0
        assert result.non_redundancy == 3.5
        assert result.evaluator_id == "test-evaluator"
        assert result.story_id == "ST-TEST"
        assert result.observation_id == "obs-001"
        assert result.evaluated_at == now


class TestBuildKey:
    """Test Redis key building."""

    def test_build_key_format(self):
        """Test key format matches spec: bmad:chiseai:memory:human_eval:{story_id}:{observation_id}"""
        key = _build_key("ST-TEST", "obs-001")
        assert key == "bmad:chiseai:memory:human_eval:ST-TEST:obs-001"


class TestStoreHumanEvaluation:
    """Test store_human_evaluation function."""

    @patch("src.governance.memory.human_evaluation._get_redis_client")
    def test_store_returns_key(self, mock_get_redis):
        """Test that store returns the Redis key."""
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        now = datetime(2026, 4, 9, 12, 0, 0, tzinfo=UTC)
        result = HumanEvaluationResult(
            accuracy=4.0,
            completeness=3.5,
            actionability=4.0,
            non_redundancy=3.5,
            evaluator_id="test-evaluator",
            story_id="ST-TEST",
            observation_id="obs-001",
            evaluated_at=now,
        )

        key = store_human_evaluation(result)
        assert key == "bmad:chiseai:memory:human_eval:ST-TEST:obs-001"
        mock_redis.hset.assert_called_once()

    @patch("src.governance.memory.human_evaluation._get_redis_client")
    def test_store_raises_when_redis_unavailable(self, mock_get_redis):
        """Test that RuntimeError is raised when Redis unavailable."""
        mock_get_redis.return_value = None

        now = datetime(2026, 4, 9, 12, 0, 0, tzinfo=UTC)
        result = HumanEvaluationResult(
            accuracy=4.0,
            completeness=3.5,
            actionability=4.0,
            non_redundancy=3.5,
            evaluator_id="test-evaluator",
            story_id="ST-TEST",
            observation_id="obs-001",
            evaluated_at=now,
        )

        with pytest.raises(RuntimeError, match="Redis connection unavailable"):
            store_human_evaluation(result)


class TestGetLatestEvaluation:
    """Test get_latest_evaluation function."""

    @patch("src.governance.memory.human_evaluation._get_redis_client")
    def test_returns_none_when_no_evaluations(self, mock_get_redis):
        """Test None returned when no evaluations exist."""
        mock_redis = MagicMock()
        mock_redis.scan_iter.return_value = iter([])
        mock_get_redis.return_value = mock_redis

        result = get_latest_evaluation("ST-NONE")
        assert result is None

    @patch("src.governance.memory.human_evaluation._get_redis_client")
    def test_returns_most_recent_evaluation(self, mock_get_redis):
        """Test that most recent evaluation is returned."""
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        # Mock scan_iter to return two keys
        keys = [
            "bmad:chiseai:memory:human_eval:ST-TEST:obs-001",
            "bmad:chiseai:memory:human_eval:ST-TEST:obs-002",
        ]
        mock_redis.scan_iter.return_value = iter(keys)

        # Mock hgetall for each key - obs-002 is more recent
        now = datetime(2026, 4, 9, 12, 0, 0, tzinfo=UTC)
        earlier = datetime(2026, 4, 9, 11, 0, 0, tzinfo=UTC)

        def mock_hgetall(key):
            if "obs-001" in key:
                return {
                    "accuracy": "3.0",
                    "completeness": "3.0",
                    "actionability": "3.0",
                    "non_redundancy": "3.0",
                    "evaluator_id": "eval-1",
                    "story_id": "ST-TEST",
                    "observation_id": "obs-001",
                    "evaluated_at": earlier.isoformat(),
                }
            else:
                return {
                    "accuracy": "4.0",
                    "completeness": "4.0",
                    "actionability": "4.0",
                    "non_redundancy": "4.0",
                    "evaluator_id": "eval-2",
                    "story_id": "ST-TEST",
                    "observation_id": "obs-002",
                    "evaluated_at": now.isoformat(),
                }

        mock_redis.hgetall.side_effect = mock_hgetall

        result = get_latest_evaluation("ST-TEST")
        assert result is not None
        assert result.observation_id == "obs-002"
        assert result.accuracy == 4.0

    @patch("src.governance.memory.human_evaluation._get_redis_client")
    def test_returns_none_when_redis_unavailable(self, mock_get_redis):
        """Test None returned when Redis unavailable."""
        mock_get_redis.return_value = None

        result = get_latest_evaluation("ST-TEST")
        assert result is None


class TestGetEvaluationSummary:
    """Test get_evaluation_summary function."""

    @patch("src.governance.memory.human_evaluation._get_redis_client")
    def test_returns_zeros_when_no_evaluations(self, mock_get_redis):
        """Test zeros returned when no evaluations exist."""
        mock_redis = MagicMock()
        mock_redis.scan_iter.return_value = iter([])
        mock_get_redis.return_value = mock_redis

        summary = get_evaluation_summary("ST-NONE")
        assert summary["count"] == 0
        assert summary["mean_accuracy"] == 0.0
        assert summary["mean_completeness"] == 0.0
        assert summary["mean_actionability"] == 0.0
        assert summary["mean_non_redundancy"] == 0.0

    @patch("src.governance.memory.human_evaluation._get_redis_client")
    def test_calculates_mean_scores(self, mock_get_redis):
        """Test mean calculation for multiple evaluations."""
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        keys = [
            "bmad:chiseai:memory:human_eval:ST-TEST:obs-001",
            "bmad:chiseai:memory:human_eval:ST-TEST:obs-002",
        ]
        mock_redis.scan_iter.return_value = iter(keys)

        def mock_hgetall(key):
            return {
                "accuracy": "4.0",
                "completeness": "3.5",
                "actionability": "4.5",
                "non_redundancy": "3.0",
                "evaluator_id": "eval-1",
                "story_id": "ST-TEST",
                "observation_id": "obs-001",
                "evaluated_at": datetime.now(UTC).isoformat(),
            }

        mock_redis.hgetall.side_effect = mock_hgetall

        summary = get_evaluation_summary("ST-TEST")
        assert summary["count"] == 2
        # Mean of [4.0, 4.0] = 4.0
        assert summary["mean_accuracy"] == 4.0
        # Mean of [3.5, 3.5] = 3.5
        assert summary["mean_completeness"] == 3.5
        # Mean of [4.5, 4.5] = 4.5
        assert summary["mean_actionability"] == 4.5
        # Mean of [3.0, 3.0] = 3.0
        assert summary["mean_non_redundancy"] == 3.0

    @patch("src.governance.memory.human_evaluation._get_redis_client")
    def test_returns_zeros_when_redis_unavailable(self, mock_get_redis):
        """Test zeros returned when Redis unavailable."""
        mock_get_redis.return_value = None

        summary = get_evaluation_summary("ST-TEST")
        assert summary["count"] == 0
        assert summary["mean_accuracy"] == 0.0


class TestRoundtrip:
    """Integration-style roundtrip tests (AC1)."""

    @patch("src.governance.memory.human_evaluation._get_redis_client")
    def test_store_and_retrieve(self, mock_get_redis):
        """Test store -> retrieve roundtrip (AC1)."""
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        # Store
        now = datetime(2026, 4, 9, 12, 0, 0, tzinfo=UTC)
        result = HumanEvaluationResult(
            accuracy=4.0,
            completeness=3.5,
            actionability=4.0,
            non_redundancy=3.5,
            evaluator_id="test-evaluator",
            story_id="ST-TEST",
            observation_id="obs-001",
            evaluated_at=now,
        )

        key = store_human_evaluation(result)
        assert key == "bmad:chiseai:memory:human_eval:ST-TEST:obs-001"

        # Mock retrieve
        mock_redis.scan_iter.return_value = iter([key])
        mock_redis.hgetall.return_value = result.to_dict()

        retrieved = get_latest_evaluation("ST-TEST")
        assert retrieved is not None
        assert retrieved.accuracy == 4.0
        assert retrieved.completeness == 3.5
        assert retrieved.actionability == 4.0
        assert retrieved.non_redundancy == 3.5
        assert retrieved.evaluator_id == "test-evaluator"
        assert retrieved.story_id == "ST-TEST"
        assert retrieved.observation_id == "obs-001"
