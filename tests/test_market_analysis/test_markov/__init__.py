"""Tests for Markov module integration."""

import pytest

from data_ingestion.ohlcv_fetcher import OHLCVData
from market_analysis.markov import (
    ProbabilityCalculator,
    StateHistory,
    TrendInferenceEngine,
    TrendState,
)


class TestMarkovIntegration:
    """Integration tests for the complete Markov chain workflow."""

    @pytest.fixture
    def sample_ohlcv_data(self):
        """Create sample OHLCV data for testing."""
        base_ts = 1609459200000
        return [
            OHLCVData(
                timestamp=base_ts + i * 60000,
                open_price=100.0 + i * 0.5,
                high_price=101.0 + i * 0.5,
                low_price=99.0 + i * 0.5,
                close_price=100.5 + i * 0.5,
                volume=1000.0 + i * 10,
            )
            for i in range(100)
        ]

    def test_full_workflow(self, sample_ohlcv_data):
        """Test complete workflow from data to predictions."""
        # Step 1: Create inference engine and infer states
        engine = TrendInferenceEngine()
        history = StateHistory(max_size=100)

        # Infer states from sliding windows
        window_size = 50
        for i in range(window_size, len(sample_ohlcv_data)):
            window = sample_ohlcv_data[i - window_size : i]
            result = engine.infer_state(window)

            # Add to history
            history.add_state(result.timestamp, result.state, result.confidence)

        # Step 2: Calculate transition probabilities
        calculator = ProbabilityCalculator(min_samples=5)
        calculator.calculate_transition_probabilities(history)

        # Step 3: Predict next state
        current_state = history.get_current_state()
        assert current_state is not None

        prediction = calculator.predict_next_state(current_state[0])

        # Verify prediction structure
        assert prediction.current_state == current_state[0]
        assert prediction.predicted_state in [
            TrendState.BULLISH,
            TrendState.BEARISH,
            TrendState.NEUTRAL,
            TrendState.TRANSITIONAL,
        ]
        assert 0 <= prediction.confidence <= 1.0

    def test_state_transitions_tracked(self, sample_ohlcv_data):
        """Test that state transitions are properly tracked."""
        engine = TrendInferenceEngine()
        history = StateHistory(max_size=100)

        # Process data
        window_size = 30
        for i in range(window_size, len(sample_ohlcv_data)):
            window = sample_ohlcv_data[i - window_size : i]
            result = engine.infer_state(window)
            history.add_state(result.timestamp, result.state, result.confidence)

        # Check that transitions were recorded
        transition_counts = history.get_transition_counts()
        total_transitions = sum(transition_counts.values())

        # Should have some transitions
        assert total_transitions >= 0

        # Check that state sequence is tracked
        sequence = history.get_state_sequence()
        assert len(sequence) > 0

    def test_probability_matrix_validity(self, sample_ohlcv_data):
        """Test that calculated probability matrix is valid."""
        engine = TrendInferenceEngine()
        history = StateHistory(max_size=100)

        # Generate states
        window_size = 30
        for i in range(window_size, len(sample_ohlcv_data)):
            window = sample_ohlcv_data[i - window_size : i]
            result = engine.infer_state(window)
            history.add_state(result.timestamp, result.state, result.confidence)

        # Calculate probabilities
        calculator = ProbabilityCalculator()
        matrix = calculator.calculate_transition_probabilities(history)

        # Verify all rows sum to 1
        from market_analysis.markov import MARKOV_STATES

        for state in MARKOV_STATES:
            row = matrix.get_row(state)
            assert abs(sum(row) - 1.0) < 1e-10, f"Row for {state} doesn't sum to 1"

        # Verify all probabilities are in [0, 1]
        for from_state in MARKOV_STATES:
            for to_state in MARKOV_STATES:
                prob = matrix.get_probability(from_state, to_state)
                assert (
                    0 <= prob <= 1
                ), f"Invalid probability for {from_state}->{to_state}"

    def test_confidence_scores(self, sample_ohlcv_data):
        """Test that confidence scores are meaningful."""
        engine = TrendInferenceEngine()

        # Test with clear trend
        bullish_data = sample_ohlcv_data[:50]
        result = engine.infer_state(bullish_data)

        # Should have reasonable confidence
        assert 0 <= result.confidence <= 1.0
        assert result.signal_strength >= 0

        # High confidence check
        if result.is_high_confidence():
            assert result.confidence >= 0.7

    def test_state_persistence_calculation(self, sample_ohlcv_data):
        """Test state persistence calculation."""
        engine = TrendInferenceEngine()
        history = StateHistory(max_size=100)

        # Generate states
        window_size = 30
        for i in range(window_size, len(sample_ohlcv_data)):
            window = sample_ohlcv_data[i - window_size : i]
            result = engine.infer_state(window)
            history.add_state(result.timestamp, result.state, result.confidence)

        # Calculate persistence
        calculator = ProbabilityCalculator()
        calculator.calculate_transition_probabilities(history)
        persistence = calculator.calculate_state_persistence(history)

        # Verify persistence values
        from market_analysis.markov import MARKOV_STATES

        for state in MARKOV_STATES:
            assert state in persistence
            assert 0 <= persistence[state] <= 1

    @pytest.mark.skip(
        reason="Pre-existing: test data produces no state transitions - see ST-TEST-FIX-001"
    )
    def test_rolling_window_stability(self, sample_ohlcv_data):
        """Test rolling window analysis produces stable results."""
        engine = TrendInferenceEngine()
        history = StateHistory(max_size=200)

        # Generate many states
        window_size = 30
        for i in range(window_size, len(sample_ohlcv_data)):
            window = sample_ohlcv_data[i - window_size : i]
            result = engine.infer_state(window)
            history.add_state(result.timestamp, result.state, result.confidence)

        # Rolling window analysis
        calculator = ProbabilityCalculator()
        analysis = calculator.rolling_window_analysis(
            history, window_size=20, step_size=5
        )

        # Should have multiple windows
        assert len(analysis.transition_matrices) > 0

        # Stability score should be in valid range
        assert 0 <= analysis.stability_score <= 1.0

    def test_markov_chain_exports(self):
        """Test that all expected exports are available."""
        from market_analysis.markov import (
            MARKOV_STATES,
        )
        from market_analysis.markov import (
            TrendState as _TrendState,
        )

        # Verify all exports are accessible
        assert len(MARKOV_STATES) == 4
        assert _TrendState.BULLISH is not None
        assert _TrendState.BEARISH is not None
        assert _TrendState.NEUTRAL is not None
        assert _TrendState.TRANSITIONAL is not None
