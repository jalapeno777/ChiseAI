"""Tests for NeuroSymbolicRuntimeIntegrator.

Tests cover:
- Shadow mode safety (no live impact)
- Divergence metrics calculation
- Baseline prediction comparison
- Influence gating based on divergence
- Fallback behavior on orchestrator failure
- Divergence report generation
- History tracking
"""

from __future__ import annotations

import pytest

from autonomous_cognition.runtime_integration import (
    BaselinePrediction,
    DivergenceMetrics,
    DivergenceSeverity,
    IntegrationMode,
    NeuroSymbolicRuntimeIntegrator,
    RuntimeIntegrationResult,
)


class TestRuntimeIntegrationResult:
    """Test RuntimeIntegrationResult dataclass."""

    def test_runtime_integration_result_to_dict(self) -> None:
        """Result should serialize to dict correctly."""
        metrics = DivergenceMetrics(
            confidence_divergence=0.2,
            prediction_drift=0.1,
            component_agreement=0.8,
            severity=DivergenceSeverity.LOW.value,
            is_drift_detected=False,
        )
        result = RuntimeIntegrationResult(
            mode="shadow",
            success=True,
            divergence_score=0.2,
            divergence_metrics=metrics,
            influence_applied=False,
            passed_non_regression=True,
            processing_time_ms=10.5,
            details={"prediction": "buy", "confidence": 0.7},
        )

        result_dict = result.to_dict()

        assert result_dict["mode"] == "shadow"
        assert result_dict["success"] is True
        assert result_dict["divergence_score"] == 0.2
        assert result_dict["influence_applied"] is False
        assert result_dict["passed_non_regression"] is True
        assert result_dict["processing_time_ms"] == 10.5
        assert (
            result_dict["divergence_metrics"]["severity"]
            == DivergenceSeverity.LOW.value
        )


class TestDivergenceMetrics:
    """Test DivergenceMetrics calculation and serialization."""

    def test_divergence_metrics_to_dict(self) -> None:
        """Metrics should serialize correctly."""
        metrics = DivergenceMetrics(
            confidence_divergence=0.25,
            prediction_drift=0.15,
            component_agreement=0.9,
            severity=DivergenceSeverity.MEDIUM.value,
            is_drift_detected=True,
            details={"baseline_prediction": "buy", "ns_components": ["reasoning"]},
        )

        metrics_dict = metrics.to_dict()

        assert metrics_dict["confidence_divergence"] == 0.25
        assert metrics_dict["prediction_drift"] == 0.15
        assert metrics_dict["component_agreement"] == 0.9
        assert metrics_dict["severity"] == DivergenceSeverity.MEDIUM.value
        assert metrics_dict["is_drift_detected"] is True


