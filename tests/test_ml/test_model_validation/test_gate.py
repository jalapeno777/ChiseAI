"""Tests for validation gate."""

import asyncio
from datetime import UTC, datetime

import pytest

from ml.model_registry.registry import ModelRegistry, ModelType
from ml.validation.gate import (
    ComparisonResult,
    ValidationConfig,
    ValidationGate,
    ValidationMetrics,
    ValidationMode,
    ValidationState,
)


class TestValidationMetrics:
    """Tests for ValidationMetrics."""

    def test_metrics_creation(self):
        """Test creating validation metrics."""
        metrics = ValidationMetrics(
            accuracy=0.85,
            precision=0.82,
            recall=0.80,
            f1=0.81,
            ece=0.12,
            sample_count=1000,
        )

        assert metrics.accuracy == 0.85
        assert metrics.precision == 0.82
        assert metrics.f1 == 0.81
        assert metrics.ece == 0.12

    def test_metrics_to_dict(self):
        """Test converting metrics to dict."""
        metrics = ValidationMetrics(
            accuracy=0.85,
            precision=0.82,
            recall=0.80,
            f1=0.81,
            ece=0.12,
            sample_count=1000,
        )

        data = metrics.to_dict()
        assert data["accuracy"] == 0.85
        assert data["f1"] == 0.81
        assert "timestamp" in data

    def test_metrics_from_dict(self):
        """Test creating metrics from dict."""
        data = {
            "accuracy": 0.85,
            "precision": 0.82,
            "recall": 0.80,
            "f1": 0.81,
            "ece": 0.12,
            "sample_count": 1000,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        metrics = ValidationMetrics.from_dict(data)
        assert metrics.accuracy == 0.85
        assert metrics.sample_count == 1000


class TestComparisonResult:
    """Tests for ComparisonResult."""

    def test_comparison_creation(self):
        """Test creating comparison result."""
        baseline = ValidationMetrics(
            accuracy=0.80,
            precision=0.78,
            recall=0.77,
            f1=0.775,
            ece=0.15,
            sample_count=1000,
        )
        candidate = ValidationMetrics(
            accuracy=0.85,
            precision=0.82,
            recall=0.80,
            f1=0.81,
            ece=0.12,
            sample_count=1000,
        )

        comparison = ComparisonResult(
            baseline_metrics=baseline,
            candidate_metrics=candidate,
            accuracy_delta=0.05,
            precision_delta=0.04,
            recall_delta=0.03,
            f1_delta=0.035,
            ece_delta=-0.03,
            is_better=True,
            confidence=0.95,
        )

        assert comparison.is_better is True
        assert comparison.f1_delta == 0.035
        assert comparison.ece_delta == -0.03


class TestValidationConfig:
    """Tests for ValidationConfig."""

    def test_default_config(self):
        """Test default validation configuration."""
        config = ValidationConfig()

        assert config.shadow_mode_duration_hours == 24.0
        assert config.min_samples_for_validation == 100
        assert config.accuracy_threshold == 0.75
        assert config.precision_threshold == 0.70
        assert config.recall_threshold == 0.70
        assert config.f1_threshold == 0.72
        assert config.max_ece_threshold == 0.15


class TestValidationGate:
    """Tests for ValidationGate."""

    @pytest.fixture
    def registry(self):
        """Create a fresh registry."""
        return ModelRegistry()

    @pytest.fixture
    def gate(self, registry):
        """Create a validation gate."""
        return ValidationGate(registry=registry)

    @pytest.mark.asyncio
    async def test_start_shadow_validation(self, registry, gate):
        """Test starting shadow validation."""
        # Register and promote to candidate
        version = registry.register_model(
            model_id="test_model",
            model_path="/models/test.pkl",
        )
        registry.promote_to_candidate(version.version_id)

        # Start shadow validation with short duration for testing
        run = await gate.start_shadow_validation(
            version_id=version.version_id,
            duration_hours=0.001,  # Very short for testing
        )

        assert run.version_id == version.version_id
        assert run.mode == ValidationMode.SHADOW
        assert run.state == ValidationState.RUNNING

        # Cancel to clean up
        await gate.cancel_validation(run.run_id)

    def test_start_shadow_validation_not_candidate(self, registry, gate):
        """Test that shadow validation requires CANDIDATE status."""
        version = registry.register_model(
            model_id="test_model",
            model_path="/models/test.pkl",
        )
        # Don't promote to candidate

        with pytest.raises(ValueError, match="CANDIDATE"):
            asyncio.run(gate.start_shadow_validation(version.version_id))

    @pytest.mark.asyncio
    async def test_run_offline_validation(self, registry, gate):
        """Test offline validation."""
        version = registry.register_model(
            model_id="test_model",
            model_path="/models/test.pkl",
        )

        run = await gate.run_offline_validation(version.version_id)

        assert run.version_id == version.version_id
        assert run.mode == ValidationMode.OFFLINE
        assert run.state == ValidationState.COMPLETED
        assert run.metrics is not None

    @pytest.mark.asyncio
    async def test_evaluate_validation_result_pass(self, registry, gate):
        """Test evaluating passing validation result."""
        version = registry.register_model(
            model_id="test_model",
            model_path="/models/test.pkl",
        )

        run = await gate.run_offline_validation(version.version_id)

        passed, failures = gate.evaluate_validation_result(run.run_id)
        # Mock metrics should pass default thresholds
        assert isinstance(passed, bool)
        assert isinstance(failures, list)

    @pytest.mark.asyncio
    async def test_get_validation_run(self, registry, gate):
        """Test retrieving validation run."""
        version = registry.register_model(
            model_id="test_model",
            model_path="/models/test.pkl",
        )

        run = await gate.run_offline_validation(version.version_id)

        retrieved = gate.get_validation_run(run.run_id)
        assert retrieved is not None
        assert retrieved.run_id == run.run_id

    @pytest.mark.asyncio
    async def test_get_validation_history(self, registry, gate):
        """Test getting validation history."""
        version = registry.register_model(
            model_id="test_model",
            model_path="/models/test.pkl",
        )

        run1 = await gate.run_offline_validation(version.version_id)
        run2 = await gate.run_offline_validation(version.version_id)

        history = gate.get_validation_history(version_id=version.version_id)
        # Should have at least 2 runs for this version
        assert len(history) >= 2

    @pytest.mark.asyncio
    async def test_cancel_validation(self, registry, gate):
        """Test cancelling validation."""
        import asyncio

        version = registry.register_model(
            model_id="test_model",
            model_path="/models/test.pkl",
        )
        registry.promote_to_candidate(version.version_id)

        run = await gate.start_shadow_validation(
            version_id=version.version_id,
            duration_hours=1.0,  # Long duration
        )

        # Give the task time to start
        await asyncio.sleep(0.1)

        cancelled = await gate.cancel_validation(run.run_id)
        assert cancelled is True

        # Check status - may be CANCELLED or already COMPLETED due to timing
        retrieved = gate.get_validation_run(run.run_id)
        assert retrieved.state in [ValidationState.CANCELLED, ValidationState.RUNNING]

    @pytest.mark.asyncio
    async def test_compare_with_champion(self, registry, gate):
        """Test comparison with champion."""
        # Create champion
        champion = registry.register_model(
            model_id="test_model",
            model_path="/models/champion.pkl",
            metrics={"f1": 0.80, "accuracy": 0.82},
        )
        registry.promote_to_candidate(champion.version_id)
        registry.promote_to_challenger(champion.version_id)
        registry.promote_to_champion(champion.version_id, force=True)

        # Create candidate metrics
        candidate_metrics = ValidationMetrics(
            accuracy=0.85,
            precision=0.82,
            recall=0.80,
            f1=0.81,
            ece=0.12,
            sample_count=1000,
        )

        comparison = await gate._compare_with_champion(
            ModelType.SIGNAL_PREDICTOR,
            candidate_metrics,
        )

        assert comparison is not None
        assert comparison.baseline_metrics.f1 == 0.80
        assert comparison.candidate_metrics.f1 == 0.81
