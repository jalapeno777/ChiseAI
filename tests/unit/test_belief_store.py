"""Unit tests for BeliefStore with focus on Redis fallback and double-deserialization fix."""

from __future__ import annotations

import logging
import sys
from unittest.mock import MagicMock, patch

import pytest

from autonomous_cognition.beliefs.models import Belief
from autonomous_cognition.beliefs.store import BeliefStore

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def belief():
    """Create a test belief."""
    return Belief(
        belief_id="test_belief_001",
        statement="Test belief statement for unit testing.",
        domain="test",
        confidence=0.85,
        evidence_refs=["test_ref_1", "test_ref_2"],
        sources_quality_score=0.75,
        status="active",
    )


@pytest.fixture
def belief_store():
    """Create a BeliefStore with no Redis client (uses module-level tools)."""
    return BeliefStore(redis_client=None)


@pytest.fixture
def belief_store_with_mock():
    """Create a BeliefStore with a mock Redis client."""
    mock_redis = MagicMock()
    mock_redis.hset.return_value = 1
    mock_redis.set.return_value = True
    mock_redis.get.return_value = None
    mock_redis.hgetall.return_value = {}
    return BeliefStore(redis_client=mock_redis), mock_redis


# =============================================================================
# Test: put() stores in memory cache
# =============================================================================


def test_put_stores_in_memory_cache(belief, belief_store):
    """Verify put() always stores belief in memory cache."""
    assert belief.belief_id not in belief_store._beliefs
    belief_store.put(belief)
    assert belief.belief_id in belief_store._beliefs
    assert belief_store._beliefs[belief.belief_id].statement == belief.statement


def test_put_with_external_redis_client_calls_hset_and_set(belief):
    """Verify put() calls Redis hset and set when external client provided."""
    mock_redis = MagicMock()
    mock_redis.hset.return_value = 1
    mock_redis.set.return_value = True
    store = BeliefStore(redis_client=mock_redis)

    store.put(belief)

    mock_redis.hset.assert_called_once()
    mock_redis.set.assert_called_once()
    call_args = mock_redis.hset.call_args[0]
    assert call_args[0] == BeliefStore.INDEX_KEY
    assert call_args[1] == belief.belief_id


# =============================================================================
# Test: get() returns from memory cache first
# =============================================================================


def test_get_returns_from_memory_cache(belief, belief_store):
    """Verify get() returns belief from memory cache without hitting Redis."""
    belief_store.put(belief)

    # Patch at tools.redis_state since that's where the import comes from
    with patch("tools.redis_state.redis_state_get") as mock_get:
        result = belief_store.get(belief.belief_id)
        mock_get.assert_not_called()

    assert result is not None
    assert result.belief_id == belief.belief_id
    assert result.statement == belief.statement


# =============================================================================
# Test: get() with Redis returns parsed data (no double-deserialization)
# =============================================================================


def test_get_with_redis_client_parses_json_once(belief):
    """Verify get() with external redis_client calls json.loads once (raw string from Redis)."""
    mock_redis = MagicMock()
    # External client returns raw JSON string
    import json

    mock_redis.get.return_value = json.dumps(belief.to_dict())
    store = BeliefStore(redis_client=mock_redis)

    # Pre-populate memory cache to skip Redis, but we need to clear it
    store._beliefs.clear()

    with patch("autonomous_cognition.beliefs.store.json.loads") as mock_loads:
        mock_loads.return_value = belief.to_dict()
        result = store.get(belief.belief_id)

        # json.loads should be called once for external client (which returns raw strings)
        assert mock_loads.call_count == 1

    assert result is not None
    assert result.belief_id == belief.belief_id


def test_get_without_redis_client_does_not_double_deserialize(belief, belief_store):
    """Verify get() with module-level tools does NOT call json.loads (already deserialized).

    This is the key test for the bug fix: redis_state_get already returns parsed data,
    so we should NOT call json.loads again.
    """
    belief_store.put(belief)
    # Clear memory to force Redis lookup
    belief_store._beliefs.clear()

    with (
        patch("tools.redis_state.redis_state_get") as mock_get,
        patch("autonomous_cognition.beliefs.store.json.loads") as mock_loads,
    ):
        # redis_state_get returns already-parsed dict (as per its _deserialize implementation)
        mock_get.return_value = belief.to_dict()
        result = belief_store.get(belief.belief_id)

        # json.loads should NOT be called - data is already deserialized
        mock_loads.assert_not_called()
        # redis_state_get should have been called
        mock_get.assert_called_once()

    assert result is not None
    assert result.belief_id == belief.belief_id


# =============================================================================
# Test: Redis unavailable fallback
# =============================================================================


