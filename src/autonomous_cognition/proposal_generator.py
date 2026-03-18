"""Proposal generator for autonomous cognition.

Creates story proposals from detected opportunities with scoring,
ranking, and human review integration.

Core Components:
1. StoryProposal dataclass - structured proposal representation
2. ProposalScorer - weighted scoring algorithm
3. ProposalGenerator - main orchestrator for proposal generation
4. Backlog integration - reference format for YAML output
5. Human review hooks - approval workflow integration
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any

from src.autonomous_cognition.opportunity_detection import (
    Opportunity,
    OpportunityCategory,
    OpportunitySeverity,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------


class ProposalPriority(Enum):
    """Priority level for story proposals."""

    P0 = auto()  # Critical - must be addressed immediately
    P1 = auto()  # High - important for current sprint
    P2 = auto()  # Medium - valuable but not urgent
    P3 = auto()  # Low - nice to have


class ProposalStatus(Enum):
    """Status of a story proposal in the review workflow."""

    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    DEFERRED = "deferred"


@dataclass
class StoryProposal:
    """A story proposal generated from a detected opportunity.

    Attributes:
        proposal_id: Unique identifier for this proposal
        title: Human-readable title for the story
        description: Detailed description of what the story addresses
        story_points: Estimated story points (1-5)
        priority: Priority level (P0-P3)
        acceptance_criteria: List of acceptance criteria for the story
        source_opportunity: The original opportunity this proposal derives from
        confidence_score: Confidence in proposal quality (0.0-1.0)
        generated_at: Timestamp when proposal was generated
        status: Current status in the review workflow
        reviewer_notes: Notes from human reviewer
        score_breakdown: Detailed scoring breakdown
    """

    proposal_id: str = field(default_factory=lambda: f"prop-{uuid.uuid4().hex[:12]}")
    title: str = ""
    description: str = ""
    story_points: int = 1
    priority: ProposalPriority = ProposalPriority.P2
    acceptance_criteria: list[str] = field(default_factory=list)
    source_opportunity: dict[str, Any] = field(default_factory=dict)
    confidence_score: float = 0.5
    generated_at: datetime = field(default_factory=datetime.utcnow)
    status: ProposalStatus = ProposalStatus.DRAFT
    reviewer_notes: str = ""
    score_breakdown: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize proposal to dictionary."""
        return {
            "proposal_id": self.proposal_id,
            "title": self.title,
            "description": self.description,
            "story_points": self.story_points,
            "priority": self.priority.name,
            "acceptance_criteria": self.acceptance_criteria,
            "source_opportunity": self.source_opportunity,
            "confidence_score": self.confidence_score,
            "generated_at": self.generated_at.isoformat(),
            "status": self.status.value,
            "reviewer_notes": self.reviewer_notes,
            "score_breakdown": self.score_breakdown,
        }

    def to_backlog_format(self) -> dict[str, Any]:
        """Convert to backlog YAML format (for human review)."""
        return {
            "story_id": self.proposal_id.upper().replace("-", "-"),
            "title": self.title,
            "priority": self.priority.name,
            "story_points": self.story_points,
            "status": "backlog",
            "description": self.description,
            "acceptance_criteria": {"must_conditions": self.acceptance_criteria},
            "source_opportunity": {
                "type": self.source_opportunity.get("type", "unknown"),
                "confidence": self.source_opportunity.get("confidence", 0.0),
            },
            "generated_date": self.generated_at.strftime("%Y-%m-%d"),
            "confidence_score": self.confidence_score,
        }


# ---------------------------------------------------------------------------
# Proposal scoring
# ---------------------------------------------------------------------------


@dataclass
class ScoringWeights:
    """Weights for the proposal scoring algorithm.

    Attributes:
        impact: Weight for business/technical impact (0-1)
        urgency: Weight for how urgent the issue is (0-1)
        feasibility: Weight for how easy to implement (0-1)
        alignment: Weight for strategic alignment (0-1)
    """

    impact: float = 0.35
    urgency: float = 0.30
    feasibility: float = 0.20
    alignment: float = 0.15


