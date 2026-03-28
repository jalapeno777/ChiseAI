"""Tests for Phase 4/5 runtime integration and autonomy tuning."""

from __future__ import annotations

from autonomous_cognition.autonomy_tuner import AutonomyTuner
from autonomous_cognition.constitution_audit import ConstitutionAuditEngine
from autonomous_cognition.runtime_integration import NeuroSymbolicRuntimeIntegrator


def test_runtime_integration_returns_result() -> None:
    """Runtime integrator should return a structured result even on fallback."""
    integrator = NeuroSymbolicRuntimeIntegrator()
    result = integrator.run(mode="shadow")
    assert result.mode == "shadow"
    assert "details" in result.__dict__


def test_autonomy_tuner_downgrades_on_high_ece() -> None:
    """Autonomy tuner should reduce level under poor calibration."""
    tuner = AutonomyTuner()
    decision = tuner.tune(current_level="assisted", ece=0.2, incident_count=0)
    assert decision.new_level in {"bounded", "supervised"}


def test_constitution_audit_detects_violations() -> None:
    """Constitution audit should detect rule-violating actions."""
    audit = ConstitutionAuditEngine()
    result = audit.run(actions=[{"type": "git_commit", "details": {"branch": "main"}}])
    assert len(result.violations) >= 1
