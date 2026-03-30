"""Tests for B5 Threshold Variant Experiment."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from src.ict.experiments.b5_threshold_variant import (
    B5ThresholdExperiment,
    ThresholdConfig,
)


class TestB5ThresholdExperiment:
    """Tests for B5ThresholdExperiment class."""

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
        for variant in B5ThresholdExperiment.VARIANTS:
            exp = B5ThresholdExperiment(
                collector=MagicMock(),
                variant=variant,
            )
            assert exp.experiment_key.variant == variant

    def test_invalid_variant_raises(self):
        """Test invalid variant raises ValueError."""
        with pytest.raises(ValueError):
            B5ThresholdExperiment(
                collector=MagicMock(),
                variant="invalid_variant",
            )

    def test_should_enter_high_threshold(self):
        """Test high threshold only enters high confidence."""
        exp = B5ThresholdExperiment(
            collector=MagicMock(),
            variant="high_threshold",
        )
        # High threshold: entry=0.7
        assert exp.should_enter(0.8) is True
        assert exp.should_enter(0.5) is False
        assert exp.should_enter(0.7) is True

    def test_should_exit_high_threshold(self):
        """Test high threshold exit logic."""
        exp = B5ThresholdExperiment(
            collector=MagicMock(),
            variant="high_threshold",
        )
        # High threshold: exit=0.5
        assert exp.should_exit(0.3) is True
        assert exp.should_exit(0.6) is False

    def test_should_enter_low_threshold(self):
        """Test low threshold enters lower confidence."""
        exp = B5ThresholdExperiment(
            collector=MagicMock(),
            variant="low_threshold",
        )
        # Low threshold: entry=0.3
        assert exp.should_enter(0.2) is False
        assert exp.should_enter(0.4) is True

    @pytest.mark.asyncio
    async def test_record_signal_below_threshold_blocked(self, mock_collector):
        """Test signals below entry threshold are blocked."""
        exp = B5ThresholdExperiment(
            collector=mock_collector,
            variant="high_threshold",  # entry=0.7
        )
        exp.start()

        result = await exp.record_signal(
            symbol="BTC/USDT",
            signal_type="entry",
            confidence=0.5,  # Below high threshold
        )

        assert result is None
        mock_collector.collect_signal.assert_not_called()

    @pytest.mark.asyncio
    async def test_record_signal_above_threshold_passes(self, mock_collector):
        """Test signals above entry threshold are recorded."""
        exp = B5ThresholdExperiment(
            collector=mock_collector,
            variant="high_threshold",  # entry=0.7
        )
        exp.start()

        result = await exp.record_signal(
            symbol="BTC/USDT",
            signal_type="entry",
            confidence=0.85,  # Above high threshold
        )

        assert result == "sig-123"


class TestThresholdConfig:
    """Tests for ThresholdConfig dataclass."""

    def test_variant_configs(self):
        """Test predefined variant configurations."""
        configs = B5ThresholdExperiment._VARIANT_CONFIGS

        assert configs["low_threshold"].entry_threshold == 0.3
        assert configs["medium_threshold"].entry_threshold == 0.5
        assert configs["high_threshold"].entry_threshold == 0.7

    def test_custom_config(self):
        """Test custom threshold config."""
        config = ThresholdConfig(
            entry_threshold=0.6,
            exit_threshold=0.4,
            stop_threshold=0.3,
        )
        assert config.entry_threshold == 0.6
        assert config.exit_threshold == 0.4
        assert config.stop_threshold == 0.3