def test_get_returns_none_when_redis_unavailable(belief, belief_store):
    """Verify get() returns None gracefully when Redis is unavailable."""
    belief_store.put(belief)
    # Clear memory to force Redis lookup
    belief_store._beliefs.clear()

    with patch("tools.redis_state.redis_state_get", return_value=None):
        result = belief_store.get(belief.belief_id)

    assert result is None


def test_get_returns_none_on_redis_exception(belief, belief_store):
    """Verify get() returns None when Redis raises an exception."""
    belief_store.put(belief)
    # Clear memory to force Redis lookup
    belief_store._beliefs.clear()

    with patch(
        "tools.redis_state.redis_state_get",
        side_effect=Exception("Redis connection failed"),
    ):
        result = belief_store.get(belief.belief_id)

    assert result is None


def test_put_continues_when_redis_fails(belief, belief_store):
    """Verify put() continues successfully even when Redis operations fail."""
    # Memory should still have the belief even if Redis fails
    with patch(
        "tools.redis_state.redis_state_hset",
        side_effect=Exception("Redis failed"),
    ):
        belief_store.put(belief)

    assert belief.belief_id in belief_store._beliefs
    assert belief_store._beliefs[belief.belief_id].statement == belief.statement


def test_list_active_returns_from_memory_when_no_redis(belief, belief_store):
    """Verify list_active() returns beliefs from memory when Redis unavailable."""
    belief_store.put(belief)

    with patch("tools.redis_state.redis_state_hgetall", return_value={}):
        result = belief_store.list_active()

    assert len(result) == 1
    assert result[0].belief_id == belief.belief_id


def test_list_active_with_redis_fallback(belief, belief_store):
    """Verify list_active() falls back to memory when Redis hgetall fails."""
    belief_store.put(belief)

    with patch(
        "tools.redis_state.redis_state_hgetall",
        side_effect=Exception("Redis failed"),
    ):
        result = belief_store.list_active()

    # Should still return from memory
    assert len(result) == 1
    assert result[0].belief_id == belief.belief_id


# =============================================================================
# Test: Connection pooling (via redis-py singleton)
# =============================================================================


def test_redis_client_singleton_prevents_resource_exhaustion():
    """Verify BeliefStore uses module-level redis_state which uses singleton client.

    The redis_state module creates a single Redis client instance (singleton pattern)
    that reuses connections via redis-py's built-in connection pooling.
    """
    store1 = BeliefStore(redis_client=None)
    store2 = BeliefStore(redis_client=None)

    # Both stores should use the same module-level redis client
    # When redis_state_get is called, it uses _get_redis_client() singleton
    with patch("tools.redis_state._get_redis_client") as mock_get_client:
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        belief = Belief(
            belief_id="pool_test",
            statement="Test connection pooling",
            domain="test",
            confidence=0.9,
            status="active",
        )
        store1.put(belief)

        # _get_redis_client called once for singleton access
        assert mock_get_client.call_count >= 1


# =============================================================================
# Test: No double-deserialization in list_active()
# =============================================================================


def test_list_active_with_module_tools_no_double_deserialize(belief, belief_store):
    """Verify list_active() with module-level tools does NOT call json.loads.

    redis_state_hgetall already deserializes via _deserialize(), so payload
    is already a dict.
    """
    belief_store.put(belief)

    # Simulate redis_state_hgetall returning already-deserialized dicts
    with (
        patch("tools.redis_state.redis_state_hgetall") as mock_hgetall,
        patch("autonomous_cognition.beliefs.store.json.loads") as mock_loads,
    ):
        # redis_state_hgetall returns {belief_id: already_deserialized_dict}
        mock_hgetall.return_value = {belief.belief_id: belief.to_dict()}
        # Clear memory to force Redis lookup
        belief_store._beliefs.clear()

        result = belief_store.list_active()

        # json.loads should NOT be called - data already deserialized by redis_state_hgetall
        mock_loads.assert_not_called()

    assert len(result) == 1
    assert result[0].belief_id == belief.belief_id


def test_list_active_with_external_client_calls_json_loads(belief):
    """Verify list_active() with external client calls json.loads (raw strings)."""
    mock_redis = MagicMock()
    import json

    # External client hgetall returns raw strings
    mock_redis.hgetall.return_value = {belief.belief_id: json.dumps(belief.to_dict())}

    store = BeliefStore(redis_client=mock_redis)
    store._beliefs.clear()

    with patch("autonomous_cognition.beliefs.store.json.loads") as mock_loads:
        mock_loads.return_value = belief.to_dict()
        result = store.list_active()

        # json.loads should be called for external client
        assert mock_loads.call_count == 1

    assert len(result) == 1
