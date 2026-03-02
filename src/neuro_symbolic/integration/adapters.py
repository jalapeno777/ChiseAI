"""Component adapters for the neuro-symbolic integration layer.

Provides adapters for each of the 6 core components:
- Hybrid Reasoning (ST-NS-031)
- Explainability (ST-NS-032)
- Adaptive Learning (ST-NS-033)
- Knowledge Graph (ST-NS-034)
- Pattern Recognition (ST-NS-035)
- Multi-Modal Fusion (ST-NS-036)
"""

import logging
from typing import Any

from src.neuro_symbolic.integration.layer import (
    ComponentAdapter,
    DataConverter,
    EventBus,
)

logger = logging.getLogger(__name__)


class HybridReasoningAdapter(ComponentAdapter):
    """Adapter for the Hybrid Reasoning Engine (ST-NS-031)."""

    def __init__(
        self,
        component_instance: Any,
        event_bus: EventBus | None = None,
    ):
        """Initialize the hybrid reasoning adapter.

        Args:
            component_instance: HybridReasoningEngine instance
            event_bus: Optional event bus
        """
        super().__init__("hybrid_reasoning", component_instance, event_bus)

    def _initialize_component(self) -> None:
        """Initialize the reasoning engine."""
        # Engine is usually ready on creation
        if hasattr(self._component, "reset_state"):
            self._component.reset_state()

    def process(self, data: dict[str, Any]) -> dict[str, Any]:
        """Process data through the reasoning engine.

        Args:
            data: Market data dictionary

        Returns:
            Reasoning result with prediction and confidence
        """
        # Convert to market data format
        market_data = DataConverter.to_market_data(data)

        # Process through reasoning engine
        result = self._component.reason(market_data)

        return {
            "prediction": result.prediction,
            "confidence": result.confidence,
            "trend_direction": result.trend_direction.value,
            "explanation": result.fused_result.explanation,
            "contributing_factors": result.fused_result.contributing_factors,
            "neural_confidence": result.neural_output.confidence,
            "symbolic_confidence": result.symbolic_output.overall_confidence,
            "processing_time_ms": result.processing_time_ms,
            "reasoning_metadata": result.metadata,
        }


class ExplainabilityAdapter(ComponentAdapter):
    """Adapter for the Explainability Generator (ST-NS-032)."""

    def __init__(
        self,
        component_instance: Any,
        event_bus: EventBus | None = None,
    ):
        """Initialize the explainability adapter.

        Args:
            component_instance: ExplanationGenerator instance
            event_bus: Optional event bus
        """
        super().__init__("explainability", component_instance, event_bus)

    def _initialize_component(self) -> None:
        """Initialize the explanation generator."""
        # Generator is usually ready on creation
        pass

    def process(self, data: dict[str, Any]) -> dict[str, Any]:
        """Generate explanation for a decision.

        Args:
            data: Decision data with prediction, confidence, features

        Returns:
            Explanation result
        """
        # Extract required fields
        prediction = data.get("prediction", "hold")
        confidence = data.get("confidence", 0.5)
        features = data.get("features", {})
        feature_contributions = data.get("contributing_factors", {})

        # Handle if contributing_factors is a list (from reasoning engine)
        if isinstance(feature_contributions, list):
            feature_contributions = {factor: 1.0 for factor in feature_contributions}

        # Generate explanation
        explanation = self._component.explain(
            {
                "prediction": prediction,
                "confidence": confidence,
                "features": features,
                "feature_contributions": feature_contributions,
                "metadata": data.get("metadata", {}),
            }
        )

        return {
            "explanation": explanation.to_dict(),
            "summary": explanation.summary,
            "reasoning_chain": [
                {
                    "step_number": step.step_number,
                    "description": step.description,
                    "confidence": step.confidence,
                }
                for step in explanation.reasoning_chain
            ],
            "key_factors": explanation.key_factors,
            "overall_confidence": explanation.overall_confidence,
        }


