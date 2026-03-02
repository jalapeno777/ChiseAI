"""Component Registry for neuro-symbolic system.

Provides dynamic component registration, discovery, and version management.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ComponentType(Enum):
    """Types of neuro-symbolic components."""

    REASONING = "reasoning"
    EXPLAINABILITY = "explainability"
    LEARNING = "learning"
    KNOWLEDGE_GRAPH = "knowledge_graph"
    PATTERN_RECOGNITION = "pattern_recognition"
    FUSION = "fusion"


class ComponentStatus(Enum):
    """Status of a registered component."""

    REGISTERED = "registered"
    INITIALIZING = "initializing"
    READY = "ready"
    ERROR = "error"
    DISABLED = "disabled"


@dataclass
class ComponentInfo:
    """Information about a registered component."""

    component_id: str
    component_type: ComponentType
    component_class: type
    version: str = "1.0.0"
    description: str = ""
    status: ComponentStatus = ComponentStatus.REGISTERED
    dependencies: list[str] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)
    instance: Any | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    initialized_at: datetime | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "component_id": self.component_id,
            "component_type": self.component_type.value,
            "version": self.version,
            "description": self.description,
            "status": self.status.value,
            "dependencies": self.dependencies,
            "config": self.config,
            "created_at": self.created_at.isoformat(),
            "initialized_at": (
                self.initialized_at.isoformat() if self.initialized_at else None
            ),
            "error_message": self.error_message,
            "metadata": self.metadata,
        }


class ComponentRegistry:
    """Registry for neuro-symbolic components.

    Manages component registration, discovery, lifecycle, and version control.
    Supports dynamic loading and dependency resolution.

    Example:
        >>> registry = ComponentRegistry()
        >>> registry.register(
        ...     "hybrid_reasoning",
        ...     ComponentType.REASONING,
        ...     HybridReasoningEngine,
        ...     version="1.0.0"
        ... )
        >>> engine = registry.get("hybrid_reasoning")
    """

    def __init__(self):
        """Initialize the component registry."""
        self._components: dict[str, ComponentInfo] = {}
        self._type_index: dict[ComponentType, set[str]] = {
            t: set() for t in ComponentType
        }
        self._factories: dict[str, Callable[[], Any]] = {}
        self._initialization_order: list[str] = []
        logger.info("ComponentRegistry initialized")

    def register(
        self,
        component_id: str,
        component_type: ComponentType,
        component_class: type,
        version: str = "1.0.0",
        description: str = "",
        dependencies: list[str] | None = None,
        config: dict[str, Any] | None = None,
        factory: Callable[[], Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ComponentInfo:
        """Register a component with the registry.

        Args:
            component_id: Unique identifier for the component
            component_type: Type of the component
            component_class: The component class
            version: Component version string
            description: Human-readable description
            dependencies: List of component IDs this depends on
            config: Default configuration for the component
            factory: Optional factory function for creating instances
            metadata: Additional metadata

        Returns:
            ComponentInfo for the registered component

        Raises:
            ValueError: If component_id already registered
        """
        if component_id in self._components:
            raise ValueError(f"Component '{component_id}' already registered")

        info = ComponentInfo(
            component_id=component_id,
            component_type=component_type,
            component_class=component_class,
            version=version,
            description=description,
            dependencies=dependencies or [],
            config=config or {},
            metadata=metadata or {},
        )

        self._components[component_id] = info
        self._type_index[component_type].add(component_id)

        if factory:
            self._factories[component_id] = factory

        # Update initialization order based on dependencies
        self._update_initialization_order()

        logger.info(
            "Registered component '%s' (type=%s, version=%s)",
            component_id,
            component_type.value,
            version,
        )

        return info

    def unregister(self, component_id: str) -> bool:
        """Unregister a component from the registry.

        Args:
            component_id: ID of the component to unregister

        Returns:
            True if unregistered, False if not found
        """
        if component_id not in self._components:
            return False

        info = self._components[component_id]
        self._type_index[info.component_type].discard(component_id)

        if component_id in self._factories:
            del self._factories[component_id]

        del self._components[component_id]
        self._update_initialization_order()

        logger.info("Unregistered component '%s'", component_id)
        return True

    def get(self, component_id: str) -> Any | None:
        """Get a component instance by ID.

        Args:
            component_id: ID of the component

        Returns:
            Component instance or None if not found
        """
        info = self._components.get(component_id)
        if info is None:
            return None
        return info.instance

    def get_info(self, component_id: str) -> ComponentInfo | None:
        """Get component info by ID.

        Args:
            component_id: ID of the component

        Returns:
            ComponentInfo or None if not found
        """
        return self._components.get(component_id)

    def get_all(self) -> dict[str, ComponentInfo]:
        """Get all registered components.

        Returns:
            Dictionary of component_id to ComponentInfo
        """
        return self._components.copy()

    def get_by_type(self, component_type: ComponentType) -> list[ComponentInfo]:
        """Get all components of a specific type.

        Args:
            component_type: Type to filter by

        Returns:
            List of ComponentInfo for matching components
        """
        component_ids = self._type_index.get(component_type, set())
        return [
            self._components[cid] for cid in component_ids if cid in self._components
        ]

    def initialize(
        self,
        component_id: str,
        config: dict[str, Any] | None = None,
        **kwargs,
    ) -> Any:
        """Initialize a component and create its instance.

        Args:
            component_id: ID of the component to initialize
            config: Configuration to use (merged with defaults)
            **kwargs: Additional arguments for initialization

        Returns:
            Initialized component instance

        Raises:
            KeyError: If component not found
            RuntimeError: If initialization fails
        """
        info = self._components.get(component_id)
        if info is None:
            raise KeyError(f"Component '{component_id}' not found")

        try:
            info.status = ComponentStatus.INITIALIZING

            # Merge configurations
            merged_config = {**info.config, **(config or {}), **kwargs}

            # Use factory or create instance directly
            if component_id in self._factories:
                instance = self._factories[component_id]()
            else:
                instance = info.component_class(**merged_config)

            info.instance = instance
            info.initialized_at = datetime.utcnow()
            info.status = ComponentStatus.READY

            logger.info("Initialized component '%s'", component_id)
            return instance

        except Exception as e:
            info.status = ComponentStatus.ERROR
            info.error_message = str(e)
            logger.error("Failed to initialize component '%s': %s", component_id, e)
            raise RuntimeError(f"Failed to initialize '{component_id}': {e}") from e

    def initialize_all(
        self, configs: dict[str, dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        """Initialize all registered components in dependency order.

        Args:
            configs: Optional dict of component_id to config

        Returns:
            Dictionary of component_id to instance
        """
        configs = configs or {}
        instances = {}
        errors = {}

        for component_id in self._initialization_order:
            if component_id not in self._components:
                continue

            try:
                config = configs.get(component_id, {})
                instance = self.initialize(component_id, config)
                instances[component_id] = instance
            except Exception as e:
                errors[component_id] = str(e)
                logger.error(
                    "Failed to initialize '%s' during batch init: %s",
                    component_id,
                    e,
                )

        if errors:
            logger.warning("Batch initialization completed with %d errors", len(errors))

        return instances

    def shutdown(self, component_id: str) -> bool:
        """Shutdown a component and release resources.

        Args:
            component_id: ID of the component to shutdown

        Returns:
            True if shutdown, False if not found or no instance
        """
        info = self._components.get(component_id)
        if info is None or info.instance is None:
            return False

        try:
            # Call shutdown method if available
            if hasattr(info.instance, "shutdown"):
                info.instance.shutdown()
            elif hasattr(info.instance, "close"):
                info.instance.close()
            elif hasattr(info.instance, "cleanup"):
                info.instance.cleanup()

            info.instance = None
            info.status = ComponentStatus.REGISTERED
            logger.info("Shutdown component '%s'", component_id)
            return True

        except Exception as e:
            logger.error("Error shutting down component '%s': %s", component_id, e)
            info.status = ComponentStatus.ERROR
            info.error_message = str(e)
            return False

    def shutdown_all(self) -> None:
        """Shutdown all initialized components in reverse order."""
        for component_id in reversed(self._initialization_order):
            self.shutdown(component_id)

        logger.info("All components shut down")

    def enable(self, component_id: str) -> bool:
        """Enable a disabled component.

        Args:
            component_id: ID of the component

        Returns:
            True if enabled, False if not found
        """
        info = self._components.get(component_id)
        if info is None:
            return False

        if info.status == ComponentStatus.DISABLED:
            info.status = ComponentStatus.REGISTERED
            logger.info("Enabled component '%s'", component_id)

        return True

    def disable(self, component_id: str) -> bool:
        """Disable a component.

        Args:
            component_id: ID of the component

        Returns:
            True if disabled, False if not found
        """
        info = self._components.get(component_id)
        if info is None:
            return False

        self.shutdown(component_id)
        info.status = ComponentStatus.DISABLED
        logger.info("Disabled component '%s'", component_id)
        return True

    def check_dependencies(self, component_id: str) -> tuple[bool, list[str]]:
        """Check if all dependencies for a component are satisfied.

        Args:
            component_id: ID of the component to check

        Returns:
            Tuple of (all_satisfied, missing_dependencies)
        """
        info = self._components.get(component_id)
        if info is None:
            return False, [component_id]

        missing = []
        for dep_id in info.dependencies:
            if dep_id not in self._components:
                missing.append(dep_id)
            else:
                dep_info = self._components[dep_id]
                if dep_info.status != ComponentStatus.READY:
                    missing.append(dep_id)

        return len(missing) == 0, missing

    def get_initialization_order(self) -> list[str]:
        """Get the order in which components should be initialized.

        Returns:
            List of component IDs in initialization order
        """
        return self._initialization_order.copy()

    def _update_initialization_order(self) -> None:
        """Update initialization order based on dependencies (topological sort)."""
        # Build dependency graph
        in_degree: dict[str, int] = {cid: 0 for cid in self._components}
        graph: dict[str, set[str]] = {cid: set() for cid in self._components}

        for cid, info in self._components.items():
            for dep_id in info.dependencies:
                if dep_id in self._components:
                    graph[dep_id].add(cid)
                    in_degree[cid] += 1

        # Kahn's algorithm for topological sort
        queue = [cid for cid, degree in in_degree.items() if degree == 0]
        order = []

        while queue:
            # Sort for deterministic ordering
            queue.sort()
            cid = queue.pop(0)
            order.append(cid)

            for dependent in graph[cid]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        # Handle cycles (shouldn't happen with proper registration)
        if len(order) != len(self._components):
            missing = set(self._components) - set(order)
            logger.warning(
                "Circular dependency detected, components may not initialize: %s",
                missing,
            )
            order.extend(missing)

        self._initialization_order = order

    def get_status(self) -> dict[str, Any]:
        """Get registry status summary.

        Returns:
            Dictionary with registry status information
        """
        status_counts = {s: 0 for s in ComponentStatus}
        for info in self._components.values():
            status_counts[info.status] += 1

        return {
            "total_components": len(self._components),
            "status_counts": {s.value: c for s, c in status_counts.items()},
            "types": {t.value: len(ids) for t, ids in self._type_index.items() if ids},
            "initialization_order": self._initialization_order,
        }

    def __contains__(self, component_id: str) -> bool:
        """Check if a component is registered."""
        return component_id in self._components

    def __len__(self) -> int:
        """Return number of registered components."""
        return len(self._components)

    def __repr__(self) -> str:
        """String representation."""
        ready = sum(
            1 for i in self._components.values() if i.status == ComponentStatus.READY
        )
        return f"ComponentRegistry(components={len(self)}, ready={ready})"
