"""PR Lifecycle Management module for autonomous AI swarm.

This module provides comprehensive PR lifecycle management including:
- State tracking and transitions
- Continuous monitoring
- Automatic failure recovery
- Health monitoring and stuck PR detection
- Escalation management
- Outcome tracking and feedback loops

Usage:
    from scripts.pr_lifecycle import PRStateManager, PRMonitor

    # Register a PR for monitoring
    state_mgr = PRStateManager()
    state = PRState(pr_number=123, story_id="ST-001", ...)
    state_mgr.register_pr(state)

    # Monitor until terminal state
    monitor = PRMonitor()
    monitor.monitor_single_pr(123)

    # Track outcomes
    from scripts.pr_lifecycle.outcome_tracker import OutcomeTracker
    tracker = OutcomeTracker()
    tracker.record_merge(pr_number=123, story_id="ST-001", ...)

    # Generate feedback
    from scripts.pr_lifecycle.feedback_loop import FeedbackLoop
    feedback = FeedbackLoop()
    feedback.generate_weekly_report()
"""

from .feedback_loop import FeedbackLoop, RuleAdjustmentSuggestion, WeeklyReport
from .health_monitor import PRHealthMonitor
from .outcome_tracker import OutcomeTracker, PROutcome, SuccessMetrics
from .pr_monitor import PRMonitor
from .pr_state_manager import PREvent, PRState, PRStateManager
from .recovery_handlers import RecoveryHandlers, RecoveryResult

__all__ = [
    "PRStateManager",
    "PRState",
    "PREvent",
    "PRMonitor",
    "PRHealthMonitor",
    "RecoveryHandlers",
    "RecoveryResult",
    "OutcomeTracker",
    "PROutcome",
    "SuccessMetrics",
    "FeedbackLoop",
    "RuleAdjustmentSuggestion",
    "WeeklyReport",
]
