"""Comprehensive integration tests for the neuro-symbolic system.

Tests cover:
- Component Registry
- Integration Layer
- Event Bus
- Component Adapters
- NeuroSymbolicOrchestrator
- End-to-end pipeline
"""

from unittest.mock import Mock

import pytest

# Integration layer tests
from src.neuro_symbolic.integration.layer import (
    ComponentAdapter,
    DataConverter,
    Event,
    EventBus,
    EventType,
    IntegrationError,
    IntegrationLayer,
)

# Registry tests
from src.neuro_symbolic.integration.registry import (
    ComponentRegistry,
    ComponentStatus,
    ComponentType,
)

# Orchestrator tests
from src.neuro_symbolic.orchestrator.orchestrator import (
    NeuroSymbolicOrchestrator,
    OrchestratorConfig,
    OrchestratorResult,
)

# =============================================================================
# Component Registry Tests
# =============================================================================


class TestComponentRegistry:
    """Tests for ComponentRegistry."""

    def test_registry_initialization(self):
        """Test registry initializes correctly."""
        registry = ComponentRegistry()
        assert len(registry) == 0
        assert "ComponentRegistry" in str(registry)

    def test_register_component(self):
        """Test registering a component."""
        registry = ComponentRegistry()

        class MockComponent:
            pass

        info = registry.register(
            component_id="test_component",
            component_type=ComponentType.REASONING,
            component_class=MockComponent,
            version="1.0.0",
            description="Test component",
        )

        assert info.component_id == "test_component"
        assert info.component_type == ComponentType.REASONING
        assert info.version == "1.0.0"
        assert len(registry) == 1

    def test_register_duplicate_fails(self):
        """Test that registering duplicate ID fails."""
        registry = ComponentRegistry()

        class MockComponent:
            pass

        registry.register(
            component_id="test",
            component_type=ComponentType.REASONING,
            component_class=MockComponent,
        )

        with pytest.raises(ValueError, match="already registered"):
            registry.register(
                component_id="test",
                component_type=ComponentType.EXPLAINABILITY,
                component_class=MockComponent,
            )

    def test_unregister_component(self):
        """Test unregistering a component."""
        registry = ComponentRegistry()

        class MockComponent:
            pass

        registry.register(
            component_id="test",
            component_type=ComponentType.REASONING,
            component_class=MockComponent,
        )

        assert registry.unregister("test") is True
        assert len(registry) == 0

    def test_unregister_nonexistent(self):
        """Test unregistering non-existent component."""
        registry = ComponentRegistry()
        assert registry.unregister("nonexistent") is False

    def test_get_component_info(self):
        """Test getting component info."""
        registry = ComponentRegistry()

        class MockComponent:
            pass

        registry.register(
            component_id="test",
            component_type=ComponentType.REASONING,
            component_class=MockComponent,
        )

        info = registry.get_info("test")
        assert info is not None
        assert info.component_id == "test"

    def test_get_nonexistent_info(self):
        """Test getting info for non-existent component."""
        registry = ComponentRegistry()
        assert registry.get_info("nonexistent") is None

    def test_get_by_type(self):
        """Test getting components by type."""
        registry = ComponentRegistry()

        class MockComponent:
            pass

        registry.register(
            component_id="reasoning1",
            component_type=ComponentType.REASONING,
            component_class=MockComponent,
        )
        registry.register(
            component_id="reasoning2",
            component_type=ComponentType.REASONING,
            component_class=MockComponent,
        )
        registry.register(
            component_id="learning1",
            component_type=ComponentType.LEARNING,
            component_class=MockComponent,
        )

        reasoning = registry.get_by_type(ComponentType.REASONING)
        assert len(reasoning) == 2

        learning = registry.get_by_type(ComponentType.LEARNING)
        assert len(learning) == 1

    def test_initialize_component(self):
        """Test initializing a component."""
        registry = ComponentRegistry()

        class MockComponent:
            def __init__(self, value=10):
                self.value = value

        registry.register(
            component_id="test",
            component_type=ComponentType.REASONING,
            component_class=MockComponent,
        )

        instance = registry.initialize("test", value=20)
        assert instance is not None
        assert instance.value == 20

        info = registry.get_info("test")
        assert info.status == ComponentStatus.READY

    def test_initialize_nonexistent_fails(self):
        """Test initializing non-existent component fails."""
        registry = ComponentRegistry()

        with pytest.raises(KeyError):
            registry.initialize("nonexistent")

    def test_initialize_all(self):
        """Test initializing all components."""
        registry = ComponentRegistry()

        class MockComponent:
            def __init__(self):
                self.initialized = True

        registry.register(
            component_id="comp1",
            component_type=ComponentType.REASONING,
            component_class=MockComponent,
        )
        registry.register(
            component_id="comp2",
            component_type=ComponentType.LEARNING,
            component_class=MockComponent,
            dependencies=["comp1"],
        )

        instances = registry.initialize_all()
        assert len(instances) == 2

    def test_shutdown_component(self):
        """Test shutting down a component."""
        registry = ComponentRegistry()

        class MockComponent:
            def shutdown(self):
                self.shutdown_called = True

        registry.register(
            component_id="test",
            component_type=ComponentType.REASONING,
            component_class=MockComponent,
        )

        registry.initialize("test")
        assert registry.shutdown("test") is True

        info = registry.get_info("test")
        assert info.instance is None

    def test_enable_disable(self):
        """Test enabling and disabling components."""
        registry = ComponentRegistry()

        class MockComponent:
            pass

        registry.register(
            component_id="test",
            component_type=ComponentType.REASONING,
            component_class=MockComponent,
        )

        assert registry.disable("test") is True
        info = registry.get_info("test")
        assert info.status == ComponentStatus.DISABLED

        assert registry.enable("test") is True
        assert info.status == ComponentStatus.REGISTERED

    def test_check_dependencies(self):
        """Test dependency checking."""
        registry = ComponentRegistry()

        class MockComponent:
            pass

        registry.register(
            component_id="dep1",
            component_type=ComponentType.REASONING,
            component_class=MockComponent,
        )
        registry.register(
            component_id="main",
            component_type=ComponentType.LEARNING,
            component_class=MockComponent,
            dependencies=["dep1"],
        )

        # Initialize the dependency so its status is READY
        registry.initialize("dep1")

        satisfied, missing = registry.check_dependencies("main")
        assert satisfied is True
        assert len(missing) == 0

    def test_check_dependencies_missing(self):
        """Test dependency checking with missing dependency."""
        registry = ComponentRegistry()

        class MockComponent:
            pass

        registry.register(
            component_id="main",
            component_type=ComponentType.LEARNING,
            component_class=MockComponent,
            dependencies=["missing_dep"],
        )

        satisfied, missing = registry.check_dependencies("main")
        assert satisfied is False
        assert "missing_dep" in missing

    def test_get_status(self):
        """Test getting registry status."""
        registry = ComponentRegistry()

        class MockComponent:
            pass

        registry.register(
            component_id="test",
            component_type=ComponentType.REASONING,
            component_class=MockComponent,
        )

        status = registry.get_status()
        assert status["total_components"] == 1
        assert "reasoning" in status["types"]

    def test_contains(self):
        """Test __contains__ method."""
        registry = ComponentRegistry()

        class MockComponent:
            pass

        registry.register(
            component_id="test",
            component_type=ComponentType.REASONING,
            component_class=MockComponent,
        )

        assert "test" in registry
        assert "nonexistent" not in registry

    def test_len(self):
        """Test __len__ method."""
        registry = ComponentRegistry()

        class MockComponent:
            pass

        registry.register(
            component_id="test",
            component_type=ComponentType.REASONING,
            component_class=MockComponent,
        )

        assert len(registry) == 1


