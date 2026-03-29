"""Full autonomous cognition cycle orchestration (Phases 1-5)."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from autonomous_cognition.action_executor import ActionExecutor  # noqa: F401
from autonomous_cognition.autonomy_tuner import AutonomyTuner
from autonomous_cognition.beliefs.consistency_checker import BeliefConsistencyChecker
from autonomous_cognition.beliefs.explanation import explain_conflict, explain_revision
from autonomous_cognition.beliefs.models import Belief, EvidenceRecord
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
from autonomous_cognition.metrics.skip_rate_monitor import SkipRateMonitor
from autonomous_cognition.runtime_integration import NeuroSymbolicRuntimeIntegrator
from autonomous_cognition.state_machine import AutonomousCycleStateMachine, CycleState
from governance.notifications.discord_notifier import DiscordNotifier

logger = logging.getLogger(__name__)


def _get_repo_root() -> Path:
    """Return the repository root directory.

    Resolves relative to the source file location, not CWD, ensuring
    Woodpecker CI (which may run from different CWDs) still finds paths.

    Resolution order:
    1. CHISEAI_REPO_ROOT environment variable (if set)
    2. Walk up from this file's location looking for pyproject.toml marker
    """
    # Priority: explicit env var
    env_root = os.environ.get("CHISEAI_REPO_ROOT")
    if env_root:
        root = Path(env_root).resolve()
        if root.exists():
            return root
        # Fall through to file-based detection if env var is invalid

    # Walk up from this file: src/autonomous_cognition/full_cycle.py
    # -> src/autonomous_cognition -> src -> <repo_root>
    current = Path(__file__).resolve()
    for _ in range(6):  # max 6 levels up to repo root
        current = current.parent
        if (current / "pyproject.toml").exists():
            return current
        if (current / "src").exists() and current.name != "src":
            # Continue walking up
            pass

    # Ultimate fallback: return parent of src/autonomous_cognition
    # This preserves legacy behavior (paths relative to where script is run)
    fallback = Path(__file__).resolve().parent.parent.parent
    logging.warning(
        "Could not determine repo root from file system; "
        "falling back to %s. Set CHISEAI_REPO_ROOT env var to silence this.",
        fallback,
    )
    return fallback


def _load_autocog_config() -> dict[str, Any]:
    """Load autocog configuration from YAML file."""
    repo_root = _get_repo_root()
    config_path = repo_root / "config/autocog.yaml"
    if not config_path.exists():
        logger.warning("Autocog config not found at %s, using defaults", config_path)
        return _default_autocog_config()
    try:
        import yaml

        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        return _merge_autocog_with_defaults(data)
    except Exception as e:
        logger.warning("Failed loading autocog config: %s", e)
        return _default_autocog_config()


def _default_autocog_config() -> dict[str, Any]:
    """Return default configuration."""
    return {
        "experiments": {
            "enabled": False,
            "max_experiments_per_cycle": 3,
            "safe_mode": True,
        },
        "qdrant": {
            "write_enabled": False,
            "collection_name": "ChiseAI",
            "vector_size": 384,
        },
        "metrics": {
            "skip_rate_alert_threshold": 0.20,
            "skip_rate_window_days": 7,
            "alert_on_high_skip_rate": True,
        },
        "safety": {
            "max_risk_level": "medium",
            "require_approval_for": ["high", "critical"],
        },
    }


def _merge_autocog_with_defaults(data: dict[str, Any]) -> dict[str, Any]:
    """Merge loaded config with defaults."""
    defaults = _default_autocog_config()
    for key, default_value in defaults.items():
        if key not in data:
            data[key] = default_value
        elif isinstance(default_value, dict) and isinstance(data[key], dict):
            for sub_key, sub_default in default_value.items():
                if sub_key not in data[key]:
                    data[key][sub_key] = sub_default
    return data


class AutonomousCognitionFullCycle:
    """Coordinates Phases 1-5 for autonomous cognition."""

    _REPO_ROOT = _get_repo_root()

    DEFAULT_CYCLE_DIR = str(_REPO_ROOT / "_bmad-output/autocog/cycles")
    DEFAULT_GOVERNANCE_STATE_PATH = str(
        _REPO_ROOT / "_bmad-output/autocog/governance_state.json"
    )
    DEFAULT_WEEKLY_META_AUDIT_DIR = str(_REPO_ROOT / "_bmad-output/autocog/meta_audit")
    CONFIG_PATH = _REPO_ROOT / "config/autocog.yaml"

    def __init__(
        self,
        controller: AutonomousCognitionController | None = None,
        redis_client: Any | None = None,
    ):
        self._controller = controller or AutonomousCognitionController(
            redis_client=redis_client
        )
        self._belief_store = BeliefStore(redis_client=redis_client)
        self._checker = BeliefConsistencyChecker()
        self._revision_engine = BeliefRevisionEngine()
        self._hypothesis_generator = HypothesisGenerator()
        self._lab = PortfolioPolicyLab()
        self._champion_engine = ChampionChallengerEngine()
        self._runtime = NeuroSymbolicRuntimeIntegrator()
        self._tuner = AutonomyTuner()
        self._audit = ConstitutionAuditEngine()
        self._config = _load_autocog_config()

    def run(self, notify_discord: bool = False, mode: str = "full") -> CycleResult:
        """Run autonomous cognition cycle and persist artifact.

        Modes:
        - full: Phases 1-5
        - belief_consistency: self-assessment + belief check/revision
        - improvement_cycle: self-assessment + strategy improvement
        - calibration/autonomy_tune: self-assessment + autonomy tuning
        - constitution_audit: self-assessment + constitution audit
        """
        allowed_modes = {
            "full",
            "belief_consistency",
            "improvement_cycle",
            "calibration",
            "autonomy_tune",
            "constitution_audit",
        }
        if mode not in allowed_modes:
            raise ValueError(f"Unsupported autocog mode: {mode}")

        run_self_assessment = True
        run_belief = mode in {"full", "belief_consistency"}
        run_improvement = mode in {"full", "improvement_cycle"}
        run_runtime = mode == "full"
        run_tuning = mode in {"full", "calibration", "autonomy_tune"}
        run_audit = mode in {"full", "constitution_audit"}

        run_id = f"autocog-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        state_machine = AutonomousCycleStateMachine()
        result = CycleResult.create(run_id=run_id)
        governance_state = self._load_governance_state()
        actions: list[str] = []
        assessment = None
        assessment_path: Path | None = None
        conflicts: list[Any] = []
        promotions = 0
        rejections = 0
        phase_durations: dict[str, float] = {}
        max_phase_seconds = 60.0
        max_cycle_seconds = 240.0
        cycle_started_monotonic = time.monotonic()
        trigger_context: dict[str, Any] = {}

        notifier = DiscordNotifier() if notify_discord else None
        notify_loop: asyncio.AbstractEventLoop | None = None
        if notifier is not None:
            notify_loop = asyncio.new_event_loop()
        try:
            state_machine.transition(CycleState.SELF_ASSESSING)
            if run_self_assessment:
                phase_started = time.monotonic()
                actions.append("daily self assessment")
                assessment, assessment_path = (
                    self._controller.run_daily_self_assessment()
                )
                result.self_assessment_status = assessment.status
                result.artifact_paths["self_assessment"] = str(assessment_path)
                trigger_context = self._build_trigger_context(assessment=assessment)
                result.metrics["trigger_context"] = trigger_context
                phase_durations["self_assessment_seconds"] = round(
                    time.monotonic() - phase_started, 3
                )
                if phase_durations["self_assessment_seconds"] > max_phase_seconds:
                    result.metrics["budget_warning_self_assessment"] = (
                        "phase_budget_exceeded"
                    )

                if notifier and notify_loop:
                    previous_score = self._get_previous_assessment_score()
                    notify_loop.run_until_complete(
                        notifier.notify_self_assessment(
                            artifact=assessment,
                            artifact_path=str(assessment_path),
                            previous_score=previous_score,
                        )
                    )

            state_machine.transition(CycleState.BELIEF_CHECK)
            if run_belief:
                phase_started = time.monotonic()
                actions.append("belief consistency check")
                findings = assessment.findings if assessment is not None else []
                beliefs = self._seed_beliefs_from_assessment(findings)
                belief_map = {b.belief_id: b for b in beliefs}
                should_run_belief, belief_skip_reason = self._should_run_belief_phase(
                    governance_state=governance_state,
                    trigger_context=trigger_context,
                    mode=mode,
                )
                if not should_run_belief:
                    result.metrics["belief_check_skipped"] = belief_skip_reason
                    conflicts = []
                    result.belief_conflicts = 0
                else:
                    conflicts = self._checker.detect_conflicts(beliefs)
                    result.belief_conflicts = len(conflicts)
                    conflicts = self._filter_conflicts_by_revision_cooldown(
                        governance_state=governance_state,
                        conflicts=conflicts,
                        trigger_context=trigger_context,
                    )
                    result.metrics["conflicts_after_cooldown"] = len(conflicts)
                if conflicts and notifier and notify_loop:
                    notify_loop.run_until_complete(
                        notifier.notify_autocog_event(
                            event_type="belief_conflict_detected",
                            severity="high",
                            summary=explain_conflict(conflicts[0]),
                            impact="Belief graph contradiction requires revision or review.",
                            top_metrics={"conflicts": len(conflicts)},
                            artifact_path=(
                                str(assessment_path) if assessment_path else None
                            ),
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

                evidence_index = self._build_belief_evidence_index(
                    assessment=assessment
                )
                result.metrics["belief_evidence_summary"] = (
                    self._summarize_belief_evidence(evidence_index)
                )
                revisions = (
                    self._revision_engine.apply_revisions(
                        beliefs=belief_map,
                        conflicts=conflicts,
                        evidence_index=evidence_index,
                    )
                    if should_run_belief
                    else []
                )
                result.belief_revisions = len(revisions)
                if self._revision_engine.last_support_scores:
                    result.metrics["belief_support_scores"] = (
                        self._revision_engine.last_support_scores
                    )
                if self._revision_engine.last_blocked_revisions:
                    result.metrics["belief_revision_blocks"] = (
                        self._revision_engine.last_blocked_revisions[:10]
                    )
                revision_artifact_path: Path | None = None
                revision_decision_packet: dict[str, Any] | None = None
                if revisions:
                    revision_details = [
                        self._revision_detail_payload(revision, belief_map)
                        for revision in revisions[:10]
                    ]
                    revision_decision_packet = self._build_revision_decision_packet(
                        revision=revisions[0],
                        beliefs=belief_map,
                        conflicts=conflicts,
                        evidence_index=evidence_index,
                    )
                    result.metrics["belief_revision_details"] = revision_details
                    result.metrics["belief_revision_decision_packet"] = (
                        revision_decision_packet
                    )
                    revision_artifact_path = self._persist_belief_revisions(
                        run_id=run_id,
                        revision_details=revision_details,
                        decision_packet=revision_decision_packet,
                    )
                    result.artifact_paths["belief_revisions"] = str(
                        revision_artifact_path
                    )
                elif (
                    self._revision_engine.last_blocked_revisions
                    and notifier
                    and notify_loop
                ):
                    first_block = self._revision_engine.last_blocked_revisions[0]
                    manual_blocks = [
                        block
                        for block in self._revision_engine.last_blocked_revisions
                        if str(block.get("reason", "")).startswith(
                            "manual_approval_required"
                        )
                    ]
                    if manual_blocks:
                        approval_packet_path = self._persist_manual_approval_packet(
                            run_id=run_id,
                            blocked_revisions=manual_blocks,
                        )
                        result.artifact_paths["manual_approval_packet"] = str(
                            approval_packet_path
                        )
                        result.metrics["manual_approval_required"] = True
                        notify_loop.run_until_complete(
                            notifier.notify_autocog_event(
                                event_type="human_approval_required",
                                severity="high",
                                summary="High-impact belief revision requires human approval.",
                                impact=(
                                    "Revision withheld until manual approval decision is recorded."
                                ),
                                top_metrics={"pending_approvals": len(manual_blocks)},
                                artifact_path=str(approval_packet_path),
                                run_id=run_id,
                                title="Human Approval Required",
                                issue=(
                                    "A high-impact belief change exceeded autonomous approval "
                                    "thresholds."
                                ),
                                intended_resolution=(
                                    "Submit approval packet for manual go/no-go decision."
                                ),
                                expected_improvement=(
                                    "Prevents unsafe high-impact autonomous changes."
                                ),
                                outcome_status="in_progress",
                                evidence_reasoning=[
                                    f"manual_approval_blocks={len(manual_blocks)}",
                                    f"top_reason={manual_blocks[0].get('reason', 'unknown')}",
                                ],
                            )
                        )
                    notify_loop.run_until_complete(
                        notifier.notify_autocog_event(
                            event_type="belief_revision_blocked",
                            severity="medium",
                            summary=(
                                "Belief conflict remained unresolved because "
                                "evidence/support gates blocked revision."
                            ),
                            impact=(
                                "Belief state preserved until stronger supporting "
                                "evidence is available."
                            ),
                            top_metrics={
                                "blocked_revisions": len(
                                    self._revision_engine.last_blocked_revisions
                                )
                            },
                            artifact_path=(
                                str(assessment_path) if assessment_path else None
                            ),
                            run_id=run_id,
                            title="Belief Revision Blocked",
                            issue=(
                                "A contradiction was detected but the proposed winner "
                                "did not meet evidence confidence policy gates."
                            ),
                            intended_resolution=(
                                "Hold current beliefs and request stronger evidence "
                                "before applying any supersession."
                            ),
                            expected_improvement=(
                                "Prevents ungrounded self-modification and lowers "
                                "rollback risk."
                            ),
                            outcome_status="failed",
                            evidence_reasoning=[
                                "revisions_applied=0",
                                (
                                    "blocked_revisions="
                                    f"{len(self._revision_engine.last_blocked_revisions)}"
                                ),
                                f"block_reason={first_block.get('reason', 'unknown')}",
                                (
                                    "winner="
                                    f"{first_block.get('winner_belief_id', 'unknown')}"
                                ),
                                (
                                    "loser="
                                    f"{first_block.get('loser_belief_id', 'unknown')}"
                                ),
                            ],
                        )
                    )
                if revisions and notifier and notify_loop:
                    first_revision = revisions[0]
                    old_belief = belief_map.get(first_revision.old_belief_id)
                    new_belief = belief_map.get(first_revision.new_belief_id)
                    notify_loop.run_until_complete(
                        notifier.notify_autocog_event(
                            event_type="belief_revision_applied",
                            severity="medium",
                            summary=explain_revision(first_revision),
                            impact="Belief inconsistency resolved using evidence-weighted revision.",
                            top_metrics={"revisions": len(revisions)},
                            artifact_path=(
                                str(revision_artifact_path)
                                if revision_artifact_path is not None
                                else (str(assessment_path) if assessment_path else None)
                            ),
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
                                f"revision_id={first_revision.revision_id}",
                                (
                                    f"replaced={first_revision.old_belief_id}"
                                    f"->{first_revision.new_belief_id}"
                                ),
                                (
                                    f"confidence={first_revision.confidence_before:.2f}"
                                    f"->{first_revision.confidence_after:.2f}"
                                ),
                                f"reason={first_revision.reason}",
                                (
                                    "evidence_refs="
                                    + ",".join(first_revision.evidence_refs)
                                    if first_revision.evidence_refs
                                    else "evidence_refs=none"
                                ),
                                (
                                    "old_statement="
                                    + self._truncate_text(old_belief.statement)
                                    if old_belief is not None
                                    else "old_statement=unknown"
                                ),
                                (
                                    "new_statement="
                                    + self._truncate_text(new_belief.statement)
                                    if new_belief is not None
                                    else "new_statement=unknown"
                                ),
                            ],
                            decision_packet=revision_decision_packet,
                        )
                    )
                self._update_belief_lifecycle_state(
                    governance_state=governance_state,
                    beliefs=belief_map,
                    revisions=revisions,
                    blocked_revisions=self._revision_engine.last_blocked_revisions,
                    trigger_context=trigger_context,
                )
                self._record_revision_cooldowns(
                    governance_state=governance_state,
                    revisions=revisions,
                )
                phase_durations["belief_check_seconds"] = round(
                    time.monotonic() - phase_started, 3
                )
                if phase_durations["belief_check_seconds"] > max_phase_seconds:
                    result.metrics["budget_warning_belief_check"] = (
                        "phase_budget_exceeded"
                    )

            state_machine.transition(CycleState.IMPROVEMENT)
            if run_improvement:
                phase_started = time.monotonic()
                actions.append("strategy portfolio improvement cycle")
                assessment_payload = (
                    assessment.to_dict() if assessment is not None else {}
                )
                hypotheses = self._hypothesis_generator.generate(
                    self_assessment=assessment_payload,
                    conflicts_count=len(conflicts),
                )
                eligible_hypotheses: list[Any] = []
                evidence_signature = self._build_candidate_evidence_signature(
                    assessment=assessment,
                    conflicts_count=len(conflicts),
                )
                skipped_candidates: list[dict[str, Any]] = []
                for hypothesis in hypotheses:
                    eligible, reason = self._is_candidate_eligible(
                        governance_state=governance_state,
                        hypothesis=hypothesis,
                        evidence_signature=evidence_signature,
                        trigger_context=trigger_context,
                    )
                    if eligible:
                        eligible_hypotheses.append(hypothesis)
                    else:
                        skipped_candidates.append(
                            {
                                "candidate": hypothesis.hypothesis_id,
                                "reason": reason,
                            }
                        )
                max_experiments = self._config.get("experiments", {}).get(
                    "max_experiments_per_cycle", 3
                )
                hypotheses = eligible_hypotheses[:max_experiments]
                if len(eligible_hypotheses) > max_experiments:
                    skipped_candidates.append(
                        {
                            "candidate": "additional_candidates",
                            "reason": (
                                "cost_budget_exceeded:"
                                f"max_experiments={max_experiments}"
                            ),
                        }
                    )
                result.metrics["candidate_skips"] = skipped_candidates
                result.experiments_run = len(hypotheses)
                for hypothesis in hypotheses:
                    exp = self._lab.run(hypothesis)
                    if self._is_uncertain_candidate_result(exp.to_metrics()):
                        rejections += 1
                        self._record_candidate_outcome(
                            governance_state=governance_state,
                            hypothesis=hypothesis,
                            outcome="rejected",
                            reason="insufficient_certainty",
                            evidence_signature=evidence_signature,
                        )
                        if notifier and notify_loop:
                            notify_loop.run_until_complete(
                                notifier.notify_autocog_event(
                                    event_type="improvement_rejected",
                                    severity="medium",
                                    summary=f"Rejected {hypothesis.hypothesis_id}",
                                    impact=(
                                        "Candidate result uncertainty exceeded threshold; "
                                        "decision deferred."
                                    ),
                                    top_metrics=exp.to_metrics(),
                                    artifact_path=(
                                        str(assessment_path)
                                        if assessment_path
                                        else None
                                    ),
                                    run_id=run_id,
                                    title="Improvement Candidate Rejected",
                                    issue=(
                                        "Candidate metrics were too close to decision "
                                        "thresholds to be considered reliable."
                                    ),
                                    intended_resolution=(
                                        "Reject for now and wait for stronger "
                                        "evidence/clearer margin."
                                    ),
                                    expected_improvement=(
                                        "Avoids unstable policy churn from noisy signals."
                                    ),
                                    outcome_status="failed",
                                    evidence_reasoning=[
                                        f"candidate={hypothesis.hypothesis_id}",
                                        "reason=insufficient_certainty",
                                    ],
                                )
                            )
                        continue
                    outcome = self._champion_engine.evaluate_candidate(
                        candidate_id=hypothesis.hypothesis_id,
                        metrics=exp.to_metrics(),
                    )
                    if outcome.promoted:
                        promotions += 1
                        self._record_candidate_outcome(
                            governance_state=governance_state,
                            hypothesis=hypothesis,
                            outcome="promoted",
                            reason=outcome.reason,
                            evidence_signature=evidence_signature,
                            version_id=outcome.version_id,
                        )
                        if notifier and notify_loop:
                            notify_loop.run_until_complete(
                                notifier.notify_autocog_event(
                                    event_type="improvement_promoted",
                                    severity="low",
                                    summary=f"Promoted {hypothesis.hypothesis_id}",
                                    impact="Candidate passed promotion gates.",
                                    top_metrics=exp.to_metrics(),
                                    artifact_path=(
                                        str(assessment_path)
                                        if assessment_path
                                        else None
                                    ),
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
                        self._record_candidate_outcome(
                            governance_state=governance_state,
                            hypothesis=hypothesis,
                            outcome="rejected",
                            reason=outcome.reason,
                            evidence_signature=evidence_signature,
                            version_id=outcome.version_id,
                        )
                        if notifier and notify_loop:
                            notify_loop.run_until_complete(
                                notifier.notify_autocog_event(
                                    event_type="improvement_rejected",
                                    severity="medium",
                                    summary=f"Rejected {hypothesis.hypothesis_id}",
                                    impact=outcome.reason,
                                    top_metrics=exp.to_metrics(),
                                    artifact_path=(
                                        str(assessment_path)
                                        if assessment_path
                                        else None
                                    ),
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
                phase_durations["improvement_seconds"] = round(
                    time.monotonic() - phase_started, 3
                )
                if phase_durations["improvement_seconds"] > max_phase_seconds:
                    result.metrics["budget_warning_improvement"] = (
                        "phase_budget_exceeded"
                    )
            result.promotions = promotions
            result.rejections = rejections

            state_machine.transition(CycleState.RUNTIME_INTEGRATION)
            if run_runtime:
                phase_started = time.monotonic()
                actions.append("neuro-symbolic runtime integration")
                runtime_result = self._runtime.run(mode="shadow")
                result.metrics["runtime_divergence_score"] = (
                    runtime_result.divergence_score
                )
                result.metrics["runtime_non_regression_passed"] = (
                    runtime_result.passed_non_regression
                )
                phase_durations["runtime_integration_seconds"] = round(
                    time.monotonic() - phase_started, 3
                )

            state_machine.transition(CycleState.TUNING)
            if run_tuning:
                phase_started = time.monotonic()
                actions.append("autonomy tuning")
                result.autonomy_level_before = "bounded"
                tuning = self._tuner.tune(
                    current_level=result.autonomy_level_before,
                    ece=0.05 if promotions > 0 else 0.12,
                    incident_count=0,
                )
                result.autonomy_level_after = tuning.new_level
                if (
                    notifier
                    and notify_loop
                    and tuning.new_level != tuning.previous_level
                ):
                    notify_loop.run_until_complete(
                        notifier.notify_autocog_event(
                            event_type="autonomy_level_changed",
                            severity="low",
                            summary=(
                                f"Autonomy level {tuning.previous_level} -> {tuning.new_level}"
                            ),
                            impact=tuning.reason,
                            top_metrics={"ece": 0.05 if promotions > 0 else 0.12},
                            artifact_path=(
                                str(assessment_path) if assessment_path else None
                            ),
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
                phase_durations["tuning_seconds"] = round(
                    time.monotonic() - phase_started, 3
                )

            state_machine.transition(CycleState.GOVERNANCE_AUDIT)
            if run_audit:
                phase_started = time.monotonic()
                actions.append("constitution audit")
                audit_result = self._audit.run(actions=actions)
                result.constitution_violations = len(audit_result.violations)
                result.metrics["constitution_critical"] = audit_result.critical_count
                if notifier and notify_loop and audit_result.violations:
                    top = audit_result.violations[0]
                    notify_loop.run_until_complete(
                        notifier.notify_autocog_event(
                            event_type="constitution_violation_detected",
                            severity=(
                                "critical" if audit_result.critical_count else "high"
                            ),
                            summary=f"Constitution violation: {top.rule_id}",
                            impact=top.description,
                            top_metrics={"violations": len(audit_result.violations)},
                            artifact_path=(
                                str(assessment_path) if assessment_path else None
                            ),
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
                phase_durations["governance_audit_seconds"] = round(
                    time.monotonic() - phase_started, 3
                )

            verification_actions = self._process_pending_verifications(
                governance_state=governance_state,
                result=result,
            )
            if verification_actions:
                result.metrics["post_change_verifications"] = verification_actions

            rollback_actions = self._process_incident_linked_rollbacks(
                governance_state=governance_state,
                result=result,
            )
            if rollback_actions:
                result.metrics["incident_rollbacks"] = rollback_actions

            result.metrics["phase_durations"] = phase_durations
            result.metrics["cycle_elapsed_seconds"] = round(
                time.monotonic() - cycle_started_monotonic, 3
            )
            if result.metrics["cycle_elapsed_seconds"] > max_cycle_seconds:
                result.metrics["budget_warning_cycle"] = "cycle_budget_exceeded"

            weekly_meta_audit_path = self._persist_weekly_meta_audit()
            result.artifact_paths["meta_audit"] = str(weekly_meta_audit_path)

            # Check skip rate and record metric
            skip_monitor = SkipRateMonitor(
                window_days=self._config.get("metrics", {}).get(
                    "skip_rate_window_days", 7
                ),
                alert_threshold=self._config.get("metrics", {}).get(
                    "skip_rate_alert_threshold", 0.20
                ),
                cycles_dir=self.DEFAULT_CYCLE_DIR,
            )
            skip_rate_result = skip_monitor.check_skip_rate()
            result.metrics["skip_rate_check"] = skip_rate_result

            # Record skip metric for this run
            total_candidates = result.experiments_run + len(
                result.metrics.get("candidate_skips", [])
            )
            skipped_candidates = len(result.metrics.get("candidate_skips", []))
            skip_monitor.record_skip_metric(
                run_id, total_candidates, skipped_candidates
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
            self._save_governance_state(governance_state)
            if notifier and notify_loop:
                # Check if notification should be suppressed via hash-based deduplication
                should_notify = notifier.should_notify_for_cycle_event(
                    mode=mode,
                    errors=result.errors if hasattr(result, "errors") else None,
                    actions_taken=len(actions),
                    score=assessment.overall_score if assessment else None,
                    previous_score=self._get_previous_assessment_score(),
                    score_drift_threshold=0.01,
                    metrics=result.metrics if hasattr(result, "metrics") else None,
                )
                if should_notify:
                    notify_loop.run_until_complete(
                        notifier.notify_autocog_event(
                            event_type="autocog_cycle_completed",
                            severity=(
                                "low" if result.status == "completed" else "critical"
                            ),
                            summary=f"Autonomous cycle {result.status}",
                            impact=(
                                "Mode pipeline executed successfully."
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
                            outcome_status=(
                                "success" if result.status == "completed" else "failed"
                            ),
                            evidence_reasoning=[
                                f"mode={mode}",
                                f"status={result.status}",
                                f"belief_conflicts={result.belief_conflicts}",
                                f"belief_revisions={result.belief_revisions}",
                                f"experiments_run={result.experiments_run}",
                                f"promotions={result.promotions}",
                            ],
                        )
                    )
                else:
                    logger.info(
                        "Autocog cycle notification suppressed due to hash match "
                        "(mode=%s, status=%s)",
                        mode,
                        result.status,
                    )
                    result.metrics["notifications_suppressed"] = (
                        result.metrics.get("notifications_suppressed", 0) + 1
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
                evidence_refs=[
                    "self_assessment_daily",
                    "self_assessment_history",
                    "runtime_health_window",
                    "governance_stability_window",
                ],
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
            if not self._belief_store.put(belief):
                logger.warning(
                    "[FULL_CYCLE] Failed to persist seed belief %s", belief.belief_id
                )
        return seed

    def _build_belief_evidence_index(
        self,
        *,
        assessment: Any | None,
    ) -> dict[str, list[EvidenceRecord]]:
        """Construct evidence index used by belief support scoring."""
        index: dict[str, list[EvidenceRecord]] = {}

        if assessment is not None:
            summary = (
                f"status={assessment.status} score={assessment.overall_score} "
                f"findings={'; '.join(assessment.findings[:2])}"
            )
            index["self_assessment_daily"] = [
                EvidenceRecord(
                    evidence_id="self_assessment_daily",
                    source="autonomous_self_assessment",
                    source_family="self_assessment_current",
                    is_llm_judgment=True,
                    timestamp=assessment.created_at,
                    reliability=0.85,
                    summary=summary,
                    metrics={
                        "overall_score": assessment.overall_score,
                        "status": assessment.status,
                        "confirmed_runs": 1,
                        "causal_strength": 0.55,
                    },
                )
            ]

        assessment_window = self._recent_self_assessment_window(max_items=5)
        if assessment_window:
            ok_count = sum(
                1 for item in assessment_window if item.get("status") == "ok"
            )
            total = len(assessment_window)
            history_conf = ok_count / total if total else 0.0
            index["self_assessment_history"] = [
                EvidenceRecord(
                    evidence_id="self_assessment_history",
                    source="autonomous_self_assessment_window",
                    source_family="self_assessment_history",
                    is_llm_judgment=True,
                    timestamp=datetime.now(UTC).isoformat(),
                    reliability=round(0.55 + 0.35 * history_conf, 3),
                    summary=(
                        f"Recent self-assessment trend ok_count={ok_count}/{total}"
                    ),
                    metrics={
                        "ok_count": ok_count,
                        "window_size": total,
                        "confirmed_runs": total,
                        "causal_strength": 0.4,
                    },
                )
            ]

        cycle_window = self._recent_cycle_window(max_items=10)
        if cycle_window:
            runtime_samples = [
                c.get("metrics", {}).get("runtime_non_regression_passed")
                for c in cycle_window
                if c.get("metrics", {}).get("runtime_non_regression_passed") is not None
            ]
            if runtime_samples:
                runtime_passes = sum(1 for s in runtime_samples if bool(s))
                total_runtime = len(runtime_samples)
                runtime_conf = runtime_passes / total_runtime
                index["runtime_health_window"] = [
                    EvidenceRecord(
                        evidence_id="runtime_health_window",
                        source="autocog_cycle_metrics",
                        source_family="runtime_telemetry",
                        is_llm_judgment=False,
                        timestamp=datetime.now(UTC).isoformat(),
                        reliability=round(0.5 + 0.45 * runtime_conf, 3),
                        summary=(
                            "Runtime non-regression trend "
                            f"passed={runtime_passes}/{total_runtime}"
                        ),
                        metrics={
                            "runtime_passes": runtime_passes,
                            "window_size": total_runtime,
                            "confirmed_runs": total_runtime,
                            "causal_strength": 0.8,
                        },
                    )
                ]

            gov_samples = [
                c.get("constitution_violations")
                for c in cycle_window
                if c.get("constitution_violations") is not None
            ]
            if gov_samples:
                zero_violations = sum(1 for v in gov_samples if int(v) == 0)
                total_gov = len(gov_samples)
                gov_conf = zero_violations / total_gov
                index["governance_stability_window"] = [
                    EvidenceRecord(
                        evidence_id="governance_stability_window",
                        source="autocog_cycle_governance_metrics",
                        source_family="governance_metrics",
                        is_llm_judgment=False,
                        timestamp=datetime.now(UTC).isoformat(),
                        reliability=round(0.5 + 0.45 * gov_conf, 3),
                        summary=(
                            "Constitution violation trend "
                            f"zero_violations={zero_violations}/{total_gov}"
                        ),
                        metrics={
                            "zero_violations": zero_violations,
                            "window_size": total_gov,
                            "confirmed_runs": total_gov,
                            "causal_strength": 0.75,
                        },
                    )
                ]
        return index

    def _get_previous_assessment_score(self) -> float | None:
        """Retrieve overall_score from the previous assessment run via Redis.

        Returns:
            The ``overall_score`` from the previous assessment stored in Redis,
            or None if no prior assessment exists or Redis is unavailable.

        Uses the same Redis key as AutonomousCognitionController
        (bmad:chiseai:autocog:self_assessment:latest) for consistency.
        """
        return self._controller._get_previous_score()

    def _recent_self_assessment_window(
        self, max_items: int = 5
    ) -> list[dict[str, Any]]:
        """Load latest self-assessment artifacts for trend evidence."""
        directory = self._REPO_ROOT / "docs/governance/self_assessments"
        if not directory.exists():
            return []
        files = sorted(
            directory.glob("self_assessment_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        snapshots: list[dict[str, Any]] = []
        for path in files[:max_items]:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            snapshots.append(
                {
                    "assessment_id": payload.get("assessment_id"),
                    "status": payload.get("status"),
                    "created_at": payload.get("created_at"),
                }
            )
        return snapshots

    def _recent_cycle_window(self, max_items: int = 10) -> list[dict[str, Any]]:
        """Load latest cycle artifacts for non-LLM evidence trends."""
        directory = Path(self.DEFAULT_CYCLE_DIR)
        if not directory.exists():
            return []
        files = sorted(
            directory.glob("autocog-*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        snapshots: list[dict[str, Any]] = []
        for path in files[:max_items]:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            snapshots.append(
                {
                    "run_id": payload.get("run_id"),
                    "started_at": payload.get("started_at"),
                    "metrics": payload.get("metrics", {}),
                    "promotions": payload.get("promotions", 0),
                    "rejections": payload.get("rejections", 0),
                    "belief_revisions": payload.get("belief_revisions", 0),
                    "constitution_violations": payload.get("constitution_violations"),
                    "status": payload.get("status"),
                }
            )
        return snapshots

    @staticmethod
    def _summarize_belief_evidence(
        evidence_index: dict[str, list[EvidenceRecord]],
    ) -> dict[str, Any]:
        """Summarize evidence index for audit visibility in cycle metrics."""
        all_records = [
            record for records in evidence_index.values() for record in records
        ]
        families = sorted(
            {record.source_family for record in all_records if record.source_family}
        )
        non_llm = sorted(
            {
                record.source_family
                for record in all_records
                if record.source_family and not record.is_llm_judgment
            }
        )
        return {
            "evidence_refs": sorted(evidence_index.keys()),
            "record_count": len(all_records),
            "distinct_source_families": len(families),
            "non_llm_source_families": len(non_llm),
            "source_families": families,
            "non_llm_families": non_llm,
            "max_temporal_confirmations": max(
                (
                    int(record.metrics.get("confirmed_runs", 1))
                    for record in all_records
                    if isinstance(record.metrics.get("confirmed_runs", 1), int)
                ),
                default=0,
            ),
        }

    def _load_governance_state(self) -> dict[str, Any]:
        """Load autonomy governance state used for cadence and cooldown controls."""
        path = Path(self.DEFAULT_GOVERNANCE_STATE_PATH)
        if not path.exists():
            return {
                "schema_version": "1.0",
                "updated_at": datetime.now(UTC).isoformat(),
                "candidate_registry": {},
                "belief_registry": {},
                "revision_registry": {},
                "pending_verifications": [],
                "rollbacks": [],
            }
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                payload.setdefault("candidate_registry", {})
                payload.setdefault("belief_registry", {})
                payload.setdefault("revision_registry", {})
                payload.setdefault("pending_verifications", [])
                payload.setdefault("rollbacks", [])
                return payload
        except (json.JSONDecodeError, OSError):
            pass
        return {
            "schema_version": "1.0",
            "updated_at": datetime.now(UTC).isoformat(),
            "candidate_registry": {},
            "belief_registry": {},
            "revision_registry": {},
            "pending_verifications": [],
            "rollbacks": [],
        }

    def _save_governance_state(self, state: dict[str, Any]) -> None:
        """Persist autonomy governance state."""
        path = Path(self.DEFAULT_GOVERNANCE_STATE_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        state["updated_at"] = datetime.now(UTC).isoformat()
        path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    @staticmethod
    def _build_trigger_context(assessment: Any | None) -> dict[str, Any]:
        """Build trigger context used for cadence and re-check activation."""
        if assessment is None:
            return {"has_incident_trigger": False}
        infra_down = any(
            phrase in finding.lower()
            for finding in getattr(assessment, "findings", [])
            for phrase in ("unavailable", "failed", "disabled")
        )
        score = float(getattr(assessment, "overall_score", 0.0))
        status = str(getattr(assessment, "status", "unknown")).lower()
        incident = status in {"degraded", "failed"} or score < 0.75 or infra_down
        return {
            "assessment_status": status,
            "assessment_score": score,
            "infra_trigger": infra_down,
            "has_incident_trigger": incident,
        }

    def _should_run_belief_phase(
        self,
        *,
        governance_state: dict[str, Any],
        trigger_context: dict[str, Any],
        mode: str,
    ) -> tuple[bool, str]:
        """Decide whether to run full belief re-check or defer by cadence."""
        if mode == "belief_consistency":
            return True, "explicit_mode"
        if trigger_context.get("has_incident_trigger"):
            return True, "incident_trigger"
        registry = governance_state.setdefault("belief_registry", {})
        global_state = registry.setdefault(
            "__global__",
            {
                "lifecycle_state": "active",
                "next_check_after": datetime.now(UTC).isoformat(),
                "stability_runs": 0,
            },
        )
        due_at = datetime.fromisoformat(
            global_state["next_check_after"].replace("Z", "+00:00")
        )
        if datetime.now(UTC) >= due_at:
            return True, "scheduled_recheck"
        return False, "cadence_deferred"

    def _update_belief_lifecycle_state(
        self,
        *,
        governance_state: dict[str, Any],
        beliefs: dict[str, Belief],
        revisions: list[Any],
        blocked_revisions: list[dict[str, Any]],
        trigger_context: dict[str, Any],
    ) -> None:
        """Update belief lifecycle to avoid hourly full re-check churn."""
        registry = governance_state.setdefault("belief_registry", {})
        global_state = registry.setdefault(
            "__global__",
            {
                "lifecycle_state": "active",
                "next_check_after": datetime.now(UTC).isoformat(),
                "stability_runs": 0,
            },
        )
        if trigger_context.get("has_incident_trigger"):
            global_state["lifecycle_state"] = "invalidated"
            global_state["stability_runs"] = 0
            global_state["next_check_after"] = datetime.now(UTC).isoformat()
            return
        if revisions:
            global_state["lifecycle_state"] = "active"
            global_state["stability_runs"] = 0
            global_state["next_check_after"] = (
                datetime.now(UTC) + timedelta(hours=4)
            ).isoformat()
        elif blocked_revisions:
            global_state["lifecycle_state"] = "active"
            global_state["stability_runs"] = 0
            global_state["next_check_after"] = (
                datetime.now(UTC) + timedelta(hours=2)
            ).isoformat()
        else:
            stability = int(global_state.get("stability_runs", 0)) + 1
            global_state["stability_runs"] = stability
            if stability >= 12:
                global_state["lifecycle_state"] = "dormant"
                global_state["next_check_after"] = (
                    datetime.now(UTC) + timedelta(days=1)
                ).isoformat()
            elif stability >= 4:
                global_state["lifecycle_state"] = "stabilized"
                global_state["next_check_after"] = (
                    datetime.now(UTC) + timedelta(hours=6)
                ).isoformat()
            else:
                global_state["lifecycle_state"] = "active"
                global_state["next_check_after"] = (
                    datetime.now(UTC) + timedelta(hours=1)
                ).isoformat()
        for belief_id, belief in beliefs.items():
            registry[belief_id] = {
                "status": belief.status,
                "confidence": belief.confidence,
                "updated_at": belief.updated_at,
            }

    @staticmethod
    def _build_candidate_evidence_signature(
        *,
        assessment: Any | None,
        conflicts_count: int,
    ) -> str:
        """Fingerprint candidate context to detect novel vs repeated retries."""
        findings = getattr(assessment, "findings", []) if assessment is not None else []
        raw = {
            "assessment_status": (
                getattr(assessment, "status", "unknown")
                if assessment is not None
                else "unknown"
            ),
            "assessment_score": (
                round(float(getattr(assessment, "overall_score", 0.0)), 3)
                if assessment is not None
                else 0.0
            ),
            "findings": findings[:3],
            "conflicts_count": conflicts_count,
        }
        return hashlib.sha256(
            json.dumps(raw, sort_keys=True).encode("utf-8")
        ).hexdigest()[:16]

    def _is_candidate_eligible(
        self,
        *,
        governance_state: dict[str, Any],
        hypothesis: Any,
        evidence_signature: str,
        trigger_context: dict[str, Any],
    ) -> tuple[bool, str]:
        """Gate candidate retests by cooldown, novelty, and trigger urgency."""
        registry = governance_state.setdefault("candidate_registry", {})
        entry = registry.get(hypothesis.hypothesis_id)
        if entry is None:
            return True, "new_candidate"
        now = datetime.now(UTC)
        if trigger_context.get("has_incident_trigger"):
            return True, "incident_override"
        next_eligible_raw = entry.get("next_eligible_at")
        if next_eligible_raw:
            next_eligible = datetime.fromisoformat(
                next_eligible_raw.replace("Z", "+00:00")
            )
            if now < next_eligible:
                return False, "cooldown_active"
        if (
            entry.get("last_outcome") == "rejected"
            and entry.get("evidence_signature") == evidence_signature
        ):
            return False, "duplicate_recheck_without_new_evidence"
        return True, "eligible"

    def _record_candidate_outcome(
        self,
        *,
        governance_state: dict[str, Any],
        hypothesis: Any,
        outcome: str,
        reason: str,
        evidence_signature: str,
        version_id: str | None = None,
    ) -> None:
        """Persist candidate lifecycle state and schedule next check."""
        registry = governance_state.setdefault("candidate_registry", {})
        existing = registry.get(hypothesis.hypothesis_id, {})
        rejected_count = int(existing.get("rejected_count", 0))
        promoted_count = int(existing.get("promoted_count", 0))
        if outcome == "rejected":
            rejected_count += 1
        if outcome == "promoted":
            promoted_count += 1
        cooldown_hours = (
            min(48, 2 ** min(rejected_count, 5)) if outcome == "rejected" else 12
        )
        next_eligible_at = (
            datetime.now(UTC) + timedelta(hours=cooldown_hours)
        ).isoformat()
        if outcome == "promoted":
            lifecycle_state = "active"
        elif rejected_count >= 6:
            lifecycle_state = "dormant"
        elif rejected_count >= 3:
            lifecycle_state = "stabilized"
        else:
            lifecycle_state = "active"
        registry[hypothesis.hypothesis_id] = {
            "last_outcome": outcome,
            "last_reason": reason,
            "last_evaluated_at": datetime.now(UTC).isoformat(),
            "next_eligible_at": next_eligible_at,
            "rejected_count": rejected_count,
            "promoted_count": promoted_count,
            "evidence_signature": evidence_signature,
            "version_id": version_id,
            "target_component": getattr(hypothesis, "target_component", "unknown"),
            "lifecycle_state": lifecycle_state,
        }
        if outcome == "promoted" and version_id:
            pending = governance_state.setdefault("pending_verifications", [])
            pending.append(
                {
                    "type": "candidate_promotion",
                    "candidate_id": hypothesis.hypothesis_id,
                    "version_id": version_id,
                    "created_at": datetime.now(UTC).isoformat(),
                    "verify_after": (
                        datetime.now(UTC) + timedelta(hours=2)
                    ).isoformat(),
                    "status": "pending",
                }
            )

    @staticmethod
    def _is_uncertain_candidate_result(metrics: dict[str, float]) -> bool:
        """Uncertainty-aware gate for promotion candidate metrics."""
        sharpe = float(metrics.get("sharpe", 0.0))
        ece = float(metrics.get("ece", 1.0))
        sharpe_margin = abs(sharpe - 1.1)
        ece_margin = abs(0.15 - ece)
        return sharpe_margin < 0.03 or ece_margin < 0.02

    def _process_pending_verifications(
        self,
        *,
        governance_state: dict[str, Any],
        result: CycleResult,
    ) -> list[dict[str, Any]]:
        """Verify post-change outcomes and mark potential regressions."""
        pending = governance_state.setdefault("pending_verifications", [])
        if not pending:
            return []
        now = datetime.now(UTC)
        actions: list[dict[str, Any]] = []
        for item in pending:
            if item.get("status") != "pending":
                continue
            verify_after_raw = item.get("verify_after")
            if not verify_after_raw:
                continue
            verify_after = datetime.fromisoformat(
                verify_after_raw.replace("Z", "+00:00")
            )
            if now < verify_after:
                continue
            regression = (
                bool(result.metrics.get("runtime_non_regression_passed") is False)
                or int(result.constitution_violations) > 0
            )
            if regression:
                item["status"] = "failed"
                item["verified_at"] = now.isoformat()
                item["rollback_required"] = True
                actions.append(
                    {
                        "type": item.get("type"),
                        "candidate_id": item.get("candidate_id"),
                        "status": "failed",
                        "reason": "post_change_regression_detected",
                    }
                )
            else:
                item["status"] = "passed"
                item["verified_at"] = now.isoformat()
                actions.append(
                    {
                        "type": item.get("type"),
                        "candidate_id": item.get("candidate_id"),
                        "status": "passed",
                        "reason": "verification_window_passed",
                    }
                )
        return actions

    def _filter_conflicts_by_revision_cooldown(
        self,
        *,
        governance_state: dict[str, Any],
        conflicts: list[Any],
        trigger_context: dict[str, Any],
    ) -> list[Any]:
        """Skip recently revised conflict pairs unless incident-triggered."""
        if trigger_context.get("has_incident_trigger"):
            return conflicts
        registry = governance_state.setdefault("revision_registry", {})
        now = datetime.now(UTC)
        filtered: list[Any] = []
        for conflict in conflicts:
            pair_key = "|".join(sorted([conflict.belief_id_a, conflict.belief_id_b]))
            record = registry.get(pair_key)
            if not isinstance(record, dict):
                filtered.append(conflict)
                continue
            cooldown_until_raw = record.get("cooldown_until")
            if not cooldown_until_raw:
                filtered.append(conflict)
                continue
            cooldown_until = datetime.fromisoformat(
                cooldown_until_raw.replace("Z", "+00:00")
            )
            if now >= cooldown_until:
                filtered.append(conflict)
        return filtered

    def _record_revision_cooldowns(
        self,
        *,
        governance_state: dict[str, Any],
        revisions: list[Any],
    ) -> None:
        """Record cooldowns to prevent rapid flip-flop revisions."""
        registry = governance_state.setdefault("revision_registry", {})
        for revision in revisions:
            pair_key = "|".join(
                sorted([revision.old_belief_id, revision.new_belief_id])
            )
            registry[pair_key] = {
                "last_revision_id": revision.revision_id,
                "last_applied_at": revision.applied_at,
                "cooldown_until": (datetime.now(UTC) + timedelta(hours=6)).isoformat(),
            }

    def _process_incident_linked_rollbacks(
        self,
        *,
        governance_state: dict[str, Any],
        result: CycleResult,
    ) -> list[dict[str, Any]]:
        """Auto-rollback when incidents/regressions invalidate recent changes."""
        actions: list[dict[str, Any]] = []
        pending = governance_state.setdefault("pending_verifications", [])
        for item in pending:
            if item.get("status") != "failed" or not item.get("rollback_required"):
                continue
            if item.get("type") == "candidate_promotion":
                version_id = str(item.get("version_id", ""))
                promoted_version = self._champion_engine._registry.get_version(
                    version_id
                )  # noqa: SLF001
                if promoted_version is not None:
                    rollback_target = self._champion_engine._registry.get_rollback_target(  # noqa: SLF001
                        model_type=promoted_version.model_type
                    )
                    if rollback_target is not None:
                        self._champion_engine._registry.promote_to_champion(  # noqa: SLF001
                            rollback_target.version_id,
                            force=True,
                        )
                        actions.append(
                            {
                                "type": "candidate_rollback",
                                "candidate_id": item.get("candidate_id"),
                                "rollback_to": rollback_target.version_id,
                            }
                        )
                item["rollback_required"] = False
                item["rolled_back_at"] = datetime.now(UTC).isoformat()

        # Belief rollback from latest revision artifact on incident.
        if (
            result.constitution_violations > 0
            or result.metrics.get("runtime_non_regression_passed") is False
        ):
            latest = self._load_latest_revision_artifact()
            if latest and latest.get("revisions"):
                first = latest["revisions"][0]
                old_id = first.get("old_belief_id")
                new_id = first.get("new_belief_id")
                old_belief = self._belief_store.get(str(old_id)) if old_id else None
                new_belief = self._belief_store.get(str(new_id)) if new_id else None
                if old_belief is not None and new_belief is not None:
                    old_belief.status = "active"
                    old_belief.updated_at = datetime.now(UTC).isoformat()
                    new_belief.status = "superseded"
                    new_belief.updated_at = datetime.now(UTC).isoformat()
                    if not self._belief_store.put(old_belief):
                        logger.warning(
                            "[FULL_CYCLE] Failed to persist rollback belief %s",
                            old_belief.belief_id,
                        )
                    if not self._belief_store.put(new_belief):
                        logger.warning(
                            "[FULL_CYCLE] Failed to persist superseded belief %s",
                            new_belief.belief_id,
                        )
                    actions.append(
                        {
                            "type": "belief_rollback",
                            "rollback_to": old_id,
                            "superseded": new_id,
                            "reason": "incident_triggered_automatic_rollback",
                        }
                    )
        governance_state.setdefault("rollbacks", []).extend(actions)
        return actions

    def _persist_weekly_meta_audit(self) -> Path:
        """Generate weekly meta-audit for reflection quality and efficiency."""
        now = datetime.now(UTC)
        week_id = now.strftime("%G-W%V")
        out_dir = Path(self.DEFAULT_WEEKLY_META_AUDIT_DIR)
        out_dir.mkdir(parents=True, exist_ok=True)
        cycles = self._recent_cycle_window(max_items=300)
        seven_days_ago = now - timedelta(days=7)
        scoped: list[dict[str, Any]] = []
        for cycle in cycles:
            started_at = cycle.get("started_at")
            if isinstance(started_at, str):
                try:
                    ts = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                except ValueError:
                    ts = None
            else:
                ts = None
            if ts is None or ts >= seven_days_ago:
                scoped.append(cycle)
        total = len(scoped)
        promotions = sum(int(c.get("promotions", 0)) for c in scoped)
        rejections = sum(int(c.get("rejections", 0)) for c in scoped)
        revisions = sum(int(c.get("belief_revisions", 0)) for c in scoped)
        blocked = sum(
            len(c.get("metrics", {}).get("belief_revision_blocks", [])) for c in scoped
        )
        duplicate_rechecks = sum(
            len(
                [
                    s
                    for s in c.get("metrics", {}).get("candidate_skips", [])
                    if s.get("reason") == "duplicate_recheck_without_new_evidence"
                ]
            )
            for c in scoped
        )
        rollback_count = len(
            [
                r
                for r in self._load_governance_state().get("rollbacks", [])
                if isinstance(r, dict)
            ]
        )
        artifact = {
            "week_id": week_id,
            "generated_at": now.isoformat(),
            "window_days": 7,
            "runs": total,
            "promotions": promotions,
            "rejections": rejections,
            "belief_revisions": revisions,
            "belief_revision_blocks": blocked,
            "duplicate_rechecks_prevented": duplicate_rechecks,
            "rollbacks_executed": rollback_count,
            "false_positive_proxy_rate": round(rollback_count / max(revisions, 1), 4),
            "efficiency_notes": [
                "Higher duplicate_rechecks_prevented indicates better candidate dedupe.",
                "Lower false_positive_proxy_rate indicates better revision quality.",
            ],
        }
        out_path = out_dir / f"weekly_meta_audit_{week_id}.json"
        out_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
        return out_path

    def _load_latest_revision_artifact(self) -> dict[str, Any] | None:
        """Load latest belief revision artifact for rollback support."""
        out_dir = self._REPO_ROOT / "_bmad-output/autocog/belief_revisions"
        if not out_dir.exists():
            return None
        files = sorted(
            out_dir.glob("autocog-*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for path in files:
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
        return None

    def _persist_manual_approval_packet(
        self,
        *,
        run_id: str,
        blocked_revisions: list[dict[str, Any]],
    ) -> Path:
        """Persist packet for manual approval of high-impact revisions."""
        out_dir = self._REPO_ROOT / "_bmad-output/autocog/manual_approval_packets"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{run_id}.json"
        packet = {
            "run_id": run_id,
            "generated_at": datetime.now(UTC).isoformat(),
            "approval_required": True,
            "reason": "high_impact_belief_revision",
            "blocked_revisions": blocked_revisions,
            "decision_fields": [
                "approved_by",
                "approved_at",
                "decision",
                "notes",
            ],
            "schema_version": "1.0",
        }
        out_path.write_text(json.dumps(packet, indent=2), encoding="utf-8")
        return out_path

    def _persist_cycle_result(self, result: CycleResult) -> Path:
        """Write cycle artifact to disk."""
        out_dir = Path(self.DEFAULT_CYCLE_DIR)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{result.run_id}.json"
        out_path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
        return out_path

    @staticmethod
    def _revision_detail_payload(
        revision: Any, beliefs: dict[str, Belief]
    ) -> dict[str, Any]:
        """Build a durable revision payload for auditing and rollback analysis."""
        old_belief = beliefs.get(revision.old_belief_id)
        new_belief = beliefs.get(revision.new_belief_id)
        return {
            "revision_id": revision.revision_id,
            "old_belief_id": revision.old_belief_id,
            "new_belief_id": revision.new_belief_id,
            "old_belief_statement": (
                old_belief.statement if old_belief is not None else None
            ),
            "new_belief_statement": (
                new_belief.statement if new_belief is not None else None
            ),
            "old_belief_domain": old_belief.domain if old_belief is not None else None,
            "new_belief_domain": new_belief.domain if new_belief is not None else None,
            "confidence_before": revision.confidence_before,
            "confidence_after": revision.confidence_after,
            "confidence_delta": round(
                revision.confidence_after - revision.confidence_before, 6
            ),
            "reason": revision.reason,
            "evidence_refs": list(revision.evidence_refs),
            "applied_at": revision.applied_at,
        }

    def _persist_belief_revisions(
        self,
        *,
        run_id: str,
        revision_details: list[dict[str, Any]],
        decision_packet: dict[str, Any] | None = None,
    ) -> Path:
        """Persist detailed belief revision history for audit and rollback support.

        Creates:
        - Individual artifact at _bmad-output/autocog/belief_revisions/{run_id}.json
        - Index entry in _bmad-output/autocog/belief_revisions/index.json for 7-day retrieval
        """
        out_dir = self._REPO_ROOT / "_bmad-output/autocog/belief_revisions"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{run_id}.json"

        # Build artifact with full schema
        generated_at = datetime.now(UTC)
        artifact = {
            "run_id": run_id,
            "generated_at": generated_at.isoformat(),
            "revision_count": len(revision_details),
            "revisions": revision_details,
            "decision_packet": decision_packet or {},
            "schema_version": "1.0",
            "artifact_type": "belief_revision_audit",
        }

        # Persist individual artifact
        out_path.write_text(
            json.dumps(artifact, indent=2),
            encoding="utf-8",
        )

        # Update index for 7-day retrieval
        self._update_belief_revision_index(
            run_id=run_id,
            generated_at=generated_at,
            revision_count=len(revision_details),
            artifact_path=str(out_path),
            revision_details=revision_details,
        )

        return out_path

    def _update_belief_revision_index(
        self,
        *,
        run_id: str,
        generated_at: datetime,
        revision_count: int,
        artifact_path: str,
        revision_details: list[dict[str, Any]],
    ) -> None:
        """Update the belief revision index for efficient 7-day queries.

        Index schema:
        - last_updated: ISO timestamp of last index update
        - entries: list of revision summaries with metadata for filtering
        """
        out_dir = self._REPO_ROOT / "_bmad-output/autocog/belief_revisions"
        index_path = out_dir / "index.json"

        # Load existing index or create new
        if index_path.exists():
            try:
                index_data = json.loads(index_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                index_data = {"schema_version": "1.0", "entries": []}
        else:
            index_data = {"schema_version": "1.0", "entries": []}

        # Build entry summary with filterable fields
        entry = {
            "run_id": run_id,
            "generated_at": generated_at.isoformat(),
            "revision_count": revision_count,
            "artifact_path": artifact_path,
            "belief_ids": list(
                set(r["old_belief_id"] for r in revision_details)
                | set(r["new_belief_id"] for r in revision_details)
            ),
            "domains": list(
                set(
                    r.get("old_belief_domain") or r.get("new_belief_domain")
                    for r in revision_details
                    if r.get("old_belief_domain") or r.get("new_belief_domain")
                )
            ),
            "severity_summary": self._summarize_severities(revision_details),
        }

        # Add entry to index (prepend for chronological order)
        index_data["entries"].insert(0, entry)
        index_data["last_updated"] = datetime.now(UTC).isoformat()

        # Persist index
        index_path.write_text(
            json.dumps(index_data, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _summarize_severities(revision_details: list[dict[str, Any]]) -> dict[str, int]:
        """Summarize severity distribution from revision details."""
        severity_counts: dict[str, int] = {}
        for detail in revision_details:
            # Severity based on confidence delta magnitude
            delta = abs(detail.get("confidence_delta", 0))
            if delta >= 0.3:
                severity = "high"
            elif delta >= 0.15:
                severity = "medium"
            else:
                severity = "low"
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
        return severity_counts

    def _build_revision_decision_packet(
        self,
        *,
        revision: Any,
        beliefs: dict[str, Belief],
        conflicts: list[Any],
        evidence_index: dict[str, list[EvidenceRecord]],
    ) -> dict[str, Any]:
        """Build explainable decision packet for Discord and rollback handling."""
        old_belief = beliefs.get(revision.old_belief_id)
        new_belief = beliefs.get(revision.new_belief_id)
        conflict_reason = "No matching conflict reason found."
        for conflict in conflicts:
            ids = {conflict.belief_id_a, conflict.belief_id_b}
            if revision.old_belief_id in ids and revision.new_belief_id in ids:
                conflict_reason = conflict.reason
                break
        old_support = self._revision_engine.last_support_scores.get(
            revision.old_belief_id, {}
        )
        new_support = self._revision_engine.last_support_scores.get(
            revision.new_belief_id, {}
        )
        replacement_records: list[EvidenceRecord] = []
        if new_belief is not None:
            for ref in new_belief.evidence_refs:
                replacement_records.extend(evidence_index.get(ref, []))
        source_families = sorted(
            {
                record.source_family
                for record in replacement_records
                if record.source_family
            }
        )
        non_llm_families = sorted(
            {
                record.source_family
                for record in replacement_records
                if record.source_family and not record.is_llm_judgment
            }
        )
        return {
            "revision_id": revision.revision_id,
            "contradiction": conflict_reason,
            "previous_belief": {
                "belief_id": revision.old_belief_id,
                "statement": old_belief.statement if old_belief else "unknown",
                "confidence": revision.confidence_before,
                "support_score": old_support.get("support_score"),
                "evidence_count": old_support.get("evidence_count"),
            },
            "replacement_belief": {
                "belief_id": revision.new_belief_id,
                "statement": new_belief.statement if new_belief else "unknown",
                "confidence": revision.confidence_after,
                "support_score": new_support.get("support_score"),
                "evidence_count": new_support.get("evidence_count"),
            },
            "selection_rationale": (
                "Replacement belief won on evidence-weighted support "
                "and confidence policy thresholds."
            ),
            "source_diversity": {
                "distinct_source_families": len(source_families),
                "non_llm_source_families": len(non_llm_families),
                "source_families": source_families,
            },
            "expected_improvements": [
                "Reduce contradictory internal reasoning paths.",
                "Increase downstream decision consistency for policy selection.",
            ],
            "rollback_hint": (
                "If regression is observed, reactivate previous belief id "
                f"{revision.old_belief_id} and mark revision {revision.revision_id} as reverted."
            ),
        }

    @staticmethod
    def _truncate_text(text: str, max_len: int = 180) -> str:
        """Trim verbose text for Discord evidence lines."""
        if len(text) <= max_len:
            return text
        return text[: max_len - 3] + "..."
