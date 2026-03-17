"""Main Hypothesis Generator for the STRONG neuro-symbolic AI system.

Provides the HypothesisGenerator class for generating testable hypotheses
from belief clusters and market context using LLM capabilities.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

import numpy as np

from src.strong_system.belief_embeddings import BeliefVector
from src.strong_system.hypothesis_generator.templates import (
    get_template_registry,
    render_prompt,
)
from src.strong_system.hypothesis_generator.types import (
    ConfidenceScore,
    GenerationResult,
    GeneratorConfig,
    Hypothesis,
    HypothesisType,
    MarketContext,
)
from src.strong_system.hypothesis_generator.validator import (
    HypothesisValidator,
    ValidationConfig,
    ValidationResult,
)


class LLMProvider(Protocol):
    """Protocol for LLM providers."""

    def generate(
        self, system_prompt: str, user_prompt: str, **kwargs: Any
    ) -> dict[str, Any]:
        """Generate a response from the LLM.

        Args:
            system_prompt: System-level instructions
            user_prompt: User query/prompt
            **kwargs: Additional generation parameters

        Returns:
            Dictionary with generated content
        """
        ...


class MockLLMProvider:
    """Mock LLM provider for testing."""

    def generate(
        self, system_prompt: str, user_prompt: str, **kwargs: Any
    ) -> dict[str, Any]:
        """Generate mock hypothesis data."""
        # Extract hypothesis type from prompt
        hypothesis_type = HypothesisType.TREND
        if "REVERSAL" in user_prompt:
            hypothesis_type = HypothesisType.REVERSAL
        elif "RANGE" in user_prompt:
            hypothesis_type = HypothesisType.RANGE
        elif "BREAKOUT" in user_prompt:
            hypothesis_type = HypothesisType.BREAKOUT

        # Generate mock hypotheses
        hypotheses = [
            {
                "description": f"Mock {hypothesis_type.name.lower()} hypothesis",
                "prediction": "Price will increase by 5% within 24 hours",
                "confidence": 0.75,
                "reasoning": "Based on technical indicators and belief cluster analysis",
            }
        ]

        return {
            "hypotheses": hypotheses,
            "raw_response": "Mock LLM response",
        }


@dataclass
class GeneratorMetrics:
    """Metrics for hypothesis generation.

    Attributes:
        total_generated: Total number of hypotheses generated
        total_by_type: Count by hypothesis type
        average_generation_time_ms: Average time to generate
        average_confidence: Average confidence score
        generation_history: History of recent generations
    """

    total_generated: int = 0
    total_by_type: dict[str, int] = field(default_factory=dict)
    average_generation_time_ms: float = 0.0
    average_confidence: float = 0.0
    generation_history: list[GenerationResult] = field(default_factory=list)

    def update(self, result: GenerationResult) -> None:
        """Update metrics with a new generation result."""
        self.total_generated += len(result)

        # Update by type
        for hypothesis in result.hypotheses:
            type_name = hypothesis.hypothesis_type.name
            self.total_by_type[type_name] = self.total_by_type.get(type_name, 0) + 1

        # Update averages
        n = len(self.generation_history) + 1
        self.average_generation_time_ms = (
            self.average_generation_time_ms * (n - 1) + result.generation_time_ms
        ) / n

        avg_conf = (
            sum(h.confidence.score for h in result.hypotheses) / len(result.hypotheses)
            if result.hypotheses
            else 0.0
        )
        self.average_confidence = (self.average_confidence * (n - 1) + avg_conf) / n

        # Add to history (keep last 100)
        self.generation_history.append(result)
        if len(self.generation_history) > 100:
            self.generation_history = self.generation_history[-100:]

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            "total_generated": self.total_generated,
            "total_by_type": self.total_by_type,
            "average_generation_time_ms": self.average_generation_time_ms,
            "average_confidence": self.average_confidence,
            "generation_history": [g.to_dict() for g in self.generation_history],
        }


class HypothesisGenerator:
    """Generator for creating testable hypotheses from beliefs and market context.

    This class uses LLM capabilities to generate structured hypotheses that can
    be validated against market conditions. It integrates with the belief
    embedding pipeline to create hypotheses based on neural pattern recognition.

    Example:
        >>> from src.strong_system.hypothesis_generator import HypothesisGenerator
        >>> from src.strong_system.belief_embeddings import BeliefVector
        >>> import numpy as np
        >>>
        >>> # Create generator
        >>> config = GeneratorConfig(llm_provider="openai", max_hypotheses=5)
        >>> generator = HypothesisGenerator(config)
        >>>
        >>> # Generate hypotheses from beliefs
        >>> beliefs = [BeliefVector(vector=np.array([0.5, 0.3, 0.8]))]
        >>> context = MarketContext(symbol="BTC-USD", current_price=50000.0)
        >>> hypotheses = generator.generate_from_beliefs(beliefs, context)
    """

    def __init__(
        self,
        config: GeneratorConfig | None = None,
        llm_provider: LLMProvider | None = None,
    ) -> None:
        """Initialize the hypothesis generator.

        Args:
            config: Generator configuration
            llm_provider: LLM provider for generation (uses mock if None)
        """
        self.config = config or GeneratorConfig()
        self.llm_provider = llm_provider or MockLLMProvider()
        self.validator = HypothesisValidator(
            ValidationConfig(min_confidence_for_validation=self.config.min_confidence)
        )
        self.metrics = GeneratorMetrics()
        self._template_registry = get_template_registry()

    def generate_from_beliefs(
        self,
        beliefs: list[BeliefVector],
        context: MarketContext,
        hypothesis_types: list[HypothesisType] | None = None,
    ) -> GenerationResult:
        """Generate hypotheses from belief clusters.

        Args:
            beliefs: List of belief vectors to base hypotheses on
            context: Market context information
            hypothesis_types: Specific types to generate (uses config default if None)

        Returns:
            GenerationResult containing generated hypotheses
        """
        start_time = time.time()

        if not beliefs:
            return GenerationResult(
                hypotheses=[],
                generation_time_ms=0.0,
                beliefs_used=0,
                context=context,
                metadata={"error": "No beliefs provided"},
            )

        # Use specified types or default from config
        types_to_generate = hypothesis_types or self.config.hypothesis_types

        all_hypotheses: list[Hypothesis] = []

        # Generate hypotheses for each type
        for hypothesis_type in types_to_generate:
            if len(all_hypotheses) >= self.config.max_hypotheses:
                break

            hypotheses = self._generate_for_type(beliefs, context, hypothesis_type)
            all_hypotheses.extend(hypotheses)

        # Trim to max_hypotheses and sort by confidence
        all_hypotheses = all_hypotheses[: self.config.max_hypotheses]
        all_hypotheses = self.rank_hypotheses(all_hypotheses)

        generation_time_ms = (time.time() - start_time) * 1000

        result = GenerationResult(
            hypotheses=all_hypotheses,
            generation_time_ms=generation_time_ms,
            beliefs_used=len(beliefs),
            context=context,
            metadata={
                "types_requested": [t.name for t in types_to_generate],
                "types_generated": list(
                    set(h.hypothesis_type.name for h in all_hypotheses)
                ),
            },
        )

        self.metrics.update(result)
        return result

    def _generate_for_type(
        self,
        beliefs: list[BeliefVector],
        context: MarketContext,
        hypothesis_type: HypothesisType,
    ) -> list[Hypothesis]:
        """Generate hypotheses for a specific type.

        Args:
            beliefs: List of belief vectors
            context: Market context
            hypothesis_type: Type of hypothesis to generate

        Returns:
            List of generated hypotheses
        """
        # Render prompt for this type
        prompts = render_prompt(beliefs, context, hypothesis_type)

        # Call LLM
        try:
            response = self.llm_provider.generate(
                prompts["system"], prompts["user"], max_tokens=1000
            )
        except Exception as e:
            return []

        # Parse response into hypotheses
        hypotheses = self._parse_llm_response(
            response, hypothesis_type, context, beliefs
        )

        return hypotheses

    def _parse_llm_response(
        self,
        response: dict[str, Any],
        hypothesis_type: HypothesisType,
        context: MarketContext,
        beliefs: list[BeliefVector],
    ) -> list[Hypothesis]:
        """Parse LLM response into hypothesis objects.

        Args:
            response: LLM response dictionary
            hypothesis_type: Type of hypothesis
            context: Market context
            beliefs: Source beliefs

        Returns:
            List of parsed hypotheses
        """
        hypotheses = []

        raw_hypotheses = response.get("hypotheses", [])
        if not isinstance(raw_hypotheses, list):
            raw_hypotheses = [raw_hypotheses]

        for i, raw in enumerate(raw_hypotheses):
            if isinstance(raw, dict):
                # Extract confidence components
                confidence_score = float(raw.get("confidence", 0.5))
                confidence = ConfidenceScore(
                    score=confidence_score,
                    evidence_strength=confidence_score * 0.8,
                    consistency_score=confidence_score * 0.9,
                    historical_accuracy=0.5,
                    factors={
                        "llm_confidence": confidence_score,
                        "belief_count": len(beliefs),
                    },
                )

                # Get supporting belief IDs
                supporting_beliefs = [b.belief_id for b in beliefs[:5]]

                # Create expiration time
                expires_at = datetime.now(UTC) + timedelta(
                    hours=self.config.default_ttl_hours
                )

                hypothesis = Hypothesis(
                    hypothesis_id=f"hyp_{hypothesis_type.name.lower()}_{int(time.time())}_{i}",
                    hypothesis_type=hypothesis_type,
                    description=raw.get("description", "No description provided"),
                    prediction=raw.get("prediction", "No prediction provided"),
                    confidence=confidence,
                    supporting_beliefs=supporting_beliefs,
                    context=context,
                    created_at=datetime.now(UTC),
                    expires_at=expires_at,
                    metadata={
                        "reasoning": raw.get("reasoning", ""),
                        "raw_response": response.get("raw_response", ""),
                    },
                )

                # Filter by minimum confidence
                if confidence.score >= self.config.min_confidence:
                    hypotheses.append(hypothesis)

        return hypotheses

    def validate_hypothesis(
        self, hypothesis: Hypothesis, market_data: dict[str, Any]
    ) -> ValidationResult:
        """Validate a hypothesis against market data.

        Args:
            hypothesis: The hypothesis to validate
            market_data: Dictionary with actual market outcomes
                Expected keys: 'actual_price', 'high', 'low', 'timestamp'

        Returns:
            ValidationResult with validation status and metrics
        """
        return self.validator.validate(hypothesis, market_data)

    def score_confidence(
        self, hypothesis: Hypothesis, evidence: dict[str, Any]
    ) -> ConfidenceScore:
        """Score confidence for a hypothesis based on evidence.

        Args:
            hypothesis: The hypothesis to score
            evidence: Dictionary with evidence data
                May include: 'historical_accuracy', 'similar_outcomes',
                'market_alignment', 'belief_strength'

        Returns:
            Updated confidence score
        """
        base_confidence = hypothesis.confidence.score

        # Calculate evidence strength
        evidence_strength = evidence.get("belief_strength", base_confidence)

        # Calculate consistency with market
        market_alignment = evidence.get("market_alignment", 0.5)

        # Historical accuracy of similar hypotheses
        historical = evidence.get("historical_accuracy", 0.5)

        # Combine factors
        new_score = (
            base_confidence * 0.3
            + evidence_strength * 0.3
            + market_alignment * 0.2
            + historical * 0.2
        )

        # Clamp to [0, 1]
        new_score = max(0.0, min(1.0, new_score))

        return ConfidenceScore(
            score=new_score,
            evidence_strength=evidence_strength,
            consistency_score=market_alignment,
            historical_accuracy=historical,
            factors={
                "base_confidence": base_confidence,
                **evidence,
            },
        )

    def rank_hypotheses(self, hypotheses: list[Hypothesis]) -> list[Hypothesis]:
        """Rank hypotheses by confidence and quality.

        Args:
            hypotheses: List of hypotheses to rank

        Returns:
            List of hypotheses sorted by confidence (highest first)
        """

        def score_key(h: Hypothesis) -> float:
            # Composite score based on multiple factors
            confidence_weight = 0.5
            evidence_weight = 0.25
            consistency_weight = 0.25

            return (
                h.confidence.score * confidence_weight
                + h.confidence.evidence_strength * evidence_weight
                + h.confidence.consistency_score * consistency_weight
            )

        return sorted(hypotheses, key=score_key, reverse=True)

    def filter_hypotheses(
        self,
        hypotheses: list[Hypothesis],
        min_confidence: float | None = None,
        hypothesis_type: HypothesisType | None = None,
        exclude_expired: bool = True,
    ) -> list[Hypothesis]:
        """Filter hypotheses by criteria.

        Args:
            hypotheses: List of hypotheses to filter
            min_confidence: Minimum confidence threshold
            hypothesis_type: Filter by specific type
            exclude_expired: Whether to exclude expired hypotheses

        Returns:
            Filtered list of hypotheses
        """
        min_conf = (
            min_confidence if min_confidence is not None else self.config.min_confidence
        )

        filtered = hypotheses

        if exclude_expired:
            filtered = [h for h in filtered if not h.is_expired()]

        filtered = [h for h in filtered if h.confidence.score >= min_conf]

        if hypothesis_type:
            filtered = [h for h in filtered if h.hypothesis_type == hypothesis_type]

        return filtered

    def get_metrics(self) -> GeneratorMetrics:
        """Get current generation metrics.

        Returns:
            Current generator metrics
        """
        return self.metrics

    def get_validation_metrics(self) -> dict[str, Any]:
        """Get validation metrics.

        Returns:
            Validation metrics dictionary
        """
        return self.validator.get_metrics().to_dict()

    def reset_metrics(self) -> None:
        """Reset all metrics."""
        self.metrics = GeneratorMetrics()
        self.validator.reset_metrics()
