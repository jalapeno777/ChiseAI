"""Integration tests for TradingModeLoader.

This module tests full workflows and integration scenarios for the
TradingModeLoader class.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.trading_mode_loader import (
    ModuleState,
    ModuleType,
    TradingModeConfig,
    TradingModeLoader,
)


class TestIntegration:
    """Integration test cases for TradingModeLoader workflows."""

    @pytest.mark.asyncio
    async def test_full_paper_mode_workflow(
        self,
        mock_imports,
    ):
        """Test full paper mode workflow: load, health check, shutdown.

        This test simulates a complete lifecycle:
        1. Create loader with paper mode config
        2. Load all modules
        3. Verify all required modules are active
        4. Perform health check
        5. Shutdown gracefully

        Verifies:
        - All required paper mode modules load successfully
        - Health check reports all modules healthy
        - Shutdown completes without errors
        """
        # Create paper mode config
        config = TradingModeConfig(
            mode="paper",
            enabled_modules={
                ModuleType.SIGNAL_GENERATOR: True,
                ModuleType.RISK_ENFORCER: True,
                ModuleType.PAPER_ORCHESTRATOR: True,
                ModuleType.LLM_PROVIDER_CHAIN: True,
            },
        )

        # Patch all module imports
        with patch.dict("sys.modules", mock_imports):
            # Step 1: Create loader
            loader = TradingModeLoader(config)

            # Verify initial state
            assert loader.config.mode == "paper"
            assert loader._loaded is False
            for status in loader.module_status.values():
                assert status.state == ModuleState.UNINITIALIZED

            # Step 2: Load all modules
            load_result = await loader.load()

            # Verify load was successful
            assert load_result is True
            assert loader._loaded is True

            # Verify all required paper mode modules are active
            assert loader.module_status[ModuleType.SIGNAL_GENERATOR].loaded is True
            assert (
                loader.module_status[ModuleType.SIGNAL_GENERATOR].state
                == ModuleState.LOADED
            )

            assert loader.module_status[ModuleType.RISK_ENFORCER].loaded is True
            assert (
                loader.module_status[ModuleType.RISK_ENFORCER].state
                == ModuleState.LOADED
            )

            assert loader.module_status[ModuleType.PAPER_ORCHESTRATOR].loaded is True
            assert (
                loader.module_status[ModuleType.PAPER_ORCHESTRATOR].state
                == ModuleState.LOADED
            )

            assert loader.module_status[ModuleType.LLM_PROVIDER_CHAIN].loaded is True
            assert (
                loader.module_status[ModuleType.LLM_PROVIDER_CHAIN].state
                == ModuleState.LOADED
            )

            # Step 3: Verify is_healthy
            assert loader.is_healthy() is True

            # Step 4: Perform health check
            health_result = await loader.health_check()

            # Verify health check results
            assert health_result["overall_healthy"] is True
            assert len(health_result["modules"]) == 4

            for _module_name, module_health in health_result["modules"].items():
                assert module_health["enabled"] is True
                assert module_health["loaded"] is True
                assert module_health["healthy"] is True

            # Step 5: Shutdown
            await loader.shutdown()

            # Verify shutdown state
            assert loader._loaded is False
            assert loader._modules == {}

            for status in loader.module_status.values():
                assert status.state == ModuleState.SHUTDOWN
                assert status.healthy is False

    @pytest.mark.asyncio
    async def test_partial_failure_recovery(self):
        """Test that loader handles partial failures and allows recovery.

        Scenario:
        1. First load attempt: one module fails
        2. User fixes the issue
        3. Second load attempt: all modules succeed

        Verifies:
        - Loader reports failure when module fails
        - Error details are available for debugging
        - After fixing, loader can successfully load
        """
        # Create config
        config = TradingModeConfig(mode="paper")

        # First attempt: signal generator fails
        failing_signal_mock = MagicMock()
        failing_signal_mock.initialize = AsyncMock(
            side_effect=Exception("Database connection failed")
        )

        mock_signal_module_fail = MagicMock()
        mock_signal_module_fail.SignalGenerator = MagicMock(
            return_value=failing_signal_mock
        )

        mock_imports_fail = {
            "src.signal_generation.signal_generator": mock_signal_module_fail,
        }

        with patch.dict("sys.modules", mock_imports_fail):
            loader = TradingModeLoader(config)
            result = await loader.load()

            # Verify failure
            assert result is False
            assert (
                loader.module_status[ModuleType.SIGNAL_GENERATOR].state
                == ModuleState.ERROR
            )
            assert (
                "Database connection failed"
                in loader.module_status[ModuleType.SIGNAL_GENERATOR].error_message
            )

        # Second attempt: all modules succeed (fresh loader)
        working_signal_mock = MagicMock()
        working_signal_mock.initialize = AsyncMock()
        working_signal_mock.health_check = AsyncMock(return_value={"healthy": True})
        working_signal_mock.shutdown = AsyncMock()

        mock_signal_module_ok = MagicMock()
        mock_signal_module_ok.SignalGenerator = MagicMock(
            return_value=working_signal_mock
        )

        mock_risk_module = MagicMock()
        mock_risk_module.RiskEnforcer = MagicMock(
            return_value=MagicMock(
                initialize=AsyncMock(),
                health_check=AsyncMock(return_value={"healthy": True}),
                shutdown=AsyncMock(),
            )
        )

        mock_orchestrator_module = MagicMock()
        mock_orchestrator_module.PaperOrchestrator = MagicMock(
            return_value=MagicMock(
                initialize=AsyncMock(),
                health_check=AsyncMock(return_value={"healthy": True}),
                shutdown=AsyncMock(),
            )
        )

        mock_llm_module = MagicMock()
        mock_llm_module.ProviderChain = MagicMock(
            return_value=MagicMock(
                initialize=AsyncMock(),
                health_check=AsyncMock(return_value={"healthy": True}),
                shutdown=AsyncMock(),
            )
        )

        mock_imports_ok = {
            "src.signal_generation.signal_generator": mock_signal_module_ok,
            "src.execution.paper.risk_enforcer": mock_risk_module,
            "src.execution.paper.orchestrator": mock_orchestrator_module,
            "src.llm.provider_chain": mock_llm_module,
        }

        with patch.dict("sys.modules", mock_imports_ok):
            loader2 = TradingModeLoader(config)
            result = await loader2.load()

            # Verify success
            assert result is True
            assert loader2.is_healthy() is True

    @pytest.mark.asyncio
    async def test_health_check_degradation(self, mock_imports):
        """Test health check behavior when modules degrade after loading.

        Scenario:
        1. Load all modules successfully
        2. One module becomes unhealthy (e.g., connection lost)
        3. Health check reflects the degraded state
        4. Overall health is False

        Verifies:
        - Health check reflects current module state
        - Unhealthy modules are detected
        - Overall health is False when any module is unhealthy
        """
        config = TradingModeConfig(mode="paper")

        # Create mocks with initial healthy state
        signal_mock = MagicMock()
        signal_mock.initialize = AsyncMock()
        signal_mock.health_check = AsyncMock(return_value={"healthy": True})
        signal_mock.shutdown = AsyncMock()

        risk_mock = MagicMock()
        risk_mock.initialize = AsyncMock()
        # Will be updated to unhealthy later
        risk_mock.health_check = AsyncMock(return_value={"healthy": True})
        risk_mock.shutdown = AsyncMock()

        orchestrator_mock = MagicMock()
        orchestrator_mock.initialize = AsyncMock()
        orchestrator_mock.health_check = AsyncMock(return_value={"healthy": True})
        orchestrator_mock.shutdown = AsyncMock()

        llm_mock = MagicMock()
        llm_mock.initialize = AsyncMock()
        llm_mock.health_check = AsyncMock(return_value={"healthy": True})
        llm_mock.shutdown = AsyncMock()

        # Update mock_imports with our controlled mocks
        mock_imports["src.signal_generation.signal_generator"].SignalGenerator = (
            MagicMock(return_value=signal_mock)
        )
        mock_imports["src.execution.paper.risk_enforcer"].RiskEnforcer = MagicMock(
            return_value=risk_mock
        )
        mock_imports["src.execution.paper.orchestrator"].PaperOrchestrator = MagicMock(
            return_value=orchestrator_mock
        )
        mock_imports["src.llm.provider_chain"].ProviderChain = MagicMock(
            return_value=llm_mock
        )

        with patch.dict("sys.modules", mock_imports):
            loader = TradingModeLoader(config)
            await loader.load()

            # Initial health check - all healthy
            health = await loader.health_check()
            assert health["overall_healthy"] is True

            # Simulate degradation - risk enforcer becomes unhealthy
            risk_mock.health_check = AsyncMock(
                return_value={"healthy": False, "error": "Connection timeout"}
            )

            # Health check reflects degradation
            health = await loader.health_check()
            assert health["overall_healthy"] is False
            assert health["modules"]["RISK_ENFORCER"]["healthy"] is False
            assert (
                "Connection timeout"
                in health["modules"]["RISK_ENFORCER"]["details"]["error"]
            )

            # Other modules still healthy
            assert health["modules"]["SIGNAL_GENERATOR"]["healthy"] is True

    @pytest.mark.asyncio
    async def test_module_interdependence_during_shutdown(self, mock_imports):
        """Test that shutdown order respects module dependencies.

        Modules should be shut down in reverse order of loading:
        1. LLM_PROVIDER_CHAIN (depends on nothing, but others may use it)
        2. PAPER_ORCHESTRATOR (depends on risk enforcer)
        3. RISK_ENFORCER (depends on signal generator)
        4. SIGNAL_GENERATOR (base module)

        This ensures dependent modules are shut down before their dependencies.
        """
        config = TradingModeConfig(mode="paper")

        # Track shutdown order
        shutdown_order = []

        def create_tracking_mock(name):
            mock = MagicMock()
            mock.initialize = AsyncMock()
            mock.health_check = AsyncMock(return_value={"healthy": True})

            async def track_shutdown():
                shutdown_order.append(name)

            mock.shutdown = track_shutdown
            return mock

        signal_mock = create_tracking_mock("signal")
        risk_mock = create_tracking_mock("risk")
        orchestrator_mock = create_tracking_mock("orchestrator")
        llm_mock = create_tracking_mock("llm")

        mock_imports["src.signal_generation.signal_generator"].SignalGenerator = (
            MagicMock(return_value=signal_mock)
        )
        mock_imports["src.execution.paper.risk_enforcer"].RiskEnforcer = MagicMock(
            return_value=risk_mock
        )
        mock_imports["src.execution.paper.orchestrator"].PaperOrchestrator = MagicMock(
            return_value=orchestrator_mock
        )
        mock_imports["src.llm.provider_chain"].ProviderChain = MagicMock(
            return_value=llm_mock
        )

        with patch.dict("sys.modules", mock_imports):
            loader = TradingModeLoader(config)
            await loader.load()

            # Clear any previous calls
            shutdown_order.clear()

            await loader.shutdown()

            # Verify shutdown order: llm, orchestrator, risk, signal
            assert shutdown_order == ["llm", "orchestrator", "risk", "signal"]

    @pytest.mark.asyncio
    async def test_minimal_paper_mode_workflow(self):
        """Test paper mode with minimal required modules.

        Paper mode can work with just:
        - SIGNAL_GENERATOR
        - PAPER_ORCHESTRATOR

        This tests a lightweight configuration.
        """
        config = TradingModeConfig(
            mode="paper",
            enabled_modules={
                ModuleType.SIGNAL_GENERATOR: True,
                ModuleType.RISK_ENFORCER: False,
                ModuleType.PAPER_ORCHESTRATOR: True,
                ModuleType.LLM_PROVIDER_CHAIN: False,
            },
        )

        signal_mock = MagicMock()
        signal_mock.initialize = AsyncMock()
        signal_mock.health_check = AsyncMock(return_value={"healthy": True})
        signal_mock.shutdown = AsyncMock()

        orchestrator_mock = MagicMock()
        orchestrator_mock.initialize = AsyncMock()
        orchestrator_mock.health_check = AsyncMock(return_value={"healthy": True})
        orchestrator_mock.shutdown = AsyncMock()

        mock_signal_module = MagicMock()
        mock_signal_module.SignalGenerator = MagicMock(return_value=signal_mock)

        mock_orchestrator_module = MagicMock()
        mock_orchestrator_module.PaperOrchestrator = MagicMock(
            return_value=orchestrator_mock
        )

        mock_imports_minimal = {
            "src.signal_generation.signal_generator": mock_signal_module,
            "src.execution.paper.orchestrator": mock_orchestrator_module,
        }

        with patch.dict("sys.modules", mock_imports_minimal):
            loader = TradingModeLoader(config)

            # Load should succeed with minimal modules
            result = await loader.load()
            assert result is True

            # Only enabled modules should be loaded
            assert loader.module_status[ModuleType.SIGNAL_GENERATOR].loaded is True
            assert loader.module_status[ModuleType.PAPER_ORCHESTRATOR].loaded is True
            assert loader.module_status[ModuleType.RISK_ENFORCER].loaded is False
            assert loader.module_status[ModuleType.LLM_PROVIDER_CHAIN].loaded is False

            # Health check should only check loaded modules
            health = await loader.health_check()
            assert len(health["modules"]) == 2
            assert health["overall_healthy"] is True

            # Shutdown should work
            await loader.shutdown()
            signal_mock.shutdown.assert_called_once()
            orchestrator_mock.shutdown.assert_called_once()
