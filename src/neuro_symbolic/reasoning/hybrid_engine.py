"""Hybrid reasoning engine combining neural and symbolic components."""

import time
from dataclasses import dataclass, field
from typing import Any

from src.neuro_symbolic.reasoning.integration_layer import (
    FusedResult,
    FusionStrategy,
    IntegrationLayer,
    ReasoningChain,
)
from src.neuro_symbolic.reasoning.neural_component import NeuralComponent, NeuralOutput
from src.neuro_symbolic.reasoning.symbolic_component import (
    SymbolicComponent,
    SymbolicOutput,
    TrendDirection,
)


@dataclass
class HybridReasoningResult:
    """Complete result from hybrid reasoning."""

    prediction: str
    confidence: float
    trend_direction: TrendDirection
    neural_output: NeuralOutput
    symbolic_output: SymbolicOutput
    fused_result: FusedResult
    reasoning_chain: ReasoningChain
    processing_time_ms: float
    metadata: dict[str, Any] = field(default_factory=dict)


class HybridReasoningEngine:
    """Hybrid reasoning engine combining neural and symbolic AI.

    This engine combines the pattern recognition capabilities of neural networks
    with the explainable logic of symbolic reasoning to provide robust market
    analysis with confidence scores and explainable reasoning chains.

    Example:
        >>> engine = HybridReasoningEngine()
        >>> result = engine.reason({'price': 100, 'volume': 1000})
        >>> print(result.prediction)
        >>> print(result.reasoning_chain)
    """

    def __init__(
        self,
        feature_dim: int = 32,
        num_patterns: int = 10,
        fusion_strategy: FusionStrategy = FusionStrategy.ADAPTIVE,
        neural_weight: float = 0.5,
        symbolic_weight: float = 0.5,
        confidence_threshold: float = 0.5,
    ):
        """Initialize the hybrid reasoning engine.

        Args:
            feature_dim: Dimensionality of feature vectors for neural component.
            num_patterns: Number of patterns to detect in neural component.
            fusion_strategy: Strategy for combining neural and symbolic outputs.
            neural_weight: Default weight for neural component (0-1).
            symbolic_weight: Default weight for symbolic component (0-1).
            confidence_threshold: Minimum confidence for predictions.
        """
        self.feature_dim = feature_dim
        self.num_patterns = num_patterns
        self.fusion_strategy = fusion_strategy
        self.neural_weight = neural_weight
        self.symbolic_weight = symbolic_weight
        self.confidence_threshold = confidence_threshold

        # Initialize components
        self._neural_component = NeuralComponent(
            feature_dim=feature_dim,
            num_patterns=num_patterns,
            confidence_threshold=confidence_threshold,
        )

        self._symbolic_component = SymbolicComponent(
            confidence_threshold=confidence_threshold
        )

        self._integration_layer = IntegrationLayer(
            fusion_strategy=fusion_strategy,
            default_neural_weight=neural_weight,
            default_symbolic_weight=symbolic_weight,
            confidence_threshold=confidence_threshold,
        )

        # State tracking
        self._last_result: HybridReasoningResult | None = None
        self._processing_count = 0

    def reason(self, data: dict[str, Any]) -> HybridReasoningResult:
        """Perform hybrid reasoning on input data.

        Args:
            data: Input market data dictionary containing fields like:
                - price: Current price
                - volume: Current volume
                - high: Period high
                - low: Period low
                - prev_price: Previous price
                - prev_volume: Previous volume
                - avg_price: Average price
                - avg_volume: Average volume
                - sma_short: Short-term moving average
                - sma_long: Long-term moving average
                - support: Support level
                - resistance: Resistance level
                - atr: Average True Range

        Returns:
            HybridReasoningResult containing prediction, confidence, and
            complete reasoning chain.
        """
        start_time = time.perf_counter()

        # Process through neural component
        neural_output = self._neural_component.process(data)

        # Process through symbolic component
        symbolic_output = self._symbolic_component.process(data)

        # Fuse results
        fused_result = self._integration_layer.fuse(neural_output, symbolic_output)

        # Build reasoning chain
        reasoning_chain = self._integration_layer.build_reasoning_chain(
            neural_output, symbolic_output, fused_result
        )

        # Calculate processing time
        processing_time = (time.perf_counter() - start_time) * 1000

        # Build complete result
        result = HybridReasoningResult(
            prediction=fused_result.prediction,
            confidence=fused_result.confidence,
            trend_direction=fused_result.trend_direction,
            neural_output=neural_output,
            symbolic_output=symbolic_output,
            fused_result=fused_result,
            reasoning_chain=reasoning_chain,
            processing_time_ms=processing_time,
            metadata={
                "engine_version": "1.0.0",
                "fusion_strategy": self.fusion_strategy.value,
                "processing_count": self._processing_count,
            },
        )

        self._last_result = result
        self._processing_count += 1

        return result

    def analyze_trend(self, data: dict[str, Any]) -> dict[str, Any]:
        """Analyze market trend using hybrid reasoning.

        Args:
            data: Input market data dictionary.

        Returns:
            Dictionary with trend analysis results.
        """
        result = self.reason(data)

        return {
            "trend_direction": result.trend_direction.value,
            "confidence": result.confidence,
            "prediction": result.prediction,
            "explanation": result.fused_result.explanation,
            "contributing_factors": result.fused_result.contributing_factors,
            "inferred_facts": result.symbolic_output.inferred_facts,
            "neural_patterns": [
                {"name": p["name"], "confidence": p["confidence"]}
                for p in result.neural_output.patterns
            ],
            "triggered_rules": [
                {
                    "name": r.rule_name,
                    "confidence": r.confidence,
                    "explanation": r.explanation,
                }
                for r in result.symbolic_output.triggered_rules
            ],
        }

    def get_explanation(self) -> str:
        """Get explanation for the last reasoning result.

        Returns:
            Human-readable explanation string.
        """
        if self._last_result is None:
            return "No reasoning has been performed yet."

        return self._last_result.fused_result.explanation

    def get_reasoning_chain(self) -> ReasoningChain | None:
        """Get the reasoning chain from the last result.

        Returns:
            ReasoningChain if available, None otherwise.
        """
        if self._last_result is None:
            return None
        return self._last_result.reasoning_chain

    def get_confidence_breakdown(self) -> dict[str, float]:
        """Get confidence breakdown from neural and symbolic components.

        Returns:
            Dictionary with confidence scores from each component.
        """
        if self._last_result is None:
            return {"neural": 0.0, "symbolic": 0.0, "fused": 0.0}

        return {
            "neural": self._last_result.neural_output.confidence,
            "symbolic": self._last_result.symbolic_output.overall_confidence,
            "fused": self._last_result.confidence,
            "neural_weight": self._last_result.fused_result.neural_weight,
            "symbolic_weight": self._last_result.fused_result.symbolic_weight,
        }

    def reset_state(self) -> None:
        """Reset internal state of all components."""
        self._neural_component.reset_state()
        self._last_result = None

    def set_fusion_strategy(self, strategy: FusionStrategy) -> None:
        """Change the fusion strategy.

        Args:
            strategy: New fusion strategy to use.
        """
        self.fusion_strategy = strategy
        self._integration_layer.fusion_strategy = strategy

    def add_custom_rule(self, rule: Any) -> None:
        """Add a custom rule to the symbolic component.

        Args:
            rule: SymbolicRule instance to add.
        """
        self._symbolic_component.add_rule(rule)

    def get_statistics(self) -> dict[str, Any]:
        """Get engine statistics.

        Returns:
            Dictionary with engine statistics.
        """
        return {
            "processing_count": self._processing_count,
            "feature_dim": self.feature_dim,
            "num_patterns": self.num_patterns,
            "fusion_strategy": self.fusion_strategy.value,
            "confidence_threshold": self.confidence_threshold,
        }


# Convenience function for quick analysis
def analyze_market_data(data: dict[str, Any]) -> HybridReasoningResult:
    """Quick analysis function for market data.

    Args:
        data: Input market data dictionary.

    Returns:
        HybridReasoningResult with analysis.
    """
    engine = HybridReasoningEngine()
    return engine.reason(data)
