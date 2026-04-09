"""
Unit tests for Reflector module.

Tests Reflector class with mocked Redis, Qdrant, and LLM clients.
"""

import json
import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from src.governance.memory.reflector_agent import (
    DEFAULT_CONSOLIDATION_THRESHOLD,
    FEATURE_FLAG_KEY,
    MIN_CONSOLIDATION_INTERVAL,
    MIN_OBSERVATIONS_FOR_CONSOLIDATION,
    CONVERGENCE_OVERLAP_THRESHOLD,
    OBSERVATIONS_ACTIVE_PREFIX,
    REFLECTOR_STATE_KEY,
    SupersededObservation,
    Reflector,
)


class TestReflectorInitDefaults(unittest.TestCase):
    """Test Reflector.__init__() defaults."""

    def test_reflector_init_defaults(self):
        """Verify Reflector initializes with correct defaults."""
        reflector = Reflector()
        self.assertEqual(reflector.threshold, DEFAULT_CONSOLIDATION_THRESHOLD)
        self.assertEqual(reflector.threshold, 40000)
        self.assertIsNone(reflector._redis_client)
        self.assertIsNone(reflector._qdrant_client)
        self.assertIsNone(reflector._llm_client)

    def test_reflector_init_custom_threshold(self):
        """Verify custom threshold is set correctly."""
        reflector = Reflector(threshold=50000)
        self.assertEqual(reflector.threshold, 50000)

    def test_reflector_init_custom_redis(self):
        """Verify pre-configured Redis client is stored."""
        mock_redis = MagicMock()
        reflector = Reflector(redis_client=mock_redis)
        self.assertIs(reflector._redis_client, mock_redis)

    def test_reflector_init_custom_qdrant(self):
        """Verify pre-configured Qdrant client is stored."""
        mock_qdrant = MagicMock()
        reflector = Reflector(qdrant_client=mock_qdrant)
        self.assertIs(reflector._qdrant_client, mock_qdrant)

    def test_reflector_init_custom_llm(self):
        """Verify pre-configured LLM client is stored."""
        mock_llm = MagicMock()
        reflector = Reflector(llm_client=mock_llm)
        self.assertIs(reflector._llm_client, mock_llm)


class TestShouldTrigger(unittest.TestCase):
    """Test should_trigger() trigger guard logic."""

    def setUp(self):
        """Set up test fixtures with mocked Redis."""
        self.mock_redis = MagicMock()
        self.reflector = Reflector(redis_client=self.mock_redis)

    def test_should_trigger_meets_threshold(self):
        """Test token_count >= 30000, obs >= 10 -> True."""
        # Create 10+ observations with enough tokens
        observations = [
            {
                "content": ("word " * 3000).strip(),
                "timestamp": datetime.now(UTC).isoformat(),
            }
            for _ in range(10)
        ]
        # Total: 10 obs * 3000 words * 1.3 = 39000 tokens >= 30000

        self.mock_redis.zrange.return_value = [json.dumps(obs) for obs in observations]
        self.mock_redis.zcard.return_value = 10
        self.mock_redis.hget.return_value = None  # No prior consolidation

        result = self.reflector.should_trigger("test-session")

        self.assertTrue(result)

    def test_should_trigger_24h_elapsed(self):
        """Test token_count >= 30000, 7 obs, 25h since last -> True."""
        # Create 7 observations with enough tokens
        # Each observation needs ~3000 words to get 7 * 3000 * 1.3 = 27300 tokens
        # But we need >= 30000, so we need more words
        observations = [
            {
                "content": ("word " * 3500).strip(),
                "timestamp": datetime.now(UTC).isoformat(),
            }
            for _ in range(7)
        ]
        # 7 * 3500 * 1.3 = 31850 tokens >= 30000

        self.mock_redis.zrange.return_value = [json.dumps(obs) for obs in observations]
        self.mock_redis.zcard.return_value = 7

        # Last consolidation was 25 hours ago
        last_time = (datetime.now(UTC) - timedelta(hours=25)).isoformat()
        self.mock_redis.hget.return_value = last_time

        result = self.reflector.should_trigger("test-session")

        self.assertTrue(result)

    def test_should_trigger_not_enough_obs(self):
        """Test token_count >= 30000, 7 obs, 1h since -> False."""
        # Create 7 observations with enough tokens
        observations = [
            {
                "content": ("word " * 3000).strip(),
                "timestamp": datetime.now(UTC).isoformat(),
            }
            for _ in range(7)
        ]

        self.mock_redis.zrange.return_value = [json.dumps(obs) for obs in observations]
        self.mock_redis.zcard.return_value = 7

        # Last consolidation was only 1 hour ago
        last_time = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        self.mock_redis.hget.return_value = last_time

        result = self.reflector.should_trigger("test-session")

        self.assertFalse(result)

    def test_should_trigger_not_enough_tokens(self):
        """Test token_count = 20000 < 30000 -> False."""
        # Create observations with not enough tokens
        observations = [
            {
                "content": ("word " * 2000).strip(),
                "timestamp": datetime.now(UTC).isoformat(),
            }
            for _ in range(3)
        ]
        # 3 * 2000 * 1.3 = 7800 tokens < 30000

        self.mock_redis.zrange.return_value = [json.dumps(obs) for obs in observations]
        self.mock_redis.zcard.return_value = 3
        self.mock_redis.hget.return_value = None

        result = self.reflector.should_trigger("test-session")

        self.assertFalse(result)

    def test_should_trigger_no_observations(self):
        """Test with no observations returns False."""
        self.mock_redis.zrange.return_value = []
        self.mock_redis.zcard.return_value = 0

        result = self.reflector.should_trigger("test-session")

        self.assertFalse(result)


