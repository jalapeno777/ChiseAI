"""
Unit tests for Observer module.

Tests Observer class with mocked Redis and dedup engine.
"""

import json
import unittest
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from src.governance.memory.observer import (
    DEFAULT_TOKEN_THRESHOLD,
    RAW_OBSERVATIONS_KEY_PREFIX,
    RAW_OBSERVATIONS_TTL,
    Observation,
    Observer,
)


class TestObserverInit(unittest.TestCase):
    """Test Observer.__init__() defaults."""

    def test_default_initialization(self):
        """Verify Observer initializes with correct defaults."""
        observer = Observer(session_id="test-session")
        self.assertEqual(observer.session_id, "test-session")
        self.assertIsNone(observer._redis_client)
        self.assertIsNone(observer._qdrant_client)
        self.assertEqual(observer.threshold, DEFAULT_TOKEN_THRESHOLD)

    def test_custom_threshold(self):
        """Verify custom threshold is set correctly."""
        observer = Observer(session_id="test-session", threshold=50000)
        self.assertEqual(observer.threshold, 50000)

    def test_preconfigured_redis_client(self):
        """Verify pre-configured Redis client is stored."""
        mock_redis = MagicMock()
        observer = Observer(session_id="test-session", redis_client=mock_redis)
        self.assertIs(observer._redis_client, mock_redis)


class TestAccumulateMessage(unittest.TestCase):
    """Test accumulate_message() with mocked Redis."""

    def setUp(self):
        """Set up test fixtures with mocked Redis."""
        self.mock_redis = MagicMock()
        self.observer = Observer(
            session_id="test-session", redis_client=self.mock_redis
        )

    def test_accumulate_message_success(self):
        """Verify message is appended and TTL is set when feature flag is true."""
        self.mock_redis.get.return_value = "true"

        result = self.observer.accumulate_message("test-session", "Hello world")

        self.assertTrue(result)
        self.mock_redis.rpush.assert_called_once()
        self.mock_redis.expire.assert_called_once()

        # Verify the key format
        call_args = self.mock_redis.rpush.call_args[0]
        self.assertEqual(call_args[0], f"{RAW_OBSERVATIONS_KEY_PREFIX}test-session")

        # Verify payload content
        payload = json.loads(call_args[1])
        self.assertEqual(payload["message"], "Hello world")
        self.assertIn("timestamp", payload)

    def test_accumulate_message_feature_disabled(self):
        """Verify no writes when feature flag is false."""
        self.mock_redis.get.return_value = "false"

        result = self.observer.accumulate_message("test-session", "Hello world")

        self.assertFalse(result)
        self.mock_redis.rpush.assert_not_called()

    def test_accumulate_message_feature_not_set(self):
        """Verify no writes when feature flag is None."""
        self.mock_redis.get.return_value = None

        result = self.observer.accumulate_message("test-session", "Hello world")

        self.assertFalse(result)
        self.mock_redis.rpush.assert_not_called()

    def test_accumulate_message_ttl_set(self):
        """Verify correct TTL is set on the key."""
        self.mock_redis.get.return_value = "true"

        self.observer.accumulate_message("test-session", "Hello world")

        expire_call = self.mock_redis.expire.call_args[0]
        self.assertEqual(expire_call[0], f"{RAW_OBSERVATIONS_KEY_PREFIX}test-session")
        self.assertEqual(expire_call[1], RAW_OBSERVATIONS_TTL)


class TestGetTokenCount(unittest.TestCase):
    """Test get_token_count() with mocked Redis."""

    def setUp(self):
        """Set up test fixtures with mocked Redis."""
        self.mock_redis = MagicMock()
        self.observer = Observer(
            session_id="test-session", redis_client=self.mock_redis
        )

    def test_token_count_calculation(self):
        """Verify word-based token estimation (words * 1.3)."""
        # Set up mock to return two messages
        messages = [
            json.dumps({"message": "Hello world this is a test"}),
            json.dumps({"message": "Another message here"}),
        ]
        self.mock_redis.lrange.return_value = messages

        token_count = self.observer.get_token_count("test-session")

        # "Hello world this is a test" = 6 words -> 6 * 1.3 = 7.8 -> 7
        # "Another message here" = 3 words -> 3 * 1.3 = 3.9 -> 3
        # Total = 10 tokens
        self.assertEqual(token_count, 10)

    def test_token_count_empty_session(self):
        """Verify zero tokens for empty session."""
        self.mock_redis.lrange.return_value = []

        token_count = self.observer.get_token_count("test-session")

        self.assertEqual(token_count, 0)

    def test_token_count_invalid_json(self):
        """Verify graceful handling of corrupted messages."""
        messages = [
            json.dumps({"message": "Valid message"}),
            "invalid json",
        ]
        self.mock_redis.lrange.return_value = messages

        token_count = self.observer.get_token_count("test-session")

        # "Valid message" = 2 words -> 2 * 1.3 = 2.6 -> 2 tokens (invalid json skipped)
        self.assertEqual(token_count, 2)

    def test_token_count_redis_unavailable(self):
        """Verify zero return when Redis is unavailable."""
        self.observer._redis_client = None
        self.observer._redis = None

        with patch.object(self.observer, "_get_redis_client", return_value=None):
            token_count = self.observer.get_token_count("test-session")

        self.assertEqual(token_count, 0)


