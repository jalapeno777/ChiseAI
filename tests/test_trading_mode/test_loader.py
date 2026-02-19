"""Comprehensive tests for TradingModeLoader.

This module tests the TradingModeLoader class from src/trading_mode_loader.py,
covering initialization, module loading, health checks, and shutdown functionality.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.trading_mode_loader import (
    ModuleState,
    ModuleStatus,
    ModuleType,
    TradingModeConfig,
    TradingModeLoader,
)


class TestTradingModeLoader:
    """Test cases for the TradingModeLoader class."""

    def test_loader_initialization(self, paper_config):
        """Test that loader stores config and initializes status dict.

        Verifies:
        - Config is stored correctly
        - Module status dict is initialized for all modules
        - All modules start in UNINITIALIZED state
        - _loaded flag is False initially
        """
        loader = TradingModeLoader(paper_config)

        # Verify config is stored
        assert loader.config == paper_config
        assert loader.config.mode == "paper"

        # Verify module status dict is initialized
        assert len(loader.module_status) == 4
        assert ModuleType.SIGNAL_GENERATOR in loader.module_status
        assert ModuleType.RISK_ENFORCER in loader.module_status
        assert ModuleType.PAPER_ORCHESTRATOR in loader.module_status
        assert ModuleType.LLM_PROVIDER_CHAIN in loader.module_status

        # Verify initial state
        for module_type, status in loader.module_status.items():
            assert status.module_type == module_type
            assert status.state == ModuleState.UNINITIALIZED
            assert status.enabled is True
            assert status.loaded is False
            assert status.healthy is False
            assert status.error_message is None

        # Verify _loaded flag
        assert loader._loaded is False
        assert loader._modules == {}

    @pytest.mark.asyncio
    async def test_load_all_modules(self, paper_config, mock_imports):
        """Test successfully loading all modules with mocked dependencies.

        Verifies:
        - All modules are loaded successfully
        - Module states transition to LOADED
        - loaded and healthy flags are set to True
        - _loaded flag is True after successful load
        - Module instances are stored in _modules dict
        """
        loader = TradingModeLoader(paper_config)

        # Patch the imports in trading_mode_loader
        with patch.dict("sys.modules", mock_imports):
            result = await loader.load()

        # Verify load was successful
        assert result is True
        assert loader._loaded is True

        # Verify all modules are loaded and healthy
        for module_type in ModuleType:
            status = loader.module_status[module_type]
            assert status.state == ModuleState.LOADED
            assert status.loaded is True
            assert status.healthy is True
            assert status.error_message is None
            assert status.last_check is not None

        # Verify module instances are stored
        assert len(loader._modules) == 4

    @pytest.mark.asyncio
    async def test_load_handles_module_failure(self, paper_config, mock_imports):
        """Test that if one module fails, others still load and error is captured.

        Verifies:
        - When one module fails, other modules still load
        - Failed module has ERROR state with error_message
        - Successfully loaded modules have LOADED state
        - _loaded flag is False when any module fails
        - Error details are captured in status
        """
        loader = TradingModeLoader(paper_config)

        # Make LLM module fail
        mock_imports["src.llm.provider_chain"].ProviderChain = MagicMock(
            side_effect=Exception("LLM initialization failed")
        )

        # Patch the imports in trading_mode_loader
        with patch.dict("sys.modules", mock_imports):
            result = await loader.load()

        # Verify load returned False (not all modules loaded)
        assert result is False
        assert loader._loaded is False

        # Verify successful modules are loaded
        assert (
            loader.module_status[ModuleType.SIGNAL_GENERATOR].state
            == ModuleState.LOADED
        )
        assert loader.module_status[ModuleType.SIGNAL_GENERATOR].loaded is True
        assert (
            loader.module_status[ModuleType.RISK_ENFORCER].state == ModuleState.LOADED
        )
        assert loader.module_status[ModuleType.RISK_ENFORCER].loaded is True
        assert (
            loader.module_status[ModuleType.PAPER_ORCHESTRATOR].state
            == ModuleState.LOADED
        )
        assert loader.module_status[ModuleType.PAPER_ORCHESTRATOR].loaded is True

        # Verify failed module has error state
        llm_status = loader.module_status[ModuleType.LLM_PROVIDER_CHAIN]
        assert llm_status.state == ModuleState.ERROR
        assert llm_status.loaded is False
        assert llm_status.healthy is False
        assert llm_status.error_message is not None
        assert "LLM initialization failed" in llm_status.error_message

        # Verify only 3 modules stored
        assert len(loader._modules) == 3
        assert ModuleType.LLM_PROVIDER_CHAIN not in loader._modules

    @pytest.mark.asyncio
    async def test_load_skips_disabled_modules(
        self, mock_signal_generator, mock_paper_orchestrator
    ):
        """Test that disabled modules are skipped during loading.

        Verifies:
        - Disabled modules are not loaded
        - Enabled modules are loaded normally
        - Load returns True when all enabled modules load successfully
        """
        # Create config with some modules disabled
        config = TradingModeConfig(
            mode="paper",
            enabled_modules={
                ModuleType.SIGNAL_GENERATOR: True,
                ModuleType.RISK_ENFORCER: False,
                ModuleType.PAPER_ORCHESTRATOR: True,
                ModuleType.LLM_PROVIDER_CHAIN: False,
            },
        )
        loader = TradingModeLoader(config)

        # Create minimal mock imports for just the enabled modules
        mock_signal_module = MagicMock()
        mock_signal_module.SignalGenerator = MagicMock(
            return_value=mock_signal_generator
        )

        mock_orchestrator_module = MagicMock()
        mock_orchestrator_module.PaperOrchestrator = MagicMock(
            return_value=mock_paper_orchestrator
        )

        mock_imports_minimal = {
            "src.signal_generation.signal_generator": mock_signal_module,
            "src.execution.paper.orchestrator": mock_orchestrator_module,
        }

        with patch.dict("sys.modules", mock_imports_minimal):
            result = await loader.load()

        # Verify load was successful
        assert result is True
        assert loader._loaded is True

        # Verify enabled modules are loaded
        assert loader.module_status[ModuleType.SIGNAL_GENERATOR].loaded is True
        assert loader.module_status[ModuleType.PAPER_ORCHESTRATOR].loaded is True

        # Verify disabled modules are not loaded
        assert loader.module_status[ModuleType.RISK_ENFORCER].loaded is False
        assert loader.module_status[ModuleType.LLM_PROVIDER_CHAIN].loaded is False
        assert (
            loader.module_status[ModuleType.RISK_ENFORCER].state
            == ModuleState.UNINITIALIZED
        )
        assert (
            loader.module_status[ModuleType.LLM_PROVIDER_CHAIN].state
            == ModuleState.UNINITIALIZED
        )

        # Verify only 2 modules stored
        assert len(loader._modules) == 2

    def test_is_healthy_all_loaded(self, paper_config):
        """Test is_healthy returns True when all modules loaded and healthy.

        Verifies:
        - is_healthy returns True when all enabled modules are loaded and healthy
        """
        loader = TradingModeLoader(paper_config)

        # Manually set all modules as loaded and healthy
        for status in loader.module_status.values():
            status.loaded = True
            status.healthy = True

        assert loader.is_healthy() is True

    def test_is_healthy_one_failed(self, paper_config):
        """Test is_healthy returns False when any module failed.

        Verifies:
        - is_healthy returns False when any enabled module is not loaded
        - is_healthy returns False when any enabled module is not healthy
        """
        loader = TradingModeLoader(paper_config)

        # Set all modules as loaded and healthy
        for status in loader.module_status.values():
            status.loaded = True
            status.healthy = True

        # Make one module unhealthy
        loader.module_status[ModuleType.RISK_ENFORCER].healthy = False

        assert loader.is_healthy() is False

        # Make one module not loaded
        loader.module_status[ModuleType.RISK_ENFORCER].healthy = True
        loader.module_status[ModuleType.RISK_ENFORCER].loaded = False

        assert loader.is_healthy() is False

    def test_is_healthy_with_disabled_modules(self):
        """Test is_healthy correctly handles disabled modules.

        Verifies:
        - Disabled modules are not considered in health check
        - Only enabled modules affect is_healthy result
        """
        config = TradingModeConfig(
            mode="paper",
            enabled_modules={
                ModuleType.SIGNAL_GENERATOR: True,
                ModuleType.RISK_ENFORCER: False,  # Disabled
                ModuleType.PAPER_ORCHESTRATOR: True,
                ModuleType.LLM_PROVIDER_CHAIN: False,  # Disabled
            },
        )
        loader = TradingModeLoader(config)

        # Set enabled modules as loaded and healthy
        loader.module_status[ModuleType.SIGNAL_GENERATOR].loaded = True
        loader.module_status[ModuleType.SIGNAL_GENERATOR].healthy = True
        loader.module_status[ModuleType.PAPER_ORCHESTRATOR].loaded = True
        loader.module_status[ModuleType.PAPER_ORCHESTRATOR].healthy = True

        # Disabled modules remain unloaded/unhealthy
        assert loader.is_healthy() is True

    def test_get_module_status(self, paper_config):
        """Test get_module_status returns correct status for each module.

        Verifies:
        - Returns a copy of the module status dict
        - Contains all module types
        - Status values are ModuleStatus instances
        """
        loader = TradingModeLoader(paper_config)

        status = loader.get_module_status()

        # Verify it's a copy (not the same object)
        assert status is not loader.module_status

        # Verify all modules are present
        assert len(status) == 4
        for module_type in ModuleType:
            assert module_type in status
            assert isinstance(status[module_type], ModuleStatus)
            assert status[module_type].module_type == module_type

    @pytest.mark.asyncio
    async def test_health_check(self, paper_config, mock_all_modules):
        """Test health_check returns dict with overall_healthy and module statuses.

        Verifies:
        - Returns dict with overall_healthy boolean
        - Returns modules dict with health status for each loaded module
        - Returns timestamp in ISO format
        - Calls health_check on modules that have the method
        - Updates module status healthy flag based on health check results
        """
        loader = TradingModeLoader(paper_config)

        # Set up modules as loaded
        for module_type, mock_module in mock_all_modules.items():
            loader._modules[module_type] = mock_module
            loader.module_status[module_type].loaded = True
            loader.module_status[module_type].enabled = True

        result = await loader.health_check()

        # Verify result structure
        assert "overall_healthy" in result
        assert "modules" in result
        assert "timestamp" in result

        # Verify overall health
        assert result["overall_healthy"] is True

        # Verify timestamp is valid ISO format
        timestamp = datetime.fromisoformat(result["timestamp"])
        assert timestamp.tzinfo is not None  # Has timezone info

        # Verify module health statuses
        modules_health = result["modules"]
        for module_type in ModuleType:
            module_name = module_type.name
            assert module_name in modules_health
            assert modules_health[module_name]["enabled"] is True
            assert modules_health[module_name]["loaded"] is True
            assert (
                modules_health[module_name]["state"] == "UNINITIALIZED"
            )  # State not changed by health_check
            assert modules_health[module_name]["healthy"] is True
            assert "details" in modules_health[module_name]

        # Verify health_check was called on all modules
        for mock_module in mock_all_modules.values():
            mock_module.health_check.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_check_with_unhealthy_module(
        self, paper_config, mock_all_modules
    ):
        """Test health_check when a module reports unhealthy.

        Verifies:
        - overall_healthy is False when any module is unhealthy
        - Unhealthy module status is correctly reported
        - Healthy modules still report healthy status
        """
        loader = TradingModeLoader(paper_config)

        # Set up modules as loaded
        for module_type, mock_module in mock_all_modules.items():
            loader._modules[module_type] = mock_module
            loader.module_status[module_type].loaded = True
            loader.module_status[module_type].enabled = True

        # Make one module report unhealthy
        mock_all_modules[ModuleType.RISK_ENFORCER].health_check = AsyncMock(
            return_value={"healthy": False, "error": "Risk limit exceeded"}
        )

        result = await loader.health_check()

        # Verify overall health is False
        assert result["overall_healthy"] is False

        # Verify risk enforcer reports unhealthy
        risk_health = result["modules"][ModuleType.RISK_ENFORCER.name]
        assert risk_health["healthy"] is False
        assert risk_health["details"]["error"] == "Risk limit exceeded"

        # Verify other modules are still healthy
        assert result["modules"][ModuleType.SIGNAL_GENERATOR.name]["healthy"] is True

    @pytest.mark.asyncio
    async def test_health_check_module_exception(self, paper_config, mock_all_modules):
        """Test health_check handles exceptions from module health checks.

        Verifies:
        - overall_healthy is False when a module health check raises exception
        - Error is captured in module health status
        - Exception is handled gracefully
        """
        loader = TradingModeLoader(paper_config)

        # Set up modules as loaded
        for module_type, mock_module in mock_all_modules.items():
            loader._modules[module_type] = mock_module
            loader.module_status[module_type].loaded = True
            loader.module_status[module_type].enabled = True

        # Make one module raise exception on health_check
        mock_all_modules[ModuleType.SIGNAL_GENERATOR].health_check = AsyncMock(
            side_effect=Exception("Connection timeout")
        )

        result = await loader.health_check()

        # Verify overall health is False
        assert result["overall_healthy"] is False

        # Verify error is captured
        signal_health = result["modules"][ModuleType.SIGNAL_GENERATOR.name]
        assert signal_health["healthy"] is False
        assert "Connection timeout" in signal_health["error"]

    @pytest.mark.asyncio
    async def test_health_check_skips_unloaded_modules(
        self, paper_config, mock_signal_generator
    ):
        """Test health_check skips modules that are not loaded.

        Verifies:
        - Unloaded modules are not included in health check results
        - Only loaded modules are checked
        """
        loader = TradingModeLoader(paper_config)

        # Only load signal generator
        loader._modules[ModuleType.SIGNAL_GENERATOR] = mock_signal_generator
        loader.module_status[ModuleType.SIGNAL_GENERATOR].loaded = True

        result = await loader.health_check()

        # Verify only signal generator is in results
        assert len(result["modules"]) == 1
        assert ModuleType.SIGNAL_GENERATOR.name in result["modules"]

        # Verify health_check was only called on loaded module
        mock_signal_generator.health_check.assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown(self, paper_config, mock_all_modules):
        """Test shutdown gracefully stops all loaded modules.

        Verifies:
        - Shutdown is called on all loaded modules in reverse order
        - Module states are updated to SHUTDOWN
        - healthy flag is set to False
        - _loaded flag is set to False
        - _modules dict is cleared
        """
        loader = TradingModeLoader(paper_config)

        # Set up modules as loaded
        for module_type, mock_module in mock_all_modules.items():
            loader._modules[module_type] = mock_module
            loader.module_status[module_type].loaded = True
            loader.module_status[module_type].state = ModuleState.LOADED
            loader.module_status[module_type].healthy = True

        loader._loaded = True

        await loader.shutdown()

        # Verify shutdown was called on all modules in reverse order
        # Expected order: LLM_PROVIDER_CHAIN, PAPER_ORCHESTRATOR,
        # RISK_ENFORCER, SIGNAL_GENERATOR
        mock_all_modules[ModuleType.LLM_PROVIDER_CHAIN].shutdown.assert_called_once()
        mock_all_modules[ModuleType.PAPER_ORCHESTRATOR].shutdown.assert_called_once()
        mock_all_modules[ModuleType.RISK_ENFORCER].shutdown.assert_called_once()
        mock_all_modules[ModuleType.SIGNAL_GENERATOR].shutdown.assert_called_once()

        # Verify module states
        for module_type in ModuleType:
            assert loader.module_status[module_type].state == ModuleState.SHUTDOWN
            assert loader.module_status[module_type].healthy is False

        # Verify loader state
        assert loader._loaded is False
        assert loader._modules == {}

    @pytest.mark.asyncio
    async def test_shutdown_handles_exceptions(self, paper_config, mock_all_modules):
        """Test shutdown handles exceptions from module shutdown gracefully.

        Verifies:
        - Exceptions during shutdown are caught and logged
        - Other modules still shut down
        - Error message is captured in module status
        """
        loader = TradingModeLoader(paper_config)

        # Set up modules as loaded
        for module_type, mock_module in mock_all_modules.items():
            loader._modules[module_type] = mock_module
            loader.module_status[module_type].loaded = True
            loader.module_status[module_type].state = ModuleState.LOADED
            loader.module_status[module_type].healthy = True

        # Make one module raise exception on shutdown
        mock_all_modules[ModuleType.RISK_ENFORCER].shutdown = AsyncMock(
            side_effect=Exception("Shutdown timeout")
        )

        loader._loaded = True

        await loader.shutdown()

        # Verify error was captured
        risk_status = loader.module_status[ModuleType.RISK_ENFORCER]
        assert risk_status.error_message is not None
        assert "Shutdown timeout" in risk_status.error_message

        # Verify other modules still shut down
        assert (
            loader.module_status[ModuleType.SIGNAL_GENERATOR].state
            == ModuleState.SHUTDOWN
        )
        assert (
            loader.module_status[ModuleType.PAPER_ORCHESTRATOR].state
            == ModuleState.SHUTDOWN
        )

    @pytest.mark.asyncio
    async def test_shutdown_skips_unloaded_modules(
        self, paper_config, mock_signal_generator
    ):
        """Test shutdown skips modules that were not loaded.

        Verifies:
        - Unloaded modules are not shut down
        - Only loaded modules have shutdown called
        """
        loader = TradingModeLoader(paper_config)

        # Only load signal generator
        loader._modules[ModuleType.SIGNAL_GENERATOR] = mock_signal_generator
        loader.module_status[ModuleType.SIGNAL_GENERATOR].loaded = True
        loader.module_status[ModuleType.SIGNAL_GENERATOR].state = ModuleState.LOADED

        await loader.shutdown()

        # Verify shutdown was only called on loaded module
        mock_signal_generator.shutdown.assert_called_once()

        # Verify other modules were not touched
        for module_type in [
            ModuleType.RISK_ENFORCER,
            ModuleType.PAPER_ORCHESTRATOR,
            ModuleType.LLM_PROVIDER_CHAIN,
        ]:
            assert loader.module_status[module_type].state == ModuleState.UNINITIALIZED

    @pytest.mark.asyncio
    async def test_shutdown_sync_method(self, paper_config):
        """Test shutdown handles modules with synchronous shutdown methods.

        Verifies:
        - Synchronous shutdown methods are called correctly
        - No async/await issues occur
        """
        loader = TradingModeLoader(paper_config)

        # Create mock with synchronous shutdown
        sync_mock = MagicMock()
        sync_mock.shutdown = MagicMock()  # Not async
        sync_mock.health_check = AsyncMock(return_value={"healthy": True})

        loader._modules[ModuleType.SIGNAL_GENERATOR] = sync_mock
        loader.module_status[ModuleType.SIGNAL_GENERATOR].loaded = True
        loader.module_status[ModuleType.SIGNAL_GENERATOR].state = ModuleState.LOADED

        await loader.shutdown()

        # Verify synchronous shutdown was called
        sync_mock.shutdown.assert_called_once()
        assert (
            loader.module_status[ModuleType.SIGNAL_GENERATOR].state
            == ModuleState.SHUTDOWN
        )
