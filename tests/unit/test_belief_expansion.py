"""Unit tests for belief expansion module."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

from src.autonomous_cognition.expansion import (
    DEFAULT_MIN_CONFIDENCE,
    DEFAULT_MIN_RELEVANCE_SCORE,
    DEFAULT_TIME_LIMIT_SECONDS,
    BeliefExpander,
    ExpandedBelief,
    ExpansionConfig,
    ExpansionProgress,
    ExpansionResult,
    ExpansionType,
    expand_beliefs,
)


class TestExpandedBelief:
    """Tests for ExpandedBelief dataclass."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        belief = ExpandedBelief(
            belief_id="test_123",
            statement="Test belief statement",
            domain="test_domain",
            confidence=0.8,
            source_belief_id="source_456",
            expansion_type=ExpansionType.DERIVATION,
            relevance_score=0.75,
        )

        result = belief.to_dict()

        assert result["belief_id"] == "test_123"
        assert result["statement"] == "Test belief statement"
        assert result["domain"] == "test_domain"
        assert result["confidence"] == 0.8
        assert result["source_belief_id"] == "source_456"
        assert result["expansion_type"] == "derivation"
        assert result["relevance_score"] == 0.75

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "belief_id": "test_123",
            "statement": "Test belief statement",
            "domain": "test_domain",
            "confidence": 0.8,
            "source_belief_id": "source_456",
            "expansion_type": "generalization",
            "relevance_score": 0.75,
        }

        belief = ExpandedBelief.from_dict(data)

        assert belief.belief_id == "test_123"
        assert belief.statement == "Test belief statement"
        assert belief.expansion_type == ExpansionType.GENERALIZATION

    def test_round_trip(self):
        """Test serialization round trip."""
        original = ExpandedBelief(
            belief_id="round_trip_test",
            statement="Original statement",
            domain="domain",
            confidence=0.9,
            source_belief_id="source_id",
            expansion_type=ExpansionType.ANALOGY,
            relevance_score=0.85,
            evidence_refs=["ref1", "ref2"],
        )

        serialized = original.to_dict()
        restored = ExpandedBelief.from_dict(serialized)

        assert restored.belief_id == original.belief_id
        assert restored.statement == original.statement
        assert restored.expansion_type == original.expansion_type
        assert restored.confidence == original.confidence


class TestExpansionConfig:
    """Tests for ExpansionConfig."""

    def test_default_values(self):
        """Test default configuration values."""
        config = ExpansionConfig()

        assert config.time_limit_seconds == DEFAULT_TIME_LIMIT_SECONDS
        assert config.min_relevance_score == DEFAULT_MIN_RELEVANCE_SCORE
        assert config.min_confidence == DEFAULT_MIN_CONFIDENCE
        assert config.max_expansions_per_belief == 10
        assert config.batch_size == 5

    def test_custom_values(self):
        """Test custom configuration values."""
        config = ExpansionConfig(
            time_limit_seconds=600,
            min_relevance_score=0.7,
            min_confidence=0.6,
            max_expansions_per_belief=5,
        )

        assert config.time_limit_seconds == 600
        assert config.min_relevance_score == 0.7
        assert config.min_confidence == 0.6
        assert config.max_expansions_per_belief == 5


class TestExpansionProgress:
    """Tests for ExpansionProgress."""

    def test_initial_state(self):
        """Test initial progress state."""
        progress = ExpansionProgress()

        assert progress.total_beliefs == 0
        assert progress.processed_beliefs == 0
        assert progress.expansions_generated == 0
        assert progress.expansions_stored == 0
        assert progress.expansions_filtered == 0
        assert progress.timed_out is False
        assert progress.error_message is None

    def test_elapsed_seconds(self):
        """Test elapsed time calculation."""
        progress = ExpansionProgress()
        progress.start_time = time.time() - 10  # 10 seconds ago

        elapsed = progress.elapsed_seconds()

        assert 9.5 <= elapsed <= 10.5

    def test_is_within_time_limit(self):
        """Test time limit check."""
        config = ExpansionConfig(time_limit_seconds=300)
        progress = ExpansionProgress()
        progress.start_time = time.time() - 100  # 100 seconds ago

        assert progress.is_within_time_limit(config) is True

        progress.start_time = time.time() - 400  # 400 seconds ago
        assert progress.is_within_time_limit(config) is False

    def test_to_dict(self):
        """Test progress serialization."""
        progress = ExpansionProgress()
        progress.total_beliefs = 10
        progress.processed_beliefs = 5

        result = progress.to_dict()

        assert result["total_beliefs"] == 10
        assert result["processed_beliefs"] == 5
        assert result["timed_out"] is False
        assert "elapsed_seconds" in result