class TestCheckThreshold(unittest.TestCase):
    """Test check_threshold() verification."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_redis = MagicMock()
        self.observer = Observer(
            session_id="test-session", redis_client=self.mock_redis
        )

    def test_threshold_exceeded(self):
        """Verify True when token count >= threshold."""
        # 30000 / 1.3 ≈ 23077 words needed, use 25000 words
        words = ("word " * 25000).strip()
        messages = [json.dumps({"message": words})]
        self.mock_redis.lrange.return_value = messages

        result = self.observer.check_threshold("test-session")

        self.assertTrue(result)

    def test_threshold_not_exceeded(self):
        """Verify False when token count < threshold."""
        messages = [json.dumps({"message": "Hello world"})]
        self.mock_redis.lrange.return_value = messages

        result = self.observer.check_threshold("test-session")

        self.assertFalse(result)

    def test_threshold_exactly_at_limit(self):
        """Verify True when token count == threshold."""
        # 30000 / 1.3 ≈ 23077 words needed
        words = "word " * 23077
        messages = [json.dumps({"message": words})]
        self.mock_redis.lrange.return_value = messages

        result = self.observer.check_threshold("test-session")

        self.assertTrue(result)


class TestGetState(unittest.TestCase):
    """Test get_state() with mocked Redis."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_redis = MagicMock()
        self.observer = Observer(
            session_id="test-session", redis_client=self.mock_redis
        )

    def test_get_state_success(self):
        """Verify state is retrieved correctly from Redis hash."""
        self.mock_redis.hgetall.return_value = {
            "last_run": "2026-04-09T10:00:00Z",
            "token_count": "15000",
            "threshold": "30000",
        }

        state = self.observer.get_state()

        self.assertEqual(state["last_run"], "2026-04-09T10:00:00Z")
        self.assertEqual(state["token_count"], 15000)
        self.assertEqual(state["threshold"], 30000)

    def test_get_state_empty(self):
        """Verify default values when no state exists."""
        self.mock_redis.hgetall.return_value = {}

        state = self.observer.get_state()

        self.assertIsNone(state["last_run"])
        self.assertEqual(state["token_count"], 0)
        self.assertEqual(state["threshold"], DEFAULT_TOKEN_THRESHOLD)

    def test_get_state_redis_unavailable(self):
        """Verify default values when Redis unavailable."""
        self.observer._redis_client = None
        self.observer._redis = None

        with patch.object(self.observer, "_get_redis_client", return_value=None):
            state = self.observer.get_state()

        self.assertIsNone(state["last_run"])
        self.assertEqual(state["token_count"], 0)


class TestLLMExtract(unittest.TestCase):
    """Test _llm_extract() pattern-based categorization."""

    def setUp(self):
        """Set up test fixtures."""
        self.observer = Observer(session_id="test-session")

    def test_decision_category(self):
        """Verify 'decided' keyword triggers decision category."""
        messages = [{"content": "We decided to use Python", "id": "1"}]

        observations = self.observer._llm_extract(messages)

        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0]["category"], "decision")

    def test_pattern_category(self):
        """Verify 'pattern' keyword triggers pattern category."""
        messages = [{"content": "I noticed a pattern emerging", "id": "1"}]

        observations = self.observer._llm_extract(messages)

        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0]["category"], "pattern")

    def test_preference_category(self):
        """Verify 'prefer' keyword triggers preference category."""
        messages = [{"content": "I prefer tea over coffee", "id": "1"}]

        observations = self.observer._llm_extract(messages)

        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0]["category"], "preference")

    def test_event_category(self):
        """Verify 'happened' keyword triggers event category."""
        messages = [{"content": "Something happened yesterday", "id": "1"}]

        observations = self.observer._llm_extract(messages)

        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0]["category"], "event")

    def test_fact_category_default(self):
        """Verify default category is fact."""
        messages = [{"content": "This is just a simple statement", "id": "1"}]

        observations = self.observer._llm_extract(messages)

        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0]["category"], "fact")

    def test_high_priority_keywords(self):
        """Verify critical/important keywords trigger high priority."""
        messages = [
            {"content": "This is critical information", "id": "1"},
            {"content": "This is important too", "id": "2"},
        ]

        observations = self.observer._llm_extract(messages)

        self.assertEqual(observations[0]["priority"], "high")
        self.assertEqual(observations[1]["priority"], "high")

    def test_medium_priority_keywords(self):
        """Verify should/prefer keywords trigger medium priority."""
        messages = [{"content": "We should do this", "id": "1"}]

        observations = self.observer._llm_extract(messages)

        self.assertEqual(observations[0]["priority"], "medium")

    def test_low_priority_default(self):
        """Verify default priority is low."""
        messages = [{"content": "Just a simple message", "id": "1"}]

        observations = self.observer._llm_extract(messages)

        self.assertEqual(observations[0]["priority"], "low")

    def test_empty_content_skipped(self):
        """Verify empty content messages are skipped."""
        messages = [{"content": "", "id": "1"}]

        observations = self.observer._llm_extract(messages)

        self.assertEqual(len(observations), 0)

    def test_mock_confidence(self):
        """Verify mock confidence score is 0.7."""
        messages = [{"content": "A simple fact", "id": "1"}]

        observations = self.observer._llm_extract(messages)

        self.assertEqual(observations[0]["confidence"], 0.7)


