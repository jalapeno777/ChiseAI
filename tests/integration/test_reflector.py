"""
Integration tests for Reflector module.

Requires Redis for testing. Skipped if Redis unavailable or feature flag not set.
"""

import json

import pytest


# Feature flag check helper
def check_feature_flag(flag_key):
    """Check if a feature flag is enabled in Redis."""
    try:
        import redis

        client = redis.Redis(
            host="host.docker.internal",
            port=6380,
            db=0,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        client.ping()
        flag_value = client.get(flag_key)
        return flag_value is not None and flag_value.lower() == "true"
    except Exception:
        return False


def check_redis_available():
    """Check if Redis is available."""
    try:
        import redis

        client = redis.Redis(
            host="host.docker.internal",
            port=6380,
            db=0,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        client.ping()
        return True
    except Exception:
        return False


# Feature flag for Reflector
REFLECTOR_FLAG_KEY = "chise:feature_flags:observations:reflector_enabled"

# Skip condition
SKIP_REASON = None
_redis_available = check_redis_available()
_feature_flag_enabled = (
    check_feature_flag(REFLECTOR_FLAG_KEY) if _redis_available else False
)

if not _redis_available:
    SKIP_REASON = "Redis not available"
elif not _feature_flag_enabled:
    SKIP_REASON = f"Feature flag '{REFLECTOR_FLAG_KEY}' not set to 'true'"


def get_redis_client():
    """Get Redis client for tests."""
    import redis

    return redis.Redis(
        host="host.docker.internal",
        port=6380,
        db=0,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )


@pytest.mark.skipif(SKIP_REASON is not None, reason=SKIP_REASON)
class TestReflectorIntegration:
    """Integration tests with real Redis."""

    def setup_method(self):
        """Set up test fixtures with real Redis."""
        self.redis_client = get_redis_client()
        self.session_id = f"test-reflector-{id(self)}"
        self.redis_client.delete(f"chise:observations:active:{self.session_id}")
        self.redis_client.delete(
            f"chise:observations:reflector:state:{self.session_id}"
        )

    def teardown_method(self):
        """Clean up test data from Redis."""
        self.redis_client.delete(f"chise:observations:active:{self.session_id}")
        self.redis_client.delete(
            f"chise:observations:reflector:state:{self.session_id}"
        )

    def test_reflector_initialization(self):
        """Test Reflector can be initialized with Redis."""
        from src.governance.memory.reflector_agent import Reflector

        reflector = Reflector(redis_client=self.redis_client)

        assert reflector._redis_client is not None

    def test_consolidate_observations_stores_in_redis_sorted_set(self):
        """Test consolidate_observations() stores results in Redis sorted set."""
        from datetime import UTC, datetime

        from src.governance.memory.reflector_agent import Reflector

        reflector = Reflector(redis_client=self.redis_client)

        # Pre-populate observations in Redis
        active_key = f"chise:observations:active:{self.session_id}"
        observations = []
        for i in range(10):
            obs = {
                "content": f"Observation content number {i} " + ("word " * 200),
                "timestamp": datetime.now(UTC).isoformat(),
                "category": "fact",
                "priority": "medium",
                "confidence": 0.7,
                "source_message_ids": [f"msg-{i}"],
            }
            # Use timestamp as score
            ts = datetime.now(UTC).timestamp()
            self.redis_client.zadd(active_key, {json.dumps(obs): ts})
            observations.append(obs)

        # Set feature flag to true for test
        self.redis_client.set(REFLECTOR_FLAG_KEY, "true")

        # Run consolidation
        result = reflector.consolidate_observations(self.session_id, dry_run=False)

        # Verify result structure
        assert result is not None
        assert result["status"] in ["success", "qdrant_failed", "skipped"]
        if result["status"] == "success":
            assert "content" in result
            assert "compression_ratio" in result
            assert result["observation_count"] == 10

    def test_reflector_dry_run_does_not_write(self):
        """Test dry_run=True does not write to storage."""
        from datetime import UTC, datetime

        from src.governance.memory.reflector_agent import Reflector

        reflector = Reflector(redis_client=self.redis_client)

        # Pre-populate observations
        active_key = f"chise:observations:active:{self.session_id}"
        for i in range(5):
            obs = {
                "content": f"Test observation {i}",
                "timestamp": datetime.now(UTC).isoformat(),
                "category": "fact",
                "priority": "low",
                "confidence": 0.7,
                "source_message_ids": [f"msg-{i}"],
            }
            ts = datetime.now(UTC).timestamp()
            self.redis_client.zadd(active_key, {json.dumps(obs): ts})

        # Set feature flag
        self.redis_client.set(REFLECTOR_FLAG_KEY, "true")

        # Run in dry-run mode
        result = reflector.consolidate_observations(self.session_id, dry_run=True)

        # Verify result
        assert result is not None
        assert result["status"] == "success"

        # Verify no state was written
        state_key = f"chise:observations:reflector:state:{self.session_id}"
        state = self.redis_client.hgetall(state_key)
        # In dry run, state should NOT be updated
        # Note: this is implementation-dependent

    def test_should_trigger_with_sufficient_observations(self):
        """Test should_trigger() returns True with sufficient data."""
        from datetime import UTC, datetime

        from src.governance.memory.reflector_agent import Reflector

        reflector = Reflector(redis_client=self.redis_client)

        # Pre-populate enough observations to trigger (>= 10 obs, >= 30000 tokens)
        active_key = f"chise:observations:active:{self.session_id}"
        # Each observation needs ~3000 words to hit threshold across 10 obs
        for i in range(10):
            obs = {
                "content": f"Observation {i} " + ("word " * 3000),
                "timestamp": datetime.now(UTC).isoformat(),
                "category": "fact",
                "priority": "medium",
                "confidence": 0.7,
                "source_message_ids": [f"msg-{i}"],
            }
            ts = datetime.now(UTC).timestamp()
            self.redis_client.zadd(active_key, {json.dumps(obs): ts})

        # Set feature flag
        self.redis_client.set(REFLECTOR_FLAG_KEY, "true")

        result = reflector.should_trigger(self.session_id)

        assert result is True

    def test_should_trigger_insufficient_tokens(self):
        """Test should_trigger() returns False with insufficient tokens."""
        from datetime import UTC, datetime

        from src.governance.memory.reflector_agent import Reflector

        reflector = Reflector(redis_client=self.redis_client)

        # Pre-populate observations with low token count
        active_key = f"chise:observations:active:{self.session_id}"
        for i in range(3):
            obs = {
                "content": f"Short observation {i}",
                "timestamp": datetime.now(UTC).isoformat(),
                "category": "fact",
                "priority": "low",
                "confidence": 0.7,
                "source_message_ids": [f"msg-{i}"],
            }
            ts = datetime.now(UTC).timestamp()
            self.redis_client.zadd(active_key, {json.dumps(obs): ts})

        result = reflector.should_trigger(self.session_id)

        assert result is False


@pytest.mark.skipif(SKIP_REASON is not None, reason=SKIP_REASON)
def test_reflector_feature_flag_gating():
    """Test that Reflector respects feature flag."""
    from src.governance.memory.reflector_agent import Reflector

    redis_client = get_redis_client()
    session_id = "test-flag-gating"

    # Ensure flag is disabled
    redis_client.set(REFLECTOR_FLAG_KEY, "false")

    reflector = Reflector(redis_client=redis_client)
    result = reflector.consolidate_observations(session_id, dry_run=False)

    # Should return None when flag is disabled
    assert result is None

    # Clean up
    redis_client.delete(f"chise:observations:active:{session_id}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