# =============================================================================
# Event Bus Tests
# =============================================================================


class TestEventBus:
    """Tests for EventBus."""

    def test_event_bus_initialization(self):
        """Test event bus initializes correctly."""
        bus = EventBus()
        stats = bus.get_statistics()
        assert stats["total_events"] == 0
        assert stats["history_size"] == 0

    def test_subscribe_and_publish(self):
        """Test subscribing to events and publishing."""
        bus = EventBus()
        received = []

        def handler(event):
            received.append(event)

        bus.subscribe(EventType.SIGNAL_GENERATED, handler)
        bus.publish(EventType.SIGNAL_GENERATED, "source", {"data": "test"})

        assert len(received) == 1
        assert received[0].source == "source"

    def test_unsubscribe(self):
        """Test unsubscribing from events."""
        bus = EventBus()
        received = []

        def handler(event):
            received.append(event)

        unsubscribe = bus.subscribe(EventType.SIGNAL_GENERATED, handler)
        bus.publish(EventType.SIGNAL_GENERATED, "source", {})
        assert len(received) == 1

        unsubscribe()
        bus.publish(EventType.SIGNAL_GENERATED, "source", {})
        assert len(received) == 1  # No new events

    def test_subscribe_all(self):
        """Test subscribing to all events."""
        bus = EventBus()
        received = []

        def handler(event):
            received.append(event)

        bus.subscribe_all(handler)
        bus.publish(EventType.SIGNAL_GENERATED, "source", {})
        bus.publish(EventType.PREDICTION_MADE, "source", {})

        assert len(received) == 2

    def test_event_history(self):
        """Test event history tracking."""
        bus = EventBus(max_history=10)

        for i in range(15):
            bus.publish(EventType.SIGNAL_GENERATED, "source", {"index": i})

        history = bus.get_history()
        assert len(history) == 10  # Max history respected

    def test_get_history_filtered(self):
        """Test filtered event history."""
        bus = EventBus()

        bus.publish(EventType.SIGNAL_GENERATED, "source1", {})
        bus.publish(EventType.PREDICTION_MADE, "source2", {})
        bus.publish(EventType.SIGNAL_GENERATED, "source3", {})

        filtered = bus.get_history(event_type=EventType.SIGNAL_GENERATED)
        assert len(filtered) == 2

        filtered_source = bus.get_history(source="source2")
        assert len(filtered_source) == 1

    def test_clear_history(self):
        """Test clearing event history."""
        bus = EventBus()
        bus.publish(EventType.SIGNAL_GENERATED, "source", {})
        bus.clear_history()

        history = bus.get_history()
        assert len(history) == 0

    def test_event_to_dict(self):
        """Test event serialization."""
        event = Event(
            event_type=EventType.SIGNAL_GENERATED,
            source="test_source",
            data={"key": "value"},
        )

        d = event.to_dict()
        assert d["event_type"] == "signal_generated"
        assert d["source"] == "test_source"
        assert d["data"]["key"] == "value"


