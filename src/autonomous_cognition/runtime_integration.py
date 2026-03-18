"""Neuro-symbolic runtime integration (shadow/canary/full) for Phase 4."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class RuntimeIntegrationResult:
    """Outcome of neuro-symbolic runtime evaluation."""

    mode: str
    divergence_score: float
    influence_applied: bool
    passed_non_regression: bool
    details: dict[str, Any]


class NeuroSymbolicRuntimeIntegrator:
    """Runs shadow/canary/full integration checks with safe fallback."""

    def run(
        self,
        mode: str = "shadow",
        market_input: dict[str, Any] | None = None,
    ) -> RuntimeIntegrationResult:
        """Run neuro-symbolic integration in selected mode."""
        data = market_input or {"price": 100.0, "volume": 1000.0, "rsi": 55.0}
        try:
            from src.neuro_symbolic.orchestrator.orchestrator import (
                NeuroSymbolicOrchestrator,
            )

            orchestrator = NeuroSymbolicOrchestrator()
            result = orchestrator.process_signal(data)
            confidence = float(result.confidence)
            divergence = max(0.0, min(1.0, abs(0.5 - confidence)))

            influence = mode in {"canary", "full"} and confidence >= 0.55
            passed = divergence <= 0.35
            return RuntimeIntegrationResult(
                mode=mode,
                divergence_score=round(divergence, 3),
                influence_applied=influence,
                passed_non_regression=passed,
                details={
                    "prediction": result.prediction,
                    "confidence": confidence,
                    "components_used": result.components_used,
                },
            )
        except Exception as e:
            return RuntimeIntegrationResult(
                mode=mode,
                divergence_score=1.0,
                influence_applied=False,
                passed_non_regression=False,
                details={"error": str(e), "fallback": "legacy_signal_pipeline"},
            )
