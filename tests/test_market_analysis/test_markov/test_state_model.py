"""Tests for Markov state model module."""

import pytest

from market_analysis.markov.state_model import (
    MARKOV_STATES,
    StateHistory,
    StateTransition,
    TransitionMatrix,
    TrendState,
)


class TestTrendState:
    """Test cases for TrendState enum."""

    def test_all_states_defined(self):
        """Test that all four states are defined."""
        assert len(MARKOV_STATES) == 4
        assert TrendState.BULLISH in MARKOV_STATES
        assert TrendState.BEARISH in MARKOV_STATES
        assert TrendState.NEUTRAL in MARKOV_STATES
        assert TrendState.TRANSITIONAL in MARKOV_STATES

    def test_state_str_representation(self):
        """Test string representation of states."""
        assert str(TrendState.BULLISH) == "bullish"
        assert str(TrendState.BEARISH) == "bearish"
        assert str(TrendState.NEUTRAL) == "neutral"
        assert str(TrendState.TRANSITIONAL) == "transitional"

    def test_is_trending_property(self):
        """Test is_trending property."""
        assert TrendState.BULLISH.is_trending is True
        assert TrendState.BEARISH.is_trending is True
        assert TrendState.NEUTRAL.is_trending is False
        assert TrendState.TRANSITIONAL.is_trending is False

    def test_is_stable_property(self):
        """Test is_stable property."""
        assert TrendState.BULLISH.is_stable is False
        assert TrendState.BEARISH.is_stable is False
        assert TrendState.NEUTRAL.is_stable is True
        assert TrendState.TRANSITIONAL.is_stable is False


class TestStateTransition:
    """Test cases for StateTransition dataclass."""

    def test_creation(self):
        """Test creating StateTransition."""
        transition = StateTransition(
            from_state=TrendState.BULLISH,
            to_state=TrendState.BEARISH,
            timestamp=1609459200000,
            confidence=0.85,
        )
        assert transition.from_state == TrendState.BULLISH
        assert transition.to_state == TrendState.BEARISH
        assert transition.timestamp == 1609459200000
        assert transition.confidence == 0.85


class TestStateHistory:
    """Test cases for StateHistory class."""

    @pytest.fixture
    def history(self):
        """Create a StateHistory instance."""
        return StateHistory(max_size=100)

    def test_add_single_state(self, history):
        """Test adding a single state."""
        result = history.add_state(
            timestamp=1609459200000,
            state=TrendState.BULLISH,
            confidence=0.8,
        )
        assert result is None  # No transition with single state
        assert len(history.states) == 1

    def test_add_state_creates_transition(self, history):
        """Test that adding different state creates transition."""
        history.add_state(1609459200000, TrendState.BULLISH, 0.8)
        transition = history.add_state(1609459260000, TrendState.BEARISH, 0.75)

        assert transition is not None
        assert transition.from_state == TrendState.BULLISH
        assert transition.to_state == TrendState.BEARISH
        assert len(history.transitions) == 1

    def test_add_same_state_no_transition(self, history):
        """Test that adding same state doesn't create transition."""
        history.add_state(1609459200000, TrendState.BULLISH, 0.8)
        transition = history.add_state(1609459260000, TrendState.BULLISH, 0.85)

        assert transition is None
        assert len(history.transitions) == 0

    def test_max_size_enforcement(self):
        """Test that max size is enforced."""
        history = StateHistory(max_size=5)

        for i in range(10):
            history.add_state(1609459200000 + i * 60000, TrendState.BULLISH, 0.8)

        assert len(history.states) == 5

    def test_get_state_sequence(self, history):
        """Test getting state sequence."""
        history.add_state(1609459200000, TrendState.BULLISH, 0.8)
        history.add_state(1609459260000, TrendState.BULLISH, 0.8)
        history.add_state(1609459320000, TrendState.BEARISH, 0.75)

        sequence = history.get_state_sequence()
        assert len(sequence) == 3
        assert sequence == [TrendState.BULLISH, TrendState.BULLISH, TrendState.BEARISH]

    def test_get_state_sequence_n_recent(self, history):
        """Test getting n recent states."""
        for i in range(5):
            history.add_state(1609459200000 + i * 60000, TrendState.BULLISH, 0.8)

        sequence = history.get_state_sequence(n=3)
        assert len(sequence) == 3

    def test_get_current_state(self, history):
        """Test getting current state."""
        history.add_state(1609459200000, TrendState.BULLISH, 0.8)
        history.add_state(1609459260000, TrendState.BEARISH, 0.75)

        current = history.get_current_state()
        assert current is not None
        assert current[0] == TrendState.BEARISH
        assert current[1] == 0.75

    def test_get_current_state_empty(self, history):
        """Test getting current state from empty history."""
        current = history.get_current_state()
        assert current is None

    def test_get_transition_counts(self, history):
        """Test getting transition counts."""
        # Create transitions: BULLISH -> BEARISH -> NEUTRAL -> BULLISH
        history.add_state(1609459200000, TrendState.BULLISH, 0.8)
        history.add_state(1609459260000, TrendState.BEARISH, 0.75)
        history.add_state(1609459320000, TrendState.NEUTRAL, 0.7)
        history.add_state(1609459380000, TrendState.BULLISH, 0.8)

        counts = history.get_transition_counts()
        assert counts[(TrendState.BULLISH, TrendState.BEARISH)] == 1
        assert counts[(TrendState.BEARISH, TrendState.NEUTRAL)] == 1
        assert counts[(TrendState.NEUTRAL, TrendState.BULLISH)] == 1

    def test_get_state_duration(self, history):
        """Test calculating state duration."""
        # BULLISH for 2 minutes
        history.add_state(1609459200000, TrendState.BULLISH, 0.8)
        history.add_state(1609459260000, TrendState.BULLISH, 0.8)
        history.add_state(1609459320000, TrendState.BEARISH, 0.75)

        duration = history.get_state_duration(TrendState.BULLISH)
        assert duration == 120000  # 2 minutes in ms

    def test_clear(self, history):
        """Test clearing history."""
        history.add_state(1609459200000, TrendState.BULLISH, 0.8)
        history.add_state(1609459260000, TrendState.BEARISH, 0.75)

        history.clear()
        assert len(history.states) == 0
        assert len(history.transitions) == 0


