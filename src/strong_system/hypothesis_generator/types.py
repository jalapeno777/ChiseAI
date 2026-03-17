"""Type definitions for the Hypothesis Generator module.

Provides dataclasses and type aliases for hypotheses, confidence scores,
validation results, and related concepts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, auto
from typing import Any, Self

import numpy as np

from src.strong_system.belief_embeddings import BeliefVector


class HypothesisType(Enum):
    """Types of market hypotheses that can be generated."""

    TREND = auto()
    REVERSAL = auto()
    RANGE = auto()
    BREAKOUT = auto()
    VOLATILITY = auto()
    MOMENTUM = auto()


class ValidationStatus(Enum):
    """Status of hypothesis validation."""

    PENDING = auto()
    VALID = auto()
    INVALID = auto()
    INCONCLUSIVE = auto()


@dataclass
class MarketContext:
    """Context information for hypothesis generation.

    Attributes:
        symbol: Trading symbol (e.g., "BTC-USD")
        timeframe: Timeframe for analysis (e.g., "1h", "1d")
        current_price: Current market price
        timestamp: UTC timestamp of the context
        indicators: Technical indicators dictionary
        market_regime: Current market regime (e.g., "bullish", "bearish", "sideways")
        additional_data: Any additional context data
    """

    symbol: str = "UNKNOWN"
    timeframe: str = "1h"
    current_price: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    indicators: dict[str, float] = field(default_factory=dict)
    market_regime: str = "unknown"
    additional_data: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate market context fields."""
        if not self.symbol or not isinstance(self.symbol, str):
            raise ValueError("Symbol must be a non-empty string")
        if self.current_price < 0:
            raise ValueError("Current price cannot be negative")

    def to_dict(self) -> dict[str, Any]:
        """Convert context to dictionary."""
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "current_price": self.current_price,
            "timestamp": self.timestamp.isoformat(),
            "indicators": self.indicators,
            "market_regime": self.market_regime,
            "additional_data": self.additional_data,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Create context from dictionary."""
        timestamp = data.get("timestamp")
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)
        elif timestamp is None:
            timestamp = datetime.now(UTC)

        return cls(
            symbol=str(data.get("symbol", "UNKNOWN")),
            timeframe=str(data.get("timeframe", "1h")),
            current_price=float(data.get("current_price", 0.0)),
            timestamp=timestamp,
            indicators=dict(data.get("indicators", {})),
            market_regime=str(data.get("market_regime", "unknown")),
            additional_data=dict(data.get("additional_data", {})),
        )


@dataclass
class ConfidenceScore:
    """Confidence score for a hypothesis.

    Attributes:
        score: Confidence value between 0.0 and 1.0
        evidence_strength: Strength of supporting evidence (0.0-1.0)
        consistency_score: Consistency with existing beliefs (0.0-1.0)
        historical_accuracy: Historical accuracy of similar hypotheses (0.0-1.0)
        factors: Dictionary of individual confidence factors
    """

    score: float = 0.5
    evidence_strength: float = 0.5
    consistency_score: float = 0.5
    historical_accuracy: float = 0.5
    factors: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate confidence score fields."""
        for field_name, value in [
            ("score", self.score),
            ("evidence_strength", self.evidence_strength),
            ("consistency_score", self.consistency_score),
            ("historical_accuracy", self.historical_accuracy),
        ]:
            if not 0.0 <= value <= 1.0:
                raise ValueError(
                    f"{field_name} must be between 0.0 and 1.0, got {value}"
                )

    def to_dict(self) -> dict[str, Any]:
        """Convert confidence score to dictionary."""
        return {
            "score": self.score,
            "evidence_strength": self.evidence_strength,
            "consistency_score": self.consistency_score,
            "historical_accuracy": self.historical_accuracy,
            "factors": self.factors,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Create confidence score from dictionary."""
        return cls(
            score=float(data.get("score", 0.5)),
            evidence_strength=float(data.get("evidence_strength", 0.5)),
            consistency_score=float(data.get("consistency_score", 0.5)),
            historical_accuracy=float(data.get("historical_accuracy", 0.5)),
            factors=dict(data.get("factors", {})),
        )


@dataclass
class Hypothesis:
    """A testable hypothesis with confidence and metadata.

    Attributes:
        hypothesis_id: Unique identifier for this hypothesis
        hypothesis_type: Type of hypothesis (trend, reversal, etc.)
        description: Human-readable description of the hypothesis
        prediction: Specific prediction (e.g., "price will increase 5%")
        confidence: Confidence score for the hypothesis
        supporting_beliefs: List of belief IDs supporting this hypothesis
        context: Market context when hypothesis was generated
        created_at: UTC timestamp when hypothesis was created
        expires_at: UTC timestamp when hypothesis expires
        metadata: Additional metadata
    """

    hypothesis_id: str = field(
        default_factory=lambda: f"hypothesis_{datetime.now(UTC).timestamp()}"
    )
    hypothesis_type: HypothesisType = HypothesisType.TREND
    description: str = ""
    prediction: str = ""
    confidence: ConfidenceScore = field(default_factory=ConfidenceScore)
    supporting_beliefs: list[str] = field(default_factory=list)
    context: MarketContext = field(default_factory=MarketContext)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate hypothesis fields."""
        if not self.description:
            raise ValueError("Description cannot be empty")
        if not self.prediction:
            raise ValueError("Prediction cannot be empty")
        if self.expires_at <= self.created_at:
            # Default expiration is 24 hours if not specified
            self.expires_at = self.created_at.replace(
                hour=(self.created_at.hour + 24) % 24
            )

    def is_expired(self) -> bool:
        """Check if the hypothesis has expired."""
        return datetime.now(UTC) > self.expires_at

    def to_dict(self) -> dict[str, Any]:
        """Convert hypothesis to dictionary."""
        return {
            "hypothesis_id": self.hypothesis_id,
            "hypothesis_type": self.hypothesis_type.name,
            "description": self.description,
            "prediction": self.prediction,
            "confidence": self.confidence.to_dict(),
            "supporting_beliefs": self.supporting_beliefs,
            "context": self.context.to_dict(),
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Create hypothesis from dictionary."""
        hypothesis_type = HypothesisType[data.get("hypothesis_type", "TREND")]

        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        elif created_at is None:
            created_at = datetime.now(UTC)

        expires_at = data.get("expires_at")
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)
        elif expires_at is None:
            expires_at = datetime.now(UTC)

        return cls(
            hypothesis_id=str(data.get("hypothesis_id", "")),
            hypothesis_type=hypothesis_type,
            description=str(data.get("description", "")),
            prediction=str(data.get("prediction", "")),
            confidence=ConfidenceScore.from_dict(data.get("confidence", {})),
            supporting_beliefs=list(data.get("supporting_beliefs", [])),
            context=MarketContext.from_dict(data.get("context", {})),
            created_at=created_at,
            expires_at=expires_at,
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class ValidationResult:
    """Result of hypothesis validation against market data.

    Attributes:
        hypothesis_id: ID of the validated hypothesis
        status: Validation status
        actual_outcome: What actually happened in the market
        predicted_outcome: What was predicted
        accuracy: Accuracy score (0.0-1.0)
        error_margin: Error margin between prediction and actual
        validated_at: UTC timestamp of validation
        notes: Additional validation notes
    """

    hypothesis_id: str = ""
    status: ValidationStatus = ValidationStatus.PENDING
    actual_outcome: str = ""
    predicted_outcome: str = ""
    accuracy: float = 0.0
    error_margin: float = 0.0
    validated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    notes: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate validation result fields."""
        if not 0.0 <= self.accuracy <= 1.0:
            raise ValueError(
                f"Accuracy must be between 0.0 and 1.0, got {self.accuracy}"
            )
        if self.error_margin < 0:
            raise ValueError("Error margin cannot be negative")

    def to_dict(self) -> dict[str, Any]:
        """Convert validation result to dictionary."""
        return {
            "hypothesis_id": self.hypothesis_id,
            "status": self.status.name,
            "actual_outcome": self.actual_outcome,
            "predicted_outcome": self.predicted_outcome,
            "accuracy": self.accuracy,
            "error_margin": self.error_margin,
            "validated_at": self.validated_at.isoformat(),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Create validation result from dictionary."""
        status = ValidationStatus[data.get("status", "PENDING")]

        validated_at = data.get("validated_at")
        if isinstance(validated_at, str):
            validated_at = datetime.fromisoformat(validated_at)
        elif validated_at is None:
            validated_at = datetime.now(UTC)

        return cls(
            hypothesis_id=str(data.get("hypothesis_id", "")),
            status=status,
            actual_outcome=str(data.get("actual_outcome", "")),
            predicted_outcome=str(data.get("predicted_outcome", "")),
            accuracy=float(data.get("accuracy", 0.0)),
            error_margin=float(data.get("error_margin", 0.0)),
            validated_at=validated_at,
            notes=dict(data.get("notes", {})),
        )


@dataclass
class GeneratorConfig:
    """Configuration for the HypothesisGenerator.

    Attributes:
        llm_provider: Name of the LLM provider (e.g., "openai", "anthropic")
        model_name: Specific model to use
        max_hypotheses: Maximum number of hypotheses to generate
        min_confidence: Minimum confidence threshold for hypotheses
        default_ttl_hours: Default time-to-live for hypotheses in hours
        hypothesis_types: Types of hypotheses to generate
        enable_validation: Whether to enable automatic validation
        custom_params: Additional provider-specific parameters
    """

    llm_provider: str = "openai"
    model_name: str = "gpt-4"
    max_hypotheses: int = 10
    min_confidence: float = 0.3
    default_ttl_hours: int = 24
    hypothesis_types: list[HypothesisType] = field(default_factory=list)
    enable_validation: bool = True
    custom_params: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Set default hypothesis types if not provided."""
        if not self.hypothesis_types:
            self.hypothesis_types = [
                HypothesisType.TREND,
                HypothesisType.REVERSAL,
                HypothesisType.RANGE,
                HypothesisType.BREAKOUT,
            ]
        if not 0.0 <= self.min_confidence <= 1.0:
            raise ValueError(
                f"min_confidence must be between 0.0 and 1.0, got {self.min_confidence}"
            )
        if self.max_hypotheses < 1:
            raise ValueError("max_hypotheses must be at least 1")


@dataclass
class GenerationResult:
    """Result of hypothesis generation.

    Attributes:
        hypotheses: List of generated hypotheses
        generation_time_ms: Time taken to generate in milliseconds
        beliefs_used: Number of beliefs used for generation
        context: Market context used
        metadata: Additional generation metadata
    """

    hypotheses: list[Hypothesis] = field(default_factory=list)
    generation_time_ms: float = 0.0
    beliefs_used: int = 0
    context: MarketContext = field(default_factory=MarketContext)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __len__(self) -> int:
        """Return number of hypotheses."""
        return len(self.hypotheses)

    def __iter__(self):
        """Iterate over hypotheses."""
        return iter(self.hypotheses)

    def to_dict(self) -> dict[str, Any]:
        """Convert generation result to dictionary."""
        return {
            "hypotheses": [h.to_dict() for h in self.hypotheses],
            "generation_time_ms": self.generation_time_ms,
            "beliefs_used": self.beliefs_used,
            "context": self.context.to_dict(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Create generation result from dictionary."""
        hypotheses = [Hypothesis.from_dict(h) for h in data.get("hypotheses", [])]

        return cls(
            hypotheses=hypotheses,
            generation_time_ms=float(data.get("generation_time_ms", 0.0)),
            beliefs_used=int(data.get("beliefs_used", 0)),
            context=MarketContext.from_dict(data.get("context", {})),
            metadata=dict(data.get("metadata", {})),
        )
