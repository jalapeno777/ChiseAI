"""Autonomous Git module for PR automation."""

# Path Analyzer (ST-AUTO-001)
try:
    from .path_analyzer import (
        PathAnalysisCache,
        PathAnalyzer,
        PathPatternMatcher,
        RiskClassification,
        RiskLevel,
        analyze_paths,
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

# Auto-Approval (ST-AUTO-002)
try:
    from .auto_approval import (
        AutoApprovalConfig,
        AutoApprover,
        DiscordNotifier,
        ExclusionManager,
        RateLimiter,
        SafetyChecker,
        SafetyCheckResult,
        load_config,
        process_safe_pr,
    )

    _AUTO_APPROVAL_AVAILABLE = True
except ImportError:
    _AUTO_APPROVAL_AVAILABLE = False
    AutoApprover = None
    process_safe_pr = None
    SafetyChecker = None
    SafetyCheckResult = None
    RateLimiter = None
    ExclusionManager = None
    DiscordNotifier = None
    load_config = None
    AutoApprovalConfig = None

# GitReviewBot (ST-AUTO-003)
from .gitreviewbot import (
    CalibrationTracker,
    ConfidenceScorer,
    CriticReviewer,
    Decision,
    DecisionSynthesizer,
    DecisionType,
    Finding,
    GiteaClient,
    GitReviewBot,
    ReviewFeedback,
    ReviewResult,
    SeniorDevReviewer,
    Violation,
    review_pr,
)

__version__ = "0.1.0"

__all__ = [
    # GitReviewBot (ST-AUTO-003)
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

# Add Auto-Approval exports if available
if _AUTO_APPROVAL_AVAILABLE:
    __all__.extend(
        [
            "AutoApprover",
            "process_safe_pr",
            "SafetyChecker",
            "SafetyCheckResult",
            "RateLimiter",
            "ExclusionManager",
            "DiscordNotifier",
            "load_config",
            "AutoApprovalConfig",
        ]
    )

# Add Path Analyzer exports if available
if _PATH_ANALYZER_AVAILABLE:
    __all__.extend(
        [
            "RiskLevel",
            "RiskClassification",
            "PathAnalyzer",
            "analyze_paths",
            "PathPatternMatcher",
            "PathAnalysisCache",
        ]
    )
