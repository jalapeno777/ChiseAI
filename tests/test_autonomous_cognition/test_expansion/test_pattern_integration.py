"""Integration tests for pattern recognition wired into belief expansion.

These tests verify that:
1. Pattern recognition is properly integrated into the expansion engine
2. Pattern confidence influences expansion scoring
3. The integration works without circular import errors
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestPatternIntegration:
    """Test pattern recognition integration in belief expansion."""

    def test_expand_belief_queries_pattern_recognizer(self):
        """Test that expand_belief queries pattern recognition for patterns."""
        from src.autonomous_cognition.expansion.belief_expansion import (
            ExpansionConfig,
        )
        from src.autonomous_cognition.expansion.engine import BeliefExpander

        config = ExpansionConfig(min_confidence=0.3, min_relevance_score=0.1)
        expander = BeliefExpander(config=config)

        # Mock the pattern recognizer
        mock_pattern_probs = {
            "double_top": 0.85,
            "head_and_shoulders": 0.45,
            "ascending_triangle": 0.32,
        }

        with patch(
            "src.autonomous_cognition.expansion.engine._get_pattern_recognizer"
        ) as mock_get_recognizer:
            mock_recognizer = MagicMock()
            mock_recognizer.get_pattern_probabilities.return_value = mock_pattern_probs
            mock_get_recognizer.return_value = mock_recognizer

            # Patch _query_patterns to use our mock
            with patch.object(
                expander, "_query_patterns", return_value=mock_pattern_probs
            ):
                # Use statement with "is" to trigger ANALOGY expansion
                expansions = expander.expand_belief(
                    belief_id="test_belief_1",
                    statement="Price at 150.00 is showing resistance",
                    domain="trading",
                    confidence=0.7,
                )

        # Should have generated expansions
        assert len(expansions) > 0

        # Check that pattern confidence is stored in metadata
        for expansion in expansions:
            assert "pattern_confidence" in expansion.metadata
            assert expansion.metadata["pattern_confidence"] == 0.85

    def test_pattern_boost_increases_confidence(self):
        """Test that high-confidence patterns boost expansion confidence."""
        from src.autonomous_cognition.expansion.belief_expansion import (
            ExpansionConfig,
        )
        from src.autonomous_cognition.expansion.engine import BeliefExpander

        config = ExpansionConfig(min_confidence=0.3, min_relevance_score=0.1)
        expander = BeliefExpander(config=config)

        # Pattern with high confidence should boost derived confidence
        high_confidence_patterns = {"double_top": 0.85}

        with patch.object(
            expander, "_query_patterns", return_value=high_confidence_patterns
        ):
            # Use statement with "is" to trigger ANALOGY expansion
            expansions = expander.expand_belief(
                belief_id="test_belief_2",
                statement="Price at 200.00 is showing reversal patterns",
                domain="trading",
                confidence=0.6,
            )

        assert len(expansions) > 0

        # With pattern boost, confidence should be higher than base decay (0.6 * 0.85 = 0.51)
        # Pattern boost = 0.85 * 0.1 = 0.085, so final should be min(1.0, 0.51 + 0.085) = 0.595
        for expansion in expansions:
            # Base confidence after decay would be 0.6 * 0.85 = 0.51
            # Pattern boost should add ~0.085, so total should be around 0.595
            assert expansion.confidence > 0.51

    def test_no_pattern_boost_when_low_confidence(self):
        """Test that low-confidence patterns don't boost expansion confidence."""
        from src.autonomous_cognition.expansion.belief_expansion import ExpansionConfig
        from src.autonomous_cognition.expansion.engine import BeliefExpander

        config = ExpansionConfig(min_confidence=0.3, min_relevance_score=0.1)
        expander = BeliefExpander(config=config)

        # Low confidence patterns (below 0.7 threshold)
        low_confidence_patterns = {"v_top": 0.3}

        with patch.object(
            expander, "_query_patterns", return_value=low_confidence_patterns
        ):
            expansions = expander.expand_belief(
                belief_id="test_belief_3",
                statement="Price fluctuating around 100.00",
                domain="trading",
                confidence=0.6,
            )

        if expansions:
            # Without pattern boost, confidence should be base decay: 0.6 * 0.85 = 0.51
            for expansion in expansions:
                # pattern_boost_applied should be False
                assert expansion.metadata.get("pattern_boost_applied") is False

    def test_pattern_recognition_unavailable_graceful_degradation(self):
        """Test that expansion works when pattern recognition is unavailable."""
        from src.autonomous_cognition.expansion.belief_expansion import ExpansionConfig
        from src.autonomous_cognition.expansion.engine import BeliefExpander

        config = ExpansionConfig(min_confidence=0.3, min_relevance_score=0.1)
        expander = BeliefExpander(config=config)

        # Simulate pattern recognizer returning None
        with patch.object(expander, "_query_patterns", return_value={}):
            expansions = expander.expand_belief(
                belief_id="test_belief_4",
                statement="Price is rising",
                domain="trading",
                confidence=0.7,
            )

        # Should still produce expansions without error
        assert expansions is not None
        assert isinstance(expansions, list)

    def test_query_patterns_returns_empty_when_no_numbers(self):
        """Test that _query_patterns handles statements without numbers."""
        from src.autonomous_cognition.expansion.engine import BeliefExpander

        expander = BeliefExpander()

        with patch(
            "src.autonomous_cognition.expansion.engine._get_pattern_recognizer",
            return_value=None,
        ):
            result = expander._query_patterns("This is a belief without numbers")

        assert result == {}

    def test_query_patterns_extracts_numbers_from_statement(self):
        """Test that _query_patterns extracts numbers for pattern recognition."""
        from src.autonomous_cognition.expansion.engine import BeliefExpander

        expander = BeliefExpander()

        mock_recognizer = MagicMock()
        mock_recognizer.get_pattern_probabilities.return_value = {
            "ascending_triangle": 0.75
        }

        with patch(
            "src.autonomous_cognition.expansion.engine._get_pattern_recognizer",
            return_value=mock_recognizer,
        ):
            result = expander._query_patterns(
                "Price moved from 100.00 to 150.50 with volume at 1000000"
            )

        # Should have called get_pattern_probabilities with extracted numbers
        mock_recognizer.get_pattern_probabilities.assert_called_once()
        call_args = mock_recognizer.get_pattern_probabilities.call_args[0][0]
        # Should contain extracted price values
        assert isinstance(call_args, list)

    def test_metadata_contains_pattern_information(self):
        """Test that expansion metadata includes pattern information."""
        from src.autonomous_cognition.expansion.belief_expansion import ExpansionConfig
        from src.autonomous_cognition.expansion.engine import BeliefExpander

        config = ExpansionConfig(min_confidence=0.3, min_relevance_score=0.1)
        expander = BeliefExpander(config=config)

        patterns = {"head_and_shoulders": 0.72, "double_top": 0.65}

        with patch.object(expander, "_query_patterns", return_value=patterns):
            # Use statement with "is" to trigger ANALOGY expansion
            expansions = expander.expand_belief(
                belief_id="test_belief_5",
                statement="Chart at 175.00 is showing a bullish pattern",
                domain="technical_analysis",
                confidence=0.65,
            )

        assert len(expansions) > 0
        for expansion in expansions:
            # Check metadata fields
            assert "pattern_confidence" in expansion.metadata
            assert "pattern_boost_applied" in expansion.metadata
            assert expansion.metadata["pattern_confidence"] == 0.72
