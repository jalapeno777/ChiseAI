"""Tests for PluginRegistry."""

import pytest

from market_analysis.indicators.base import BaseIndicator
from market_analysis.indicators.registry import PluginRegistry


class MockIndicatorA(BaseIndicator):
    """Mock indicator A."""

    @property
    def description(self):
        return "Mock A"

    @property
    def parameters(self):
        return {}

    def compute(self, data):
        return {}

    def validate(self, data):
        return True

    def get_metadata(self):
        return {}


class MockIndicatorB(BaseIndicator):
    """Mock indicator B."""

    @property
    def description(self):
        return "Mock B"

    @property
    def parameters(self):
        return {}

    def compute(self, data):
        return {}

    def validate(self, data):
        return True

    def get_metadata(self):
        return {}


class TestPluginRegistry:
    """Test cases for PluginRegistry."""

    @pytest.fixture
    def registry(self):
        """Create fresh registry."""
        return PluginRegistry()

    def test_register(self, registry):
        """Test registering an indicator."""
        registry.register(MockIndicatorA)
        assert registry.get("MockIndicatorA") == MockIndicatorA

    def test_register_with_custom_name(self, registry):
        """Test registering with custom name."""
        registry.register(MockIndicatorA, name="CustomA")
        assert registry.get("CustomA") == MockIndicatorA

    def test_register_duplicate(self, registry):
        """Test registering duplicate raises error."""
        registry.register(MockIndicatorA)
        with pytest.raises(ValueError):
            registry.register(MockIndicatorA)

    def test_register_invalid_class(self, registry):
        """Test registering non-BaseIndicator raises error."""

        class NotAnIndicator:
            pass

        with pytest.raises(TypeError):
            registry.register(NotAnIndicator)

    def test_unregister(self, registry):
        """Test unregistering."""
        registry.register(MockIndicatorA)
        assert registry.unregister("MockIndicatorA") is True
        assert registry.get("MockIndicatorA") is None

    def test_unregister_nonexistent(self, registry):
        """Test unregistering non-existent."""
        assert registry.unregister("nonexistent") is False

    def test_list_all(self, registry):
        """Test listing all indicators."""
        registry.register(MockIndicatorA)
        registry.register(MockIndicatorB)
        indicators = registry.list_all()
        assert "MockIndicatorA" in indicators
        assert "MockIndicatorB" in indicators

    def test_get_instance(self, registry):
        """Test getting indicator instance."""
        registry.register(MockIndicatorA)
        instance = registry.get_instance("MockIndicatorA")
        assert isinstance(instance, MockIndicatorA)

    def test_get_instance_caching(self, registry):
        """Test instance caching."""
        registry.register(MockIndicatorA)
        instance1 = registry.get_instance("MockIndicatorA")
        instance2 = registry.get_instance("MockIndicatorA")
        assert instance1 is instance2
