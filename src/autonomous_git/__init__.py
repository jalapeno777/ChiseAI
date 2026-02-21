"""Autonomous Git module for PR automation."""

# Path Analyzer (ST-AUTO-001)
try:
    from .path_analyzer import (
        RiskLevel,
        RiskClassification,
        PathAnalyzer,
        analyze_paths,
        PathPatternMatcher,
        PathAnalysisCache,
    )

    _path_analyzer_available = True
except ImportError:
    _path_analyzer_available = False
    RiskLevel = None
    RiskClassification = None
    PathAnalyzer = None
    analyze_paths = None
    PathPatternMatcher = None
    PathAnalysisCache = None

# Auto-Approval (ST-AUTO-002)
from .auto_approval import (
    AutoApprover,
    process_safe_pr,
    SafetyChecker,
    SafetyCheckResult,
    RateLimiter,
    ExclusionManager,
    DiscordNotifier,
    load_config,
    AutoApprovalConfig,
)

__version__ = "0.1.0"

__all__ = [
    # Auto-Approval (always available)
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

# Add Path Analyzer exports if available
if _path_analyzer_available:
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
