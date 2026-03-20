"""Plugin registry for dynamic indicator loading."""

import importlib
import inspect
import logging
from typing import Any

from market_analysis.indicators.base import BaseIndicator

logger = logging.getLogger(__name__)


class PluginRegistry:
    """Registry for indicator plugins with dynamic loading.

    Supports entry point-based plugin discovery and manual registration.
    """

    ENTRY_POINT_GROUP = "indicators.plugins"

    def __init__(self) -> None:
        """Initialize empty registry."""
        self._indicators: dict[str, type[BaseIndicator]] = {}
        self._instances: dict[str, BaseIndicator] = {}

    def register(
        self, indicator_class: type[BaseIndicator], name: str | None = None
    ) -> None:
        """Register an indicator class.

        Args:
            indicator_class: Class inheriting from BaseIndicator
            name: Optional custom name (defaults to class name)

        Raises:
            TypeError: If class doesn't inherit from BaseIndicator
            ValueError: If name already registered
        """
        if not issubclass(indicator_class, BaseIndicator):
            raise TypeError(f"{indicator_class} must inherit from BaseIndicator")

        indicator_name = name or indicator_class.__name__

        if indicator_name in self._indicators:
            raise ValueError(f"Indicator '{indicator_name}' already registered")

        self._indicators[indicator_name] = indicator_class
        logger.debug(f"Registered indicator: {indicator_name}")

    def unregister(self, name: str) -> bool:
        """Unregister an indicator.

        Args:
            name: Indicator name

        Returns:
            True if unregistered, False if not found
        """
        if name in self._indicators:
            del self._indicators[name]
            self._instances.pop(name, None)
            logger.debug(f"Unregistered indicator: {name}")
            return True
        return False

    def get(self, name: str) -> type[BaseIndicator] | None:
        """Get indicator class by name.

        Args:
            name: Indicator name

        Returns:
            Indicator class or None if not found
        """
        return self._indicators.get(name)

    def get_instance(self, name: str, **kwargs: Any) -> BaseIndicator | None:
        """Get or create indicator instance.

        Args:
            name: Indicator name
            **kwargs: Constructor arguments

        Returns:
            Indicator instance or None if not found
        """
        # Return cached instance if exists with same kwargs
        cache_key = f"{name}:{hash(frozenset(kwargs.items()))}"
        if cache_key in self._instances:
            return self._instances[cache_key]

        indicator_class = self.get(name)
        if indicator_class is None:
            return None

        instance = indicator_class(**kwargs)
        self._instances[cache_key] = instance
        return instance

    def list_all(self) -> dict[str, type[BaseIndicator]]:
        """List all registered indicators.

        Returns:
            Dictionary mapping names to indicator classes
        """
        return dict(self._indicators)

    def load_entry_points(self) -> int:
        """Load indicators from entry points.

        Returns:
            Number of indicators loaded
        """
        count = 0
        try:
            from importlib.metadata import entry_points

            eps = entry_points()
            if hasattr(eps, "select"):
                # Python 3.10+
                indicator_eps = eps.select(group=self.ENTRY_POINT_GROUP)
            else:
                # Python 3.9 - eps is a dict-like object
                indicator_eps = eps.get(self.ENTRY_POINT_GROUP, [])  # type: ignore[arg-type]

            for ep in indicator_eps:
                try:
                    indicator_class = ep.load()
                    self.register(indicator_class, ep.name)
                    count += 1
                except Exception as e:
                    logger.error(
                        f"Failed to load indicator from entry point {ep.name}: {e}"
                    )
        except ImportError:
            logger.warning(
                "importlib.metadata not available, skipping entry point loading"
            )

        return count

    def load_module(self, module_path: str) -> int:
        """Load all indicators from a module.

        Args:
            module_path: Python module path (e.g., 'market_analysis.indicators')

        Returns:
            Number of indicators loaded
        """
        count = 0
        try:
            module = importlib.import_module(module_path)
            for _name, obj in inspect.getmembers(module):
                if (
                    inspect.isclass(obj)
                    and issubclass(obj, BaseIndicator)
                    and obj is not BaseIndicator
                    and not inspect.isabstract(obj)
                ):
                    try:
                        self.register(obj)
                        count += 1
                    except ValueError:
                        pass  # Already registered
        except ImportError as e:
            logger.error(f"Failed to import module {module_path}: {e}")

        return count


# Global registry instance
_registry: PluginRegistry | None = None


def get_registry() -> PluginRegistry:
    """Get or create global registry instance."""
    global _registry
    if _registry is None:
        _registry = PluginRegistry()
    return _registry
