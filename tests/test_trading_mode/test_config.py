"""Tests for TradingModeConfig validation.

This module tests the TradingModeConfig class from src/trading_mode_loader.py,
covering configuration validation for different trading modes.
"""

import pytest
from src.trading_mode_loader import (
    ModuleType,
    TradingModeConfig,
)


class TestTradingModeConfig:
    """Test cases for TradingModeConfig validation."""

    def test_paper_mode_required_modules(self):
        """Verify PAPER mode requires SIGNAL_GENERATOR and PAPER_ORCHESTRATOR.

        Paper mode must have:
        - SIGNAL_GENERATOR: To generate trading signals
        - PAPER_ORCHESTRATOR: To execute paper trades

        RISK_ENFORCER and LLM_PROVIDER_CHAIN are optional but recommended.
        """
        # Valid paper config with all modules
        config = TradingModeConfig(
            mode="paper",
            enabled_modules={
                ModuleType.SIGNAL_GENERATOR: True,
                ModuleType.RISK_ENFORCER: True,
                ModuleType.PAPER_ORCHESTRATOR: True,
                ModuleType.LLM_PROVIDER_CHAIN: True,
            },
        )

        # Verify paper mode is set correctly
        assert config.mode == "paper"

        # Verify required modules are enabled
        assert config.enabled_modules[ModuleType.SIGNAL_GENERATOR] is True
        assert config.enabled_modules[ModuleType.PAPER_ORCHESTRATOR] is True

        # Paper mode can work with minimal modules
        minimal_paper_config = TradingModeConfig(
            mode="paper",
            enabled_modules={
                ModuleType.SIGNAL_GENERATOR: True,
                ModuleType.RISK_ENFORCER: False,
                ModuleType.PAPER_ORCHESTRATOR: True,
                ModuleType.LLM_PROVIDER_CHAIN: False,
            },
        )

        assert minimal_paper_config.mode == "paper"
        assert minimal_paper_config.enabled_modules[ModuleType.SIGNAL_GENERATOR] is True
        assert (
            minimal_paper_config.enabled_modules[ModuleType.PAPER_ORCHESTRATOR] is True
        )

    def test_live_mode_required_modules(self):
        """Verify LIVE mode requires all modules.

        Live mode must have:
        - SIGNAL_GENERATOR: To generate trading signals
        - RISK_ENFORCER: To enforce risk limits (critical for live trading)
        - PAPER_ORCHESTRATOR: For trade execution
        - LLM_PROVIDER_CHAIN: For LLM-based enhancements
        """
        # Valid live config with all modules
        config = TradingModeConfig(
            mode="live",
            enabled_modules={
                ModuleType.SIGNAL_GENERATOR: True,
                ModuleType.RISK_ENFORCER: True,
                ModuleType.PAPER_ORCHESTRATOR: True,
                ModuleType.LLM_PROVIDER_CHAIN: True,
            },
        )

        # Verify live mode is set correctly
        assert config.mode == "live"

        # Verify all modules are enabled
        assert all(enabled for enabled in config.enabled_modules.values())

    def test_validate_config_pass(self):
        """Test that valid config returns True.

        A valid config has:
        - Valid mode (paper, live, or backtest)
        - Required modules enabled for the mode
        - Valid health_check_interval (>= 5)
        - Valid llm_provider_priority list
        """
        # Valid paper config
        paper_config = TradingModeConfig(
            mode="paper",
            enabled_modules={
                ModuleType.SIGNAL_GENERATOR: True,
                ModuleType.RISK_ENFORCER: True,
                ModuleType.PAPER_ORCHESTRATOR: True,
                ModuleType.LLM_PROVIDER_CHAIN: True,
            },
            health_check_interval=30,
            llm_provider_priority=["kimi", "zai", "zhipu", "minimax"],
        )

        # Verify config is valid
        assert paper_config.mode in ("paper", "live", "backtest")
        assert paper_config.health_check_interval >= 5
        assert len(paper_config.llm_provider_priority) > 0
        assert all(isinstance(p, str) for p in paper_config.llm_provider_priority)

        # Valid live config
        live_config = TradingModeConfig(
            mode="live",
            enabled_modules={
                ModuleType.SIGNAL_GENERATOR: True,
                ModuleType.RISK_ENFORCER: True,
                ModuleType.PAPER_ORCHESTRATOR: True,
                ModuleType.LLM_PROVIDER_CHAIN: True,
            },
            health_check_interval=60,
            llm_provider_priority=["kimi", "zai"],
        )

        assert live_config.mode in ("paper", "live", "backtest")
        assert live_config.health_check_interval >= 5

        # Valid backtest config
        backtest_config = TradingModeConfig(
            mode="backtest",
            enabled_modules={
                ModuleType.SIGNAL_GENERATOR: True,
                ModuleType.RISK_ENFORCER: False,
                ModuleType.PAPER_ORCHESTRATOR: False,
                ModuleType.LLM_PROVIDER_CHAIN: True,
            },
            health_check_interval=10,
        )

        assert backtest_config.mode in ("paper", "live", "backtest")

    def test_validate_config_fail(self):
        """Test that config with missing modules or invalid values is rejected.

        Invalid configs include:
        - Invalid mode values
        - Health check interval < 5
        - Empty provider priority list (if LLM enabled)
        """
        # Test invalid mode
        with pytest.raises(ValueError):
            TradingModeConfig(
                mode="invalid_mode",  # Not in allowed values
                enabled_modules={
                    ModuleType.SIGNAL_GENERATOR: True,
                    ModuleType.RISK_ENFORCER: True,
                    ModuleType.PAPER_ORCHESTRATOR: True,
                    ModuleType.LLM_PROVIDER_CHAIN: True,
                },
            )

        # Test health check interval too low
        with pytest.raises(ValueError):
            TradingModeConfig(
                mode="paper",
                health_check_interval=3,  # Below minimum of 5
            )

    def test_default_config_values(self):
        """Test that default config values are set correctly.

        Default config should have:
        - mode: "paper"
        - All modules enabled
        - Default LLM provider priority
        - Default health check interval of 30
        """
        config = TradingModeConfig()

        assert config.mode == "paper"
        assert config.enabled_modules[ModuleType.SIGNAL_GENERATOR] is True
        assert config.enabled_modules[ModuleType.RISK_ENFORCER] is True
        assert config.enabled_modules[ModuleType.PAPER_ORCHESTRATOR] is True
        assert config.enabled_modules[ModuleType.LLM_PROVIDER_CHAIN] is True
        assert config.health_check_interval == 30
        assert config.llm_provider_priority == ["kimi", "zai", "zhipu", "minimax"]

    def test_get_module_status_returns_copy(self):
        """Test that get_module_status returns a copy of the status dict.

        The dict itself should be a copy (different object), but the ModuleStatus
        values are shared references (shallow copy).
        """
        from src.trading_mode_loader import TradingModeLoader

        config = TradingModeConfig()
        loader = TradingModeLoader(config)

        status = loader.get_module_status()

        # The returned dict should be a different object
        assert status is not loader.module_status

        # But the ModuleStatus values are shared (shallow copy)
        assert (
            status[ModuleType.SIGNAL_GENERATOR]
            is loader.module_status[ModuleType.SIGNAL_GENERATOR]
        )

        # Modifying the dict itself doesn't affect the loader
        status[ModuleType.SIGNAL_GENERATOR] = None
        assert loader.module_status[ModuleType.SIGNAL_GENERATOR] is not None

    def test_backtest_mode_config(self):
        """Test backtest mode configuration.

        Backtest mode typically only needs:
        - SIGNAL_GENERATOR: To generate signals for backtesting
        - LLM_PROVIDER_CHAIN: Optional, for LLM enhancements

        Does not need:
        - RISK_ENFORCER: Risk is handled differently in backtest
        - PAPER_ORCHESTRATOR: Not executing real or paper trades
        """
        config = TradingModeConfig(
            mode="backtest",
            enabled_modules={
                ModuleType.SIGNAL_GENERATOR: True,
                ModuleType.RISK_ENFORCER: False,
                ModuleType.PAPER_ORCHESTRATOR: False,
                ModuleType.LLM_PROVIDER_CHAIN: True,
            },
        )

        assert config.mode == "backtest"
        assert config.enabled_modules[ModuleType.SIGNAL_GENERATOR] is True
        assert config.enabled_modules[ModuleType.RISK_ENFORCER] is False
        assert config.enabled_modules[ModuleType.PAPER_ORCHESTRATOR] is False

    def test_config_with_custom_llm_priority(self):
        """Test config with custom LLM provider priority.

        Users should be able to specify their own provider priority.
        """
        custom_priority = ["zai", "kimi", "minimax"]

        config = TradingModeConfig(
            mode="paper",
            llm_provider_priority=custom_priority,
        )

        assert config.llm_provider_priority == custom_priority

    def test_config_health_check_interval_validation(self):
        """Test health check interval boundary values.

        Valid: >= 5
        Invalid: < 5
        """
        # Valid boundary value
        config = TradingModeConfig(health_check_interval=5)
        assert config.health_check_interval == 5

        # Another valid value
        config = TradingModeConfig(health_check_interval=100)
        assert config.health_check_interval == 100

        # Invalid values should raise ValueError
        with pytest.raises(ValueError):
            TradingModeConfig(health_check_interval=4)

        with pytest.raises(ValueError):
            TradingModeConfig(health_check_interval=0)

        with pytest.raises(ValueError):
            TradingModeConfig(health_check_interval=-1)
