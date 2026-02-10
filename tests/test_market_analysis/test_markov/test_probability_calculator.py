"""Tests for Markov probability calculator module."""

import pytest

from market_analysis.markov.probability_calculator import (
    ProbabilityCalculator,
    RollingWindowAnalysis,
    TransitionPrediction,
)
from market_analysis.markov.state_model import (
    MARKOV_STATES,
    StateHistory,
    StateTransition,
    TransitionMatrix,
    TrendState,
)


class TestTransitionPrediction:
    """Test cases for TransitionPrediction dataclass."""

    def test_creation(self):
        """Test creating TransitionPrediction."""
        matrix = TransitionMatrix()
        prediction = TransitionPrediction(
            current_state=TrendState.BULLISH,
            predicted_state=TrendState.BULLISH,
            confidence=0.8,
            probabilities={state: 0.25 for state in MARKOV_STATES},
            transition_matrix=matrix,
        )
        assert prediction.current_state == TrendState.BULLISH
        assert prediction.predicted_state == TrendState.BULLISH
        assert prediction.confidence == 0.8

    def test_get_probability(self):
        """Test getting probability for specific state."""
        matrix = TransitionMatrix()
        probabilities = {
            TrendState.BULLISH: 0.7,
            TrendState.BEARISH: 0.1,
            TrendState.NEUTRAL: 0.1,
            TrendState.TRANSITIONAL: 0.1,
        }
        prediction = TransitionPrediction(
            current_state=TrendState.BULLISH,
            predicted_state=TrendState.BULLISH,
            confidence=0.8,
            probabilities=probabilities,
            transition_matrix=matrix,
        )
        assert prediction.get_probability(TrendState.BULLISH) == 0.7
        assert prediction.get_probability(TrendState.BEARISH) == 0.1

    def test_is_confident(self):
        """Test confidence threshold check."""
        matrix = TransitionMatrix()
        prediction = TransitionPrediction(
            current_state=TrendState.BULLISH,
            predicted_state=TrendState.BULLISH,
            confidence=0.8,
            probabilities={state: 0.25 for state in MARKOV_STATES},
            transition_matrix=matrix,
        )
        assert prediction.is_confident() is True
        assert prediction.is_confident(threshold=0.9) is False