class TestDataConverter:
    """Tests for DataConverter."""

    def test_to_market_data(self):
        """Test converting to market data format."""
        data = {"price": 100.0, "volume": 1000, "high": 105, "low": 95}
        result = DataConverter.to_market_data(data)

        assert result["price"] == 100.0
        assert result["volume"] == 1000
        assert result["high"] == 105
        assert result["low"] == 95

    def test_to_market_data_defaults(self):
        """Test market data with missing fields."""
        data = {"close": 100.0}
        result = DataConverter.to_market_data(data)

        assert result["price"] == 100.0
        assert result["volume"] == 0

    def test_to_signal_format(self):
        """Test converting to signal format."""
        result = DataConverter.to_signal_format(
            prediction="buy",
            confidence=0.8,
            features={"rsi": 30},
        )

        assert result["prediction"] == "buy"
        assert result["confidence"] == 0.8
        assert result["features"]["rsi"] == 30

    def test_to_signal_format_confidence_clamping(self):
        """Test confidence clamping in signal format."""
        result = DataConverter.to_signal_format("buy", 1.5)
        assert result["confidence"] == 1.0

        result = DataConverter.to_signal_format("buy", -0.5)
        assert result["confidence"] == 0.0

    def test_to_explanation_format(self):
        """Test converting to explanation format."""
        result = DataConverter.to_explanation_format(
            summary="Test explanation",
            reasoning_chain=[{"step": 1}],
            key_factors={"factor1": 0.5},
            confidence=0.9,
        )

        assert result["summary"] == "Test explanation"
        assert len(result["reasoning_chain"]) == 1
        assert result["key_factors"]["factor1"] == 0.5

    def test_to_fusion_input(self):
        """Test converting to fusion input format."""
        result = DataConverter.to_fusion_input(
            signals={"technical": 0.8, "sentiment": 0.6},
            confidences={"technical": 0.9, "sentiment": 0.7},
        )

        assert result["signals"]["technical"] == 0.8
        assert result["confidences"]["technical"] == 0.9

    def test_to_learning_format(self):
        """Test converting to learning format."""
        result = DataConverter.to_learning_format(
            outcome={"pnl": 100, "pnl_pct": 0.1, "success": True}
        )

        assert result["outcome"]["pnl"] == 100
        assert result["outcome"]["success"] is True


