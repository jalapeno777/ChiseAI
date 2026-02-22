"""Unit tests for threshold optimizer.

Tests for ThresholdOptimizer, OptimizationResult, ECECurve, and ECECurveVisualizer.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

import numpy as np
import pytest
import yaml

sys.path.insert(0, "src")

from ml.calibration.data_collector import CalibrationDataCollector
from ml.calibration.models import CalibrationConfig
from ml.calibration.optimizer import (
    ECECurve,
    OptimizationResult,
    ThresholdOptimizer,
)
from ml.calibration.storage import InMemoryCalibrationStorage
from ml.calibration.visualization import (
    CurveVisualization,
    ECECurveVisualizer,
    create_grafana_panel_json,
)


class TestOptimizationResult:
    """Tests for OptimizationResult dataclass."""

    def test_creation(self):
        """Test creating an OptimizationResult."""
        result = OptimizationResult(
            signal_type="LONG",
            optimal_threshold=0.75,
            min_ece=0.05,
            confidence_bin=7,
            sample_size=100,
        )

        assert result.signal_type == "LONG"
        assert result.optimal_threshold == 0.75
        assert result.min_ece == 0.05
        assert result.confidence_bin == 7
        assert result.sample_size == 100

    def test_to_dict(self):
        """Test converting to dictionary."""
        result = OptimizationResult(
            signal_type="LONG",
            optimal_threshold=0.75,
            min_ece=0.05,
            confidence_bin=7,
            sample_size=100,
            threshold_range=(0.4, 0.95),
            step_size=0.05,
        )

        d = result.to_dict()

        assert d["signal_type"] == "LONG"
        assert d["optimal_threshold"] == 0.75
        assert d["min_ece"] == 0.05
        assert d["confidence_bin"] == 7
        assert d["sample_size"] == 100
        assert d["threshold_range"] == [0.4, 0.95]
        assert d["step_size"] == 0.05


class TestECECurve:
    """Tests for ECECurve dataclass."""

    def test_creation(self):
        """Test creating an ECECurve."""
        curve = ECECurve(
            thresholds=[0.4, 0.5, 0.6, 0.7, 0.8],
            ece_values=[0.15, 0.12, 0.08, 0.10, 0.20],
            optimal_idx=2,
            signal_type="LONG",
            sample_sizes=[100, 90, 80, 70, 60],
        )

        assert curve.signal_type == "LONG"
        assert curve.optimal_idx == 2
        assert curve.optimal_threshold == 0.6
        assert curve.min_ece == 0.08

    def test_to_dict(self):
        """Test converting to dictionary."""
        curve = ECECurve(
            thresholds=[0.4, 0.5, 0.6],
            ece_values=[0.15, 0.12, 0.08],
            optimal_idx=2,
            signal_type="LONG",
            sample_sizes=[100, 90, 80],
        )

        d = curve.to_dict()

        assert d["signal_type"] == "LONG"
        assert d["thresholds"] == [0.4, 0.5, 0.6]
        assert d["ece_values"] == [0.15, 0.12, 0.08]
        assert d["optimal_idx"] == 2
        assert d["optimal_threshold"] == 0.6
        assert d["min_ece"] == 0.08
        assert d["sample_sizes"] == [100, 90, 80]


class TestThresholdOptimizer:
    """Tests for ThresholdOptimizer."""

    @pytest.fixture
    def storage(self):
        """Create a fresh in-memory storage."""
        return InMemoryCalibrationStorage()

    @pytest.fixture
    def collector(self, storage):
        """Create a collector with in-memory storage."""
        config = CalibrationConfig()
        return CalibrationDataCollector(config=config, storage=storage)

    @pytest.fixture
    def optimizer(self, collector):
        """Create a threshold optimizer."""
        return ThresholdOptimizer(collector, n_bins=10)

    def test_calculate_ece_well_calibrated(self, optimizer, collector):
        """Test ECE calculation with well-calibrated data.

        Well-calibrated data: predictions match actual outcomes on average.
        """
        # Create well-calibrated data
        # For prob=0.7, outcomes should average to ~0.7
        np.random.seed(42)
        for i in range(100):
            prob = 0.7
            # Outcome with probability matching prediction
            outcome = 1 if np.random.random() < prob else 0
            collector.collect(
                signal_id=f"sig-{i:03d}",
                predicted_prob=prob,
                actual_outcome=outcome,
                signal_type="LONG",
            )

        records = collector.get_records(signal_type="LONG")
        ece = optimizer.calculate_ece(records)

        # Well-calibrated model should have low ECE
        assert ece < 0.2

    def test_calculate_ece_poorly_calibrated(self, optimizer, collector):
        """Test ECE calculation with poorly calibrated data."""
        # Create poorly calibrated data
        # High confidence (0.9) but low accuracy (~0.5)
        np.random.seed(42)
        for i in range(100):
            prob = 0.9
            outcome = i % 2  # 50% accuracy regardless of confidence
            collector.collect(
                signal_id=f"sig-{i:03d}",
                predicted_prob=prob,
                actual_outcome=outcome,
                signal_type="LONG",
            )

        records = collector.get_records(signal_type="LONG")
        ece = optimizer.calculate_ece(records)

        # Poorly calibrated model should have higher ECE
        assert ece > 0.3

    def test_calculate_ece_empty_records(self, optimizer):
        """Test ECE calculation with empty records."""
        with pytest.raises(ValueError, match="no records"):
            optimizer.calculate_ece([])

    def test_optimize_thresholds_basic(self, optimizer, collector):
        """Test basic threshold optimization."""
        # Create synthetic data with known optimal threshold
        # Higher thresholds should have better calibration
        np.random.seed(42)
        for i in range(100):
            # Create correlation: higher prob = higher chance of success
            prob = 0.4 + (i / 100) * 0.55  # 0.4 to 0.95
            outcome = 1 if prob > 0.7 else 0
            collector.collect(
                signal_id=f"sig-{i:03d}",
                predicted_prob=prob,
                actual_outcome=outcome,
                signal_type="LONG",
            )

        result = optimizer.optimize_thresholds("LONG")

        assert isinstance(result, OptimizationResult)
        assert result.signal_type == "LONG"
        assert 0.4 <= result.optimal_threshold <= 0.95
        assert result.min_ece < 0.2  # Should find a good threshold
        assert result.sample_size >= 30

    def test_optimize_thresholds_insufficient_samples(self, optimizer, collector):
        """Test optimization with insufficient samples."""
        # Only add a few records
        for i in range(5):
            collector.collect(
                signal_id=f"sig-{i:03d}",
                predicted_prob=0.7,
                actual_outcome=1,
                signal_type="LONG",
            )

        with pytest.raises(ValueError, match="Insufficient samples"):
            optimizer.optimize_thresholds("LONG", min_samples=30)

    def test_optimize_thresholds_different_signal_types(self, optimizer, collector):
        """Test optimization for different signal types."""
        np.random.seed(42)

        # Add data for each signal type
        for signal_type in ["LONG", "SHORT", "SCALP"]:
            for i in range(50):
                prob = 0.5 + (i / 50) * 0.45
                outcome = 1 if prob > 0.7 else 0
                collector.collect(
                    signal_id=f"{signal_type.lower()}-{i:03d}",
                    predicted_prob=prob,
                    actual_outcome=outcome,
                    signal_type=signal_type,
                )

        for signal_type in ["LONG", "SHORT", "SCALP"]:
            result = optimizer.optimize_thresholds(signal_type)
            assert result.signal_type == signal_type
            assert result.sample_size >= 30

    def test_generate_ece_curve(self, optimizer, collector):
        """Test ECE curve generation."""
        np.random.seed(42)
        for i in range(100):
            prob = 0.4 + (i / 100) * 0.55
            outcome = 1 if prob > 0.7 else 0
            collector.collect(
                signal_id=f"sig-{i:03d}",
                predicted_prob=prob,
                actual_outcome=outcome,
                signal_type="LONG",
            )

        curve = optimizer.generate_ece_curve("LONG")

        assert isinstance(curve, ECECurve)
        assert curve.signal_type == "LONG"
        assert len(curve.thresholds) > 0
        assert len(curve.thresholds) == len(curve.ece_values)
        assert 0 <= curve.optimal_idx < len(curve.thresholds)

    def test_generate_ece_curve_no_records(self, optimizer):
        """Test curve generation with no records."""
        with pytest.raises(ValueError, match="No records found"):
            optimizer.generate_ece_curve("LONG")

    def test_optimize_all_signal_types(self, optimizer, collector):
        """Test optimizing all signal types at once."""
        np.random.seed(42)

        for signal_type in ["LONG", "SHORT", "SCALP"]:
            for i in range(50):
                prob = 0.5 + (i / 50) * 0.45
                outcome = 1 if prob > 0.7 else 0
                collector.collect(
                    signal_id=f"{signal_type.lower()}-{i:03d}",
                    predicted_prob=prob,
                    actual_outcome=outcome,
                    signal_type=signal_type,
                )

        results = optimizer.optimize_all_signal_types()

        assert "LONG" in results
        assert "SHORT" in results
        assert "SCALP" in results

        for signal_type, result in results.items():
            assert isinstance(result, OptimizationResult)
            assert result.signal_type == signal_type

    def test_generate_all_ece_curves(self, optimizer, collector):
        """Test generating curves for all signal types."""
        np.random.seed(42)

        for signal_type in ["LONG", "SHORT", "SCALP"]:
            for i in range(50):
                prob = 0.5 + (i / 50) * 0.45
                outcome = 1 if prob > 0.7 else 0
                collector.collect(
                    signal_id=f"{signal_type.lower()}-{i:03d}",
                    predicted_prob=prob,
                    actual_outcome=outcome,
                    signal_type=signal_type,
                )

        curves = optimizer.generate_all_ece_curves()

        assert "LONG" in curves
        assert "SHORT" in curves
        assert "SCALP" in curves

    def test_export_config_yaml(self, optimizer, collector):
        """Test exporting config to YAML."""
        np.random.seed(42)
        for i in range(100):
            prob = 0.5 + (i / 100) * 0.45
            outcome = 1 if prob > 0.7 else 0
            collector.collect(
                signal_id=f"sig-{i:03d}",
                predicted_prob=prob,
                actual_outcome=outcome,
                signal_type="LONG",
            )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            filepath = f.name

        try:
            success = optimizer.export_config(filepath)
            assert success is True

            # Verify file contents
            with open(filepath) as f:
                config = yaml.safe_load(f)

            assert "threshold_optimization" in config
            assert "thresholds" in config["threshold_optimization"]
            assert "LONG" in config["threshold_optimization"]["thresholds"]
        finally:
            os.unlink(filepath)

    def test_export_config_json(self, optimizer, collector):
        """Test exporting config to JSON."""
        np.random.seed(42)
        for i in range(100):
            prob = 0.5 + (i / 100) * 0.45
            outcome = 1 if prob > 0.7 else 0
            collector.collect(
                signal_id=f"sig-{i:03d}",
                predicted_prob=prob,
                actual_outcome=outcome,
                signal_type="LONG",
            )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            filepath = f.name

        try:
            success = optimizer.export_to_json(filepath)
            assert success is True

            # Verify file contents
            with open(filepath) as f:
                config = json.load(f)

            assert "threshold_optimization" in config
            assert "thresholds" in config["threshold_optimization"]
        finally:
            os.unlink(filepath)


class TestECECurveVisualizer:
    """Tests for ECECurveVisualizer."""

    @pytest.fixture
    def sample_curve(self):
        """Create a sample ECE curve."""
        return ECECurve(
            thresholds=[0.4, 0.5, 0.6, 0.7, 0.8],
            ece_values=[0.15, 0.12, 0.08, 0.10, 0.20],
            optimal_idx=2,
            signal_type="LONG",
            sample_sizes=[100, 90, 80, 70, 60],
        )

    def test_create_visualization(self, sample_curve):
        """Test creating a visualization."""
        visualizer = ECECurveVisualizer()
        viz = visualizer.create_visualization(sample_curve)

        assert isinstance(viz, CurveVisualization)
        assert viz.signal_type == "LONG"
        assert viz.title == "ECE Curve - LONG"
        assert len(viz.data_points) == 5
        assert viz.optimal_point == (0.6, 0.08)
        assert len(viz.annotations) > 0

    def test_create_visualization_no_annotations(self, sample_curve):
        """Test creating visualization without annotations."""
        visualizer = ECECurveVisualizer()
        viz = visualizer.create_visualization(sample_curve, include_annotations=False)

        assert len(viz.annotations) == 0

    def test_create_all_visualizations(self, sample_curve):
        """Test creating multiple visualizations."""
        curves = {
            "LONG": sample_curve,
            "SHORT": ECECurve(
                thresholds=[0.4, 0.5, 0.6],
                ece_values=[0.20, 0.15, 0.10],
                optimal_idx=2,
                signal_type="SHORT",
                sample_sizes=[80, 70, 60],
            ),
        }

        visualizer = ECECurveVisualizer()
        visualizations = visualizer.create_all_visualizations(curves)

        assert "LONG" in visualizations
        assert "SHORT" in visualizations
        assert visualizations["LONG"].signal_type == "LONG"
        assert visualizations["SHORT"].signal_type == "SHORT"

    def test_to_grafana_format(self, sample_curve):
        """Test Grafana format conversion."""
        visualizer = ECECurveVisualizer()
        viz = visualizer.create_visualization(sample_curve)
        grafana = viz.to_grafana_format()

        assert grafana["title"] == "ECE Curve - LONG"
        assert grafana["type"] == "graph"
        assert "series" in grafana
        assert len(grafana["series"]) >= 1

    def test_export_to_json_grafana_format(self, sample_curve):
        """Test exporting to JSON in Grafana format."""
        curves = {"LONG": sample_curve}
        visualizer = ECECurveVisualizer()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            filepath = f.name

        try:
            success = visualizer.export_to_json(curves, filepath, format="grafana")
            assert success is True

            with open(filepath) as f:
                data = json.load(f)

            assert "dashboard" in data
            assert "panels" in data["dashboard"]
        finally:
            os.unlink(filepath)

    def test_export_to_json_raw_format(self, sample_curve):
        """Test exporting to JSON in raw format."""
        curves = {"LONG": sample_curve}
        visualizer = ECECurveVisualizer()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            filepath = f.name

        try:
            success = visualizer.export_to_json(curves, filepath, format="raw")
            assert success is True

            with open(filepath) as f:
                data = json.load(f)

            assert "curves" in data
            assert "LONG" in data["curves"]
        finally:
            os.unlink(filepath)

    def test_generate_metrics(self, sample_curve):
        """Test metrics generation."""
        curves = {"LONG": sample_curve}
        visualizer = ECECurveVisualizer()
        metrics = visualizer.generate_metrics(curves)

        assert "LONG" in metrics
        assert "optimal_threshold" in metrics["LONG"]
        assert "min_ece" in metrics["LONG"]
        assert "max_ece" in metrics["LONG"]
        assert metrics["LONG"]["optimal_threshold"] == 0.6

    def test_export_metrics_to_line_protocol(self, sample_curve):
        """Test InfluxDB line protocol export."""
        curves = {"LONG": sample_curve}
        visualizer = ECECurveVisualizer()
        line_protocol = visualizer.export_metrics_to_line_protocol(curves)

        assert "ece_optimization" in line_protocol
        assert "signal_type=LONG" in line_protocol
        assert "optimal_threshold=0.6" in line_protocol


class TestCreateGrafanaPanelJson:
    """Tests for create_grafana_panel_json function."""

    def test_basic_panel(self):
        """Test creating a basic Grafana panel."""
        panel = create_grafana_panel_json(
            signal_types=["LONG", "SHORT"],
            title="Test Panel",
        )

        assert panel["title"] == "Test Panel"
        assert panel["type"] == "graph"
        assert "targets" in panel
        assert len(panel["targets"]) == 4  # 2 signal types * 2 metrics each

    def test_default_title(self):
        """Test default title."""
        panel = create_grafana_panel_json(signal_types=["LONG"])
        assert "ECE" in panel["title"]


class TestThresholdOptimizerIntegration:
    """Integration tests for ThresholdOptimizer."""

    def test_full_workflow(self):
        """Test a complete optimization workflow."""
        storage = InMemoryCalibrationStorage()
        config = CalibrationConfig()
        collector = CalibrationDataCollector(config=config, storage=storage)
        optimizer = ThresholdOptimizer(collector, n_bins=10)

        # Generate synthetic calibration data
        np.random.seed(42)
        for signal_type in ["LONG", "SHORT", "SCALP"]:
            for i in range(100):
                prob = 0.4 + (i / 100) * 0.55
                # Create correlation between prob and outcome
                outcome = 1 if np.random.random() < prob else 0
                collector.collect(
                    signal_id=f"{signal_type.lower()}-{i:03d}",
                    predicted_prob=prob,
                    actual_outcome=outcome,
                    signal_type=signal_type,
                )

        # Optimize all signal types
        results = optimizer.optimize_all_signal_types()

        # Verify results
        for signal_type in ["LONG", "SHORT", "SCALP"]:
            assert signal_type in results
            result = results[signal_type]
            assert result.sample_size >= 30
            assert 0.4 <= result.optimal_threshold <= 0.95

        # Generate ECE curves
        curves = optimizer.generate_all_ece_curves()
        assert len(curves) == 3

        # Create visualizations
        visualizer = ECECurveVisualizer()
        visualizations = visualizer.create_all_visualizations(curves)
        assert len(visualizations) == 3

    def test_ece_calculation_verification(self):
        """Verify ECE calculation against known values."""
        storage = InMemoryCalibrationStorage()
        collector = CalibrationDataCollector(storage=storage)
        optimizer = ThresholdOptimizer(collector, n_bins=10)

        # Create perfectly calibrated data
        # For each bin, accuracy should match average confidence
        np.random.seed(42)
        for bin_idx in range(10):
            bin_center = (bin_idx + 0.5) / 10  # 0.05, 0.15, ..., 0.95
            for i in range(10):
                # Outcome matches confidence (perfect calibration)
                outcome = 1 if np.random.random() < bin_center else 0
                collector.collect(
                    signal_id=f"perfect-{bin_idx}-{i}",
                    predicted_prob=bin_center,
                    actual_outcome=outcome,
                    signal_type="LONG",
                )

        records = collector.get_records(signal_type="LONG")
        ece = optimizer.calculate_ece(records)

        # Perfectly calibrated model should have very low ECE
        # (not exactly 0 due to randomness in outcomes)
        assert ece < 0.15

    def test_threshold_optimization_convergence(self):
        """Test that optimization converges within expected iterations."""
        storage = InMemoryCalibrationStorage()
        collector = CalibrationDataCollector(storage=storage)
        optimizer = ThresholdOptimizer(collector, n_bins=10)

        # Create data with clear optimal threshold
        np.random.seed(42)
        for i in range(200):
            if i < 100:
                # Low confidence, poor calibration
                prob = 0.45
                outcome = i % 2  # 50% accuracy
            else:
                # High confidence, good calibration
                prob = 0.85
                outcome = 1 if np.random.random() < 0.85 else 0

            collector.collect(
                signal_id=f"conv-{i:03d}",
                predicted_prob=prob,
                actual_outcome=outcome,
                signal_type="LONG",
            )

        result = optimizer.optimize_thresholds("LONG")

        # Should find threshold in high-confidence region
        assert result.optimal_threshold >= 0.5
        assert result.min_ece < 0.3

    def test_export_config_compatibility(self):
        """Test that exported config is compatible with existing config system."""
        storage = InMemoryCalibrationStorage()
        collector = CalibrationDataCollector(storage=storage)
        optimizer = ThresholdOptimizer(collector, n_bins=10)

        np.random.seed(42)
        for i in range(100):
            prob = 0.5 + (i / 100) * 0.45
            outcome = 1 if np.random.random() < prob else 0
            collector.collect(
                signal_id=f"compat-{i:03d}",
                predicted_prob=prob,
                actual_outcome=outcome,
                signal_type="LONG",
            )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            filepath = f.name

        try:
            optimizer.export_config(filepath)

            with open(filepath) as f:
                config = yaml.safe_load(f)

            # Verify structure matches expected format
            assert "threshold_optimization" in config
            top = config["threshold_optimization"]
            assert "version" in top
            assert "generated_at" in top
            assert "parameters" in top
            assert "thresholds" in top

            # Verify threshold structure
            for signal_type, threshold_config in top["thresholds"].items():
                assert "optimal_threshold" in threshold_config
                assert "min_ece" in threshold_config
                assert "sample_size" in threshold_config
                assert "confidence_bin" in threshold_config
        finally:
            os.unlink(filepath)
