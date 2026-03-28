"""Unit tests for GradientClipper."""

import pytest
from src.autonomous_cognition.gradient_learning.clipping import (
    ClipMode,
    ClipResult,
    GradientClipper,
)


class TestGradientClipper:
    """Tests for GradientClipper."""

    def test_init_norm_mode(self):
        """Test initialization in norm mode."""
        clipper = GradientClipper(mode=ClipMode.NORM, max_norm=1.0)
        assert clipper.mode == ClipMode.NORM
        assert clipper.max_norm == 1.0

    def test_init_value_mode(self):
        """Test initialization in value mode."""
        clipper = GradientClipper(mode=ClipMode.VALUE, max_value=0.5)
        assert clipper.mode == ClipMode.VALUE
        assert clipper.max_value == 0.5

    def test_invalid_norm_raises(self):
        """Test that non-positive max_norm raises ValueError."""
        with pytest.raises(ValueError):
            GradientClipper(mode=ClipMode.NORM, max_norm=0)
        with pytest.raises(ValueError):
            GradientClipper(mode=ClipMode.NORM, max_norm=-1)

    def test_invalid_value_raises(self):
        """Test that non-positive max_value raises ValueError."""
        with pytest.raises(ValueError):
            GradientClipper(mode=ClipMode.VALUE, max_value=0)
        with pytest.raises(ValueError):
            GradientClipper(mode=ClipMode.VALUE, max_value=-1)

    def test_clip_empty_gradients(self):
        """Test clipping empty gradients."""
        clipper = GradientClipper(mode=ClipMode.NORM, max_norm=1.0)
        result = clipper.clip({})

        assert result.clipped_gradients == {}
        assert result.original_norm == 0.0
        assert result.was_clipped is False

    def test_clip_norm_no_op(self):
        """Test norm clipping when gradients are below threshold."""
        clipper = GradientClipper(mode=ClipMode.NORM, max_norm=2.0)
        gradients = {"x": 0.5, "y": 0.5}  # norm = sqrt(0.25 + 0.25) = ~0.707
        result = clipper.clip(gradients)

        assert result.was_clipped is False
        assert result.original_norm == result.clipped_norm

    def test_clip_norm_scaling(self):
        """Test norm clipping scales gradients."""
        clipper = GradientClipper(mode=ClipMode.NORM, max_norm=1.0)
        gradients = {"x": 1.0, "y": 1.0}  # norm = sqrt(2) ~= 1.414
        result = clipper.clip(gradients)

        assert result.was_clipped is True
        assert result.clipped_norm == pytest.approx(1.0)
        # Original: [1, 1], scale factor: 1/1.414 ~= 0.707
        assert result.clipped_gradients["x"] == pytest.approx(0.707, abs=0.01)
        assert result.clipped_gradients["y"] == pytest.approx(0.707, abs=0.01)

    def test_clip_value_no_op(self):
        """Test value clipping when all values are below threshold."""
        clipper = GradientClipper(mode=ClipMode.VALUE, max_value=1.0)
        gradients = {"x": 0.5, "y": 0.5}
        result = clipper.clip(gradients)

        assert result.was_clipped is False
        assert result.clipped_gradients == gradients

    def test_clip_value_individual(self):
        """Test value clipping clips individual values."""
        clipper = GradientClipper(mode=ClipMode.VALUE, max_value=0.5)
        gradients = {"x": 1.0, "y": -1.0, "z": 0.1}
        result = clipper.clip(gradients)

        assert result.was_clipped is True
        assert result.clipped_gradients["x"] == pytest.approx(0.5)
        assert result.clipped_gradients["y"] == pytest.approx(-0.5)
        assert result.clipped_gradients["z"] == pytest.approx(0.1)
        assert result.clip_fraction == pytest.approx(2 / 3)

    def test_clip_fraction_calculation(self):
        """Test clip fraction is calculated correctly."""
        clipper = GradientClipper(mode=ClipMode.VALUE, max_value=0.5)
        gradients = {"a": 1.0, "b": 2.0, "c": 3.0, "d": 0.1}
        result = clipper.clip(gradients)

        # 3 out of 4 gradients were clipped
        assert result.clip_fraction == pytest.approx(0.75)

    def test_get_state(self):
        """Test getting clipper state."""
        clipper = GradientClipper(mode=ClipMode.NORM, max_norm=1.5)
        state = clipper.get_state()

        assert state["mode"] == ClipMode.NORM
        assert state["max_norm"] == 1.5

    def test_from_state(self):
        """Test creating clipper from state."""
        state = {"mode": ClipMode.VALUE, "max_value": 0.3}
        clipper = GradientClipper.from_state(state)

        assert clipper.mode == ClipMode.VALUE
        assert clipper.max_value == 0.3


class TestClipResult:
    """Tests for ClipResult dataclass."""

    def test_dataclass_fields(self):
        """Test ClipResult fields."""
        result = ClipResult(
            clipped_gradients={"x": 0.5},
            original_norm=1.0,
            clipped_norm=0.5,
            was_clipped=True,
            clip_fraction=0.5,
        )

        assert result.clipped_gradients["x"] == 0.5
        assert result.original_norm == 1.0
        assert result.clipped_norm == 0.5
        assert result.was_clipped is True
        assert result.clip_fraction == 0.5
