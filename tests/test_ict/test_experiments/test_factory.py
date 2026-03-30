"""Tests for Experiment Factory."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.ict.experiments.b1_baseline import B1BaselineExperiment
from src.ict.experiments.b2_enhanced import B2EnhancedExperiment
from src.ict.experiments.b3_timeframe_variant import B3TimeframeExperiment
from src.ict.experiments.b4_signal_weight_variant import B4SignalWeightExperiment
from src.ict.experiments.b5_threshold_variant import B5ThresholdExperiment
from src.ict.experiments.factory import ExperimentFactory


class TestExperimentFactory:
    """Tests for ExperimentFactory class."""

    @pytest.fixture
    def collector(self):
        """Create a mock collector."""
        return MagicMock()

    def test_create_b1(self, collector):
        """Test creating ICT-B1 experiment."""
        exp = ExperimentFactory.create_experiment("ICT-B1", collector)
        assert isinstance(exp, B1BaselineExperiment)

    def test_create_b2(self, collector):
        """Test creating ICT-B2 experiment."""
        exp = ExperimentFactory.create_experiment("ICT-B2", collector)
        assert isinstance(exp, B2EnhancedExperiment)

    def test_create_b3(self, collector):
        """Test creating ICT-B3 experiment."""
        exp = ExperimentFactory.create_experiment(
            "ICT-B3", collector, variant="timeframe_1h"
        )
        assert isinstance(exp, B3TimeframeExperiment)

    def test_create_b4(self, collector):
        """Test creating ICT-B4 experiment."""
        exp = ExperimentFactory.create_experiment(
            "ICT-B4", collector, variant="confidence_weighted"
        )
        assert isinstance(exp, B4SignalWeightExperiment)

    def test_create_b5(self, collector):
        """Test creating ICT-B5 experiment."""
        exp = ExperimentFactory.create_experiment(
            "ICT-B5", collector, variant="medium_threshold"
        )
        assert isinstance(exp, B5ThresholdExperiment)

    def test_create_unknown_raises(self, collector):
        """Test creating unknown experiment raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            ExperimentFactory.create_experiment("ICT-B99", collector)
        assert "Unknown experiment ID" in str(exc_info.value)

    def test_list_experiments(self):
        """Test listing all available experiments."""
        experiments = ExperimentFactory.list_experiments()
        assert len(experiments) == 5
        assert "ICT-B1" in experiments
        assert "ICT-B2" in experiments
        assert "ICT-B3" in experiments
        assert "ICT-B4" in experiments
        assert "ICT-B5" in experiments

    def test_is_valid_experiment_true(self):
        """Test is_valid_experiment returns True for valid IDs."""
        assert ExperimentFactory.is_valid_experiment("ICT-B1") is True
        assert ExperimentFactory.is_valid_experiment("ICT-B5") is True

    def test_is_valid_experiment_false(self):
        """Test is_valid_experiment returns False for invalid IDs."""
        assert ExperimentFactory.is_valid_experiment("ICT-B99") is False
        assert ExperimentFactory.is_valid_experiment("INVALID") is False

    def test_create_with_registry(self, collector):
        """Test creating experiment with custom registry."""
        mock_registry = MagicMock()
        exp = ExperimentFactory.create_experiment(
            "ICT-B1",
            collector,
            registry=mock_registry,
        )
        assert exp.registry is mock_registry
