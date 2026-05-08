"""Tests for Checkpoint Updater.

Tests checkpoint_updater.py functions with mocked Redis data.
"""

from __future__ import annotations

import math
import sys
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from src.validation.experiment_telemetry.checkpoint_updater import (
    EXCLUDED_SIGNAL_TYPES,
    calculate_cohens_h,
    calculate_experiment_metrics,
    calculate_group_metrics,
    format_metrics_for_json,
    format_metrics_for_markdown,
    update_checkpoint_file,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_redis():
    """Mock Redis client returning appropriate types."""
    return MagicMock()


@pytest.fixture
def sample_control_signals():
    """Sample control signal IDs."""
    return ["c1", "c2", "c3", "c4", "c5"]


@pytest.fixture
def sample_treatment_signals():
    """Sample treatment signal IDs."""
    return ["t1", "t2", "t3", "t4", "t5"]


@pytest.fixture
def mock_signal_data():
    """Mock signal data for testing."""
    return {
        "c1": {
            "signal_type": "fvg",
            "direction": "long",
            "entry_price": "50000.0",
            "confluence_score": "0.8",
        },
        "c2": {
            "signal_type": "order_block",
            "direction": "long",
            "entry_price": "50100.0",
            "confluence_score": "0.7",
        },
        "c3": {
            "signal_type": "bos",
            "direction": "long",
            "entry_price": "50200.0",
            "confluence_score": "0.6",
        },  # Should be excluded
        "c4": {
            "signal_type": "fvg",
            "direction": "short",
            "entry_price": "50300.0",
            "confluence_score": "0.9",
        },
        "c5": {
            "signal_type": "choch",
            "direction": "long",
            "entry_price": "50400.0",
            "confluence_score": "0.5",
        },  # Should be excluded
        "t1": {
            "signal_type": "fvg",
            "direction": "long",
            "entry_price": "50000.0",
            "confluence_score": "0.85",
        },
        "t2": {
            "signal_type": "order_block",
            "direction": "long",
            "entry_price": "50100.0",
            "confluence_score": "0.75",
        },
        "t3": {
            "signal_type": "bos",
            "direction": "long",
            "entry_price": "50200.0",
            "confluence_score": "0.65",
        },  # Should be excluded
        "t4": {
            "signal_type": "fvg",
            "direction": "short",
            "entry_price": "50300.0",
            "confluence_score": "0.95",
        },
        "t5": {
            "signal_type": "fvg",
            "direction": "long",
            "entry_price": "50400.0",
            "confluence_score": "0.55",
        },
    }


@pytest.fixture
def mock_outcome_data():
    """Mock outcome data for testing."""
    return {
        "c1": {"pnl": "0.025", "outcome": "win"},
        "c2": {"pnl": "0.015", "outcome": "win"},
        "c3": {"pnl": "-0.010", "outcome": "loss"},
        "c4": {"pnl": "0.008", "outcome": "win"},
        "c5": {"pnl": "-0.005", "outcome": "loss"},
        "t1": {"pnl": "0.030", "outcome": "win"},
        "t2": {"pnl": "0.022", "outcome": "win"},
        "t3": {"pnl": "0.012", "outcome": "profitable"},
        "t4": {"pnl": "0.018", "outcome": "win"},
        "t5": {"pnl": "-0.008", "outcome": "loss"},
    }


@pytest.fixture
def sample_checkpoint_file(tmp_path):
    """Create a temporary checkpoint file for testing."""
    content = """---
story_id: ST-ICT-020-PART-B
title: Live Paper Trading Data Collection
---

# Observation Checkpoint

## Schedule

| Checkpoint | Date | Status |
|------------|------|--------|
| Week 1 | 2026-04-01 | Pending |

## Current Metrics

_Last updated: 2026-03-25 12:00:00 UTC_

| Metric | Value |
|--------|-------|
| Days elapsed | 0 |
| Signals collected | 0 |
| Control win rate | N/A |
| Treatment win rate | N/A |

## Next Checkpoint

**Date:** 2026-04-01
"""
    checkpoint_file = tmp_path / "ST-ICT-020-PART-B-checkpoint.md"
    checkpoint_file.write_text(content)
    return checkpoint_file


# =============================================================================
# Cohen's h Calculation Tests
# =============================================================================


class TestCalculateCohenSH:
    """Tests for Cohen's h effect size calculation."""

    def test_cohens_h_equal_proportions(self):
        """Test Cohen's h when proportions are equal (should be 0)."""
        # Equal proportions should give h close to 0
        result = calculate_cohens_h(0.5, 0.5)
        assert abs(result) < 1e-10

    def test_cohens_h_treatment_better(self):
        """Test Cohen's h when treatment win rate is higher."""
        # Treatment 60%, Control 40%
        result = calculate_cohens_h(0.6, 0.4)
        # Should be positive since treatment > control
        assert result > 0
        # Should be reasonable effect size
        assert 0.3 < result < 0.8

    def test_cohens_h_control_better(self):
        """Test Cohen's h when control win rate is higher."""
        # Treatment 35%, Control 55%
        result = calculate_cohens_h(0.35, 0.55)
        # Should be negative since treatment < control
        assert result < 0
        # Should be reasonable effect size
        assert -0.8 < result < -0.3

    def test_cohens_h_edge_cases_zero(self):
        """Test Cohen's h with zero proportions."""
        result = calculate_cohens_h(0.0, 0.5)
        assert math.isnan(result)

        result = calculate_cohens_h(0.5, 0.0)
        assert math.isnan(result)

    def test_cohens_h_edge_cases_one(self):
        """Test Cohen's h with proportion of 1.0."""
        result = calculate_cohens_h(1.0, 0.5)
        assert math.isnan(result)

        result = calculate_cohens_h(0.5, 1.0)
        assert math.isnan(result)

    def test_cohens_h_known_values(self):
        """Test Cohen's h with known calculated values."""
        # For p1 = 0.6, p2 = 0.4:
        # arcsin(sqrt(0.6)) ≈ arcsin(0.7746) ≈ 0.886
        # arcsin(sqrt(0.4)) ≈ arcsin(0.6325) ≈ 0.684
        # h = 2 * (0.886 - 0.684) ≈ 0.404
        result = calculate_cohens_h(0.6, 0.4)
        assert abs(result - 0.404) < 0.01


# =============================================================================
# Group Metrics Calculation Tests
# =============================================================================


class TestCalculateGroupMetrics:
    """Tests for calculate_group_metrics with mocked Redis."""

    def test_calculate_group_metrics_with_valid_signals(
        self, mock_signal_data, mock_outcome_data
    ):
        """Test calculate_group_metrics with valid signal data."""
        with (
            patch(
                "src.validation.experiment_telemetry.checkpoint_updater.get_signal_data"
            ) as mock_get_signal,
            patch(
                "src.validation.experiment_telemetry.checkpoint_updater.get_outcome_data"
            ) as mock_get_outcome,
        ):

            def signal_side_effect(sig_id):
                return mock_signal_data.get(sig_id, {})

            def outcome_side_effect(sig_id):
                return mock_outcome_data.get(sig_id, {})

            mock_get_signal.side_effect = signal_side_effect
            mock_get_outcome.side_effect = outcome_side_effect

            # c1, c2, c4 are valid (not bos/choch) = 3 signals
            # c1: win, c2: win, c4: win = 3 wins
            result = calculate_group_metrics(["c1", "c2", "c3", "c4", "c5"])

            assert result["count"] == 3
            assert result["win_count"] == 3
            assert result["win_rate"] == 1.0
            assert result["pnl_sum"] == pytest.approx(0.025 + 0.015 + 0.008)

    def test_calculate_group_metrics_includes_bos_choch(
        self, mock_signal_data, mock_outcome_data
    ):
        """Test that BOS/CHoCH signals are now included in metrics."""
        with (
            patch(
                "src.validation.experiment_telemetry.checkpoint_updater.get_signal_data"
            ) as mock_get_signal,
            patch(
                "src.validation.experiment_telemetry.checkpoint_updater.get_outcome_data"
            ) as mock_get_outcome,
        ):

            def signal_side_effect(sig_id):
                return mock_signal_data.get(sig_id, {})

            def outcome_side_effect(sig_id):
                return mock_outcome_data.get(sig_id, {})

            mock_get_signal.side_effect = signal_side_effect
            mock_get_outcome.side_effect = outcome_side_effect

            # All signals including bos (c3) and choch (c5)
            result = calculate_group_metrics(["c1", "c2", "c3", "c4", "c5"])

            # All 5 signals should be counted (BOS/CHOCH no longer excluded)
            assert result["count"] == 5

    def test_calculate_group_metrics_empty_list(self):
        """Test calculate_group_metrics with empty signal list."""
        with (
            patch(
                "src.validation.experiment_telemetry.checkpoint_updater.get_signal_data"
            ) as mock_get_signal,
            patch(
                "src.validation.experiment_telemetry.checkpoint_updater.get_outcome_data"
            ) as mock_get_outcome,
        ):
            mock_get_signal.return_value = {}
            mock_get_outcome.return_value = {}

            result = calculate_group_metrics([])

            assert result["count"] == 0
            assert result["win_count"] == 0
            assert math.isnan(result["win_rate"])
            assert math.isnan(result["avg_pnl"])

    def test_calculate_group_metrics_no_valid_signals(self):
        """Test when all signals are filtered out (all BOS/CHoCH)."""
        with (
            patch(
                "src.validation.experiment_telemetry.checkpoint_updater.get_signal_data"
            ) as mock_get_signal,
            patch(
                "src.validation.experiment_telemetry.checkpoint_updater.get_outcome_data"
            ) as mock_get_outcome,
        ):
            # All signals are bos or choch
            mock_get_signal.return_value = {"signal_type": "bos"}
            mock_get_outcome.return_value = {}

            result = calculate_group_metrics(["sig1", "sig2"])

            assert result["count"] == 0
            assert result["win_count"] == 0


# =============================================================================
# Experiment Metrics Integration Tests
# =============================================================================


class TestCalculateExperimentMetrics:
    """Integration tests for calculate_experiment_metrics."""

    def test_calculate_experiment_metrics_with_mock_data(
        self,
        sample_control_signals,
        sample_treatment_signals,
        mock_signal_data,
        mock_outcome_data,
    ):
        """Test calculate_experiment_metrics end-to-end."""
        with (
            patch(
                "src.validation.experiment_telemetry.checkpoint_updater.get_signal_ids"
            ) as mock_get_ids,
            patch(
                "src.validation.experiment_telemetry.checkpoint_updater.get_signal_data"
            ) as mock_get_signal,
            patch(
                "src.validation.experiment_telemetry.checkpoint_updater.get_outcome_data"
            ) as mock_get_outcome,
            patch(
                "src.validation.experiment_telemetry.checkpoint_updater.get_experiment_meta"
            ) as mock_get_meta,
        ):
            # Setup mock returns
            def ids_side_effect(group):
                return (
                    sample_control_signals
                    if group == "control"
                    else sample_treatment_signals
                )

            mock_get_ids.side_effect = ids_side_effect
            mock_get_signal.side_effect = lambda sig_id: mock_signal_data.get(
                sig_id, {}
            )
            mock_get_outcome.side_effect = lambda sig_id: mock_outcome_data.get(
                sig_id, {}
            )
            mock_get_meta.return_value = {"observation_start": "2026-03-25T00:00:00Z"}

            result = calculate_experiment_metrics()

            # Control: c1, c2, c4 are valid (3 signals)
            # c1: win, c2: win, c4: win = 3 wins, win_rate = 1.0
            assert result["control"]["count"] == 3
            assert result["control"]["win_count"] == 3
            assert result["control"]["win_rate"] == 1.0

            # Treatment: t1, t2, t4, t5 are valid (4 signals, t3 is bos)
            # t1: win, t2: win, t4: win, t5: loss = 3 wins, win_rate = 0.75
            assert result["treatment"]["count"] == 4
            assert result["treatment"]["win_count"] == 3
            assert result["treatment"]["win_rate"] == 0.75

            assert result["total_signals"] == 7

    def test_calculate_experiment_metrics_with_missing_data(self):
        """Test handling of missing signal/outcome data."""
        with (
            patch(
                "src.validation.experiment_telemetry.checkpoint_updater.get_signal_ids"
            ) as mock_get_ids,
            patch(
                "src.validation.experiment_telemetry.checkpoint_updater.get_signal_data"
            ) as mock_get_signal,
            patch(
                "src.validation.experiment_telemetry.checkpoint_updater.get_outcome_data"
            ) as mock_get_outcome,
            patch(
                "src.validation.experiment_telemetry.checkpoint_updater.get_experiment_meta"
            ) as mock_get_meta,
        ):
            mock_get_ids.return_value = ["sig1", "sig2"]
            mock_get_signal.return_value = {}  # No signal data
            mock_get_outcome.return_value = {}  # No outcome data
            mock_get_meta.return_value = {}

            result = calculate_experiment_metrics()

            assert result["control"]["count"] == 0
            assert result["treatment"]["count"] == 0
            assert result["total_signals"] == 0


# =============================================================================
# BOS/CHoCH Exclusion Tests
# =============================================================================


class TestBOSCHoCHExclusion:
    """Tests for BOS/CHoCH signal exclusion."""

    def test_excluded_signal_types_empty(self):
        """Test that excluded signal types set is now empty."""
        assert "bos" not in EXCLUDED_SIGNAL_TYPES
        assert "choch" not in EXCLUDED_SIGNAL_TYPES
        assert len(EXCLUDED_SIGNAL_TYPES) == 0

    def test_bos_signal_included(self, mock_signal_data, mock_outcome_data):
        """Test that BOS signals are now included in metrics."""
        with (
            patch(
                "src.validation.experiment_telemetry.checkpoint_updater.get_signal_data"
            ) as mock_get_signal,
            patch(
                "src.validation.experiment_telemetry.checkpoint_updater.get_outcome_data"
            ) as mock_get_outcome,
        ):
            mock_get_signal.side_effect = lambda sig_id: mock_signal_data.get(
                sig_id, {}
            )
            mock_get_outcome.side_effect = lambda sig_id: mock_outcome_data.get(
                sig_id, {}
            )

            # c3 is BOS - should now be included
            result = calculate_group_metrics(["c3"])

            assert result["count"] == 1  # Included
            assert result["win_count"] == 0  # loss outcome

    def test_choch_signal_included(self, mock_signal_data, mock_outcome_data):
        """Test that CHoCH signals are now included in metrics."""
        with (
            patch(
                "src.validation.experiment_telemetry.checkpoint_updater.get_signal_data"
            ) as mock_get_signal,
            patch(
                "src.validation.experiment_telemetry.checkpoint_updater.get_outcome_data"
            ) as mock_get_outcome,
        ):
            mock_get_signal.side_effect = lambda sig_id: mock_signal_data.get(
                sig_id, {}
            )
            mock_get_outcome.side_effect = lambda sig_id: mock_outcome_data.get(
                sig_id, {}
            )

            # c5 is CHoCH - should now be included
            result = calculate_group_metrics(["c5"])

            assert result["count"] == 1  # Included


# =============================================================================
# Checkpoint File Update Tests
# =============================================================================


class TestCheckpointFileUpdate:
    """Tests for checkpoint file parsing and updating."""

    def test_update_checkpoint_file_success(self, sample_checkpoint_file):
        """Test successful checkpoint file update."""
        metrics = {
            "days_elapsed": 5,
            "total_signals": 100,
            "control": {
                "count": 50,
                "win_count": 25,
                "win_rate": 0.5,
                "avg_pnl": 0.015,
            },
            "treatment": {
                "count": 50,
                "win_count": 30,
                "win_rate": 0.6,
                "avg_pnl": 0.022,
            },
            "effect_size": 0.2,
            "p_value": 0.15,
            "z_statistic": 1.5,
        }

        # Patch CHECKPOINT_FILE to use our temp file
        import src.validation.experiment_telemetry.checkpoint_updater as updater

        original_file = updater.CHECKPOINT_FILE
        updater.CHECKPOINT_FILE = sample_checkpoint_file

        try:
            result = update_checkpoint_file(metrics, dry_run=False)

            assert result is True
            content = sample_checkpoint_file.read_text()
            assert "Days elapsed" in content
            assert "Signals collected" in content
            assert "100" in content
        finally:
            updater.CHECKPOINT_FILE = original_file

    def test_update_checkpoint_file_dry_run(self, sample_checkpoint_file):
        """Test dry-run mode doesn't modify file."""
        original_content = sample_checkpoint_file.read_text()

        metrics = {
            "days_elapsed": 5,
            "total_signals": 100,
            "control": {
                "count": 50,
                "win_count": 25,
                "win_rate": 0.5,
                "avg_pnl": 0.015,
            },
            "treatment": {
                "count": 50,
                "win_count": 30,
                "win_rate": 0.6,
                "avg_pnl": 0.022,
            },
            "effect_size": 0.2,
            "p_value": 0.15,
        }

        # Capture stdout
        captured = StringIO()
        sys.stdout = captured

        result = update_checkpoint_file(metrics, dry_run=True)

        sys.stdout = sys.__stdout__

        assert result is True
        assert (
            "Dry run" in captured.getvalue() or "dry run" in captured.getvalue().lower()
        )
        # File should not be modified
        assert sample_checkpoint_file.read_text() == original_content

    def test_update_checkpoint_file_missing_marker(self, tmp_path):
        """Test handling of missing markers in checkpoint file."""
        # File without proper markers
        content = "Some content without proper markers"
        checkpoint_file = tmp_path / "test.md"
        checkpoint_file.write_text(content)

        metrics = {"days_elapsed": 1, "total_signals": 10}

        # Patch the global CHECKPOINT_FILE
        with patch(
            "src.validation.experiment_telemetry.checkpoint_updater.CHECKPOINT_FILE",
            checkpoint_file,
        ):
            result = update_checkpoint_file(metrics, dry_run=False)

        assert result is False


# =============================================================================
# CLI Argument Parsing Tests
# =============================================================================


class TestCLIArgumentParsing:
    """Tests for CLI argument parsing (--dry-run, --update, --json)."""

    def test_argparse_dry_run_flag(self):
        """Test that --dry-run flag is recognized by argparse."""
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("--dry-run", action="store_true")
        args = parser.parse_args(["--dry-run"])
        assert args.dry_run is True

    def test_argparse_update_flag(self):
        """Test that --update flag is recognized by argparse."""
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("--update", action="store_true")
        args = parser.parse_args(["--update"])
        assert args.update is True

    def test_argparse_json_flag(self):
        """Test that --json flag is recognized by argparse."""
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("--json", action="store_true")
        args = parser.parse_args(["--json"])
        assert args.json is True

    def test_argparse_multiple_flags(self):
        """Test that multiple flags can be used together."""
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--update", action="store_true")
        parser.add_argument("--json", action="store_true")

        args = parser.parse_args(["--dry-run", "--json"])
        assert args.dry_run is True
        assert args.json is True
        assert args.update is False


# =============================================================================
# Formatting Tests
# =============================================================================


class TestFormatting:
    """Tests for output formatting functions."""

    def test_format_metrics_for_markdown(self):
        """Test markdown formatting of metrics."""
        metrics = {
            "days_elapsed": 5,
            "total_signals": 100,
            "control": {
                "count": 50,
                "win_count": 25,
                "win_rate": 0.5,
                "avg_pnl": 0.015,
            },
            "treatment": {
                "count": 50,
                "win_count": 30,
                "win_rate": 0.6,
                "avg_pnl": 0.022,
            },
            "effect_size": 0.2,
            "p_value": 0.15,
        }

        result = format_metrics_for_markdown(metrics)

        assert "## Current Metrics" in result
        assert "Days elapsed" in result
        assert "Signals collected" in result
        assert "100" in result
        assert "Control win rate" in result
        assert "Treatment win rate" in result

    def test_format_metrics_for_json(self):
        """Test JSON formatting of metrics."""
        metrics = {
            "days_elapsed": 5,
            "total_signals": 100,
            "control": {
                "count": 50,
                "win_count": 25,
                "win_rate": 0.5,
                "avg_pnl": 0.015,
            },
            "treatment": {
                "count": 50,
                "win_count": 30,
                "win_rate": 0.6,
                "avg_pnl": 0.022,
            },
            "effect_size": 0.2,
            "p_value": 0.15,
            "z_statistic": 1.5,
        }

        result = format_metrics_for_json(metrics)

        # format_metrics_for_json returns a dict (caller does json.dumps)
        assert isinstance(result, dict)
        assert result["days_elapsed"] == 5
        assert result["total_signals"] == 100
        assert result["control"]["count"] == 50
        assert result["treatment"]["count"] == 50

    def test_format_metrics_for_json_sanitizes_nan(self):
        """Test that JSON formatting sanitizes NaN/Inf values."""
        metrics = {
            "days_elapsed": 0,
            "total_signals": 0,
            "control": {
                "count": 0,
                "win_count": 0,
                "win_rate": float("nan"),
                "avg_pnl": float("nan"),
            },
            "treatment": {
                "count": 0,
                "win_count": 0,
                "win_rate": float("nan"),
                "avg_pnl": float("nan"),
            },
            "effect_size": float("nan"),
            "p_value": float("nan"),
            "z_statistic": float("nan"),
        }

        result = format_metrics_for_json(metrics)

        # NaN should be converted to None
        assert result["control"]["win_rate"] is None
        assert result["effect_size_cohens_h"] is None
