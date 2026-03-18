"""Tests for proposal_generator module.

Tests the StoryProposal dataclass, ProposalScorer, and ProposalGenerator.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from src.autonomous_cognition.opportunity_detection import (
    Opportunity,
    OpportunityCategory,
    OpportunitySeverity,
)
from src.autonomous_cognition.proposal_generator import (
    ProposalGenerator,
    ProposalPriority,
    ProposalScorer,
    ProposalStatus,
    ScoringWeights,
    StoryProposal,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_opportunity() -> Opportunity:
    """Create a sample opportunity for testing."""
    return Opportunity(
        id="test-opp-001",
        type="low_test_coverage",
        title="Low test coverage: src/api/main.py",
        description="File src/api/main.py has 45% coverage, below 80% threshold.",
        severity=OpportunitySeverity.HIGH,
        category=OpportunityCategory.TESTING,
        confidence=0.85,
        score=0.7,
        source="coverage_report",
        metadata={"coverage_percent": 45.0, "threshold": 80.0},
        file_path="src/api/main.py",
        suggestion="Add tests to increase coverage above 80%.",
    )


@pytest.fixture
def critical_opportunity() -> Opportunity:
    """Create a critical severity opportunity."""
    return Opportunity(
        id="test-opp-002",
        type="dependency_vulnerability",
        title="Vulnerability: requests (CVE-2023-12345)",
        description="Package requests v2.28.0 has critical vulnerability.",
        severity=OpportunitySeverity.CRITICAL,
        category=OpportunityCategory.SECURITY,
        confidence=0.95,
        score=0.95,
        source="dependency_audit",
        metadata={
            "package": "requests",
            "version": "2.28.0",
            "cve_id": "CVE-2023-12345",
            "vulnerability_severity": "CRITICAL",
        },
        suggestion="Update requests to patched version.",
    )


@pytest.fixture
def low_priority_opportunity() -> Opportunity:
    """Create a low priority opportunity."""
    return Opportunity(
        id="test-opp-003",
        type="documentation_gap",
        title="Documentation gap: src/utils/helper.py",
        description="File has 30% docstring coverage.",
        severity=OpportunitySeverity.LOW,
        category=OpportunityCategory.DOCUMENTATION,
        confidence=0.7,
        score=0.3,
        source="doc_analysis",
        metadata={"docstring_ratio": 0.3, "public_undocumented": 5, "total_public": 10},
        file_path="src/utils/helper.py",
        suggestion="Add docstrings to undocumented symbols.",
    )


@pytest.fixture
def scorer() -> ProposalScorer:
    """Create a scorer with default weights."""
    return ProposalScorer()


@pytest.fixture
def generator() -> ProposalGenerator:
    """Create a proposal generator."""
    return ProposalGenerator()


@pytest.fixture
def scoring_context() -> dict:
    """Create a scoring context with strategic priorities."""
    return {
        "strategic_priorities": ["security", "reliability", "performance"],
        "feasibility_hints": {
            "known_easy_types": ["documentation_gap", "unused_code"],
            "known_hard_types": ["performance_regression", "memory_anomaly"],
        },
    }


# ---------------------------------------------------------------------------
# StoryProposal tests
# ---------------------------------------------------------------------------


class TestStoryProposal:
    """Tests for the StoryProposal dataclass."""

    def test_default_creation(self):
        """Test creating a proposal with defaults."""
        proposal = StoryProposal()

        assert proposal.proposal_id.startswith("prop-")
        assert proposal.story_points == 1
        assert proposal.priority == ProposalPriority.P2
        assert proposal.status == ProposalStatus.DRAFT
        assert proposal.confidence_score == 0.5
        assert isinstance(proposal.generated_at, datetime)

    def test_custom_creation(self):
        """Test creating a proposal with custom values."""
        proposal = StoryProposal(
            title="Test Proposal",
            description="Test description",
            story_points=3,
            priority=ProposalPriority.P1,
            acceptance_criteria=["Criterion 1", "Criterion 2"],
        )

        assert proposal.title == "Test Proposal"
        assert proposal.description == "Test description"
        assert proposal.story_points == 3
        assert proposal.priority == ProposalPriority.P1
        assert proposal.acceptance_criteria == ["Criterion 1", "Criterion 2"]

    def test_to_dict(self):
        """Test serialization to dictionary."""
        proposal = StoryProposal(
            title="Test",
            description="Desc",
            priority=ProposalPriority.P0,
        )

        result = proposal.to_dict()

        assert result["title"] == "Test"
        assert result["description"] == "Desc"
        assert result["priority"] == "P0"
        assert "proposal_id" in result
        assert "generated_at" in result

    def test_to_backlog_format(self):
        """Test conversion to backlog format."""
        proposal = StoryProposal(
            title="Test Proposal",
            story_points=2,
            priority=ProposalPriority.P1,
            source_opportunity={"type": "test_type", "confidence": 0.8},
        )

        result = proposal.to_backlog_format()

        assert result["title"] == "Test Proposal"
        assert result["story_points"] == 2
        assert result["priority"] == "P1"
        assert result["status"] == "backlog"
        assert "acceptance_criteria" in result


# ---------------------------------------------------------------------------
# ProposalScorer tests
# ---------------------------------------------------------------------------


class TestProposalScorer:
    """Tests for the ProposalScorer class."""

    def test_default_weights(self, scorer):
        """Test default scoring weights."""
        assert scorer.weights.impact == 0.35
        assert scorer.weights.urgency == 0.30
        assert scorer.weights.feasibility == 0.20
        assert scorer.weights.alignment == 0.15

    def test_custom_weights(self):
        """Test custom scoring weights."""
        weights = ScoringWeights(
            impact=0.4, urgency=0.3, feasibility=0.2, alignment=0.1
        )
        scorer = ProposalScorer(weights)

        assert scorer.weights.impact == 0.4
        assert scorer.weights.alignment == 0.1

    def test_score_proposal_returns_tuple(self, scorer, sample_opportunity):
        """Test that score_proposal returns a tuple."""
        score, breakdown = scorer.score_proposal(sample_opportunity)

        assert isinstance(score, float)
        assert isinstance(breakdown, dict)
        assert 0.0 <= score <= 1.0
        assert "impact" in breakdown
        assert "urgency" in breakdown
        assert "feasibility" in breakdown
        assert "alignment" in breakdown
        assert "overall" in breakdown

    def test_critical_severity_high_impact(self, scorer, critical_opportunity):
        """Test that critical severity gets high impact score."""
        score, breakdown = scorer.score_proposal(critical_opportunity)

        assert breakdown["impact"] >= 0.7  # High for CRITICAL
        assert score >= 0.6  # Overall should be high

    def test_low_severity_low_impact(self, scorer, low_priority_opportunity):
        """Test that low severity gets lower impact score."""
        score, breakdown = scorer.score_proposal(low_priority_opportunity)

        assert breakdown["impact"] <= 0.4  # Lower for LOW

    def test_security_category_high_impact(self, scorer):
        """Test that security category has high impact."""
        opp = Opportunity(
            type="test",
            title="Test",
            severity=OpportunitySeverity.HIGH,
            category=OpportunityCategory.SECURITY,
            confidence=0.9,
        )

        score, breakdown = scorer.score_proposal(opp)

        assert breakdown["impact"] >= 0.6

    def test_strategic_alignment(self, scorer, sample_opportunity, scoring_context):
        """Test strategic alignment scoring."""
        score_with_context, _ = scorer.score_proposal(
            sample_opportunity, scoring_context
        )
        score_without_context, _ = scorer.score_proposal(sample_opportunity)

        # With strategic priorities matching, should be higher or equal
        assert score_with_context >= score_without_context

    def test_ranking_proposals(self, scorer, sample_opportunity, critical_opportunity):
        """Test ranking proposals by score."""
        score1, _ = scorer.score_proposal(sample_opportunity)
        score2, _ = scorer.score_proposal(critical_opportunity)

        proposal1 = StoryProposal(
            title="A",
            confidence_score=score1,
            source_opportunity=sample_opportunity.to_dict(),
        )
        proposal2 = StoryProposal(
            title="B",
            confidence_score=score2,
            source_opportunity=critical_opportunity.to_dict(),
        )

        ranked = scorer.rank_proposals([proposal1, proposal2])

        assert ranked[0].confidence_score >= ranked[1].confidence_score

    def test_filter_by_threshold(self, scorer):
        """Test filtering proposals by score threshold."""
        proposals = [
            StoryProposal(title="A", confidence_score=0.8),
            StoryProposal(title="B", confidence_score=0.5),
            StoryProposal(title="C", confidence_score=0.3),
        ]

        filtered = scorer.filter_by_threshold(proposals, 0.4)

        assert len(filtered) == 2
        assert all(p.confidence_score >= 0.4 for p in filtered)


# ---------------------------------------------------------------------------
# ProposalGenerator tests
# ---------------------------------------------------------------------------


class TestProposalGenerator:
    """Tests for the ProposalGenerator class."""

    def test_generate_from_opportunity(self, generator, sample_opportunity):
        """Test generating a proposal from an opportunity."""
        proposal = generator.generate_from_opportunity(sample_opportunity)

        assert proposal.title
        assert proposal.description
        assert proposal.story_points in range(1, 6)
        assert proposal.priority in ProposalPriority
        assert proposal.acceptance_criteria
        assert proposal.source_opportunity
        assert proposal.confidence_score > 0

    def test_generate_preserves_opportunity_data(self, generator, sample_opportunity):
        """Test that generated proposal preserves source opportunity data."""
        proposal = generator.generate_from_opportunity(sample_opportunity)

        assert proposal.source_opportunity["type"] == sample_opportunity.type
        assert proposal.source_opportunity["severity"] == "HIGH"
        assert proposal.source_opportunity["category"] == "testing"

    def test_priority_mapping_from_severity(self, generator):
        """Test that priority is correctly mapped from severity."""
        # CRITICAL -> P0
        opp_critical = Opportunity(
            type="test",
            title="Test",
            severity=OpportunitySeverity.CRITICAL,
            confidence=0.9,
        )
        prop_critical = generator.generate_from_opportunity(opp_critical)
        assert prop_critical.priority == ProposalPriority.P0

        # HIGH -> P1
        opp_high = Opportunity(
            type="test", title="Test", severity=OpportunitySeverity.HIGH, confidence=0.9
        )
        prop_high = generator.generate_from_opportunity(opp_high)
        assert prop_high.priority == ProposalPriority.P1

        # MEDIUM -> P2
        opp_medium = Opportunity(
            type="test",
            title="Test",
            severity=OpportunitySeverity.MEDIUM,
            confidence=0.9,
        )
        prop_medium = generator.generate_from_opportunity(opp_medium)
        assert prop_medium.priority == ProposalPriority.P2

        # LOW -> P3
        opp_low = Opportunity(
            type="test", title="Test", severity=OpportunitySeverity.LOW, confidence=0.9
        )
        prop_low = generator.generate_from_opportunity(opp_low)
        assert prop_low.priority == ProposalPriority.P3

    def test_story_points_estimation(self, generator, sample_opportunity):
        """Test story points estimation based on opportunity type."""
        proposal = generator.generate_from_opportunity(sample_opportunity)

        # low_test_coverage has base 3 points, HIGH severity multiplies by 1.0
        assert proposal.story_points >= 2
        assert proposal.story_points <= 5

    def test_generate_batch(self, generator, sample_opportunity, critical_opportunity):
        """Test generating proposals from multiple opportunities."""
        opportunities = [sample_opportunity, critical_opportunity]

        proposals = generator.generate_batch(opportunities)

        assert len(proposals) == 2
        assert all(isinstance(p, StoryProposal) for p in proposals)

    def test_generate_batch_handles_errors(self, generator):
        """Test that batch generation handles invalid opportunities gracefully."""
        # Create an opportunity with missing required fields
        invalid_opp = Opportunity(type="", title="")  # type and title empty but valid
        opportunities = [invalid_opp]

        # Should not raise, just skip invalid
        proposals = generator.generate_batch(opportunities)

        assert isinstance(proposals, list)

    def test_rank_proposals(
        self, generator, sample_opportunity, low_priority_opportunity
    ):
        """Test ranking proposals by score."""
        proposals = [
            generator.generate_from_opportunity(low_priority_opportunity),
            generator.generate_from_opportunity(sample_opportunity),
        ]

        ranked = generator.rank_proposals(proposals)

        assert ranked[0].confidence_score >= ranked[1].confidence_score

    def test_filter_by_threshold(
        self, generator, sample_opportunity, low_priority_opportunity
    ):
        """Test filtering by minimum score threshold."""
        proposals = [
            generator.generate_from_opportunity(sample_opportunity),
            generator.generate_from_opportunity(low_priority_opportunity),
        ]

        # Filter with high threshold
        filtered = generator.filter_by_threshold(proposals, min_score=0.5)

        assert all(p.confidence_score >= 0.5 for p in filtered)

    def test_generate_review_package(
        self, generator, sample_opportunity, critical_opportunity
    ):
        """Test generating a review package."""
        proposals = [
            generator.generate_from_opportunity(sample_opportunity),
            generator.generate_from_opportunity(critical_opportunity),
        ]

        package = generator.generate_review_package(proposals)

        assert "generated_at" in package
        assert "total_proposals" in package
        assert "proposals_for_review" in package
        assert "proposals" in package
        assert "summary" in package
        assert package["total_proposals"] == 2

    def test_review_package_contains_backlog_format(
        self, generator, sample_opportunity
    ):
        """Test that review package contains properly formatted proposals."""
        proposals = [generator.generate_from_opportunity(sample_opportunity)]

        package = generator.generate_review_package(proposals)

        assert len(package["proposals"]) == 1
        prop = package["proposals"][0]
        assert "story_id" in prop
        assert "title" in prop
        assert "priority" in prop
        assert "story_points" in prop

    def test_title_generation_with_prefix(self, generator):
        """Test that titles get category prefixes."""
        opp = Opportunity(
            type="test",
            title="Slow endpoint: /api/users",
            severity=OpportunitySeverity.HIGH,
            category=OpportunityCategory.PERFORMANCE,
            confidence=0.9,
        )

        proposal = generator.generate_from_opportunity(opp)

        assert "[PERF]" in proposal.title

    def test_acceptance_criteria_generation(self, generator, sample_opportunity):
        """Test that acceptance criteria are generated."""
        proposal = generator.generate_from_opportunity(sample_opportunity)

        assert len(proposal.acceptance_criteria) > 0
        assert len(proposal.acceptance_criteria) <= 5  # Limited to 5

    def test_acceptance_criteria_type_specific(self, generator):
        """Test that acceptance criteria vary by opportunity type."""
        # Test low_test_coverage
        opp = Opportunity(
            type="low_test_coverage",
            title="Test",
            severity=OpportunitySeverity.MEDIUM,
            category=OpportunityCategory.TESTING,
            confidence=0.9,
            metadata={"coverage_percent": 45.0},
        )
        prop = generator.generate_from_opportunity(opp)

        assert any("coverage" in c.lower() for c in prop.acceptance_criteria)

    def test_min_score_threshold_default(self, generator):
        """Test default minimum score threshold."""
        assert generator.min_score_threshold == 0.3

    def test_custom_min_score_threshold(self):
        """Test custom minimum score threshold."""
        generator = ProposalGenerator(min_score_threshold=0.5)
        assert generator.min_score_threshold == 0.5


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


class TestProposalGeneratorIntegration:
    """Integration tests for proposal generation."""

    def test_full_pipeline(self, generator, sample_opportunity, scoring_context):
        """Test the full proposal generation pipeline."""
        # Generate
        proposal = generator.generate_from_opportunity(
            sample_opportunity, scoring_context
        )

        # Verify
        assert proposal.proposal_id
        assert proposal.title
        assert proposal.description
        assert proposal.story_points in range(1, 6)
        assert proposal.priority in ProposalPriority
        assert proposal.confidence_score > 0

        # Serialize
        data = proposal.to_dict()
        assert data["proposal_id"] == proposal.proposal_id

        # Convert to backlog format
        backlog = proposal.to_backlog_format()
        assert backlog["title"] == proposal.title

    def test_multiple_opportunities_pipeline(self, generator, scoring_context):
        """Test pipeline with multiple opportunities."""
        opportunities = [
            Opportunity(
                type="low_test_coverage",
                title="Low coverage: file1.py",
                severity=OpportunitySeverity.HIGH,
                category=OpportunityCategory.TESTING,
                confidence=0.85,
                metadata={"coverage_percent": 45.0},
            ),
            Opportunity(
                type="dependency_vulnerability",
                title="Vuln: pkg",
                severity=OpportunitySeverity.CRITICAL,
                category=OpportunityCategory.SECURITY,
                confidence=0.95,
                metadata={"vulnerability_severity": "CRITICAL"},
            ),
            Opportunity(
                type="documentation_gap",
                title="Docs missing",
                severity=OpportunitySeverity.LOW,
                category=OpportunityCategory.DOCUMENTATION,
                confidence=0.7,
                metadata={"docstring_ratio": 0.3},
            ),
        ]

        # Generate batch
        proposals = generator.generate_batch(opportunities, scoring_context)

        # Rank
        ranked = generator.rank_proposals(proposals)

        # Filter
        filtered = generator.filter_by_threshold(ranked, min_score=0.3)

        # Generate review package
        package = generator.generate_review_package(filtered)

        assert package["total_proposals"] >= 2  # At least 2 should pass threshold
        assert package["summary"]["avg_confidence"] > 0

    def test_proposal_id_uniqueness(self, generator):
        """Test that proposal IDs are unique."""
        opportunities = [
            Opportunity(
                type="test",
                title=f"Test {i}",
                severity=OpportunitySeverity.MEDIUM,
                category=OpportunityCategory.CODE_QUALITY,
                confidence=0.9,
            )
            for i in range(10)
        ]

        proposals = generator.generate_batch(opportunities)
        ids = [p.proposal_id for p in proposals]

        assert len(ids) == len(set(ids))  # All unique


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestProposalGeneratorEdgeCases:
    """Edge case tests for proposal generator."""

    def test_opportunity_with_minimal_data(self, generator):
        """Test generating proposal with minimal opportunity data."""
        opp = Opportunity(
            type="test",
            title="Test",
            severity=OpportunitySeverity.MEDIUM,
            category=OpportunityCategory.CODE_QUALITY,
            confidence=0.5,
        )

        proposal = generator.generate_from_opportunity(opp)

        assert proposal.title
        assert proposal.description

    def test_opportunity_with_empty_metadata(self, generator):
        """Test with opportunity that has empty metadata."""
        opp = Opportunity(
            type="test",
            title="Test",
            severity=OpportunitySeverity.MEDIUM,
            category=OpportunityCategory.CODE_QUALITY,
            confidence=0.9,
            metadata={},
        )

        proposal = generator.generate_from_opportunity(opp)

        assert proposal.story_points in range(1, 6)

    def test_all_severity_levels(self, generator):
        """Test that all severity levels produce valid proposals."""
        severities = [
            OpportunitySeverity.LOW,
            OpportunitySeverity.MEDIUM,
            OpportunitySeverity.HIGH,
            OpportunitySeverity.CRITICAL,
        ]

        for severity in severities:
            opp = Opportunity(
                type="test",
                title="Test",
                severity=severity,
                category=OpportunityCategory.CODE_QUALITY,
                confidence=0.9,
            )
            proposal = generator.generate_from_opportunity(opp)

            assert proposal.priority in ProposalPriority
            assert proposal.story_points in range(1, 6)

    def test_all_categories(self, generator):
        """Test that all categories produce valid proposals."""
        categories = list(OpportunityCategory)

        for category in categories:
            opp = Opportunity(
                type="test",
                title="Test",
                severity=OpportunitySeverity.MEDIUM,
                category=category,
                confidence=0.9,
            )
            proposal = generator.generate_from_opportunity(opp)

            assert proposal.source_opportunity["category"] == category.value

    def test_empty_opportunities_list(self, generator):
        """Test batch generation with empty list."""
        proposals = generator.generate_batch([])

        assert proposals == []

    def test_empty_context(self, generator, sample_opportunity):
        """Test generation with empty context."""
        proposal = generator.generate_from_opportunity(sample_opportunity, {})

        assert proposal.confidence_score > 0

    def test_proposal_with_all_types(self, generator):
        """Test that all registered opportunity types work."""
        types = [
            "low_test_coverage",
            "slow_api_endpoint",
            "high_error_rate",
            "unused_code",
            "configuration_drift",
            "memory_anomaly",
            "ci_bottleneck",
            "documentation_gap",
            "dependency_vulnerability",
            "performance_regression",
        ]

        for opp_type in types:
            opp = Opportunity(
                type=opp_type,
                title=f"Test {opp_type}",
                severity=OpportunitySeverity.MEDIUM,
                category=OpportunityCategory.CODE_QUALITY,
                confidence=0.9,
            )
            proposal = generator.generate_from_opportunity(opp)

            assert proposal.story_points in range(1, 6)
