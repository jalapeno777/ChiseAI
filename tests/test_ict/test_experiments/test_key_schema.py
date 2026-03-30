"""Tests for experiment key schema."""

from __future__ import annotations

from datetime import datetime

from src.ict.experiments.key_schema import ExperimentKey


class TestExperimentKey:
    """Tests for ExperimentKey dataclass."""

    def test_key_format_basic(self):
        """Test basic key format generation."""
        key = ExperimentKey(
            experiment_id="ICT-B1",
            variant="baseline",
            started_at=datetime(2026, 3, 29, 12, 0, 0),
        )
        result = key.key_format()
        assert result == "ict:exp:ICT-B1:baseline:20260329"

    def test_key_format_different_date(self):
        """Test key format with different date."""
        key = ExperimentKey(
            experiment_id="ICT-B2",
            variant="enhanced",
            started_at=datetime(2026, 1, 15, 0, 0, 0),
        )
        result = key.key_format()
        assert result == "ict:exp:ICT-B2:enhanced:20260115"

    def test_prefix(self):
        """Test key prefix generation."""
        key = ExperimentKey(
            experiment_id="ICT-B1",
            variant="baseline",
            started_at=datetime(2026, 3, 29),
        )
        result = key.prefix()
        assert result == "ict:exp:ICT-B1:baseline"

    def test_str_representation(self):
        """Test string representation."""
        key = ExperimentKey(
            experiment_id="ICT-B3",
            variant="timeframe_1h",
            started_at=datetime(2026, 3, 29),
        )
        result = str(key)
        assert "ICT-B3" in result
        assert "timeframe_1h" in result
        assert "20260329" in result

    def test_different_experiment_ids(self):
        """Test various experiment IDs."""
        for exp_id in ["ICT-B1", "ICT-B2", "ICT-B3", "ICT-B4", "ICT-B5"]:
            key = ExperimentKey(
                experiment_id=exp_id,
                variant="test",
                started_at=datetime(2026, 3, 29),
            )
            formatted = key.key_format()
            assert exp_id in formatted

    def test_different_variants(self):
        """Test various variant formats."""
        key = ExperimentKey(
            experiment_id="ICT-B1",
            variant="timeframe_15m",
            started_at=datetime(2026, 3, 29),
        )
        assert "timeframe_15m" in key.key_format()
