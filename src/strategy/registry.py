"""Strategy registry - lightweight registration of strategy implementations.

Maps strategy names to their implementing classes and metadata.
Separate from the candidate/champion registry in backtesting/.
"""

from __future__ import annotations

from typing import Any

from strategy.contracts import StrategyMetadata


class StrategyRegistrationError(Exception):
    """Raised when a strategy registration fails."""


class StrategyNotFoundError(KeyError):
    """Raised when a requested strategy is not found in the registry."""


class StrategyRegistry:
    """Registry of available strategy implementations.

    Maps strategy names to their implementing classes/Protocol satisfiers.
    Separate from the candidate/champion registry in backtesting/.

    Usage::

        registry = StrategyRegistry()
        registry.register("momentum_v1", MomentumStrategy, metadata)
        strategy_cls, meta = registry.get("momentum_v1")
        instance = strategy_cls()
        result = instance.execute(config, data, capital)
    """

    def __init__(self) -> None:
        self._strategies: dict[str, type[Any]] = {}
        self._metadata: dict[str, StrategyMetadata] = {}

    def register(
        self,
        name: str,
        strategy_class: type[Any],
        metadata: StrategyMetadata,
    ) -> None:
        """Register a strategy implementation.

        Args:
            name: Unique strategy name for lookup.
            strategy_class: Class that satisfies StrategyProtocol.
            metadata: Strategy metadata describing the implementation.

        Raises:
            StrategyRegistrationError: If name is already registered or
                inputs are invalid.
        """
        if not name or not name.strip():
            msg = "Strategy name must be non-empty"
            raise StrategyRegistrationError(msg)

        if name in self._strategies:
            msg = (
                f"Strategy '{name}' is already registered. "
                f"Use unregister() first or choose a different name."
            )
            raise StrategyRegistrationError(msg)

        if strategy_class is None:
            msg = "strategy_class must not be None"
            raise StrategyRegistrationError(msg)

        if not isinstance(metadata, StrategyMetadata):
            msg = f"metadata must be StrategyMetadata, got {type(metadata)}"
            raise StrategyRegistrationError(msg)

        self._strategies[name] = strategy_class
        self._metadata[name] = metadata

    def unregister(self, name: str) -> None:
        """Remove a strategy from the registry.

        Args:
            name: Strategy name to remove.

        Raises:
            StrategyNotFoundError: If strategy is not registered.
        """
        if name not in self._strategies:
            msg = f"Strategy '{name}' is not registered"
            raise StrategyNotFoundError(msg)

        del self._strategies[name]
        del self._metadata[name]

    def get(self, name: str) -> tuple[type[Any], StrategyMetadata]:
        """Retrieve a strategy class and its metadata.

        Args:
            name: Registered strategy name.

        Returns:
            Tuple of (strategy_class, metadata).

        Raises:
            StrategyNotFoundError: If strategy is not registered.
        """
        if name not in self._strategies:
            registered = ", ".join(self._strategies.keys()) or "(empty)"
            msg = f"Strategy '{name}' not found. Registered strategies: {registered}"
            raise StrategyNotFoundError(msg)

        return self._strategies[name], self._metadata[name]

    def list_strategies(self) -> list[str]:
        """List all registered strategy names.

        Returns:
            Sorted list of registered strategy names.
        """
        return sorted(self._strategies.keys())

    def get_metadata(self, name: str) -> StrategyMetadata:
        """Retrieve metadata for a registered strategy.

        Args:
            name: Registered strategy name.

        Returns:
            Strategy metadata.

        Raises:
            StrategyNotFoundError: If strategy is not registered.
        """
        if name not in self._metadata:
            msg = f"Strategy '{name}' not found"
            raise StrategyNotFoundError(msg)
        return self._metadata[name]

    def validate_strategy(self, name: str) -> bool:
        """Validate that a registered strategy satisfies StrategyProtocol.

        Performs runtime checks on the strategy class to verify it
        has the required protocol methods.

        Args:
            name: Registered strategy name.

        Returns:
            True if the strategy satisfies the protocol interface.

        Raises:
            StrategyNotFoundError: If strategy is not registered.
        """
        strategy_class, _ = self.get(name)

        required_methods = (
            "validate_config",
            "generate_signals",
            "execute",
        )
        for method_name in required_methods:
            if not hasattr(strategy_class, method_name):
                return False

        # Check properties
        for prop_name in ("name", "version"):
            if not hasattr(strategy_class, prop_name):
                return False

        return True

    def __len__(self) -> int:
        return len(self._strategies)

    def __contains__(self, name: str) -> bool:
        return name in self._strategies
