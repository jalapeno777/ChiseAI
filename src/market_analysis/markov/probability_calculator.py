"""Probability calculator for Markov state transitions.

Calculates transition probabilities from historical state sequences,
predicts most likely next states, and provides confidence scores.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from market_analysis.markov.state_model import (
    MARKOV_STATES,
    StateHistory,
    StateTransition,
    TransitionMatrix,
    TrendState,
)

logger = logging.getLogger(__name__)


@dataclass
class TransitionPrediction:
    """Prediction for next state transition.

    Attributes:
        current_state: The current trend state
        predicted_state: The most likely next state
        confidence: Confidence score for the prediction (0.0-1.0)
        probabilities: Dictionary of all state probabilities
        transition_matrix: The transition matrix used for prediction
    """

    current_state: TrendState
    predicted_state: TrendState
    confidence: float
    probabilities: dict[TrendState, float]
    transition_matrix: TransitionMatrix

    def get_probability(self, state: TrendState) -> float:
        """Get probability for a specific state."""
        return self.probabilities.get(state, 0.0)

    def is_confident(self, threshold: float = 0.6) -> bool:
        """Check if prediction meets confidence threshold."""
        return self.confidence >= threshold


@dataclass
class RollingWindowAnalysis:
    """Results from rolling window probability analysis.

    Attributes:
        window_size: Size of the rolling window
        step_size: Step size for window movement
        transition_matrices: List of transition matrices for each window
        timestamps: List of timestamps for each window
        stability_score: Measure of how stable probabilities are (0-1)
    """

    window_size: int
    step_size: int
    transition_matrices: list[TransitionMatrix]
    timestamps: list[int]
    stability_score: float

    def get_trend(self) -> dict[TrendState, list[float]]:
        """Get probability trends for each state over time.

        Returns:
            Dictionary mapping states to lists of probabilities
        """
        trends: dict[TrendState, list[float]] = {state: [] for state in MARKOV_STATES}

        for matrix in self.transition_matrices:
            for state in MARKOV_STATES:
                # Get self-transition probability (persistence)
                prob = matrix.get_probability(state, state)
                trends[state].append(prob)

        return trends


class ProbabilityCalculator:
    """Calculator for Markov state transition probabilities.

    Computes transition probabilities from historical state sequences,
    predicts next states, and analyzes probability stability over time.
    """

    def __init__(
        self,
        min_samples: int = 10,
        smoothing_factor: float = 0.1,
        prior_weight: float = 1.0,
    ):
        """Initialize probability calculator.

        Args:
            min_samples: Minimum number of transitions for reliable estimates
            smoothing_factor: Laplace smoothing factor (additive smoothing)
            prior_weight: Weight for uniform prior (prevents zero probabilities)
        """
        self.min_samples = min_samples
        self.smoothing_factor = smoothing_factor
        self.prior_weight = prior_weight
        self._transition_matrix = TransitionMatrix()

    def calculate_transition_probabilities(
        self, state_history: StateHistory
    ) -> TransitionMatrix:
        """Calculate transition probabilities from state history.

        Args:
            state_history: History of states and transitions

        Returns:
            TransitionMatrix with calculated probabilities
        """
        counts = state_history.get_transition_counts()
        total_transitions = sum(counts.values())

        if total_transitions < self.min_samples:
            logger.warning(
                f"Insufficient samples ({total_transitions} < {self.min_samples}) "
                f"for reliable probability estimates"
            )

        # Create new matrix with smoothing
        matrix = TransitionMatrix()

        for from_state in MARKOV_STATES:
            row_counts = []
            total_count = 0

            for to_state in MARKOV_STATES:
                count = counts.get((from_state, to_state), 0)
                row_counts.append(count)
                total_count += count

            # Apply Laplace smoothing
            smoothed_total = total_count + self.smoothing_factor * len(MARKOV_STATES)

            for i, to_state in enumerate(MARKOV_STATES):
                smoothed_count = row_counts[i] + self.smoothing_factor
                probability = (
                    smoothed_count / smoothed_total if smoothed_total > 0 else 0.25
                )
                matrix.set_probability(from_state, to_state, probability)

        # Store and return
        self._transition_matrix = matrix
        return matrix

    def predict_next_state(
        self,
        current_state: TrendState,
        transition_matrix: TransitionMatrix | None = None,
    ) -> TransitionPrediction:
        """Predict the most likely next state.

        Args:
            current_state: The current trend state
            transition_matrix: Optional custom transition matrix
                (uses calculated matrix if None)

        Returns:
            TransitionPrediction with predicted state and confidence
        """
        matrix = transition_matrix or self._transition_matrix

        # Get probabilities for all states
        probabilities = {
            state: matrix.get_probability(current_state, state)
            for state in MARKOV_STATES
        }

        # Find most likely state
        predicted_state = max(probabilities.items(), key=lambda x: x[1])[0]

        # Calculate confidence
        confidence = matrix.get_confidence(current_state, predicted_state)

        return TransitionPrediction(
            current_state=current_state,
            predicted_state=predicted_state,
            confidence=confidence,
            probabilities=probabilities,
            transition_matrix=matrix,
        )

    def calculate_state_persistence(
        self, state_history: StateHistory
    ) -> dict[TrendState, float]:
        """Calculate persistence probability for each state.

        Persistence is the probability of staying in the same state.

        Args:
            state_history: History of states and transitions

        Returns:
            Dictionary mapping states to persistence probabilities
        """
        counts = state_history.get_transition_counts()
        persistence: dict[TrendState, float] = {}

        for state in MARKOV_STATES:
            self_transitions = counts.get((state, state), 0)
            total_from_state = sum(
                counts.get((state, to_state), 0) for to_state in MARKOV_STATES
            )

            if total_from_state > 0:
                persistence[state] = self_transitions / total_from_state
            else:
                persistence[state] = 0.25  # Default uniform

        return persistence

    def calculate_entrance_probabilities(
        self, state_history: StateHistory
    ) -> dict[TrendState, float]:
        """Calculate probability of entering each state.

        Args:
            state_history: History of states and transitions

        Returns:
            Dictionary mapping states to entrance probabilities
        """
        if not state_history.transitions:
            return {state: 0.25 for state in MARKOV_STATES}

        entrance_counts: dict[TrendState, int] = {state: 0 for state in MARKOV_STATES}

        for transition in state_history.transitions:
            entrance_counts[transition.to_state] += 1

        total = len(state_history.transitions)
        return {state: count / total for state, count in entrance_counts.items()}

    def rolling_window_analysis(
        self,
        state_history: StateHistory,
        window_size: int = 50,
        step_size: int = 10,
    ) -> RollingWindowAnalysis:
        """Analyze transition probabilities over rolling windows.

        Args:
            state_history: History of states and transitions
            window_size: Number of transitions per window
            step_size: Number of transitions to advance per step

        Returns:
            RollingWindowAnalysis with matrices and stability metrics
        """
        transitions = state_history.transitions

        if len(transitions) < window_size:
            logger.warning(
                f"Insufficient transitions ({len(transitions)} < {window_size}) "
                f"for rolling window analysis"
            )
            return RollingWindowAnalysis(
                window_size=window_size,
                step_size=step_size,
                transition_matrices=[],
                timestamps=[],
                stability_score=0.0,
            )

        matrices: list[TransitionMatrix] = []
        timestamps: list[int] = []

        # Slide window over transitions
        for start in range(0, len(transitions) - window_size + 1, step_size):
            end = start + window_size
            window_transitions = transitions[start:end]

            # Create temporary state history for this window
            window_history = StateHistory(max_size=window_size)
            window_history.transitions = list(window_transitions)

            # Calculate matrix for this window
            matrix = self.calculate_transition_probabilities(window_history)
            matrices.append(matrix)

            # Use end timestamp
            if window_transitions:
                timestamps.append(window_transitions[-1].timestamp)

        # Calculate stability score
        stability_score = self._calculate_stability_score(matrices)

        return RollingWindowAnalysis(
            window_size=window_size,
            step_size=step_size,
            transition_matrices=matrices,
            timestamps=timestamps,
            stability_score=stability_score,
        )

    def _calculate_stability_score(self, matrices: list[TransitionMatrix]) -> float:
        """Calculate stability score from sequence of matrices.

        Stability measures how consistent probabilities are over time.
        Higher score = more stable = more reliable predictions.

        Args:
            matrices: List of transition matrices

        Returns:
            Stability score (0.0-1.0)
        """
        if len(matrices) < 2:
            return 1.0  # Perfectly stable with single matrix

        total_variance = 0.0
        num_comparisons = 0

        for i in range(1, len(matrices)):
            prev_matrix = matrices[i - 1]
            curr_matrix = matrices[i]

            # Calculate variance for each transition probability
            for from_state in MARKOV_STATES:
                for to_state in MARKOV_STATES:
                    prev_prob = prev_matrix.get_probability(from_state, to_state)
                    curr_prob = curr_matrix.get_probability(from_state, to_state)
                    variance = (curr_prob - prev_prob) ** 2
                    total_variance += variance
                    num_comparisons += 1

        if num_comparisons == 0:
            return 1.0

        avg_variance = total_variance / num_comparisons
        # Convert to stability score (lower variance = higher stability)
        stability = max(0.0, 1.0 - avg_variance * 10)

        return stability

    def get_stationary_distribution(
        self, transition_matrix: TransitionMatrix | None = None
    ) -> dict[TrendState, float]:
        """Calculate stationary distribution of the Markov chain.

        The stationary distribution represents long-term state probabilities.

        Args:
            transition_matrix: Optional custom transition matrix

        Returns:
            Dictionary mapping states to long-term probabilities
        """
        matrix = transition_matrix or self._transition_matrix

        # Power iteration to find stationary distribution
        # Start with uniform distribution
        dist = [0.25] * 4

        for _ in range(100):  # Max iterations
            new_dist = [0.0] * 4
            for j in range(4):
                for i in range(4):
                    new_dist[j] += dist[i] * matrix.matrix[i][j]

            # Check convergence
            if max(abs(new_dist[i] - dist[i]) for i in range(4)) < 1e-6:
                break

            dist = new_dist

        # Map to states
        index_to_state = {v: k for k, v in matrix.state_index.items()}
        return {index_to_state[i]: dist[i] for i in range(4)}

    def calculate_expected_time_to_state(
        self,
        from_state: TrendState,
        to_state: TrendState,
        transition_matrix: TransitionMatrix | None = None,
    ) -> float:
        """Calculate expected number of steps to reach a state.

        Uses fundamental matrix approach for absorbing Markov chains.

        Args:
            from_state: Starting state
            to_state: Target state
            transition_matrix: Optional custom transition matrix

        Returns:
            Expected number of steps (infinity if unreachable)
        """
        matrix = transition_matrix or self._transition_matrix

        if from_state == to_state:
            return 0.0

        # Get transition probability
        prob = matrix.get_probability(from_state, to_state)

        if prob > 0:
            # Geometric distribution expected value
            return 1.0 / prob

        # If direct transition probability is 0, estimate from matrix structure
        # This is a simplified approximation
        return float("inf")

    def update_probabilities_incrementally(
        self,
        new_transition: StateTransition,
        learning_rate: float = 0.1,
    ) -> None:
        """Update transition probabilities incrementally with new data.

        Uses exponential moving average for online learning.

        Args:
            new_transition: The new state transition observed
            learning_rate: Rate at which to incorporate new data (0-1)
        """
        from_state = new_transition.from_state
        to_state = new_transition.to_state

        # Current probability
        current_prob = self._transition_matrix.get_probability(from_state, to_state)

        # Update with exponential moving average
        # New observation counts as 1.0 for the specific transition
        new_prob = current_prob * (1 - learning_rate) + learning_rate * 1.0

        self._transition_matrix.set_probability(from_state, to_state, new_prob)

        # Renormalize the row
        self._transition_matrix.normalize()

        logger.debug(
            f"Updated P({from_state}->{to_state}): {current_prob:.3f} -> {new_prob:.3f}"
        )