class TestConsolidateObservationsDryRun(unittest.TestCase):
    """Test consolidate_observations() dry_run behavior."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_redis = MagicMock()
        self.mock_qdrant = MagicMock()
        self.mock_llm = MagicMock()
        self.reflector = Reflector(
            redis_client=self.mock_redis,
            qdrant_client=self.mock_qdrant,
            llm_client=self.mock_llm,
        )

    def test_consolidate_observations_dry_run(self):
        """Test dry_run=True, no Qdrant writes."""
        # Enable feature flag
        self.mock_redis.get.return_value = "true"

        # Set up enough observations
        observations = [
            {
                "content": ("word " * 3000).strip(),
                "timestamp": datetime.now(UTC).isoformat(),
                "source_message_ids": ["1"],
            }
            for _ in range(10)
        ]
        self.mock_redis.zrange.return_value = [json.dumps(obs) for obs in observations]
        self.mock_redis.zcard.return_value = 10
        self.mock_redis.hget.return_value = None  # No prior consolidation state

        # Configure LLM mock
        self.mock_llm.consolidate.return_value = {
            "content": "Consolidated content",
            "raw_tokens": 40000,
            "consolidated_tokens": 1000,
            "priority": "high",
            "category": "decision",
        }

        result = self.reflector.consolidate_observations("test-session", dry_run=True)

        # Should succeed
        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "success")

        # Qdrant upsert should NOT be called in dry run
        self.mock_qdrant.upsert.assert_not_called()

        # Redis hset should NOT be called in dry run
        self.mock_redis.hset.assert_not_called()


class TestFeatureFlagGating(unittest.TestCase):
    """Test feature flag gating behavior."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_redis = MagicMock()
        self.mock_llm = MagicMock()
        self.reflector = Reflector(
            redis_client=self.mock_redis,
            llm_client=self.mock_llm,
        )

    def test_feature_flag_disabled_no_writes(self):
        """Test that no writes occur when feature flag is disabled."""
        self.mock_redis.get.return_value = "false"

        result = self.reflector.consolidate_observations("test-session", dry_run=False)

        self.assertIsNone(result)
        self.mock_llm.consolidate.assert_not_called()

    def test_feature_flag_enabled_allows_consolidation(self):
        """Test consolidation proceeds when flag is enabled."""
        self.mock_redis.get.return_value = "true"

        # Set up enough observations
        observations = [
            {
                "content": ("word " * 3000).strip(),
                "timestamp": datetime.now(UTC).isoformat(),
                "source_message_ids": ["1"],
            }
            for _ in range(10)
        ]
        self.mock_redis.zrange.return_value = [json.dumps(obs) for obs in observations]
        self.mock_redis.zcard.return_value = 10
        self.mock_redis.hget.return_value = None

        self.mock_llm.consolidate.return_value = {
            "content": "Consolidated content",
            "raw_tokens": 40000,
            "consolidated_tokens": 1000,
            "priority": "high",
            "category": "decision",
        }

        result = self.reflector.consolidate_observations("test-session", dry_run=True)

        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "success")


