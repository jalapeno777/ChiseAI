"""Integration Layer for neuro-symbolic components.

Provides adapters, data converters, event bus, and error handling
for inter-component communication.
"""

import logging
import time
import uuid
from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class EventType(Enum):
    """Types of events in the integration layer."""

    # Component lifecycle
    COMPONENT_REGISTERED = "component_registered"
    COMPONENT_INITIALIZED = "component_initialized"
    COMPONENT_ERROR = "component_error"
    COMPONENT_SHUTDOWN = "component_shutdown"

    # Data flow
    DATA_PRODUCED = "data_produced"
    DATA_CONSUMED = "data_consumed"
    DATA_TRANSFORMED = "data_transformed"

    # Pipeline
    PIPELINE_STARTED = "pipeline_started"
    PIPELINE_COMPLETED = "pipeline_completed"
    PIPELINE_ERROR = "pipeline_error"

    # Processing
    SIGNAL_GENERATED = "signal_generated"
    PREDICTION_MADE = "prediction_made"
    EXPLANATION_GENERATED = "explanation_generated"
    FEEDBACK_RECEIVED = "feedback_received"


@dataclass
class Event:
    """Event for inter-component communication."""

    event_type: EventType
    source: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "event_type": self.event_type.value,
            "source": self.source,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
            "event_id": self.event_id,
            "metadata": self.metadata,
        }


class IntegrationError(Exception):
    """Base exception for integration layer errors."""

    def __init__(
        self,
        message: str,
        component_id: str | None = None,
        original_error: Exception | None = None,
    ):
        super().__init__(message)
        self.component_id = component_id
        self.original_error = original_error


class DataConversionError(IntegrationError):
    """Error during data conversion."""


class ComponentNotReadyError(IntegrationError):
    """Component is not ready for operation."""


class EventBus:
    """Event bus for inter-component communication.

    Provides publish-subscribe pattern for loose coupling between components.

    Example:
        >>> bus = EventBus()
        >>> bus.subscribe(EventType.SIGNAL_GENERATED, my_handler)
        >>> bus.publish(EventType.SIGNAL_GENERATED, "source", {"signal": "buy"})
    """

    def __init__(self, max_history: int = 1000):
        """Initialize the event bus.

        Args:
            max_history: Maximum number of events to keep in history
        """
        self._subscribers: dict[EventType, list[Callable[[Event], None]]] = defaultdict(
            list
        )
        self._wildcard_subscribers: list[Callable[[Event], None]] = []
        self._history: list[Event] = []
        self._max_history = max_history
        self._event_count = 0
        logger.info("EventBus initialized with max_history=%d", max_history)

    def subscribe(
        self,
        event_type: EventType,
        handler: Callable[[Event], None],
    ) -> Callable[[], None]:
        """Subscribe to events of a specific type.

        Args:
            event_type: Type of events to subscribe to
            handler: Function to call when event is received

        Returns:
            Unsubscribe function
        """
        self._subscribers[event_type].append(handler)
        logger.debug("Subscribed handler to %s events", event_type.value)

        def unsubscribe():
            if handler in self._subscribers[event_type]:
                self._subscribers[event_type].remove(handler)

        return unsubscribe

    def subscribe_all(self, handler: Callable[[Event], None]) -> Callable[[], None]:
        """Subscribe to all events.

        Args:
            handler: Function to call when any event is received

        Returns:
            Unsubscribe function
        """
        self._wildcard_subscribers.append(handler)
        logger.debug("Subscribed handler to all events")

        def unsubscribe():
            if handler in self._wildcard_subscribers:
                self._wildcard_subscribers.remove(handler)

        return unsubscribe

    def publish(
        self,
        event_type: EventType,
        source: str,
        data: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Event:
        """Publish an event to all subscribers.

        Args:
            event_type: Type of event
            source: Source component ID
            data: Event data
            metadata: Additional metadata

        Returns:
            The published Event
        """
        event = Event(
            event_type=event_type,
            source=source,
            data=data or {},
            metadata=metadata or {},
        )

        # Store in history
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history :]

        self._event_count += 1

        # Notify type-specific subscribers
        for handler in self._subscribers[event_type]:
            try:
                handler(event)
            except Exception as e:
                logger.error("Error in event handler for %s: %s", event_type.value, e)

        # Notify wildcard subscribers
        for handler in self._wildcard_subscribers:
            try:
                handler(event)
            except Exception as e:
                logger.error("Error in wildcard event handler: %s", e)

        logger.debug(
            "Published %s event from %s (subscribers=%d)",
            event_type.value,
            source,
            len(self._subscribers[event_type]) + len(self._wildcard_subscribers),
        )

        return event

    def get_history(
        self,
        event_type: EventType | None = None,
        source: str | None = None,
        limit: int = 100,
    ) -> list[Event]:
        """Get event history.

        Args:
            event_type: Filter by event type (optional)
            source: Filter by source (optional)
            limit: Maximum number of events to return

        Returns:
            List of matching events
        """
        events = self._history

        if event_type:
            events = [e for e in events if e.event_type == event_type]
        if source:
            events = [e for e in events if e.source == source]

        return events[-limit:]

    def clear_history(self) -> None:
        """Clear event history."""
        self._history.clear()
        logger.info("Event history cleared")

    def get_statistics(self) -> dict[str, Any]:
        """Get event bus statistics.

        Returns:
            Dictionary with statistics
        """
        type_counts = defaultdict(int)
        for event in self._history:
            type_counts[event.event_type.value] += 1

        return {
            "total_events": self._event_count,
            "history_size": len(self._history),
            "subscriber_counts": {
                et.value: len(handlers)
                for et, handlers in self._subscribers.items()
                if handlers
            },
            "wildcard_subscribers": len(self._wildcard_subscribers),
            "event_type_counts": dict(type_counts),
        }


