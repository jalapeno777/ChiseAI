"""Test fixtures for brain promotion flow integration tests.

ST-CHISE-001.4: Add Integration Tests for Brain Promotion Flow
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import Any

import pytest
from src.brain.batch_evaluator import (
    BatchEvaluator,
    EvaluationResult,
    EvaluationStatus,
    Leaderboard,
)
from src.brain.promotion_packet import (
    ApprovalSignature,
    ApprovalStatus,
    PacketGenerator,
    PacketStatus,
    PromotionPacket,
)
from src.brain.rollback_handler import (
    RollbackHandler,
    RollbackStep,
)
from src.brain.shadow_testing import (
    ShadowTestConfig,
)
from src.brain.version import BrainVersion

# =============================================================================
# Brain Function Fixtures
# =============================================================================


@pytest.fixture
def fast_brain() -> Callable[[Any], Coroutine[Any, Any, Any]]:
    """Mock brain function with fast latency (< 10ms)."""

    async def _brain(input_data: Any) -> dict[str, Any]:
        await asyncio.sleep(0.001)  # 1ms simulated latency
        return {
            "prediction": "buy",
            "confidence": 0.85,
            "input": input_data,
        }

    return _brain


@pytest.fixture
def slow_brain() -> Callable[[Any], Coroutine[Any, Any, Any]]:
    """Mock brain function with slow latency (> 100ms)."""

    async def _brain(input_data: Any) -> dict[str, Any]:
        await asyncio.sleep(0.15)  # 150ms simulated latency
        return {
            "prediction": "sell",
            "confidence": 0.75,
            "input": input_data,
        }

    return _brain


@pytest.fixture
def medium_brain() -> Callable[[Any], Coroutine[Any, Any, Any]]:
    """Mock brain function with medium latency (~50ms)."""

    async def _brain(input_data: Any) -> dict[str, Any]:
        await asyncio.sleep(0.05)  # 50ms simulated latency
        return {
            "prediction": "hold",
            "confidence": 0.60,
            "input": input_data,
        }

    return _brain


@pytest.fixture
def failing_brain() -> Callable[[Any], Coroutine[Any, Any, Any]]:
    """Mock brain function that raises an exception."""

    async def _brain(input_data: Any) -> dict[str, Any]:
        raise ValueError("Brain prediction failed")

    return _brain


# =============================================================================
# Version Fixtures
# =============================================================================


@pytest.fixture
def version_1_0_0() -> BrainVersion:
    """Brain version 1.0.0 (baseline)."""
    return BrainVersion(major=1, minor=0, patch=0)


@pytest.fixture
def version_1_1_0() -> BrainVersion:
    """Brain version 1.1.0 (minor update)."""
    return BrainVersion(major=1, minor=1, patch=0)


@pytest.fixture
def version_2_0_0() -> BrainVersion:
    """Brain version 2.0.0 (major update)."""
    return BrainVersion(major=2, minor=0, patch=0)


@pytest.fixture
def version_2_0_0_alpha() -> BrainVersion:
    """Brain version 2.0.0-alpha (pre-release)."""
    return BrainVersion(major=2, minor=0, patch=0, prerelease="alpha")


# =============================================================================
# Test Input Fixtures
# =============================================================================


@pytest.fixture
def sample_test_inputs() -> list[dict[str, Any]]:
    """Sample test inputs for brain evaluation."""
    return [
        {"symbol": "BTCUSDT", "price": 50000.0, "volume": 1000.0},
        {"symbol": "ETHUSDT", "price": 3000.0, "volume": 5000.0},
        {"symbol": "SOLUSDT", "price": 100.0, "volume": 10000.0},
        {"symbol": "ADAUSDT", "price": 0.50, "volume": 50000.0},
        {"symbol": "DOTUSDT", "price": 7.0, "volume": 20000.0},
    ]


# =============================================================================
# Shadow Test Configuration Fixtures
# =============================================================================


@pytest.fixture
def passing_shadow_config(
    version_2_0_0: BrainVersion,
    version_1_0_0: BrainVersion,
) -> ShadowTestConfig:
    """Shadow test config that will pass with fast brains."""
    return ShadowTestConfig(
        candidate_version=version_2_0_0,
        baseline_version=version_1_0_0,
        max_latency_overhead_ms=100.0,
        sample_size=5,
        parallel_enabled=True,
        warmup_iterations=1,
        measurement_iterations=3,
    )


@pytest.fixture
def strict_shadow_config(
    version_2_0_0: BrainVersion,
    version_1_0_0: BrainVersion,
) -> ShadowTestConfig:
    """Strict shadow test config that will fail with slow brains."""
    return ShadowTestConfig(
        candidate_version=version_2_0_0,
        baseline_version=version_1_0_0,
        max_latency_overhead_ms=50.0,  # Strict 50ms threshold
        sample_size=3,
        parallel_enabled=True,
        warmup_iterations=0,
        measurement_iterations=2,
    )


# =============================================================================
# Evaluation Result Fixtures
# =============================================================================


@pytest.fixture
def sample_evaluation_results() -> list[EvaluationResult]:
    """Sample evaluation results for multiple brain versions."""
    return [
        EvaluationResult(
            brain_version="1.0.0",
            status=EvaluationStatus.COMPLETED,
            accuracy=0.82,
            precision=0.80,
            recall=0.78,
            f1_score=0.79,
            win_rate=0.75,
            sharpe_ratio=1.2,
            max_drawdown=0.15,
            duration_seconds=120.0,
        ),
        EvaluationResult(
            brain_version="1.1.0",
            status=EvaluationStatus.COMPLETED,
            accuracy=0.85,
            precision=0.83,
            recall=0.81,
            f1_score=0.82,
            win_rate=0.78,
            sharpe_ratio=1.4,
            max_drawdown=0.12,
            duration_seconds=125.0,
        ),
        EvaluationResult(
            brain_version="2.0.0",
            status=EvaluationStatus.COMPLETED,
            accuracy=0.88,
            precision=0.86,
            recall=0.84,
            f1_score=0.85,
            win_rate=0.82,
            sharpe_ratio=1.6,
            max_drawdown=0.10,
            duration_seconds=130.0,
        ),
    ]


@pytest.fixture
def failing_evaluation_result() -> EvaluationResult:
    """Sample failing evaluation result."""
    return EvaluationResult(
        brain_version="2.0.0-failed",
        status=EvaluationStatus.FAILED,
        error_message="Evaluation timed out after 300 seconds",
    )


# =============================================================================
# Promotion Packet Fixtures
# =============================================================================


@pytest.fixture
def sample_promotion_packet() -> PromotionPacket:
    """Sample promotion packet with complete data."""
    return PromotionPacket(
        candidate_version="2.0.0",
        baseline_version="1.0.0",
        summary_metrics={
            "accuracy": 0.88,
            "precision": 0.86,
            "recall": 0.84,
            "f1": 0.85,
            "win_rate": 0.82,
            "sharpe": 1.6,
            "max_drawdown": 0.10,
        },
        safety_checks={
            "no_regression_on_critical_metrics": True,
            "passes_all_unit_tests": True,
            "passes_integration_tests": True,
            "shadow_test_passed": True,
            "latency_within_bounds": True,
            "memory_within_bounds": True,
        },
        rollback_plan="# Rollback Plan\n\nSteps to rollback...",
        required_approvers=["admin", "lead"],
        status=PacketStatus.DRAFT,
    )


@pytest.fixture
def approved_promotion_packet() -> PromotionPacket:
    """Sample approved promotion packet."""
    packet = PromotionPacket(
        candidate_version="2.0.0",
        baseline_version="1.0.0",
        summary_metrics={"accuracy": 0.88},
        safety_checks={"tests_pass": True},
        rollback_plan="Rollback plan",
        required_approvers=["admin"],
        status=PacketStatus.APPROVED,
    )
    packet.signatures.append(
        ApprovalSignature(
            approver="admin",
            timestamp=datetime.now(UTC),
            status=ApprovalStatus.APPROVED,
            comments="Approved for production",
        )
    )
    return packet


@pytest.fixture
def packet_generator() -> PacketGenerator:
    """Packet generator instance."""
    return PacketGenerator()


# =============================================================================
# Rollback Handler Fixtures
# =============================================================================


@pytest.fixture
def rollback_handler() -> RollbackHandler:
    """Rollback handler with default settings."""
    return RollbackHandler(
        ece_threshold=0.15,
        win_rate_threshold=0.05,
        max_drawdown_threshold=0.20,
        active_trades_check=True,
        version_registry=["1.0.0", "1.1.0", "2.0.0"],
    )


@pytest.fixture
def rollback_handler_no_trade_check() -> RollbackHandler:
    """Rollback handler with active trades check disabled."""
    return RollbackHandler(
        ece_threshold=0.15,
        active_trades_check=False,
        version_registry=["1.0.0", "1.1.0", "2.0.0"],
    )


@pytest.fixture
def sample_rollback_steps() -> list[RollbackStep]:
    """Sample rollback steps for testing."""
    return [
        RollbackStep(
            step_number=1,
            description="Stop active trading",
            verification_command="systemctl stop chise-trader",
            expected_result="trader stopped",
        ),
        RollbackStep(
            step_number=2,
            description="Backup current state",
            verification_command="chise-backup create --tag pre-rollback",
            expected_result="backup created",
        ),
        RollbackStep(
            step_number=3,
            description="Switch to target version",
            verification_command="chise-version switch",
            expected_result="version switched",
        ),
        RollbackStep(
            step_number=4,
            description="Verify version",
            verification_command="chise-version current",
            expected_result="version verified",
        ),
        RollbackStep(
            step_number=5,
            description="Restart services",
            verification_command="systemctl start chise-trader",
            expected_result="trader started",
        ),
    ]


# =============================================================================
# Batch Evaluator Fixtures
# =============================================================================


@pytest.fixture
def batch_evaluator() -> BatchEvaluator:
    """Batch evaluator instance."""
    return BatchEvaluator(
        default_timeout_seconds=60.0,
        max_concurrent=5,
    )


@pytest.fixture
def leaderboard() -> Leaderboard:
    """Leaderboard instance with default config."""
    return Leaderboard()


# =============================================================================
# Integration Test Data Fixtures
# =============================================================================


@pytest.fixture
def complete_evaluation_data() -> dict[str, Any]:
    """Complete evaluation data for packet generation."""
    return {
        "version": "2.0.0",
        "metrics": {
            "accuracy": 0.88,
            "precision": 0.86,
            "recall": 0.84,
            "f1": 0.85,
            "win_rate": 0.82,
            "sharpe": 1.6,
            "max_drawdown": 0.10,
        },
        "safety_checks": {
            "no_regression_on_critical_metrics": True,
            "passes_all_unit_tests": True,
            "passes_integration_tests": True,
            "shadow_test_passed": True,
            "latency_within_bounds": True,
            "memory_within_bounds": True,
        },
        "timestamp": datetime.now(UTC).isoformat(),
    }


@pytest.fixture
def ece_degradation_metrics() -> dict[str, float]:
    """Metrics that trigger ECE degradation rollback."""
    return {
        "ece": 0.20,  # Above 0.15 threshold
        "win_rate": 0.75,
        "baseline_win_rate": 0.80,
        "max_drawdown": 0.15,
        "active_trades": 0,
        "data_consistent": True,
    }


@pytest.fixture
def win_rate_drop_metrics() -> dict[str, float]:
    """Metrics that trigger win rate drop rollback."""
    return {
        "ece": 0.10,
        "win_rate": 0.70,  # 10% drop from baseline
        "baseline_win_rate": 0.80,
        "max_drawdown": 0.15,
        "active_trades": 0,
        "data_consistent": True,
    }


@pytest.fixture
def max_drawdown_breach_metrics() -> dict[str, float]:
    """Metrics that trigger max drawdown breach rollback."""
    return {
        "ece": 0.10,
        "win_rate": 0.75,
        "baseline_win_rate": 0.80,
        "max_drawdown": 0.25,  # Above 0.20 threshold
        "active_trades": 0,
        "data_consistent": True,
    }


@pytest.fixture
def safety_violation_metrics() -> dict[str, float]:
    """Metrics that trigger safety violation rollback."""
    return {
        "ece": 0.10,
        "win_rate": 0.75,
        "baseline_win_rate": 0.80,
        "max_drawdown": 0.15,
        "safety_violations": 1,  # Safety violation present
        "active_trades": 0,
        "data_consistent": True,
    }