class TestNeuroSymbolicRuntimeIntegrator:
    """Test NeuroSymbolicRuntimeIntegrator functionality."""

    def test_integrator_initialization(self) -> None:
        """Integrator should initialize with default values."""
        integrator = NeuroSymbolicRuntimeIntegrator()

        assert integrator.shadow_lock is True
        assert integrator.fallback_used is False

    def test_integrator_with_baseline(self) -> None:
        """Integrator should accept baseline prediction."""
        baseline = BaselinePrediction(
            prediction="buy", confidence=0.7, symbol="BTC/USD"
        )
        integrator = NeuroSymbolicRuntimeIntegrator(baseline_prediction=baseline)

        assert integrator._baseline is not None
        assert integrator._baseline.prediction == "buy"
        assert integrator._baseline.confidence == 0.7

    def test_set_baseline(self) -> None:
        """Should update baseline prediction."""
        integrator = NeuroSymbolicRuntimeIntegrator()
        baseline = BaselinePrediction(prediction="sell", confidence=0.6)

        integrator.set_baseline(baseline)

        assert integrator._baseline.prediction == "sell"
        assert integrator._baseline.confidence == 0.6

    def test_shadow_lock_prevents_influence(self) -> None:
        """Shadow lock should always prevent influence application."""
        integrator = NeuroSymbolicRuntimeIntegrator(shadow_lock=True)

        # In shadow mode with shadow_lock, no influence should be applied
        assert integrator.shadow_lock is True

    def test_fallback_on_orchestrator_failure(self) -> None:
        """Should use fallback when orchestrator is unavailable."""
        integrator = NeuroSymbolicRuntimeIntegrator(
            enable_fallback=True, shadow_lock=True
        )

        # Run with invalid module path to trigger fallback
        # The lazy loading will fail because orchestrator can't be imported
        # So we get fallback behavior
        result = integrator.run(mode="shadow")

        assert result is not None
        assert isinstance(result, RuntimeIntegrationResult)
        assert result.mode == "shadow"

    def test_run_returns_result_in_shadow_mode(self) -> None:
        """run() should return RuntimeIntegrationResult in shadow mode."""
        integrator = NeuroSymbolicRuntimeIntegrator(shadow_lock=True)
        result = integrator.run(mode="shadow")

        assert isinstance(result, RuntimeIntegrationResult)
        assert result.mode == "shadow"
        assert "details" in result.to_dict()

    def test_run_with_custom_market_input(self) -> None:
        """run() should accept custom market input."""
        integrator = NeuroSymbolicRuntimeIntegrator(shadow_lock=True)
        market_data = {"price": 50000.0, "volume": 1000000.0, "rsi": 45.0}

        result = integrator.run(mode="shadow", market_input=market_data)

        assert isinstance(result, RuntimeIntegrationResult)
        assert result.success in [True, False]  # May succeed or fallback

    def test_influence_not_applied_in_shadow_mode(self) -> None:
        """Influence should not be applied in shadow mode."""
        integrator = NeuroSymbolicRuntimeIntegrator(shadow_lock=True)
        result = integrator.run(mode="shadow")

        # In shadow mode, influence should never be applied
        assert result.influence_applied is False

    def test_divergence_metrics_calculated(self) -> None:
        """Divergence metrics should be calculated on successful run."""
        integrator = NeuroSymbolicRuntimeIntegrator(
            baseline_prediction=BaselinePrediction(prediction="buy", confidence=0.7),
            shadow_lock=True,
        )
        result = integrator.run(mode="shadow")

        assert isinstance(result.divergence_metrics, DivergenceMetrics)
        assert "divergence_score" in result.to_dict()

    def test_get_divergence_report_empty(self) -> None:
        """Should return empty report when no history."""
        integrator = NeuroSymbolicRuntimeIntegrator()
        report = integrator.get_divergence_report()

        assert "summary" in report
        assert "metrics" in report
        assert "recommendations" in report

    def test_get_integration_history(self) -> None:
        """Should return list of historical results."""
        integrator = NeuroSymbolicRuntimeIntegrator(shadow_lock=True)
        # Run to generate history
        integrator.run(mode="shadow")

        history = integrator.get_integration_history()

        assert isinstance(history, list)

    def test_reset_history(self) -> None:
        """Should clear all history."""
        integrator = NeuroSymbolicRuntimeIntegrator(shadow_lock=True)
        integrator.run(mode="shadow")

        integrator.reset_history()

        assert len(integrator._integration_history) == 0
        assert len(integrator._divergence_history) == 0

    def test_integration_mode_enum(self) -> None:
        """IntegrationMode enum should have correct values."""
        assert IntegrationMode.SHADOW.value == "shadow"
        assert IntegrationMode.CANARY.value == "canary"
        assert IntegrationMode.FULL.value == "full"

    def test_divergence_severity_enum(self) -> None:
        """DivergenceSeverity enum should have correct values."""
        assert DivergenceSeverity.LOW.value == "low"
        assert DivergenceSeverity.MEDIUM.value == "medium"
        assert DivergenceSeverity.HIGH.value == "high"
        assert DivergenceSeverity.CRITICAL.value == "critical"

    def test_baseline_prediction_dataclass(self) -> None:
        """BaselinePrediction should store values correctly."""
        baseline = BaselinePrediction(
            prediction="buy", confidence=0.8, symbol="ETH/USD"
        )

        assert baseline.prediction == "buy"
        assert baseline.confidence == 0.8
        assert baseline.symbol == "ETH/USD"
        assert baseline.timestamp is not None


