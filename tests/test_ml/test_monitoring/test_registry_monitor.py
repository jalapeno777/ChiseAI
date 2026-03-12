"""Tests for model registry monitoring.

This module tests the ModelRegistryMonitor class for tracking model versions,
validation gates, shadow mode comparisons, and degradation events.

Acceptance Criteria:
- Model version tracking over time
- Validation gate result logging
- Shadow mode comparison tracking
- Degradation event detection and logging
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import pytest

from ml.monitoring.registry_monitor import (
    DegradationEvent,
    ModelRegistryMonitor,
    ModelVersionInfo,
    ShadowModeRecord,
    ValidationGateRecord,
    ValidationGateStatus,
    ShadowModeResult,
)
from ml.models.model_registry import ModelRegistry

logger = logging.getLogger(__name__)


class TestModelVersionInfo:
    """Tests for ModelVersionInfo dataclass."""

    def test_version_info_creation(self):
        """Test creating model version info."""
        info = ModelVersionInfo(
            model_name="signal_predictor",
            version="1.0.0",
            created_at=datetime.now(timezone.utc),
            metrics={"accuracy": 0.65},
            tags=["production"],
            status="champion",
        )

        assert info.model_name == "signal_predictor"
        assert info.version == "1.0.0"
        assert info.metrics == {"accuracy": 0.65}
        assert info.tags == ["production"]
        assert info.status == "champion"

    def test_version_info_to_dict(self):
        """Test converting version info to dictionary."""
        created = datetime.now(timezone.utc)
        info = ModelVersionInfo(
            model_name="signal_predictor",
            version="1.0.0",
            created_at=created,
            metrics={"accuracy": 0.65},
        )

        result = info.to_dict()

        assert result["model_name"] == "signal_predictor"
        assert result["version"] == "1.0.0"
        assert result["created_at"] == created.isoformat()
        assert result["metrics"] == {"accuracy": 0.65}


class TestValidationGateRecord:
    """Tests for ValidationGateRecord dataclass."""

    def test_gate_record_creation(self):
        """Test creating validation gate record."""
        record = ValidationGateRecord(
            model_name="signal_predictor",
            version="1.0.0",
            gate_name="accuracy_gate",
            status=ValidationGateStatus.PASS,
            metrics={"accuracy": 0.65},
            thresholds={"accuracy": 0.60},
        )

        assert record.model_name == "signal_predictor"
        assert record.gate_name == "accuracy_gate"
        assert record.status == ValidationGateStatus.PASS

    def test_gate_record_to_dict(self):
        """Test converting gate record to dictionary."""
        record = ValidationGateRecord(
            model_name="signal_predictor",
            version="1.0.0",
            gate_name="accuracy_gate",
            status=ValidationGateStatus.FAIL,
        )

        result = record.to_dict()

        assert result["status"] == "fail"
        assert result["gate_name"] == "accuracy_gate"


class TestShadowModeRecord:
    """Tests for ShadowModeRecord dataclass."""

    def test_shadow_record_creation(self):
        """Test creating shadow mode record."""
        record = ShadowModeRecord(
            model_name="signal_predictor",
            champion_version="1.0.0",
            candidate_version="1.1.0",
            result=ShadowModeResult.PROMOTE,
            champion_metrics={"accuracy": 0.65},
            candidate_metrics={"accuracy": 0.70},
            delta={"accuracy": 0.05},
            sample_count=1000,
            duration_hours=24.0,
        )

        assert record.model_name == "signal_predictor"
        assert record.result == ShadowModeResult.PROMOTE
        assert record.delta == {"accuracy": 0.05}

    def test_shadow_record_to_dict(self):
        """Test converting shadow record to dictionary."""
        record = ShadowModeRecord(
            model_name="signal_predictor",
            champion_version="1.0.0",
            candidate_version="1.1.0",
            result=ShadowModeResult.REJECT,
        )

        result = record.to_dict()

        assert result["result"] == "reject"
        assert result["champion_version"] == "1.0.0"


class TestDegradationEvent:
    """Tests for DegradationEvent dataclass."""

    def test_degradation_event_creation(self):
        """Test creating degradation event."""
        event = DegradationEvent(
            model_name="signal_predictor",
            version="1.0.0",
            metric_name="accuracy",
            baseline_value=0.65,
            current_value=0.55,
            degradation_percentage=15.4,
            alert_triggered=True,
        )

        assert event.model_name == "signal_predictor"
        assert event.metric_name == "accuracy"
        assert event.degradation_percentage == 15.4
        assert event.alert_triggered is True

    def test_degradation_event_to_dict(self):
        """Test converting degradation event to dictionary."""
        event = DegradationEvent(
            model_name="signal_predictor",
            version="1.0.0",
            metric_name="accuracy",
            baseline_value=0.65,
            current_value=0.55,
            degradation_percentage=15.4,
        )

        result = event.to_dict()

        assert result["degradation_percentage"] == 15.4
        assert result["alert_triggered"] is False


class TestModelRegistryMonitor:
    """Tests for ModelRegistryMonitor."""

    def test_initialization(self):
        """Test monitor initialization."""
        monitor = ModelRegistryMonitor()

        assert monitor.get_models_summary() == {}

    def test_initialization_with_registry(self):
        """Test monitor initialization with registry."""
        registry = ModelRegistry()
        monitor = ModelRegistryMonitor(registry=registry)

        assert monitor._registry is registry

    def test_record_model_registration(self):
        """Test recording model registration."""
        monitor = ModelRegistryMonitor()

        info = monitor.record_model_registration(
            model_name="signal_predictor",
            version="1.0.0",
            metrics={"accuracy": 0.65, "f1": 0.62},
            tags=["production"],
            training_data="dataset_v1",
        )

        assert info.model_name == "signal_predictor"
        assert info.version == "1.0.0"
        assert info.metrics == {"accuracy": 0.65, "f1": 0.62}

        # Should be in history
        history = monitor.get_version_history("signal_predictor")
        assert len(history) == 1
        assert history[0].version == "1.0.0"

    def test_record_validation_gate(self):
        """Test recording validation gate."""
        monitor = ModelRegistryMonitor()

        record = monitor.record_validation_gate(
            model_name="signal_predictor",
            version="1.0.0",
            gate_name="accuracy_gate",
            passed=True,
            metrics={"accuracy": 0.65},
            thresholds={"accuracy": 0.60},
        )

        assert record.status == ValidationGateStatus.PASS
        assert record.gate_name == "accuracy_gate"

        # Should be in history
        history = monitor.get_validation_history(model_name="signal_predictor")
        assert len(history) == 1

    def test_record_validation_gate_failure(self):
        """Test recording failed validation gate."""
        monitor = ModelRegistryMonitor()

        record = monitor.record_validation_gate(
            model_name="signal_predictor",
            version="1.0.0",
            gate_name="accuracy_gate",
            passed=False,
            metrics={"accuracy": 0.55},
            thresholds={"accuracy": 0.60},
        )

        assert record.status == ValidationGateStatus.FAIL

    def test_record_shadow_mode(self):
        """Test recording shadow mode comparison."""
        monitor = ModelRegistryMonitor()

        record = monitor.record_shadow_mode(
            model_name="signal_predictor",
            champion_version="1.0.0",
            candidate_version="1.1.0",
            result="promote",
            champion_metrics={"accuracy": 0.65},
            candidate_metrics={"accuracy": 0.70},
            delta={"accuracy": 0.05},
            sample_count=1000,
            duration_hours=24.0,
        )

        assert record.result == ShadowModeResult.PROMOTE
        assert record.sample_count == 1000

        # Should be in history
        history = monitor.get_shadow_mode_history(model_name="signal_predictor")
        assert len(history) == 1

    def test_record_shadow_mode_with_enum(self):
        """Test recording shadow mode with enum."""
        monitor = ModelRegistryMonitor()

        record = monitor.record_shadow_mode(
            model_name="signal_predictor",
            champion_version="1.0.0",
            candidate_version="1.1.0",
            result=ShadowModeResult.REJECT,
        )

        assert record.result == ShadowModeResult.REJECT

    def test_record_degradation(self):
        """Test recording degradation event."""
        monitor = ModelRegistryMonitor()

        event = monitor.record_degradation(
            model_name="signal_predictor",
            version="1.0.0",
            metric_name="accuracy",
            baseline_value=0.65,
            current_value=0.55,
            alert_triggered=True,
        )

        assert event.degradation_percentage > 0
        assert event.alert_triggered is True

        # Should be in history
        history = monitor.get_degradation_events(model_name="signal_predictor")
        assert len(history) == 1

    def test_set_baseline(self):
        """Test setting baseline metrics."""
        monitor = ModelRegistryMonitor()

        monitor.set_baseline(
            "signal_predictor",
            "1.0.0",
            {"accuracy": 0.65, "f1": 0.62},
        )

        # Baseline should be used for degradation detection
        events = monitor.check_degradation(
            "signal_predictor",
            "1.0.0",
            {"accuracy": 0.55, "f1": 0.60},
            threshold_percentage=10.0,
        )

        assert len(events) >= 1
        assert any(e.metric_name == "accuracy" for e in events)

    def test_check_degradation_no_baseline(self):
        """Test degradation check without baseline."""
        monitor = ModelRegistryMonitor()

        events = monitor.check_degradation(
            "signal_predictor",
            "1.0.0",
            {"accuracy": 0.55},
            threshold_percentage=10.0,
        )

        assert len(events) == 0

    def test_check_degradation_no_degradation(self):
        """Test degradation check with no actual degradation."""
        monitor = ModelRegistryMonitor()

        monitor.set_baseline(
            "signal_predictor",
            "1.0.0",
            {"accuracy": 0.65},
        )

        # Current value is better than baseline
        events = monitor.check_degradation(
            "signal_predictor",
            "1.0.0",
            {"accuracy": 0.70},
            threshold_percentage=10.0,
        )

        assert len(events) == 0

    def test_get_validation_history_filtering(self):
        """Test validation history filtering."""
        monitor = ModelRegistryMonitor()

        # Record gates for different models
        monitor.record_validation_gate("model_a", "1.0.0", "gate1", True)
        monitor.record_validation_gate("model_b", "1.0.0", "gate1", True)
        monitor.record_validation_gate("model_a", "1.1.0", "gate2", False)

        # Filter by model
        history_a = monitor.get_validation_history(model_name="model_a")
        assert len(history_a) == 2

        # Filter by version
        history_v1 = monitor.get_validation_history(version="1.0.0")
        assert len(history_v1) == 2

        # Filter by gate name
        history_gate1 = monitor.get_validation_history(gate_name="gate1")
        assert len(history_gate1) == 2

    def test_get_shadow_mode_history_filtering(self):
        """Test shadow mode history filtering."""
        monitor = ModelRegistryMonitor()

        monitor.record_shadow_mode(
            "model_a", "1.0.0", "1.1.0", ShadowModeResult.PROMOTE
        )
        monitor.record_shadow_mode("model_b", "1.0.0", "1.1.0", ShadowModeResult.REJECT)

        history_a = monitor.get_shadow_mode_history(model_name="model_a")
        assert len(history_a) == 1
        assert history_a[0].model_name == "model_a"

    def test_get_degradation_events_filtering(self):
        """Test degradation events filtering."""
        monitor = ModelRegistryMonitor()

        monitor.record_degradation("model_a", "1.0.0", "accuracy", 0.65, 0.55)
        monitor.record_degradation("model_a", "1.1.0", "f1", 0.62, 0.50)
        monitor.record_degradation("model_b", "1.0.0", "accuracy", 0.70, 0.60)

        # Filter by model
        events_a = monitor.get_degradation_events(model_name="model_a")
        assert len(events_a) == 2

        # Filter by version
        events_v1 = monitor.get_degradation_events(version="1.0.0")
        assert len(events_v1) == 2

    def test_get_models_summary(self):
        """Test getting models summary."""
        monitor = ModelRegistryMonitor()

        # Register models
        info_a1 = monitor.record_model_registration("model_a", "1.0.0")
        info_a1.status = "champion"
        info_a2 = monitor.record_model_registration("model_a", "1.1.0")
        info_a2.status = "challenger"
        info_b1 = monitor.record_model_registration("model_b", "1.0.0")
        info_b1.status = "champion"

        # Record validation gates
        monitor.record_validation_gate("model_a", "1.0.0", "gate1", True)
        monitor.record_validation_gate("model_a", "1.1.0", "gate1", False)

        # Record degradation
        monitor.record_degradation("model_a", "1.0.0", "accuracy", 0.65, 0.55)

        summary = monitor.get_models_summary()

        assert "model_a" in summary
        assert "model_b" in summary

        assert summary["model_a"]["total_versions"] == 2
        assert summary["model_a"]["degradation_events"] == 1
        assert summary["model_a"]["validation_pass_rate"] == 50.0

    def test_clear_history(self):
        """Test clearing history."""
        monitor = ModelRegistryMonitor()

        monitor.record_model_registration("model_a", "1.0.0")
        monitor.record_validation_gate("model_a", "1.0.0", "gate1", True)
        monitor.record_shadow_mode(
            "model_a", "1.0.0", "1.1.0", ShadowModeResult.PROMOTE
        )
        monitor.record_degradation("model_a", "1.0.0", "accuracy", 0.65, 0.55)

        monitor.clear_history()

        assert monitor.get_version_history("model_a") == []
        assert monitor.get_validation_history() == []
        assert monitor.get_shadow_mode_history() == []
        assert monitor.get_degradation_events() == []


class TestValidationGateStatus:
    """Tests for ValidationGateStatus enum."""

    def test_status_values(self):
        """Test validation gate status values."""
        assert ValidationGateStatus.PASS.value == "pass"
        assert ValidationGateStatus.FAIL.value == "fail"
        assert ValidationGateStatus.PENDING.value == "pending"


class TestShadowModeResult:
    """Tests for ShadowModeResult enum."""

    def test_result_values(self):
        """Test shadow mode result values."""
        assert ShadowModeResult.PROMOTE.value == "promote"
        assert ShadowModeResult.REJECT.value == "reject"
        assert ShadowModeResult.EXTEND.value == "extend"
        assert ShadowModeResult.PENDING.value == "pending"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
