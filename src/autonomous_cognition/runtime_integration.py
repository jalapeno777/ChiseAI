"""Neuro-symbolic runtime integration (shadow/canary/full) for Phase 4.

This module provides a safe integration layer between autonomous cognition
and the neuro-symbolic components, ensuring that:
1. Shadow mode prevents any live trading impact
2. Divergence metrics are calculated and reported
3. Safe fallback when neuro-symbolic components fail
4. Decision-level audit trail with structured explanations
5. Discord event emission for key decisions
6. Redis persistence for historical audit records
"""

from __future__ import annotations

import json
import logging
import time
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from autonomous_cognition.beliefs.audit_writer import (
    BeliefMutationAuditWriter,
    BeliefMutationEvent,
)

logger = logging.getLogger(__name__)


# Redis key prefix for audit trail persistence
AUDIT_TRAIL_KEY_PREFIX = "bmad:chiseai:autocog:audit"
AUDIT_TRAIL_LIST_KEY = f"{AUDIT_TRAIL_KEY_PREFIX}:decisions"
AUDIT_TRAIL_TTL_SECONDS = 30 * 24 * 60 * 60  # 30 days retention


@dataclass
class PerformanceMetrics:
    """Risk-adjusted performance metrics for non-regression tracking.

    Attributes:
        sharpe: Sharpe ratio (risk-adjusted returns)
        sortino: Sortino ratio (downside risk-adjusted returns)
        drawdown: Maximum drawdown percentage
        ece: Expected Calibration Error
        win_rate: Percentage of profitable trades
        turnover: Portfolio turnover rate
    """

    sharpe: float = 1.0
    sortino: float = 1.0
    drawdown: float = 0.0
    ece: float = 0.1
    win_rate: float = 0.55
    turnover: float = 0.15

    def to_dict(self) -> dict[str, Any]:
        return {
            "sharpe": round(self.sharpe, 3),
            "sortino": round(self.sortino, 3),
            "drawdown": round(self.drawdown, 4),
            "ece": round(self.ece, 4),
            "win_rate": round(self.win_rate, 4),
            "turnover": round(self.turnover, 4),
        }


@dataclass
class BeforeAfterComparison:
    """Tracks before/after comparison for improvement validation.

    Attributes:
        before_metrics: Metrics before improvement
        after_metrics: Metrics after improvement
        delta_sharpe: Change in Sharpe ratio
        delta_sortino: Change in Sortino ratio
        delta_drawdown: Change in drawdown (negative = improvement)
        is_improvement: Whether improvement was achieved
        passed_non_regression: Whether no degradation occurred
    """

    before_metrics: PerformanceMetrics
    after_metrics: PerformanceMetrics
    delta_sharpe: float = 0.0
    delta_sortino: float = 0.0
    delta_drawdown: float = 0.0
    is_improvement: bool = False
    passed_non_regression: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "before": self.before_metrics.to_dict(),
            "after": self.after_metrics.to_dict(),
            "delta_sharpe": round(self.delta_sharpe, 4),
            "delta_sortino": round(self.delta_sortino, 4),
            "delta_drawdown": round(self.delta_drawdown, 4),
            "is_improvement": self.is_improvement,
            "passed_non_regression": self.passed_non_regression,
        }


class IntegrationMode(Enum):
    """Operating modes for neuro-symbolic integration."""

    SHADOW = "shadow"  # Observe only, no live impact
    CANARY = "canary"  # Small position test
    FULL = "full"  # Full live trading


