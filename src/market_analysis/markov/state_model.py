"""Markov state model for trend state definitions and transition matrix.

Defines the four trend states (bullish, bearish, neutral, transitional)
and manages the state transition probability matrix.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from enum import Enum, auto

logger = logging.getLogger(__name__)


class TrendState(Enum):
    """Trend state enumeration.

    Represents the four possible market trend states:
    - BULLISH: Rising prices with positive momentum
    - BEARISH: Falling prices with negative momentum
    - NEUTRAL: Sideways/ranging prices with low volatility
    - TRANSITIONAL: High volatility with mixed signals
    """

    BULLISH = auto()
    BEARISH = auto()
    NEUTRAL = auto()
    TRANSITIONAL = auto()

    def __str__(self) -> str:
        """Return human-readable state name."""
        return self.name.lower()

    @property
    def is_trending(self) -> bool:
        """Check if state represents a trending market."""
        return self in (TrendState.BULLISH, TrendState.BEARISH)

    @property
    def is_stable(self) -> bool:
        """Check if state represents a stable/non-volatile market."""
        return self == TrendState.NEUTRAL


# All Markov states for iteration
MARKOV_STATES = list(TrendState)


@dataclass
class StateTransition:
    """Represents a single state transition.

    Attributes:
        from_state: The state transitioning from
        to_state: The state transitioning to
        timestamp: When the transition occurred (ms)
        confidence: Confidence score for this transition (0.0-1.0)
    """

    from_state: TrendState
    to_state: TrendState
    timestamp: int
    confidence: float


@dataclass
class StateHistory:
    """Tracks state history for pattern analysis.

    Maintains a rolling window of states and transitions
    for calculating transition probabilities and detecting patterns.

    Attributes:
        max_size: Maximum number of states to retain in history
        states: Deque of (timestamp, state, confidence) tuples
        transitions: List of state transitions
    """

    max_size: int = 1000
    states: deque[tuple[int, TrendState, float]] = field(default_factory=deque)
    transitions: list[StateTransition] = field(default_factory=list)

    def add_state(
        self,
        timestamp: int,
        state: TrendState,
        confidence: float,
    ) -> StateTransition | None:
        """Add a new state to history.

        Args:
            timestamp: Unix timestamp in milliseconds
            state: The detected trend state
            confidence: Confidence score (0.0-1.0)

        Returns:
            StateTransition if this was a state change, None otherwise
        """
        # Add to state history
        self.states.append((timestamp, state, confidence))

        # Maintain max size
        while len(self.states) > self.max_size:
            self.states.popleft()

        # Check for transition
        if len(self.states) >= 2:
            prev_timestamp, prev_state, prev_confidence = list(self.states)[-2]
            if prev_state != state:
                transition = StateTransition(
                    from_state=prev_state,
                    to_state=state,
                    timestamp=timestamp,
                    confidence=confidence,
                )
                self.transitions.append(transition)
                logger.debug(
                    f"State transition: {prev_state} -> {state} "
                    f"at {timestamp} (confidence: {confidence:.3f})"
                )
                return transition

        return None

    def get_state_sequence(self, n: int | None = None) -> list[TrendState]:
        """Get recent state sequence.

        Args:
            n: Number of recent states to return (None for all)

        Returns:
            List of TrendState values
        """
        states_list = [s[1] for s in self.states]
        if n is not None:
            return states_list[-n:]
        return states_list

    def get_current_state(self) -> tuple[TrendState, float] | None:
        """Get the most recent state and confidence.

        Returns:
            Tuple of (state, confidence) or None if no history
        """
        if not self.states:
            return None
        timestamp, state, confidence = self.states[-1]
        return state, confidence

    def get_transition_counts(self) -> dict[tuple[TrendState, TrendState], int]:
        """Count transitions between each state pair.

        Returns:
            Dictionary mapping (from_state, to_state) to count
        """
        counts: dict[tuple[TrendState, TrendState], int] = {}
        for transition in self.transitions:
            key = (transition.from_state, transition.to_state)
            counts[key] = counts.get(key, 0) + 1
        return counts

    def get_state_duration(self, state: TrendState) -> float:
        """Calculate average duration of a state in milliseconds.

        Args:
            state: The state to analyze

        Returns:
            Average duration in milliseconds
        """
        durations: list[int] = []
        current_start: int | None = None

        for timestamp, s, _ in self.states:
            if s == state and current_start is None:
                current_start = timestamp
            elif s != state and current_start is not None:
                durations.append(timestamp - current_start)
                current_start = None

        # Handle case where state is current
        if current_start is not None and self.states:
            last_timestamp = self.states[-1][0]
            durations.append(last_timestamp - current_start)

        if not durations:
            return 0.0

        return sum(durations) / len(durations)

    def clear(self) -> None:
        """Clear all history."""
        self.states.clear()
        self.transitions.clear()


@dataclass
class TransitionMatrix:
    """4x4 Markov transition probability matrix.

    Represents the probability of transitioning from one state to another.
    Rows sum to 1.0 (or 0.0 if no transitions observed).

    Attributes:
        matrix: 4x4 matrix where matrix[i][j] is P(state_j | state_i)
        state_index: Mapping from TrendState to matrix index
    """

    matrix: list[list[float]] = field(
        default_factory=lambda: [[0.25] * 4 for _ in range(4)]
    )

    # Map states to matrix indices
    state_index: dict[TrendState, int] = field(
        default_factory=lambda: {
            TrendState.BULLISH: 0,
            TrendState.BEARISH: 1,
            TrendState.NEUTRAL: 2,
            TrendState.TRANSITIONAL: 3,
        }
    )

    def get_probability(self, from_state: TrendState, to_state: TrendState) -> float:
        """Get transition probability from one state to another.

        Args:
            from_state: The starting state
            to_state: The target state

        Returns:
            Transition probability (0.0-1.0)
        """
        i = self.state_index[from_state]
        j = self.state_index[to_state]
        return self.matrix[i][j]

    def set_probability(
        self, from_state: TrendState, to_state: TrendState, probability: float
    ) -> None:
        """Set transition probability.

        Args:
            from_state: The starting state
            to_state: The target state
            probability: The probability value (0.0-1.0)
        """
        i = self.state_index[from_state]
        j = self.state_index[to_state]
        self.matrix[i][j] = max(0.0, min(1.0, probability))

    def get_row(self, state: TrendState) -> list[float]:
        """Get the transition probability row for a state.

        Args:
            state: The state to get probabilities for

        Returns:
            List of probabilities for all target states
        """
        i = self.state_index[state]
        return self.matrix[i][:]

    def normalize(self) -> None:
        """Normalize each row to sum to 1.0."""
        for i in range(4):
            row_sum = sum(self.matrix[i])
            if row_sum > 0:
                self.matrix[i] = [p / row_sum for p in self.matrix[i]]
            else:
                # Uniform distribution if no data
                self.matrix[i] = [0.25] * 4

    def update_from_counts(
        self, counts: dict[tuple[TrendState, TrendState], int]
    ) -> None:
        """Update matrix from transition counts.

        Args:
            counts: Dictionary of (from_state, to_state) -> count
        """
        # Reset matrix
        self.matrix = [[0.0] * 4 for _ in range(4)]

        # Fill in counts
        for (from_state, to_state), count in counts.items():
            i = self.state_index[from_state]
            j = self.state_index[to_state]
            self.matrix[i][j] = float(count)

        # Normalize
        self.normalize()

    def get_most_likely_next_state(self, current_state: TrendState) -> TrendState:
        """Get the most likely next state from current state.

        Args:
            current_state: The current trend state

        Returns:
            The most likely next state
        """
        row = self.get_row(current_state)
        max_prob = max(row)
        max_index = row.index(max_prob)

        # Reverse lookup
        for state, idx in self.state_index.items():
            if idx == max_index:
                return state

        # Fallback (should never happen)
        return current_state

    def get_confidence(
        self, current_state: TrendState, next_state: TrendState
    ) -> float:
        """Get confidence score for a specific transition.

        Args:
            current_state: The current state
            next_state: The predicted next state

        Returns:
            Confidence score (0.0-1.0)
        """
        probability = self.get_probability(current_state, next_state)

        # Higher probability = higher confidence
        # Also consider how much higher than other options
        row = self.get_row(current_state)
        row_sorted = sorted(row, reverse=True)

        if len(row_sorted) >= 2 and row_sorted[0] > 0:
            # Confidence based on dominance over second best
            dominance = (row_sorted[0] - row_sorted[1]) / row_sorted[0]
            return probability * (0.5 + 0.5 * dominance)

        return probability

    def to_dict(self) -> dict[str, list[float]]:
        """Convert matrix to dictionary for serialization.

        Returns:
            Dictionary mapping state names to probability lists
        """
        result: dict[str, list[float]] = {}
        for state, idx in self.state_index.items():
            result[state.name.lower()] = self.matrix[idx][:]
        return result

    @classmethod
    def from_dict(cls, data: dict[str, list[float]]) -> TransitionMatrix:
        """Create matrix from dictionary.

        Args:
            data: Dictionary mapping state names to probability lists

        Returns:
            New TransitionMatrix instance
        """
        matrix = cls()
        for state_name, probs in data.items():
            state = TrendState[state_name.upper()]
            idx = matrix.state_index[state]
            matrix.matrix[idx] = probs[:]
        return matrix
