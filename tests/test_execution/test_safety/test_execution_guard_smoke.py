"""Smoke tests for execution_guard module.

Basic tests to verify the ExecutionGuard functionality.
"""

from unittest.mock import MagicMock, patch

import pytest

from execution.safety.execution_guard import (
    ExecutionGuardResult,
    ExecutionSafetyGuard,
    guard_execution,
)


class TestExecutionGuardResult:
    """Tests for ExecutionGuardResult dataclass."""

    def test_guard_result_creation(self):
        """Test that ExecutionGuardResult can be created."""
        result = ExecutionGuardResult(
            allowed=True,
            reason="Test reason",
            recommendation="Test recommendation",
        )
        assert result.allowed is True
        assert result.reason == "Test reason"
        assert result.recommendation == "Test recommendation"

    def test_guard_result_blocked(self):
        """Test ExecutionGuardResult for blocked execution."""
        result = ExecutionGuardResult(
            allowed=False,
            reason="Execution blocked",
            recommendation="Stop immediately",
        )
        assert result.allowed is False
        assert result.reason == "Execution blocked"
        assert result.recommendation == "Stop immediately"


class TestExecutionSafetyGuard:
    """Tests for ExecutionSafetyGuard class."""

    def test_execution_safety_guard_exists(self):
        """Test that ExecutionSafetyGuard class exists."""
        assert ExecutionSafetyGuard is not None

    def test_check_execution_path_with_bybit_demo_connector_demo_mode(self):
        """Test execution path check with BybitDemoConnector in demo mode."""
        mock_executor = MagicMock()
        mock_executor.__class__.__name__ = "BybitDemoConnector"
        mock_executor.is_demo_mode.return_value = True

        with patch.dict(
            "os.environ",
            {
                "BYBIT_DEMO_API_KEY": "test_key",
                "BYBIT_DEMO_API_SECRET": "test_secret",
            },
        ):
            result = ExecutionSafetyGuard.check_execution_path(mock_executor)

        assert result.allowed is True
        assert "BybitDemoConnector" in result.reason
        assert "demo" in result.reason.lower()

    def test_check_execution_path_with_bybit_demo_connector_not_demo_mode(self):
        """Test execution path check with BybitDemoConnector not in demo mode."""
        mock_executor = MagicMock()
        mock_executor.__class__.__name__ = "BybitDemoConnector"
        mock_executor.is_demo_mode.return_value = False

        with patch.dict(
            "os.environ",
            {
                "BYBIT_DEMO_API_KEY": "test_key",
                "BYBIT_DEMO_API_SECRET": "test_secret",
            },
        ):
            result = ExecutionSafetyGuard.check_execution_path(mock_executor)

        assert result.allowed is False
        assert "not in demo mode" in result.reason

    def test_check_execution_path_with_bybit_demo_connector_no_creds(self):
        """Test execution path check with BybitDemoConnector but no demo credentials."""
        mock_executor = MagicMock()
        mock_executor.__class__.__name__ = "BybitDemoConnector"

        with patch.dict("os.environ", {}, clear=True):
            result = ExecutionSafetyGuard.check_execution_path(mock_executor)

        assert result.allowed is False
        assert "requires demo credentials" in result.reason

    def test_check_execution_path_with_order_simulator_no_creds(self):
        """Test execution path check with OrderSimulator and no demo credentials."""
        mock_executor = MagicMock()
        mock_executor.__class__.__name__ = "OrderSimulator"

        with patch.dict("os.environ", {}, clear=True):
            result = ExecutionSafetyGuard.check_execution_path(mock_executor)

        assert result.allowed is True
        assert "OrderSimulator" in result.reason
        assert "simulated" in result.reason.lower()

    def test_check_execution_path_with_order_simulator_with_creds(self):
        """Test execution path check with OrderSimulator but demo credentials exist."""
        mock_executor = MagicMock()
        mock_executor.__class__.__name__ = "OrderSimulator"

        with patch.dict(
            "os.environ",
            {
                "BYBIT_DEMO_API_KEY": "test_key",
                "BYBIT_DEMO_API_SECRET": "test_secret",
            },
        ):
            result = ExecutionSafetyGuard.check_execution_path(mock_executor)

        assert result.allowed is False
        assert "demo credentials are available" in result.reason

    def test_check_execution_path_with_unknown_executor(self):
        """Test execution path check with unknown executor type."""
        mock_executor = MagicMock()
        mock_executor.__class__.__name__ = "UnknownExecutor"

        result = ExecutionSafetyGuard.check_execution_path(mock_executor)

        assert result.allowed is False
        assert "Unknown executor type" in result.reason

    def test_validate_before_execution_raises_on_blocked(self):
        """Test that validate_before_execution raises on blocked execution."""
        mock_executor = MagicMock()
        mock_executor.__class__.__name__ = "UnknownExecutor"

        with pytest.raises(RuntimeError) as exc_info:
            ExecutionSafetyGuard.validate_before_execution(mock_executor)

        assert "Execution blocked by safety guard" in str(exc_info.value)

    def test_validate_before_execution_passes_on_allowed(self):
        """Test that validate_before_execution passes on allowed execution."""
        mock_executor = MagicMock()
        mock_executor.__class__.__name__ = "OrderSimulator"

        with patch.dict("os.environ", {}, clear=True):
            # Should not raise
            ExecutionSafetyGuard.validate_before_execution(mock_executor)

    def test_log_execution_provenance_with_provenance(self):
        """Test logging execution provenance when provenance is available."""
        mock_executor = MagicMock()
        mock_executor.__class__.__name__ = "TestExecutor"

        mock_provenance = MagicMock()
        mock_provenance.is_demo = True
        mock_provenance.endpoint = "https://api-demo.bybit.com"
        mock_provenance.api_key_prefix = "test_key_"
        mock_provenance.timestamp = "2024-01-01T00:00:00"
        mock_executor.get_provenance.return_value = mock_provenance

        with patch("execution.safety.execution_guard.logger") as mock_logger:
            ExecutionSafetyGuard.log_execution_provenance(
                mock_executor, "test_operation"
            )
            mock_logger.info.assert_called()
            log_call = mock_logger.info.call_args[0][0]
            assert "EXECUTION PROVENANCE" in log_call
            assert "TestExecutor" in log_call

    def test_log_execution_provenance_without_provenance(self):
        """Test logging execution provenance when provenance is not available."""
        mock_executor = MagicMock()
        mock_executor.__class__.__name__ = "TestExecutor"
        del mock_executor.get_provenance

        with patch("execution.safety.execution_guard.logger") as mock_logger:
            ExecutionSafetyGuard.log_execution_provenance(
                mock_executor, "test_operation"
            )
            mock_logger.info.assert_called()
            log_call = mock_logger.info.call_args[0][0]
            assert "EXECUTION PROVENANCE" in log_call
            assert "no_provenance_available" in log_call


class TestGuardExecutionFunction:
    """Tests for the guard_execution convenience function."""

    def test_guard_execution_exists(self):
        """Test that guard_execution function exists."""
        assert guard_execution is not None
        assert callable(guard_execution)

    def test_guard_execution_validates_and_logs(self):
        """Test that guard_execution validates and logs provenance."""
        mock_executor = MagicMock()
        mock_executor.__class__.__name__ = "OrderSimulator"

        with patch.dict("os.environ", {}, clear=True):
            with patch("execution.safety.execution_guard.logger") as mock_logger:
                # Should not raise
                guard_execution(mock_executor)
                mock_logger.info.assert_called()

    def test_guard_execution_raises_on_invalid(self):
        """Test that guard_execution raises on invalid execution."""
        mock_executor = MagicMock()
        mock_executor.__class__.__name__ = "UnknownExecutor"

        with pytest.raises(RuntimeError):
            guard_execution(mock_executor)


class TestDefaultGuardInstance:
    """Tests for the default guard instance."""

    def test_default_guard_exists(self):
        """Test that default_guard instance exists."""
        from execution.safety.execution_guard import default_guard

        assert default_guard is not None
        assert isinstance(default_guard, ExecutionSafetyGuard)