class DivergenceSeverity(Enum):
    """Severity levels for divergence detection."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class DivergenceMetrics:
    """Metrics capturing divergence between neuro-symbolic and baseline predictions."""

    confidence_divergence: float = 0.0
    prediction_drift: float = 0.0
    component_agreement: float = 0.0
    severity: str = DivergenceSeverity.LOW.value
    is_drift_detected: bool = False
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "confidence_divergence": self.confidence_divergence,
            "prediction_drift": self.prediction_drift,
            "component_agreement": self.component_agreement,
            "severity": self.severity,
            "is_drift_detected": self.is_drift_detected,
            "details": self.details,
        }


@dataclass
class RuntimeIntegrationResult:
    """Outcome of neuro-symbolic runtime evaluation."""

    mode: str
    success: bool
    divergence_score: float
    divergence_metrics: DivergenceMetrics
    influence_applied: bool
    passed_non_regression: bool
    processing_time_ms: float
    details: dict[str, Any]
    performance_metrics: PerformanceMetrics | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "success": self.success,
            "divergence_score": self.divergence_score,
            "divergence_metrics": self.divergence_metrics.to_dict(),
            "influence_applied": self.influence_applied,
            "passed_non_regression": self.passed_non_regression,
            "processing_time_ms": self.processing_time_ms,
            "details": self.details,
            "performance_metrics": (
                self.performance_metrics.to_dict() if self.performance_metrics else None
            ),
            "timestamp": self.timestamp,
        }


@dataclass
class BaselinePrediction:
    """Represents a baseline prediction for comparison."""

    prediction: str
    confidence: float
    symbol: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class CanaryOutcome:
    """Tracks P&L of a canary-influenced decision.

    Attributes:
        decision_id: Unique identifier for this decision
        symbol: Trading pair symbol (e.g., "BTC/USDT")
        prediction: The prediction made (buy/sell/hold)
        confidence: Confidence level (0-1)
        predicted_direction: Direction predicted (up/down/flat)
        actual_direction: Actual market direction (up/down/flat)
        pnl: Profit/loss realized from this decision
        pnl_fraction: P&L as fraction of portfolio
        entry_price: Price at which decision was made
        exit_price: Price at which position was closed
        is_canary: Whether this was a canary-influenced decision
        influence_applied: Whether neuro-symbolic influence was applied
        divergence_score: Divergence score at time of decision
        timestamp: When the decision was made
    """

    decision_id: str
    symbol: str | None
    prediction: str
    confidence: float
    predicted_direction: str  # up, down, flat
    actual_direction: str | None = None  # up, down, flat, unknown
    pnl: float = 0.0
    pnl_fraction: float = 0.0
    entry_price: float = 0.0
    exit_price: float = 0.0
    is_canary: bool = True
    influence_applied: bool = False
    divergence_score: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "symbol": self.symbol,
            "prediction": self.prediction,
            "confidence": round(self.confidence, 4),
            "predicted_direction": self.predicted_direction,
            "actual_direction": self.actual_direction,
            "pnl": round(self.pnl, 8),
            "pnl_fraction": round(self.pnl_fraction, 6),
            "entry_price": round(self.entry_price, 8),
            "exit_price": round(self.exit_price, 8),
            "is_canary": self.is_canary,
            "influence_applied": self.influence_applied,
            "divergence_score": round(self.divergence_score, 4),
            "timestamp": self.timestamp,
        }


@dataclass
class OutcomeComparison:
    """Compares canary outcomes vs baseline.

    Attributes:
        canary_total_pnl: Total P&L from canary-influenced decisions
        baseline_total_pnl: Total P&L from baseline decisions
        canary_win_rate: Win rate of canary decisions
        baseline_win_rate: Win rate of baseline decisions
        canary_trade_count: Number of canary trades
        baseline_trade_count: Number of baseline trades
        pnl_difference: Difference in P&L (canary - baseline)
        win_rate_difference: Difference in win rates
        relative_performance: Relative performance (canary vs baseline as ratio)
        is_regression: Whether canary represents a regression vs baseline
    """

    canary_total_pnl: float = 0.0
    baseline_total_pnl: float = 0.0
    canary_win_rate: float = 0.0
    baseline_win_rate: float = 0.0
    canary_trade_count: int = 0
    baseline_trade_count: int = 0
    pnl_difference: float = 0.0
    win_rate_difference: float = 0.0
    relative_performance: float = 1.0
    is_regression: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "canary_total_pnl": round(self.canary_total_pnl, 8),
            "baseline_total_pnl": round(self.baseline_total_pnl, 8),
            "canary_win_rate": round(self.canary_win_rate, 4),
            "baseline_win_rate": round(self.baseline_win_rate, 4),
            "canary_trade_count": self.canary_trade_count,
            "baseline_trade_count": self.baseline_trade_count,
            "pnl_difference": round(self.pnl_difference, 8),
            "win_rate_difference": round(self.win_rate_difference, 4),
            "relative_performance": round(self.relative_performance, 4),
            "is_regression": self.is_regression,
        }


@dataclass
class ExplanationPacket:
    """Structured explanation packet for autonomous decisions.

    This packet provides a human-understandable explanation of why
    a particular decision was made, including reasoning chain,
    evidence references, and confidence breakdown.

    Attributes:
        decision_id: Unique identifier for this decision
        decision_type: Type of decision (mode_transition, influence_apply,
                      promotion, demotion, divergence_detected)
        summary: One-line summary of the decision
        reasoning_chain: Step-by-step reasoning that led to the decision
        evidence_refs: List of evidence references supporting the decision
        confidence_breakdown: Confidence scores for different aspects
        uncertainty_notes: Explicit notes about uncertainty or caveats
        influenced_by: Factors that influenced the decision
        timestamp: When the decision was made
    """

    decision_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    decision_type: str = ""
    summary: str = ""
    reasoning_chain: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    confidence_breakdown: dict[str, float] = field(default_factory=dict)
    uncertainty_notes: list[str] = field(default_factory=list)
    influenced_by: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "decision_type": self.decision_type,
            "summary": self.summary,
            "reasoning_chain": self.reasoning_chain,
            "evidence_refs": self.evidence_refs,
            "confidence_breakdown": {
                k: round(v, 4) for k, v in self.confidence_breakdown.items()
            },
            "uncertainty_notes": self.uncertainty_notes,
            "influenced_by": self.influenced_by,
            "timestamp": self.timestamp,
        }


@dataclass
class DecisionAuditEntry:
    """A decision-level audit trail entry.

    Records every significant decision made by the autonomous cognition
    system, including the decision context, outcome, and explanation.

    Attributes:
        decision_id: Unique identifier for this decision
        decision_type: Type of decision (mode_transition, promotion,
                      demotion, divergence_detected, influence_apply)
        mode: Current integration mode at time of decision
        timestamp: When the decision was made
        summary: Human-readable summary of the decision
        explanation: Structured explanation packet
        divergence_metrics: Divergence metrics at time of decision
        success: Whether the decision action succeeded
        error: Error message if decision failed
    """

    decision_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    decision_type: str = ""
    mode: str = "shadow"
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    summary: str = ""
    explanation: ExplanationPacket | None = None
    divergence_metrics: DivergenceMetrics | None = None
    success: bool = True
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "decision_type": self.decision_type,
            "mode": self.mode,
            "timestamp": self.timestamp,
            "summary": self.summary,
            "explanation": self.explanation.to_dict() if self.explanation else None,
            "divergence_metrics": (
                self.divergence_metrics.to_dict() if self.divergence_metrics else None
            ),
            "success": self.success,
            "error": self.error,
        }


class NeuroSymbolicRuntimeIntegrator:
    """Runs shadow/canary/full integration checks with safe fallback.

    This integrator provides a safe wrapper around the neuro-symbolic
    components with the following safety guarantees:

    SHADOW mode:
    - Predictions are generated but NOT applied to any trading system
    - Divergence metrics are calculated and logged
    - No orders are sent, no positions modified

    CANARY mode:
    - Small test position may be applied (configurable threshold)
    - Strict divergence gates before any live action
    - Full metrics reporting

    FULL mode:
    - Normal trading operation with neuro-symbolic influence
    - Continuous divergence monitoring
    - Automatic rollback if drift detected

    PHASE 4 ADDITIONS:
    - Decision-level audit trail logging every decision
    - Structured explanation packets for explainability
    - Discord event emission for key decisions
    - Redis persistence for historical audit records
    """

    # Divergence thresholds
    DIVERGENCE_THRESHOLD_LOW = 0.15
    DIVERGENCE_THRESHOLD_MEDIUM = 0.25
    DIVERGENCE_THRESHOLD_HIGH = 0.35
    DIVERGENCE_THRESHOLD_CRITICAL = 0.45

    # Influence thresholds
    MIN_CONFIDENCE_FOR_INFLUENCE = 0.55
    MAX_ALLOWED_DIVERGENCE_FOR_INFLUENCE = 0.30

    # Canary mode constraints
    CANARY_MAX_POSITION_FRACTION = 0.01  # Max 1% of portfolio in canary

    # Non-regression thresholds for risk-adjusted performance
    # These ensure no degradation in key metrics when promoting improvements
    MIN_SHARPE_NON_REGRESSION = 1.0  # Minimum Sharpe ratio - below this is regression
    MAX_DRAWDOWN_NON_REGRESSION = 0.25  # Maximum drawdown - above this is regression
    MIN_SORTINO_NON_REGRESSION = 1.0  # Minimum Sortino ratio - below this is regression
    MAX_ECE_NON_REGRESSION = 0.20  # Maximum ECE - above this is regression

    # Mode transition hysteresis thresholds
    # Promote: canary -> full when score >= 0.35
    PROMOTE_THRESHOLD = 0.35
    # Demote: full -> canary when score >= 0.40
    DEMOTE_THRESHOLD = 0.40

    # Window-based promotion criteria
    # Require N consecutive non-regression checks before promoting
    REQUIRED_CONSECUTIVE_CHECKS = 5

    # Drift detection threshold for auto-demotion
    DRIFT_THRESHOLD_FOR_DEMOTION = 0.40

    def __init__(
        self,
        baseline_prediction: BaselinePrediction | None = None,
        enable_fallback: bool = True,
        shadow_lock: bool = True,
        baseline_performance: PerformanceMetrics | None = None,
    ):
        """Initialize the runtime integrator.

        Args:
            baseline_prediction: Optional baseline for divergence comparison
            enable_fallback: Whether to use fallback on orchestrator failure
            shadow_lock: If True, forces shadow mode regardless of settings
            baseline_performance: Optional baseline performance metrics for comparison
        """
        self._baseline = baseline_prediction
        self._enable_fallback = enable_fallback
        self._shadow_lock = shadow_lock
        self._baseline_performance = baseline_performance
        self._integration_history: list[RuntimeIntegrationResult] = []
        self._divergence_history: list[DivergenceMetrics] = []
        self._canary_outcomes: list[CanaryOutcome] = []  # Track canary P&L
        self._baseline_outcomes: list[CanaryOutcome] = []  # Track baseline P&L
        self._orchestrator = None
        self._fallback_used = False

        # Mode transition state machine tracking
        self._current_mode: IntegrationMode = IntegrationMode.SHADOW
        self._consecutive_non_regression_count: int = 0
        self._consecutive_non_regression_history: list[int] = []

        # Phase 4: Decision audit trail
        self._audit_trail: list[DecisionAuditEntry] = []
        self._discord_notifier = None  # Lazy-loaded Discord notifier

    @property
    def audit_trail(self) -> list[DecisionAuditEntry]:
        """Get the decision audit trail."""
        return self._audit_trail

    def set_discord_notifier(self, notifier: Any) -> None:
        """Set Discord notifier for event emission.

        Args:
            notifier: DiscordNotifier instance for emitting events
        """
        self._discord_notifier = notifier
        logger.info("[RUNTIME_INTEGRATION] Discord notifier set for event emission")

    @property
    def shadow_lock(self) -> bool:
        """Check if shadow lock is engaged (prevents live impact)."""
        return self._shadow_lock

    @property
    def fallback_used(self) -> bool:
        """Check if fallback was used in last run."""
        return self._fallback_used

    def set_baseline(self, baseline: BaselinePrediction) -> None:
        """Set baseline prediction for divergence calculation."""
        self._baseline = baseline
        logger.info(
            "[RUNTIME_INTEGRATION] Baseline set: prediction=%s, confidence=%.2f",
            baseline.prediction,
            baseline.confidence,
        )

    def capture_baseline_from_signal(self, signal: Any) -> None:
        """Capture a baseline from a live signal pipeline output.

        Converts a :class:`signal_generation.models.Signal` into a
        :class:`BaselinePrediction` and stores it for divergence comparison.

        This is designed to be registered as a signal flow tap on the
        :class:`SignalGenerator` so that every live signal automatically
        updates the baseline without any additional wiring.

        Args:
            signal: A ``Signal`` dataclass from the signal generation pipeline.
        """
        direction = getattr(signal, "direction", None)
        direction_str = (
            getattr(direction, "value", str(direction)) if direction else "neutral"
        )
        confidence = float(getattr(signal, "confidence", 0.0))
        token = getattr(signal, "token", None)

        baseline = BaselinePrediction(
            prediction=direction_str,
            confidence=confidence,
            symbol=token,
        )
        self.set_baseline(baseline)
        logger.debug(
            "[RUNTIME_INTEGRATION] Baseline captured from live signal: "
            "token=%s, direction=%s, confidence=%.2f",
            token,
            direction_str,
            confidence,
        )

    def compare_shadow_vs_live(
        self, shadow_result: RuntimeIntegrationResult, live_signal: Any
    ) -> DivergenceMetrics:
        """Calculate divergence between a shadow evaluation and a live signal.

        This compares the neuro-symbolic shadow output against the actual
        live signal from the signal generation pipeline, producing a
        :class:`DivergenceMetrics` that captures the quality gap.

        Args:
            shadow_result: Result from a shadow-mode :meth:`run` call.
            live_signal: A ``Signal`` dataclass from the signal generation pipeline.

        Returns:
            DivergenceMetrics capturing the comparison.
        """
        live_confidence = float(getattr(live_signal, "confidence", 0.0))
        live_direction = getattr(live_signal, "direction", None)
        live_direction_str = (
            getattr(live_direction, "value", str(live_direction))
            if live_direction
            else "neutral"
        )

        shadow_confidence = float(shadow_result.details.get("confidence", 0.0))
        shadow_prediction = shadow_result.details.get("prediction", "neutral")
        shadow_components = shadow_result.details.get("components_used", [])

        metrics = DivergenceMetrics()

        # Confidence divergence
        metrics.confidence_divergence = abs(shadow_confidence - live_confidence)

        # Prediction drift
        if shadow_prediction.lower() != live_direction_str.lower():
            if shadow_confidence > 0.7 and live_confidence < 0.4:
                metrics.prediction_drift = 1.0
            elif shadow_confidence > live_confidence + 0.2:
                metrics.prediction_drift = 0.7
            else:
                metrics.prediction_drift = 0.4
        else:
            metrics.prediction_drift = abs(shadow_confidence - live_confidence)

        # Component agreement
        if shadow_components:
            metrics.component_agreement = min(1.0, len(shadow_components) / 3.0)
        else:
            metrics.component_agreement = 0.0

        # Determine severity
        max_divergence = max(metrics.confidence_divergence, metrics.prediction_drift)
        if max_divergence >= self.DIVERGENCE_THRESHOLD_CRITICAL:
            metrics.severity = DivergenceSeverity.CRITICAL.value
        elif max_divergence >= self.DIVERGENCE_THRESHOLD_HIGH:
            metrics.severity = DivergenceSeverity.HIGH.value
        elif max_divergence >= self.DIVERGENCE_THRESHOLD_MEDIUM:
            metrics.severity = DivergenceSeverity.MEDIUM.value
        else:
            metrics.severity = DivergenceSeverity.LOW.value

        metrics.is_drift_detected = (
            max_divergence > self.DIVERGENCE_THRESHOLD_LOW
            or metrics.confidence_divergence > 0.3
        )

        metrics.details = {
            "live_prediction": live_direction_str,
            "live_confidence": live_confidence,
            "shadow_prediction": shadow_prediction,
            "shadow_confidence": shadow_confidence,
            "shadow_components": shadow_components,
            "shadow_divergence_score": shadow_result.divergence_score,
        }

        return metrics

    def set_baseline_performance(self, performance: PerformanceMetrics) -> None:
        """Set baseline performance metrics for non-regression comparison.

        Args:
            performance: Baseline performance metrics (Sharpe, Sortino, drawdown)
        """
        self._baseline_performance = performance
        logger.info(
            "[RUNTIME_INTEGRATION] Baseline performance set: Sharpe=%.3f, "
            "Sortino=%.3f, Drawdown=%.4f",
            performance.sharpe,
            performance.sortino,
            performance.drawdown,
        )

    def get_baseline_performance(self) -> PerformanceMetrics | None:
        """Get the current baseline performance metrics.

        Returns:
            Baseline performance metrics or None if not set
        """
        return self._baseline_performance

    def check_non_regression(
        self, current_metrics: PerformanceMetrics
    ) -> tuple[bool, BeforeAfterComparison]:
        """Check if current metrics show non-regression vs baseline.

        Args:
            current_metrics: Current performance metrics to check

        Returns:
            Tuple of (passed_non_regression, comparison_details)
        """
        if self._baseline_performance is None:
            # No baseline set - cannot check non-regression
            return True, BeforeAfterComparison(
                before_metrics=current_metrics,
                after_metrics=current_metrics,
                passed_non_regression=True,
            )

        # Calculate deltas
        delta_sharpe = current_metrics.sharpe - self._baseline_performance.sharpe
        delta_sortino = current_metrics.sortino - self._baseline_performance.sortino
        delta_drawdown = current_metrics.drawdown - self._baseline_performance.drawdown

        # Check non-regression criteria
        # Sharpe should not decrease
        sharpe_ok = delta_sharpe >= -0.1  # Allow 0.1 tolerance
        # Sortino should not decrease
        sortino_ok = delta_sortino >= -0.1  # Allow 0.1 tolerance
        # Drawdown should not increase (negative delta means improvement)
        drawdown_ok = delta_drawdown <= 0.05  # Allow 5% tolerance for drawdown increase
        # ECE should not increase
        ece_ok = current_metrics.ece <= self._baseline_performance.ece + 0.02

        passed_non_regression = sharpe_ok and sortino_ok and drawdown_ok and ece_ok

        # Determine if this is an improvement
        is_improvement = (
            current_metrics.sharpe > self._baseline_performance.sharpe
            or current_metrics.sortino > self._baseline_performance.sortino
            or current_metrics.drawdown < self._baseline_performance.drawdown
        )

        comparison = BeforeAfterComparison(
            before_metrics=self._baseline_performance,
            after_metrics=current_metrics,
            delta_sharpe=delta_sharpe,
            delta_sortino=delta_sortino,
            delta_drawdown=delta_drawdown,
            is_improvement=is_improvement,
            passed_non_regression=passed_non_regression,
        )

        return passed_non_regression, comparison

    def get_performance_report(self) -> dict[str, Any]:
        """Generate a performance comparison report.

        Returns:
            Dictionary with baseline, current, and comparison metrics
        """
        if self._baseline_performance is None:
            return {
                "status": "no_baseline",
                "message": "No baseline performance metrics set",
            }

        recent_with_performance = [
            r for r in self._integration_history if r.performance_metrics is not None
        ]

        if not recent_with_performance:
            return {
                "status": "no_current_data",
                "baseline": self._baseline_performance.to_dict(),
                "message": "No current performance metrics available",
            }

        # Get latest performance
        latest = recent_with_performance[-1].performance_metrics
        if latest is None:
            return {
                "status": "error",
                "message": "Unexpected: latest performance is None",
            }
        passed, comparison = self.check_non_regression(latest)

        return {
            "status": "ok",
            "baseline": self._baseline_performance.to_dict(),
            "current": latest.to_dict(),
            "comparison": comparison.to_dict(),
            "passed_non_regression": passed,
        }

    def _get_orchestrator(self):
        """Lazy-load the neuro-symbolic orchestrator."""
        if self._orchestrator is None:
            try:
                from src.neuro_symbolic.orchestrator.orchestrator import (
                    NeuroSymbolicOrchestrator,
                )

                self._orchestrator = NeuroSymbolicOrchestrator()
                logger.info(
                    "[RUNTIME_INTEGRATION] Neuro-symbolic orchestrator initialized"
                )
            except Exception as e:
                logger.warning(
                    "[RUNTIME_INTEGRATION] Could not initialize orchestrator: %s", e
                )
                raise
        return self._orchestrator

    def _calculate_divergence_metrics(
        self,
        ns_prediction: str,
        ns_confidence: float,
        ns_components: list[str],
    ) -> DivergenceMetrics:
        """Calculate divergence between neuro-symbolic and baseline predictions.

        Args:
            ns_prediction: Neuro-symbolic prediction (buy/sell/hold)
            ns_confidence: Neuro-symbolic confidence (0-1)
            ns_components: List of components used

        Returns:
            DivergenceMetrics with calculated values
        """
        metrics = DivergenceMetrics()

        # Calculate confidence divergence
        if self._baseline:
            baseline_conf = self._baseline.confidence
            metrics.confidence_divergence = abs(ns_confidence - baseline_conf)

            # Calculate prediction drift
            if ns_prediction != self._baseline.prediction:
                # Different prediction - calculate drift severity
                if ns_confidence > 0.7 and baseline_conf < 0.4:
                    metrics.prediction_drift = 1.0  # Strong reversal
                elif ns_confidence > baseline_conf + 0.2:
                    metrics.prediction_drift = 0.7  # Significant shift
                else:
                    metrics.prediction_drift = 0.4  # Minor shift
            else:
                # Same prediction - check confidence drift
                metrics.prediction_drift = abs(ns_confidence - baseline_conf)

        else:
            # No baseline - use confidence uncertainty as proxy
            metrics.confidence_divergence = 0.5 - ns_confidence
            metrics.prediction_drift = 0.0

        # Calculate component agreement (based on number of components used)
        if ns_components:
            # More components = higher agreement requirement
            metrics.component_agreement = min(1.0, len(ns_components) / 3.0)
        else:
            metrics.component_agreement = 0.0

        # Determine overall severity
        max_divergence = max(metrics.confidence_divergence, metrics.prediction_drift)

        if max_divergence >= self.DIVERGENCE_THRESHOLD_CRITICAL:
            metrics.severity = DivergenceSeverity.CRITICAL.value
        elif max_divergence >= self.DIVERGENCE_THRESHOLD_HIGH:
            metrics.severity = DivergenceSeverity.HIGH.value
        elif max_divergence >= self.DIVERGENCE_THRESHOLD_MEDIUM:
            metrics.severity = DivergenceSeverity.MEDIUM.value
        else:
            metrics.severity = DivergenceSeverity.LOW.value

        # Check if drift is detected
        metrics.is_drift_detected = (
            max_divergence > self.DIVERGENCE_THRESHOLD_LOW
            or metrics.confidence_divergence > 0.3
        )

        # Store component details
        metrics.details = {
            "baseline_prediction": (
                self._baseline.prediction if self._baseline else None
            ),
            "baseline_confidence": (
                self._baseline.confidence if self._baseline else None
            ),
            "ns_components": ns_components,
        }

        return metrics

    def _should_apply_influence(
        self, mode: IntegrationMode, metrics: DivergenceMetrics
    ) -> tuple[bool, str]:
        """Determine if influence should be applied based on mode and metrics.

        Args:
            mode: Current integration mode
            metrics: Calculated divergence metrics

        Returns:
            Tuple of (should_apply, reason)
        """
        # Shadow lock always prevents influence
        if self._shadow_lock:
            return False, "shadow_lock_engaged"

        # Only canary and full modes can apply influence
        if mode == IntegrationMode.SHADOW:
            return False, "shadow_mode_no_influence"

        # Check divergence thresholds
        if metrics.is_drift_detected:
            if metrics.severity in {
                DivergenceSeverity.HIGH.value,
                DivergenceSeverity.CRITICAL.value,
            }:
                return False, f"divergence_too_high_{metrics.severity}"

        # Check confidence threshold
        if metrics.details.get("ns_confidence", 0) < self.MIN_CONFIDENCE_FOR_INFLUENCE:
            return False, "confidence_below_threshold"

        # Passed all checks
        return True, "approved"

    def run(
        self,
        mode: str = "shadow",
        market_input: dict[str, Any] | None = None,
        performance_metrics: PerformanceMetrics | None = None,
    ) -> RuntimeIntegrationResult:
        """Run neuro-symbolic integration in selected mode.

        Args:
            mode: Operating mode - "shadow", "canary", or "full"
            market_input: Market data for processing
            performance_metrics: Optional performance metrics (Sharpe, Sortino, drawdown)
                               for non-regression tracking

        Returns:
            RuntimeIntegrationResult with divergence metrics and status
        """
        start_time = time.perf_counter()
        integration_mode = IntegrationMode(mode)

        # Validate market_input is provided for non-shadow modes
        if market_input is None and integration_mode != IntegrationMode.SHADOW:
            raise ValueError(
                f"market_input is required for {integration_mode.value} mode; "
                "use shadow mode if you don't have market data"
            )

        data = market_input or {
            "price": 100.0,
            "volume": 1000.0,
            "rsi": 55.0,
        }

        logger.info(
            "[RUNTIME_INTEGRATION] Running integration in %s mode",
            integration_mode.value,
        )

        # Default fallback result
        fallback_result = RuntimeIntegrationResult(
            mode=mode,
            success=False,
            divergence_score=1.0,
            divergence_metrics=DivergenceMetrics(
                confidence_divergence=1.0,
                severity=DivergenceSeverity.CRITICAL.value,
                is_drift_detected=True,
                details={"error": "orchestrator_unavailable"},
            ),
            influence_applied=False,
            passed_non_regression=False,
            processing_time_ms=0.0,
            details={"fallback": "legacy_signal_pipeline"},
            performance_metrics=None,
        )

        try:
            # Get orchestrator (lazy load)
            orchestrator = self._get_orchestrator()
            result = orchestrator.process_signal(data)

            ns_prediction = result.prediction
            ns_confidence = float(result.confidence)
            ns_components = result.components_used

            # Calculate divergence metrics
            divergence_metrics = self._calculate_divergence_metrics(
                ns_prediction, ns_confidence, ns_components
            )

            # Determine if influence should be applied
            should_apply, reason = self._should_apply_influence(
                integration_mode, divergence_metrics
            )

            # Calculate overall divergence score
            divergence_score = max(
                divergence_metrics.confidence_divergence,
                divergence_metrics.prediction_drift,
            )

            # Determine non-regression status
            passed = divergence_score <= self.DIVERGENCE_THRESHOLD_HIGH

            processing_time = (time.perf_counter() - start_time) * 1000

            integration_result = RuntimeIntegrationResult(
                mode=mode,
                success=True,
                divergence_score=round(divergence_score, 3),
                divergence_metrics=divergence_metrics,
                influence_applied=should_apply,
                passed_non_regression=passed,
                processing_time_ms=round(processing_time, 2),
                details={
                    "prediction": ns_prediction,
                    "confidence": ns_confidence,
                    "components_used": ns_components,
                    "influence_reason": reason,
                    "orchestrator_used": True,
                },
                performance_metrics=performance_metrics,
            )

            self._fallback_used = False

        except ImportError as e:
            # ImportError is permanent - the module is not available
            logger.error(
                "[RUNTIME_INTEGRATION] ImportError: Neuro-symbolic orchestrator "
                "module unavailable (permanent failure): %s\n%s",
                e,
                traceback.format_exc(),
            )

            if not self._enable_fallback:
                return fallback_result

            self._fallback_used = True
            fallback_result.processing_time_ms = (
                time.perf_counter() - start_time
            ) * 1000
            return fallback_result

        except Exception as e:
            # Other exceptions may be transient
            logger.error(
                "[RUNTIME_INTEGRATION] Orchestrator failed (transient): %s\n%s",
                e,
                traceback.format_exc(),
            )

            if not self._enable_fallback:
                return fallback_result

            self._fallback_used = True
            fallback_result.processing_time_ms = (
                time.perf_counter() - start_time
            ) * 1000
            return fallback_result

        # Store in history
        self._integration_history.append(integration_result)
        self._divergence_history.append(divergence_metrics)

        # Trim history if needed
        if len(self._integration_history) > 1000:
            self._integration_history = self._integration_history[-1000:]
        if len(self._divergence_history) > 1000:
            self._divergence_history = self._divergence_history[-1000:]

        # Update mode transition state machine
        self._update_consecutive_non_regression(passed, divergence_score)

        # Check for auto-demotion from full to canary
        if self._current_mode == IntegrationMode.FULL:
            demoted, demote_reason = self.check_auto_demotion(divergence_score)
            if demoted:
                integration_result.details["auto_demoted"] = True
                integration_result.details["demote_reason"] = demote_reason

        logger.info(
            "[RUNTIME_INTEGRATION] Result: mode=%s, divergence=%.3f, "
            "influence=%s, passed=%s, consecutive_checks=%d/%d",
            mode,
            integration_result.divergence_score,
            integration_result.influence_applied,
            integration_result.passed_non_regression,
            self._consecutive_non_regression_count,
            self.REQUIRED_CONSECUTIVE_CHECKS,
        )

        return integration_result

    def get_divergence_report(self) -> dict[str, Any]:
        """Generate a comprehensive divergence analysis report.

        Returns:
            Dictionary containing divergence metrics, trends, and recommendations
        """
        if not self._divergence_history:
            return {
                "summary": "No divergence data collected yet",
                "metrics": {},
                "recommendations": [],
            }

        # Calculate aggregate statistics
        recent_metrics = self._divergence_history[-100:]

        avg_confidence_div = sum(m.confidence_divergence for m in recent_metrics) / len(
            recent_metrics
        )

        avg_prediction_drift = sum(m.prediction_drift for m in recent_metrics) / len(
            recent_metrics
        )

        drift_count = sum(1 for m in recent_metrics if m.is_drift_detected)

        severity_counts = {
            DivergenceSeverity.LOW.value: 0,
            DivergenceSeverity.MEDIUM.value: 0,
            DivergenceSeverity.HIGH.value: 0,
            DivergenceSeverity.CRITICAL.value: 0,
        }
        for m in recent_metrics:
            severity_counts[m.severity] = severity_counts.get(m.severity, 0) + 1

        # Generate recommendations
        recommendations = []

        if drift_count / len(recent_metrics) > 0.3:
            recommendations.append(
                "High drift frequency detected. Consider reviewing neuro-symbolic components."
            )

        if severity_counts[DivergenceSeverity.CRITICAL.value] > 0:
            recommendations.append(
                "Critical divergence events observed. Immediate review required."
            )

        if avg_confidence_div > self.DIVERGENCE_THRESHOLD_MEDIUM:
            recommendations.append(
                "Confidence divergence above threshold. Check model calibration."
            )

        return {
            "summary": {
                "total_evaluations": len(self._integration_history),
                "recent_evaluations": len(recent_metrics),
                "drift_frequency": round(drift_count / len(recent_metrics), 3),
                "avg_confidence_divergence": round(avg_confidence_div, 3),
                "avg_prediction_drift": round(avg_prediction_drift, 3),
                "severity_distribution": severity_counts,
            },
            "metrics": {
                m.severity: m.to_dict()
                for m in recent_metrics[-10:]  # Last 10 for detail
            },
            "recommendations": recommendations,
            "current_baseline": (
                {
                    "prediction": self._baseline.prediction,
                    "confidence": self._baseline.confidence,
                }
                if self._baseline
                else None
            ),
        }

    def get_integration_history(self) -> list[dict[str, Any]]:
        """Get the history of integration results.

        Returns:
            List of result dictionaries
        """
        return [r.to_dict() for r in self._integration_history]

    def reset_history(self) -> None:
        """Clear integration and divergence history."""
        self._integration_history.clear()
        self._divergence_history.clear()
        logger.info("[RUNTIME_INTEGRATION] History cleared")

    def record_canary_outcome(
        self,
        decision_id: str,
        symbol: str | None,
        prediction: str,
        confidence: float,
        predicted_direction: str,
        pnl: float = 0.0,
        pnl_fraction: float = 0.0,
        entry_price: float = 0.0,
        exit_price: float = 0.0,
        actual_direction: str | None = None,
        divergence_score: float = 0.0,
    ) -> CanaryOutcome:
        """Record a canary-influenced decision outcome."""
        outcome = CanaryOutcome(
            decision_id=decision_id,
            symbol=symbol,
            prediction=prediction,
            confidence=confidence,
            predicted_direction=predicted_direction,
            actual_direction=actual_direction,
            pnl=pnl,
            pnl_fraction=pnl_fraction,
            entry_price=entry_price,
            exit_price=exit_price,
            is_canary=True,
            influence_applied=True,
            divergence_score=divergence_score,
        )
        self._canary_outcomes.append(outcome)
        logger.info(
            "[RUNTIME_INTEGRATION] Canary outcome recorded: decision_id=%s symbol=%s pnl=%.4f",
            decision_id,
            symbol,
            pnl,
        )
        return outcome

    def record_baseline_outcome(
        self,
        decision_id: str,
        symbol: str | None,
        prediction: str,
        confidence: float,
        predicted_direction: str,
        pnl: float = 0.0,
        pnl_fraction: float = 0.0,
        entry_price: float = 0.0,
        exit_price: float = 0.0,
        actual_direction: str | None = None,
    ) -> CanaryOutcome:
        """Record a baseline (non-canary) decision outcome."""
        outcome = CanaryOutcome(
            decision_id=decision_id,
            symbol=symbol,
            prediction=prediction,
            confidence=confidence,
            predicted_direction=predicted_direction,
            actual_direction=actual_direction,
            pnl=pnl,
            pnl_fraction=pnl_fraction,
            entry_price=entry_price,
            exit_price=exit_price,
            is_canary=False,
            influence_applied=False,
            divergence_score=0.0,
        )
        self._baseline_outcomes.append(outcome)
        logger.info(
            "[RUNTIME_INTEGRATION] Baseline outcome recorded: decision_id=%s symbol=%s pnl=%.4f",
            decision_id,
            symbol,
            pnl,
        )
        return outcome

    def get_outcome_comparison(self) -> OutcomeComparison:
        """Compare canary outcomes vs baseline."""
        canary_wins = sum(1 for o in self._canary_outcomes if o.pnl > 0)
        baseline_wins = sum(1 for o in self._baseline_outcomes if o.pnl > 0)
        canary_total = sum(o.pnl for o in self._canary_outcomes)
        baseline_total = sum(o.pnl for o in self._baseline_outcomes)
        canary_count = len(self._canary_outcomes)
        baseline_count = len(self._baseline_outcomes)
        canary_win_rate = (
            (canary_wins / canary_count * 100) if canary_count > 0 else 0.0
        )
        baseline_win_rate = (
            (baseline_wins / baseline_count * 100) if baseline_count > 0 else 0.0
        )
        pnl_diff = canary_total - baseline_total
        win_rate_diff = canary_win_rate - baseline_win_rate
        if baseline_total != 0:
            relative_perf = canary_total / baseline_total
        elif canary_total > 0:
            relative_perf = float("inf")
        else:
            relative_perf = 1.0
        is_regression = (
            canary_total < (baseline_total * 0.9) if baseline_total != 0 else False
        )
        return OutcomeComparison(
            canary_total_pnl=canary_total,
            baseline_total_pnl=baseline_total,
            canary_win_rate=canary_win_rate,
            baseline_win_rate=baseline_win_rate,
            canary_trade_count=canary_count,
            baseline_trade_count=baseline_count,
            pnl_difference=pnl_diff,
            win_rate_difference=win_rate_diff,
            relative_performance=relative_perf,
            is_regression=is_regression,
        )

    def get_canary_pnl_report(self) -> dict[str, Any]:
        """Generate a P&L report for canary-influenced decisions."""
        if not self._canary_outcomes:
            return {
                "summary": "No canary outcomes recorded yet",
                "canary_outcomes": [],
                "comparison": None,
            }
        total_pnl = sum(o.pnl for o in self._canary_outcomes)
        avg_pnl = (
            total_pnl / len(self._canary_outcomes) if self._canary_outcomes else 0.0
        )
        wins = sum(1 for o in self._canary_outcomes if o.pnl > 0)
        losses = sum(1 for o in self._canary_outcomes if o.pnl < 0)
        breakeven = sum(1 for o in self._canary_outcomes if o.pnl == 0)
        win_rate = (
            (wins / len(self._canary_outcomes) * 100) if self._canary_outcomes else 0.0
        )
        sorted_outcomes = sorted(self._canary_outcomes, key=lambda o: o.pnl)
        worst = sorted_outcomes[0] if sorted_outcomes else None
        best = sorted_outcomes[-1] if sorted_outcomes else None
        total_pnl_fraction = sum(o.pnl_fraction for o in self._canary_outcomes)
        comparison = self.get_outcome_comparison()
        return {
            "summary": {
                "total_canary_trades": len(self._canary_outcomes),
                "total_pnl": round(total_pnl, 8),
                "avg_pnl_per_trade": round(avg_pnl, 8),
                "total_pnl_fraction": round(total_pnl_fraction, 6),
                "wins": wins,
                "losses": losses,
                "breakeven": breakeven,
                "win_rate_pct": round(win_rate, 2),
                "best_trade": best.to_dict() if best else None,
                "worst_trade": worst.to_dict() if worst else None,
            },
            "canary_outcomes": [o.to_dict() for o in self._canary_outcomes],
            "comparison": comparison.to_dict(),
        }

    def reset_outcomes(self) -> None:
        """Clear all outcome tracking data."""
        self._canary_outcomes.clear()
        self._baseline_outcomes.clear()
        logger.info("[RUNTIME_INTEGRATION] Outcome history cleared")

    def get_current_mode(self) -> IntegrationMode:
        """Get the current operating mode.

        Returns:
            Current IntegrationMode (SHADOW, CANARY, or FULL)
        """
        return self._current_mode

    def get_mode_transition_status(self) -> dict[str, Any]:
        """Get the current mode transition state machine status.

        Returns:
            Dictionary with mode, consecutive non-regression count,
            required checks, and whether promotion is available
        """
        promotion_ready = (
            self._current_mode == IntegrationMode.CANARY
            and self._consecutive_non_regression_count
            >= self.REQUIRED_CONSECUTIVE_CHECKS
        )

        return {
            "current_mode": self._current_mode.value,
            "consecutive_non_regression_count": self._consecutive_non_regression_count,
            "required_consecutive_checks": self.REQUIRED_CONSECUTIVE_CHECKS,
            "promotion_ready": promotion_ready,
            "promote_threshold": self.PROMOTE_THRESHOLD,
            "demote_threshold": self.DEMOTE_THRESHOLD,
            "consecutive_non_regression_history": self._consecutive_non_regression_history[
                -10:
            ],
        }

    def _update_consecutive_non_regression(
        self, passed: bool, divergence_score: float
    ) -> None:
        """Update the consecutive non-regression counter.

        Args:
            passed: Whether non-regression check passed
            divergence_score: Current divergence score
        """
        if passed:
            self._consecutive_non_regression_count += 1
        else:
            # Reset counter on non-regression failure
            self._consecutive_non_regression_count = 0

        self._consecutive_non_regression_history.append(
            self._consecutive_non_regression_count
        )

        # Trim history if needed
        if len(self._consecutive_non_regression_history) > 100:
            self._consecutive_non_regression_history = (
                self._consecutive_non_regression_history[-100:]
            )

        logger.debug(
            "[RUNTIME_INTEGRATION] Non-regression count: %d/%d (passed=%s, divergence=%.3f)",
            self._consecutive_non_regression_count,
            self.REQUIRED_CONSECUTIVE_CHECKS,
            passed,
            divergence_score,
        )

    def _create_explanation_packet(
        self,
        decision_type: str,
        summary: str,
        reasoning_chain: list[str],
        confidence_breakdown: dict[str, float],
        influenced_by: dict[str, Any],
        uncertainty_notes: list[str] | None = None,
        evidence_refs: list[str] | None = None,
    ) -> ExplanationPacket:
        """Create a structured explanation packet for a decision.

        Args:
            decision_type: Type of decision (promotion, demotion, divergence_detected, etc.)
            summary: One-line summary of the decision
            reasoning_chain: Step-by-step reasoning that led to the decision
            confidence_breakdown: Confidence scores for different aspects
            influenced_by: Factors that influenced the decision
            uncertainty_notes: Optional explicit notes about uncertainty
            evidence_refs: Optional list of evidence references

        Returns:
            ExplanationPacket with structured explanation
        """
        return ExplanationPacket(
            decision_type=decision_type,
            summary=summary,
            reasoning_chain=reasoning_chain,
            confidence_breakdown=confidence_breakdown,
            uncertainty_notes=uncertainty_notes or [],
            evidence_refs=evidence_refs or [],
            influenced_by=influenced_by,
        )

    def _log_audit_entry(
        self,
        decision_type: str,
        summary: str,
        explanation: ExplanationPacket,
        divergence_metrics: DivergenceMetrics | None = None,
        success: bool = True,
        error: str | None = None,
    ) -> DecisionAuditEntry:
        """Log a decision audit entry to the in-memory audit trail.

        Args:
            decision_type: Type of decision
            summary: Human-readable summary
            explanation: Structured explanation packet
            divergence_metrics: Optional divergence metrics at time of decision
            success: Whether the decision action succeeded
            error: Optional error message if decision failed

        Returns:
            DecisionAuditEntry that was logged
        """
        entry = DecisionAuditEntry(
            decision_type=decision_type,
            mode=self._current_mode.value,
            summary=summary,
            explanation=explanation,
            divergence_metrics=divergence_metrics,
            success=success,
            error=error,
        )

        self._audit_trail.append(entry)

        # Trim audit trail if needed (keep last 1000 entries)
        if len(self._audit_trail) > 1000:
            self._audit_trail = self._audit_trail[-1000:]

        # Persist to Redis
        self._persist_audit_to_redis(entry)

        logger.info(
            "[RUNTIME_INTEGRATION] Audit entry logged: decision_type=%s, "
            "decision_id=%s, mode=%s, success=%s",
            decision_type,
            entry.decision_id,
            entry.mode,
            success,
        )

        return entry

    def _persist_audit_to_redis(self, entry: DecisionAuditEntry) -> bool:
        """Persist an audit entry to Redis.

        Args:
            entry: The audit entry to persist

        Returns:
            True if persisted successfully, False otherwise
        """
        try:
            from tools.redis_state import (
                redis_state_expire,
                redis_state_set,
                redis_state_zadd,
            )

            key = f"{AUDIT_TRAIL_LIST_KEY}:{entry.decision_id}"
            redis_state_set(key, json.dumps(entry.to_dict()))
            # Set TTL for 30-day retention
            redis_state_expire(key, AUDIT_TRAIL_TTL_SECONDS)

            # Also add to sorted set by timestamp for time-based queries
            timestamp_key = f"{AUDIT_TRAIL_KEY_PREFIX}:by_timestamp"
            try:
                from datetime import datetime

                ts = datetime.fromisoformat(entry.timestamp).timestamp()
                redis_state_zadd(timestamp_key, ts, entry.decision_id)
                redis_state_expire(timestamp_key, AUDIT_TRAIL_TTL_SECONDS)
            except Exception:
                pass  # Timestamp sorting is best-effort

            logger.debug(
                "[RUNTIME_INTEGRATION] Audit entry persisted to Redis: %s",
                entry.decision_id,
            )
            return True
        except ImportError:
            logger.debug(
                "[RUNTIME_INTEGRATION] Redis not available, skipping audit persistence"
            )
            return False
        except Exception as e:
            logger.warning(
                "[RUNTIME_INTEGRATION] Failed to persist audit entry to Redis: %s", e
            )
            return False

    def _emit_decision_event(
        self,
        event_type: str,
        severity: str,
        summary: str,
        impact: str,
        explanation: ExplanationPacket,
    ) -> bool:
        """Emit a Discord event for a key decision.

        Args:
            event_type: Type of event (mode_promotion, mode_demotion, etc.)
            severity: Event severity (low, medium, high, critical)
            summary: Human-readable summary
            impact: Impact description
            explanation: Structured explanation packet

        Returns:
            True if event was emitted successfully, False otherwise
        """
        if self._discord_notifier is None:
            logger.debug(
                "[RUNTIME_INTEGRATION] Discord notifier not set, skipping event emission"
            )
            return False

        try:
            import asyncio

            # Run async emit in sync context
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            success = loop.run_until_complete(
                self._discord_notifier.notify_autocog_event(
                    event_type=event_type,
                    severity=severity,
                    summary=summary,
                    impact=impact,
                    top_metrics=explanation.confidence_breakdown,
                    artifact_path=None,
                    run_id=explanation.decision_id,
                    title=f"Autonomous Decision: {event_type}",
                    evidence_reasoning=explanation.reasoning_chain,
                )
            )

            if success:
                logger.info(
                    "[RUNTIME_INTEGRATION] Discord event emitted: %s (%s)",
                    event_type,
                    severity,
                )
            return success
        except Exception as e:
            logger.warning("[RUNTIME_INTEGRATION] Failed to emit Discord event: %s", e)
            return False

    def _emit_belief_mutation_audit_event(
        self,
        mutation_type: str,
        severity: str,
        summary: str,
        influenced_by: dict[str, Any],
    ) -> None:
        """Emit a belief mutation audit event for mode transitions.

        Args:
            mutation_type: Type of mutation (promote, demote, merge)
            severity: Event severity (low, medium, high, critical)
            summary: Human-readable summary of the event
            influenced_by: Factors that influenced the decision
        """
        audit_writer = BeliefMutationAuditWriter()
        if not audit_writer.is_enabled():
            return

        event = BeliefMutationEvent(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.now(UTC).isoformat(),
            actor="autonomous_cognition",
            belief_key="runtime_integration.mode_transition",
            mutation_type=mutation_type,
            severity=severity,
            old_value={"mode": influenced_by.get("old_mode", "unknown")},
            new_value={"mode": influenced_by.get("new_mode", "unknown")},
            evidence=[
                {
                    "source_type": "system",
                    "summary": summary,
                    "evidence_refs": [],
                }
            ],
            conflict_resolution=None,
            approval_required=audit_writer._determine_approval_required(
                "mode_transition"
            ),
            approval_reason=None,
            applied=True,
            notified=False,
            notification_mode=audit_writer._derive_notification_mode(
                severity,
                audit_writer._determine_approval_required("mode_transition"),
            ),
            notes=None,
        )
        audit_writer.write_mutation_event(event)

    def get_audit_trail_report(self) -> dict[str, Any]:
        """Generate a report of all audit trail entries.

        Returns:
            Dictionary containing audit trail summary and entries
        """
        if not self._audit_trail:
            return {
                "summary": {
                    "total_entries": 0,
                    "decision_type_distribution": {},
                    "success_count": 0,
                    "failure_count": 0,
                    "message": "No audit trail entries recorded yet",
                },
                "entries": [],
            }

        # Count by decision type
        decision_type_counts: dict[str, int] = {}
        success_count = 0
        failure_count = 0

        for entry in self._audit_trail:
            decision_type_counts[entry.decision_type] = (
                decision_type_counts.get(entry.decision_type, 0) + 1
            )
            if entry.success:
                success_count += 1
            else:
                failure_count += 1

        return {
            "summary": {
                "total_entries": len(self._audit_trail),
                "decision_type_distribution": decision_type_counts,
                "success_count": success_count,
                "failure_count": failure_count,
            },
            "entries": [entry.to_dict() for entry in self._audit_trail[-50:]],
        }

    def promote_mode(self) -> tuple[bool, str]:
        """Promote from CANARY to FULL mode.

        Promotion requires:
        1. Currently in CANARY mode
        2. N consecutive non-regression checks passed
        3. Divergence score below promote threshold (0.35)

        Returns:
            Tuple of (promotion_succeeded, reason)
        """
        if self._current_mode != IntegrationMode.CANARY:
            return False, f"not_in_canary_mode_currently_{self._current_mode.value}"

        if self._consecutive_non_regression_count < self.REQUIRED_CONSECUTIVE_CHECKS:
            return False, (
                f"insufficient_consecutive_checks "
                f"{self._consecutive_non_regression_count}/{self.REQUIRED_CONSECUTIVE_CHECKS}"
            )

        # Check hysteresis: promote threshold is 0.35
        # Get most recent divergence score
        recent_score = 0.0
        if self._divergence_history:
            recent_score = self._divergence_history[-1].confidence_divergence
            if recent_score >= self.PROMOTE_THRESHOLD:
                return False, (
                    f"divergence_score_too_high "
                    f"{recent_score:.3f} >= {self.PROMOTE_THRESHOLD}"
                )

        # All conditions met - promote
        old_mode = self._current_mode.value
        self._current_mode = IntegrationMode.FULL
        logger.info(
            "[RUNTIME_INTEGRATION] MODE PROMOTED: CANARY -> FULL "
            "(consecutive_checks=%d, divergence=%.3f)",
            self._consecutive_non_regression_count,
            recent_score,
        )

        # Create audit entry for promotion decision
        explanation = self._create_explanation_packet(
            decision_type="promotion",
            summary=f"Mode promoted from {old_mode} to FULL",
            reasoning_chain=[
                f"Consecutive non-regression checks: {self._consecutive_non_regression_count}/{self.REQUIRED_CONSECUTIVE_CHECKS}",
                f"Recent divergence score: {recent_score:.3f}",
                f"Promotion threshold: {self.PROMOTE_THRESHOLD}",
                "All promotion criteria met",
            ],
            confidence_breakdown={
                "consecutive_checks_confidence": min(
                    self._consecutive_non_regression_count
                    / self.REQUIRED_CONSECUTIVE_CHECKS,
                    1.0,
                ),
                "divergence_confidence": 1.0
                - min(recent_score / self.PROMOTE_THRESHOLD, 1.0),
            },
            influenced_by={
                "old_mode": old_mode,
                "new_mode": "full",
                "consecutive_checks": self._consecutive_non_regression_count,
                "divergence_score": recent_score,
            },
        )

        self._log_audit_entry(
            decision_type="promotion",
            summary=f"Mode promoted from {old_mode} to FULL",
            explanation=explanation,
            divergence_metrics=(
                self._divergence_history[-1] if self._divergence_history else None
            ),
            success=True,
        )

        # Emit Discord event for promotion
        self._emit_decision_event(
            event_type="mode_promotion",
            severity="medium",
            summary=f"Mode promoted from {old_mode} to FULL",
            impact=f"Neuro-symbolic influence now active with {self._consecutive_non_regression_count} consecutive checks",
            explanation=explanation,
        )

        # Emit belief mutation audit event for mode promotion
        self._emit_belief_mutation_audit_event(
            mutation_type="promote",
            severity="medium",
            summary=f"Mode promoted from {old_mode} to FULL",
            influenced_by={
                "old_mode": old_mode,
                "new_mode": "full",
                "consecutive_checks": self._consecutive_non_regression_count,
                "divergence_score": recent_score,
            },
        )

        return True, "promotion_succeeded"

    def check_auto_demotion(
        self, divergence_score: float | None = None
    ) -> tuple[bool, str]:
        """Check if automatic demotion to canary is required due to drift.

        Auto-demotion occurs when:
        1. Currently in FULL mode
        2. Divergence score >= demote threshold (0.40)

        Args:
            divergence_score: Optional explicit divergence score to check.
                            If None, uses the most recent from history.

        Returns:
            Tuple of (demotion_triggered, reason)
        """
        if self._current_mode != IntegrationMode.FULL:
            return False, "not_in_full_mode"

        # Get the divergence score to check
        score_to_check = divergence_score
        if score_to_check is None and self._divergence_history:
            score_to_check = max(
                self._divergence_history[-1].confidence_divergence,
                self._divergence_history[-1].prediction_drift,
            )
        elif score_to_check is None:
            return False, "no_divergence_data_available"

        # Check hysteresis: demote threshold is 0.40
        if score_to_check >= self.DEMOTE_THRESHOLD:
            self._current_mode = IntegrationMode.CANARY
            self._consecutive_non_regression_count = 0
            logger.warning(
                "[RUNTIME_INTEGRATION] AUTO-DEMOTED: FULL -> CANARY "
                "(divergence=%.3f >= %.3f, consecutive_checks_reset)",
                score_to_check,
                self.DEMOTE_THRESHOLD,
            )

            # Emit belief mutation audit event for mode demotion
            self._emit_belief_mutation_audit_event(
                mutation_type="demote",
                severity="high",
                summary="Mode auto-demoted from FULL to CANARY due to drift",
                influenced_by={
                    "old_mode": "full",
                    "new_mode": "canary",
                    "divergence_score": score_to_check,
                    "demote_threshold": self.DEMOTE_THRESHOLD,
                },
            )

            return True, f"drift_detected_{score_to_check:.3f}"

        return False, "drift_within_tolerance"

    def shutdown(self) -> None:
        """Shutdown the integrator and cleanup resources."""
        if self._orchestrator is not None:
            try:
                self._orchestrator.shutdown()
            except Exception as e:
                logger.warning("[RUNTIME_INTEGRATION] Error during shutdown: %s", e)
        self._orchestrator = None
        logger.info("[RUNTIME_INTEGRATION] Shutdown complete")