class TestLLMConsolidation(unittest.TestCase):
    """Test LLM client injection and consolidation."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_redis = MagicMock()
        self.mock_llm = MagicMock()
        self.reflector = Reflector(
            redis_client=self.mock_redis,
            llm_client=self.mock_llm,
        )

    def test_llm_client_injectable(self):
        """Test that LLM client can be injected and used."""
        self.mock_redis.get.return_value = "true"

        # Create enough observations to trigger (>= 10 obs, >= 30000 tokens)
        observations = [
            {
                "content": ("word " * 3000).strip(),
                "timestamp": datetime.now(UTC).isoformat(),
                "source_message_ids": [str(i)],
            }
            for i in range(10)
        ]
        # 10 * 3000 * 1.3 = 39000 tokens >= 30000

        self.mock_redis.zrange.return_value = [json.dumps(obs) for obs in observations]
        self.mock_redis.zcard.return_value = 10
        self.mock_redis.hget.return_value = None  # No prior consolidation

        self.mock_llm.consolidate.return_value = {
            "content": "LLM consolidated content",
            "raw_tokens": 100,
            "consolidated_tokens": 50,
            "priority": "medium",
            "category": "fact",
        }

        result = self.reflector.consolidate_observations("test-session", dry_run=True)

        self.assertIsNotNone(result)
        self.mock_llm.consolidate.assert_called_once()


class TestConvergenceGuard(unittest.TestCase):
    """Test convergence guard logic."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_redis = MagicMock()
        self.mock_llm = MagicMock()
        self.reflector = Reflector(
            redis_client=self.mock_redis,
            llm_client=self.mock_llm,
        )

    def test_check_convergence_85_percent_overlap(self):
        """Test 85% word overlap triggers skip."""
        # Prior consolidated content
        prior_content = "the quick brown fox jumps over the lazy dog"

        self.mock_redis.hget.return_value = prior_content

        # New content with >80% overlap
        new_content = "the quick brown fox jumps over the lazy cat"

        result = self.reflector._check_convergence(new_content, "test-session")

        self.assertTrue(result)

    def test_check_convergence_50_percent_overlap(self):
        """Test 50% word overlap allows write."""
        # Prior consolidated content
        prior_content = "the quick brown fox jumps over the lazy dog"

        self.mock_redis.hget.return_value = prior_content

        # New content with ~50% overlap
        new_content = "the quick red car drives down the road"

        result = self.reflector._check_convergence(new_content, "test-session")

        self.assertFalse(result)

    def test_check_convergence_no_prior_content(self):
        """Test no skip when no prior content."""
        self.mock_redis.hget.return_value = None

        new_content = "some new content"

        result = self.reflector._check_convergence(new_content, "test-session")

        self.assertFalse(result)


class TestSupersededObservation(unittest.TestCase):
    """Test SupersededObservation dataclass."""

    def test_superseded_observation_dataclass(self):
        """Test dataclass fields are correct."""
        obs = SupersededObservation(
            content="Test content",
            created_at="2026-04-09T10:00:00Z",
            updated_at="2026-04-09T11:00:00Z",
            superseded_at="2026-04-09T12:00:00Z",
            session_id="test-session",
            priority="high",
            category="decision",
            confidence=0.85,
            source_observation_ids=["obs1", "obs2"],
        )

        self.assertEqual(obs.content, "Test content")
        self.assertEqual(obs.created_at, "2026-04-09T10:00:00Z")
        self.assertEqual(obs.updated_at, "2026-04-09T11:00:00Z")
        self.assertEqual(obs.superseded_at, "2026-04-09T12:00:00Z")
        self.assertEqual(obs.session_id, "test-session")
        self.assertEqual(obs.priority, "high")
        self.assertEqual(obs.category, "decision")
        self.assertEqual(obs.confidence, 0.85)
        self.assertEqual(obs.source_observation_ids, ["obs1", "obs2"])

    def test_superseded_at_none_when_active(self):
        """Test superseded_at is None for active observations."""
        obs = SupersededObservation(
            content="Active content",
            created_at="2026-04-09T10:00:00Z",
            updated_at="2026-04-09T11:00:00Z",
            superseded_at=None,
            session_id="test-session",
            priority="medium",
            category="fact",
            confidence=0.7,
            source_observation_ids=["obs1"],
        )

        self.assertIsNone(obs.superseded_at)


