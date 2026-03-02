"""Explanation Generator Module.

Generates human-readable explanations for AI trading decisions using
natural language generation for reasoning chains.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ExplanationType(Enum):
    """Types of explanations that can be generated."""

    SIGNAL = "signal"  # Trading signal explanation
    PREDICTION = "prediction"  # Price prediction explanation
    RISK = "risk"  # Risk assessment explanation
    PORTFOLIO = "portfolio"  # Portfolio decision explanation
    MARKET_REGIME = "market_regime"  # Market regime classification explanation
    FEATURE_CONTRIBUTION = "feature_contribution"  # Feature importance explanation


@dataclass
class ReasoningStep:
    """A single step in the reasoning chain."""

    step_number: int
    description: str
    evidence: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0

    def __post_init__(self):
        """Validate reasoning step."""
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"Confidence must be between 0 and 1, got {self.confidence}"
            )


@dataclass
class ExplanationResult:
    """Complete explanation result with reasoning chain."""

    explanation_type: ExplanationType
    summary: str
    reasoning_chain: list[ReasoningStep] = field(default_factory=list)
    key_factors: dict[str, float] = field(default_factory=dict)
    overall_confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate explanation result."""
        if not 0.0 <= self.overall_confidence <= 1.0:
            raise ValueError(
                f"Overall confidence must be between 0 and 1, got {self.overall_confidence}"
            )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "explanation_type": self.explanation_type.value,
            "summary": self.summary,
            "reasoning_chain": [
                {
                    "step_number": step.step_number,
                    "description": step.description,
                    "evidence": step.evidence,
                    "confidence": step.confidence,
                }
                for step in self.reasoning_chain
            ],
            "key_factors": self.key_factors,
            "overall_confidence": self.overall_confidence,
            "metadata": self.metadata,
        }


@dataclass
class ExplanationConfig:
    """Configuration for explanation generation."""

    max_reasoning_steps: int = 5
    min_confidence_threshold: float = 0.1
    include_evidence: bool = True
    language_style: str = "professional"  # professional, casual, technical
    detail_level: str = "standard"  # brief, standard, detailed