class TestIntegrationLayer:
    """Tests for IntegrationLayer."""

    def test_layer_initialization(self):
        """Test integration layer initializes correctly."""
        layer = IntegrationLayer()
        status = layer.get_status()

        assert status["adapter_count"] == 0
        assert status["pipeline_stages"] == 0

    def test_register_adapter(self):
        """Test registering an adapter."""
        layer = IntegrationLayer()

        # Create mock adapter
        adapter = Mock(spec=ComponentAdapter)
        adapter.component_id = "test"
        adapter.is_ready = True

        layer.register_adapter("test", adapter)

        assert layer.get_adapter("test") == adapter

    def test_unregister_adapter(self):
        """Test unregistering an adapter."""
        layer = IntegrationLayer()

        adapter = Mock(spec=ComponentAdapter)
        adapter.component_id = "test"
        adapter.is_ready = True
        adapter.shutdown = Mock()

        layer.register_adapter("test", adapter)
        assert layer.unregister_adapter("test") is True
        assert layer.get_adapter("test") is None

    def test_initialize_all(self):
        """Test initializing all adapters."""
        layer = IntegrationLayer()

        adapter1 = Mock(spec=ComponentAdapter)
        adapter1.component_id = "test1"
        adapter1.initialize = Mock(return_value=True)

        adapter2 = Mock(spec=ComponentAdapter)
        adapter2.component_id = "test2"
        adapter2.initialize = Mock(return_value=True)

        layer.register_adapter("test1", adapter1)
        layer.register_adapter("test2", adapter2)

        results = layer.initialize_all()
        assert results["test1"] is True
        assert results["test2"] is True

    def test_set_pipeline_config(self):
        """Test setting pipeline configuration."""
        layer = IntegrationLayer()

        layer.set_pipeline_config(
            [
                ["reasoning"],
                ["fusion"],
            ]
        )

        status = layer.get_status()
        assert status["pipeline_stages"] == 2

    def test_process_stage(self):
        """Test processing a single stage."""
        layer = IntegrationLayer()

        adapter = Mock(spec=ComponentAdapter)
        adapter.component_id = "test"
        adapter.is_ready = True
        adapter.safe_process = Mock(return_value={"result": "ok"})

        layer.register_adapter("test", adapter)

        results = layer.process_stage(["test"], {"input": "data"})
        assert "test" in results
        assert results["test"]["result"] == "ok"

    def test_process_pipeline(self):
        """Test full pipeline processing."""
        layer = IntegrationLayer()

        adapter = Mock(spec=ComponentAdapter)
        adapter.component_id = "test"
        adapter.is_ready = True
        adapter.safe_process = Mock(return_value={"result": "ok", "confidence": 0.8})

        layer.register_adapter("test", adapter)
        layer.set_pipeline_config([["test"]])

        result = layer.process_pipeline({"input": "data"})
        assert "result" in result

    def process_with_component(self):
        """Test processing with specific component."""
        layer = IntegrationLayer()

        adapter = Mock(spec=ComponentAdapter)
        adapter.component_id = "test"
        adapter.is_ready = True
        adapter.safe_process = Mock(return_value={"result": "ok"})

        layer.register_adapter("test", adapter)

        result = layer.process_with_component("test", {"input": "data"})
        assert result["result"] == "ok"

    def test_process_with_nonexistent_component(self):
        """Test processing with non-existent component."""
        layer = IntegrationLayer()

        with pytest.raises(IntegrationError):
            layer.process_with_component("nonexistent", {})

    def test_broadcast_event(self):
        """Test broadcasting events."""
        layer = IntegrationLayer()
        received = []

        def handler(event):
            received.append(event)

        layer.event_bus.subscribe(EventType.SIGNAL_GENERATED, handler)
        layer.broadcast_event(EventType.SIGNAL_GENERATED, {"data": "test"})

        assert len(received) == 1

    def test_shutdown(self):
        """Test shutting down integration layer."""
        layer = IntegrationLayer()

        adapter = Mock(spec=ComponentAdapter)
        adapter.component_id = "test"
        adapter.shutdown = Mock()

        layer.register_adapter("test", adapter)
        layer.shutdown()

        adapter.shutdown.assert_called_once()


