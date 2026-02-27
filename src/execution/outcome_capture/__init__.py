"""Outcome capture module for execution integration.

Integrates outcome persistence and alerting into the execution hot path.
"""

from execution.outcome_capture.integration import OutcomeCaptureIntegration

__all__ = ["OutcomeCaptureIntegration"]
