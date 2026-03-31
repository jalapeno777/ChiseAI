"""Tests for Q4: Per-gate outcome metrics in the paper orchestrator.

Verifies that gate_outcome log lines are emitted for each named gate
(risk, signal_quality, confidence) with correct pass/fail outcomes.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from execution.paper.risk_models import (
    RiskAssessment,
    RiskSeverity,
    RiskViolation,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_signal(confidence: float = 0.90, **kwargs) -> MagicMock:
    """Create a mock Signal with the given confidence."""
    signal = MagicMock()
    signal.confidence = confidence
    signal.token = kwargs.get("token", "BTCUSDT")
    signal.signal_id = kwargs.get("signal_id", "test-signal-123")
    signal.direction = MagicMock()
    signal.direction.value = kwargs.get("direction", "long")
    signal.stop_loss = kwargs.get("stop_loss")
    signal.risk_reward_ratio = kwargs.get("risk_reward_ratio", 2.0)
    signal.metadata = kwargs.get("metadata", {})
    return signal


def _make_assessment(
    approved: bool = True,
    violations: list[RiskViolation] | None = None,
) -> RiskAssessment:
    """Create a RiskAssessment with the given parameters."""
    return RiskAssessment(
        approved=approved,
        violations=violations or [],
        position_size=100.0,
    )


# ---------------------------------------------------------------------------
# Direct unit tests for _emit_gate_outcomes
# ---------------------------------------------------------------------------


class TestEmitGateOutcomes:
    """Tests for PaperTradingOrchestrator._emit_gate_outcomes."""

    def _make_orchestrator(self) -> MagicMock:
        """Create a minimal orchestrator mock with _emit_gate_outcomes bound."""
        from execution.paper.orchestrator import PaperTradingOrchestrator

        # We instantiate the class but mock all heavy dependencies.
        # _emit_gate_outcomes is a plain method that only uses logger + assessment attrs.
        orch = object.__new__(PaperTradingOrchestrator)
        orch._running = False
        orch._metrics = {}
        orch._redis = None
        orch._paper_kill_switch = None
        return orch

    @pytest.fixture
    def orchestrator(self):
        return self._make_orchestrator()

    @pytest.fixture
    def log_capture(self):
        with patch("execution.paper.orchestrator.logger") as mock_logger:
            yield mock_logger

    # -- All gates pass --

    def test_all_gates_pass(self, orchestrator, log_capture):
        """When assessment is approved with no violations, all gates pass."""
        assessment = _make_assessment(approved=True)
        signal = _make_signal(confidence=0.85)

        orchestrator._emit_gate_outcomes(assessment, signal, "corr-1")

        info_calls = [c for c in log_capture.info.call_args_list]
        gate_msgs = [str(c) for c in info_calls]

        # Should have exactly 3 gate_outcome calls
        assert len(gate_msgs) == 3

        # Risk gate: pass
        assert any("gate=risk" in m and "outcome=pass" in m for m in gate_msgs)

        # Confidence gate: pass
        assert any("gate=confidence" in m and "outcome=pass" in m for m in gate_msgs)

        # Signal quality gate: pass
        assert any(
            "gate=signal_quality" in m and "outcome=pass" in m for m in gate_msgs
        )

    # -- Risk gate fails --

    def test_risk_gate_fail(self, orchestrator, log_capture):
        """When assessment is rejected, risk gate fails."""
        violations = [
            RiskViolation(
                rule="position_size",
                severity=RiskSeverity.BLOCK.value,
                message="Position too large",
                current_value=0.15,
                limit_value=0.10,
            )
        ]
        assessment = _make_assessment(approved=False, violations=violations)
        signal = _make_signal(confidence=0.85)

        orchestrator._emit_gate_outcomes(assessment, signal, "corr-2")

        info_calls = [str(c) for c in log_capture.info.call_args_list]
        assert any("gate=risk" in m and "outcome=fail" in m for m in info_calls)

    # -- Confidence gate fails --

    def test_confidence_gate_fail(self, orchestrator, log_capture):
        """When confidence violation exists, confidence gate fails."""
        violations = [
            RiskViolation(
                rule="confidence",
                severity=RiskSeverity.BLOCK.value,
                message="Signal confidence 60.00% below minimum 75.00%",
                current_value=0.60,
                limit_value=0.75,
            )
        ]
        assessment = _make_assessment(approved=False, violations=violations)
        signal = _make_signal(confidence=0.60)

        orchestrator._emit_gate_outcomes(assessment, signal, "corr-3")

        info_calls = [str(c) for c in log_capture.info.call_args_list]

        # Confidence gate should be fail
        assert any("gate=confidence" in m and "outcome=fail" in m for m in info_calls)

    # -- Signal quality gate fails --

    def test_signal_quality_gate_fail(self, orchestrator, log_capture):
        """When blocking violations exist, signal_quality gate fails."""
        violations = [
            RiskViolation(
                rule="position_size",
                severity=RiskSeverity.BLOCK.value,
                message="Position too large",
                current_value=0.15,
                limit_value=0.10,
            ),
            RiskViolation(
                rule="confidence",
                severity=RiskSeverity.BLOCK.value,
                message="Low confidence",
                current_value=0.50,
                limit_value=0.75,
            ),
        ]
        assessment = _make_assessment(approved=False, violations=violations)
        signal = _make_signal(confidence=0.50)

        orchestrator._emit_gate_outcomes(assessment, signal, "corr-4")

        info_calls = [str(c) for c in log_capture.info.call_args_list]

        # Signal quality should be fail
        assert any(
            "gate=signal_quality" in m and "outcome=fail" in m for m in info_calls
        )

        # Should list blocking violations
        sq_msg = next(m for m in info_calls if "gate=signal_quality" in m)
        assert "confidence" in sq_msg
        assert "position_size" in sq_msg

    # -- Warning violations don't fail signal_quality --

    def test_warning_only_passes_signal_quality(self, orchestrator, log_capture):
        """Warning-level violations do not fail the signal_quality gate."""
        violations = [
            RiskViolation(
                rule="exposure",
                severity=RiskSeverity.WARNING.value,
                message="Portfolio exposure high",
                current_value=0.85,
                limit_value=0.80,
            )
        ]
        assessment = _make_assessment(approved=True, violations=violations)
        signal = _make_signal(confidence=0.85)

        orchestrator._emit_gate_outcomes(assessment, signal, "corr-5")

        info_calls = [str(c) for c in log_capture.info.call_args_list]

        # Risk gate: pass (approved=True)
        assert any("gate=risk" in m and "outcome=pass" in m for m in info_calls)

        # Signal quality: pass (no blocking violations)
        assert any(
            "gate=signal_quality" in m and "outcome=pass" in m for m in info_calls
        )

    # -- Correlation ID is included in all gate outcomes --

    def test_correlation_id_in_all_gates(self, orchestrator, log_capture):
        """Every gate_outcome log includes the correlation_id."""
        assessment = _make_assessment(approved=True)
        signal = _make_signal(confidence=0.85)

        orchestrator._emit_gate_outcomes(assessment, signal, "my-corr-id-42")

        info_calls = [str(c) for c in log_capture.info.call_args_list]
        gate_msgs = [m for m in info_calls if "gate_outcome" in m]

        assert len(gate_msgs) == 3
        for msg in gate_msgs:
            assert "correlation_id=my-corr-id-42" in msg

    # -- Confidence pass includes confidence value --

    def test_confidence_pass_includes_value(self, orchestrator, log_capture):
        """When confidence gate passes, the log includes the confidence value."""
        assessment = _make_assessment(approved=True)
        signal = _make_signal(confidence=0.92)

        orchestrator._emit_gate_outcomes(assessment, signal, "corr-6")

        info_calls = [str(c) for c in log_capture.info.call_args_list]
        conf_msg = next(m for m in info_calls if "gate=confidence" in m)

        assert "confidence=92.00%" in conf_msg