# =============================================================================
# Orchestrator Tests
# =============================================================================


class TestOrchestrator:
    """Tests for NeuroSymbolicOrchestrator."""

    def test_orchestrator_initialization(self):
        """Test orchestrator initializes correctly."""
        orch = NeuroSymbolicOrchestrator()
        status = orch.get_component_status()

        assert len(status["components"]) == 6
        assert "hybrid_reasoning" in status["components"]

    def test_orchestrator_with_config(self):
        """Test orchestrator with custom config."""
        config = OrchestratorConfig(
            enable_pattern_detection=False,
            enable_fusion=False,
        )
        orch = NeuroSymbolicOrchestrator(config)

        stats = orch.get_statistics()
        assert stats["config"]["pattern_detection"] is False
        assert stats["config"]["fusion"] is False

    def test_process_signal(self):
        """Test processing a signal."""
        orch = NeuroSymbolicOrchestrator()

        result = orch.process_signal(
            {
                "price": 100.0,
                "volume": 1000,
                "high": 105,
                "low": 95,
            }
        )

        assert result.prediction in ["buy", "sell", "hold"]
        assert 0.0 <= result.confidence <= 1.0
        assert "hybrid_reasoning" in result.components_used

    def test_process_signal_returns_result(self):
        """Test that process_signal returns OrchestratorResult."""
        orch = NeuroSymbolicOrchestrator()

        result = orch.process_signal({"price": 100, "volume": 1000})

        assert isinstance(result, OrchestratorResult)
        assert result.prediction is not None
        assert result.explanation is not None

    def process_signal_with_pattern_detection(self):
        """Test signal processing with pattern detection enabled."""
        config = OrchestratorConfig(enable_pattern_detection=True)
        orch = NeuroSymbolicOrchestrator(config)

        result = orch.process_signal(
            {
                "price": 100,
                "volume": 1000,
                "prices": [100 + i for i in range(50)],
            }
        )

        assert "pattern_recognition" in result.components_used

    def process_signal_without_pattern_detection(self):
        """Test signal processing with pattern detection disabled."""
        config = OrchestratorConfig(enable_pattern_detection=False)
        orch = NeuroSymbolicOrchestrator(config)

        result = orch.process_signal({"price": 100, "volume": 1000})

        assert "pattern_recognition" not in result.components_used

    def process_signal_with_fusion(self):
        """Test signal processing with fusion enabled."""
        config = OrchestratorConfig(enable_fusion=True)
        orch = NeuroSymbolicOrchestrator(config)

        result = orch.process_signal({"price": 100, "volume": 1000})

        assert "fusion" in result.components_used
        assert result.fused_signal is not None

    def process_signal_with_explanation(self):
        """Test signal processing generates explanation."""
        config = OrchestratorConfig(enable_explanation=True)
        orch = NeuroSymbolicOrchestrator(config)

        result = orch.process_signal({"price": 100, "volume": 1000})

        assert "explainability" in result.components_used
        assert result.explanation is not None

    def test_process_feedback(self):
        """Test processing feedback for learning."""
        orch = NeuroSymbolicOrchestrator()

        result = orch.process_feedback(
            {
                "pnl": 100,
                "pnl_pct": 0.1,
                "success": True,
                "symbol": "BTC",
            }
        )

        assert "feedback_processed" in result or "learning_disabled" in result

    def test_process_feedback_disabled(self):
        """Test feedback processing when disabled."""
        config = OrchestratorConfig(enable_learning=False)
        orch = NeuroSymbolicOrchestrator(config)

        result = orch.process_feedback({"pnl": 100})

        assert result.get("learning_disabled") is True

    def test_get_explanation(self):
        """Test getting explanation."""
        orch = NeuroSymbolicOrchestrator()

        orch.process_signal({"price": 100, "volume": 1000})
        explanation = orch.get_explanation()

        assert "summary" in explanation

    def test_get_explanation_no_signal(self):
        """Test getting explanation when no signal processed."""
        orch = NeuroSymbolicOrchestrator()

        explanation = orch.get_explanation()

        assert "No signal" in explanation["summary"]

    def test_get_component_status(self):
        """Test getting component status."""
        orch = NeuroSymbolicOrchestrator()

        status = orch.get_component_status()

        assert "components" in status
        assert "registry_status" in status
        assert "integration_status" in status

    def test_get_statistics(self):
        """Test getting orchestrator statistics."""
        orch = NeuroSymbolicOrchestrator()

        stats = orch.get_statistics()

        assert stats["processing_count"] == 0
        assert "config" in stats
        assert "event_bus_stats" in stats

    def test_reset_state(self):
        """Test resetting orchestrator state."""
        orch = NeuroSymbolicOrchestrator()

        orch.process_signal({"price": 100, "volume": 1000})
        orch.reset_state()

        stats = orch.get_statistics()
        assert stats["processing_count"] == 0
        assert stats["last_prediction"] is None

    def test_shutdown(self):
        """Test shutting down orchestrator."""
        orch = NeuroSymbolicOrchestrator()
        orch.shutdown()

        # Should not raise

    def test_repr(self):
        """Test string representation."""
        orch = NeuroSymbolicOrchestrator()

        repr_str = repr(orch)
        assert "NeuroSymbolicOrchestrator" in repr_str
        assert "components=6" in repr_str