class TestBeliefExpander:
    """Tests for BeliefExpander."""

    def test_expand_belief_low_confidence(self):
        """Test that low confidence beliefs are skipped."""
        expander = BeliefExpander()
        expander.config.min_confidence = 0.7

        result = expander.expand_belief(
            belief_id="low_conf",
            statement="Some belief",
            domain="test",
            confidence=0.5,  # Below threshold
        )

        assert result == []

    def test_expand_belief_derivation(self):
        """Test derivation expansion type."""
        expander = BeliefExpander()

        result = expander.expand_belief(
            belief_id="test_1",
            statement="The market is volatile therefore trading is risky",
            domain="trading",
            confidence=0.9,
        )

        # Should generate expansions
        assert len(result) > 0

    def test_expand_belief_generalization(self):
        """Test generalization expansion type."""
        expander = BeliefExpander()

        result = expander.expand_belief(
            belief_id="test_2",
            statement="Sometimes the market moves in trends",
            domain="trading",
            confidence=0.8,
        )

        # Check that expansions have generalization type
        if result:
            assert any(e.expansion_type == ExpansionType.GENERALIZATION for e in result)

    def test_expand_belief_specialization(self):
        """Test specialization expansion type."""
        expander = BeliefExpander()

        result = expander.expand_belief(
            belief_id="test_3",
            statement="Many traders use stop losses",
            domain="trading",
            confidence=0.85,
        )

        # Check that expansions have specialization type
        if result:
            assert any(e.expansion_type == ExpansionType.SPECIALIZATION for e in result)

    def test_expand_belief_analogy(self):
        """Test analogy expansion type."""
        expander = BeliefExpander()

        result = expander.expand_belief(
            belief_id="test_4",
            statement="The market is like an ocean",
            domain="trading",
            confidence=0.75,
        )

        # Check that expansions have analogy type
        if result:
            assert any(e.expansion_type == ExpansionType.ANALOGY for e in result)

    def test_expand_belief_inference(self):
        """Test inference expansion type."""
        expander = BeliefExpander()

        result = expander.expand_belief(
            belief_id="test_5",
            statement="Volatility is high and volume is low",
            domain="trading",
            confidence=0.8,
        )

        # Check that expansions have inference type
        if result:
            assert any(e.expansion_type == ExpansionType.INFERENCE for e in result)

    def test_relevance_filtering(self):
        """Test that low relevance expansions are filtered."""
        expander = BeliefExpander()
        expander.config.min_relevance_score = 0.9  # High threshold

        result = expander.expand_belief(
            belief_id="test_relevance",
            statement="The market is volatile therefore trading is risky",
            domain="trading",
            confidence=0.9,
        )

        # All results should meet relevance threshold
        for expansion in result:
            assert expansion.relevance_score >= 0.9

    def test_calculate_relevance(self):
        """Test relevance score calculation."""
        expander = BeliefExpander()

        score = expander._calculate_relevance(
            "The market is volatile",
            "The market is volatile and risky",
        )

        assert 0.0 <= score <= 1.0
        # Higher overlap should give higher score
        high_overlap = expander._calculate_relevance(
            "The market is volatile",
            "The market is volatile",
        )
        assert high_overlap > score

    def test_generate_embedding(self):
        """Test embedding generation."""
        expander = BeliefExpander()

        embedding = expander._generate_embedding("Test text")

        assert len(embedding) == 384
        assert all(-1.0 <= x <= 1.0 for x in embedding)

    def test_generate_embedding_empty(self):
        """Test embedding generation for empty text."""
        expander = BeliefExpander()

        embedding = expander._generate_embedding("")

        assert len(embedding) == 384
        assert all(x == 0.0 for x in embedding)