class TestExtractObservationsDryRun(unittest.TestCase):
    """Test extract_observations() with dry_run=True."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_redis = MagicMock()
        self.observer = Observer(
            session_id="test-session", redis_client=self.mock_redis
        )

        # Mock the dedup engine to not filter anything
        self.mock_dedup_engine = MagicMock()
        self.mock_dedup_engine.deduplicate_content.return_value = {
            "is_duplicate": False
        }
        self.observer._dedup_engine = self.mock_dedup_engine

    def test_dry_run_no_storage(self):
        """Verify no writes to Redis when dry_run=True."""
        self.mock_redis.get.return_value = "true"
        # Use a message with recognizable keywords
        self.mock_redis.lrange.return_value = [
            "We decided to use Python for the project"
        ]

        observations = self.observer.extract_observations("test-session", dry_run=True)

        # Should still return observations
        self.assertGreater(len(observations), 0)
        # But no zadd should be called (no storage)
        self.mock_redis.zadd.assert_not_called()

    def test_dry_run_with_feature_flag_disabled(self):
        """Verify dry_run still returns observations even with flag disabled."""
        self.mock_redis.get.return_value = "false"
        # Use a message with recognizable keywords
        self.mock_redis.lrange.return_value = [
            "We decided to use Python for the project"
        ]

        observations = self.observer.extract_observations("test-session", dry_run=True)

        # Should still return observations (dry_run bypasses storage check)
        self.assertGreater(len(observations), 0)

    def test_extract_observations_parses_json_wrappers(self):
        """Verify extract_observations() parses JSON wrappers before extraction.

        This is the R1 fix: accumulate_message() stores messages as JSON like
        {"message": "...", "timestamp": "..."}. extract_observations() must parse
        this and extract the "message" field, not pass the raw JSON string.
        """
        self.mock_redis.get.return_value = "true"
        # Simulate what accumulate_message() stores: JSON-wrapped messages
        self.mock_redis.lrange.return_value = [
            json.dumps(
                {
                    "message": "We decided to use Python for the project",
                    "timestamp": "2026-04-09T10:00:00Z",
                }
            ),
            json.dumps(
                {
                    "message": "I noticed a pattern emerging in user behavior",
                    "timestamp": "2026-04-09T10:05:00Z",
                }
            ),
        ]

        observations = self.observer.extract_observations("test-session", dry_run=True)

        # Verify we got observations
        self.assertGreater(len(observations), 0)
        # R1 FIX VERIFICATION: content should be plain text, NOT a JSON blob
        for obs in observations:
            self.assertFalse(obs.content.startswith("{"))
            self.assertFalse(obs.content.endswith("}"))
            # The content should NOT be a JSON string
            self.assertNotIn('"message":', obs.content)
            self.assertNotIn('"timestamp":', obs.content)


class TestRunDedup(unittest.TestCase):
    """Test run_dedup() with mocked dedup engine."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_redis = MagicMock()
        self.observer = Observer(
            session_id="test-session", redis_client=self.mock_redis
        )

    def test_run_dedup_no_duplicates(self):
        """Verify observations pass through when not duplicates."""
        mock_dedup_engine = MagicMock()
        mock_dedup_engine.deduplicate_content.return_value = {"is_duplicate": False}
        self.observer._dedup_engine = mock_dedup_engine

        obs1 = Observation(
            content="First observation",
            timestamp=datetime.now(UTC).isoformat(),
            category="fact",
            priority="low",
            session_id="test-session",
        )

        result = self.observer.run_dedup([obs1])

        self.assertEqual(len(result), 1)

    def test_run_dedup_filters_duplicates(self):
        """Verify duplicate observations are filtered out."""
        mock_dedup_engine = MagicMock()
        mock_dedup_engine.deduplicate_content.return_value = {"is_duplicate": True}
        self.observer._dedup_engine = mock_dedup_engine

        obs1 = Observation(
            content="Duplicate content",
            timestamp=datetime.now(UTC).isoformat(),
            category="fact",
            priority="low",
            session_id="test-session",
        )

        result = self.observer.run_dedup([obs1])

        self.assertEqual(len(result), 0)

    def test_run_dedup_mixed_results(self):
        """Verify both unique and duplicate observations are handled correctly."""
        mock_dedup_engine = MagicMock()
        # First call returns non-duplicate, second returns duplicate
        mock_dedup_engine.deduplicate_content.side_effect = [
            {"is_duplicate": False},
            {"is_duplicate": True},
        ]
        self.observer._dedup_engine = mock_dedup_engine

        obs1 = Observation(
            content="Unique content",
            timestamp=datetime.now(UTC).isoformat(),
            category="fact",
            priority="low",
            session_id="test-session",
        )
        obs2 = Observation(
            content="Duplicate content",
            timestamp=datetime.now(UTC).isoformat(),
            category="fact",
            priority="low",
            session_id="test-session",
        )

        result = self.observer.run_dedup([obs1, obs2])

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].content, "Unique content")

    def test_run_dedup_empty_list(self):
        """Verify empty list returns empty list."""
        result = self.observer.run_dedup([])
        self.assertEqual(len(result), 0)


