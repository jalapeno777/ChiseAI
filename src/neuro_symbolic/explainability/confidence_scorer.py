"""Explanation Confidence Scorer Module.

Scores the confidence and reliability of explanations, providing
metrics for explanation quality assessment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
import logging
import math

logger = logging.getLogger(__name__)


class ConfidenceLevel(Enum):
    """Confidence levels for explanations."""

    VERY_HIGH = "very_high"  # > 0.9
    HIGH = "high"  # 0.75 - 0.9
    MODERATE = "moderate"  # 0.5 - 0.75
    LOW = "low"  # 0.25 - 0.5
    VERY_LOW = "very_low"  # < 0.25


@dataclass
class ConfidenceMetric:
    """A single confidence metric with details."""

    name: str
    value: float
    weight: float = 1.0
    description: str = ""
    factors: dict[str, float] = field(default_factory=dict)

    def __post_init__(self):
        """Validate metric value."""
        if not 0.0 <= self.value <= 1.0:
            raise ValueError(f"Metric value must be between 0 and 1, got {self.value}")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "name": self.name,
            "value": self.value,
            "weight": self.weight,
            "description": self.description,
            "factors": self.factors,
        }


@dataclass
class ConfidenceScore:
    """Complete confidence score with breakdown."""

    overall_score: float
    level: ConfidenceLevel
    metrics: list[ConfidenceMetric] = field(default_factory=list)
    reliability_factors: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_reliable(self) -> bool:
        """Check if explanation is considered reliable."""
        return self.overall_score >= 0.5

    @property
    def confidence_interval(self) -> tuple[float, float]:
        """Calculate confidence interval for the score."""
        margin = 0.1 * (1 - self.overall_score)  # Wider interval for lower confidence
        return (
            max(0, self.overall_score - margin),
            min(1, self.overall_score + margin),
        )

    def get_metric_by_name(self, name: str) -> Optional[ConfidenceMetric]:
        """Get a specific metric by name."""
        for metric in self.metrics:
            if metric.name == name:
                return metric
        return None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "overall_score": self.overall_score,
            "level": self.level.value,
            "is_reliable": self.is_reliable,
            "confidence_interval": self.confidence_interval,
            "metrics": [m.to_dict() for m in self.metrics],
            "reliability_factors": self.reliability_factors,
            "warnings": self.warnings,
            "metadata": self.metadata,
        }


@dataclass
class ScoringConfig:
    """Configuration for confidence scoring."""

    # Weights for different scoring components
    consistency_weight: float = 0.25
    completeness_weight: float = 0.20
    evidence_weight: float = 0.25
    clarity_weight: float = 0.15
    model_confidence_weight: float = 0.15

    # Thresholds
    low_confidence_threshold: float = 0.25
    moderate_confidence_threshold: float = 0.5
    high_confidence_threshold: float = 0.75
    very_high_confidence_threshold: float = 0.9

    # Minimum requirements
    min_reasoning_steps: int = 2
    min_key_factors: int = 1
    min_evidence_items: int = 0

    def get_weights(self) -> dict[str, float]:
        """Get all weights as dictionary."""
        return {
            "consistency": self.consistency_weight,
            "completeness": self.completeness_weight,
            "evidence": self.evidence_weight,
            "clarity": self.clarity_weight,
            "model_confidence": self.model_confidence_weight,
        }


class ExplanationConfidenceScorer:
    """Scores confidence of explanations for AI decisions.

    This class evaluates explanation quality across multiple dimensions
    and provides reliability metrics for explanation trustworthiness.

    Example:
        >>> scorer = ExplanationConfidenceScorer()
        >>> score = scorer.score_explanation({
        ...     'summary': 'Buy signal based on RSI and MACD',
        ...     'reasoning_chain': [...],
        ...     'key_factors': {'rsi': 0.3, 'macd': 0.5},
        ...     'overall_confidence': 0.85
        ... })
        >>> print(score.level)
        ConfidenceLevel.HIGH
    """

    # Threshold values for scoring
    _REASONING_QUALITY_THRESHOLDS = {
        "min_steps": 2,
        "good_steps": 4,
        "excellent_steps": 6,
    }

    _FACTOR_IMPORTANCE_THRESHOLDS = {
        "min_factors": 1,
        "good_factors": 3,
        "excellent_factors": 5,
    }

    def __init__(self, config: Optional[ScoringConfig] = None):
        """Initialize the confidence scorer.

        Args:
            config: Configuration for scoring.
                   Uses defaults if not provided.
        """
        self.config = config or ScoringConfig()
        logger.info(
            "ExplanationConfidenceScorer initialized with thresholds: "
            "low=%.2f, moderate=%.2f, high=%.2f",
            self.config.low_confidence_threshold,
            self.config.moderate_confidence_threshold,
            self.config.high_confidence_threshold,
        )

    def score_explanation(self, explanation: dict[str, Any]) -> ConfidenceScore:
        """Score the confidence of an explanation.

        Args:
            explanation: Dictionary containing:
                - summary: Text summary of explanation
                - reasoning_chain: List of reasoning steps
                - key_factors: Dictionary of key factors and importance
                - overall_confidence: Model's confidence in the decision
                - evidence: Optional supporting evidence
                - metadata: Optional additional context

        Returns:
            ConfidenceScore with detailed breakdown.
        """
        metrics = []
        warnings = []

        # Score consistency
        consistency_metric = self._score_consistency(explanation)
        metrics.append(consistency_metric)
        if consistency_metric.value < 0.5:
            warnings.append("Low consistency detected in reasoning chain")

        # Score completeness
        completeness_metric = self._score_completeness(explanation)
        metrics.append(completeness_metric)
        if completeness_metric.value < 0.5:
            warnings.append("Explanation lacks sufficient detail")

        # Score evidence quality
        evidence_metric = self._score_evidence(explanation)
        metrics.append(evidence_metric)
        if evidence_metric.value < 0.3:
            warnings.append("Limited supporting evidence provided")

        # Score clarity
        clarity_metric = self._score_clarity(explanation)
        metrics.append(clarity_metric)
        if clarity_metric.value < 0.5:
            warnings.append("Explanation clarity could be improved")

        # Score model confidence alignment
        model_confidence = explanation.get("overall_confidence", 0.5)
        model_metric = ConfidenceMetric(
            name="model_confidence",
            value=model_confidence,
            weight=self.config.model_confidence_weight,
            description="Confidence from the underlying model",
        )
        metrics.append(model_metric)

        # Calculate overall score
        overall_score = self._calculate_weighted_score(metrics)

        # Determine confidence level
        level = self._determine_confidence_level(overall_score)

        # Calculate reliability factors
        reliability_factors = self._calculate_reliability_factors(explanation, metrics)

        return ConfidenceScore(
            overall_score=overall_score,
            level=level,
            metrics=metrics,
            reliability_factors=reliability_factors,
            warnings=warnings,
            metadata={
                "explanation_type": explanation.get("explanation_type", "unknown"),
                "scoring_version": "1.0",
            },
        )

    def score_reasoning_chain(
        self,
        reasoning_chain: list[dict[str, Any]],
    ) -> ConfidenceMetric:
        """Score the quality of a reasoning chain.

        Args:
            reasoning_chain: List of reasoning steps.

        Returns:
            ConfidenceMetric for reasoning chain quality.
        """
        if not reasoning_chain:
            return ConfidenceMetric(
                name="reasoning_chain",
                value=0.0,
                weight=1.0,
                description="No reasoning chain provided",
            )

        # Score based on chain properties
        n_steps = len(reasoning_chain)

        # Step count score
        if n_steps >= self._REASONING_QUALITY_THRESHOLDS["excellent_steps"]:
            step_score = 1.0
        elif n_steps >= self._REASONING_QUALITY_THRESHOLDS["good_steps"]:
            step_score = 0.8
        elif n_steps >= self._REASONING_QUALITY_THRESHOLDS["min_steps"]:
            step_score = 0.6
        else:
            step_score = 0.3

        # Step quality score (average confidence)
        step_confidences = []
        for step in reasoning_chain:
            if isinstance(step, dict):
                conf = step.get("confidence", 0.5)
                if isinstance(conf, (int, float)):
                    step_confidences.append(conf)

        avg_confidence = (
            sum(step_confidences) / len(step_confidences) if step_confidences else 0.5
        )

        # Chain coherence score
        coherence_score = self._assess_chain_coherence(reasoning_chain)

        # Combined score
        combined_score = step_score * 0.4 + avg_confidence * 0.4 + coherence_score * 0.2

        return ConfidenceMetric(
            name="reasoning_chain",
            value=combined_score,
            weight=1.0,
            description=f"Reasoning chain with {n_steps} steps",
            factors={
                "step_count_score": step_score,
                "avg_step_confidence": avg_confidence,
                "coherence_score": coherence_score,
            },
        )

    def score_feature_importance(
        self,
        key_factors: dict[str, float],
    ) -> ConfidenceMetric:
        """Score the quality of feature importance explanation.

        Args:
            key_factors: Dictionary of features and their importance.

        Returns:
            ConfidenceMetric for feature importance quality.
        """
        if not key_factors:
            return ConfidenceMetric(
                name="feature_importance",
                value=0.0,
                weight=1.0,
                description="No key factors provided",
            )

        n_factors = len(key_factors)

        # Factor count score
        if n_factors >= self._FACTOR_IMPORTANCE_THRESHOLDS["excellent_factors"]:
            count_score = 1.0
        elif n_factors >= self._FACTOR_IMPORTANCE_THRESHOLDS["good_factors"]:
            count_score = 0.8
        elif n_factors >= self._FACTOR_IMPORTANCE_THRESHOLDS["min_factors"]:
            count_score = 0.6
        else:
            count_score = 0.3

        # Distribution score (are factors balanced or dominated by one?)
        values = list(key_factors.values())
        if values:
            max_val = max(values)
            sum_val = sum(values)
            dominance = max_val / sum_val if sum_val > 0 else 1.0

            # Lower dominance (more balanced) is better
            distribution_score = 1.0 - min(0.8, dominance)
        else:
            distribution_score = 0.5

        # Significance score (do factors have meaningful values?)
        significant_count = sum(1 for v in values if v > 0.1)
        significance_score = min(1.0, significant_count / max(1, n_factors))

        # Combined score
        combined_score = (
            count_score * 0.4 + distribution_score * 0.3 + significance_score * 0.3
        )

        return ConfidenceMetric(
            name="feature_importance",
            value=combined_score,
            weight=1.0,
            description=f"Feature importance with {n_factors} factors",
            factors={
                "count_score": count_score,
                "distribution_score": distribution_score,
                "significance_score": significance_score,
            },
        )

    def compare_explanations(
        self,
        explanations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Compare multiple explanations and rank by confidence.

        Args:
            explanations: List of explanation dictionaries.

        Returns:
            Dictionary with comparison results and rankings.
        """
        scored = []
        for i, explanation in enumerate(explanations):
            score = self.score_explanation(explanation)
            scored.append(
                {
                    "index": i,
                    "score": score.overall_score,
                    "level": score.level.value,
                    "is_reliable": score.is_reliable,
                }
            )

        # Sort by score descending
        ranked = sorted(scored, key=lambda x: x["score"], reverse=True)

        return {
            "rankings": ranked,
            "best_index": ranked[0]["index"] if ranked else None,
            "reliable_count": sum(1 for s in scored if s["is_reliable"]),
            "avg_score": sum(s["score"] for s in scored) / len(scored) if scored else 0,
        }

    def _score_consistency(self, explanation: dict[str, Any]) -> ConfidenceMetric:
        """Score internal consistency of the explanation."""
        reasoning_chain = explanation.get("reasoning_chain", [])
        key_factors = explanation.get("key_factors", {})
        overall_confidence = explanation.get("overall_confidence", 0.5)

        factors = {}

        # Check if reasoning steps have consistent confidence
        if reasoning_chain:
            step_confidences = [
                s.get("confidence", 0.5) for s in reasoning_chain if isinstance(s, dict)
            ]
            if step_confidences:
                avg_step_conf = sum(step_confidences) / len(step_confidences)
                conf_deviation = abs(avg_step_conf - overall_confidence)
                factors["confidence_alignment"] = 1.0 - min(1.0, conf_deviation * 2)
            else:
                factors["confidence_alignment"] = 0.5
        else:
            factors["confidence_alignment"] = 0.5

        # Check if key factors align with reasoning
        if key_factors and reasoning_chain:
            # Simple check: do reasoning steps reference the key factors?
            factor_names = set(key_factors.keys())
            referenced = set()
            for step in reasoning_chain:
                if isinstance(step, dict):
                    evidence = step.get("evidence", {})
                    if isinstance(evidence, dict):
                        referenced.update(evidence.keys())

            if factor_names:
                overlap = len(factor_names & referenced) / len(factor_names)
                factors["factor_coverage"] = overlap
            else:
                factors["factor_coverage"] = 0.5
        else:
            factors["factor_coverage"] = 0.5

        # Overall consistency score
        consistency_score = sum(factors.values()) / len(factors) if factors else 0.5

        return ConfidenceMetric(
            name="consistency",
            value=consistency_score,
            weight=self.config.consistency_weight,
            description="Internal consistency of explanation components",
            factors=factors,
        )

    def _score_completeness(self, explanation: dict[str, Any]) -> ConfidenceMetric:
        """Score completeness of the explanation."""
        factors = {}

        # Check for summary
        has_summary = bool(explanation.get("summary"))
        factors["has_summary"] = 1.0 if has_summary else 0.0

        # Check reasoning chain length
        reasoning_chain = explanation.get("reasoning_chain", [])
        n_steps = len(reasoning_chain)
        factors["reasoning_depth"] = min(1.0, n_steps / 4)

        # Check key factors
        key_factors = explanation.get("key_factors", {})
        n_factors = len(key_factors)
        factors["factor_coverage"] = min(1.0, n_factors / 3)

        # Check metadata
        has_metadata = bool(explanation.get("metadata"))
        factors["has_context"] = 0.5 if has_metadata else 0.0

        # Overall completeness score
        completeness_score = sum(factors.values()) / len(factors) if factors else 0.5

        return ConfidenceMetric(
            name="completeness",
            value=completeness_score,
            weight=self.config.completeness_weight,
            description="Completeness of explanation components",
            factors=factors,
        )

    def _score_evidence(self, explanation: dict[str, Any]) -> ConfidenceMetric:
        """Score the quality of supporting evidence."""
        factors = {}

        # Check for explicit evidence
        evidence = explanation.get("evidence", {})
        if isinstance(evidence, dict):
            n_evidence = len(evidence)
            factors["evidence_count"] = min(1.0, n_evidence / 3)
        else:
            factors["evidence_count"] = 0.0

        # Check reasoning chain evidence
        reasoning_chain = explanation.get("reasoning_chain", [])
        evidence_in_steps = 0
        for step in reasoning_chain:
            if isinstance(step, dict):
                step_evidence = step.get("evidence", {})
                if isinstance(step_evidence, dict) and step_evidence:
                    evidence_in_steps += 1

        if reasoning_chain:
            factors["step_evidence_ratio"] = evidence_in_steps / len(reasoning_chain)
        else:
            factors["step_evidence_ratio"] = 0.0

        # Check key factors as implicit evidence
        key_factors = explanation.get("key_factors", {})
        significant_factors = sum(1 for v in key_factors.values() if v > 0.1)
        factors["significant_factors"] = min(1.0, significant_factors / 3)

        # Overall evidence score
        evidence_score = sum(factors.values()) / len(factors) if factors else 0.5

        return ConfidenceMetric(
            name="evidence",
            value=evidence_score,
            weight=self.config.evidence_weight,
            description="Quality and quantity of supporting evidence",
            factors=factors,
        )

    def _score_clarity(self, explanation: dict[str, Any]) -> ConfidenceMetric:
        """Score the clarity of the explanation."""
        factors = {}

        # Check summary quality
        summary = explanation.get("summary", "")
        if summary:
            # Simple heuristics for clarity
            word_count = len(summary.split())

            # Too short or too long is less clear
            if word_count < 5:
                factors["summary_length"] = 0.3
            elif word_count > 100:
                factors["summary_length"] = 0.6
            else:
                factors["summary_length"] = 1.0

            # Check for clarity indicators
            clarity_words = ["because", "due to", "based on", "given", "therefore"]
            has_clarity_words = any(word in summary.lower() for word in clarity_words)
            factors["clarity_indicators"] = 0.3 if has_clarity_words else 0.0
        else:
            factors["summary_length"] = 0.0
            factors["clarity_indicators"] = 0.0

        # Check reasoning step descriptions
        reasoning_chain = explanation.get("reasoning_chain", [])
        if reasoning_chain:
            clear_steps = 0
            for step in reasoning_chain:
                if isinstance(step, dict):
                    desc = step.get("description", "")
                    if desc and len(desc.split()) >= 3:
                        clear_steps += 1

            factors["step_clarity"] = clear_steps / len(reasoning_chain)
        else:
            factors["step_clarity"] = 0.5

        # Overall clarity score
        clarity_score = sum(factors.values()) / len(factors) if factors else 0.5

        return ConfidenceMetric(
            name="clarity",
            value=clarity_score,
            weight=self.config.clarity_weight,
            description="Clarity and understandability of explanation",
            factors=factors,
        )

    def _assess_chain_coherence(self, reasoning_chain: list[Any]) -> float:
        """Assess coherence of the reasoning chain."""
        if len(reasoning_chain) < 2:
            return 0.5

        # Check step numbering consistency
        step_numbers = []
        for step in reasoning_chain:
            if isinstance(step, dict):
                num = step.get("step_number")
                if isinstance(num, int):
                    step_numbers.append(num)

        if step_numbers:
            expected = list(range(1, len(step_numbers) + 1))
            if step_numbers == expected:
                return 1.0
            elif sorted(step_numbers) == expected:
                return 0.7

        return 0.5

    def _calculate_weighted_score(
        self,
        metrics: list[ConfidenceMetric],
    ) -> float:
        """Calculate weighted overall score from metrics."""
        total_weight = sum(m.weight for m in metrics)
        if total_weight == 0:
            return 0.5

        weighted_sum = sum(m.value * m.weight for m in metrics)
        return weighted_sum / total_weight

    def _determine_confidence_level(self, score: float) -> ConfidenceLevel:
        """Determine confidence level from score."""
        if score >= self.config.very_high_confidence_threshold:
            return ConfidenceLevel.VERY_HIGH
        elif score >= self.config.high_confidence_threshold:
            return ConfidenceLevel.HIGH
        elif score >= self.config.moderate_confidence_threshold:
            return ConfidenceLevel.MODERATE
        elif score >= self.config.low_confidence_threshold:
            return ConfidenceLevel.LOW
        return ConfidenceLevel.VERY_LOW

    def _calculate_reliability_factors(
        self,
        explanation: dict[str, Any],
        metrics: list[ConfidenceMetric],
    ) -> dict[str, float]:
        """Calculate reliability factors for the explanation."""
        factors = {}

        # Data quality reliability
        evidence_metric = next((m for m in metrics if m.name == "evidence"), None)
        if evidence_metric:
            factors["data_quality"] = evidence_metric.value

        # Logic reliability
        consistency_metric = next((m for m in metrics if m.name == "consistency"), None)
        if consistency_metric:
            factors["logical_soundness"] = consistency_metric.value

        # Coverage reliability
        completeness_metric = next(
            (m for m in metrics if m.name == "completeness"), None
        )
        if completeness_metric:
            factors["coverage"] = completeness_metric.value

        # Model reliability
        model_confidence = explanation.get("overall_confidence", 0.5)
        factors["model_reliability"] = model_confidence

        return factors


__all__ = [
    "ConfidenceLevel",
    "ConfidenceMetric",
    "ConfidenceScore",
    "ScoringConfig",
    "ExplanationConfidenceScorer",
]
