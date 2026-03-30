"""Tests for B3 Timeframe Variant Experiment."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from src.ict.experiments.b3_timeframe_variant import (
    B3TimeframeExperiment,
    TimeframeConfig,
)


class TestB3TimeframeExperiment:
    """Tests for B3TimeframeExperiment class."""

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
        for variant in B3TimeframeExperiment.VARIANTS:
            exp = B3TimeframeExperiment(
                collector=MagicMock(),
                variant=variant,
            )
            assert exp.experiment_key.variant == variant

    def test_invalid_variant_raises(self):
        """Test invalid variant raises ValueError."""
        with pytest.raises(ValueError):
            B3TimeframeExperiment(
                collector=MagicMock(),
                variant="invalid_variant",
            )

    def test_experiment_key_contains_variant(self, mock_collector):
        """Test experiment key contains timeframe variant."""
        exp = B3TimeframeExperiment(
            collector=mock_collector,
            variant="timeframe_15m",
        )
        assert "timeframe_15m" in exp.experiment_key.variant

    @pytest.mark.asyncio
    async def test_record_signal_includes_timeframe(self, mock_collector):
        """Test recorded signals include timeframe context."""
        exp = B3TimeframeExperiment(
            collector=mock_collector,
            variant="timeframe_1h",
        )
        exp.start()

        await exp.record_signal(
            symbol="BTC/USDT",
            signal_type="entry",
            confidence=0.85,
        )

        call_kwargs = mock_collector.collect_signal.call_args
        assert "timeframe" in call_kwargs.kwargs.get("context", {})

    def test_start_experiment(self, mock_collector, mock_registry):
        """Test starting the experiment."""
        exp = B3TimeframeExperiment(
            collector=mock_collector,
            registry=mock_registry,
        )
        result = exp.start()
        assert result is True
        assert exp.is_running() is True


class TestTimeframeConfig:
    """Tests for TimeframeConfig dataclass."""

    def test_default_values(self):
        """Test default timeframe config."""
        config = TimeframeConfig()
        assert config.timeframe == "1h"
        assert config.aggregation_method == "last"

    def test_custom_values(self):
        """Test custom timeframe config."""
        config = TimeframeConfig(
            timeframe="4h",
            aggregation_method="mean",
        )
        assert config.timeframe == "4h"
        assert config.aggregation_method == "mean"
