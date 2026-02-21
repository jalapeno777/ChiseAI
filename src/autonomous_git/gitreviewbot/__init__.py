"""GitReviewBot - AI-powered code review bot for MEDIUM_RISK PRs.

This module provides a dual-role review architecture where SeniorDev
and Critic roles evaluate PRs in parallel, with synthesis into a
decision with confidence scoring.
"""

from .bot import GitReviewBot, review_pr
from .models import (
    ReviewResult,
    Decision,
    DecisionType,
    Finding,
    Violation,
    ReviewFeedback,
)
from .senior_dev import SeniorDevReviewer
from .critic import CriticReviewer
from .synthesizer import DecisionSynthesizer
from .confidence import ConfidenceScorer
from .calibration import CalibrationTracker
from .gitea_client import GiteaClient

__version__ = "0.1.0"
__all__ = [
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
