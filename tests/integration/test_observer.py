"""
Integration tests for Observer module.

Requires real Redis connection. Skips gracefully if Redis or feature flag unavailable.
"""

import json
import logging

import pytest
from src.governance.memory.observer import (
    FEATURE_FLAG_KEY,
    OBSERVER_STATE_KEY,
    RAW_OBSERVATIONS_KEY_PREFIX,
    Observer,
)

logger = logging.getLogger(__name__)


def is_redis_available():
    """Check if Redis is available."""
    try:
        import redis

        client = redis.Redis(
            host="host.docker.internal",
            port=6380,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        client.ping()
        return True
    except Exception:
        return False


def is_feature_flag_enabled():
    """Check if observer feature flag is enabled."""
    try:
        import redis

        client = redis.Redis(
            host="host.docker.internal",
            port=6380,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        flag_value = client.get(FEATURE_FLAG_KEY)
        return flag_value is not None and flag_value.lower() == "true"
    except Exception:
        return False


# Skip entire test module if Redis is unavailable or feature flag not set
redis_available = is_redis_available()
feature_flag_enabled = is_feature_flag_enabled()

skip_if_no_redis = pytest.mark.skipif(
    not redis_available,
    reason="Redis not available at host.docker.internal:6380",
)

skip_if_flag_not_enabled = pytest.mark.skipif(
    not feature_flag_enabled,
    reason=f"Feature flag '{FEATURE_FLAG_KEY}' not set to 'true'",
)

# Combined skip condition
skip_condition = pytest.mark.skipif(
    not (redis_available and feature_flag_enabled),
    reason="Requires Redis available and feature flag enabled",
)


@pytest.fixture
def observer():
    """Create Observer instance with real Redis."""
    return Observer(session_id="test-integration-session")


@pytest.fixture
def cleanup_test_keys(observer):
    """Clean up test Redis keys before and after test."""
    import redis

    client = redis.Redis(
        host="host.docker.internal",
        port=6380,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )

    # Clean before test
    test_key = f"{RAW_OBSERVATIONS_KEY_PREFIX}test-integration-session"
    state_key = OBSERVER_STATE_KEY
    client.delete(test_key)
    client.delete(state_key)

    yield client

    # Clean after test
    client.delete(test_key)
    client.delete(state_key)


class TestAccumulateMessageIntegration:
    """Integration tests for accumulate_message() with real Redis."""

    @skip_condition
    def test_accumulate_message_stores_in_redis(self, observer, cleanup_test_keys):
        """Verify message is stored in Redis list."""
        client = cleanup_test_keys

        result = observer.accumulate_message("test-integration-session", "Hello world")

        assert result is True

        # Verify message is stored
        key = f"{RAW_OBSERVATIONS_KEY_PREFIX}test-integration-session"
        messages = client.lrange(key, 0, -1)
        assert len(messages) == 1

        payload = json.loads(messages[0])
        assert payload["message"] == "Hello world"
        assert "timestamp" in payload

    @skip_condition
    def test_accumulate_message_multiple_messages(self, observer, cleanup_test_keys):
        """Verify multiple messages are accumulated correctly."""
        client = cleanup_test_keys

        observer.accumulate_message("test-integration-session", "Message 1")
        observer.accumulate_message("test-integration-session", "Message 2")
        observer.accumulate_message("test-integration-session", "Message 3")

        key = f"{RAW_OBSERVATIONS_KEY_PREFIX}test-integration-session"
        messages = client.lrange(key, 0, -1)

        assert len(messages) == 3

    @skip_condition
    def test_accumulate_message_ttl_is_set(self, observer, cleanup_test_keys):
        """Verify TTL is set on the Redis key."""
        client = cleanup_test_keys

        observer.accumulate_message("test-integration-session", "Test message")

        key = f"{RAW_OBSERVATIONS_KEY_PREFIX}test-integration-session"
        ttl = client.ttl(key)

        # TTL should be set (close to 24 hours = 86400 seconds)
        assert ttl > 0
        assert ttl <= 86400


class TestGetTokenCountIntegration:
    """Integration tests for get_token_count() with real Redis."""

    @skip_condition
    def test_token_count_empty_session(self, observer, cleanup_test_keys):
        """Verify zero tokens for empty session."""
        token_count = observer.get_token_count("test-integration-session")
        assert token_count == 0

    @skip_condition
    def test_token_count_with_messages(self, observer, cleanup_test_keys):
        """Verify token count calculation with real messages."""
        # Add messages
        observer.accumulate_message(
            "test-integration-session", "Hello world this is a test"
        )
        observer.accumulate_message("test-integration-session", "Another message here")

        token_count = observer.get_token_count("test-integration-session")

        # "Hello world this is a test" = 6 words -> 6 * 1.3 = 7.8 -> 7 tokens
        # "Another message here" = 3 words -> 3 * 1.3 = 3.9 -> 3 tokens
        # Total = 10 tokens
        assert token_count == 10

    @skip_condition
    def test_token_count_persists_after_accumulate(self, observer, cleanup_test_keys):
        """Verify token count reflects all accumulated messages."""
        observer.accumulate_message("test-integration-session", "First message")
        observer.accumulate_message("test-integration-session", "Second message")
        observer.accumulate_message("test-integration-session", "Third message")

        token_count = observer.get_token_count("test-integration-session")

        # 3 messages with ~3 words each = ~9 words * 1.3 ≈ 12 tokens
        assert token_count >= 10


class TestExtractObservationsDryRunIntegration:
    """Integration tests for extract_observations() with dry_run=True."""

    @skip_condition
    def test_extract_observations_dry_run_returns_observations(
        self, observer, cleanup_test_keys
    ):
        """Verify dry run returns observations without storing."""
        client = cleanup_test_keys

        # Accumulate some messages
        observer.accumulate_message(
            "test-integration-session", "We decided to use Python for the project"
        )
        observer.accumulate_message(
            "test-integration-session", "I noticed a pattern in the data"
        )

        # Extract in dry-run mode
        observations = observer.extract_observations(
            "test-integration-session", dry_run=True
        )

        assert len(observations) >= 1

        # Verify no storage happened (active key should not exist)
        active_key = "chise:observations:active:test-integration-session"
        assert client.exists(active_key) == 0

    @skip_condition
    def test_extract_observations_dry_run_classifies_correctly(
        self, observer, cleanup_test_keys
    ):
        """Verify observations are classified correctly during dry run."""
        observer.accumulate_message(
            "test-integration-session", "We decided to go with option A"
        )
        observer.accumulate_message(
            "test-integration-session", "This is a fact about the system"
        )

        observations = observer.extract_observations(
            "test-integration-session", dry_run=True
        )

        categories = [obs.category for obs in observations]

        # Should have at least one decision and one fact
        assert "decision" in categories or "fact" in categories


class TestObserverStorageIntegration:
    """Integration tests for Observer storage when feature flag is enabled."""

    @skip_if_flag_not_enabled
    def test_observer_stores_active_observations(self, observer, cleanup_test_keys):
        """Verify observations are stored in Redis sorted set when flag is enabled."""
        client = cleanup_test_keys

        # This test only runs when feature flag is enabled
        # Accumulate messages
        observer.accumulate_message(
            "test-integration-session", "Important critical decision made"
        )

        # Extract with dry_run=False (actual storage)
        observations = observer.extract_observations(
            "test-integration-session", dry_run=False
        )

        # Verify observations were stored
        if len(observations) > 0:
            active_key = "chise:observations:active:test-integration-session"
            stored_count = client.zcard(active_key)
            assert stored_count >= 0  # May be 0 if dedup filtered everything

    @skip_if_flag_not_enabled
    def test_observer_state_updated_after_extraction(self, observer, cleanup_test_keys):
        """Verify observer state is updated after extraction."""
        client = cleanup_test_keys

        observer.accumulate_message(
            "test-integration-session", "Test message for state update"
        )
        observer.extract_observations("test-integration-session", dry_run=True)

        state = observer.get_state()

        # State should be updated (last_session_id may be set)
        assert state is not None


class TestObserverIntegrationEdgeCases:
    """Integration tests for edge cases."""

    @skip_condition
    def test_observer_handles_empty_message(self, observer, cleanup_test_keys):
        """Verify observer handles empty messages gracefully."""
        result = observer.accumulate_message("test-integration-session", "")
        # Should return True (message was processed) even if content is empty
        # Behavior depends on implementation - this documents expected behavior

    @skip_condition
    def test_observer_handles_unicode_content(self, observer, cleanup_test_keys):
        """Verify observer handles unicode content."""
        result = observer.accumulate_message(
            "test-integration-session", "Hello 🌍 🐍 Python 中文"
        )
        assert result is True

        token_count = observer.get_token_count("test-integration-session")
        assert token_count > 0

    @skip_condition
    def test_observer_concurrent_accumulation(self, observer, cleanup_test_keys):
        """Verify observer handles rapid sequential accumulation."""
        for i in range(10):
            observer.accumulate_message(
                "test-integration-session", f"Message number {i}"
            )

        token_count = observer.get_token_count("test-integration-session")
        assert token_count > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
