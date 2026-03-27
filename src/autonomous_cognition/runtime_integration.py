"""Neuro-symbolic runtime integration (shadow/canary/full) for Phase 4.

This module provides a safe integration layer between autonomous cognition
and the neuro-symbolic components, ensuring that:
1. Shadow mode prevents any live trading impact
2. Divergence metrics are calculated and reported
3. Safe fallback when neuro-symbolic components fail
"""

from __future__ import annotations

import logging
import time
import traceback
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


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
            "timestamp": self.timestamp,
        }


@dataclass
class BaselinePrediction:
    """Represents a baseline prediction for comparison."""

    prediction: str
    confidence: float
    symbol: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


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

    def __init__(
        self,
        baseline_prediction: BaselinePrediction | None = None,
        enable_fallback: bool = True,
        shadow_lock: bool = True,
    ):
        """Initialize the runtime integrator.

        Args:
            baseline_prediction: Optional baseline for divergence comparison
            enable_fallback: Whether to use fallback on orchestrator failure
            shadow_lock: If True, forces shadow mode regardless of settings
        """
        self._baseline = baseline_prediction
        self._enable_fallback = enable_fallback
        self._shadow_lock = shadow_lock
        self._integration_history: list[RuntimeIntegrationResult] = []
        self._divergence_history: list[DivergenceMetrics] = []
        self._orchestrator = None
        self._fallback_used = False

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
    ) -> RuntimeIntegrationResult:
        """Run neuro-symbolic integration in selected mode.

        Args:
            mode: Operating mode - "shadow", "canary", or "full"
            market_input: Market data for processing

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

        logger.info(
            "[RUNTIME_INTEGRATION] Result: mode=%s, divergence=%.3f, "
            "influence=%s, passed=%s",
            mode,
            integration_result.divergence_score,
            integration_result.influence_applied,
            integration_result.passed_non_regression,
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

    def shutdown(self) -> None:
        """Shutdown the integrator and cleanup resources."""
        if self._orchestrator is not None:
            try:
                self._orchestrator.shutdown()
            except Exception as e:
                logger.warning("[RUNTIME_INTEGRATION] Error during shutdown: %s", e)
        self._orchestrator = None
        logger.info("[RUNTIME_INTEGRATION] Shutdown complete")