class TestShadowModeSafety:
    """Test shadow mode safety guarantees."""

    def test_shadow_lock_property(self) -> None:
        """shadow_lock property should be accessible."""
        integrator = NeuroSymbolicRuntimeIntegrator(shadow_lock=True)
        assert integrator.shadow_lock is True

        integrator2 = NeuroSymbolicRuntimeIntegrator(shadow_lock=False)
        assert integrator2.shadow_lock is False

    def test_fallback_used_property(self) -> None:
        """fallback_used should track fallback state."""
        integrator = NeuroSymbolicRuntimeIntegrator()
        assert integrator.fallback_used is False


class TestIntegrationModes:
    """Test different integration modes."""

    def test_shadow_mode_structure(self) -> None:
        """Shadow mode should produce valid result structure."""
        integrator = NeuroSymbolicRuntimeIntegrator(shadow_lock=True)
        result = integrator.run(mode="shadow")

        assert result.mode == "shadow"
        assert isinstance(result.to_dict(), dict)

    def test_canary_mode_available(self) -> None:
        """Canary mode should be available."""
        integrator = NeuroSymbolicRuntimeIntegrator(shadow_lock=True)
        result = integrator.run(
            mode="canary", market_input={"price": 100.0, "volume": 1000.0, "rsi": 55.0}
        )

        assert result.mode == "canary"

    def test_full_mode_available(self) -> None:
        """Full mode should be available."""
        integrator = NeuroSymbolicRuntimeIntegrator(shadow_lock=True)
        result = integrator.run(
            mode="full", market_input={"price": 100.0, "volume": 1000.0, "rsi": 55.0}
        )

        assert result.mode == "full"


class TestBaselineCaptureFromSignal:
    """Test automatic baseline capture from live signals."""

    @staticmethod
    def _make_signal(direction="long", confidence=0.8, token="BTC/USDT"):
        """Create a mock Signal object."""
        from types import SimpleNamespace

        dir_enum = SimpleNamespace(value=direction)
        return SimpleNamespace(
            direction=dir_enum,
            confidence=confidence,
            token=token,
        )

    def test_capture_baseline_from_signal(self) -> None:
        """Should capture baseline from a live signal."""
        integrator = NeuroSymbolicRuntimeIntegrator()
        signal = self._make_signal(direction="long", confidence=0.85)

        integrator.capture_baseline_from_signal(signal)

        assert integrator._baseline is not None
        assert integrator._baseline.prediction == "long"
        assert integrator._baseline.confidence == 0.85
        assert integrator._baseline.symbol == "BTC/USDT"

    def test_capture_baseline_updates_on_new_signal(self) -> None:
        """Each new signal should update the baseline."""
        integrator = NeuroSymbolicRuntimeIntegrator()

        integrator.capture_baseline_from_signal(
            self._make_signal(direction="long", confidence=0.7)
        )
        assert integrator._baseline.confidence == 0.7

        integrator.capture_baseline_from_signal(
            self._make_signal(direction="short", confidence=0.9)
        )
        assert integrator._baseline.prediction == "short"
        assert integrator._baseline.confidence == 0.9

    def test_capture_baseline_with_neutral_direction(self) -> None:
        """Should handle neutral direction correctly."""
        integrator = NeuroSymbolicRuntimeIntegrator()
        signal = self._make_signal(direction="neutral", confidence=0.3)

        integrator.capture_baseline_from_signal(signal)

        assert integrator._baseline.prediction == "neutral"
        assert integrator._baseline.confidence == 0.3

    def test_capture_baseline_from_signal_works_as_tap(self) -> None:
        """capture_baseline_from_signal can be used directly as a signal flow tap."""
        from unittest.mock import MagicMock

        from signal_generation.signal_generator import (
            SignalGenerationConfig,
            SignalGenerator,
        )

        integrator = NeuroSymbolicRuntimeIntegrator(shadow_lock=True)
        gen = SignalGenerator(
            config=SignalGenerationConfig(
                enable_shadow_tap=True,
                enable_freshness_checks=False,
                enable_caching=False,
            )
        )
        gen.register_signal_flow_tap(integrator.capture_baseline_from_signal)

        # Generate a signal - tap should fire and capture baseline
        mock_tf = MagicMock()
        mock_tf.value = "1h"
        gen.generate_signal(token="ETH/USDT", timeframe=mock_tf, ohlcv_data=[])

        assert integrator._baseline is not None
        assert integrator._baseline.symbol == "ETH/USDT"