class ProposalScorer:
    """Scores proposals based on multiple factors.

    Uses weighted scoring algorithm considering:
    - Impact: How much value fixing this provides
    - Urgency: How time-sensitive the issue is
    - Feasibility: How easy it is to implement
    - Strategic alignment: How well it fits with goals
    """

    def __init__(self, weights: ScoringWeights | None = None) -> None:
        self.weights = weights or ScoringWeights()

    def score_proposal(
        self, opportunity: Opportunity, context: dict[str, Any] | None = None
    ) -> tuple[float, dict[str, float]]:
        """Score a proposal based on the source opportunity.

        Args:
            opportunity: The opportunity to score
            context: Optional context for scoring (e.g., strategic priorities)

        Returns:
            Tuple of (overall_score, score_breakdown)
        """
        context = context or {}

        # Calculate component scores
        impact_score = self._score_impact(opportunity)
        urgency_score = self._score_urgency(opportunity)
        feasibility_score = self._score_feasibility(opportunity, context)
        alignment_score = self._score_alignment(opportunity, context)

        # Apply weights
        overall = (
            impact_score * self.weights.impact
            + urgency_score * self.weights.urgency
            + feasibility_score * self.weights.feasibility
            + alignment_score * self.weights.alignment
        )

        breakdown = {
            "impact": impact_score,
            "urgency": urgency_score,
            "feasibility": feasibility_score,
            "alignment": alignment_score,
            "overall": overall,
        }

        return round(overall, 3), breakdown

    def _score_impact(self, opportunity: Opportunity) -> float:
        """Score the potential impact of addressing this opportunity.

        Higher severity and broader scope = higher impact.
        """
        # Severity mapping
        severity_scores = {
            OpportunitySeverity.CRITICAL: 1.0,
            OpportunitySeverity.HIGH: 0.75,
            OpportunitySeverity.MEDIUM: 0.5,
            OpportunitySeverity.LOW: 0.25,
        }
        severity_score = severity_scores.get(opportunity.severity, 0.5)

        # Category impact weights
        category_impact = {
            OpportunityCategory.SECURITY: 1.0,
            OpportunityCategory.RELIABILITY: 0.9,
            OpportunityCategory.PERFORMANCE: 0.8,
            OpportunityCategory.TESTING: 0.7,
            OpportunityCategory.CODE_QUALITY: 0.6,
            OpportunityCategory.INFRASTRUCTURE: 0.5,
            OpportunityCategory.OPERATIONS: 0.4,
            OpportunityCategory.DOCUMENTATION: 0.3,
        }
        category_score = category_impact.get(opportunity.category, 0.5)

        # Combine with confidence
        confidence_factor = opportunity.confidence

        return round(
            min(1.0, (severity_score * 0.6 + category_score * 0.4) * confidence_factor),
            3,
        )

    def _score_urgency(self, opportunity: Opportunity) -> float:
        """Score how urgent it is to address this opportunity.

        Based on severity and time-sensitive factors.
        """
        severity_scores = {
            OpportunitySeverity.CRITICAL: 1.0,
            OpportunitySeverity.HIGH: 0.75,
            OpportunitySeverity.MEDIUM: 0.4,
            OpportunitySeverity.LOW: 0.2,
        }
        severity_score = severity_scores.get(opportunity.severity, 0.5)

        # Check for time-sensitive metadata
        metadata = opportunity.metadata
        time_factors = []

        if metadata.get("error_rate", 0) > 0.1:
            time_factors.append(0.2)
        if metadata.get("usage_ratio", 0) > 0.9:
            time_factors.append(0.15)
        if metadata.get("regression_pct", 0) > 0.5:
            time_factors.append(0.2)

        time_bonus = min(0.3, sum(time_factors))

        return round(min(1.0, severity_score + time_bonus), 3)

    def _score_feasibility(
        self, opportunity: Opportunity, context: dict[str, Any]
    ) -> float:
        """Score how feasible it is to implement a solution.

        Based on scope, complexity hints, and available context.
        """
        # Base feasibility from opportunity characteristics
        file_path = opportunity.file_path
        has_file_context = bool(file_path)

        # Check for complexity hints in metadata
        metadata = opportunity.metadata
        complexity_indicators = 0

        if metadata.get("public_undocumented", 0) > 10:
            complexity_indicators += 0.1
        if metadata.get("reference_count", 1) < 1:
            complexity_indicators += 0.15
        if metadata.get("error_types") and len(metadata.get("error_types", [])) > 3:
            complexity_indicators += 0.15

        # Context hints
        context_hints = context.get("feasibility_hints", {})
        known_easy = context_hints.get("known_easy_types", [])
        known_hard = context_hints.get("known_hard_types", [])

        if opportunity.type in known_easy:
            complexity_indicators += 0.2
        elif opportunity.type in known_hard:
            complexity_indicators -= 0.2

        base_score = 0.7 if has_file_context else 0.5
        feasibility = base_score - complexity_indicators

        return round(max(0.1, min(1.0, feasibility)), 3)

    def _score_alignment(
        self, opportunity: Opportunity, context: dict[str, Any]
    ) -> float:
        """Score strategic alignment of addressing this opportunity.

        Based on current priorities and strategic goals.
        """
        # Get strategic priorities from context
        priorities = context.get("strategic_priorities", [])

        # Category alignment scores
        category_priorities = {
            OpportunityCategory.SECURITY: ["security", "reliability", "safety"],
            OpportunityCategory.RELIABILITY: ["reliability", "stability"],
            OpportunityCategory.PERFORMANCE: ["performance", "speed", "efficiency"],
            OpportunityCategory.TESTING: ["quality", "reliability", "confidence"],
            OpportunityCategory.CODE_QUALITY: ["maintainability", "quality"],
            OpportunityCategory.INFRASTRUCTURE: ["infrastructure", "reliability"],
            OpportunityCategory.OPERATIONS: ["efficiency", "automation"],
            OpportunityCategory.DOCUMENTATION: ["DX", "onboarding"],
        }

        category_keywords = category_priorities.get(opportunity.category, [])

        # Check alignment with stated priorities
        alignment_score = 0.5  # base
        for priority in priorities:
            priority_lower = priority.lower()
            if any(kw in priority_lower for kw in category_keywords):
                alignment_score += 0.15

        return round(min(1.0, alignment_score), 3)

    def rank_proposals(self, proposals: list[StoryProposal]) -> list[StoryProposal]:
        """Rank proposals by score (highest first)."""
        return sorted(proposals, key=lambda p: p.confidence_score, reverse=True)

    def filter_by_threshold(
        self, proposals: list[StoryProposal], min_score: float
    ) -> list[StoryProposal]:
        """Filter proposals by minimum score threshold."""
        return [p for p in proposals if p.confidence_score >= min_score]