class ExplanationGenerator:
    """Generates human-readable explanations for AI decisions.

    This class produces natural language explanations with reasoning chains
    for various types of trading decisions including signals, predictions,
    risk assessments, and portfolio decisions.

    Example:
        >>> generator = ExplanationGenerator()
        >>> result = generator.explain({
        ...     'prediction': 'buy',
        ...     'confidence': 0.85,
        ...     'features': {'rsi': 0.3, 'macd': 0.7}
        ... })
        >>> print(result.summary)
        'Strong buy signal with 85% confidence based on oversold RSI and bullish MACD crossover.'
    """

    # Templates for different decision types
    _SUMMARY_TEMPLATES = {
        "buy": {
            "high_confidence": "Strong buy signal with {confidence:.0%} confidence. {primary_reason}",
            "medium_confidence": "Moderate buy signal with {confidence:.0%} confidence. {primary_reason}",
            "low_confidence": "Weak buy signal with {confidence:.0%} confidence. {primary_reason}",
        },
        "sell": {
            "high_confidence": "Strong sell signal with {confidence:.0%} confidence. {primary_reason}",
            "medium_confidence": "Moderate sell signal with {confidence:.0%} confidence. {primary_reason}",
            "low_confidence": "Weak sell signal with {confidence:.0%} confidence. {primary_reason}",
        },
        "hold": {
            "high_confidence": "Hold position recommended with {confidence:.0%} confidence. {primary_reason}",
            "medium_confidence": "Hold position suggested with {confidence:.0%} confidence. {primary_reason}",
            "low_confidence": "Uncertain hold with {confidence:.0%} confidence. {primary_reason}",
        },
    }

    # Feature impact descriptions
    _FEATURE_DESCRIPTIONS = {
        "rsi": {
            "oversold": "RSI indicates oversold conditions",
            "overbought": "RSI indicates overbought conditions",
            "neutral": "RSI in neutral territory",
        },
        "macd": {
            "bullish": "MACD shows bullish momentum",
            "bearish": "MACD shows bearish momentum",
            "neutral": "MACD indicates neutral momentum",
        },
        "volume": {
            "high": "High volume supports the signal",
            "low": "Low volume weakens confidence",
            "average": "Average volume observed",
        },
        "trend": {
            "uptrend": "Asset in uptrend",
            "downtrend": "Asset in downtrend",
            "sideways": "Asset in consolidation",
        },
        "volatility": {
            "high": "High volatility increases risk",
            "low": "Low volatility environment",
            "normal": "Normal volatility levels",
        },
    }

    def __init__(self, config: ExplanationConfig | None = None):
        """Initialize the explanation generator.

        Args:
            config: Configuration for explanation generation.
                   Uses defaults if not provided.
        """
        self.config = config or ExplanationConfig()
        logger.info(
            "ExplanationGenerator initialized with detail_level=%s",
            self.config.detail_level,
        )

    def explain(self, decision_data: dict[str, Any]) -> ExplanationResult:
        """Generate an explanation for a trading decision.

        Args:
            decision_data: Dictionary containing:
                - prediction: The decision (buy/sell/hold)
                - confidence: Confidence score (0-1)
                - features: Dictionary of feature values
                - feature_contributions: Optional feature importance scores
                - metadata: Additional context

        Returns:
            ExplanationResult with summary and reasoning chain.

        Raises:
            ValueError: If required fields are missing or invalid.
        """
        # Validate input
        self._validate_decision_data(decision_data)

        prediction = decision_data.get("prediction", "hold")
        confidence = decision_data.get("confidence", 0.5)
        features = decision_data.get("features", {})
        feature_contributions = decision_data.get("feature_contributions", {})
        metadata = decision_data.get("metadata", {})

        # Determine explanation type
        explanation_type = self._determine_explanation_type(decision_data)

        # Build reasoning chain
        reasoning_chain = self._build_reasoning_chain(
            prediction=prediction,
            confidence=confidence,
            features=features,
            feature_contributions=feature_contributions,
        )

        # Generate summary
        summary = self._generate_summary(
            prediction=prediction,
            confidence=confidence,
            features=features,
            feature_contributions=feature_contributions,
        )

        # Extract key factors
        key_factors = self._extract_key_factors(
            features=features,
            feature_contributions=feature_contributions,
        )

        return ExplanationResult(
            explanation_type=explanation_type,
            summary=summary,
            reasoning_chain=reasoning_chain,
            key_factors=key_factors,
            overall_confidence=confidence,
            metadata=metadata,
        )

    def explain_signal(
        self,
        signal_type: str,
        confidence: float,
        contributing_factors: dict[str, float],
    ) -> ExplanationResult:
        """Generate an explanation specifically for a trading signal.

        Args:
            signal_type: Type of signal (buy/sell/hold).
            confidence: Signal confidence score.
            contributing_factors: Factors and their contribution scores.

        Returns:
            ExplanationResult for the signal.
        """
        return self.explain(
            {
                "prediction": signal_type,
                "confidence": confidence,
                "feature_contributions": contributing_factors,
            }
        )

    def explain_prediction(
        self,
        prediction: str,
        confidence: float,
        features: dict[str, Any],
        timeframe: str | None = None,
    ) -> ExplanationResult:
        """Generate an explanation for a price prediction.

        Args:
            prediction: Prediction direction (up/down/neutral).
            confidence: Prediction confidence.
            features: Features used in prediction.
            timeframe: Optional prediction timeframe.

        Returns:
            ExplanationResult for the prediction.
        """
        metadata = {"timeframe": timeframe} if timeframe else {}
        return self.explain(
            {
                "prediction": prediction,
                "confidence": confidence,
                "features": features,
                "metadata": metadata,
            }
        )

    def explain_risk_assessment(
        self,
        risk_level: str,
        risk_score: float,
        risk_factors: dict[str, float],
    ) -> ExplanationResult:
        """Generate an explanation for a risk assessment.

        Args:
            risk_level: Risk level (low/medium/high).
            risk_score: Numerical risk score.
            risk_factors: Factors contributing to risk.

        Returns:
            ExplanationResult for the risk assessment.
        """
        return self.explain(
            {
                "prediction": risk_level,
                "confidence": risk_score,
                "feature_contributions": risk_factors,
                "metadata": {"assessment_type": "risk"},
            }
        )

    def _validate_decision_data(self, data: dict[str, Any]) -> None:
        """Validate decision data has required fields."""
        if not isinstance(data, dict):
            raise ValueError("decision_data must be a dictionary")

        prediction = data.get("prediction")
        if prediction and prediction.lower() not in (
            "buy",
            "sell",
            "hold",
            "up",
            "down",
            "neutral",
            "low",
            "medium",
            "high",
        ):
            logger.warning("Unusual prediction value: %s", prediction)

        confidence = data.get("confidence")
        if confidence is not None:
            if not isinstance(confidence, (int, float)):
                raise ValueError(f"confidence must be numeric, got {type(confidence)}")
            if not 0 <= confidence <= 1:
                raise ValueError(
                    f"confidence must be between 0 and 1, got {confidence}"
                )

    def _determine_explanation_type(self, data: dict[str, Any]) -> ExplanationType:
        """Determine the type of explanation based on input data."""
        metadata = data.get("metadata", {})

        if metadata.get("assessment_type") == "risk":
            return ExplanationType.RISK

        # Check if this is a prediction (directional forecast)
        prediction = data.get("prediction", "")
        if prediction.lower() in ("up", "down", "neutral"):
            return ExplanationType.PREDICTION

        return ExplanationType.SIGNAL

    def _build_reasoning_chain(
        self,
        prediction: str,
        confidence: float,
        features: dict[str, Any],
        feature_contributions: dict[str, float],
    ) -> list[ReasoningStep]:
        """Build the reasoning chain for the explanation."""
        chain = []
        step_num = 1

        # Step 1: Signal/prediction identification
        chain.append(
            ReasoningStep(
                step_number=step_num,
                description=f"Identified {prediction} signal with {confidence:.0%} confidence",
                evidence={"prediction": prediction, "confidence": confidence},
                confidence=confidence,
            )
        )
        step_num += 1

        # Step 2: Feature analysis
        if features:
            feature_desc = self._describe_features(features)
            chain.append(
                ReasoningStep(
                    step_number=step_num,
                    description=f"Technical analysis: {feature_desc}",
                    evidence=features,
                    confidence=self._calculate_feature_confidence(features),
                )
            )
            step_num += 1

        # Step 3: Contribution analysis (if available)
        if feature_contributions:
            top_contributors = self._get_top_contributors(feature_contributions)
            chain.append(
                ReasoningStep(
                    step_number=step_num,
                    description=f"Primary drivers: {', '.join(top_contributors)}",
                    evidence=feature_contributions,
                    confidence=(
                        max(feature_contributions.values())
                        if feature_contributions
                        else 0.5
                    ),
                )
            )
            step_num += 1

        # Step 4: Market context (if available)
        if step_num <= self.config.max_reasoning_steps:
            chain.append(
                ReasoningStep(
                    step_number=step_num,
                    description=f"Signal strength assessment: {self._get_strength_level(confidence)}",
                    evidence={"strength": self._get_strength_level(confidence)},
                    confidence=confidence,
                )
            )

        return chain

    def _generate_summary(
        self,
        prediction: str,
        confidence: float,
        features: dict[str, Any],
        feature_contributions: dict[str, float],
    ) -> str:
        """Generate a human-readable summary."""
        # Normalize prediction
        pred_key = prediction.lower() if prediction else "hold"

        # Determine confidence level
        if confidence >= 0.75:
            conf_level = "high_confidence"
        elif confidence >= 0.5:
            conf_level = "medium_confidence"
        else:
            conf_level = "low_confidence"

        # Get primary reason
        primary_reason = self._get_primary_reason(features, feature_contributions)

        # Get template
        templates = self._SUMMARY_TEMPLATES.get(
            pred_key, self._SUMMARY_TEMPLATES["hold"]
        )
        template = templates.get(conf_level, templates["medium_confidence"])

        return template.format(
            confidence=confidence,
            primary_reason=primary_reason,
        )

    def _get_primary_reason(
        self,
        features: dict[str, Any],
        feature_contributions: dict[str, float],
    ) -> str:
        """Get the primary reason for the decision."""
        reasons = []

        # Check feature contributions first
        if feature_contributions:
            top_feature = max(feature_contributions.items(), key=lambda x: abs(x[1]))
            feature_name, contribution = top_feature
            if abs(contribution) > 0.1:
                reasons.append(f"driven primarily by {feature_name}")

        # Add feature descriptions
        if features:
            if "rsi" in features:
                rsi_val = features["rsi"]
                if rsi_val < 30:
                    reasons.append("oversold RSI conditions")
                elif rsi_val > 70:
                    reasons.append("overbought RSI conditions")

            if "macd" in features:
                macd_val = features["macd"]
                if macd_val > 0:
                    reasons.append("bullish MACD")
                elif macd_val < 0:
                    reasons.append("bearish MACD")

        if reasons:
            return "Decision is " + " and ".join(reasons[:2]) + "."

        return "Based on current market conditions."

    def _describe_features(self, features: dict[str, Any]) -> str:
        """Generate description of feature values."""
        descriptions = []

        for feature, value in features.items():
            if feature in self._FEATURE_DESCRIPTIONS:
                desc = self._get_feature_description(feature, value)
                if desc:
                    descriptions.append(desc)

        return "; ".join(descriptions) if descriptions else "features analyzed"

    def _get_feature_description(self, feature: str, value: Any) -> str:
        """Get description for a specific feature value."""
        descriptions = self._FEATURE_DESCRIPTIONS.get(feature, {})

        if feature == "rsi":
            if value < 30:
                return descriptions.get("oversold", "")
            elif value > 70:
                return descriptions.get("overbought", "")
            return descriptions.get("neutral", "")

        if feature == "macd":
            if value > 0:
                return descriptions.get("bullish", "")
            elif value < 0:
                return descriptions.get("bearish", "")
            return descriptions.get("neutral", "")

        if feature == "volume":
            if value > 1.5:
                return descriptions.get("high", "")
            elif value < 0.5:
                return descriptions.get("low", "")
            return descriptions.get("average", "")

        return ""

    def _calculate_feature_confidence(self, features: dict[str, Any]) -> float:
        """Calculate confidence based on feature consistency."""
        if not features:
            return 0.5

        # Simple heuristic: more features = higher confidence
        return min(0.5 + len(features) * 0.1, 0.95)

    def _get_top_contributors(
        self,
        contributions: dict[str, float],
        n: int = 3,
    ) -> list[str]:
        """Get top N contributing features."""
        sorted_items = sorted(
            contributions.items(),
            key=lambda x: abs(x[1]),
            reverse=True,
        )
        return [f"{name} ({val:+.2f})" for name, val in sorted_items[:n]]

    def _get_strength_level(self, confidence: float) -> str:
        """Get strength level description."""
        if confidence >= 0.8:
            return "very strong"
        elif confidence >= 0.6:
            return "strong"
        elif confidence >= 0.4:
            return "moderate"
        elif confidence >= 0.2:
            return "weak"
        return "very weak"

    def _extract_key_factors(
        self,
        features: dict[str, Any],
        feature_contributions: dict[str, float],
    ) -> dict[str, float]:
        """Extract key factors and their importance."""
        factors = {}

        # Use contributions if available
        if feature_contributions:
            for name, contribution in feature_contributions.items():
                if abs(contribution) > 0.05:  # Threshold for significance
                    factors[name] = abs(contribution)
        elif features:
            # Infer importance from feature values
            for name, value in features.items():
                if isinstance(value, (int, float)):
                    factors[name] = abs(float(value))

        return factors


__all__ = [
    "ExplanationType",
    "ReasoningStep",
    "ExplanationResult",
    "ExplanationConfig",
    "ExplanationGenerator",
]
