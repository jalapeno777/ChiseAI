"""Tests for FeatureStore."""

import pytest

from market_analysis.indicators.feature_store import FeatureStore


class TestFeatureStore:
    """Test cases for FeatureStore."""

    @pytest.fixture
    def store(self):
        """Create fresh FeatureStore instance."""
        return FeatureStore(prefix="test", default_ttl=60)

    def test_set_and_get(self, store):
        """Test basic set and get operations."""
        store.set("key1", {"value": 123})
        result = store.get("key1")
        assert result == {"value": 123}

    def test_get_nonexistent(self, store):
        """Test getting non-existent key."""
        result = store.get("nonexistent")
        assert result is None

    def test_delete(self, store):
        """Test delete operation."""
        store.set("key1", "value")
        assert store.delete("key1") is True
        assert store.get("key1") is None

    def test_exists(self, store):
        """Test exists check."""
        store.set("key1", "value")
        assert store.exists("key1") is True
        assert store.exists("nonexistent") is False

    def test_mget(self, store):
        """Test batch get."""
        store.set("key1", "value1")
        store.set("key2", "value2")
        results = store.mget(["key1", "key2", "key3"])
        assert results["key1"] == "value1"
        assert results["key2"] == "value2"
        assert results["key3"] is None

    def test_mset(self, store):
        """Test batch set."""
        results = store.mset({"key1": "value1", "key2": "value2"})
        assert results["key1"] is True
        assert results["key2"] is True
        assert store.get("key1") == "value1"
        assert store.get("key2") == "value2"
