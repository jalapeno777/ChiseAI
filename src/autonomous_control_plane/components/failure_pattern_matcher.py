"""Failure pattern matcher with pattern registry.

Provides centralized pattern matching with priority/scoring.

For ST-NS-040: Self-Healing Engine with Action Sandboxing
"""

from __future__ import annotations

import logging
from typing import Any

from autonomous_control_plane.components.failure_patterns import (
    ALL_PATTERNS,
    BaseFailurePattern,
)
from autonomous_control_plane.models.healing import (
    FailurePatternMatch,
    FailurePatternType,
    LogEntry,
)

logger = logging.getLogger(__name__)


class FailurePatternMatcher:
    """Matches log entries against registered failure patterns.

    Provides:
    - Pattern registration and management
    - Priority-based matching
    - Confidence scoring
    - Best match selection

    Example:
        >>> matcher = FailurePatternMatcher()
        >>> matcher.register_default_patterns()
        >>> match = matcher.match(log_entry)
        >>> if match.matched:
        ...     print(f"Detected: {match.pattern_type}")
    """

    def __init__(self):
        """Initialize pattern matcher."""
        self._patterns: list[BaseFailurePattern] = []
        self._pattern_types: dict[FailurePatternType, BaseFailurePattern] = {}

    def register(self, pattern: BaseFailurePattern) -> None:
        """Register a failure pattern.

        Args:
            pattern: Pattern matcher to register
        """
        self._patterns.append(pattern)
        self._pattern_types[pattern.pattern_type] = pattern
        logger.debug(f"Registered pattern: {pattern.pattern_type.value}")

    def register_default_patterns(self) -> None:
        """Register all default patterns."""
        for pattern_class in ALL_PATTERNS:
            self.register(pattern_class())
        logger.info(f"Registered {len(ALL_PATTERNS)} default patterns")

    def unregister(self, pattern_type: FailurePatternType) -> BaseFailurePattern | None:
        """Unregister a pattern by type.

        Args:
            pattern_type: Type of pattern to unregister

        Returns:
            Removed pattern or None
        """
        pattern = self._pattern_types.pop(pattern_type, None)
        if pattern:
            self._patterns = [
                p for p in self._patterns if p.pattern_type != pattern_type
            ]
            logger.debug(f"Unregistered pattern: {pattern_type.value}")
        return pattern

    def match(self, log_entry: LogEntry) -> FailurePatternMatch:
        """Match log entry against all registered patterns.

        Returns the best match based on confidence and priority.

        Args:
            log_entry: Log entry to match

        Returns:
            Best match result
        """
        matches: list[FailurePatternMatch] = []

        for pattern in self._patterns:
            try:
                match = pattern.match(log_entry)
                if match.matched:
                    matches.append(match)
            except Exception as e:
                logger.warning(
                    f"Pattern {pattern.pattern_type.value} matching failed: {e}"
                )

        if not matches:
            return FailurePatternMatch.no_match()

        # Select best match based on priority (higher is better) then confidence
        best_match = max(matches, key=lambda m: (m.priority, m.confidence))

        assert (
            best_match.pattern_type is not None
        ), "Best match should have a pattern_type"
        logger.debug(
            f"Best match: {best_match.pattern_type.value} "
            f"(priority={best_match.priority}, confidence={best_match.confidence:.2f})"
        )

        return best_match

    def match_all(self, log_entry: LogEntry) -> list[FailurePatternMatch]:
        """Match log entry and return all matching patterns.

        Args:
            log_entry: Log entry to match

        Returns:
            List of all matches sorted by priority/confidence
        """
        matches: list[FailurePatternMatch] = []

        for pattern in self._patterns:
            try:
                match = pattern.match(log_entry)
                if match.matched:
                    matches.append(match)
            except Exception as e:
                logger.warning(
                    f"Pattern {pattern.pattern_type.value} matching failed: {e}"
                )

        # Sort by priority (descending) then confidence (descending)
        matches.sort(key=lambda m: (m.priority, m.confidence), reverse=True)

        return matches

    def get_pattern(
        self, pattern_type: FailurePatternType
    ) -> BaseFailurePattern | None:
        """Get a registered pattern by type.

        Args:
            pattern_type: Type of pattern to get

        Returns:
            Pattern or None if not registered
        """
        return self._pattern_types.get(pattern_type)

    def list_patterns(self) -> list[dict[str, Any]]:
        """List all registered patterns.

        Returns:
            List of pattern information
        """
        return [
            {
                "type": p.pattern_type.value,
                "priority": p.priority,
            }
            for p in self._patterns
        ]

    def clear(self) -> None:
        """Clear all registered patterns."""
        self._patterns.clear()
        self._pattern_types.clear()
        logger.debug("Cleared all patterns")

    @property
    def pattern_count(self) -> int:
        """Number of registered patterns."""
        return len(self._patterns)