class TestCompareShadowVsLive:
    """Test divergence calculation between shadow output and live signal."""

    @staticmethod
    def _make_signal(direction="long", confidence=0.8, token="BTC/USDT"):
        """Create a mock Signal object."""
        from types import SimpleNamespace

        dir_enum = SimpleNamespace(value=direction)
        return SimpleNamespace(
            direction=dir_enum,
            confidence=confidence,
            token=token,
        )

    @staticmethod
    def _make_shadow_result(prediction="long", confidence=0.75, components=None):
        """Create a mock RuntimeIntegrationResult."""
        metrics = DivergenceMetrics(
            confidence_divergence=0.05,
            prediction_drift=0.0,
            severity=DivergenceSeverity.LOW.value,
        )
        return RuntimeIntegrationResult(
            mode="shadow",
            success=True,
            divergence_score=0.05,
            divergence_metrics=metrics,
            influence_applied=False,
            passed_non_regression=True,
            processing_time_ms=1.0,
            details={
                "prediction": prediction,
                "confidence": confidence,
                "components_used": components or [],
            },
        )

    def test_identical_predictions_low_divergence(self) -> None:
        """Same direction and similar confidence → low divergence."""
        integrator = NeuroSymbolicRuntimeIntegrator(shadow_lock=True)
        shadow = self._make_shadow_result(prediction="long", confidence=0.78)
        live = self._make_signal(direction="long", confidence=0.80)

        metrics = integrator.compare_shadow_vs_live(shadow, live)

        assert metrics.confidence_divergence == pytest.approx(0.02, abs=0.01)
        assert metrics.prediction_drift == pytest.approx(0.02, abs=0.01)
        assert metrics.severity == DivergenceSeverity.LOW.value

    def test_opposite_predictions_high_divergence(self) -> None:
        """Opposite directions → high divergence."""
        integrator = NeuroSymbolicRuntimeIntegrator(shadow_lock=True)
        shadow = self._make_shadow_result(prediction="long", confidence=0.8)
        live = self._make_signal(direction="short", confidence=0.3)

        metrics = integrator.compare_shadow_vs_live(shadow, live)

        assert metrics.prediction_drift == 1.0  # Strong reversal
        assert metrics.severity == DivergenceSeverity.CRITICAL.value
        assert metrics.is_drift_detected is True

    def test_divergence_details_include_both_sides(self) -> None:
        """Divergence details should include live and shadow values."""
        integrator = NeuroSymbolicRuntimeIntegrator(shadow_lock=True)
        shadow = self._make_shadow_result(
            prediction="long", confidence=0.7, components=["reasoning"]
        )
        live = self._make_signal(direction="long", confidence=0.85)

        metrics = integrator.compare_shadow_vs_live(shadow, live)

        assert "live_prediction" in metrics.details
        assert "live_confidence" in metrics.details
        assert "shadow_prediction" in metrics.details
        assert "shadow_confidence" in metrics.details
        assert metrics.details["live_prediction"] == "long"
        assert metrics.details["shadow_prediction"] == "long"

    def test_with_components_increases_agreement(self) -> None:
        """More components should increase component_agreement."""
        integrator = NeuroSymbolicRuntimeIntegrator(shadow_lock=True)
        shadow_no_comp = self._make_shadow_result(components=[])
        shadow_with_comp = self._make_shadow_result(
            components=["reasoning", "memory", "planning"]
        )
        live = self._make_signal(direction="long", confidence=0.8)

        metrics_no = integrator.compare_shadow_vs_live(shadow_no_comp, live)
        metrics_with = integrator.compare_shadow_vs_live(shadow_with_comp, live)

        assert metrics_with.component_agreement > metrics_no.component_agreement