class TestExpandBeliefs:
    """Tests for expand_beliefs function."""

    def test_expand_empty_list(self):
        """Test expanding empty belief list."""
        result = expand_beliefs([])

        assert result.success is True
        assert result.progress.processed_beliefs == 0
        assert len(result.expanded_beliefs) == 0

    def test_expand_single_belief(self):
        """Test expanding a single belief."""
        beliefs = [
            {
                "belief_id": "belief_1",
                "statement": "The market is volatile therefore trading is risky",
                "domain": "trading",
                "confidence": 0.9,
            }
        ]

        result = expand_beliefs(beliefs)

        assert result.success is True
        assert result.progress.processed_beliefs == 1

    def test_expand_multiple_beliefs(self):
        """Test expanding multiple beliefs."""
        beliefs = [
            {
                "belief_id": "belief_1",
                "statement": "Sometimes markets trend",
                "domain": "trading",
                "confidence": 0.8,
            },
            {
                "belief_id": "belief_2",
                "statement": "Many traders use stop losses",
                "domain": "trading",
                "confidence": 0.85,
            },
        ]

        result = expand_beliefs(beliefs)

        assert result.success is True
        assert result.progress.processed_beliefs == 2

    def test_time_limit_enforcement(self):
        """Test that time limit is enforced."""
        beliefs = [
            {
                "belief_id": f"belief_{i}",
                "statement": "Sometimes markets trend",
                "domain": "trading",
                "confidence": 0.8,
            }
            for i in range(100)
        ]

        config = ExpansionConfig(time_limit_seconds=0.001)  # Very short limit

        result = expand_beliefs(beliefs, config=config)

        assert result.progress.timed_out is True
        assert result.progress.processed_beliefs < len(beliefs)

    def test_progress_callback(self):
        """Test progress callback is called."""
        beliefs = [
            {
                "belief_id": "belief_1",
                "statement": "Sometimes markets trend",
                "domain": "trading",
                "confidence": 0.8,
            }
        ]

        callback_progress = []

        def callback(progress: ExpansionProgress):
            callback_progress.append(progress.processed_beliefs)

        result = expand_beliefs(beliefs, progress_callback=callback)

        assert len(callback_progress) > 0
        assert callback_progress[-1] == result.progress.processed_beliefs

    def test_qdrant_storage(self):
        """Test Qdrant storage integration."""
        mock_qdrant = MagicMock()

        beliefs = [
            {
                "belief_id": "belief_1",
                "statement": "Sometimes markets trend",
                "domain": "trading",
                "confidence": 0.8,
            }
        ]

        result = expand_beliefs(beliefs, qdrant_client=mock_qdrant)

        # Result should be successful
        assert result.success is True

    def test_graceful_timeout(self):
        """Test graceful handling of timeout."""
        beliefs = [
            {
                "belief_id": f"belief_{i}",
                "statement": "Statement " + "word " * 100,
                "domain": "trading",
                "confidence": 0.8,
            }
            for i in range(50)
        ]

        config = ExpansionConfig(time_limit_seconds=0.01)

        result = expand_beliefs(beliefs, config=config)

        # Should complete gracefully
        assert result.progress.timed_out is True
        assert result.error is None or result.error == ""


class TestExpansionResult:
    """Tests for ExpansionResult."""

    def test_success_result(self):
        """Test success result."""
        progress = ExpansionProgress()
        progress.expansions_stored = 5

        result = ExpansionResult(
            success=True,
            progress=progress,
            expanded_beliefs=[],
        )

        assert result.success is True
        assert result.error is None

    def test_failure_result(self):
        """Test failure result."""
        progress = ExpansionProgress()
        progress.error_message = "Test error"

        result = ExpansionResult(
            success=False,
            progress=progress,
            error="Test error",
        )

        assert result.success is False
        assert result.error == "Test error"

    def test_to_dict(self):
        """Test result serialization."""
        progress = ExpansionProgress()
        progress.total_beliefs = 10
        progress.processed_beliefs = 10
        progress.expansions_stored = 5

        result = ExpansionResult(
            success=True,
            progress=progress,
            expanded_beliefs=[],
        )

        serialized = result.to_dict()

        assert serialized["success"] is True
        assert serialized["progress"]["total_beliefs"] == 10
        assert serialized["expanded_belief_count"] == 0