class AdaptiveLearningAdapter(ComponentAdapter):
    """Adapter for the Adaptive Learning Engine (ST-NS-033)."""

    def __init__(
        self,
        component_instance: Any,
        event_bus: EventBus | None = None,
    ):
        """Initialize the adaptive learning adapter.

        Args:
            component_instance: AdaptiveLearningEngine instance
            event_bus: Optional event bus
        """
        super().__init__("adaptive_learning", component_instance, event_bus)

    def _initialize_component(self) -> None:
        """Initialize the learning engine."""
        if hasattr(self._component, "reset"):
            self._component.reset()

    def process(self, data: dict[str, Any]) -> dict[str, Any]:
        """Process feedback or get learning status.

        Args:
            data: Either feedback data or status request

        Returns:
            Learning result or status
        """
        # Check if this is a feedback processing request
        if "outcome" in data or "pnl" in data:
            return self._process_feedback(data)
        else:
            return self._get_status()

    def _process_feedback(self, data: dict[str, Any]) -> dict[str, Any]:
        """Process trade outcome feedback.

        Args:
            data: Feedback data with outcome

        Returns:
            Feedback processing result
        """
        # Convert to learning format
        learning_data = DataConverter.to_learning_format(data)

        # Process the outcome
        strategy_id = data.get("strategy_id", "default")
        signal = self._component.process_outcome(
            strategy_id=strategy_id,
            outcome=learning_data["outcome"],
            trade_id=data.get("trade_id"),
            symbol=data.get("symbol"),
        )

        return {
            "feedback_processed": True,
            "signal_value": signal.value,
            "signal_type": signal.signal_type.value,
            "engine_adapted": self._component.is_adapted(),
        }

    def _get_status(self) -> dict[str, Any]:
        """Get learning engine status.

        Returns:
            Engine status
        """
        state = self._component.get_state()
        metrics = self._component.get_performance_metrics()

        return {
            "is_adapted": self._component.is_adapted(),
            "state": state.to_dict() if hasattr(state, "to_dict") else {},
            "performance": metrics.to_dict() if hasattr(metrics, "to_dict") else {},
        }

    def trigger_adaptation(
        self, feedback: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Trigger model adaptation.

        Args:
            feedback: Optional feedback for adaptation

        Returns:
            Adaptation result
        """
        result = self._component.adapt(feedback=feedback)

        return {
            "adaptation_status": (
                result.status.value
                if hasattr(result.status, "value")
                else str(result.status)
            ),
            "is_successful": result.is_successful,
            "error_message": result.error_message,
        }


class KnowledgeGraphAdapter(ComponentAdapter):
    """Adapter for the Knowledge Graph (ST-NS-034)."""

    def __init__(
        self,
        component_instance: Any,
        event_bus: EventBus | None = None,
    ):
        """Initialize the knowledge graph adapter.

        Args:
            component_instance: KnowledgeGraph instance
            event_bus: Optional event bus
        """
        super().__init__("knowledge_graph", component_instance, event_bus)

    def _initialize_component(self) -> None:
        """Initialize the knowledge graph."""
        # Graph is usually ready on creation
        pass

    def process(self, data: dict[str, Any]) -> dict[str, Any]:
        """Query or update the knowledge graph.

        Args:
            data: Query or update data

        Returns:
            Query result or update status
        """
        # Check operation type
        if "query" in data:
            return self._query_graph(data)
        elif "entities" in data:
            return self._add_entities(data)
        else:
            return self._get_metrics()

    def _query_graph(self, data: dict[str, Any]) -> dict[str, Any]:
        """Query the knowledge graph.

        Args:
            data: Query data

        Returns:
            Query results
        """
        query = data.get("query", {})
        node_type = query.get("node_type")
        edge_type = query.get("edge_type")
        node_id = query.get("node_id")

        results = {}

        if node_id:
            node = self._component.get_node(node_id)
            if node:
                results["node"] = node.to_dict() if hasattr(node, "to_dict") else {}

        if node_type:
            nodes = self._component.get_nodes_by_type(node_type)
            results["nodes"] = [
                n.to_dict() if hasattr(n, "to_dict") else {} for n in nodes
            ]

        if edge_type:
            edges = self._component.get_edges_by_type(edge_type)
            results["edges"] = [
                e.to_dict() if hasattr(e, "to_dict") else {} for e in edges
            ]

        metrics = self._component.get_metrics()
        return {
            "query_results": results,
            "metrics": metrics.to_dict() if hasattr(metrics, "to_dict") else {},
        }

    def _add_entities(self, data: dict[str, Any]) -> dict[str, Any]:
        """Add entities and relationships to the graph.

        Args:
            data: Entity data

        Returns:
            Update status
        """
        entities = data.get("entities", [])
        relationships = data.get("relationships", [])

        added_nodes = 0
        added_edges = 0

        for entity in entities:
            try:
                self._component.add_node(
                    node_id=entity.get("id", str(entity)),
                    node_type=entity.get("type", "entity"),
                    properties=entity.get("properties", {}),
                    confidence=entity.get("confidence", 1.0),
                )
                added_nodes += 1
            except Exception as e:
                logger.warning("Failed to add entity: %s", e)

        for rel in relationships:
            try:
                self._component.add_edge(
                    source_id=rel.get("source"),
                    target_id=rel.get("target"),
                    edge_type=rel.get("type", "related_to"),
                    properties=rel.get("properties", {}),
                    weight=rel.get("weight", 1.0),
                    confidence=rel.get("confidence", 1.0),
                )
                added_edges += 1
            except Exception as e:
                logger.warning("Failed to add relationship: %s", e)

        return {
            "nodes_added": added_nodes,
            "edges_added": added_edges,
            "success": True,
        }

    def _get_metrics(self) -> dict[str, Any]:
        """Get graph metrics.

        Returns:
            Graph metrics
        """
        metrics = self._component.get_metrics()
        return {
            "metrics": metrics.to_dict() if hasattr(metrics, "to_dict") else {},
            "node_count": self._component.node_count,
            "edge_count": self._component.edge_count,
        }


class PatternRecognitionAdapter(ComponentAdapter):
    """Adapter for the Pattern Recognition Engine (ST-NS-035)."""

    def __init__(
        self,
        component_instance: Any,
        event_bus: EventBus | None = None,
    ):
        """Initialize the pattern recognition adapter.

        Args:
            component_instance: PatternRecognitionEngine instance
            event_bus: Optional event bus
        """
        super().__init__("pattern_recognition", component_instance, event_bus)

    def _initialize_component(self) -> None:
        """Initialize the pattern engine."""
        # Engine is usually ready on creation
        pass

    def process(self, data: dict[str, Any]) -> dict[str, Any]:
        """Detect patterns in data.

        Args:
            data: Price data for pattern detection

        Returns:
            Detected patterns and probabilities
        """
        # Extract price data
        prices = data.get("prices", data.get("price_data", []))
        if not prices and "price" in data:
            # Single price point - create a simple sequence
            price = data.get("price")
            prices = [price] * 50  # Pad with same price

        if not prices:
            return {
                "pattern": None,
                "probabilities": {},
                "features": {},
                "error": "No price data provided",
            }

        # Detect patterns
        pattern = self._component.detect_patterns(prices)
        probabilities = self._component.get_pattern_probabilities(prices)
        features = self._component.compute_features(prices)

        result = {
            "probabilities": probabilities,
            "features": features,
        }

        if pattern:
            result["pattern"] = {
                "type": pattern.pattern_type.value,
                "confidence": pattern.confidence,
                "start_idx": pattern.start_idx,
                "end_idx": pattern.end_idx,
                "features": pattern.features,
            }
        else:
            result["pattern"] = None

        return result


class FusionAdapter(ComponentAdapter):
    """Adapter for the Multi-Modal Fusion Engine (ST-NS-036)."""

    def __init__(
        self,
        component_instance: Any,
        event_bus: EventBus | None = None,
    ):
        """Initialize the fusion adapter.

        Args:
            component_instance: MultiModalFusionEngine instance
            event_bus: Optional event bus
        """
        super().__init__("fusion", component_instance, event_bus)

    def _initialize_component(self) -> None:
        """Initialize the fusion engine."""
        if hasattr(self._component, "reset_state"):
            self._component.reset_state()

    def process(self, data: dict[str, Any]) -> dict[str, Any]:
        """Fuse multiple signals.

        Args:
            data: Signals to fuse (dict of source to value)

        Returns:
            Fused signal result
        """
        # Extract signals
        signals = data.get("signals", {})
        context = data.get("context", {})

        # If no explicit signals, try to extract from data
        if not signals:
            signals = {}
            signal_keys = ["technical", "sentiment", "onchain", "fundamental"]
            for key in signal_keys:
                if key in data:
                    signals[key] = data[key]

        if not signals:
            return {
                "fused_value": 0.0,
                "confidence": 0.0,
                "direction": "neutral",
                "error": "No signals to fuse",
            }

        # Fuse signals
        result = self._component.fuse(signals, context)

        return {
            "fused_value": result.fused_value,
            "confidence": result.confidence,
            "direction": result.direction,
            "strategy_used": result.strategy_used.value,
            "modality_contributions": {
                m.value: c for m, c in result.modality_contributions.items()
            },
            "signal_count": result.signal_count,
            "alignment_quality": result.alignment_quality,
            "processing_time_ms": result.processing_time_ms,
        }