class DataConverter:
    """Converts data between different formats for component interoperability.

    Provides conversion methods for common data types used across components.
    """

    @staticmethod
    def to_market_data(data: dict[str, Any]) -> dict[str, Any]:
        """Convert input data to standard market data format.

        Args:
            data: Input data dictionary

        Returns:
            Standardized market data dictionary
        """
        return {
            "price": data.get("price", data.get("close", 0.0)),
            "volume": data.get("volume", 0),
            "high": data.get("high", data.get("price", 0.0)),
            "low": data.get("low", data.get("price", 0.0)),
            "open": data.get("open", data.get("price", 0.0)),
            "close": data.get("close", data.get("price", 0.0)),
            "timestamp": data.get("timestamp", datetime.now(UTC).isoformat()),
            "symbol": data.get("symbol", "UNKNOWN"),
        }

    @staticmethod
    def to_signal_format(
        prediction: str,
        confidence: float,
        features: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Convert to standard signal format.

        Args:
            prediction: Signal prediction (buy/sell/hold)
            confidence: Confidence score (0-1)
            features: Feature dictionary
            metadata: Additional metadata

        Returns:
            Standardized signal dictionary
        """
        return {
            "prediction": prediction.lower(),
            "confidence": max(0.0, min(1.0, confidence)),
            "features": features or {},
            "metadata": metadata or {},
            "timestamp": datetime.now(UTC).isoformat(),
        }

    @staticmethod
    def to_explanation_format(
        summary: str,
        reasoning_chain: list[dict[str, Any]] | None = None,
        key_factors: dict[str, float] | None = None,
        confidence: float = 0.0,
    ) -> dict[str, Any]:
        """Convert to standard explanation format.

        Args:
            summary: Explanation summary text
            reasoning_chain: List of reasoning steps
            key_factors: Dictionary of factor names to importance
            confidence: Overall confidence

        Returns:
            Standardized explanation dictionary
        """
        return {
            "summary": summary,
            "reasoning_chain": reasoning_chain or [],
            "key_factors": key_factors or {},
            "overall_confidence": confidence,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    @staticmethod
    def to_fusion_input(
        signals: dict[str, float],
        confidences: dict[str, float] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Convert to fusion engine input format.

        Args:
            signals: Dictionary of signal source to value
            confidences: Dictionary of source to confidence
            context: Additional context

        Returns:
            Fusion-ready input dictionary
        """
        return {
            "signals": signals,
            "confidences": confidences or {k: 0.8 for k in signals},
            "context": context or {},
            "timestamp": datetime.now(UTC).isoformat(),
        }

    @staticmethod
    def to_learning_format(
        outcome: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Convert to adaptive learning input format.

        Args:
            outcome: Trade outcome dictionary
            context: Additional context

        Returns:
            Learning-ready input dictionary
        """
        return {
            "outcome": {
                "pnl": outcome.get("pnl", 0.0),
                "pnl_pct": outcome.get("pnl_pct", 0.0),
                "exit_reason": outcome.get("exit_reason", "unknown"),
                "duration": outcome.get("duration", 0),
                "success": outcome.get("success", False),
            },
            "context": context or {},
            "timestamp": datetime.now(UTC).isoformat(),
        }


class ComponentAdapter(ABC):
    """Abstract base class for component adapters.

    Adapters provide a standardized interface for integrating different
    components into the neuro-symbolic system.
    """

    def __init__(
        self,
        component_id: str,
        component_instance: Any,
        event_bus: EventBus | None = None,
    ):
        """Initialize the adapter.

        Args:
            component_id: Unique identifier for this component
            component_instance: The actual component instance
            event_bus: Optional event bus for communication
        """
        self.component_id = component_id
        self._component = component_instance
        self._event_bus = event_bus
        self._data_converter = DataConverter()
        self._is_ready = False
        self._error_count = 0
        self._last_error: str | None = None
        logger.info("ComponentAdapter initialized for '%s'", component_id)

    @property
    def is_ready(self) -> bool:
        """Check if the component is ready for operation."""
        return self._is_ready

    @property
    def component(self) -> Any:
        """Get the wrapped component instance."""
        return self._component

    def initialize(self) -> bool:
        """Initialize the component.

        Returns:
            True if initialization successful
        """
        try:
            self._initialize_component()
            self._is_ready = True
            self._publish_event(
                EventType.COMPONENT_INITIALIZED,
                {"status": "ready"},
            )
            return True
        except Exception as e:
            self._error_count += 1
            self._last_error = str(e)
            self._publish_event(
                EventType.COMPONENT_ERROR,
                {"error": str(e)},
            )
            logger.error(
                "Failed to initialize component '%s': %s",
                self.component_id,
                e,
            )
            return False

    @abstractmethod
    def _initialize_component(self) -> None:
        """Perform component-specific initialization."""
        pass

    @abstractmethod
    def process(self, data: dict[str, Any]) -> dict[str, Any]:
        """Process data through the component.

        Args:
            data: Input data

        Returns:
            Processing result
        """
        pass

    def safe_process(
        self,
        data: dict[str, Any],
        fallback: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Safely process data with error handling and fallback.

        Args:
            data: Input data
            fallback: Fallback result on error

        Returns:
            Processing result or fallback
        """
        if not self._is_ready:
            logger.warning(
                "Component '%s' not ready, using fallback", self.component_id
            )
            return fallback or {"error": "component_not_ready"}

        try:
            result = self.process(data)
            self._publish_event(
                EventType.DATA_TRANSFORMED,
                {"input_keys": list(data.keys()), "output_keys": list(result.keys())},
            )
            return result
        except Exception as e:
            self._error_count += 1
            self._last_error = str(e)
            self._publish_event(
                EventType.COMPONENT_ERROR,
                {"error": str(e), "input_data": str(data)[:200]},
            )
            logger.error(
                "Error processing in component '%s': %s",
                self.component_id,
                e,
            )
            return fallback or {"error": str(e), "component_id": self.component_id}

    def shutdown(self) -> None:
        """Shutdown the component."""
        try:
            if hasattr(self._component, "shutdown"):
                self._component.shutdown()
            elif hasattr(self._component, "close"):
                self._component.close()
            elif hasattr(self._component, "cleanup"):
                self._component.cleanup()

            self._is_ready = False
            self._publish_event(
                EventType.COMPONENT_SHUTDOWN,
                {"status": "shutdown"},
            )
            logger.info("Component '%s' shut down", self.component_id)

        except Exception as e:
            logger.error(
                "Error shutting down component '%s': %s",
                self.component_id,
                e,
            )

    def _publish_event(
        self,
        event_type: EventType,
        data: dict[str, Any] | None = None,
    ) -> Event | None:
        """Publish an event to the event bus.

        Args:
            event_type: Type of event
            data: Event data

        Returns:
            Published event or None if no bus
        """
        if self._event_bus:
            return self._event_bus.publish(
                event_type,
                self.component_id,
                data,
            )
        return None

    def get_status(self) -> dict[str, Any]:
        """Get adapter status.

        Returns:
            Status dictionary
        """
        return {
            "component_id": self.component_id,
            "is_ready": self._is_ready,
            "error_count": self._error_count,
            "last_error": self._last_error,
        }


class IntegrationLayer:
    """Main integration layer coordinating all adapters and data flow.

    Provides a unified interface for orchestrating data flow between
    all neuro-symbolic components.

    Example:
        >>> layer = IntegrationLayer()
        >>> layer.register_adapter("reasoning", reasoning_adapter)
        >>> result = layer.process_pipeline({"price": 100, "volume": 1000})
    """

    def __init__(
        self,
        event_bus: EventBus | None = None,
        enable_fallbacks: bool = True,
    ):
        """Initialize the integration layer.

        Args:
            event_bus: Optional event bus (created if not provided)
            enable_fallbacks: Whether to use fallback mechanisms
        """
        self._event_bus = event_bus or EventBus()
        self._adapters: dict[str, ComponentAdapter] = {}
        self._pipeline_config: list[list[str]] = []
        self._enable_fallbacks = enable_fallbacks
        self._data_converter = DataConverter()
        self._processing_count = 0
        logger.info("IntegrationLayer initialized (fallbacks=%s)", enable_fallbacks)

    @property
    def event_bus(self) -> EventBus:
        """Get the event bus."""
        return self._event_bus

    def register_adapter(
        self,
        component_id: str,
        adapter: ComponentAdapter,
    ) -> None:
        """Register a component adapter.

        Args:
            component_id: Unique identifier for the component
            adapter: The adapter instance
        """
        self._adapters[component_id] = adapter
        self._event_bus.publish(
            EventType.COMPONENT_REGISTERED,
            "integration_layer",
            {"component_id": component_id},
        )
        logger.info("Registered adapter '%s'", component_id)

    def unregister_adapter(self, component_id: str) -> bool:
        """Unregister a component adapter.

        Args:
            component_id: ID of the adapter to unregister

        Returns:
            True if unregistered, False if not found
        """
        if component_id not in self._adapters:
            return False

        adapter = self._adapters[component_id]
        adapter.shutdown()
        del self._adapters[component_id]
        logger.info("Unregistered adapter '%s'", component_id)
        return True

    def get_adapter(self, component_id: str) -> ComponentAdapter | None:
        """Get a registered adapter by ID.

        Args:
            component_id: ID of the adapter

        Returns:
            Adapter instance or None
        """
        return self._adapters.get(component_id)

    def initialize_all(self) -> dict[str, bool]:
        """Initialize all registered adapters.

        Returns:
            Dictionary of component_id to success status
        """
        results = {}
        for component_id, adapter in self._adapters.items():
            results[component_id] = adapter.initialize()
        return results

    def set_pipeline_config(self, stages: list[list[str]]) -> None:
        """Set the pipeline configuration.

        Args:
            stages: List of stages, each stage is a list of component IDs
                   to run in parallel
        """
        self._pipeline_config = stages
        logger.info("Pipeline configured with %d stages", len(stages))

    def process_stage(
        self,
        stage_components: list[str],
        data: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        """Process data through a single pipeline stage.

        Args:
            stage_components: List of component IDs for this stage
            data: Input data

        Returns:
            Dictionary of component_id to result
        """
        results = {}
        for component_id in stage_components:
            adapter = self._adapters.get(component_id)
            if adapter is None:
                logger.warning("Adapter '%s' not found, skipping", component_id)
                continue

            fallback = None if not self._enable_fallbacks else {"skipped": True}
            results[component_id] = adapter.safe_process(data, fallback)

        return results

    def process_pipeline(
        self,
        data: dict[str, Any],
        merge_strategy: str = "last",
    ) -> dict[str, Any]:
        """Process data through the full pipeline.

        Args:
            data: Input data
            merge_strategy: How to merge stage results ("last", "all", "best")

        Returns:
            Final processing result
        """
        start_time = time.perf_counter()
        self._processing_count += 1

        self._event_bus.publish(
            EventType.PIPELINE_STARTED,
            "integration_layer",
            {"input_keys": list(data.keys())},
        )

        current_data = data.copy()
        all_results: dict[str, dict[str, Any]] = {}

        try:
            for stage_idx, stage_components in enumerate(self._pipeline_config):
                stage_results = self.process_stage(stage_components, current_data)

                # Merge results based on strategy
                if merge_strategy == "last":
                    for result in stage_results.values():
                        if isinstance(result, dict):
                            current_data.update(result)
                elif merge_strategy == "all":
                    all_results.update(stage_results)
                elif merge_strategy == "best":
                    # Select result with highest confidence
                    best_result = None
                    best_confidence = -1
                    for result in stage_results.values():
                        if isinstance(result, dict):
                            conf = result.get("confidence", 0)
                            if conf > best_confidence:
                                best_confidence = conf
                                best_result = result
                    if best_result:
                        current_data.update(best_result)

                logger.debug(
                    "Pipeline stage %d completed with %d components",
                    stage_idx,
                    len(stage_results),
                )

            processing_time = (time.perf_counter() - start_time) * 1000

            # Prepare final result
            if merge_strategy == "all":
                final_result = all_results
            else:
                final_result = current_data

            final_result["_metadata"] = {
                "processing_time_ms": processing_time,
                "stages_completed": len(self._pipeline_config),
                "processing_count": self._processing_count,
            }

            self._event_bus.publish(
                EventType.PIPELINE_COMPLETED,
                "integration_layer",
                {"processing_time_ms": processing_time},
            )

            return final_result

        except Exception as e:
            self._event_bus.publish(
                EventType.PIPELINE_ERROR,
                "integration_layer",
                {"error": str(e)},
            )
            logger.error("Pipeline processing error: %s", e)
            raise IntegrationError(
                f"Pipeline processing failed: {e}",
                original_error=e,
            ) from e

    def process_with_component(
        self,
        component_id: str,
        data: dict[str, Any],
        fallback: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Process data through a specific component.

        Args:
            component_id: ID of the component to use
            data: Input data
            fallback: Fallback result on error

        Returns:
            Processing result
        """
        adapter = self._adapters.get(component_id)
        if adapter is None:
            raise IntegrationError(f"Component '{component_id}' not found")

        if not self._enable_fallbacks:
            fallback = None

        return adapter.safe_process(data, fallback)

    def broadcast_event(
        self,
        event_type: EventType,
        data: dict[str, Any],
    ) -> Event:
        """Broadcast an event to all subscribers.

        Args:
            event_type: Type of event
            data: Event data

        Returns:
            The published event
        """
        return self._event_bus.publish(event_type, "integration_layer", data)

    def get_status(self) -> dict[str, Any]:
        """Get integration layer status.

        Returns:
            Status dictionary
        """
        adapter_statuses = {
            cid: adapter.get_status() for cid, adapter in self._adapters.items()
        }

        ready_count = sum(1 for a in self._adapters.values() if a.is_ready)

        return {
            "adapter_count": len(self._adapters),
            "ready_adapters": ready_count,
            "pipeline_stages": len(self._pipeline_config),
            "processing_count": self._processing_count,
            "event_bus_stats": self._event_bus.get_statistics(),
            "adapters": adapter_statuses,
        }

    def shutdown(self) -> None:
        """Shutdown all adapters."""
        for adapter in self._adapters.values():
            adapter.shutdown()

        self._event_bus.clear_history()
        logger.info("IntegrationLayer shut down")
