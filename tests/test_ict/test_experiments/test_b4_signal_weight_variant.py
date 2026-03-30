"""Tests for B4 Signal Weight Variant Experiment."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from src.ict.experiments.b4_signal_weight_variant import (
    B4SignalWeightExperiment,
    WeightingConfig,
)


class TestB4SignalWeightExperiment:
    """Tests for B4SignalWeightExperiment class."""

    @pytest.fixture
    def mock_collector(self):
        """Create a mock ICT data collector."""
        collector = MagicMock()
        collector.collect_signal = AsyncMock(return_value="sig-123")
        collector.stop_collection = AsyncMock()
        return collector

    @pytest.fixture
    def mock_registry(self):
        """Create a mock experiment registry."""
        registry = MagicMock()
        registry.register_experiment = MagicMock(return_value=True)
        registry.close_experiment = MagicMock(return_value=True)
        return registry

    def test_valid_variants(self):
        """Test all valid variant names."""
        for variant in B4SignalWeightExperiment.VARIANTS:
            exp = B4SignalWeightExperiment(
                collector=MagicMock(),
                variant=variant,
            )
            assert exp.experiment_key.variant == variant

    def test_invalid_variant_raises(self):
        """Test invalid variant raises ValueError."""
        with pytest.raises(ValueError):
            B4SignalWeightExperiment(
                collector=MagicMock(),
                variant="invalid_variant",
            )

    def test_calculate_signal_weight_equal(self):
        """Test equal weighting returns 1.0."""
        config = WeightingConfig(weighting_method="equal")
        exp = B4SignalWeightExperiment(
            collector=MagicMock(),
            weighting_config=config,
        )
        weight = exp.calculate_signal_weight(0.8, age_seconds=0)
        assert weight == 1.0

    def test_calculate_signal_weight_confidence(self):
        """Test confidence weighting returns confidence value."""
        config = WeightingConfig(weighting_method="confidence")
        exp = B4SignalWeightExperiment(
            collector=MagicMock(),
            weighting_config=config,
        )
        weight = exp.calculate_signal_weight(0.75, age_seconds=0)
        assert weight == 0.75

    def test_calculate_signal_weight_recency(self):
        """Test recency weighting applies decay."""
        config = WeightingConfig(weighting_method="recency", decay_factor=0.9)
        exp = B4SignalWeightExperiment(
            collector=MagicMock(),
            weighting_config=config,
        )
        # Fresh signal should have weight close to confidence
        weight_fresh = exp.calculate_signal_weight(1.0, age_seconds=0)
        # Older signal should have lower weight
        weight_old = exp.calculate_signal_weight(1.0, age_seconds=3600)  # 1 hour
        assert weight_fresh > weight_old

    @pytest.mark.asyncio
    async def test_record_signal_includes_weight(self, mock_collector):
        """Test recorded signals include weight context."""
        exp = B4SignalWeightExperiment(
            collector=mock_collector,
            variant="confidence_weighted",
        )
        exp.start()

        await exp.record_signal(
            symbol="BTC/USDT",
            signal_type="entry",
            confidence=0.85,
        )

        call_kwargs = mock_collector.collect_signal.call_args
        assert "weight" in call_kwargs.kwargs.get("context", {})
        assert "weighting_method" in call_kwargs.kwargs.get("context", {})


class TestWeightingConfig:
    """Tests for WeightingConfig dataclass."""

    def test_default_values(self):
        """Test default weighting config."""
        config = WeightingConfig()
        assert config.weighting_method == "equal"
        assert config.decay_factor == 0.9

    def test_custom_values(self):
        """Test custom weighting config."""
        config = WeightingConfig(
            weighting_method="recency",
            decay_factor=0.8,
        )
        assert config.weighting_method == "recency"
        assert config.decay_factor == 0.8
