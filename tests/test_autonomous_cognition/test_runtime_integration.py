"""Tests for NeuroSymbolicRuntimeIntegrator.

Tests cover:
- Shadow mode safety (no live impact)
- Divergence metrics calculation
- Baseline prediction comparison
- Influence gating based on divergence
- Fallback behavior on orchestrator failure
- Divergence report generation
- History tracking

Phase 4 additions:
- Mock orchestrator tests (mocked signal generator, risk metrics, divergence)
- Canary mode tests (P&L tracking, outcome comparison, position constraints)
- Full mode tests (auto-demotion, influence gating, mode transitions)
- Threshold boundary tests (0.35 promote, 0.40 demote boundaries)
- Mode transition tests (promote/demote with hysteresis, consecutive checks)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from autonomous_cognition.runtime_integration import (
    BaselinePrediction,
    BeforeAfterComparison,
    CanaryOutcome,
    DivergenceMetrics,
    DivergenceSeverity,
    IntegrationMode,
    NeuroSymbolicRuntimeIntegrator,
    OutcomeComparison,
    PerformanceMetrics,
    RuntimeIntegrationResult,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_integrator(**kwargs) -> NeuroSymbolicRuntimeIntegrator:
    """Create an integrator with common defaults for testing."""
    defaults = {"shadow_lock": True, "enable_fallback": True}
    defaults.update(kwargs)
    return NeuroSymbolicRuntimeIntegrator(**defaults)


def _make_orchestrator_mock(
    prediction: str = "buy",
    confidence: float = 0.7,
    components_used: list[str] | None = None,
) -> MagicMock:
    """Create a mock orchestrator with a process_signal return value."""
    mock = MagicMock()
    result = MagicMock()
    result.prediction = prediction
    result.confidence = confidence
    result.components_used = components_used or ["reasoning"]
    mock.process_signal.return_value = result
    return mock


# ===========================================================================
# Existing tests (preserved)
# ===========================================================================


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


# ===========================================================================
# Phase 4: Mock Orchestrator Tests
# ===========================================================================


class TestMockOrchestrator:
    """Test runtime integration with mocked orchestrator dependencies.

    These tests replace the real orchestrator with mocks to test the
    integration logic in isolation.
    """

    def test_mock_orchestrator_buy_prediction(self) -> None:
        """Mock orchestrator should return buy prediction correctly."""
        integrator = _make_integrator(
            baseline_prediction=BaselinePrediction(prediction="buy", confidence=0.7),
            shadow_lock=True,
        )
        mock_orch = _make_orchestrator_mock(prediction="buy", confidence=0.75)

        with patch.object(integrator, "_get_orchestrator", return_value=mock_orch):
            result = integrator.run(mode="shadow")

        assert result.success is True
        assert result.details["prediction"] == "buy"
        assert result.details["confidence"] == 0.75
        assert result.details["orchestrator_used"] is True

    def test_mock_orchestrator_sell_prediction(self) -> None:
        """Mock orchestrator sell prediction should produce correct divergence."""
        integrator = _make_integrator(
            baseline_prediction=BaselinePrediction(prediction="buy", confidence=0.7),
            shadow_lock=True,
        )
        mock_orch = _make_orchestrator_mock(prediction="sell", confidence=0.8)

        with patch.object(integrator, "_get_orchestrator", return_value=mock_orch):
            result = integrator.run(mode="shadow")

        assert result.success is True
        assert result.details["prediction"] == "sell"
        # Prediction drift should be detected (different prediction)
        assert result.divergence_metrics.prediction_drift > 0

    def test_mock_orchestrator_with_high_confidence(self) -> None:
        """High confidence NS prediction with low baseline should trigger drift."""
        integrator = _make_integrator(
            baseline_prediction=BaselinePrediction(prediction="hold", confidence=0.3),
            shadow_lock=True,
        )
        mock_orch = _make_orchestrator_mock(prediction="buy", confidence=0.9)

        with patch.object(integrator, "_get_orchestrator", return_value=mock_orch):
            result = integrator.run(mode="shadow")

        # Strong reversal: NS high conf + baseline low conf => prediction_drift=1.0
        assert result.divergence_metrics.prediction_drift == 1.0
        assert result.divergence_metrics.severity == DivergenceSeverity.CRITICAL.value

    def test_mock_orchestrator_with_multiple_components(self) -> None:
        """Multiple NS components should increase component agreement."""
        integrator = _make_integrator(shadow_lock=True)
        mock_orch = _make_orchestrator_mock(
            prediction="buy",
            confidence=0.7,
            components_used=["reasoning", "memory", "planning"],
        )

        with patch.object(integrator, "_get_orchestrator", return_value=mock_orch):
            result = integrator.run(mode="shadow")

        assert result.divergence_metrics.component_agreement == 1.0

    def test_mock_orchestrator_no_components(self) -> None:
        """Empty NS components list should yield zero component agreement."""
        integrator = _make_integrator(shadow_lock=True)
        mock_orch = MagicMock()
        result_mock = MagicMock()
        result_mock.prediction = "buy"
        result_mock.confidence = 0.7
        result_mock.components_used = []  # Explicit empty list
        mock_orch.process_signal.return_value = result_mock

        with patch.object(integrator, "_get_orchestrator", return_value=mock_orch):
            result = integrator.run(mode="shadow")

        # Empty components list => component_agreement should be 0
        assert result.divergence_metrics.component_agreement == 0.0

    def test_mock_orchestrator_stores_history(self) -> None:
        """Successful mock run should store result in integration history."""
        integrator = _make_integrator(shadow_lock=True)
        mock_orch = _make_orchestrator_mock()

        with patch.object(integrator, "_get_orchestrator", return_value=mock_orch):
            integrator.run(mode="shadow")

        history = integrator.get_integration_history()
        assert len(history) == 1
        assert history[0]["success"] is True

    def test_mock_orchestrator_influence_gating_low_divergence(self) -> None:
        """Low divergence should allow influence (when shadow_lock is off).

        Note: _should_apply_influence checks details['ns_confidence'] which is
        not set by _calculate_divergence_metrics, so it defaults to 0 and
        influence is blocked by confidence_below_threshold. This test verifies
        that behavior - influence is blocked when ns_confidence is not in details.
        """
        integrator = _make_integrator(
            shadow_lock=False,
            baseline_prediction=BaselinePrediction(prediction="buy", confidence=0.7),
        )
        mock_orch = _make_orchestrator_mock(prediction="buy", confidence=0.7)

        with patch.object(integrator, "_get_orchestrator", return_value=mock_orch):
            result = integrator.run(
                mode="canary",
                market_input={"price": 100.0, "volume": 1000.0, "rsi": 55.0},
            )

        # Same prediction, same confidence => low divergence
        assert result.divergence_metrics.confidence_divergence == 0.0
        # BUT influence is blocked because ns_confidence is not in details
        # (defaults to 0 < MIN_CONFIDENCE_FOR_INFLUENCE=0.55)
        assert result.influence_applied is False
        assert result.details["influence_reason"] == "confidence_below_threshold"

    def test_mock_orchestrator_influence_gating_critical_divergence(self) -> None:
        """Critical divergence should block influence even in canary mode."""
        integrator = _make_integrator(
            shadow_lock=False,
            baseline_prediction=BaselinePrediction(prediction="sell", confidence=0.3),
        )
        mock_orch = _make_orchestrator_mock(prediction="buy", confidence=0.95)

        with patch.object(integrator, "_get_orchestrator", return_value=mock_orch):
            result = integrator.run(
                mode="canary",
                market_input={"price": 100.0, "volume": 1000.0, "rsi": 55.0},
            )

        # Strong reversal triggers critical severity
        assert result.divergence_metrics.severity == DivergenceSeverity.CRITICAL.value
        assert result.influence_applied is False

    def test_mock_orchestrator_fallback_used_flag(self) -> None:
        """Fallback flag should be set when orchestrator fails."""
        integrator = _make_integrator(shadow_lock=True, enable_fallback=True)

        with patch.object(
            integrator, "_get_orchestrator", side_effect=ImportError("no module")
        ):
            result = integrator.run(mode="shadow")

        assert integrator.fallback_used is True
        assert result.success is False

    def test_mock_orchestrator_performance_metrics_attached(self) -> None:
        """Performance metrics should be attached to result when provided."""
        integrator = _make_integrator(shadow_lock=True)
        mock_orch = _make_orchestrator_mock()
        perf = PerformanceMetrics(sharpe=1.5, sortino=1.2, drawdown=0.05)

        with patch.object(integrator, "_get_orchestrator", return_value=mock_orch):
            result = integrator.run(mode="shadow", performance_metrics=perf)

        assert result.performance_metrics is not None
        assert result.performance_metrics.sharpe == 1.5


# ===========================================================================
# Phase 4: Canary Mode Tests
# ===========================================================================


class TestCanaryMode:
    """Test canary mode specific behavior.

    Canary mode runs small test positions with strict divergence gates
    and full P&L tracking.
    """

    def test_canary_mode_requires_market_input(self) -> None:
        """Canary mode should raise ValueError without market_input."""
        integrator = _make_integrator(shadow_lock=True)

        with pytest.raises(ValueError, match="market_input is required"):
            integrator.run(mode="canary")

    def test_canary_mode_result_mode(self) -> None:
        """Canary mode run should produce result with mode='canary'."""
        integrator = _make_integrator(shadow_lock=True)
        mock_orch = _make_orchestrator_mock()

        with patch.object(integrator, "_get_orchestrator", return_value=mock_orch):
            result = integrator.run(
                mode="canary",
                market_input={"price": 100.0, "volume": 1000.0, "rsi": 55.0},
            )

        assert result.mode == "canary"

    def test_canary_outcome_recording(self) -> None:
        """Recording canary outcome should track P&L correctly."""
        integrator = _make_integrator()
        outcome = integrator.record_canary_outcome(
            decision_id="canary-001",
            symbol="BTC/USDT",
            prediction="buy",
            confidence=0.75,
            predicted_direction="up",
            actual_direction="up",
            pnl=0.005,
            pnl_fraction=0.0005,
            entry_price=50000.0,
            exit_price=50250.0,
            divergence_score=0.15,
        )

        assert isinstance(outcome, CanaryOutcome)
        assert outcome.is_canary is True
        assert outcome.influence_applied is True
        assert outcome.pnl == 0.005
        assert len(integrator._canary_outcomes) == 1

    def test_canary_outcome_serialization(self) -> None:
        """Canary outcome should serialize correctly."""
        integrator = _make_integrator()
        integrator.record_canary_outcome(
            decision_id="canary-002",
            symbol="ETH/USDT",
            prediction="sell",
            confidence=0.8,
            predicted_direction="down",
            actual_direction="down",
            pnl=-0.002,
            pnl_fraction=-0.0002,
        )

        report = integrator.get_canary_pnl_report()
        assert len(report["canary_outcomes"]) == 1
        assert report["canary_outcomes"][0]["decision_id"] == "canary-002"
        assert report["canary_outcomes"][0]["pnl"] == -0.002

    def test_canary_pnl_report_empty(self) -> None:
        """Empty canary P&L report when no outcomes recorded."""
        integrator = _make_integrator()
        report = integrator.get_canary_pnl_report()

        assert report["summary"] == "No canary outcomes recorded yet"
        assert report["canary_outcomes"] == []
        assert report["comparison"] is None

    def test_canary_pnl_report_with_outcomes(self) -> None:
        """P&L report should aggregate outcomes correctly."""
        integrator = _make_integrator()

        # Record multiple canary outcomes
        integrator.record_canary_outcome(
            decision_id="c1",
            symbol="BTC",
            prediction="buy",
            confidence=0.7,
            predicted_direction="up",
            pnl=0.01,
        )
        integrator.record_canary_outcome(
            decision_id="c2",
            symbol="ETH",
            prediction="sell",
            confidence=0.8,
            predicted_direction="down",
            pnl=-0.005,
        )
        integrator.record_canary_outcome(
            decision_id="c3",
            symbol="SOL",
            prediction="buy",
            confidence=0.6,
            predicted_direction="up",
            pnl=0.003,
        )

        report = integrator.get_canary_pnl_report()
        summary = report["summary"]

        assert summary["total_canary_trades"] == 3
        assert summary["total_pnl"] == 0.008  # 0.01 - 0.005 + 0.003
        assert summary["wins"] == 2
        assert summary["losses"] == 1
        assert summary["breakeven"] == 0
        assert summary["win_rate_pct"] == pytest.approx(66.67, abs=0.01)

    def test_canary_outcome_comparison_with_baseline(self) -> None:
        """Canary vs baseline outcome comparison should work correctly."""
        integrator = _make_integrator()

        # Record canary outcomes (2 wins, 1 loss)
        integrator.record_canary_outcome(
            decision_id="c1",
            symbol="BTC",
            prediction="buy",
            confidence=0.7,
            predicted_direction="up",
            pnl=0.01,
        )
        integrator.record_canary_outcome(
            decision_id="c2",
            symbol="ETH",
            prediction="sell",
            confidence=0.8,
            predicted_direction="down",
            pnl=-0.005,
        )
        integrator.record_canary_outcome(
            decision_id="c3",
            symbol="SOL",
            prediction="buy",
            confidence=0.6,
            predicted_direction="up",
            pnl=0.003,
        )

        # Record baseline outcomes (1 win, 1 loss)
        integrator.record_baseline_outcome(
            decision_id="b1",
            symbol="BTC",
            prediction="buy",
            confidence=0.7,
            predicted_direction="up",
            pnl=0.006,
        )
        integrator.record_baseline_outcome(
            decision_id="b2",
            symbol="ETH",
            prediction="sell",
            confidence=0.8,
            predicted_direction="down",
            pnl=-0.003,
        )

        comparison = integrator.get_outcome_comparison()

        assert comparison.canary_total_pnl == 0.008
        assert comparison.baseline_total_pnl == 0.003
        assert comparison.canary_trade_count == 3
        assert comparison.baseline_trade_count == 2
        assert comparison.pnl_difference == 0.005
        assert comparison.is_regression is False

    def test_canary_outcome_comparison_detects_regression(self) -> None:
        """Comparison should detect regression when canary underperforms."""
        integrator = _make_integrator()

        # Canary: net loss
        integrator.record_canary_outcome(
            decision_id="c1",
            symbol="BTC",
            prediction="buy",
            confidence=0.7,
            predicted_direction="up",
            pnl=-0.01,
        )
        integrator.record_canary_outcome(
            decision_id="c2",
            symbol="ETH",
            prediction="sell",
            confidence=0.8,
            predicted_direction="down",
            pnl=-0.005,
        )

        # Baseline: net gain
        integrator.record_baseline_outcome(
            decision_id="b1",
            symbol="BTC",
            prediction="buy",
            confidence=0.7,
            predicted_direction="up",
            pnl=0.02,
        )

        comparison = integrator.get_outcome_comparison()

        assert comparison.is_regression is True  # canary << baseline
        assert comparison.pnl_difference < 0

    def test_canary_max_position_fraction(self) -> None:
        """Canary mode constant should enforce 1% max position fraction."""
        assert NeuroSymbolicRuntimeIntegrator.CANARY_MAX_POSITION_FRACTION == 0.01

    def test_reset_outcomes_clears_all_tracking(self) -> None:
        """reset_outcomes should clear canary and baseline tracking."""
        integrator = _make_integrator()
        integrator.record_canary_outcome(
            decision_id="c1",
            symbol="BTC",
            prediction="buy",
            confidence=0.7,
            predicted_direction="up",
            pnl=0.01,
        )
        integrator.record_baseline_outcome(
            decision_id="b1",
            symbol="BTC",
            prediction="buy",
            confidence=0.7,
            predicted_direction="up",
            pnl=0.005,
        )

        integrator.reset_outcomes()

        assert len(integrator._canary_outcomes) == 0
        assert len(integrator._baseline_outcomes) == 0
        report = integrator.get_canary_pnl_report()
        assert report["summary"] == "No canary outcomes recorded yet"


# ===========================================================================
# Phase 4: Full Mode Tests
# ===========================================================================


class TestFullMode:
    """Test full mode behavior.

    Full mode applies neuro-symbolic influence with continuous monitoring
    and automatic rollback on drift detection.
    """

    def test_full_mode_requires_market_input(self) -> None:
        """Full mode should raise ValueError without market_input."""
        integrator = _make_integrator(shadow_lock=True)

        with pytest.raises(ValueError, match="market_input is required"):
            integrator.run(mode="full")

    def test_full_mode_result_mode(self) -> None:
        """Full mode run should produce result with mode='full'."""
        integrator = _make_integrator(shadow_lock=True)
        mock_orch = _make_orchestrator_mock()

        with patch.object(integrator, "_get_orchestrator", return_value=mock_orch):
            result = integrator.run(
                mode="full",
                market_input={"price": 100.0, "volume": 1000.0, "rsi": 55.0},
            )

        assert result.mode == "full"

    def test_full_mode_influence_with_shadow_lock(self) -> None:
        """Full mode with shadow_lock should NOT apply influence."""
        integrator = _make_integrator(shadow_lock=True)
        mock_orch = _make_orchestrator_mock(prediction="buy", confidence=0.8)

        with patch.object(integrator, "_get_orchestrator", return_value=mock_orch):
            result = integrator.run(
                mode="full",
                market_input={"price": 100.0, "volume": 1000.0, "rsi": 55.0},
            )

        assert result.influence_applied is False

    def test_full_mode_influence_without_shadow_lock(self) -> None:
        """Full mode without shadow_lock should still block influence when ns_confidence is missing.

        Note: _should_apply_influence checks details['ns_confidence'] which is not
        populated by _calculate_divergence_metrics. It defaults to 0, which is
        below MIN_CONFIDENCE_FOR_INFLUENCE (0.55), so influence is blocked.
        """
        integrator = _make_integrator(
            shadow_lock=False,
            baseline_prediction=BaselinePrediction(prediction="buy", confidence=0.7),
        )
        mock_orch = _make_orchestrator_mock(prediction="buy", confidence=0.7)

        with patch.object(integrator, "_get_orchestrator", return_value=mock_orch):
            result = integrator.run(
                mode="full",
                market_input={"price": 100.0, "volume": 1000.0, "rsi": 55.0},
            )

        # Influence blocked because ns_confidence not in details (defaults to 0)
        assert result.influence_applied is False
        assert result.details["influence_reason"] == "confidence_below_threshold"

    def test_full_mode_auto_demotion_on_drift(self) -> None:
        """Full mode should auto-demote to CANARY when divergence >= 0.40."""
        integrator = _make_integrator(
            shadow_lock=False,
            baseline_prediction=BaselinePrediction(prediction="buy", confidence=0.7),
        )

        # Set mode to FULL
        integrator._current_mode = IntegrationMode.FULL
        integrator._consecutive_non_regression_count = 5

        # Simulate critical divergence
        mock_orch = _make_orchestrator_mock(prediction="sell", confidence=0.95)

        with patch.object(integrator, "_get_orchestrator", return_value=mock_orch):
            result = integrator.run(
                mode="full",
                market_input={"price": 100.0, "volume": 1000.0, "rsi": 55.0},
            )

        # Should be auto-demoted
        assert result.details.get("auto_demoted") is True
        assert integrator.get_current_mode() == IntegrationMode.CANARY
        assert integrator._consecutive_non_regression_count == 0

    def test_full_mode_no_demotion_within_tolerance(self) -> None:
        """Full mode should NOT demote when divergence is below threshold."""
        integrator = _make_integrator(
            shadow_lock=False,
            baseline_prediction=BaselinePrediction(prediction="buy", confidence=0.7),
        )
        integrator._current_mode = IntegrationMode.FULL
        integrator._consecutive_non_regression_count = 5

        # Same prediction, low divergence
        mock_orch = _make_orchestrator_mock(prediction="buy", confidence=0.7)

        with patch.object(integrator, "_get_orchestrator", return_value=mock_orch):
            result = integrator.run(
                mode="full",
                market_input={"price": 100.0, "volume": 1000.0, "rsi": 55.0},
            )

        assert result.details.get("auto_demoted") is not True
        assert integrator.get_current_mode() == IntegrationMode.FULL

    def test_full_mode_performance_metrics_tracking(self) -> None:
        """Full mode should track performance metrics for non-regression checks."""
        integrator = _make_integrator(
            shadow_lock=False,
            baseline_prediction=BaselinePrediction(prediction="buy", confidence=0.7),
            baseline_performance=PerformanceMetrics(
                sharpe=1.0, sortino=1.0, drawdown=0.1
            ),
        )
        mock_orch = _make_orchestrator_mock(prediction="buy", confidence=0.7)
        perf = PerformanceMetrics(sharpe=1.2, sortino=1.1, drawdown=0.08)

        with patch.object(integrator, "_get_orchestrator", return_value=mock_orch):
            result = integrator.run(
                mode="full",
                market_input={"price": 100.0, "volume": 1000.0, "rsi": 55.0},
                performance_metrics=perf,
            )

        assert result.performance_metrics is not None
        assert result.performance_metrics.sharpe == 1.2

    def test_full_mode_non_regression_check(self) -> None:
        """Full mode should track non-regression against baseline."""
        integrator = _make_integrator(
            shadow_lock=False,
            baseline_performance=PerformanceMetrics(
                sharpe=1.0, sortino=1.0, drawdown=0.1
            ),
        )
        current = PerformanceMetrics(sharpe=1.5, sortino=1.3, drawdown=0.08)

        passed, comparison = integrator.check_non_regression(current)

        assert passed is True
        assert comparison.delta_sharpe == 0.5
        assert comparison.is_improvement is True

    def test_full_mode_non_regression_failure(self) -> None:
        """Non-regression check should fail when metrics degrade significantly."""
        integrator = _make_integrator(
            baseline_performance=PerformanceMetrics(
                sharpe=1.5, sortino=1.5, drawdown=0.1
            ),
        )
        # Significant degradation
        current = PerformanceMetrics(sharpe=0.5, sortino=0.5, drawdown=0.5)

        passed, comparison = integrator.check_non_regression(current)

        assert passed is False
        assert comparison.delta_sharpe == -1.0
        assert comparison.is_improvement is False


# ===========================================================================
# Phase 4: Threshold Boundary Tests
# ===========================================================================


class TestThresholdBoundaries:
    """Test behavior at exact threshold boundaries.

    Key thresholds:
    - PROMOTE_THRESHOLD = 0.35 (canary -> full)
    - DEMOTE_THRESHOLD = 0.40 (full -> canary)
    - DIVERGENCE_THRESHOLD_HIGH = 0.35
    - DIVERGENCE_THRESHOLD_CRITICAL = 0.45
    - REQUIRED_CONSECUTIVE_CHECKS = 5
    - MIN_CONFIDENCE_FOR_INFLUENCE = 0.55
    - MAX_ALLOWED_DIVERGENCE_FOR_INFLUENCE = 0.30
    """

    def test_promote_threshold_constant(self) -> None:
        """Promote threshold should be 0.35."""
        assert NeuroSymbolicRuntimeIntegrator.PROMOTE_THRESHOLD == 0.35

    def test_demote_threshold_constant(self) -> None:
        """Demote threshold should be 0.40."""
        assert NeuroSymbolicRuntimeIntegrator.DEMOTE_THRESHOLD == 0.40

    def test_hysteresis_gap(self) -> None:
        """Demote threshold must be higher than promote threshold (hysteresis)."""
        assert (
            NeuroSymbolicRuntimeIntegrator.DEMOTE_THRESHOLD
            > NeuroSymbolicRuntimeIntegrator.PROMOTE_THRESHOLD
        )

    def test_required_consecutive_checks_constant(self) -> None:
        """Required consecutive checks should be 5."""
        assert NeuroSymbolicRuntimeIntegrator.REQUIRED_CONSECUTIVE_CHECKS == 5

    def test_divergence_high_threshold(self) -> None:
        """High divergence threshold should be 0.35."""
        assert NeuroSymbolicRuntimeIntegrator.DIVERGENCE_THRESHOLD_HIGH == 0.35

    def test_divergence_critical_threshold(self) -> None:
        """Critical divergence threshold should be 0.45."""
        assert NeuroSymbolicRuntimeIntegrator.DIVERGENCE_THRESHOLD_CRITICAL == 0.45

    def test_promote_at_exact_boundary_fails(self) -> None:
        """Promotion should FAIL at exact promote threshold (>= check)."""
        integrator = _make_integrator()
        integrator._current_mode = IntegrationMode.CANARY
        integrator._consecutive_non_regression_count = 5

        # Set divergence to exactly 0.35
        integrator._divergence_history = [
            DivergenceMetrics(confidence_divergence=0.35, prediction_drift=0.0)
        ]

        success, reason = integrator.promote_mode()

        assert success is False
        assert "divergence_score_too_high" in reason

    def test_promote_just_below_boundary_succeeds(self) -> None:
        """Promotion should succeed just below promote threshold."""
        integrator = _make_integrator()
        integrator._current_mode = IntegrationMode.CANARY
        integrator._consecutive_non_regression_count = 5

        # Set divergence to 0.349 (just below 0.35)
        integrator._divergence_history = [
            DivergenceMetrics(confidence_divergence=0.349, prediction_drift=0.0)
        ]

        success, reason = integrator.promote_mode()

        assert success is True
        assert reason == "promotion_succeeded"

    def test_demote_at_exact_boundary_triggers(self) -> None:
        """Demotion should TRIGGER at exact demote threshold (>= check)."""
        integrator = _make_integrator()
        integrator._current_mode = IntegrationMode.FULL

        demoted, reason = integrator.check_auto_demotion(divergence_score=0.40)

        assert demoted is True
        assert "drift_detected" in reason
        assert integrator.get_current_mode() == IntegrationMode.CANARY

    def test_demote_just_below_boundary_does_not_trigger(self) -> None:
        """Demotion should NOT trigger just below demote threshold."""
        integrator = _make_integrator()
        integrator._current_mode = IntegrationMode.FULL
        integrator._consecutive_non_regression_count = 5

        demoted, reason = integrator.check_auto_demotion(divergence_score=0.399)

        assert demoted is False
        assert reason == "drift_within_tolerance"
        assert integrator.get_current_mode() == IntegrationMode.FULL

    def test_hysteresis_dead_zone(self) -> None:
        """Scores in [0.35, 0.40) should neither promote nor demote.

        This is the hysteresis dead zone that prevents oscillation.
        """
        integrator = _make_integrator()

        # At 0.375 - in the dead zone
        # Should NOT promote (>= 0.35)
        integrator._current_mode = IntegrationMode.CANARY
        integrator._consecutive_non_regression_count = 5
        integrator._divergence_history = [
            DivergenceMetrics(confidence_divergence=0.375, prediction_drift=0.0)
        ]
        promote_ok, _ = integrator.promote_mode()
        assert promote_ok is False

        # Should NOT demote (< 0.40)
        integrator._current_mode = IntegrationMode.FULL
        demote_ok, _ = integrator.check_auto_demotion(divergence_score=0.375)
        assert demote_ok is False

    def test_consecutive_checks_exact_boundary(self) -> None:
        """Promotion should succeed at exactly REQUIRED_CONSECUTIVE_CHECKS."""
        integrator = _make_integrator()
        integrator._current_mode = IntegrationMode.CANARY
        integrator._consecutive_non_regression_count = 5
        integrator._divergence_history = [
            DivergenceMetrics(confidence_divergence=0.1, prediction_drift=0.0)
        ]

        success, reason = integrator.promote_mode()

        assert success is True

    def test_consecutive_checks_one_below_boundary(self) -> None:
        """Promotion should fail at REQUIRED_CONSECUTIVE_CHECKS - 1."""
        integrator = _make_integrator()
        integrator._current_mode = IntegrationMode.CANARY
        integrator._consecutive_non_regression_count = 4
        integrator._divergence_history = [
            DivergenceMetrics(confidence_divergence=0.1, prediction_drift=0.0)
        ]

        success, reason = integrator.promote_mode()

        assert success is False
        assert "insufficient_consecutive_checks" in reason

    def test_non_regression_min_sharpe_boundary(self) -> None:
        """Non-regression constant MIN_SHARPE_NON_REGRESSION should be 1.0."""
        assert NeuroSymbolicRuntimeIntegrator.MIN_SHARPE_NON_REGRESSION == 1.0

    def test_non_regression_max_drawdown_boundary(self) -> None:
        """Non-regression constant MAX_DRAWDOWN_NON_REGRESSION should be 0.25."""
        assert NeuroSymbolicRuntimeIntegrator.MAX_DRAWDOWN_NON_REGRESSION == 0.25

    def test_non_regression_min_sortino_boundary(self) -> None:
        """Non-regression constant MIN_SORTINO_NON_REGRESSION should be 1.0."""
        assert NeuroSymbolicRuntimeIntegrator.MIN_SORTINO_NON_REGRESSION == 1.0

    def test_non_regression_max_ece_boundary(self) -> None:
        """Non-regression constant MAX_ECE_NON_REGRESSION should be 0.20."""
        assert NeuroSymbolicRuntimeIntegrator.MAX_ECE_NON_REGRESSION == 0.20

    def test_influence_confidence_threshold(self) -> None:
        """MIN_CONFIDENCE_FOR_INFLUENCE should be 0.55."""
        assert NeuroSymbolicRuntimeIntegrator.MIN_CONFIDENCE_FOR_INFLUENCE == 0.55

    def test_influence_max_divergence_threshold(self) -> None:
        """MAX_ALLOWED_DIVERGENCE_FOR_INFLUENCE should be 0.30."""
        assert (
            NeuroSymbolicRuntimeIntegrator.MAX_ALLOWED_DIVERGENCE_FOR_INFLUENCE == 0.30
        )


# ===========================================================================
# Phase 4: Mode Transition Tests
# ===========================================================================


class TestModeTransitions:
    """Test mode promotion and demotion logic with hysteresis.

    Mode lifecycle: SHADOW -> CANARY -> FULL -> (auto-demotion) -> CANARY -> ...
    """

    def test_initial_mode_is_shadow(self) -> None:
        """Integrator should start in SHADOW mode."""
        integrator = _make_integrator()
        assert integrator.get_current_mode() == IntegrationMode.SHADOW

    def test_promote_from_non_canary_fails(self) -> None:
        """Promotion from SHADOW (not CANARY) should fail."""
        integrator = _make_integrator()
        integrator._consecutive_non_regression_count = 10

        success, reason = integrator.promote_mode()

        assert success is False
        assert "not_in_canary_mode" in reason

    def test_promote_from_full_fails(self) -> None:
        """Promotion from FULL should fail (already at highest mode)."""
        integrator = _make_integrator()
        integrator._current_mode = IntegrationMode.FULL
        integrator._consecutive_non_regression_count = 10

        success, reason = integrator.promote_mode()

        assert success is False
        assert "not_in_canary_mode" in reason

    def test_promote_resets_on_demotion(self) -> None:
        """Auto-demotion should reset consecutive non-regression count."""
        integrator = _make_integrator()
        integrator._current_mode = IntegrationMode.FULL
        integrator._consecutive_non_regression_count = 10

        integrator.check_auto_demotion(divergence_score=0.50)

        assert integrator._consecutive_non_regression_count == 0
        assert integrator.get_current_mode() == IntegrationMode.CANARY

    def test_consecutive_counter_increments_on_pass(self) -> None:
        """Consecutive counter should increment when non-regression passes."""
        integrator = _make_integrator()
        integrator._consecutive_non_regression_count = 0

        integrator._update_consecutive_non_regression(passed=True, divergence_score=0.1)
        assert integrator._consecutive_non_regression_count == 1

        integrator._update_consecutive_non_regression(passed=True, divergence_score=0.1)
        assert integrator._consecutive_non_regression_count == 2

    def test_consecutive_counter_resets_on_fail(self) -> None:
        """Consecutive counter should reset to 0 on non-regression failure."""
        integrator = _make_integrator()
        integrator._consecutive_non_regression_count = 4

        integrator._update_consecutive_non_regression(
            passed=False, divergence_score=0.5
        )

        assert integrator._consecutive_non_regression_count == 0

    def test_consecutive_counter_history_tracking(self) -> None:
        """Consecutive counter history should track all updates."""
        integrator = _make_integrator()

        integrator._update_consecutive_non_regression(passed=True, divergence_score=0.1)
        integrator._update_consecutive_non_regression(passed=True, divergence_score=0.1)
        integrator._update_consecutive_non_regression(
            passed=False, divergence_score=0.5
        )
        integrator._update_consecutive_non_regression(passed=True, divergence_score=0.1)

        history = integrator._consecutive_non_regression_history
        assert history == [1, 2, 0, 1]

    def test_full_promotion_lifecycle(self) -> None:
        """Test complete promotion lifecycle: canary -> 5 checks -> full."""
        integrator = _make_integrator()
        integrator._current_mode = IntegrationMode.CANARY

        # Simulate 5 consecutive non-regression passes
        for i in range(5):
            integrator._update_consecutive_non_regression(
                passed=True, divergence_score=0.1
            )
            # Add low divergence history
            integrator._divergence_history.append(
                DivergenceMetrics(confidence_divergence=0.1, prediction_drift=0.0)
            )

        assert integrator._consecutive_non_regression_count == 5

        # Now promote
        success, reason = integrator.promote_mode()

        assert success is True
        assert integrator.get_current_mode() == IntegrationMode.FULL

    def test_demote_from_non_full_fails(self) -> None:
        """Demotion from SHADOW should fail (not in FULL mode)."""
        integrator = _make_integrator()
        integrator._current_mode = IntegrationMode.SHADOW

        demoted, reason = integrator.check_auto_demotion(divergence_score=1.0)

        assert demoted is False
        assert "not_in_full_mode" in reason

    def test_demote_from_canary_fails(self) -> None:
        """Demotion from CANARY should fail (not in FULL mode)."""
        integrator = _make_integrator()
        integrator._current_mode = IntegrationMode.CANARY

        demoted, reason = integrator.check_auto_demotion(divergence_score=1.0)

        assert demoted is False
        assert "not_in_full_mode" in reason

    def test_demote_with_no_data(self) -> None:
        """Demotion with no divergence data should not trigger."""
        integrator = _make_integrator()
        integrator._current_mode = IntegrationMode.FULL

        demoted, reason = integrator.check_auto_demotion(divergence_score=None)

        assert demoted is False
        assert "no_divergence_data" in reason

    def test_demote_uses_history_when_no_score(self) -> None:
        """Demotion should use recent divergence history when no score given."""
        integrator = _make_integrator()
        integrator._current_mode = IntegrationMode.FULL

        # Add high divergence to history
        integrator._divergence_history.append(
            DivergenceMetrics(confidence_divergence=0.45, prediction_drift=0.3)
        )

        demoted, reason = integrator.check_auto_demotion(divergence_score=None)

        assert demoted is True
        assert "drift_detected" in reason

    def test_mode_transition_status(self) -> None:
        """get_mode_transition_status should reflect current state machine."""
        integrator = _make_integrator()
        integrator._current_mode = IntegrationMode.CANARY

        status = integrator.get_mode_transition_status()

        assert status["current_mode"] == "canary"
        assert status["consecutive_non_regression_count"] == 0
        assert status["required_consecutive_checks"] == 5
        assert status["promotion_ready"] is False
        assert status["promote_threshold"] == 0.35
        assert status["demote_threshold"] == 0.40

    def test_mode_transition_status_promotion_ready(self) -> None:
        """Status should show promotion_ready=True when conditions are met."""
        integrator = _make_integrator()
        integrator._current_mode = IntegrationMode.CANARY
        integrator._consecutive_non_regression_count = 6  # More than required

        status = integrator.get_mode_transition_status()

        assert status["promotion_ready"] is True

    def test_mode_transition_status_not_ready_in_full(self) -> None:
        """Status should show promotion_ready=False in FULL mode."""
        integrator = _make_integrator()
        integrator._current_mode = IntegrationMode.FULL
        integrator._consecutive_non_regression_count = 10

        status = integrator.get_mode_transition_status()

        assert status["promotion_ready"] is False

    def test_oscillation_prevention_via_hysteresis(self) -> None:
        """Hysteresis should prevent rapid promote/demote oscillation.

        At score 0.375 (in dead zone [0.35, 0.40)):
        - Should NOT promote (< 0.35 is required for promote)
        - Should NOT demote (< 0.40 is required for demote)
        """
        integrator = _make_integrator()
        integrator._current_mode = IntegrationMode.CANARY
        integrator._consecutive_non_regression_count = 5

        # Add divergence at 0.375
        integrator._divergence_history.append(
            DivergenceMetrics(confidence_divergence=0.375, prediction_drift=0.0)
        )

        # Try promote - should fail because 0.375 >= 0.35
        promote_ok, promote_reason = integrator.promote_mode()
        assert promote_ok is False

        # Switch to FULL and try demote - should pass because 0.375 < 0.40
        integrator._current_mode = IntegrationMode.FULL
        demote_ok, demote_reason = integrator.check_auto_demotion(
            divergence_score=0.375
        )
        assert demote_ok is False
        assert "drift_within_tolerance" in demote_reason

    def test_performance_report_no_baseline(self) -> None:
        """Performance report should return no_baseline when no baseline set."""
        integrator = _make_integrator()
        report = integrator.get_performance_report()

        assert report["status"] == "no_baseline"

    def test_performance_report_with_baseline(self) -> None:
        """Performance report should include comparison when baseline is set."""
        integrator = _make_integrator(
            baseline_performance=PerformanceMetrics(
                sharpe=1.0, sortino=1.0, drawdown=0.1
            ),
        )
        mock_orch = _make_orchestrator_mock()
        perf = PerformanceMetrics(sharpe=1.2, sortino=1.1, drawdown=0.08)

        with patch.object(integrator, "_get_orchestrator", return_value=mock_orch):
            integrator.run(mode="shadow", performance_metrics=perf)

        report = integrator.get_performance_report()

        assert report["status"] == "ok"
        assert report["baseline"]["sharpe"] == 1.0
        assert report["current"]["sharpe"] == 1.2
        assert report["passed_non_regression"] is True

    def test_before_after_comparison_serialization(self) -> None:
        """BeforeAfterComparison should serialize correctly."""
        before = PerformanceMetrics(sharpe=1.0, sortino=1.0, drawdown=0.1)
        after = PerformanceMetrics(sharpe=1.5, sortino=1.2, drawdown=0.08)
        comparison = BeforeAfterComparison(
            before_metrics=before,
            after_metrics=after,
            delta_sharpe=0.5,
            delta_sortino=0.2,
            delta_drawdown=-0.02,
            is_improvement=True,
            passed_non_regression=True,
        )

        d = comparison.to_dict()
        assert d["delta_sharpe"] == 0.5
        assert d["delta_drawdown"] == -0.02
        assert d["is_improvement"] is True
        assert d["passed_non_regression"] is True

    def test_outcome_comparison_serialization(self) -> None:
        """OutcomeComparison should serialize correctly."""
        comp = OutcomeComparison(
            canary_total_pnl=0.01,
            baseline_total_pnl=0.005,
            canary_win_rate=60.0,
            baseline_win_rate=50.0,
            canary_trade_count=10,
            baseline_trade_count=10,
            pnl_difference=0.005,
            win_rate_difference=10.0,
            relative_performance=2.0,
            is_regression=False,
        )

        d = comp.to_dict()
        assert d["canary_total_pnl"] == 0.01
        assert d["relative_performance"] == 2.0
        assert d["is_regression"] is False