class TestProbabilityCalculator:
    """Test cases for ProbabilityCalculator class."""

    @pytest.fixture
    def calculator(self):
        """Create a ProbabilityCalculator instance."""
        return ProbabilityCalculator(min_samples=5)

    @pytest.fixture
    def sample_history(self):
        """Create a StateHistory with sample transitions."""
        history = StateHistory(max_size=100)

        # Create pattern: mostly bullish persistence with some transitions
        states = [
            (1609459200000, TrendState.BULLISH, 0.8),
            (1609459260000, TrendState.BULLISH, 0.85),
            (1609459320000, TrendState.BULLISH, 0.9),
            (1609459380000, TrendState.BEARISH, 0.75),  # Transition
            (1609459440000, TrendState.BEARISH, 0.8),
            (1609459500000, TrendState.BEARISH, 0.85),
            (1609459560000, TrendState.BULLISH, 0.7),  # Transition back
            (1609459620000, TrendState.BULLISH, 0.8),
            (1609459680000, TrendState.BULLISH, 0.85),
            (1609459740000, TrendState.NEUTRAL, 0.6),  # To neutral
            (1609459800000, TrendState.NEUTRAL, 0.65),
        ]

        for ts, state, conf in states:
            history.add_state(ts, state, conf)

        return history

    def test_calculate_transition_probabilities(self, calculator, sample_history):
        """Test calculating transition probabilities."""
        matrix = calculator.calculate_transition_probabilities(sample_history)

        # Check that matrix is returned
        assert isinstance(matrix, TransitionMatrix)

        # Check that rows sum to 1
        for state in MARKOV_STATES:
            row = matrix.get_row(state)
            assert abs(sum(row) - 1.0) < 1e-10

    def test_predict_next_state(self, calculator, sample_history):
        """Test predicting next state."""
        calculator.calculate_transition_probabilities(sample_history)

        prediction = calculator.predict_next_state(TrendState.BULLISH)

        assert isinstance(prediction, TransitionPrediction)
        assert prediction.current_state == TrendState.BULLISH
        assert prediction.predicted_state in MARKOV_STATES
        assert 0 <= prediction.confidence <= 1.0

    def test_calculate_state_persistence(self, calculator, sample_history):
        """Test calculating state persistence."""
        persistence = calculator.calculate_state_persistence(sample_history)

        assert len(persistence) == 4
        for state in MARKOV_STATES:
            assert state in persistence
            assert 0 <= persistence[state] <= 1

    def test_calculate_entrance_probabilities(self, calculator, sample_history):
        """Test calculating entrance probabilities."""
        entrances = calculator.calculate_entrance_probabilities(sample_history)

        assert len(entrances) == 4
        for state in MARKOV_STATES:
            assert state in entrances
            assert 0 <= entrances[state] <= 1

        # Should sum to 1
        assert abs(sum(entrances.values()) - 1.0) < 1e-10

    def test_rolling_window_analysis(self, calculator, sample_history):
        """Test rolling window analysis."""
        # Add more transitions for meaningful analysis
        for i in range(60):
            sample_history.add_state(
                1609459800000 + i * 60000,
                TrendState.BULLISH if i % 5 != 0 else TrendState.BEARISH,
                0.8,
            )

        analysis = calculator.rolling_window_analysis(
            sample_history, window_size=20, step_size=5
        )

        assert isinstance(analysis, RollingWindowAnalysis)
        assert analysis.window_size == 20
        assert analysis.step_size == 5
        assert len(analysis.transition_matrices) > 0
        assert len(analysis.timestamps) == len(analysis.transition_matrices)
        assert 0 <= analysis.stability_score <= 1.0

    def test_rolling_window_insufficient_data(self, calculator):
        """Test rolling window with insufficient data."""
        history = StateHistory()
        history.add_state(1609459200000, TrendState.BULLISH, 0.8)
        history.add_state(1609459260000, TrendState.BEARISH, 0.75)

        analysis = calculator.rolling_window_analysis(
            history, window_size=50, step_size=10
        )

        assert len(analysis.transition_matrices) == 0
        assert analysis.stability_score == 0.0

    def test_get_stationary_distribution(self, calculator, sample_history):
        """Test calculating stationary distribution."""
        calculator.calculate_transition_probabilities(sample_history)

        stationary = calculator.get_stationary_distribution()

        assert len(stationary) == 4
        for state in MARKOV_STATES:
            assert state in stationary
            assert 0 <= stationary[state] <= 1

        # Should sum to 1
        assert abs(sum(stationary.values()) - 1.0) < 1e-6

    def test_calculate_expected_time_to_state(self, calculator, sample_history):
        """Test calculating expected time to state."""
        calculator.calculate_transition_probabilities(sample_history)

        expected_time = calculator.calculate_expected_time_to_state(
            TrendState.BULLISH, TrendState.BEARISH
        )

        assert expected_time >= 0 or expected_time == float("inf")

    def test_calculate_expected_time_same_state(self, calculator):
        """Test expected time for same state."""
        result = calculator.calculate_expected_time_to_state(
            TrendState.BULLISH, TrendState.BULLISH
        )
        assert result == 0.0

    def test_update_probabilities_incrementally(self, calculator):
        """Test incremental probability update."""
        # Initialize with some data
        history = StateHistory()
        for i in range(10):
            history.add_state(
                1609459200000 + i * 60000,
                TrendState.BULLISH,
                0.8,
            )

        calculator.calculate_transition_probabilities(history)

        # Get initial probability
        initial_prob = calculator._transition_matrix.get_probability(
            TrendState.BULLISH, TrendState.BULLISH
        )

        # Update with new transition
        transition = StateTransition(
            from_state=TrendState.BULLISH,
            to_state=TrendState.BULLISH,
            timestamp=1609459800000,
            confidence=0.9,
        )
        calculator.update_probabilities_incrementally(transition, learning_rate=0.1)

        # Probability should have changed
        new_prob = calculator._transition_matrix.get_probability(
            TrendState.BULLISH, TrendState.BULLISH
        )
        assert new_prob != initial_prob

    def test_smoothing_with_few_samples(self):
        """Test that smoothing works with few samples."""
        calculator = ProbabilityCalculator(min_samples=100)  # High threshold
        history = StateHistory()

        # Add just a few transitions
        for i in range(5):
            history.add_state(
                1609459200000 + i * 60000,
                TrendState.BULLISH if i % 2 == 0 else TrendState.BEARISH,
                0.8,
            )

        # Should still work (with warning)
        matrix = calculator.calculate_transition_probabilities(history)

        # Check that all probabilities are valid (non-zero due to smoothing)
        for from_state in MARKOV_STATES:
            for to_state in MARKOV_STATES:
                prob = matrix.get_probability(from_state, to_state)
                assert prob > 0  # Smoothing ensures no zeros

    def test_predict_with_custom_matrix(self, calculator, sample_history):
        """Test prediction with custom transition matrix."""
        custom_matrix = TransitionMatrix()
        custom_matrix.set_probability(TrendState.BULLISH, TrendState.BULLISH, 0.9)
        custom_matrix.set_probability(TrendState.BULLISH, TrendState.BEARISH, 0.1)
        custom_matrix.set_probability(TrendState.BULLISH, TrendState.NEUTRAL, 0.0)
        custom_matrix.set_probability(TrendState.BULLISH, TrendState.TRANSITIONAL, 0.0)

        prediction = calculator.predict_next_state(
            TrendState.BULLISH, transition_matrix=custom_matrix
        )

        assert prediction.predicted_state == TrendState.BULLISH
        assert prediction.get_probability(TrendState.BULLISH) == 0.9
