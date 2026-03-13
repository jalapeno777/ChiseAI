"""Full autonomous cognition cycle orchestration (Phases 1-5)."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from autonomous_cognition.beliefs.consistency_checker import BeliefConsistencyChecker
from autonomous_cognition.beliefs.explanation import explain_conflict, explain_revision
from autonomous_cognition.beliefs.models import Belief
from autonomous_cognition.beliefs.revision_engine import BeliefRevisionEngine
from autonomous_cognition.beliefs.store import BeliefStore
from autonomous_cognition.constitution_audit import ConstitutionAuditEngine
from autonomous_cognition.contracts import CycleResult
from autonomous_cognition.controller import AutonomousCognitionController
from autonomous_cognition.experiments.champion_challenger import (
    ChampionChallengerEngine,
)
from autonomous_cognition.experiments.hypothesis_generator import HypothesisGenerator
from autonomous_cognition.experiments.portfolio_policy_lab import PortfolioPolicyLab
from autonomous_cognition.metacog.autonomy_tuner import AutonomyTuner
from autonomous_cognition.runtime_integration import NeuroSymbolicRuntimeIntegrator
from autonomous_cognition.state_machine import AutonomousCycleStateMachine, CycleState
from governance.notifications.discord_notifier import DiscordNotifier

logger = logging.getLogger(__name__)


class AutonomousCognitionFullCycle:
    """Coordinates Phases 1-5 for autonomous cognition."""

    DEFAULT_CYCLE_DIR = "_bmad-output/autocog/cycles"

    def __init__(
        self,
        controller: AutonomousCognitionController | None = None,
        redis_client: Any | None = None,
    ):
        self._controller = controller or AutonomousCognitionController(redis_client=redis_client)
        self._belief_store = BeliefStore(redis_client=redis_client)
        self._checker = BeliefConsistencyChecker()
        self._revision_engine = BeliefRevisionEngine()
        self._hypothesis_generator = HypothesisGenerator()
        self._lab = PortfolioPolicyLab()
        self._champion_engine = ChampionChallengerEngine()
        self._runtime = NeuroSymbolicRuntimeIntegrator()
        self._tuner = AutonomyTuner()
        self._audit = ConstitutionAuditEngine()

    def run(self, notify_discord: bool = False) -> CycleResult:
        """Run full autonomous cognition cycle and persist artifact."""
        run_id = f"autocog-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        state_machine = AutonomousCycleStateMachine()
        result = CycleResult.create(run_id=run_id)
        actions: list[str] = []

        notifier = DiscordNotifier() if notify_discord else None
        notify_loop: asyncio.AbstractEventLoop | None = None
        if notifier is not None:
            notify_loop = asyncio.new_event_loop()
        try:
            state_machine.transition(CycleState.SELF_ASSESSING)
            actions.append("daily self assessment")
            assessment, assessment_path = self._controller.run_daily_self_assessment()
            result.self_assessment_status = assessment.status
            result.artifact_paths["self_assessment"] = str(assessment_path)

            if notifier and notify_loop:
                notify_loop.run_until_complete(
                    notifier.notify_self_assessment(
                        artifact=assessment,
                        artifact_path=str(assessment_path),
                    )
                )

            state_machine.transition(CycleState.BELIEF_CHECK)
            actions.append("belief consistency check")
            beliefs = self._seed_beliefs_from_assessment(assessment.findings)
            conflicts = self._checker.detect_conflicts(beliefs)
            result.belief_conflicts = len(conflicts)
            if conflicts and notifier and notify_loop:
                notify_loop.run_until_complete(
                    notifier.notify_autocog_event(
                        event_type="belief_conflict_detected",
                        severity="high",
                        summary=explain_conflict(conflicts[0]),
                        impact="Belief graph contradiction requires revision or review.",
                        top_metrics={"conflicts": len(conflicts)},
                        artifact_path=str(assessment_path),
                        run_id=run_id,
                        title="Belief Conflict Detected",
                        issue=(
                            "Two active beliefs disagree, so the system could reason "
                            "in inconsistent ways."
                        ),
                        intended_resolution=(
                            "Run belief revision to reconcile the contradiction using "
                            "higher-quality evidence."
                        ),
                        expected_improvement=(
                            "Keeps strategy reasoning internally consistent and "
                            "reduces contradictory decisions."
                        ),
                        outcome_status="in_progress",
                        evidence_reasoning=[
                            f"conflicts_detected={len(conflicts)}",
                            explain_conflict(conflicts[0]),
                        ],
                    )
                )

            revisions = self._revision_engine.apply_revisions(
                beliefs={b.belief_id: b for b in beliefs},
                conflicts=conflicts,
            )
            result.belief_revisions = len(revisions)
            if revisions and notifier and notify_loop:
                notify_loop.run_until_complete(
                    notifier.notify_autocog_event(
                        event_type="belief_revision_applied",
                        severity="medium",
                        summary=explain_revision(revisions[0]),
                        impact="Belief inconsistency resolved using evidence-weighted revision.",
                        top_metrics={"revisions": len(revisions)},
                        artifact_path=str(assessment_path),
                        run_id=run_id,
                        title="Belief Revision Applied",
                        issue=(
                            "Conflicting beliefs were found and needed a deterministic "
                            "resolution."
                        ),
                        intended_resolution=(
                            "Adjust belief confidence/state to preserve the strongest "
                            "evidence-backed interpretation."
                        ),
                        expected_improvement=(
                            "Reduces internal contradictions and improves downstream "
                            "decision reliability."
                        ),
                        outcome_status="success",
                        evidence_reasoning=[
                            f"revisions_applied={len(revisions)}",
                            explain_revision(revisions[0]),
                        ],
                    )
                )

            state_machine.transition(CycleState.IMPROVEMENT)
            actions.append("strategy portfolio improvement cycle")
            hypotheses = self._hypothesis_generator.generate(
                self_assessment=assessment.to_dict(),
                conflicts_count=len(conflicts),
            )
            result.experiments_run = len(hypotheses)
            promotions = 0
            rejections = 0
            for hypothesis in hypotheses:
                exp = self._lab.run(hypothesis)
                outcome = self._champion_engine.evaluate_candidate(
                    candidate_id=hypothesis.hypothesis_id,
                    metrics=exp.to_metrics(),
                )
                if outcome.promoted:
                    promotions += 1
                    if notifier and notify_loop:
                        notify_loop.run_until_complete(
                            notifier.notify_autocog_event(
                                event_type="improvement_promoted",
                                severity="low",
                                summary=f"Promoted {hypothesis.hypothesis_id}",
                                impact="Candidate passed promotion gates.",
                                top_metrics=exp.to_metrics(),
                                artifact_path=str(assessment_path),
                                run_id=run_id,
                                title="Improvement Candidate Promoted",
                                issue=(
                                    "A new candidate policy outperformed the current "
                                    "baseline under promotion gates."
                                ),
                                intended_resolution=(
                                    "Promote the validated candidate into the active "
                                    "improvement set."
                                ),
                                expected_improvement=(
                                    "Improves trading/portfolio behavior while staying "
                                    "inside risk controls."
                                ),
                                outcome_status="success",
                                evidence_reasoning=[
                                    f"candidate={hypothesis.hypothesis_id}",
                                    outcome.reason,
                                ],
                            )
                        )
                else:
                    rejections += 1
                    if notifier and notify_loop:
                        notify_loop.run_until_complete(
                            notifier.notify_autocog_event(
                                event_type="improvement_rejected",
                                severity="medium",
                                summary=f"Rejected {hypothesis.hypothesis_id}",
                                impact=outcome.reason,
                                top_metrics=exp.to_metrics(),
                                artifact_path=str(assessment_path),
                                run_id=run_id,
                                title="Improvement Candidate Rejected",
                                issue=(
                                    "A candidate policy failed one or more promotion "
                                    "criteria."
                                ),
                                intended_resolution=(
                                    "Reject the candidate and preserve the current "
                                    "champion policy."
                                ),
                                expected_improvement=(
                                    "Prevents degraded strategy performance from being "
                                    "deployed."
                                ),
                                outcome_status="failed",
                                evidence_reasoning=[
                                    f"candidate={hypothesis.hypothesis_id}",
                                    outcome.reason,
                                ],
                            )
                        )
            result.promotions = promotions
            result.rejections = rejections

            state_machine.transition(CycleState.RUNTIME_INTEGRATION)
            actions.append("neuro-symbolic runtime integration")
            runtime_result = self._runtime.run(mode="shadow")
            result.metrics["runtime_divergence_score"] = runtime_result.divergence_score
            result.metrics["runtime_non_regression_passed"] = runtime_result.passed_non_regression

            state_machine.transition(CycleState.TUNING)
            actions.append("autonomy tuning")
            result.autonomy_level_before = "bounded"
            tuning = self._tuner.tune(
                current_level=result.autonomy_level_before,
                ece=0.05 if promotions > 0 else 0.12,
                incident_count=0,
            )
            result.autonomy_level_after = tuning.new_level
            if notifier and notify_loop and tuning.new_level != tuning.previous_level:
                notify_loop.run_until_complete(
                    notifier.notify_autocog_event(
                        event_type="autonomy_level_changed",
                        severity="low",
                        summary=(
                            f"Autonomy level {tuning.previous_level} -> {tuning.new_level}"
                        ),
                        impact=tuning.reason,
                        top_metrics={"ece": 0.05 if promotions > 0 else 0.12},
                        artifact_path=str(assessment_path),
                        run_id=run_id,
                        title="Autonomy Level Updated",
                        issue=(
                            "Calibration and control signals indicated autonomy settings "
                            "needed adjustment."
                        ),
                        intended_resolution=(
                            "Apply tuner-recommended autonomy level while honoring "
                            "guardrails."
                        ),
                        expected_improvement=(
                            "Balances execution speed with safety and calibration quality."
                        ),
                        outcome_status="success",
                        evidence_reasoning=[
                            f"previous_level={tuning.previous_level}",
                            f"new_level={tuning.new_level}",
                            tuning.reason,
                        ],
                    )
                )

            state_machine.transition(CycleState.GOVERNANCE_AUDIT)
            actions.append("constitution audit")
            audit_result = self._audit.run(actions=actions)
            result.constitution_violations = len(audit_result.violations)
            result.metrics["constitution_critical"] = audit_result.critical_count
            if notifier and notify_loop and audit_result.violations:
                top = audit_result.violations[0]
                notify_loop.run_until_complete(
                    notifier.notify_autocog_event(
                        event_type="constitution_violation_detected",
                        severity="critical" if audit_result.critical_count else "high",
                        summary=f"Constitution violation: {top.rule_id}",
                        impact=top.description,
                        top_metrics={"violations": len(audit_result.violations)},
                        artifact_path=str(assessment_path),
                        run_id=run_id,
                        title="Constitution Violation Detected",
                        issue=(
                            "At least one action conflicted with project constitution "
                            "or safety policy."
                        ),
                        intended_resolution=(
                            "Escalate violation details and constrain unsafe autonomous "
                            "actions."
                        ),
                        expected_improvement=(
                            "Keeps the system aligned to safety rules and project scope."
                        ),
                        outcome_status="failed",
                        evidence_reasoning=[
                            f"critical_violations={audit_result.critical_count}",
                            f"total_violations={len(audit_result.violations)}",
                            f"top_rule={top.rule_id}",
                        ],
                    )
                )

            state_machine.transition(CycleState.COMPLETED)
            result.status = "completed"
        except Exception as e:
            logger.exception("Full autonomous cycle failed: %s", e)
            result.status = "failed"
            result.metrics["error"] = str(e)
            if notifier and notify_loop:
                notify_loop.run_until_complete(
                    notifier.notify_autocog_event(
                        event_type="autocog_cycle_completed",
                        severity="critical",
                        summary="Autonomous cycle failed",
                        impact=str(e),
                        top_metrics={"status": "failed"},
                        artifact_path=result.artifact_paths.get("self_assessment"),
                        run_id=run_id,
                        title="Autonomous Cycle Failed",
                        issue="The full cognition cycle terminated due to an exception.",
                        intended_resolution=(
                            "Stop execution safely, persist what is available, and alert "
                            "for investigation."
                        ),
                        expected_improvement=(
                            "Prevents silent failures and supports faster root-cause "
                            "recovery."
                        ),
                        outcome_status="failed",
                        evidence_reasoning=[f"exception={e}"],
                    )
                )
            raise
        finally:
            result.completed_at = datetime.now(UTC).isoformat()
            cycle_path = self._persist_cycle_result(result)
            result.artifact_paths["cycle"] = str(cycle_path)
            if notifier and notify_loop:
                notify_loop.run_until_complete(
                    notifier.notify_autocog_event(
                        event_type="autocog_cycle_completed",
                        severity="low" if result.status == "completed" else "critical",
                        summary=f"Autonomous cycle {result.status}",
                        impact=(
                            "Phases 1-5 executed end-to-end."
                            if result.status == "completed"
                            else "Cycle terminated with failure."
                        ),
                        top_metrics={
                            "belief_conflicts": result.belief_conflicts,
                            "belief_revisions": result.belief_revisions,
                            "experiments_run": result.experiments_run,
                            "promotions": result.promotions,
                            "rejections": result.rejections,
                        },
                        artifact_path=str(cycle_path),
                        run_id=run_id,
                        title="Autonomous Cycle Completed",
                        issue=(
                            "A scheduled end-to-end cognition maintenance and "
                            "improvement run was executed."
                        ),
                        intended_resolution=(
                            "Complete the full phase pipeline and persist decision "
                            "artifacts."
                        ),
                        expected_improvement=(
                            "Sustains continuous learning, calibration, and governance "
                            "visibility."
                        ),
                        outcome_status="success"
                        if result.status == "completed"
                        else "failed",
                        evidence_reasoning=[
                            f"status={result.status}",
                            f"belief_conflicts={result.belief_conflicts}",
                            f"belief_revisions={result.belief_revisions}",
                            f"experiments_run={result.experiments_run}",
                            f"promotions={result.promotions}",
                        ],
                    )
                )
                notify_loop.run_until_complete(notifier.close())
        if notify_loop:
            notify_loop.close()
        return result

    def _seed_beliefs_from_assessment(self, findings: list[str]) -> list[Belief]:
        """Seed beliefs from latest assessment findings."""
        beliefs = self._belief_store.list_active()
        if beliefs:
            return beliefs
        statement_a = findings[0] if findings else "System memory is healthy."
        statement_b = "System memory is outdated and no longer valid."
        seed = [
            Belief(
                belief_id="belief-memory-health",
                statement=statement_a,
                domain="memory",
                confidence=0.82,
                evidence_refs=["self_assessment_daily"],
                sources_quality_score=0.85,
            ),
            Belief(
                belief_id="belief-memory-outdated",
                statement=statement_b,
                domain="memory",
                confidence=0.64,
                evidence_refs=["legacy_runtime_warning"],
                sources_quality_score=0.62,
            ),
        ]
        for belief in seed:
            self._belief_store.put(belief)
        return seed

    def _persist_cycle_result(self, result: CycleResult) -> Path:
        """Write cycle artifact to disk."""
        out_dir = Path(self.DEFAULT_CYCLE_DIR)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{result.run_id}.json"
        out_path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
        return out_path