class TestSupersedePriorObservations(unittest.TestCase):
    """Test _supersede_prior_observations() behavior."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_redis = MagicMock()
        self.reflector = Reflector(redis_client=self.mock_redis)

    def test_supersede_prior_observations_sets_superseded_at(self):
        """Test that old observations are marked with superseded_at."""
        # Set up existing observations
        observations = [
            {"content": "Old content 1", "timestamp": "2026-04-09T10:00:00Z"},
            {"content": "Old content 2", "timestamp": "2026-04-09T11:00:00Z"},
        ]
        self.mock_redis.zrange.return_value = [json.dumps(obs) for obs in observations]
        self.mock_redis.zscore.return_value = 1234567890.0

        self.reflector._supersede_prior_observations("test-session")

        # Verify zadd was called (with updated superseded_at)
        self.mock_redis.zadd.assert_called()
        # Get the call arguments
        call_args = self.mock_redis.zadd.call_args
        # The second arg is the dict of {json_data: score}
        added_data = list(call_args[0][1].keys())
        for item in added_data:
            parsed = json.loads(item)
            self.assertIsNotNone(parsed.get("superseded_at"))


class TestGetActiveObservations(unittest.TestCase):
    """Test _get_active_observations() parsing."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_redis = MagicMock()
        self.reflector = Reflector(redis_client=self.mock_redis)

    def test_get_active_observations_parses_json(self):
        """Test observations are parsed from JSON."""
        observations = [
            {"content": "Test 1", "timestamp": "2026-04-09T10:00:00Z"},
            {"content": "Test 2", "timestamp": "2026-04-09T11:00:00Z"},
        ]
        self.mock_redis.zrange.return_value = [json.dumps(obs) for obs in observations]

        result = self.reflector._get_active_observations("test-session")

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["content"], "Test 1")
        self.assertEqual(result[1]["content"], "Test 2")

    def test_get_active_observations_handles_invalid_json(self):
        """Test invalid JSON is skipped with warning."""
        valid_obs = {"content": "Valid", "timestamp": "2026-04-09T10:00:00Z"}
        self.mock_redis.zrange.return_value = [
            json.dumps(valid_obs),
            "invalid json",
            '{"incomplete": ',
        ]

        result = self.reflector._get_active_observations("test-session")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["content"], "Valid")


class TestGetTokenCountFromObservations(unittest.TestCase):
    """Test _get_token_count_from_observations() calculation."""

    def setUp(self):
        """Set up test fixtures."""
        self.reflector = Reflector()

    def test_token_count_calculation(self):
        """Test word-based token estimation (words * 1.3)."""
        observations = [
            {"content": "Hello world this is a test"},  # 6 words -> 7.8 -> 7 tokens
            {"content": "Another message"},  # 2 words -> 2.6 -> 2 tokens
        ]

        result = self.reflector._get_token_count_from_observations(observations)

        # 6 * 1.3 = 7.8 -> 7, 2 * 1.3 = 2.6 -> 2, total = 9
        self.assertEqual(result, 9)


class TestFeatureFlagChecks(unittest.TestCase):
    """Test feature flag checking methods."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_redis = MagicMock()
        self.reflector = Reflector(redis_client=self.mock_redis)

    def test_is_feature_enabled_returns_true(self):
        """Test _is_feature_enabled returns True when flag is 'true'."""
        self.mock_redis.get.return_value = "true"

        result = self.reflector._is_feature_enabled()

        self.assertTrue(result)

    def test_is_feature_enabled_returns_false(self):
        """Test _is_feature_enabled returns False when flag is 'false'."""
        self.mock_redis.get.return_value = "false"

        result = self.reflector._is_feature_enabled()

        self.assertFalse(result)

    def test_is_feature_enabled_case_insensitive(self):
        """Test flag check is case insensitive."""
        self.mock_redis.get.return_value = "TRUE"

        result = self.reflector._is_feature_enabled()

        self.assertTrue(result)

    def test_is_feature_enabled_redis_unavailable(self):
        """Test returns False when Redis is unavailable."""
        self.mock_redis.get.side_effect = Exception("Connection failed")

        result = self.reflector._is_feature_enabled()

        self.assertFalse(result)


class TestConsolidationResult(unittest.TestCase):
    """Test consolidation result structure."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_redis = MagicMock()
        self.mock_qdrant = MagicMock()
        self.mock_llm = MagicMock()
        self.reflector = Reflector(
            redis_client=self.mock_redis,
            qdrant_client=self.mock_qdrant,
            llm_client=self.mock_llm,
        )

    def test_consolidation_result_structure(self):
        """Test result dict contains expected keys."""
        self.mock_redis.get.return_value = "true"

        observations = [
            {
                "content": ("word " * 3000).strip(),
                "timestamp": datetime.now(UTC).isoformat(),
                "source_message_ids": ["1"],
            }
            for _ in range(10)
        ]
        self.mock_redis.zrange.return_value = [json.dumps(obs) for obs in observations]
        self.mock_redis.zcard.return_value = 10
        self.mock_redis.hget.return_value = None

        self.mock_llm.consolidate.return_value = {
            "content": "Consolidated content",
            "raw_tokens": 40000,
            "consolidated_tokens": 1000,
            "priority": "high",
            "category": "decision",
        }

        result = self.reflector.consolidate_observations("test-session", dry_run=True)

        self.assertIn("status", result)
        self.assertIn("session_id", result)
        self.assertIn("content", result)
        self.assertIn("raw_tokens", result)
        self.assertIn("consolidated_tokens", result)
        self.assertIn("compression_ratio", result)
        self.assertIn("observation_count", result)


if __name__ == "__main__":
    unittest.main()