class TestExtractObservationsNonJsonFallback(unittest.TestCase):
    """Test extract_observations() JSON parse fallback."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_redis = MagicMock()
        self.observer = Observer(
            session_id="test-session", redis_client=self.mock_redis
        )
        # Mock dedup engine to not filter anything
        self.mock_dedup_engine = MagicMock()
        self.mock_dedup_engine.deduplicate_content.return_value = {
            "is_duplicate": False
        }
        self.observer._dedup_engine = self.mock_dedup_engine

    def test_extract_observations_non_json_fallback(self):
        """Test that non-JSON input falls back gracefully.

        This is the N2 fix: when lrange returns plain text (not JSON),
        the code should use the raw text as the message content rather
        than failing or producing garbage.
        """
        self.mock_redis.get.return_value = "true"

        # Mix of JSON and plain text (simulating what might be stored)
        self.mock_redis.lrange.return_value = [
            json.dumps(
                {
                    "message": "We decided to use Python for the project",
                    "timestamp": "2026-04-09T10:00:00Z",
                }
            ),
            "plain text message without JSON wrapping",  # Non-JSON fallback case
            json.dumps(
                {
                    "message": "I noticed a pattern in user behavior",
                    "timestamp": "2026-04-09T10:05:00Z",
                }
            ),
        ]

        observations = self.observer.extract_observations("test-session", dry_run=True)

        # Should get observations from all three items
        self.assertGreaterEqual(len(observations), 3)

        # Verify that plain text was handled gracefully
        # The content should be usable text, not broken JSON
        contents = [obs.content for obs in observations]
        for content in contents:
            # Should not be empty
            self.assertTrue(len(content) > 0)
            # Should not be a JSON parse error or broken text
            if not content.startswith("{"):
                # Plain text content should be preserved
                self.assertNotIn("None", content)
                self.assertNotIn("undefined", content)


class TestFeatureFlagGating(unittest.TestCase):
    """Test feature flag gating behavior."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_redis = MagicMock()
        self.observer = Observer(
            session_id="test-session", redis_client=self.mock_redis
        )

    def test_accumulate_message_blocked_when_flag_false(self):
        """Verify accumulate_message returns False when flag is 'false'."""
        self.mock_redis.get.return_value = "false"

        result = self.observer.accumulate_message("test-session", "Test message")

        self.assertFalse(result)
        self.mock_redis.rpush.assert_not_called()

    def test_accumulate_message_blocked_when_flag_none(self):
        """Verify accumulate_message returns False when flag is None."""
        self.mock_redis.get.return_value = None

        result = self.observer.accumulate_message("test-session", "Test message")

        self.assertFalse(result)

    def test_is_feature_enabled_true(self):
        """Verify _is_feature_enabled returns True when flag is 'true'."""
        self.mock_redis.get.return_value = "true"

        result = self.observer._is_feature_enabled()

        self.assertTrue(result)

    def test_is_feature_enabled_false(self):
        """Verify _is_feature_enabled returns False when flag is 'false'."""
        self.mock_redis.get.return_value = "false"

        result = self.observer._is_feature_enabled()

        self.assertFalse(result)

    def test_is_feature_enabled_case_insensitive(self):
        """Verify flag check is case insensitive."""
        self.mock_redis.get.return_value = "TRUE"

        result = self.observer._is_feature_enabled()

        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
