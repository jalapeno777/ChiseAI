"""Pydantic models for GitReviewBot."""

from enum import Enum
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class DecisionType(str, Enum):
    """Review decision types."""

    APPROVE = "APPROVE"
    COMMENT = "COMMENT"
    REQUEST_CHANGES = "REQUEST_CHANGES"


class Severity(str, Enum):
    """Finding severity levels."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class Finding(BaseModel):
    """A technical finding from SeniorDev review."""

    file: str = Field(..., description="Path to the file")
    line: Optional[int] = Field(None, description="Line number (1-indexed)")
    severity: Severity = Field(..., description="Severity of the finding")
    message: str = Field(..., description="Description of the issue")
    suggestion: Optional[str] = Field(None, description="Suggested fix")
    code_snippet: Optional[str] = Field(None, description="Relevant code snippet")


class Violation(BaseModel):
    """A compliance violation from Critic review."""

    rule: str = Field(..., description="Rule that was violated")
    severity: Severity = Field(..., description="Severity of the violation")
    message: str = Field(..., description="Description of the violation")
    file: Optional[str] = Field(None, description="File where violation occurred")


class ReviewResult(BaseModel):
    """Result from a single role review."""

    role: str = Field(
        ..., description="Role that performed the review (SeniorDev/Critic)"
    )
    findings: List[Finding] = Field(
        default_factory=list, description="Technical findings"
    )
    violations: List[Violation] = Field(
        default_factory=list, description="Compliance violations"
    )
    summary: str = Field(..., description="Overall assessment summary")
    confidence: float = Field(..., ge=0, le=100, description="Confidence score 0-100")
    blockers: List[str] = Field(default_factory=list, description="Blocking issues")
    reviewed_at: datetime = Field(default_factory=datetime.utcnow)
    duration_ms: Optional[int] = Field(
        None, description="Review duration in milliseconds"
    )


class Decision(BaseModel):
    """Synthesized decision from dual-role review."""

    decision: DecisionType = Field(..., description="Final decision")
    confidence: float = Field(
        ..., ge=0, le=100, description="Combined confidence 0-100"
    )
    senior_dev_confidence: float = Field(..., ge=0, le=100)
    critic_confidence: float = Field(..., ge=0, le=100)
    blockers: List[str] = Field(default_factory=list)
    findings: List[Finding] = Field(default_factory=list)
    violations: List[Violation] = Field(default_factory=list)
    summary: str = Field(..., description="Decision reasoning")
    auto_merge_eligible: bool = Field(
        False, description="Whether auto-merge is allowed"
    )
    pr_number: int = Field(..., description="PR number")
    pr_title: str = Field(..., description="PR title")
    story_id: Optional[str] = Field(None, description="Extracted story ID")
    decided_at: datetime = Field(default_factory=datetime.utcnow)


class ReviewFeedback(BaseModel):
    """Human feedback on a bot review."""

    pr_number: int
    review_id: str
    feedback_type: str = Field(..., pattern="^(👍|👎|thumbs_up|thumbs_down)$")
    reviewer: str
    comment: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class PRDetails(BaseModel):
    """PR details from Gitea."""

    number: int
    title: str
    body: Optional[str] = None
    author: str
    branch: str
    base_branch: str
    state: str
    created_at: datetime
    updated_at: datetime
    files_changed: List[str] = Field(default_factory=list)
    labels: List[str] = Field(default_factory=list)


class CalibrationMetrics(BaseModel):
    """Metrics for bot calibration."""

    total_reviews: int
    approved_reviews: int
    commented_reviews: int
    requested_changes_reviews: int
    human_overrides: int
    human_agreements: int
    accuracy_rate: float = Field(..., ge=0, le=100)
    avg_confidence: float = Field(..., ge=0, le=100)
    false_positive_rate: float = Field(..., ge=0, le=100)
    false_negative_rate: float = Field(..., ge=0, le=100)
    period_start: datetime
    period_end: datetime


class CachedDiff(BaseModel):
    """Cached diff for similarity matching."""

    diff_hash: str
    pr_number: int
    files: List[str]
    review_result: ReviewResult
    created_at: datetime = Field(default_factory=datetime.utcnow)
    ttl_seconds: int = Field(default=86400)  # 24 hours
