"""
Brain Promotion Packet - Evidence + Rollback Documentation

Generates human-approval promotion packets with evaluation summary,
safety checks, rollback steps, and approval tracking.

ST-CHISE-003: Brain Promotion Packet - Evidence + Rollback
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

# Import from local module to avoid circular imports
from brain.batch_evaluator import EvaluationResult, EvaluationStatus


class PacketStatus(Enum):
    """Status of a promotion packet."""

    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class SafetyCheckStatus(Enum):
    """Status of a safety check."""

    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class SafetyCheck:
    """Individual safety check with result."""

    name: str
    description: str
    status: SafetyCheckStatus
    details: str = ""
    checked_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "details": self.details,
            "checked_at": self.checked_at.isoformat() if self.checked_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SafetyCheck:
        """Create from dictionary."""
        return cls(
            name=data["name"],
            description=data["description"],
            status=SafetyCheckStatus(data["status"]),
            details=data.get("details", ""),
            checked_at=datetime.fromisoformat(data["checked_at"])
            if data.get("checked_at")
            else None,
        )


@dataclass
class RollbackStep:
    """Single rollback step with verification."""

    step_number: int
    description: str
    command: str
    verification_command: str
    expected_result: str
    estimated_time_seconds: int
    requires_confirmation: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RollbackStep:
        """Create from dictionary."""
        return cls(**data)


@dataclass
class RollbackPlan:
    """Complete rollback plan with steps."""

    trigger_conditions: list[str] = field(default_factory=list)
    steps: list[RollbackStep] = field(default_factory=list)
    estimated_total_time_seconds: int = 0
    tested_in_dev: bool = False
    tested_at: datetime | None = None

    def __post_init__(self):
        """Calculate estimated total time."""
        self.estimated_total_time_seconds = sum(
            step.estimated_time_seconds for step in self.steps
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "trigger_conditions": self.trigger_conditions,
            "steps": [s.to_dict() for s in self.steps],
            "estimated_total_time_seconds": self.estimated_total_time_seconds,
            "tested_in_dev": self.tested_in_dev,
            "tested_at": self.tested_at.isoformat() if self.tested_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RollbackPlan:
        """Create from dictionary."""
        return cls(
            trigger_conditions=data.get("trigger_conditions", []),
            steps=[RollbackStep.from_dict(s) for s in data.get("steps", [])],
            estimated_total_time_seconds=data.get("estimated_total_time_seconds", 0),
            tested_in_dev=data.get("tested_in_dev", False),
            tested_at=datetime.fromisoformat(data["tested_at"])
            if data.get("tested_at")
            else None,
        )


@dataclass
class ApprovalRecord:
    """Human approval record."""

    approver_name: str
    approver_email: str
    approved_at: datetime
    signature: str  # Cryptographic signature or approval hash
    comments: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "approver_name": self.approver_name,
            "approver_email": self.approver_email,
            "approved_at": self.approved_at.isoformat(),
            "signature": self.signature,
            "comments": self.comments,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ApprovalRecord:
        """Create from dictionary."""
        return cls(
            approver_name=data["approver_name"],
            approver_email=data["approver_email"],
            approved_at=datetime.fromisoformat(data["approved_at"]),
            signature=data["signature"],
            comments=data.get("comments", ""),
        )


@dataclass
class PromotionPacket:
    """
    Complete promotion packet for brain version approval.

    Includes evaluation summary, safety checks, rollback plan,
    and human approval tracking.
    """

    # Identification
    packet_id: str
    brain_version: str
    brain_name: str
    created_at: datetime

    # Evaluation Summary
    evaluation_result: EvaluationResult
    comparison_baseline: str | None = None  # Version being compared against
    improvement_summary: dict[str, float] = field(default_factory=dict)

    # Safety Checks
    safety_checks: list[SafetyCheck] = field(default_factory=list)

    # Rollback Plan
    rollback_plan: RollbackPlan = field(default_factory=lambda: RollbackPlan())

    # Approval
    status: PacketStatus = PacketStatus.DRAFT
    approval: ApprovalRecord | None = None

    # Metadata
    generated_by: str = "system"
    expires_at: datetime | None = None

    def __post_init__(self):
        """Post-initialization validation."""
        if not self.packet_id:
            timestamp = int(time.time())
            version_hash = hashlib.sha256(self.brain_version.encode()).hexdigest()[:8]
            self.packet_id = f"PROMO-{timestamp}-{version_hash}"

        # Set default expiration (7 days)
        if self.expires_at is None:
            from datetime import timedelta

            self.expires_at = self.created_at + timedelta(days=7)

    def to_dict(self) -> dict[str, Any]:
        """Convert packet to dictionary (machine-parseable)."""
        return {
            "packet_id": self.packet_id,
            "brain_version": self.brain_version,
            "brain_name": self.brain_name,
            "created_at": self.created_at.isoformat(),
            "evaluation_result": self.evaluation_result.to_dict(),
            "comparison_baseline": self.comparison_baseline,
            "improvement_summary": self.improvement_summary,
            "safety_checks": [sc.to_dict() for sc in self.safety_checks],
            "rollback_plan": self.rollback_plan.to_dict(),
            "status": self.status.value,
            "approval": self.approval.to_dict() if self.approval else None,
            "generated_by": self.generated_by,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }

    def to_json(self) -> str:
        """Export as JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    def to_markdown(self) -> str:
        """
        Export as human-readable Markdown.

        This is the primary human-approval format.
        """
        lines = [
            f"# Brain Promotion Packet: {self.brain_name} ({self.brain_version})",
            "",
            "## Packet Information",
            f"- **Packet ID:** `{self.packet_id}`",
            f"- **Brain Version:** `{self.brain_version}`",
            f"- **Brain Name:** {self.brain_name}",
            f"- **Created:** {self.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}",
            f"- **Generated By:** {self.generated_by}",
            f"- **Status:** {self.status.value.upper()}",
            f"- **Expires:** {self.expires_at.strftime('%Y-%m-%d %H:%M:%S UTC') if self.expires_at else 'N/A'}",
            "",
            "---",
            "",
            "## Evaluation Summary",
            "",
        ]

        # Evaluation metrics table
        m = self.evaluation_result.metrics
        lines.extend(
            [
                "### Performance Metrics",
                "",
                "| Metric | Value | Status |",
                "|--------|-------|--------|",
                f"| Accuracy | {m.accuracy:.3f} | {'✅' if m.accuracy >= 0.70 else '⚠️'} |",
                f"| Precision | {m.precision:.3f} | {'✅' if m.precision >= 0.70 else '⚠️'} |",
                f"| Recall | {m.recall:.3f} | {'✅' if m.recall >= 0.70 else '⚠️'} |",
                f"| F1 Score | {m.f1_score:.3f} | {'✅' if m.f1_score >= 0.70 else '⚠️'} |",
                f"| Win Rate | {m.win_rate:.3f} | {'✅' if m.win_rate >= 0.55 else '⚠️'} |",
                f"| Sharpe Ratio | {m.sharpe_ratio:.3f} | {'✅' if m.sharpe_ratio >= 1.0 else '⚠️'} |",
                f"| Max Drawdown | {m.max_drawdown:.3f} | {'✅' if m.max_drawdown <= 0.15 else '⚠️'} |",
                "",
            ]
        )

        # Comparison baseline
        if self.comparison_baseline:
            lines.extend(
                [
                    f"### Comparison vs Baseline ({self.comparison_baseline})",
                    "",
                ]
            )
            for metric, improvement in self.improvement_summary.items():
                emoji = "📈" if improvement > 0 else ("📉" if improvement < 0 else "➡️")
                lines.append(f"- **{metric}:** {improvement:+.3f} {emoji}")
            lines.append("")

        # Evaluation details
        lines.extend(
            [
                "### Evaluation Details",
                f"- **Test Suite:** {self.evaluation_result.test_suite}",
                f"- **Duration:** {self.evaluation_result.duration_seconds:.1f} seconds",
                f"- **Completed:** {self.evaluation_result.completed_at.strftime('%Y-%m-%d %H:%M:%S UTC') if self.evaluation_result.completed_at else 'N/A'}",
                f"- **Evaluation Status:** {self.evaluation_result.status.value}",
                "",
            ]
        )

        if self.evaluation_result.error_message:
            lines.extend(
                [
                    f"⚠️ **Error:** {self.evaluation_result.error_message}",
                    "",
                ]
            )

        lines.extend(
            [
                "---",
                "",
                "## Safety Checks",
                "",
            ]
        )

        # Safety checks table
        lines.extend(
            [
                "| Check | Status | Details |",
                "|-------|--------|---------|",
            ]
        )
        for check in self.safety_checks:
            status_emoji = {
                SafetyCheckStatus.PASSED: "✅",
                SafetyCheckStatus.FAILED: "❌",
                SafetyCheckStatus.PENDING: "⏳",
                SafetyCheckStatus.SKIPPED: "⏭️",
            }.get(check.status, "❓")
            lines.append(
                f"| {check.name} | {status_emoji} {check.status.value} | {check.details} |"
            )
        lines.append("")

        lines.extend(
            [
                "---",
                "",
                "## Rollback Plan",
                "",
            ]
        )

        # Trigger conditions
        lines.extend(
            [
                "### Trigger Conditions",
                "The following conditions will trigger an automatic rollback:",
                "",
            ]
        )
        for condition in self.rollback_plan.trigger_conditions:
            lines.append(f"- {condition}")
        lines.append("")

        # Rollback steps
        lines.extend(
            [
                f"### Rollback Steps (Estimated Time: {self.rollback_plan.estimated_total_time_seconds // 60} minutes)",
                "",
            ]
        )

        if self.rollback_plan.tested_in_dev:
            lines.append(
                f"✅ **Tested in Dev Environment** (Last tested: {self.rollback_plan.tested_at.strftime('%Y-%m-%d %H:%M:%S UTC') if self.rollback_plan.tested_at else 'Unknown'})"
            )
        else:
            lines.append("⚠️ **Not yet tested in Dev Environment**")
        lines.append("")

        for step in self.rollback_plan.steps:
            confirm_text = (
                " [REQUIRES CONFIRMATION]" if step.requires_confirmation else ""
            )
            lines.extend(
                [
                    f"#### Step {step.step_number}: {step.description}{confirm_text}",
                    "",
                    "**Command:**",
                    f"```bash\n{step.command}\n```",
                    "",
                    "**Verification:**",
                    f"```bash\n{step.verification_command}\n```",
                    "",
                    f"**Expected Result:** {step.expected_result}",
                    f"**Estimated Time:** {step.estimated_time_seconds} seconds",
                    "",
                ]
            )

        lines.extend(
            [
                "---",
                "",
                "## Human Approval",
                "",
            ]
        )

        if self.approval:
            lines.extend(
                [
                    f"✅ **APPROVED** by {self.approval.approver_name} ({self.approval.approver_email})",
                    f"- **Approved At:** {self.approval.approved_at.strftime('%Y-%m-%d %H:%M:%S UTC')}",
                    f"- **Signature:** `{self.approval.signature}`",
                    "",
                    "**Comments:**",
                    f"> {self.approval.comments or 'No comments provided'}",
                    "",
                ]
            )
        else:
            lines.extend(
                [
                    "⏳ **PENDING APPROVAL**",
                    "",
                    "### Approval Checklist",
                    "",
                    "- [ ] I have reviewed the evaluation metrics",
                    "- [ ] I have verified all safety checks passed",
                    "- [ ] I understand the rollback procedure",
                    "- [ ] I have tested the rollback in dev environment",
                    "- [ ] I approve this brain version for promotion",
                    "",
                    "### Approval Signature",
                    "",
                    "To approve this packet, run:",
                    "",
                    f'```bash\npython -m src.brain.promotion_packet approve {self.packet_id} --name="Your Name" --email="your.email@example.com"\n```',
                    "",
                ]
            )

        lines.extend(
            [
                "---",
                "",
                "## Packet Verification",
                "",
                f"**Packet Hash:** `{self._calculate_hash()}`",
                "",
                "This packet is machine-parseable. To verify integrity:",
                "",
                f"```bash\npython -m src.brain.promotion_packet verify {self.packet_id}\n```",
                "",
            ]
        )

        return "\n".join(lines)

    def _calculate_hash(self) -> str:
        """Calculate packet hash for integrity verification."""
        content = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def verify_completeness(self) -> tuple[bool, list[str]]:
        """
        Verify all required fields are present.

        Returns:
            Tuple of (is_complete, list of missing fields)
        """
        missing = []

        # Required fields
        if not self.brain_version:
            missing.append("brain_version")
        if not self.brain_name:
            missing.append("brain_name")

        # Evaluation required
        if self.evaluation_result.status != EvaluationStatus.COMPLETED:
            missing.append("evaluation_result (must be completed)")

        # Safety checks required
        if not self.safety_checks:
            missing.append("safety_checks (at least one required)")

        # Rollback plan required
        if not self.rollback_plan.steps:
            missing.append("rollback_plan.steps (at least one required)")

        # Check for failed safety checks
        failed_checks = [
            sc.name
            for sc in self.safety_checks
            if sc.status == SafetyCheckStatus.FAILED
        ]
        if failed_checks:
            missing.append(f"safety_checks failed: {', '.join(failed_checks)}")

        return len(missing) == 0, missing

    def approve(
        self,
        approver_name: str,
        approver_email: str,
        comments: str = "",
    ) -> None:
        """
        Approve this promotion packet.

        Args:
            approver_name: Name of approver
            approver_email: Email of approver
            comments: Optional approval comments
        """
        # Verify completeness first
        is_complete, missing = self.verify_completeness()
        if not is_complete:
            raise ValueError(
                f"Cannot approve incomplete packet. Missing: {', '.join(missing)}"
            )

        # Create approval signature
        approval_data = (
            f"{self.packet_id}:{approver_name}:{approver_email}:{int(time.time())}"
        )
        signature = hashlib.sha256(approval_data.encode()).hexdigest()[:32]

        self.approval = ApprovalRecord(
            approver_name=approver_name,
            approver_email=approver_email,
            approved_at=datetime.utcnow(),
            signature=signature,
            comments=comments,
        )
        self.status = PacketStatus.APPROVED

    def reject(self, reason: str) -> None:
        """Reject this promotion packet."""
        self.status = PacketStatus.REJECTED
        # Store rejection reason in first safety check or create new one
        if self.safety_checks:
            self.safety_checks[0].details = f"Rejected: {reason}"

    def is_expired(self) -> bool:
        """Check if packet has expired."""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at

    def save(self, directory: Path | None = None) -> Path:
        """
        Save packet to disk.

        Returns:
            Path to saved file
        """
        if directory is None:
            directory = Path("_bmad-output/brain-promotions")

        directory.mkdir(parents=True, exist_ok=True)

        # Save both JSON and Markdown
        json_path = directory / f"{self.packet_id}.json"
        md_path = directory / f"{self.packet_id}.md"

        with open(json_path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

        with open(md_path, "w") as f:
            f.write(self.to_markdown())

        return json_path

    @classmethod
    def load(
        cls, packet_id: str, directory: Path | None = None
    ) -> PromotionPacket | None:
        """Load packet from disk."""
        if directory is None:
            directory = Path("_bmad-output/brain-promotions")

        json_path = directory / f"{packet_id}.json"

        if not json_path.exists():
            return None

        with open(json_path) as f:
            data = json.load(f)

        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PromotionPacket:
        """Create packet from dictionary."""
        return cls(
            packet_id=data["packet_id"],
            brain_version=data["brain_version"],
            brain_name=data["brain_name"],
            created_at=datetime.fromisoformat(data["created_at"]),
            evaluation_result=EvaluationResult.from_dict(data["evaluation_result"]),
            comparison_baseline=data.get("comparison_baseline"),
            improvement_summary=data.get("improvement_summary", {}),
            safety_checks=[
                SafetyCheck.from_dict(sc) for sc in data.get("safety_checks", [])
            ],
            rollback_plan=RollbackPlan.from_dict(data.get("rollback_plan", {})),
            status=PacketStatus(data.get("status", "draft")),
            approval=ApprovalRecord.from_dict(data["approval"])
            if data.get("approval")
            else None,
            generated_by=data.get("generated_by", "system"),
            expires_at=datetime.fromisoformat(data["expires_at"])
            if data.get("expires_at")
            else None,
        )


class PromotionPacketGenerator:
    """Generates promotion packets from evaluation results."""

    def __init__(self, packets_dir: Path | None = None):
        """
        Initialize generator.

        Args:
            packets_dir: Directory to save packets
        """
        self.packets_dir = packets_dir or Path("_bmad-output/brain-promotions")
        self.packets_dir.mkdir(parents=True, exist_ok=True)

    def generate_packet(
        self,
        evaluation_result: EvaluationResult,
        comparison_baseline: EvaluationResult | None = None,
        generated_by: str = "system",
    ) -> PromotionPacket:
        """
        Generate a promotion packet from evaluation result.

        Args:
            evaluation_result: The evaluation result to promote
            comparison_baseline: Optional baseline to compare against
            generated_by: Identifier of generator

        Returns:
            Complete promotion packet
        """
        # Calculate improvements if baseline provided
        improvement_summary = {}
        if comparison_baseline:
            m_current = evaluation_result.metrics
            m_baseline = comparison_baseline.metrics

            for metric_name in [
                "accuracy",
                "precision",
                "recall",
                "f1_score",
                "win_rate",
            ]:
                current = getattr(m_current, metric_name)
                baseline = getattr(m_baseline, metric_name)
                improvement_summary[metric_name] = current - baseline

        # Create default safety checks
        safety_checks = self._create_default_safety_checks(evaluation_result)

        # Create default rollback plan
        rollback_plan = self._create_default_rollback_plan(
            evaluation_result.brain_version
        )

        packet = PromotionPacket(
            packet_id="",
            brain_version=evaluation_result.brain_version,
            brain_name=evaluation_result.brain_name,
            created_at=datetime.utcnow(),
            evaluation_result=evaluation_result,
            comparison_baseline=comparison_baseline.brain_version
            if comparison_baseline
            else None,
            improvement_summary=improvement_summary,
            safety_checks=safety_checks,
            rollback_plan=rollback_plan,
            status=PacketStatus.PENDING_APPROVAL,
            generated_by=generated_by,
        )

        return packet

    def _create_default_safety_checks(
        self,
        evaluation_result: EvaluationResult,
    ) -> list[SafetyCheck]:
        """Create default safety checks based on evaluation."""
        m = evaluation_result.metrics

        checks = [
            SafetyCheck(
                name="Minimum Accuracy Threshold",
                description="Brain must achieve at least 70% accuracy",
                status=SafetyCheckStatus.PASSED
                if m.accuracy >= 0.70
                else SafetyCheckStatus.FAILED,
                details=f"Achieved: {m.accuracy:.3f}",
                checked_at=datetime.utcnow(),
            ),
            SafetyCheck(
                name="Minimum Win Rate",
                description="Brain must achieve at least 55% win rate",
                status=SafetyCheckStatus.PASSED
                if m.win_rate >= 0.55
                else SafetyCheckStatus.FAILED,
                details=f"Achieved: {m.win_rate:.3f}",
                checked_at=datetime.utcnow(),
            ),
            SafetyCheck(
                name="Maximum Drawdown",
                description="Brain must not exceed 15% max drawdown",
                status=SafetyCheckStatus.PASSED
                if m.max_drawdown <= 0.15
                else SafetyCheckStatus.FAILED,
                details=f"Achieved: {m.max_drawdown:.3f}",
                checked_at=datetime.utcnow(),
            ),
            SafetyCheck(
                name="Evaluation Completion",
                description="Evaluation must complete without errors",
                status=SafetyCheckStatus.PASSED
                if evaluation_result.status == EvaluationStatus.COMPLETED
                else SafetyCheckStatus.FAILED,
                details=f"Status: {evaluation_result.status.value}",
                checked_at=datetime.utcnow(),
            ),
            SafetyCheck(
                name="Sharpe Ratio",
                description="Brain should have Sharpe ratio >= 1.0",
                status=SafetyCheckStatus.PASSED
                if m.sharpe_ratio >= 1.0
                else SafetyCheckStatus.FAILED,
                details=f"Achieved: {m.sharpe_ratio:.3f}",
                checked_at=datetime.utcnow(),
            ),
        ]

        return checks

    def _create_default_rollback_plan(self, brain_version: str) -> RollbackPlan:
        """Create default rollback plan."""
        return RollbackPlan(
            trigger_conditions=[
                "ECE degradation > 0.15 from baseline",
                "Safety violations detected in production",
                "Human request via emergency rollback command",
                "Win rate drops below 50% over 24h period",
                "Max drawdown exceeds 20%",
            ],
            steps=[
                RollbackStep(
                    step_number=1,
                    description="Stop active signal generation",
                    command="python -m src.brain.rollback_handler stop-signals --version="
                    + brain_version,
                    verification_command="python -m src.brain.rollback_handler check-signals --version="
                    + brain_version,
                    expected_result="Signal generation stopped, no new signals being emitted",
                    estimated_time_seconds=30,
                ),
                RollbackStep(
                    step_number=2,
                    description="Verify no active trades",
                    command="python -m src.execution.check_trades --status=active",
                    verification_command="python -m src.execution.check_trades --status=active --count",
                    expected_result="Active trade count = 0",
                    estimated_time_seconds=15,
                    requires_confirmation=True,
                ),
                RollbackStep(
                    step_number=3,
                    description="Switch to previous brain version",
                    command=f"python -m src.brain.rollback_handler switch-version --from={brain_version} --to=previous",
                    verification_command="python -m src.brain.rollback_handler get-current-version",
                    expected_result="Current version is previous stable version",
                    estimated_time_seconds=60,
                    requires_confirmation=True,
                ),
                RollbackStep(
                    step_number=4,
                    description="Verify data consistency",
                    command="python -m src.data.consistency_check --full",
                    verification_command="python -m src.data.consistency_check --summary",
                    expected_result="All consistency checks pass",
                    estimated_time_seconds=120,
                ),
                RollbackStep(
                    step_number=5,
                    description="Resume signal generation with previous version",
                    command="python -m src.brain.rollback_handler start-signals --version=previous",
                    verification_command="python -m src.brain.rollback_handler check-signals --version=previous",
                    expected_result="Signal generation resumed with previous version",
                    estimated_time_seconds=30,
                ),
            ],
            tested_in_dev=False,
        )


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python promotion_packet.py <command> [args...]")
        print("Commands: generate, approve, verify")
        sys.exit(1)

    command = sys.argv[1]

    if command == "verify" and len(sys.argv) >= 3:
        packet_id = sys.argv[2]
        packet = PromotionPacket.load(packet_id)
        if packet:
            is_complete, missing = packet.verify_completeness()
            print(f"Packet {packet_id}:")
            print(f"  Complete: {is_complete}")
            if not is_complete:
                print(f"  Missing: {', '.join(missing)}")
            print(f"  Hash: {packet._calculate_hash()}")
        else:
            print(f"Packet {packet_id} not found")
    else:
        print(f"Unknown command: {command}")