class TestTransitionMatrix:
    """Test cases for TransitionMatrix class."""

    @pytest.fixture
    def matrix(self):
        """Create a TransitionMatrix instance."""
        return TransitionMatrix()

    def test_default_matrix(self, matrix):
        """Test default matrix is uniform."""
        for state in MARKOV_STATES:
            row = matrix.get_row(state)
            assert all(p == 0.25 for p in row)

    def test_get_and_set_probability(self, matrix):
        """Test getting and setting probabilities."""
        matrix.set_probability(TrendState.BULLISH, TrendState.BEARISH, 0.5)
        prob = matrix.get_probability(TrendState.BULLISH, TrendState.BEARISH)
        assert prob == 0.5

    def test_probability_clamping(self, matrix):
        """Test that probabilities are clamped to [0, 1]."""
        matrix.set_probability(TrendState.BULLISH, TrendState.BEARISH, 1.5)
        assert matrix.get_probability(TrendState.BULLISH, TrendState.BEARISH) == 1.0

        matrix.set_probability(TrendState.BULLISH, TrendState.BEARISH, -0.5)
        assert matrix.get_probability(TrendState.BULLISH, TrendState.BEARISH) == 0.0

    def test_normalize(self, matrix):
        """Test matrix normalization."""
        matrix.set_probability(TrendState.BULLISH, TrendState.BULLISH, 0.5)
        matrix.set_probability(TrendState.BULLISH, TrendState.BEARISH, 0.5)
        matrix.set_probability(TrendState.BULLISH, TrendState.NEUTRAL, 0.0)
        matrix.set_probability(TrendState.BULLISH, TrendState.TRANSITIONAL, 0.0)

        matrix.normalize()

        row = matrix.get_row(TrendState.BULLISH)
        assert abs(sum(row) - 1.0) < 1e-10

    def test_update_from_counts(self, matrix):
        """Test updating matrix from transition counts."""
        counts = {
            (TrendState.BULLISH, TrendState.BULLISH): 80,
            (TrendState.BULLISH, TrendState.BEARISH): 20,
            (TrendState.BEARISH, TrendState.BEARISH): 70,
            (TrendState.BEARISH, TrendState.BULLISH): 30,
        }

        matrix.update_from_counts(counts)

        # Check that rows sum to 1
        for state in [TrendState.BULLISH, TrendState.BEARISH]:
            row = matrix.get_row(state)
            assert abs(sum(row) - 1.0) < 1e-10

        # Check specific probabilities
        bullish_persistence = matrix.get_probability(
            TrendState.BULLISH, TrendState.BULLISH
        )
        assert abs(bullish_persistence - 0.8) < 0.01

    def test_get_most_likely_next_state(self, matrix):
        """Test getting most likely next state."""
        matrix.set_probability(TrendState.BULLISH, TrendState.BULLISH, 0.7)
        matrix.set_probability(TrendState.BULLISH, TrendState.BEARISH, 0.1)
        matrix.set_probability(TrendState.BULLISH, TrendState.NEUTRAL, 0.1)
        matrix.set_probability(TrendState.BULLISH, TrendState.TRANSITIONAL, 0.1)

        most_likely = matrix.get_most_likely_next_state(TrendState.BULLISH)
        assert most_likely == TrendState.BULLISH

    def test_get_confidence(self, matrix):
        """Test getting confidence score."""
        matrix.set_probability(TrendState.BULLISH, TrendState.BULLISH, 0.8)
        matrix.set_probability(TrendState.BULLISH, TrendState.BEARISH, 0.1)
        matrix.set_probability(TrendState.BULLISH, TrendState.NEUTRAL, 0.05)
        matrix.set_probability(TrendState.BULLISH, TrendState.TRANSITIONAL, 0.05)

        confidence = matrix.get_confidence(TrendState.BULLISH, TrendState.BULLISH)
        assert confidence > 0.7  # Should be high due to dominance (0.8 * 0.9375)

    def test_to_dict(self, matrix):
        """Test conversion to dictionary."""
        matrix.set_probability(TrendState.BULLISH, TrendState.BEARISH, 0.5)
        data = matrix.to_dict()

        assert "bullish" in data
        assert "bearish" in data
        assert "neutral" in data
        assert "transitional" in data
        assert len(data["bullish"]) == 4

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "bullish": [0.7, 0.1, 0.1, 0.1],
            "bearish": [0.1, 0.7, 0.1, 0.1],
            "neutral": [0.25, 0.25, 0.25, 0.25],
            "transitional": [0.25, 0.25, 0.25, 0.25],
        }

        matrix = TransitionMatrix.from_dict(data)
        assert matrix.get_probability(TrendState.BULLISH, TrendState.BULLISH) == 0.7
        assert matrix.get_probability(TrendState.BEARISH, TrendState.BEARISH) == 0.7
