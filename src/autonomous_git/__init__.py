"""Autonomous Git Pipeline modules."""

# Path Analyzer exports (ST-AUTO-001) - may not exist in worktree
try:
    from .path_analyzer import (
        RiskLevel,
        RiskClassification,
        PathAnalyzer,
        analyze_paths,
        PathPatternMatcher,
        PathAnalysisCache,
    )

    _PATH_ANALYZER_AVAILABLE = True
except ImportError:
    _PATH_ANALYZER_AVAILABLE = False
    RiskLevel = None
    RiskClassification = None
    PathAnalyzer = None
    analyze_paths = None
    PathPatternMatcher = None
    PathAnalysisCache = None

# GitReviewBot exports (ST-AUTO-003)
from .gitreviewbot import (
    GitReviewBot,
    review_pr,
    ReviewResult,
    Decision,
    DecisionType,
    Finding,
    Violation,
    ReviewFeedback,
    SeniorDevReviewer,
    CriticReviewer,
    DecisionSynthesizer,
    ConfidenceScorer,
    CalibrationTracker,
    GiteaClient,
)

__version__ = "0.1.0"

__all__ = [
    # Path Analyzer (optional)
    "RiskLevel",
    "RiskClassification",
    "PathAnalyzer",
    "analyze_paths",
    "PathPatternMatcher",
    "PathAnalysisCache",
    # GitReviewBot
    "GitReviewBot",
    "review_pr",
    "ReviewResult",
    "Decision",
    "DecisionType",
    "Finding",
    "Violation",
    "ReviewFeedback",
    "SeniorDevReviewer",
    "CriticReviewer",
    "DecisionSynthesizer",
    "ConfidenceScorer",
    "CalibrationTracker",
    "GiteaClient",
]
