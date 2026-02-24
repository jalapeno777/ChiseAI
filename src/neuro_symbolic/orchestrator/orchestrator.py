"""Neuro-Symbolic Orchestrator - Central coordination for all components.

The orchestrator integrates all 6 neuro-symbolic components:
1. Hybrid Reasoning (ST-NS-031)
2. Explainability (ST-NS-032)
3. Adaptive Learning (ST-NS-033)
4. Knowledge Graph (ST-NS-034)
5. Pattern Recognition (ST-NS-035)
6. Multi-Modal Fusion (ST-NS-036)

It provides:
- Unified signal generation pipeline
- Explanation generation for all outputs
- Learning from feedback
- Coordinated data flow
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from src.neuro_symbolic.adaptive_learning import AdaptiveLearningEngine
from src.neuro_symbolic.explainability import ExplanationGenerator
from src.neuro_symbolic.fusion import MultiModalFusionEngine
from src.neuro_symbolic.integration.adapters import (
    AdaptiveLearningAdapter,
    ExplainabilityAdapter,
    FusionAdapter,
    HybridReasoningAdapter,
    KnowledgeGraphAdapter,
    PatternRecognitionAdapter,
)
from src.neuro_symbolic.integration.layer import (
    EventBus,
    EventType,
    IntegrationLayer,
)
from src.neuro_symbolic.integration.registry import (
    ComponentRegistry,
    ComponentType,
)
from src.neuro_symbolic.knowledge_graph import KnowledgeGraph
from src.neuro_symbolic.pattern_recognition import PatternRecognitionEngine

# Import the actual component classes
from src.neuro_symbolic.reasoning import HybridReasoningEngine

logger = logging.getLogger(__name__)


class PipelineStage(Enum):
    """Pipeline stages for signal generation."""

    REASONING = "reasoning"
    PATTERN_RECOGNITION = "pattern_recognition"
    FUSION = "fusion"
    EXPLANATION = "explanation"
    LEARNING = "learning"


@dataclass
class OrchestratorConfig:
    """Configuration for the Neuro-Symbolic Orchestrator."""

    # Reasoning settings
    reasoning_feature_dim: int = 32
    reasoning_num_patterns: int = 10
    reasoning_confidence_threshold: float = 0.5

    # Pattern recognition settings
    pattern_sequence_length: int = 50
    pattern_confidence_threshold: float = 0.7

    # Fusion settings
    fusion_confidence_threshold: float = 0.3

    # Learning settings
    learning_enabled: bool = True
    online_learning: bool = True

    # Explanation settings
    explanation_detail_level: str = "standard"

    # Pipeline settings
    enable_pattern_detection: bool = True
    enable_fusion: bool = True
    enable_learning: bool = True
    enable_explanation: bool = True

    # Fallback settings
    enable_fallbacks: bool = True


@dataclass
class OrchestratorResult:
    """Result from orchestrator processing."""

    prediction: str
    confidence: float
    explanation: dict[str, Any]
    pattern_detected: dict[str, Any] | None = None
    fused_signal: dict[str, Any] | None = None
    reasoning_result: dict[str, Any] | None = None
    learning_feedback: dict[str, Any] | None = None
    processing_time_ms: float = 0.0
    components_used: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "prediction": self.prediction,
            "confidence": self.confidence,
            "explanation": self.explanation,
            "pattern_detected": self.pattern_detected,
            "fused_signal": self.fused_signal,
            "reasoning_result": self.reasoning_result,
            "learning_feedback": self.learning_feedback,
            "processing_time_ms": self.processing_time_ms,
            "components_used": self.components_used,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
        }


class NeuroSymbolicOrchestrator:
    """Central orchestrator for the neuro-symbolic system.

    Coordinates all components to provide unified signal generation
    with explanations and learning capabilities.

    Example:
        >>> orchestrator = NeuroSymbolicOrchestrator()
        >>> result = orchestrator.process_signal({"price": 100, "volume": 1000})
        >>> print(result.prediction)
        >>> print(result.explanation["summary"])
    """

    def __init__(self, config: OrchestratorConfig | None = None):
        """Initialize the orchestrator.

        Args:
            config: Optional configuration. Uses defaults if not provided.
        """
        self.config = config or OrchestratorConfig()

        # Initialize event bus and integration layer
        self._event_bus = EventBus()
        self._integration_layer = IntegrationLayer(
            event_bus=self._event_bus,
            enable_fallbacks=self.config.enable_fallbacks,
        )

        # Initialize component registry
        self._registry = ComponentRegistry()

        # Initialize and register all components
        self._initialize_components()

        # Processing state
        self._processing_count = 0
        self._last_result: OrchestratorResult | None = None

        logger.info(
            "NeuroSymbolicOrchestrator initialized with %d components",
            len(self._registry),
        )

    def _initialize_components(self) -> None:
        """Initialize all neuro-symbolic components."""
        # 1. Hybrid Reasoning Engine
        reasoning_engine = HybridReasoningEngine(
            feature_dim=self.config.reasoning_feature_dim,
            num_patterns=self.config.reasoning_num_patterns,
            confidence_threshold=self.config.reasoning_confidence_threshold,
        )
        self._registry.register(
            component_id="hybrid_reasoning",
            component_type=ComponentType.REASONING,
            component_class=HybridReasoningEngine,
            description="Hybrid reasoning engine combining neural and symbolic AI",
            version="1.0.0",
        )
        reasoning_adapter = HybridReasoningAdapter(reasoning_engine, self._event_bus)
        reasoning_adapter.initialize()
        self._integration_layer.register_adapter("hybrid_reasoning", reasoning_adapter)

        # 2. Explanation Generator
        explanation_generator = ExplanationGenerator()
        self._registry.register(
            component_id="explainability",
            component_type=ComponentType.EXPLAINABILITY,
            component_class=ExplanationGenerator,
            description="Human-readable explanation generator",
            version="1.0.0",
        )
        explainability_adapter = ExplainabilityAdapter(
            explanation_generator, self._event_bus
        )
        explainability_adapter.initialize()
        self._integration_layer.register_adapter(
            "explainability", explainability_adapter
        )

        # 3. Adaptive Learning Engine
        learning_engine = AdaptiveLearningEngine()
        self._registry.register(
            component_id="adaptive_learning",
            component_type=ComponentType.LEARNING,
            component_class=AdaptiveLearningEngine,
            description="Adaptive learning from market feedback",
            version="1.0.0",
        )
        learning_adapter = AdaptiveLearningAdapter(learning_engine, self._event_bus)
        learning_adapter.initialize()
        self._integration_layer.register_adapter("adaptive_learning", learning_adapter)

        # 4. Knowledge Graph
        knowledge_graph = KnowledgeGraph(name="chiseai_market_knowledge")
        self._registry.register(
            component_id="knowledge_graph",
            component_type=ComponentType.KNOWLEDGE_GRAPH,
            component_class=KnowledgeGraph,
            description="Market relationship knowledge graph",
            version="1.0.0",
        )
        kg_adapter = KnowledgeGraphAdapter(knowledge_graph, self._event_bus)
        kg_adapter.initialize()
        self._integration_layer.register_adapter("knowledge_graph", kg_adapter)

        # 5. Pattern Recognition Engine
        pattern_engine = PatternRecognitionEngine()
        self._registry.register(
            component_id="pattern_recognition",
            component_type=ComponentType.PATTERN_RECOGNITION,
            component_class=PatternRecognitionEngine,
            description="Deep learning pattern recognition",
            version="1.0.0",
        )
        pattern_adapter = PatternRecognitionAdapter(pattern_engine, self._event_bus)
        pattern_adapter.initialize()
        self._integration_layer.register_adapter("pattern_recognition", pattern_adapter)

        # 6. Multi-Modal Fusion Engine
        fusion_engine = MultiModalFusionEngine()
        self._registry.register(
            component_id="fusion",
            component_type=ComponentType.FUSION,
            component_class=MultiModalFusionEngine,
            description="Multi-modal signal fusion",
            version="1.0.0",
        )
        fusion_adapter = FusionAdapter(fusion_engine, self._event_bus)
        fusion_adapter.initialize()
        self._integration_layer.register_adapter("fusion", fusion_adapter)

        # Store references for quick access
        self._reasoning_engine = reasoning_engine
        self._explanation_generator = explanation_generator
        self._learning_engine = learning_engine
        self._knowledge_graph = knowledge_graph
        self._pattern_engine = pattern_engine
        self._fusion_engine = fusion_engine

        # Store adapters
        self._adapters = {
            "hybrid_reasoning": reasoning_adapter,
            "explainability": explainability_adapter,
            "adaptive_learning": learning_adapter,
            "knowledge_graph": kg_adapter,
            "pattern_recognition": pattern_adapter,
            "fusion": fusion_adapter,
        }

    def process_signal(self, data: dict[str, Any]) -> OrchestratorResult:
        """Process a signal through the complete pipeline.

        This is the main entry point for signal processing. It:
        1. Runs hybrid reasoning
        2. Detects patterns (if enabled)
        3. Fuses signals (if enabled)
        4. Generates explanation
        5. Records for learning

        Args:
            data: Input market data with price, volume, etc.

        Returns:
            OrchestratorResult with prediction, confidence, and explanation
        """
        start_time = time.perf_counter()
        self._processing_count += 1

        components_used = []
        reasoning_result = None
        pattern_result = None
        fusion_result = None
        explanation_result = None

        try:
            # Stage 1: Hybrid Reasoning
            reasoning_adapter = self._adapters["hybrid_reasoning"]
            reasoning_result = reasoning_adapter.safe_process(data)
            components_used.append("hybrid_reasoning")

            prediction = reasoning_result.get("prediction", "hold")
            confidence = reasoning_result.get("confidence", 0.5)

            # Stage 2: Pattern Recognition (if enabled)
            if self.config.enable_pattern_detection:
                pattern_adapter = self._adapters["pattern_recognition"]
                pattern_result = pattern_adapter.safe_process(data)
                components_used.append("pattern_recognition")

            # Stage 3: Multi-Modal Fusion (if enabled)
            if self.config.enable_fusion:
                fusion_adapter = self._adapters["fusion"]

                # Build signals from different sources
                signals = {
                    "reasoning": confidence
                    if prediction == "buy"
                    else -confidence
                    if prediction == "sell"
                    else 0.0,
                }

                # Add pattern signal if available
                if pattern_result and pattern_result.get("pattern"):
                    pattern_conf = pattern_result["pattern"].get("confidence", 0.5)
                    pattern_type = pattern_result["pattern"].get("type", "")
                    if (
                        "bull" in pattern_type.lower()
                        or "ascending" in pattern_type.lower()
                    ):
                        signals["pattern"] = pattern_conf
                    elif (
                        "bear" in pattern_type.lower()
                        or "descending" in pattern_type.lower()
                    ):
                        signals["pattern"] = -pattern_conf
                    else:
                        signals["pattern"] = 0.0

                fusion_result = fusion_adapter.safe_process({"signals": signals})
                components_used.append("fusion")

                # Update prediction from fusion if available
                if fusion_result and "fused_value" in fusion_result:
                    fused_value = fusion_result["fused_value"]
                    fused_conf = fusion_result.get("confidence", confidence)

                    if fused_value > 0.1:
                        prediction = "buy"
                        confidence = max(confidence, fused_conf)
                    elif fused_value < -0.1:
                        prediction = "sell"
                        confidence = max(confidence, fused_conf)
                    else:
                        prediction = "hold"

            # Stage 4: Generate Explanation (if enabled)
            if self.config.enable_explanation:
                explanation_adapter = self._adapters["explainability"]

                explanation_input = {
                    "prediction": prediction,
                    "confidence": confidence,
                    "features": data,
                    "contributing_factors": reasoning_result.get(
                        "contributing_factors", {}
                    ),
                    "metadata": {
                        "pattern_detected": pattern_result.get("pattern")
                        if pattern_result
                        else None,
                        "fusion_used": self.config.enable_fusion,
                    },
                }

                explanation_result = explanation_adapter.safe_process(explanation_input)
                components_used.append("explainability")

            # Calculate processing time
            processing_time = (time.perf_counter() - start_time) * 1000

            # Build result
            result = OrchestratorResult(
                prediction=prediction,
                confidence=confidence,
                explanation=explanation_result.get("explanation", {})
                if explanation_result
                else {
                    "summary": f"{prediction} signal with {confidence:.0%} confidence"
                },
                pattern_detected=pattern_result.get("pattern")
                if pattern_result
                else None,
                fused_signal=fusion_result if fusion_result else None,
                reasoning_result=reasoning_result,
                processing_time_ms=processing_time,
                components_used=components_used,
                metadata={
                    "processing_count": self._processing_count,
                    "config": {
                        "pattern_detection": self.config.enable_pattern_detection,
                        "fusion": self.config.enable_fusion,
                        "learning": self.config.enable_learning,
                    },
                },
            )

            self._last_result = result

            # Publish completion event
            self._event_bus.publish(
                EventType.PIPELINE_COMPLETED,
                "orchestrator",
                {
                    "prediction": prediction,
                    "confidence": confidence,
                    "processing_time_ms": processing_time,
                },
            )

            return result

        except Exception as e:
            logger.error("Error in signal processing pipeline: %s", e)
            self._event_bus.publish(
                EventType.PIPELINE_ERROR,
                "orchestrator",
                {"error": str(e)},
            )

            # Return error result
            return OrchestratorResult(
                prediction="hold",
                confidence=0.0,
                explanation={"summary": f"Error in processing: {str(e)}"},
                processing_time_ms=(time.perf_counter() - start_time) * 1000,
                components_used=components_used,
                metadata={"error": str(e)},
            )

    def process_feedback(
        self,
        outcome: dict[str, Any],
        prediction_id: str | None = None,
    ) -> dict[str, Any]:
        """Process feedback from a trade outcome for learning.

        Args:
            outcome: Trade outcome with pnl, success, etc.
            prediction_id: Optional ID of the prediction being evaluated

        Returns:
            Learning result
        """
        if not self.config.enable_learning:
            return {"learning_disabled": True}

        learning_adapter = self._adapters["adaptive_learning"]
        result = learning_adapter.safe_process(outcome)

        # Also update knowledge graph if we have entity info
        if outcome.get("symbol"):
            kg_adapter = self._adapters["knowledge_graph"]
            kg_adapter.safe_process(
                {
                    "entities": [
                        {
                            "id": outcome["symbol"],
                            "type": "asset",
                            "properties": {
                                "last_outcome": outcome.get("pnl", 0),
                                "last_success": outcome.get("success", False),
                            },
                        }
                    ]
                }
            )

        return result

    def get_explanation(self) -> dict[str, Any]:
        """Get explanation for the last processed signal.

        Returns:
            Explanation dictionary
        """
        if self._last_result is None:
            return {"summary": "No signal has been processed yet."}

        return self._last_result.explanation

    def get_component_status(self) -> dict[str, Any]:
        """Get status of all components.

        Returns:
            Dictionary with component statuses
        """
        statuses = {}
        for name, adapter in self._adapters.items():
            statuses[name] = adapter.get_status()

        return {
            "components": statuses,
            "registry_status": self._registry.get_status(),
            "integration_status": self._integration_layer.get_status(),
        }

    def get_statistics(self) -> dict[str, Any]:
        """Get orchestrator statistics.

        Returns:
            Statistics dictionary
        """
        return {
            "processing_count": self._processing_count,
            "last_prediction": self._last_result.prediction
            if self._last_result
            else None,
            "last_confidence": self._last_result.confidence
            if self._last_result
            else None,
            "event_bus_stats": self._event_bus.get_statistics(),
            "config": {
                "pattern_detection": self.config.enable_pattern_detection,
                "fusion": self.config.enable_fusion,
                "learning": self.config.enable_learning,
                "explanation": self.config.enable_explanation,
            },
        }

    def reset_state(self) -> None:
        """Reset all component states."""
        # Reset reasoning engine
        if hasattr(self._reasoning_engine, "reset_state"):
            self._reasoning_engine.reset_state()

        # Reset fusion engine
        if hasattr(self._fusion_engine, "reset_state"):
            self._fusion_engine.reset_state()

        # Reset learning engine
        if hasattr(self._learning_engine, "reset"):
            self._learning_engine.reset()

        # Clear event history
        self._event_bus.clear_history()

        # Reset counters
        self._processing_count = 0
        self._last_result = None

        logger.info("Orchestrator state reset")

    def shutdown(self) -> None:
        """Shutdown all components."""
        self._integration_layer.shutdown()
        logger.info("Orchestrator shutdown complete")

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"NeuroSymbolicOrchestrator("
            f"components={len(self._adapters)}, "
            f"processed={self._processing_count})"
        )
