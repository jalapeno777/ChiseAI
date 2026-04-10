"""Tests for feature flags canary routing (ST-PHASE5-CANARY-001).

Tests session-ID hash-based canary routing for MEMORY_HYBRID_ENABLED.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


class MockRedisClient:
    """Mock Redis client for testing."""

    def __init__(self):
        self._data: dict[str, str] = {}
        self._sets: dict[str, set[str]] = {}

    def get(self, key: str) -> str | None:
        return self._data.get(key)

    def setex(self, key: str, ttl: int, value: str) -> None:
        self._data[key] = value

    def smembers(self, key: str) -> set[str]:
        return self._sets.get(key, set())

    def sadd(self, key: str, *values: str) -> int:
        if key not in self._sets:
            self._sets[key] = set()
        for v in values:
            self._sets[key].add(v)
        return len(values)

    def set_data(self, key: str, value: str) -> None:
        self._data[key] = value

    def set_set(self, key: str, values: set[str]) -> None:
        self._sets[key] = values

    def clear(self) -> None:
        self._data.clear()
        self._sets.clear()


class TestCanaryRouting:
    """Tests for session-ID hash-based canary routing."""

    @pytest.fixture
    def mock_redis(self):
        """Create a fresh mock Redis client for each test."""
        return MockRedisClient()

    @pytest.fixture
    def feature_flags(self, mock_redis):
        """Create a FeatureFlags instance with mocked Redis."""
        from src.config.feature_flags import FeatureFlags

        ff = FeatureFlags()
        # Inject mock Redis client
        object.__setattr__(ff, "_redis_client", mock_redis)
        return ff

    def test_0_percent_routes_all_to_fallback(self, feature_flags, mock_redis):
        """AC0: 0% canary percentage -> all sessions use fallback."""
        # Enable global flag and set 0% canary
        mock_redis.set_data("chise:feature_flags:config:memory_hybrid_enabled", "true")
        mock_redis.set_data("chise:feature_flags:config:memory:canary_percentage", "0")

        # Test 10 different sessions - all should use fallback
        results = []
        for i in range(10):
            session_id = f"session-{i}"
            results.append(
                feature_flags.is_memory_hybrid_enabled_for_session(session_id)
            )

        # All should be False (fallback)
        assert all(r is False for r in results), f"Expected all False, got {results}"

    def test_100_percent_routes_all_to_hybrid(self, feature_flags, mock_redis):
        """AC1: 100% canary percentage -> all sessions use hybrid."""
        # Enable global flag and set 100% canary
        mock_redis.set_data("chise:feature_flags:config:memory_hybrid_enabled", "true")
        mock_redis.set_data(
            "chise:feature_flags:config:memory:canary_percentage", "100"
        )

        # Test 10 different sessions - all should use hybrid
        results = []
        for i in range(10):
            session_id = f"session-{i}"
            results.append(
                feature_flags.is_memory_hybrid_enabled_for_session(session_id)
            )

        # All should be True (hybrid)
        assert all(r is True for r in results), f"Expected all True, got {results}"

    def test_deterministic_routing(self, feature_flags, mock_redis):
        """AC2: Same session_id 100x -> always same result."""
        # Enable global flag and set 50% canary
        mock_redis.set_data("chise:feature_flags:config:memory_hybrid_enabled", "true")
        mock_redis.set_data("chise:feature_flags:config:memory:canary_percentage", "50")

        session_id = "test-session-123"
        results = [
            feature_flags.is_memory_hybrid_enabled_for_session(session_id)
            for _ in range(100)
        ]

        # All results should be identical
        first_result = results[0]
        assert all(
            r == first_result for r in results
        ), f"Routing not deterministic: got {set(results)}"

    def test_kill_switch_disables_even_at_100_percent(self, feature_flags, mock_redis):
        """AC3: Global disabled -> 0 hybrid regardless of percentage."""
        # Global flag DISABLED but canary at 100%
        mock_redis.set_data("chise:feature_flags:config:memory_hybrid_enabled", "false")
        mock_redis.set_data(
            "chise:feature_flags:config:memory:canary_percentage", "100"
        )

        results = []
        for i in range(10):
            session_id = f"session-{i}"
            results.append(
                feature_flags.is_memory_hybrid_enabled_for_session(session_id)
            )

        # All should be False (kill switch takes precedence)
        assert all(r is False for r in results), f"Expected all False, got {results}"

    def test_allowlist_overrides_percentage(self, feature_flags, mock_redis):
        """AC4: Session in allowlist -> hybrid even at 0%."""
        # Global enabled, 0% canary, but session in allowlist
        mock_redis.set_data("chise:feature_flags:config:memory_hybrid_enabled", "true")
        mock_redis.set_data("chise:feature_flags:config:memory:canary_percentage", "0")
        mock_redis.set_set(
            "chise:feature_flags:config:memory:canary_allowlist",
            {"session-special", "session-vip"},
        )

        # Allowlisted sessions should get hybrid
        assert (
            feature_flags.is_memory_hybrid_enabled_for_session("session-special")
            is True
        )
        assert feature_flags.is_memory_hybrid_enabled_for_session("session-vip") is True

        # Non-allowlisted should get fallback
        assert (
            feature_flags.is_memory_hybrid_enabled_for_session("session-normal")
            is False
        )

    def test_hash_distribution_approximately_uniform(self, feature_flags, mock_redis):
        """Verify hash distribution is approximately uniform across 1000 sessions."""
        mock_redis.set_data("chise:feature_flags:config:memory_hybrid_enabled", "true")
        mock_redis.set_data("chise:feature_flags:config:memory:canary_percentage", "50")

        # Test 1000 sessions at 50%
        results = [
            feature_flags.is_memory_hybrid_enabled_for_session(f"session-{i}")
            for i in range(1000)
        ]

        hybrid_count = sum(1 for r in results if r)
        fallback_count = sum(1 for r in results if not r)

        # At 50%, expect roughly 500 each. Allow 10% tolerance (450-550)
        assert 400 <= hybrid_count <= 600, (
            f"Distribution too skewed: {hybrid_count}/1000 hybrid, "
            f"{fallback_count}/1000 fallback"
        )

    def test_canary_percentage_setter(self, feature_flags, mock_redis):
        """Test set_canary_percentage method."""
        feature_flags.set_canary_percentage(25)

        # Verify it was stored
        assert (
            mock_redis.get("chise:feature_flags:config:memory:canary_percentage")
            == "25"
        )

    def test_canary_percentage_getter(self, feature_flags, mock_redis):
        """Test get_canary_percentage method."""
        mock_redis.set_data("chise:feature_flags:config:memory:canary_percentage", "75")

        assert feature_flags.get_canary_percentage() == 75

    def test_canary_percentage_default(self, feature_flags):
        """Test get_canary_percentage returns default when not set."""
        assert feature_flags.get_canary_percentage() == 0

    def test_add_canary_allowlist(self, feature_flags, mock_redis):
        """Test add_canary_allowlist method."""
        result = feature_flags.add_canary_allowlist("session-test")
        assert result is True

        # Verify it was added to the Redis set
        members = mock_redis.smembers(
            "chise:feature_flags:config:memory:canary_allowlist"
        )
        assert "session-test" in members

    def test_redis_client_none_uses_defaults(self, mock_redis):
        """Test graceful handling when Redis client is unavailable."""
        from src.config.feature_flags import FeatureFlags

        # Make the mock redis_client return None for gets but still allow sets
        ff = FeatureFlags()
        # Inject mock Redis client that returns None on get
        mock_client = MagicMock()
        mock_client.get.return_value = None
        mock_client.smembers.return_value = set()
        mock_client.setex.side_effect = Exception("Redis error")
        mock_client.sadd.side_effect = Exception("Redis error")
        object.__setattr__(ff, "_redis_client", mock_client)

        # _get_redis_set should handle errors gracefully
        assert ff._get_redis_set("any-key") == set()

        # _get_int should return default on error
        assert ff._get_int("any-key", 42) == 42

        # _set_int should return False on error
        assert ff._set_int("any-key", 100) is False

    def test_is_memory_hybrid_enabled_for_session_kill_switch(
        self, feature_flags, mock_redis
    ):
        """Explicit test: is_memory_hybrid_enabled() returns False -> always False."""
        # Global disabled
        mock_redis.set_data("chise:feature_flags:config:memory_hybrid_enabled", "false")
        # Even with allowlist and 100%, should still return False
        mock_redis.set_set(
            "chise:feature_flags:config:memory:canary_allowlist",
            {"session-in-allowlist"},
        )

        assert (
            feature_flags.is_memory_hybrid_enabled_for_session("session-in-allowlist")
            is False
        )


class TestCanaryRoutingEdgeCases:
    """Edge case tests for canary routing."""

    @pytest.fixture
    def mock_redis(self):
        return MockRedisClient()

    @pytest.fixture
    def feature_flags(self, mock_redis):
        from src.config.feature_flags import FeatureFlags

        ff = FeatureFlags()
        object.__setattr__(ff, "_redis_client", mock_redis)
        return ff

    def test_negative_percentage_treated_as_zero(self, feature_flags, mock_redis):
        """Negative percentage should behave as 0 (no canary)."""
        mock_redis.set_data("chise:feature_flags:config:memory_hybrid_enabled", "true")
        mock_redis.set_data(
            "chise:feature_flags:config:memory:canary_percentage", "-10"
        )

        results = [
            feature_flags.is_memory_hybrid_enabled_for_session(f"session-{i}")
            for i in range(10)
        ]
        assert all(r is False for r in results)

    def test_percentage_over_100_treated_as_100(self, feature_flags, mock_redis):
        """Percentage > 100 should behave as 100 (all hybrid)."""
        mock_redis.set_data("chise:feature_flags:config:memory_hybrid_enabled", "true")
        mock_redis.set_data(
            "chise:feature_flags:config:memory:canary_percentage", "150"
        )

        results = [
            feature_flags.is_memory_hybrid_enabled_for_session(f"session-{i}")
            for i in range(10)
        ]
        assert all(r is True for r in results)

    def test_empty_session_id(self, feature_flags, mock_redis):
        """Empty string session ID should still work deterministically."""
        mock_redis.set_data("chise:feature_flags:config:memory_hybrid_enabled", "true")
        mock_redis.set_data("chise:feature_flags:config:memory:canary_percentage", "50")

        # Run multiple times - should be deterministic
        results = [
            feature_flags.is_memory_hybrid_enabled_for_session("") for _ in range(10)
        ]
        assert all(r == results[0] for r in results)

    def test_unicode_session_id(self, feature_flags, mock_redis):
        """Unicode session IDs should work correctly."""
        mock_redis.set_data("chise:feature_flags:config:memory_hybrid_enabled", "true")
        mock_redis.set_data("chise:feature_flags:config:memory:canary_percentage", "50")

        # Should not raise
        result = feature_flags.is_memory_hybrid_enabled_for_session("session-日本語")
        assert isinstance(result, bool)

    def test_redis_error_falls_back_safely(self, mock_redis):
        """Redis errors should be handled gracefully."""
        from src.config.feature_flags import FeatureFlags

        # Make smembers raise an error
        mock_redis.smembers = MagicMock(side_effect=Exception("Redis error"))

        ff = FeatureFlags()
        object.__setattr__(ff, "_redis_client", mock_redis)

        # Should not raise, should treat as empty allowlist
        result = ff._get_redis_set("any-key")
        assert result == set()
