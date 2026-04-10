"""Execution safety guards to prevent mock/sim leakage.

This module provides runtime guards to ensure that:
1. Only authenticated demo connectors are used when credentials available
2. OrderSimulator cannot be used if demo credentials are present
3. All execution paths are logged with provenance

For REMEDIATION-001: G8 Bybit Demo Provenance
"""

from __future__ import annotations

import contextlib
import logging
import os
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ExecutionGuardResult:
    """Result of execution guard check.

    Attributes:
        allowed: Whether the execution is allowed
        reason: Reason for the decision
        recommendation: Recommended action
    """

    allowed: bool
    reason: str
    recommendation: str


class ExecutionSafetyGuard:
    """Safety guard to prevent mock/sim leakage.

    This guard ensures that:
    - BybitDemoConnector is used when demo credentials are available
    - OrderSimulator is only used when no demo credentials exist
    - All execution paths are logged with provenance
    """

    @staticmethod
    def check_execution_path(
        executor: Any,
        require_demo: bool = True,
    ) -> ExecutionGuardResult:
        """Check if the execution path is safe.

        Args:
            executor: The order executor instance
            require_demo: Whether to require demo mode

        Returns:
            ExecutionGuardResult with check results
        """
        executor_type = type(executor).__name__
        has_demo_creds = bool(
            os.environ.get("BYBIT_DEMO_API_KEY")
            and os.environ.get("BYBIT_DEMO_API_SECRET")
        )

        # Check FORCE_SIMULATOR_MODE (PAPER-RECON-001)
        # When True, OrderSimulator is allowed even if demo credentials exist
        force_simulator_mode = False
        try:
            from config.feature_flags import get_feature_flags

            flags = get_feature_flags()
            force_simulator_mode = flags.is_force_simulator_mode_enabled()
        except Exception:
            pass  # If feature flags unavailable, use default behavior

        # Check if using BybitDemoConnector with demo credentials
        if executor_type == "BybitDemoConnector":
            if has_demo_creds:
                # Check if it's actually in demo mode
                if hasattr(executor, "is_demo_mode") and executor.is_demo_mode():
                    return ExecutionGuardResult(
                        allowed=True,
                        reason="Using BybitDemoConnector with demo credentials in demo mode",
                        recommendation="Execution approved - authenticated demo trading",
                    )
                else:
                    return ExecutionGuardResult(
                        allowed=False,
                        reason="BybitDemoConnector not in demo mode",
                        recommendation="STOP - Connector must be in demo mode",
                    )
            else:
                return ExecutionGuardResult(
                    allowed=False,
                    reason="BybitDemoConnector requires demo credentials",
                    recommendation="STOP - Set BYBIT_DEMO_API_KEY and BYBIT_DEMO_API_SECRET",
                )

        # Check if using OrderSimulator
        elif executor_type == "OrderSimulator":
            # Allow OrderSimulator if FORCE_SIMULATOR_MODE is enabled
            if force_simulator_mode:
                return ExecutionGuardResult(
                    allowed=True,
                    reason="OrderSimulator used with FORCE_SIMULATOR_MODE=true (rollback option)",
                    recommendation="Execution approved - simulator forced via feature flag",
                )
            if has_demo_creds and require_demo:
                return ExecutionGuardResult(
                    allowed=False,
                    reason="OrderSimulator used but demo credentials are available",
                    recommendation="STOP - Use BybitDemoConnector instead of OrderSimulator",
                )
            else:
                return ExecutionGuardResult(
                    allowed=True,
                    reason="OrderSimulator used without demo credentials (simulated execution)",
                    recommendation="Execution approved - no credentials available for live trading",
                )

        # Unknown executor type
        else:
            return ExecutionGuardResult(
                allowed=False,
                reason=f"Unknown executor type: {executor_type}",
                recommendation="STOP - Use only approved executors (BybitDemoConnector, OrderSimulator)",
            )

    @staticmethod
    def validate_before_execution(executor: Any) -> None:
        """Validate execution path before placing orders.

        Args:
            executor: The order executor instance

        Raises:
            RuntimeError: If execution path is not safe
        """
        result = ExecutionSafetyGuard.check_execution_path(executor)

        if not result.allowed:
            logger.error(
                f"EXECUTION GUARD BLOCKED: {result.reason}. "
                f"Recommendation: {result.recommendation}"
            )
            raise RuntimeError(
                f"Execution blocked by safety guard: {result.reason}. "
                f"{result.recommendation}"
            )

        logger.info(f"EXECUTION GUARD APPROVED: {result.reason}")

    @staticmethod
    def log_execution_provenance(executor: Any, operation: str) -> None:
        """Log execution provenance for audit trail.

        Args:
            executor: The order executor instance
            operation: The operation being performed
        """
        executor_type = type(executor).__name__

        # Get provenance if available
        provenance = None
        if hasattr(executor, "get_provenance"):
            with contextlib.suppress(Exception):
                provenance = executor.get_provenance()

        if provenance:
            logger.info(
                f"EXECUTION PROVENANCE: {operation} | "
                f"executor={executor_type} | "
                f"demo_mode={provenance.is_demo} | "
                f"endpoint={provenance.endpoint} | "
                f"api_key={provenance.api_key_prefix}... | "
                f"timestamp={provenance.timestamp}"
            )
        else:
            logger.info(
                f"EXECUTION PROVENANCE: {operation} | "
                f"executor={executor_type} | "
                f"no_provenance_available"
            )


def guard_execution(executor: Any) -> None:
    """Guard execution to prevent mock/sim leakage.

    This is a convenience function that validates the execution path
    and logs provenance in one call.

    Args:
        executor: The order executor instance

    Raises:
        RuntimeError: If execution path is not safe

    Example:
        >>> from execution.safety.execution_guard import guard_execution
        >>> guard_execution(order_executor)
        >>> result = await order_executor.place_order(...)
    """
    ExecutionSafetyGuard.validate_before_execution(executor)
    ExecutionSafetyGuard.log_execution_provenance(executor, "order_placement")


# Global guard instance
default_guard = ExecutionSafetyGuard()
