"""Modality encoder for encoding different data types into unified representations."""

from dataclasses import dataclass
from typing import Any

from src.neuro_symbolic.multimodal.types import (
    EncodedSignal,
    ModalityType,
    MultiModalSignal,
)


@dataclass
class EncoderConfig:
    """Configuration for the modality encoder."""

    technical_dim: int = 64
    sentiment_dim: int = 32
    onchain_dim: int = 48
    fundamental_dim: int = 32
    news_dim: int = 24
    social_dim: int = 24
    use_attention: bool = True
    normalize_output: bool = True


class ModalityEncoder:
    """Encodes different data types into unified vector representations.

    This encoder transforms signals from various modalities (technical, sentiment,
    on-chain, etc.) into a unified embedding space for fusion.

    Example:
        >>> encoder = ModalityEncoder()
        >>> signal = MultiModalSignal(...)
        >>> encoded = encoder.encode(signal)
        >>> print(encoded.encoded_vector)
    """

    def __init__(self, config: EncoderConfig | None = None):
        """Initialize the modality encoder.

        Args:
            config: Encoder configuration. Uses defaults if not provided.
        """
        self.config = config or EncoderConfig()
        self._encoding_stats: dict[ModalityType, int] = {}
        self._feature_extractors = {
            ModalityType.TECHNICAL: self._extract_technical_features,
            ModalityType.SENTIMENT: self._extract_sentiment_features,
            ModalityType.ONCHAIN: self._extract_onchain_features,
            ModalityType.FUNDAMENTAL: self._extract_fundamental_features,
            ModalityType.NEWS: self._extract_news_features,
            ModalityType.SOCIAL: self._extract_social_features,
        }

    def encode(self, signal: MultiModalSignal) -> EncodedSignal:
        """Encode a multi-modal signal into a unified representation.

        Args:
            signal: The signal to encode.

        Returns:
            EncodedSignal with encoded vector and metadata.
        """
        # Get dimension for this modality
        dim = self._get_dimension(signal.modality)

        # Extract features based on modality
        features = self._feature_extractors[signal.modality](signal)

        # Create encoded vector
        encoded_vector = self._create_encoded_vector(signal, features, dim)

        # Calculate attention weights
        attention_weights = self._calculate_attention(signal, dim)

        # Calculate feature importance
        feature_importance = self._calculate_feature_importance(features)

        # Track stats
        self._encoding_stats[signal.modality] = (
            self._encoding_stats.get(signal.modality, 0) + 1
        )

        return EncodedSignal(
            modality=signal.modality,
            encoded_vector=encoded_vector,
            attention_weights=attention_weights,
            feature_importance=feature_importance,
            original_signal=signal,
        )

    def encode_batch(self, signals: list[MultiModalSignal]) -> list[EncodedSignal]:
        """Encode a batch of signals.

        Args:
            signals: List of signals to encode.

        Returns:
            List of encoded signals.
        """
        return [self.encode(s) for s in signals]

    def get_encoding_dim(self, modality: ModalityType) -> int:
        """Get the encoding dimension for a modality.

        Args:
            modality: The modality type.

        Returns:
            Dimension of encoded vectors for this modality.
        """
        return self._get_dimension(modality)

    def get_statistics(self) -> dict[str, Any]:
        """Get encoder statistics.

        Returns:
            Dictionary with encoding statistics.
        """
        return {
            "total_encoded": sum(self._encoding_stats.values()),
            "by_modality": {m.value: c for m, c in self._encoding_stats.items()},
            "config": {
                "technical_dim": self.config.technical_dim,
                "sentiment_dim": self.config.sentiment_dim,
                "onchain_dim": self.config.onchain_dim,
            },
        }

    def reset_statistics(self) -> None:
        """Reset encoding statistics."""
        self._encoding_stats = {}

    def _get_dimension(self, modality: ModalityType) -> int:
        """Get dimension for a modality type."""
        dims = {
            ModalityType.TECHNICAL: self.config.technical_dim,
            ModalityType.SENTIMENT: self.config.sentiment_dim,
            ModalityType.ONCHAIN: self.config.onchain_dim,
            ModalityType.FUNDAMENTAL: self.config.fundamental_dim,
            ModalityType.NEWS: self.config.news_dim,
            ModalityType.SOCIAL: self.config.social_dim,
        }
        return dims.get(modality, 32)

    def _extract_technical_features(self, signal: MultiModalSignal) -> dict[str, float]:
        """Extract features from technical signal."""
        base_features = {
            "signal_value": signal.value,
            "confidence": signal.metadata.confidence,
            "reliability": signal.metadata.reliability,
        }

        # Add technical-specific features
        technical_features = {
            "rsi": signal.features.get("rsi", 50.0),
            "macd": signal.features.get("macd", 0.0),
            "macd_signal": signal.features.get("macd_signal", 0.0),
            "bb_upper": signal.features.get("bb_upper", 0.0),
            "bb_lower": signal.features.get("bb_lower", 0.0),
            "volume_ratio": signal.features.get("volume_ratio", 1.0),
            "trend_strength": signal.features.get("trend_strength", 0.0),
            "volatility": signal.features.get("volatility", 0.0),
            "momentum": signal.features.get("momentum", 0.0),
        }

        return {**base_features, **technical_features}

    def _extract_sentiment_features(self, signal: MultiModalSignal) -> dict[str, float]:
        """Extract features from sentiment signal."""
        base_features = {
            "signal_value": signal.value,
            "confidence": signal.metadata.confidence,
            "reliability": signal.metadata.reliability,
        }

        sentiment_features = {
            "polarity": signal.features.get("polarity", 0.0),
            "subjectivity": signal.features.get("subjectivity", 0.5),
            "source_count": signal.features.get("source_count", 1.0),
            "agreement": signal.features.get("agreement", 0.5),
            "volume_spike": signal.features.get("volume_spike", 0.0),
            "trend": signal.features.get("trend", 0.0),
        }

        return {**base_features, **sentiment_features}

    def _extract_onchain_features(self, signal: MultiModalSignal) -> dict[str, float]:
        """Extract features from on-chain signal."""
        base_features = {
            "signal_value": signal.value,
            "confidence": signal.metadata.confidence,
            "reliability": signal.metadata.reliability,
        }

        onchain_features = {
            "active_addresses": signal.features.get("active_addresses", 0.0),
            "transaction_volume": signal.features.get("transaction_volume", 0.0),
            "whale_activity": signal.features.get("whale_activity", 0.0),
            "exchange_flow": signal.features.get("exchange_flow", 0.0),
            "holder_distribution": signal.features.get("holder_distribution", 0.0),
            "smart_contract_activity": signal.features.get(
                "smart_contract_activity", 0.0
            ),
            "network_growth": signal.features.get("network_growth", 0.0),
        }

        return {**base_features, **onchain_features}

    def _extract_fundamental_features(
        self, signal: MultiModalSignal
    ) -> dict[str, float]:
        """Extract features from fundamental signal."""
        base_features = {
            "signal_value": signal.value,
            "confidence": signal.metadata.confidence,
            "reliability": signal.metadata.reliability,
        }

        fundamental_features = {
            "pe_ratio": signal.features.get("pe_ratio", 0.0),
            "market_cap": signal.features.get("market_cap", 0.0),
            "volume_24h": signal.features.get("volume_24h", 0.0),
            "circulating_supply": signal.features.get("circulating_supply", 0.0),
        }

        return {**base_features, **fundamental_features}

    def _extract_news_features(self, signal: MultiModalSignal) -> dict[str, float]:
        """Extract features from news signal."""
        base_features = {
            "signal_value": signal.value,
            "confidence": signal.metadata.confidence,
            "reliability": signal.metadata.reliability,
        }

        news_features = {
            "relevance": signal.features.get("relevance", 0.5),
            "source_credibility": signal.features.get("source_credibility", 0.5),
            "impact_score": signal.features.get("impact_score", 0.0),
        }

        return {**base_features, **news_features}

    def _extract_social_features(self, signal: MultiModalSignal) -> dict[str, float]:
        """Extract features from social signal."""
        base_features = {
            "signal_value": signal.value,
            "confidence": signal.metadata.confidence,
            "reliability": signal.metadata.reliability,
        }

        social_features = {
            "engagement_rate": signal.features.get("engagement_rate", 0.0),
            "reach": signal.features.get("reach", 0.0),
            "influencer_score": signal.features.get("influencer_score", 0.0),
        }

        return {**base_features, **social_features}

    def _create_encoded_vector(
        self,
        signal: MultiModalSignal,
        features: dict[str, float],
        dim: int,
    ) -> list[float]:
        """Create encoded vector from features."""
        feature_values = list(features.values())
        encoded = []

        # Normalize and pad/truncate to dimension
        for i in range(dim):
            if i < len(feature_values):
                val = feature_values[i]
                # Normalize to [-1, 1] range
                normalized = max(-1.0, min(1.0, val / (abs(val) + 1e-8)))
                encoded.append(normalized)
            else:
                # Pad with attention-weighted noise based on signal confidence
                if self.config.normalize_output:
                    encoded.append(0.0)
                else:
                    import random

                    random.seed(hash(f"{signal.modality.value}_{i}"))
                    encoded.append(random.gauss(0, 0.1) * signal.metadata.confidence)

        # Scale by signal value and confidence
        scale_factor = signal.value * signal.effective_confidence
        encoded = [v * scale_factor for v in encoded]

        return encoded

    def _calculate_attention(self, signal: MultiModalSignal, dim: int) -> list[float]:
        """Calculate attention weights for encoded dimensions."""
        if not self.config.use_attention:
            return [1.0] * dim

        # Base attention from confidence
        base_attention = signal.effective_confidence

        # Modality-specific attention patterns
        attention = []
        for i in range(dim):
            # Create attention pattern based on position and modality
            position_weight = (
                1.0 - (i / dim) * 0.3
            )  # Earlier dimensions get more attention
            attention.append(base_attention * position_weight)

        # Normalize
        total = sum(attention)
        if total > 0:
            attention = [a / total for a in attention]

        return attention

    def _calculate_feature_importance(
        self, features: dict[str, float]
    ) -> dict[str, float]:
        """Calculate importance scores for features."""
        importance = {}

        # Calculate importance based on absolute value
        total = sum(abs(v) for v in features.values()) + 1e-8

        for name, value in features.items():
            importance[name] = abs(value) / total

        return importance


def encode_signal(
    signal: MultiModalSignal,
    config: EncoderConfig | None = None,
) -> EncodedSignal:
    """Convenience function to encode a single signal.

    Args:
        signal: Signal to encode.
        config: Optional encoder configuration.

    Returns:
        Encoded signal.
    """
    encoder = ModalityEncoder(config=config)
    return encoder.encode(signal)
