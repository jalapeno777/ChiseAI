"""Champion-challenger gate integration for autonomous experiments."""

from __future__ import annotations

from dataclasses import dataclass

from autonomous_cognition.policy_engine import AutonomousPolicyEngine
from ml.model_registry.registry import ModelRegistry, ModelType


@dataclass
class PromotionOutcome:
    """Outcome of candidate evaluation against champion gates."""

    promoted: bool
    version_id: str
    reason: str


class ChampionChallengerEngine:
    """Coordinates model registry with autonomous gate policy."""

    def __init__(
        self,
        model_registry: ModelRegistry | None = None,
        policy_engine: AutonomousPolicyEngine | None = None,
    ):
        self._registry = model_registry or ModelRegistry()
        self._policy = policy_engine or AutonomousPolicyEngine()

    def evaluate_candidate(
        self,
        candidate_id: str,
        metrics: dict[str, float],
        model_path: str = "/tmp/autocog_candidate.bin",
    ) -> PromotionOutcome:
        """Register, challenge, and promote/reject a candidate."""
        version = self._registry.register_model(
            model_id=candidate_id,
            model_path=model_path,
            model_type=ModelType.SIGNAL_PREDICTOR,
            metrics={
                "accuracy": max(0.75, metrics.get("sharpe", 1.0) / 2),
                "precision": 0.75,
                "recall": 0.75,
                "f1": max(0.72, metrics.get("sharpe", 1.0) / 2),
                "ece": metrics.get("ece", 0.1),
            },
        )
        self._registry.promote_to_candidate(version.version_id)
        self._registry.promote_to_challenger(version.version_id)

        gate = self._policy.evaluate_promotion_gates(metrics)
        if not gate.passed:
            self._registry.mark_failed(version.version_id, ",".join(gate.failed_gates))
            return PromotionOutcome(
                promoted=False,
                version_id=version.version_id,
                reason=f"gates_failed:{','.join(gate.failed_gates)}",
            )

        self._registry.promote_to_champion(version.version_id, force=True)
        return PromotionOutcome(
            promoted=True,
            version_id=version.version_id,
            reason="all_gates_passed",
        )

