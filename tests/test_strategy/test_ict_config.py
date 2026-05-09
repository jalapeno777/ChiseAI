"""Tests for ICT Confluence Strategy configuration.

ST-MVP-010: Config validation, default values, immutability.
"""

from __future__ import annotations

import pytest

from strategy.executors.ict_executor import ICTConfluenceExecutor
from strategy.strategies.ict_confluence_config import (
    DEFAULT_CONFIG,
    ICTConfluenceConfig,
)


class TestICTConfluenceConfig:
    """Tests for ICTConfluenceConfig dataclass."""

    def test_default_values(self) -> None:
        config = ICTConfluenceConfig()
        assert config.min_confluence == 60.0
        assert config.min_signals == 2
        assert config.require_bos_choch is True
        assert config.stop_loss_type == "atr"
        assert config.stop_loss_atr_multiplier == 1.5
        assert config.stop_loss_fixed_pct == 0.01
        assert config.risk_per_trade == 0.02
        assert config.take_profit_rr_ratio == 2.0
        assert config.preferred_sessions == ("london", "new_york")
        assert config.timeframe == "15m"

    def test_frozen_immutability(self) -> None:
        config = ICTConfluenceConfig()
        with pytest.raises(AttributeError):
            config.min_confluence = 80.0  # type: ignore[misc]

    def test_custom_values(self) -> None:
        config = ICTConfluenceConfig(
            min_confluence=80.0,
            min_signals=3,
            require_bos_choch=False,
            stop_loss_type="fixed",
            risk_per_trade=0.05,
        )
        assert config.min_confluence == 80.0
        assert config.min_signals == 3
        assert config.require_bos_choch is False
        assert config.stop_loss_type == "fixed"
        assert config.risk_per_trade == 0.05

    def test_to_dict(self) -> None:
        config = ICTConfluenceConfig()
        d = config.to_dict()
        assert isinstance(d, dict)
        assert d["min_confluence"] == 60.0
        assert d["min_signals"] == 2
        assert d["require_bos_choch"] is True
        assert "exit_threshold" in d
        assert d["exit_threshold"] == 30.0  # 60 * 0.5

    def test_to_dict_custom_config(self) -> None:
        config = ICTConfluenceConfig(min_confluence=80.0)
        d = config.to_dict()
        assert d["exit_threshold"] == 40.0  # 80 * 0.5

    def test_default_config_singleton(self) -> None:
        """DEFAULT_CONFIG is a pre-built instance."""
        assert isinstance(DEFAULT_CONFIG, ICTConfluenceConfig)
        assert DEFAULT_CONFIG.min_confluence == 60.0


class TestConfigWithExecutor:
    """Verify config dict works with ICTConfluenceExecutor."""

    def test_default_config_validates(self) -> None:
        executor = ICTConfluenceExecutor()
        config = ICTConfluenceConfig()
        assert executor.validate_config(config.to_dict()) is True

    def test_custom_config_validates(self) -> None:
        executor = ICTConfluenceExecutor()
        config = ICTConfluenceConfig(
            min_confluence=70.0,
            min_signals=3,
            risk_per_trade=0.03,
        )
        assert executor.validate_config(config.to_dict()) is True

    def test_generate_signals_with_config_dict(self) -> None:
        executor = ICTConfluenceExecutor()
        config = ICTConfluenceConfig()
        # No signals expected from empty data
        signals = executor.generate_signals([], config.to_dict())
        assert signals == []
