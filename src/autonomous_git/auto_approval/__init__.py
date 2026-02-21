"""Auto-approval module for safe PRs."""

from .approver import AutoApprover, process_safe_pr
from .safety_checks import SafetyChecker, SafetyCheckResult
from .rate_limiter import RateLimiter
from .exclusions import ExclusionManager
from .notifier import DiscordNotifier
from .config import load_config, AutoApprovalConfig

__version__ = "0.1.0"
__all__ = [
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
