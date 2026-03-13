"""Automation module for self-healing control plane.

Provides comprehensive self-healing automation with:
- Automation Controller for closed-loop remediation
- Runbook Engine for structured procedure execution
- Predefined remediation workflows

For ST-CONTROL-002: Self-Healing Automation
"""

from autonomous_control_plane.automation.controller import (
    AutomationController,
    DecisionRule,
    EscalationLevel,
    EscalationPolicy,
    RemediationStatus,
    RemediationStep,
    RemediationWorkflow,
)
from autonomous_control_plane.automation.runbook_engine import (
    Runbook,
    RunbookEngine,
    RunbookExecution,
    RunbookStatus,
    RunbookStep,
    RunbookStepStatus,
)
from autonomous_control_plane.automation.workflows.remediation_workflows import (
    RemediationWorkflows,
)

__all__ = [
    # Controller
    "AutomationController",
    "RemediationWorkflow",
    "RemediationStep",
    "RemediationStatus",
    "EscalationLevel",
    "EscalationPolicy",
    "DecisionRule",
    # Runbook Engine
    "RunbookEngine",
    "Runbook",
    "RunbookStep",
    "RunbookExecution",
    "RunbookStatus",
    "RunbookStepStatus",
    # Workflows
    "RemediationWorkflows",
]