# ---------------------------------------------------------------------------
# Proposal generation
# ---------------------------------------------------------------------------


class ProposalGenerator:
    """Generates story proposals from detected opportunities.

    Orchestrates the full pipeline:
    1. Convert opportunities to proposals
    2. Score and rank proposals
    3. Filter by quality thresholds
    4. Prepare for human review
    """

    # Mapping from opportunity severity to proposal priority
    SEVERITY_TO_PRIORITY = {
        OpportunitySeverity.CRITICAL: ProposalPriority.P0,
        OpportunitySeverity.HIGH: ProposalPriority.P1,
        OpportunitySeverity.MEDIUM: ProposalPriority.P2,
        OpportunitySeverity.LOW: ProposalPriority.P3,
    }

    # Story point estimates based on opportunity type
    TYPE_STORY_POINTS = {
        "low_test_coverage": 3,
        "slow_api_endpoint": 2,
        "high_error_rate": 3,
        "unused_code": 1,
        "configuration_drift": 2,
        "memory_anomaly": 3,
        "ci_bottleneck": 2,
        "documentation_gap": 1,
        "dependency_vulnerability": 2,
        "performance_regression": 3,
    }

    def __init__(
        self,
        scorer: ProposalScorer | None = None,
        min_score_threshold: float = 0.3,
    ) -> None:
        self.scorer = scorer or ProposalScorer()
        self.min_score_threshold = min_score_threshold

    def generate_from_opportunity(
        self, opportunity: Opportunity, context: dict[str, Any] | None = None
    ) -> StoryProposal:
        """Generate a story proposal from a single opportunity.

        Args:
            opportunity: The opportunity to convert
            context: Optional context for scoring

        Returns:
            A StoryProposal derived from the opportunity
        """
        context = context or {}

        # Generate proposal fields
        title = self._generate_title(opportunity)
        description = self._generate_description(opportunity)
        story_points = self._estimate_story_points(opportunity)
        priority = self.SEVERITY_TO_PRIORITY.get(
            opportunity.severity, ProposalPriority.P2
        )
        acceptance_criteria = self._generate_acceptance_criteria(opportunity)

        # Score the proposal
        score, breakdown = self.scorer.score_proposal(opportunity, context)

        # Create proposal
        proposal = StoryProposal(
            title=title,
            description=description,
            story_points=story_points,
            priority=priority,
            acceptance_criteria=acceptance_criteria,
            source_opportunity=opportunity.to_dict(),
            confidence_score=score,
            score_breakdown=breakdown,
        )

        logger.info(
            "Generated proposal %s from opportunity %s with score %.3f",
            proposal.proposal_id,
            opportunity.id,
            score,
        )

        return proposal

    def generate_batch(
        self,
        opportunities: list[Opportunity],
        context: dict[str, Any] | None = None,
    ) -> list[StoryProposal]:
        """Generate proposals from multiple opportunities.

        Args:
            opportunities: List of opportunities to convert
            context: Optional context for scoring

        Returns:
            List of StoryProposals
        """
        proposals = []
        for opp in opportunities:
            try:
                proposal = self.generate_from_opportunity(opp, context)
                proposals.append(proposal)
            except Exception as e:
                logger.error(
                    "Failed to generate proposal for opportunity %s: %s",
                    opp.id,
                    e,
                )

        logger.info(
            "Generated %d proposals from %d opportunities",
            len(proposals),
            len(opportunities),
        )

        return proposals

    def rank_proposals(self, proposals: list[StoryProposal]) -> list[StoryProposal]:
        """Rank proposals by score (highest first)."""
        return self.scorer.rank_proposals(proposals)

    def filter_by_threshold(
        self, proposals: list[StoryProposal], min_score: float | None = None
    ) -> list[StoryProposal]:
        """Filter proposals by minimum score threshold."""
        threshold = min_score if min_score is not None else self.min_score_threshold
        return self.scorer.filter_by_threshold(proposals, threshold)

    def generate_review_package(self, proposals: list[StoryProposal]) -> dict[str, Any]:
        """Generate a review package for human approval.

        Args:
            proposals: List of proposals to package

        Returns:
            Dictionary suitable for human review
        """
        ranked = self.rank_proposals(proposals)
        filtered = self.filter_by_threshold(ranked)

        return {
            "generated_at": datetime.utcnow().isoformat(),
            "total_proposals": len(proposals),
            "proposals_for_review": len(filtered),
            "proposals": [p.to_backlog_format() for p in filtered],
            "summary": {
                "by_priority": self._summarize_by_priority(filtered),
                "by_category": self._summarize_by_category(filtered),
                "avg_confidence": (
                    sum(p.confidence_score for p in filtered) / len(filtered)
                    if filtered
                    else 0
                ),
            },
        }

    def _generate_title(self, opportunity: Opportunity) -> str:
        """Generate a human-readable title from an opportunity."""
        # Clean up the opportunity title
        base_title = opportunity.title

        # Add category prefix for clarity
        category_prefix = {
            OpportunityCategory.SECURITY: "[SECURITY]",
            OpportunityCategory.RELIABILITY: "[RELIABILITY]",
            OpportunityCategory.PERFORMANCE: "[PERF]",
            OpportunityCategory.TESTING: "[TEST]",
            OpportunityCategory.CODE_QUALITY: "[QUALITY]",
            OpportunityCategory.INFRASTRUCTURE: "[INFRA]",
            OpportunityCategory.OPERATIONS: "[OPS]",
            OpportunityCategory.DOCUMENTATION: "[DOCS]",
        }

        prefix = category_prefix.get(opportunity.category, "")
        if prefix:
            return f"{prefix} {base_title}"

        return base_title

    def _generate_description(self, opportunity: Opportunity) -> str:
        """Generate a detailed description from an opportunity."""
        lines = [
            opportunity.description,
            "",
            "## Source",
            f"- Type: {opportunity.type}",
            f"- Category: {opportunity.category.value}",
            f"- Severity: {opportunity.severity.name}",
            f"- Confidence: {opportunity.confidence:.0%}",
            "",
            "## Suggested Action",
            opportunity.suggestion,
        ]

        if opportunity.file_path:
            lines.insert(3, f"- File: `{opportunity.file_path}`")

        return "\n".join(lines)

    def _estimate_story_points(self, opportunity: Opportunity) -> int:
        """Estimate story points based on opportunity type and severity."""
        base_points = self.TYPE_STORY_POINTS.get(opportunity.type, 2)

        # Adjust based on severity
        severity_multiplier = {
            OpportunitySeverity.CRITICAL: 1.2,
            OpportunitySeverity.HIGH: 1.0,
            OpportunitySeverity.MEDIUM: 0.9,
            OpportunitySeverity.LOW: 0.7,
        }

        multiplier = severity_multiplier.get(opportunity.severity, 1.0)
        estimated = int(base_points * multiplier)

        # Clamp to 1-5 range
        return max(1, min(5, estimated))

    def _generate_acceptance_criteria(self, opportunity: Opportunity) -> list[str]:
        """Generate acceptance criteria from opportunity details."""
        criteria = []

        # Base criteria based on opportunity type
        type_criteria = {
            "low_test_coverage": [
                "Increase test coverage above threshold",
                "All new tests pass",
                "Code review approves test quality",
            ],
            "slow_api_endpoint": [
                "P95 latency below threshold",
                "No regression in other endpoints",
                "Performance tests pass",
            ],
            "high_error_rate": [
                "Error rate below threshold",
                "Error types resolved",
                "Monitoring confirms improvement",
            ],
            "unused_code": [
                "Code removed or verified as used",
                "No breaking changes",
                "Build passes",
            ],
            "configuration_drift": [
                "Configuration aligned across environments",
                "Deployment succeeds in all envs",
                "Documentation updated",
            ],
            "memory_anomaly": [
                "Memory usage within limits",
                "No memory leaks detected",
                "Load tests pass",
            ],
            "ci_bottleneck": [
                "CI stage duration reduced",
                "Failure rate below threshold",
                "All tests still run",
            ],
            "documentation_gap": [
                "Docstring coverage above threshold",
                "Documentation builds without warnings",
                "Code review approves docs",
            ],
            "dependency_vulnerability": [
                "Vulnerability patched",
                "No breaking changes",
                "Security scan passes",
            ],
            "performance_regression": [
                "Performance restored to baseline",
                "Regression tests pass",
                "Monitoring confirms improvement",
            ],
        }

        criteria.extend(type_criteria.get(opportunity.type, []))

        # Add metadata-specific criteria
        metadata = opportunity.metadata
        if metadata.get("coverage_percent"):
            criteria.append(
                f"Coverage increased from {metadata['coverage_percent']:.0f}%"
            )
        if metadata.get("p95_latency_ms"):
            criteria.append(
                f"Latency reduced below {metadata.get('threshold_ms', 1000)}ms"
            )
        if metadata.get("error_rate"):
            criteria.append(
                f"Error rate reduced below {metadata.get('threshold', 0.05):.1%}"
            )

        return criteria[:5]  # Limit to 5 criteria

    def _summarize_by_priority(self, proposals: list[StoryProposal]) -> dict[str, int]:
        """Summarize proposals by priority."""
        summary: dict[str, int] = {}
        for p in proposals:
            priority = p.priority.name
            summary[priority] = summary.get(priority, 0) + 1
        return summary

    def _summarize_by_category(self, proposals: list[StoryProposal]) -> dict[str, int]:
        """Summarize proposals by source category."""
        summary: dict[str, int] = {}
        for p in proposals:
            cat = p.source_opportunity.get("category", "unknown")
            summary[cat] = summary.get(cat, 0) + 1
        return summary


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------


async def generate_proposals_from_detector(
    detector, context: dict[str, Any] | None = None
) -> list[StoryProposal]:
    """Convenience function to generate proposals from an OpportunityDetector.

    Args:
        detector: An OpportunityDetector instance
        context: Optional context for detection and scoring

    Returns:
        List of generated proposals
    """
    # Detect opportunities
    result = await detector.detect_all(context)

    # Generate proposals
    generator = ProposalGenerator()
    proposals = generator.generate_batch(result.opportunities, context)

    return proposals