class TestOrchestratorResult:
    """Tests for OrchestratorResult."""

    def test_result_creation(self):
        """Test creating a result."""
        result = OrchestratorResult(
            prediction="buy",
            confidence=0.8,
            explanation={"summary": "Test"},
        )

        assert result.prediction == "buy"
        assert result.confidence == 0.8

    def test_result_to_dict(self):
        """Test converting result to dict."""
        result = OrchestratorResult(
            prediction="buy",
            confidence=0.8,
            explanation={"summary": "Test"},
            components_used=["reasoning"],
        )

        d = result.to_dict()

        assert d["prediction"] == "buy"
        assert d["confidence"] == 0.8
        assert d["components_used"] == ["reasoning"]
        assert "timestamp" in d


class TestOrchestratorConfig:
    """Tests for OrchestratorConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = OrchestratorConfig()

        assert config.enable_pattern_detection is True
        assert config.enable_fusion is True
        assert config.enable_learning is True
        assert config.enable_explanation is True

    def test_custom_config(self):
        """Test custom configuration values."""
        config = OrchestratorConfig(
            reasoning_feature_dim=64,
            pattern_confidence_threshold=0.8,
            enable_fusion=False,
        )

        assert config.reasoning_feature_dim == 64
        assert config.pattern_confidence_threshold == 0.8
        assert config.enable_fusion is False


# =============================================================================
# End-to-End Integration Tests
# =============================================================================


class TestEndToEndIntegration:
    """End-to-end integration tests."""

    def test_full_pipeline(self):
        """Test the complete pipeline from input to output."""
        orch = NeuroSymbolicOrchestrator()

        # Process a signal
        result = orch.process_signal(
            {
                "price": 50000,
                "volume": 1000000,
                "high": 51000,
                "low": 49000,
                "open": 49500,
                "close": 50000,
                "sma_short": 49800,
                "sma_long": 49500,
                "rsi": 45,
            }
        )

        # Verify complete result
        assert result.prediction in ["buy", "sell", "hold"]
        assert result.confidence >= 0
        assert result.explanation is not None
        assert len(result.components_used) >= 1
        assert result.processing_time_ms > 0

    def test_multiple_signals(self):
        """Test processing multiple signals."""
        orch = NeuroSymbolicOrchestrator()

        results = []
        for i in range(5):
            result = orch.process_signal(
                {
                    "price": 100 + i * 10,
                    "volume": 1000 + i * 100,
                }
            )
            results.append(result)

        assert len(results) == 5
        stats = orch.get_statistics()
        assert stats["processing_count"] == 5

    def test_learning_from_feedback(self):
        """Test that learning is triggered from feedback."""
        config = OrchestratorConfig(enable_learning=True)
        orch = NeuroSymbolicOrchestrator(config)

        # Process signal
        orch.process_signal({"price": 100, "volume": 1000})

        # Provide feedback
        feedback_result = orch.process_feedback(
            {
                "pnl": 100,
                "pnl_pct": 0.1,
                "success": True,
                "strategy_id": "test",
            }
        )

        assert feedback_result is not None

    def test_component_communication_via_events(self):
        """Test that components communicate via events."""
        orch = NeuroSymbolicOrchestrator()

        # Process signal to generate events
        orch.process_signal({"price": 100, "volume": 1000})

        # Check event bus has events
        stats = orch.get_statistics()
        event_stats = stats["event_bus_stats"]

        assert event_stats["total_events"] > 0

    def test_error_handling_with_fallbacks(self):
        """Test error handling with fallbacks enabled."""
        config = OrchestratorConfig(enable_fallbacks=True)
        orch = NeuroSymbolicOrchestrator(config)

        # Process with minimal data - should still return a result
        result = orch.process_signal({})

        # Should not crash, return fallback result
        assert result is not None
        assert result.prediction in ["buy", "sell", "hold"]

    def test_performance_timing(self):
        """Test that processing completes in reasonable time."""
        import time

        orch = NeuroSymbolicOrchestrator()

        start = time.time()
        orch.process_signal({"price": 100, "volume": 1000})
        elapsed = time.time() - start

        # Should complete in under 5 seconds
        assert elapsed < 5.0

    def test_state_isolation(self):
        """Test that reset properly isolates state."""
        orch = NeuroSymbolicOrchestrator()

        # Process signals
        orch.process_signal({"price": 100, "volume": 1000})
        orch.process_signal({"price": 200, "volume": 2000})

        # Reset
        orch.reset_state()

        # Check state is reset
        stats = orch.get_statistics()
        assert stats["processing_count"] == 0
        assert stats["last_prediction"] is None


if __name__ == "__main__":
    pytest.main([__file__])
