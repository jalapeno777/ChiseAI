"""Core types for multi-modal signal handling."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class ModalityType(Enum):
    """Types of data modalities for signal fusion."""

    TECHNICAL = "technical"
    SENTIMENT = "sentiment"
    ONCHAIN = "onchain"
    FUNDAMENTAL = "fundamental"
    NEWS = "news"
    SOCIAL = "social"


@dataclass
class TemporalContext:
    """Temporal context for signal alignment."""

    timestamp: datetime
    period_ms: int = 60000  # 1 minute default
    lag_ms: int = 0
    timezone: str = "UTC"

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "period_ms": self.period_ms,
            "lag_ms": self.lag_ms,
            "timezone": self.timezone,
        }

    @classmethod
    def now(cls, period_ms: int = 60000) -> "TemporalContext":
        return cls(timestamp=datetime.now(UTC), period_ms=period_ms)


@dataclass
class SignalMetadata:
    """Metadata for a signal."""

    source: str
    modality: ModalityType
    confidence: float
    reliability: float = 1.0
    staleness_ms: int = 0
    version: str = "1.0.0"
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "modality": self.modality.value,
            "confidence": self.confidence,
            "reliability": self.reliability,
            "staleness_ms": self.staleness_ms,
            "version": self.version,
            "tags": self.tags,
        }


@dataclass
class MultiModalSignal:
    """A signal from a single modality."""

    value: float
    modality: ModalityType
    metadata: SignalMetadata
    temporal_context: TemporalContext
    features: dict[str, float] = field(default_factory=dict)
    raw_data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "modality": self.modality.value,
            "metadata": self.metadata.to_dict(),
            "temporal_context": self.temporal_context.to_dict(),
            "features": self.features,
            "raw_data": self.raw_data,
        }

    @property
    def effective_confidence(self) -> float:
        """Calculate effective confidence considering staleness."""
        staleness_penalty = min(
            self.metadata.staleness_ms / 300000, 0.5
        )  # Max 50% penalty
        return (
            self.metadata.confidence
            * self.metadata.reliability
            * (1 - staleness_penalty)
        )


@dataclass
class EncodedSignal:
    """Encoded representation of a multi-modal signal."""

    modality: ModalityType
    encoded_vector: list[float]
    attention_weights: list[float]
    feature_importance: dict[str, float]
    original_signal: MultiModalSignal

    def to_dict(self) -> dict[str, Any]:
        return {
            "modality": self.modality.value,
            "encoded_vector": self.encoded_vector[:8],  # Truncate for display
            "attention_weights": self.attention_weights[:8],
            "feature_importance": self.feature_importance,
        }

    @property
    def dimension(self) -> int:
        return len(self.encoded_vector)


@dataclass
class SignalBatch:
    """A batch of signals ready for fusion."""

    signals: list[MultiModalSignal]
    aligned_timestamp: datetime
    alignment_quality: float
    modality_coverage: dict[ModalityType, bool]

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_count": len(self.signals),
            "aligned_timestamp": self.aligned_timestamp.isoformat(),
            "alignment_quality": self.alignment_quality,
            "modality_coverage": {
                m.value: v for m, v in self.modality_coverage.items()
            },
        }

    def get_signals_by_modality(self, modality: ModalityType) -> list[MultiModalSignal]:
        return [s for s in self.signals if s.modality == modality]


@dataclass
class FusionWeights:
    """Weights for fusing signals from different modalities."""

    technical: float = 0.4
    sentiment: float = 0.3
    onchain: float = 0.2
    fundamental: float = 0.05
    news: float = 0.03
    social: float = 0.02

    def normalize(self) -> "FusionWeights":
        """Return normalized weights that sum to 1."""
        total = (
            self.technical
            + self.sentiment
            + self.onchain
            + self.fundamental
            + self.news
            + self.social
        )
        if total == 0:
            return FusionWeights()
        return FusionWeights(
            technical=self.technical / total,
            sentiment=self.sentiment / total,
            onchain=self.onchain / total,
            fundamental=self.fundamental / total,
            news=self.news / total,
            social=self.social / total,
        )

    def to_dict(self) -> dict[str, float]:
        return {
            "technical": self.technical,
            "sentiment": self.sentiment,
            "onchain": self.onchain,
            "fundamental": self.fundamental,
            "news": self.news,
            "social": self.social,
        }

    def get_weight(self, modality: ModalityType) -> float:
        """Get weight for a specific modality."""
        mapping = {
            ModalityType.TECHNICAL: self.technical,
            ModalityType.SENTIMENT: self.sentiment,
            ModalityType.ONCHAIN: self.onchain,
            ModalityType.FUNDAMENTAL: self.fundamental,
            ModalityType.NEWS: self.news,
            ModalityType.SOCIAL: self.social,
        }
        return mapping.get(modality, 0.0)
