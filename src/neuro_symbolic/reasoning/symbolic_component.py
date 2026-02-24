"""Symbolic component for rule-based reasoning."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RuleType(Enum):
    """Types of symbolic rules."""

    TREND = "trend"
    VOLUME = "volume"
    MOMENTUM = "momentum"
    VOLATILITY = "volatility"
    SUPPORT_RESISTANCE = "support_resistance"
    COMPOSITE = "composite"


class TrendDirection(Enum):
    """Trend direction indicators."""

    UP = "up"
    DOWN = "down"
    SIDEWAYS = "sideways"
    UNKNOWN = "unknown"


@dataclass
class RuleResult:
    """Result from applying a single rule."""

    rule_name: str
    rule_type: RuleType
    triggered: bool
    confidence: float
    value: Any
    explanation: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SymbolicOutput:
    """Output from symbolic component reasoning."""

    triggered_rules: list[RuleResult]
    trend_direction: TrendDirection
    overall_confidence: float
    explanations: list[str]
    inferred_facts: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)


class SymbolicRule(ABC):
    """Abstract base class for symbolic rules."""

    def __init__(self, name: str, rule_type: RuleType, weight: float = 1.0):
        self.name = name
        self.rule_type = rule_type
        self.weight = weight

    @abstractmethod
    def evaluate(self, data: dict[str, Any]) -> RuleResult:
        """Evaluate the rule against input data."""
        pass

    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        """Safely convert value to float."""
        try:
            return float(value) if value is not None else default
        except (TypeError, ValueError):
            return default


class TrendRule(SymbolicRule):
    """Rule for detecting trend direction."""

    def __init__(self, threshold: float = 0.02):
        super().__init__("trend_detection", RuleType.TREND, weight=1.5)
        self.threshold = threshold

    def evaluate(self, data: dict[str, Any]) -> RuleResult:
        price = self._safe_float(data.get("price"))
        prev_price = self._safe_float(data.get("prev_price"), price)
        sma_short = self._safe_float(data.get("sma_short"), price)
        sma_long = self._safe_float(data.get("sma_long"), price)

        triggered = False
        direction = TrendDirection.UNKNOWN
        confidence = 0.0
        explanation = "Insufficient data for trend analysis"

        if price > 0 and prev_price > 0:
            price_change = (price - prev_price) / prev_price

            if abs(price_change) > self.threshold:
                triggered = True
                direction = (
                    TrendDirection.UP if price_change > 0 else TrendDirection.DOWN
                )

                # Higher confidence for larger moves
                confidence = min(abs(price_change) / self.threshold, 1.0)
                explanation = f"Price {'increased' if price_change > 0 else 'decreased'} by {abs(price_change) * 100:.2f}%"

            # Check SMA crossover if available
            if sma_short > 0 and sma_long > 0:
                if sma_short > sma_long:
                    if direction == TrendDirection.UNKNOWN:
                        direction = TrendDirection.UP
                        confidence = 0.6
                    explanation += (
                        f"; SMA short ({sma_short:.2f}) above SMA long ({sma_long:.2f})"
                    )
                elif sma_short < sma_long:
                    if direction == TrendDirection.UNKNOWN:
                        direction = TrendDirection.DOWN
                        confidence = 0.6
                    explanation += (
                        f"; SMA short ({sma_short:.2f}) below SMA long ({sma_long:.2f})"
                    )

            if not triggered and abs(price_change) <= self.threshold:
                direction = TrendDirection.SIDEWAYS
                confidence = 0.5
                explanation = (
                    f"Price change ({abs(price_change) * 100:.2f}%) within threshold"
                )

        return RuleResult(
            rule_name=self.name,
            rule_type=self.rule_type,
            triggered=triggered,
            confidence=confidence * self.weight,
            value=direction,
            explanation=explanation,
        )


class VolumeRule(SymbolicRule):
    """Rule for analyzing volume patterns."""

    def __init__(self, spike_threshold: float = 2.0):
        super().__init__("volume_analysis", RuleType.VOLUME, weight=1.2)
        self.spike_threshold = spike_threshold

    def evaluate(self, data: dict[str, Any]) -> RuleResult:
        volume = self._safe_float(data.get("volume"))
        avg_volume = self._safe_float(data.get("avg_volume"), volume)
        prev_volume = self._safe_float(data.get("prev_volume"), volume)

        triggered = False
        confidence = 0.0
        explanation = "Volume data unavailable"
        volume_signal = "normal"

        if volume > 0 and avg_volume > 0:
            volume_ratio = volume / avg_volume

            if volume_ratio > self.spike_threshold:
                triggered = True
                volume_signal = "spike"
                confidence = min(volume_ratio / self.spike_threshold, 1.0)
                explanation = f"Volume spike detected: {volume_ratio:.2f}x average"
            elif volume_ratio < 1.0 / self.spike_threshold:
                triggered = True
                volume_signal = "drought"
                confidence = min(avg_volume / volume / self.spike_threshold, 1.0)
                explanation = f"Volume drought detected: {volume_ratio:.2f}x average"
            else:
                confidence = 0.3
                explanation = f"Volume normal: {volume_ratio:.2f}x average"

            # Check volume trend
            if prev_volume > 0:
                vol_change = (volume - prev_volume) / prev_volume
                if abs(vol_change) > 0.5:
                    explanation += f"; Volume {'increased' if vol_change > 0 else 'decreased'} by {abs(vol_change) * 100:.1f}%"

        return RuleResult(
            rule_name=self.name,
            rule_type=self.rule_type,
            triggered=triggered,
            confidence=confidence * self.weight,
            value=volume_signal,
            explanation=explanation,
            metadata={"volume_ratio": volume / avg_volume if avg_volume > 0 else 1.0},
        )


class MomentumRule(SymbolicRule):
    """Rule for momentum analysis."""

    def __init__(self, strong_momentum_threshold: float = 0.05):
        super().__init__("momentum_analysis", RuleType.MOMENTUM, weight=1.3)
        self.strong_momentum_threshold = strong_momentum_threshold

    def evaluate(self, data: dict[str, Any]) -> RuleResult:
        price = self._safe_float(data.get("price"))
        prev_price = self._safe_float(data.get("prev_price"), price)
        prev_price_2 = self._safe_float(data.get("prev_price_2"), prev_price)

        triggered = False
        confidence = 0.0
        explanation = "Momentum data unavailable"
        momentum_type = "neutral"

        if price > 0 and prev_price > 0:
            # Calculate momentum (rate of change)
            current_change = (price - prev_price) / prev_price
            prior_change = (
                (prev_price - prev_price_2) / prev_price_2 if prev_price_2 > 0 else 0
            )

            momentum_acceleration = current_change - prior_change

            if abs(current_change) > self.strong_momentum_threshold:
                triggered = True
                momentum_type = (
                    "strong_bullish" if current_change > 0 else "strong_bearish"
                )
                confidence = min(
                    abs(current_change) / self.strong_momentum_threshold, 1.0
                )
                explanation = f"Strong {'bullish' if current_change > 0 else 'bearish'} momentum: {abs(current_change) * 100:.2f}%"
            elif abs(current_change) > self.strong_momentum_threshold / 2:
                momentum_type = "bullish" if current_change > 0 else "bearish"
                confidence = 0.5
                explanation = f"Moderate {'bullish' if current_change > 0 else 'bearish'} momentum: {abs(current_change) * 100:.2f}%"
            else:
                confidence = 0.2
                explanation = f"Weak momentum: {abs(current_change) * 100:.2f}%"

            # Check for momentum acceleration/deceleration
            if abs(momentum_acceleration) > 0.02:
                accel_type = (
                    "accelerating" if momentum_acceleration > 0 else "decelerating"
                )
                explanation += f"; Momentum {accel_type}"

        return RuleResult(
            rule_name=self.name,
            rule_type=self.rule_type,
            triggered=triggered,
            confidence=confidence * self.weight,
            value=momentum_type,
            explanation=explanation,
        )


class VolatilityRule(SymbolicRule):
    """Rule for volatility assessment."""

    def __init__(self, high_volatility_threshold: float = 0.05):
        super().__init__("volatility_analysis", RuleType.VOLATILITY, weight=1.0)
        self.high_volatility_threshold = high_volatility_threshold

    def evaluate(self, data: dict[str, Any]) -> RuleResult:
        high = self._safe_float(data.get("high"))
        low = self._safe_float(data.get("low"))
        price = self._safe_float(data.get("price"))
        atr = self._safe_float(data.get("atr"))  # Average True Range if available

        triggered = False
        confidence = 0.0
        explanation = "Volatility data unavailable"
        volatility_level = "unknown"

        # Calculate range-based volatility
        if high > 0 and low > 0 and price > 0:
            range_pct = (high - low) / price

            if range_pct > self.high_volatility_threshold:
                triggered = True
                volatility_level = "high"
                confidence = min(range_pct / self.high_volatility_threshold, 1.0)
                explanation = f"High volatility: {range_pct * 100:.2f}% range"
            elif range_pct > self.high_volatility_threshold / 2:
                volatility_level = "moderate"
                confidence = 0.5
                explanation = f"Moderate volatility: {range_pct * 100:.2f}% range"
            else:
                volatility_level = "low"
                confidence = 0.3
                explanation = f"Low volatility: {range_pct * 100:.2f}% range"
        elif atr > 0 and price > 0:
            # Use ATR if available
            atr_pct = atr / price
            if atr_pct > self.high_volatility_threshold:
                triggered = True
                volatility_level = "high"
                confidence = min(atr_pct / self.high_volatility_threshold, 1.0)
                explanation = f"High volatility (ATR): {atr_pct * 100:.2f}%"

        return RuleResult(
            rule_name=self.name,
            rule_type=self.rule_type,
            triggered=triggered,
            confidence=confidence * self.weight,
            value=volatility_level,
            explanation=explanation,
        )


class SupportResistanceRule(SymbolicRule):
    """Rule for support/resistance level analysis."""

    def __init__(self, proximity_threshold: float = 0.02):
        super().__init__("support_resistance", RuleType.SUPPORT_RESISTANCE, weight=1.1)
        self.proximity_threshold = proximity_threshold

    def evaluate(self, data: dict[str, Any]) -> RuleResult:
        price = self._safe_float(data.get("price"))
        support = self._safe_float(data.get("support"))
        resistance = self._safe_float(data.get("resistance"))

        triggered = False
        confidence = 0.0
        explanation = "Support/resistance levels not defined"
        level_type = "none"
        proximity = 0.0

        if price > 0:
            if support > 0:
                support_distance = (price - support) / price
                if (
                    support_distance < self.proximity_threshold
                    and support_distance >= 0
                ):
                    triggered = True
                    level_type = "support_test"
                    proximity = support_distance
                    confidence = 1.0 - (support_distance / self.proximity_threshold)
                    explanation = f"Testing support at {support:.2f} ({support_distance * 100:.2f}% away)"
                elif support_distance < 0:
                    triggered = True
                    level_type = "support_broken"
                    confidence = 0.8
                    explanation = f"Support at {support:.2f} broken"

            if resistance > 0:
                resistance_distance = (resistance - price) / price
                if (
                    resistance_distance < self.proximity_threshold
                    and resistance_distance >= 0
                ):
                    triggered = True
                    level_type = "resistance_test"
                    proximity = resistance_distance
                    confidence = max(
                        confidence,
                        1.0 - (resistance_distance / self.proximity_threshold),
                    )
                    explanation = f"Testing resistance at {resistance:.2f} ({resistance_distance * 100:.2f}% away)"
                elif resistance_distance < 0:
                    triggered = True
                    level_type = "resistance_broken"
                    confidence = max(confidence, 0.8)
                    explanation = f"Resistance at {resistance:.2f} broken"

            if not triggered and (support > 0 or resistance > 0):
                confidence = 0.2
                explanation = "Price not near key levels"

        return RuleResult(
            rule_name=self.name,
            rule_type=self.rule_type,
            triggered=triggered,
            confidence=confidence * self.weight,
            value=level_type,
            explanation=explanation,
            metadata={"proximity": proximity},
        )


class InferenceEngine:
    """Engine for logical inference over rule results."""

    def __init__(self):
        self._inference_rules = [
            self._infer_trend_confirmation,
            self._infer_reversal_signal,
            self._infer_breakout_signal,
            self._infer_risk_level,
        ]

    def infer(self, rule_results: list[RuleResult]) -> dict[str, Any]:
        """Run inference over rule results to derive new facts."""
        inferred = {}

        for inference_func in self._inference_rules:
            try:
                result = inference_func(rule_results)
                inferred.update(result)
            except Exception:
                continue

        return inferred

    def _infer_trend_confirmation(self, results: list[RuleResult]) -> dict[str, Any]:
        """Infer trend confirmation from multiple signals."""
        trend_results = [r for r in results if r.rule_type == RuleType.TREND]
        momentum_results = [r for r in results if r.rule_type == RuleType.MOMENTUM]

        inferred = {}

        if trend_results and momentum_results:
            trend_dir = trend_results[0].value
            mom_type = momentum_results[0].value

            if trend_dir == TrendDirection.UP and "bullish" in str(mom_type):
                inferred["trend_confirmed"] = "bullish"
                inferred["trend_strength"] = "strong"
            elif trend_dir == TrendDirection.DOWN and "bearish" in str(mom_type):
                inferred["trend_confirmed"] = "bearish"
                inferred["trend_strength"] = "strong"

        return inferred

    def _infer_reversal_signal(self, results: list[RuleResult]) -> dict[str, Any]:
        """Infer potential reversal signals."""
        inferred = {}

        sr_result = next(
            (r for r in results if r.rule_type == RuleType.SUPPORT_RESISTANCE), None
        )
        volume_result = next(
            (r for r in results if r.rule_type == RuleType.VOLUME), None
        )

        if sr_result and volume_result:
            if "test" in str(sr_result.value) and volume_result.value == "spike":
                inferred["reversal_signal"] = True
                inferred["reversal_confidence"] = min(
                    sr_result.confidence, volume_result.confidence
                )

        return inferred

    def _infer_breakout_signal(self, results: list[RuleResult]) -> dict[str, Any]:
        """Infer breakout signals."""
        inferred = {}

        sr_result = next(
            (r for r in results if r.rule_type == RuleType.SUPPORT_RESISTANCE), None
        )
        volume_result = next(
            (r for r in results if r.rule_type == RuleType.VOLUME), None
        )
        volatility_result = next(
            (r for r in results if r.rule_type == RuleType.VOLATILITY), None
        )

        if sr_result and "broken" in str(sr_result.value):
            inferred["breakout_signal"] = True
            inferred["breakout_type"] = sr_result.value

            if volume_result and volume_result.value == "spike":
                inferred["breakout_confirmed"] = True
            if volatility_result and volatility_result.value == "high":
                inferred["breakout_volatility"] = "high"

        return inferred

    def _infer_risk_level(self, results: list[RuleResult]) -> dict[str, Any]:
        """Infer overall risk level."""
        inferred = {}

        risk_factors = 0
        max_confidence = 0.0

        for result in results:
            if result.triggered:
                if (
                    result.rule_type == RuleType.VOLATILITY
                    and result.value == "high"
                    or (
                        result.rule_type == RuleType.SUPPORT_RESISTANCE
                        and "broken" in str(result.value)
                    )
                ):
                    risk_factors += 1
                    max_confidence = max(max_confidence, result.confidence)

        if risk_factors >= 2:
            inferred["risk_level"] = "high"
            inferred["risk_confidence"] = max_confidence
        elif risk_factors == 1:
            inferred["risk_level"] = "moderate"
            inferred["risk_confidence"] = max_confidence
        else:
            inferred["risk_level"] = "low"
            inferred["risk_confidence"] = 0.3

        return inferred


class SymbolicComponent:
    """Symbolic reasoning component for hybrid engine.

    Implements rule-based reasoning for market analysis using
    logical inference and explainable rules.
    """

    def __init__(self, confidence_threshold: float = 0.5):
        self.confidence_threshold = confidence_threshold

        # Initialize rules
        self._rules: list[SymbolicRule] = [
            TrendRule(),
            VolumeRule(),
            MomentumRule(),
            VolatilityRule(),
            SupportResistanceRule(),
        ]

        # Initialize inference engine
        self._inference_engine = InferenceEngine()

        # State tracking
        self._last_results: list[RuleResult] = []

    def process(self, data: dict[str, Any]) -> SymbolicOutput:
        """Process input data through symbolic rules.

        Args:
            data: Input market data dictionary.

        Returns:
            SymbolicOutput containing rule results and inferences.
        """
        # Evaluate all rules
        results = []
        for rule in self._rules:
            try:
                result = rule.evaluate(data)
                results.append(result)
            except Exception as e:
                # Log error but continue
                results.append(
                    RuleResult(
                        rule_name=rule.name,
                        rule_type=rule.rule_type,
                        triggered=False,
                        confidence=0.0,
                        value=None,
                        explanation=f"Rule evaluation failed: {str(e)}",
                    )
                )

        self._last_results = results

        # Get triggered rules above threshold
        triggered = [
            r
            for r in results
            if r.triggered and r.confidence >= self.confidence_threshold
        ]

        # Determine overall trend direction
        trend_direction = self._determine_trend(results)

        # Calculate overall confidence
        if results:
            overall_confidence = sum(
                r.confidence for r in results if r.triggered
            ) / len(self._rules)
        else:
            overall_confidence = 0.0

        # Generate explanations
        explanations = [r.explanation for r in triggered if r.explanation]

        # Run inference
        inferred_facts = self._inference_engine.infer(results)

        return SymbolicOutput(
            triggered_rules=triggered,
            trend_direction=trend_direction,
            overall_confidence=overall_confidence,
            explanations=explanations,
            inferred_facts=inferred_facts,
            metadata={
                "total_rules": len(self._rules),
                "triggered_count": len(triggered),
                "processing_type": "symbolic",
            },
        )

    def _determine_trend(self, results: list[RuleResult]) -> TrendDirection:
        """Determine overall trend from rule results."""
        trend_result = next((r for r in results if r.rule_type == RuleType.TREND), None)

        if trend_result and isinstance(trend_result.value, TrendDirection):
            return trend_result.value

        return TrendDirection.UNKNOWN

    def add_rule(self, rule: SymbolicRule) -> None:
        """Add a custom rule to the component."""
        self._rules.append(rule)

    def remove_rule(self, rule_name: str) -> bool:
        """Remove a rule by name."""
        for i, rule in enumerate(self._rules):
            if rule.name == rule_name:
                self._rules.pop(i)
                return True
        return False

    def get_rule(self, rule_name: str) -> SymbolicRule | None:
        """Get a rule by name."""
        for rule in self._rules:
            if rule.name == rule_name:
                return rule
        return None
