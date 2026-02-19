"""Pytest configuration for test_trading_mode module.

Fixtures for testing the TradingModeLoader and TradingModeConfig.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from src.trading_mode_loader import (
    ModuleType,
    TradingModeConfig,
)


@pytest.fixture
def paper_config():
    """Create a TradingModeConfig for paper mode testing.

    Returns:
        TradingModeConfig configured for paper mode with all modules enabled.
    """
    return TradingModeConfig(
        mode="paper",
        enabled_modules={
            ModuleType.SIGNAL_GENERATOR: True,
            ModuleType.RISK_ENFORCER: True,
            ModuleType.PAPER_ORCHESTRATOR: True,
            ModuleType.LLM_PROVIDER_CHAIN: True,
        },
        llm_provider_priority=["kimi", "zai", "zhipu", "minimax"],
        health_check_interval=30,
    )


@pytest.fixture
def live_config():
    """Create a TradingModeConfig for live mode testing.

    Returns:
        TradingModeConfig configured for live mode with all modules enabled.
    """
    return TradingModeConfig(
        mode="live",
        enabled_modules={
            ModuleType.SIGNAL_GENERATOR: True,
            ModuleType.RISK_ENFORCER: True,
            ModuleType.PAPER_ORCHESTRATOR: True,
            ModuleType.LLM_PROVIDER_CHAIN: True,
        },
        llm_provider_priority=["kimi", "zai", "zhipu", "minimax"],
        health_check_interval=30,
    )


@pytest.fixture
def mock_signal_generator():
    """Create a mock SignalGenerator for testing.

    Returns:
        MagicMock configured as a SignalGenerator with async initialize method.
    """
    mock = MagicMock()
    mock.initialize = AsyncMock()
    mock.health_check = AsyncMock(return_value={"healthy": True, "status": "ok"})
    mock.shutdown = AsyncMock()
    return mock


@pytest.fixture
def mock_risk_enforcer():
    """Create a mock RiskEnforcer for testing.

    Returns:
        MagicMock configured as a RiskEnforcer with async initialize method.
    """
    mock = MagicMock()
    mock.initialize = AsyncMock()
    mock.health_check = AsyncMock(return_value={"healthy": True, "status": "ok"})
    mock.shutdown = AsyncMock()
    return mock


@pytest.fixture
def mock_paper_orchestrator():
    """Create a mock PaperOrchestrator for testing.

    Returns:
        MagicMock configured as a PaperOrchestrator with async initialize method.
    """
    mock = MagicMock()
    mock.initialize = AsyncMock()
    mock.health_check = AsyncMock(return_value={"healthy": True, "status": "ok"})
    mock.shutdown = AsyncMock()
    return mock


@pytest.fixture
def mock_llm_provider_chain():
    """Create a mock ProviderChain for testing.

    Returns:
        MagicMock configured as a ProviderChain with async initialize method.
    """
    mock = MagicMock()
    mock.initialize = AsyncMock()
    mock.health_check = AsyncMock(return_value={"healthy": True, "status": "ok"})
    mock.shutdown = AsyncMock()
    return mock


@pytest.fixture
def mock_all_modules(
    mock_signal_generator,
    mock_risk_enforcer,
    mock_paper_orchestrator,
    mock_llm_provider_chain,
):
    """Create a dict of all mock modules for easy access.

    Returns:
        Dict mapping ModuleType to mock instances.
    """
    return {
        ModuleType.SIGNAL_GENERATOR: mock_signal_generator,
        ModuleType.RISK_ENFORCER: mock_risk_enforcer,
        ModuleType.PAPER_ORCHESTRATOR: mock_paper_orchestrator,
        ModuleType.LLM_PROVIDER_CHAIN: mock_llm_provider_chain,
    }


@pytest.fixture
def mock_imports(
    mock_signal_generator,
    mock_risk_enforcer,
    mock_paper_orchestrator,
    mock_llm_provider_chain,
):
    """Create mock modules for patching imports in trading_mode_loader.

    Returns:
        Dict suitable for use with patch.dict("sys.modules", ...).
    """

    # Create mock modules with the required classes
    mock_signal_module = MagicMock()
    mock_signal_module.SignalGenerator = MagicMock(return_value=mock_signal_generator)

    mock_risk_module = MagicMock()
    mock_risk_module.RiskEnforcer = MagicMock(return_value=mock_risk_enforcer)

    mock_orchestrator_module = MagicMock()
    mock_orchestrator_module.PaperOrchestrator = MagicMock(
        return_value=mock_paper_orchestrator
    )

    mock_llm_module = MagicMock()
    mock_llm_module.ProviderChain = MagicMock(return_value=mock_llm_provider_chain)

    return {
        "src.signal_generation.signal_generator": mock_signal_module,
        "src.execution.paper.risk_enforcer": mock_risk_module,
        "src.execution.paper.orchestrator": mock_orchestrator_module,
        "src.llm.provider_chain": mock_llm_module,
    }
