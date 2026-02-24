"""Integration layer for combining neural and symbolic reasoning outputs."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from src.neuro_symbolic.reasoning.neural_component import NeuralOutput
from src.neuro_symbolic.reasoning.symbolic_component import (
    SymbolicOutput,
    TrendDirection,
)


class FusionStrategy(Enum):
    """Strategies for fusing neural and symbolic outputs."""

    WEIGHTED_AVERAGE = "weighted_average"
    NEURAL_PRIORITY = "neural_priority"
    SYMBOLIC_PRIORITY = "symbolic_priority"
    ADAPTIVE = "adaptive"
    CONFIDENCE_WEIGHTED = "confidence_weighted"


@dataclass
class FusedResult:
    """Result of fusing neural and symbolic outputs."""

    prediction: str
    confidence: float
    neural_weight: float
    symbolic_weight: float
    trend_direction: TrendDirection
    contributing_factors: list[str]
    explanation: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReasoningChain:
    """Chain of reasoning steps for explainability."""

    steps: list[dict[str, Any]]
    final_conclusion: str
    confidence: float
    neural_contribution: float
    symbolic_contribution: float


class IntegrationLayer:
    """Integration layer for hybrid reasoning.

    Combines outputs from neural and symbolic components using
    configurable fusion strategies.
    """

    def __init__(
        self,
        fusion_strategy: FusionStrategy = FusionStrategy.ADAPTIVE,
        default_neural_weight: float = 0.5,
        default_symbolic_weight: float = 0.5,
        confidence_threshold: float = 0.6,
    ):
        self.fusion_strategy = fusion_strategy
        self.default_neural_weight = default_neural_weight
        self.default_symbolic_weight = default_symbolic_weight
        self.confidence_threshold = confidence_threshold

        # Strategy-specific configurations
        self._strategy_configs = {
            FusionStrategy.ADAPTIVE: {
                "neural_boost": 0.1,  # Boost neural when patterns detected
                "symbolic_boost": 0.15,  # Boost symbolic when rules triggered
                "agreement_bonus": 0.2,  # Bonus when both agree
            }
        }

    def fuse(
        self, neural_output: NeuralOutput, symbolic_output: SymbolicOutput
    ) -> FusedResult:
        """Fuse neural and symbolic outputs.

        Args:
            neural_output: Output from neural component.
            symbolic_output: Output from symbolic component.

        Returns:
            FusedResult combining both perspectives.
        """
        # Calculate weights based on strategy
        neural_weight, symbolic_weight = self._calculate_weights(
            neural_output, symbolic_output
        )

        # Fuse predictions
        prediction = self._fuse_predictions(
            neural_output, symbolic_output, neural_weight, symbolic_weight
        )

        # Fuse confidence
        fused_confidence = self._fuse_confidence(
            neural_output.confidence,
            symbolic_output.overall_confidence,
            neural_weight,
            symbolic_weight,
        )

        # Determine trend direction (prefer symbolic for explicit direction)
        trend_direction = self._determine_fused_trend(neural_output, symbolic_output)

        # Build contributing factors
        contributing_factors = self._build_contributing_factors(
            neural_output, symbolic_output
        )

        # Generate explanation
        explanation = self._generate_explanation(
            neural_output, symbolic_output, prediction, fused_confidence
        )

        return FusedResult(
            prediction=prediction,
            confidence=fused_confidence,
            neural_weight=neural_weight,
            symbolic_weight=symbolic_weight,
            trend_direction=trend_direction,
            contributing_factors=contributing_factors,
            explanation=explanation,
            metadata={
                "fusion_strategy": self.fusion_strategy.value,
                "neural_confidence": neural_output.confidence,
                "symbolic_confidence": symbolic_output.overall_confidence,
            },
        )

    def build_reasoning_chain(
        self,
        neural_output: NeuralOutput,
        symbolic_output: SymbolicOutput,
        fused_result: FusedResult,
    ) -> ReasoningChain:
        """Build explainable reasoning chain.

        Args:
            neural_output: Neural component output.
            symbolic_output: Symbolic component output.
            fused_result: Fused result.

        Returns:
            ReasoningChain with step-by-step explanation.
        """
        steps = []

        # Step 1: Neural pattern detection
        steps.append(
            {
                "step": 1,
                "component": "neural",
                "action": "pattern_detection",
                "result": f"Detected {len(neural_output.patterns)} patterns",
                "confidence": neural_output.confidence,
                "details": [p["name"] for p in neural_output.patterns[:3]],
            }
        )

        # Step 2: Symbolic rule evaluation
        steps.append(
            {
                "step": 2,
                "component": "symbolic",
                "action": "rule_evaluation",
                "result": f"Triggered {len(symbolic_output.triggered_rules)} rules",
                "confidence": symbolic_output.overall_confidence,
                "details": [r.rule_name for r in symbolic_output.triggered_rules[:3]],
            }
        )

        # Step 3: Inference application
        if symbolic_output.inferred_facts:
            steps.append(
                {
                    "step": 3,
                    "component": "symbolic",
                    "action": "inference",
                    "result": f"Derived {len(symbolic_output.inferred_facts)} facts",
                    "confidence": 0.8,
                    "details": list(symbolic_output.inferred_facts.keys()),
                }
            )

        # Step 4: Weight calculation
        steps.append(
            {
                "step": len(steps) + 1,
                "component": "integration",
                "action": "weight_calculation",
                "result": f"Neural weight: {fused_result.neural_weight:.2f}, "
                f"Symbolic weight: {fused_result.symbolic_weight:.2f}",
                "confidence": 1.0,
                "details": [f"Strategy: {self.fusion_strategy.value}"],
            }
        )

        # Step 5: Final fusion
        steps.append(
            {
                "step": len(steps) + 1,
                "component": "integration",
                "action": "fusion",
                "result": fused_result.prediction,
                "confidence": fused_result.confidence,
                "details": fused_result.contributing_factors[:3],
            }
        )

        return ReasoningChain(
            steps=steps,
            final_conclusion=fused_result.prediction,
            confidence=fused_result.confidence,
            neural_contribution=fused_result.neural_weight,
            symbolic_contribution=fused_result.symbolic_weight,
        )

    def _calculate_weights(
        self, neural_output: NeuralOutput, symbolic_output: SymbolicOutput
    ) -> tuple[float, float]:
        """Calculate fusion weights based on strategy."""
        if self.fusion_strategy == FusionStrategy.WEIGHTED_AVERAGE:
            return self.default_neural_weight, self.default_symbolic_weight

        elif self.fusion_strategy == FusionStrategy.NEURAL_PRIORITY:
            return 0.7, 0.3

        elif self.fusion_strategy == FusionStrategy.SYMBOLIC_PRIORITY:
            return 0.3, 0.7

        elif self.fusion_strategy == FusionStrategy.CONFIDENCE_WEIGHTED:
            total_confidence = (
                neural_output.confidence + symbolic_output.overall_confidence
            )
            if total_confidence > 0:
                n_weight = neural_output.confidence / total_confidence
                s_weight = symbolic_output.overall_confidence / total_confidence
                return n_weight, s_weight
            return 0.5, 0.5

        elif self.fusion_strategy == FusionStrategy.ADAPTIVE:
            return self._adaptive_weights(neural_output, symbolic_output)

        return self.default_neural_weight, self.default_symbolic_weight

    def _adaptive_weights(
        self, neural_output: NeuralOutput, symbolic_output: SymbolicOutput
    ) -> tuple[float, float]:
        """Calculate adaptive weights based on output quality."""
        config = self._strategy_configs[FusionStrategy.ADAPTIVE]

        neural_weight = self.default_neural_weight
        symbolic_weight = self.default_symbolic_weight

        # Boost neural if multiple patterns detected
        if len(neural_output.patterns) >= 2:
            neural_weight += config["neural_boost"]

        # Boost symbolic if multiple rules triggered
        if len(symbolic_output.triggered_rules) >= 2:
            symbolic_weight += config["symbolic_boost"]

        # Check for agreement
        neural_trend = self._infer_neural_trend(neural_output)
        symbolic_trend = symbolic_output.trend_direction

        if neural_trend == symbolic_trend and neural_trend != TrendDirection.UNKNOWN:
            # Both agree - add bonus to confidence (keep weights balanced)
            pass  # Agreement bonus is implicit in higher confidence

        # Normalize weights
        total = neural_weight + symbolic_weight
        if total > 0:
            neural_weight /= total
            symbolic_weight /= total

        return neural_weight, symbolic_weight

    def _infer_neural_trend(self, neural_output: NeuralOutput) -> TrendDirection:
        """Infer trend direction from neural patterns."""
        if not neural_output.patterns:
            return TrendDirection.UNKNOWN

        # Check pattern names for trend indicators
        for pattern in neural_output.patterns:
            name = pattern["name"].lower()
            if "uptrend" in name or "bullish" in name:
                return TrendDirection.UP
            elif "downtrend" in name or "bearish" in name:
                return TrendDirection.DOWN

        return TrendDirection.SIDEWAYS

    def _fuse_predictions(
        self,
        neural_output: NeuralOutput,
        symbolic_output: SymbolicOutput,
        neural_weight: float,
        symbolic_weight: float,
    ) -> str:
        """Fuse predictions from both components."""
        predictions = []

        # Get neural prediction
        if neural_output.patterns:
            top_pattern = neural_output.patterns[0]
            predictions.append((f"Neural: {top_pattern['name']}", neural_weight))

        # Get symbolic prediction
        if symbolic_output.triggered_rules:
            rule_names = [r.rule_name for r in symbolic_output.triggered_rules[:2]]
            predictions.append((f"Rules: {', '.join(rule_names)}", symbolic_weight))

        # Get inference predictions
        if symbolic_output.inferred_facts:
            key_inferences = [
                k
                for k in symbolic_output.inferred_facts
                if "signal" in k or "confirmed" in k
            ][:2]
            if key_inferences:
                predictions.append((f"Inferred: {', '.join(key_inferences)}", 0.5))

        if not predictions:
            return "No significant signals detected"

        # Build prediction string
        sorted_predictions = sorted(predictions, key=lambda x: x[1], reverse=True)
        return " | ".join([p[0] for p in sorted_predictions[:3]])

    def _fuse_confidence(
        self,
        neural_confidence: float,
        symbolic_confidence: float,
        neural_weight: float,
        symbolic_weight: float,
    ) -> float:
        """Fuse confidence scores."""
        weighted_confidence = (
            neural_confidence * neural_weight + symbolic_confidence * symbolic_weight
        )

        # Apply agreement bonus if both are confident
        if neural_confidence > 0.5 and symbolic_confidence > 0.5:
            weighted_confidence = min(weighted_confidence * 1.1, 1.0)

        return round(weighted_confidence, 3)

    def _determine_fused_trend(
        self, neural_output: NeuralOutput, symbolic_output: SymbolicOutput
    ) -> TrendDirection:
        """Determine trend direction from fused outputs."""
        symbolic_trend = symbolic_output.trend_direction
        neural_trend = self._infer_neural_trend(neural_output)

        # Prefer symbolic for explicit direction
        if symbolic_trend != TrendDirection.UNKNOWN:
            return symbolic_trend

        return neural_trend

    def _build_contributing_factors(
        self, neural_output: NeuralOutput, symbolic_output: SymbolicOutput
    ) -> list[str]:
        """Build list of contributing factors."""
        factors = []

        # Add neural patterns
        for pattern in neural_output.patterns[:3]:
            factors.append(f"Pattern: {pattern['name']} ({pattern['confidence']:.2f})")

        # Add triggered rules
        for rule in symbolic_output.triggered_rules[:3]:
            factors.append(f"Rule: {rule.rule_name} ({rule.confidence:.2f})")

        # Add inferences
        for key, value in list(symbolic_output.inferred_facts.items())[:2]:
            factors.append(f"Inference: {key} = {value}")

        return factors

    def _generate_explanation(
        self,
        neural_output: NeuralOutput,
        symbolic_output: SymbolicOutput,
        prediction: str,
        confidence: float,
    ) -> str:
        """Generate human-readable explanation."""
        parts = []

        # Overall assessment
        if confidence >= 0.8:
            parts.append("High confidence")
        elif confidence >= 0.6:
            parts.append("Moderate confidence")
        else:
            parts.append("Low confidence")

        # Neural contribution
        if neural_output.patterns:
            pattern_names = [p["name"] for p in neural_output.patterns[:2]]
            parts.append(f"neural patterns: {', '.join(pattern_names)}")

        # Symbolic contribution
        if symbolic_output.triggered_rules:
            rule_names = [r.rule_name for r in symbolic_output.triggered_rules[:2]]
            parts.append(f"rules triggered: {', '.join(rule_names)}")

        # Key inferences
        if symbolic_output.inferred_facts:
            key_facts = [
                f"{k}: {v}" for k, v in list(symbolic_output.inferred_facts.items())[:1]
            ]
            if key_facts:
                parts.append(f"key inference: {key_facts[0]}")

        return ". ".join(parts) + "."
