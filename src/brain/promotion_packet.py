"""
Brain Promotion Packet Module

Provides data models and utilities for generating human-approval promotion packets
for brain version promotions.

ST-CHISE-003: Brain Promotion Packet - Evidence + Rollback
"""

import contextlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


class PacketStatus(Enum):
    """Status of a promotion packet."""

    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"


class ApprovalStatus(Enum):
    """Status of an individual approval signature."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass
class ApprovalSignature:
    """
    Represents a single approval signature on a promotion packet.

    Attributes:
        approver: Name/identifier of the approver
        timestamp: When the signature was recorded
        status: Approval status (pending/approved/rejected)
        comments: Optional comments from the approver
    """

    approver: str
    timestamp: datetime
    status: ApprovalStatus
    comments: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "approver": self.approver,
            "timestamp": self.timestamp.isoformat(),
            "status": self.status.value,
            "comments": self.comments,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ApprovalSignature":
        """Create from dictionary."""
        return cls(
            approver=data["approver"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            status=ApprovalStatus(data["status"]),
            comments=data.get("comments"),
        )


@dataclass
class PromotionPacket:
    """
    Complete promotion packet for brain version approval.

    Contains all evidence, metrics, safety checks, and approval workflow
    information needed for human decision-making on brain promotions.

    Attributes:
        candidate_version: Version string of the candidate brain
        baseline_version: Version string of the baseline brain
        summary_metrics: Dict of performance metrics (accuracy, precision, etc.)
        safety_checks: Dict of safety check results (check_name -> pass/fail)
        rollback_plan: Markdown text describing rollback procedure
        required_approvers: List of approver names/roles required
        signatures: List of approval signatures
        created_at: When the packet was created
        status: Current status of the packet
    """

    candidate_version: str
    baseline_version: str
    summary_metrics: dict[str, float] = field(default_factory=dict)
    safety_checks: dict[str, bool] = field(default_factory=dict)
    rollback_plan: str = ""
    required_approvers: list[str] = field(default_factory=list)
    signatures: list[ApprovalSignature] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    status: PacketStatus = PacketStatus.DRAFT

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "candidate_version": self.candidate_version,
            "baseline_version": self.baseline_version,
            "summary_metrics": self.summary_metrics,
            "safety_checks": self.safety_checks,
            "rollback_plan": self.rollback_plan,
            "required_approvers": self.required_approvers,
            "signatures": [s.to_dict() for s in self.signatures],
            "created_at": self.created_at.isoformat(),
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PromotionPacket":
        """Create from dictionary."""
        return cls(
            candidate_version=data["candidate_version"],
            baseline_version=data["baseline_version"],
            summary_metrics=data.get("summary_metrics", {}),
            safety_checks=data.get("safety_checks", {}),
            rollback_plan=data.get("rollback_plan", ""),
            required_approvers=data.get("required_approvers", []),
            signatures=[
                ApprovalSignature.from_dict(s) for s in data.get("signatures", [])
            ],
            created_at=datetime.fromisoformat(data["created_at"]),
            status=PacketStatus(data.get("status", "draft")),
        )


class PacketGenerator:
    """
    Generates promotion packets from evaluation results and leaderboard data.

    This class builds complete promotion packets by extracting metrics from
    evaluation results and populating all required fields.
    """

    # Standard metrics to extract from evaluation results
    STANDARD_METRICS = [
        "accuracy",
        "precision",
        "recall",
        "f1",
        "win_rate",
        "sharpe",
        "max_drawdown",
    ]

    # Standard safety checks
    STANDARD_SAFETY_CHECKS = [
        "no_regression_on_critical_metrics",
        "passes_all_unit_tests",
        "passes_integration_tests",
        "shadow_test_passed",
        "latency_within_bounds",
        "memory_within_bounds",
    ]

    def __init__(self, rollback_template: str | None = None):
        """
        Initialize the packet generator.

        Args:
            rollback_template: Optional template for rollback plans
        """
        self.rollback_template = rollback_template or self._default_rollback_template()

    def _default_rollback_template(self) -> str:
        """Return default rollback plan template."""
        return """# Rollback Plan

## Immediate Rollback (Emergency)

If critical issues are detected after promotion:

1. **Stop new traffic** to the candidate version
   ```bash
   # Command to stop traffic routing
   brain-ops deactivate {candidate_version}
   ```

2. **Activate baseline version**
   ```bash
   brain-ops activate {baseline_version}
   ```

3. **Verify rollback**
   - Check health endpoints return 200
   - Confirm baseline version is serving traffic
   - Monitor error rates for 5 minutes

## Post-Rollback Steps

1. Document the issue in incident tracker
2. Preserve logs from candidate version
3. Notify team via #brain-ops channel
4. Schedule post-mortem within 24 hours

## Rollback Verification

- [ ] Baseline version active and healthy
- [ ] No traffic routed to candidate
- [ ] Error rates returned to normal
- [ ] Stakeholders notified
"""

    def generate(
        self,
        evaluation_results: dict[str, Any],
        leaderboard: dict[str, Any] | None = None,
        baseline_version: str = "unknown",
        required_approvers: list[str] | None = None,
    ) -> PromotionPacket:
        """
        Generate a promotion packet from evaluation results.

        Args:
            evaluation_results: Dict containing evaluation metrics and results
            leaderboard: Optional leaderboard data for context
            baseline_version: Version string of the baseline brain
            required_approvers: List of required approver names/roles

        Returns:
            PromotionPacket with populated fields
        """
        # Extract candidate version
        candidate_version = evaluation_results.get("version", "unknown")

        # Extract summary metrics
        summary_metrics = self._extract_metrics(evaluation_results)

        # Extract safety checks
        safety_checks = self._extract_safety_checks(evaluation_results)

        # Generate rollback plan
        rollback_plan = self._generate_rollback_plan(
            candidate_version, baseline_version
        )

        # Create packet
        packet = PromotionPacket(
            candidate_version=candidate_version,
            baseline_version=baseline_version,
            summary_metrics=summary_metrics,
            safety_checks=safety_checks,
            rollback_plan=rollback_plan,
            required_approvers=required_approvers or [],
            signatures=[],
            status=PacketStatus.DRAFT,
        )

        return packet

    def _extract_metrics(self, evaluation_results: dict[str, Any]) -> dict[str, float]:
        """Extract standard metrics from evaluation results."""
        metrics = {}

        # Try to get metrics from various possible locations in the results
        metrics_source = (
            evaluation_results.get("metrics", {})
            or evaluation_results.get("summary", {})
            or evaluation_results
        )

        for metric_name in self.STANDARD_METRICS:
            if metric_name in metrics_source:
                value = metrics_source[metric_name]
                # Ensure it's a float
                with contextlib.suppress(TypeError, ValueError):
                    metrics[metric_name] = float(value)

        return metrics

    def _extract_safety_checks(
        self, evaluation_results: dict[str, Any]
    ) -> dict[str, bool]:
        """Extract safety check results from evaluation results."""
        checks = {}

        # Try to get checks from various possible locations
        checks_source = (
            evaluation_results.get("safety_checks", {})
            or evaluation_results.get("checks", {})
            or evaluation_results.get("validation", {})
            or {}
        )

        for check_name in self.STANDARD_SAFETY_CHECKS:
            if check_name in checks_source:
                checks[check_name] = bool(checks_source[check_name])

        return checks

    def _generate_rollback_plan(
        self, candidate_version: str, baseline_version: str
    ) -> str:
        """Generate rollback plan with version placeholders filled."""
        return self.rollback_template.format(
            candidate_version=candidate_version,
            baseline_version=baseline_version,
        )


def export_to_markdown(packet: PromotionPacket, filepath: str) -> None:
    """
    Export a promotion packet to Markdown format.

    Creates a human-readable document suitable for review and approval.

    Args:
        packet: The promotion packet to export
        filepath: Path where the markdown file should be written
    """
    lines = []

    # Header
    lines.append("# Brain Promotion Packet")
    lines.append("")
    lines.append(f"**Candidate Version:** `{packet.candidate_version}`")
    lines.append(f"**Baseline Version:** `{packet.baseline_version}`")
    lines.append(f"**Status:** {packet.status.value.upper()}")
    lines.append(f"**Created:** {packet.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    lines.append("")

    # Summary Metrics
    lines.append("## Summary Metrics")
    lines.append("")
    if packet.summary_metrics:
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        for metric_name, value in packet.summary_metrics.items():
            # Format based on metric type
            if (
                "rate" in metric_name.lower()
                or metric_name
                in [
                    "accuracy",
                    "precision",
                    "recall",
                    "f1",
                    "win_rate",
                ]
                or "drawdown" in metric_name.lower()
            ):
                formatted_value = f"{value:.2%}"
            else:
                formatted_value = f"{value:.4f}"
            lines.append(
                f"| {metric_name.replace('_', ' ').title()} | {formatted_value} |"
            )
    else:
        lines.append("*No metrics available*")
    lines.append("")

    # Safety Checks
    lines.append("## Safety Checks")
    lines.append("")
    if packet.safety_checks:
        for check_name, passed in packet.safety_checks.items():
            status = "✅ PASS" if passed else "❌ FAIL"
            lines.append(f"- {status} {check_name.replace('_', ' ').title()}")
    else:
        lines.append("*No safety checks recorded*")
    lines.append("")

    # Rollback Plan
    lines.append("## Rollback Plan")
    lines.append("")
    lines.append(packet.rollback_plan)
    lines.append("")

    # Approval Workflow
    lines.append("## Approval Workflow")
    lines.append("")
    approvers_str = (
        ", ".join(packet.required_approvers)
        if packet.required_approvers
        else "None specified"
    )
    lines.append(f"**Required Approvers:** {approvers_str}")
    lines.append("")

    if packet.signatures:
        lines.append("### Signatures")
        lines.append("")
        lines.append("| Approver | Status | Timestamp | Comments |")
        lines.append("|----------|--------|-----------|----------|")
        for sig in packet.signatures:
            status_emoji = {
                ApprovalStatus.PENDING: "⏳",
                ApprovalStatus.APPROVED: "✅",
                ApprovalStatus.REJECTED: "❌",
            }.get(sig.status, "❓")
            comments = sig.comments or ""
            timestamp_str = sig.timestamp.strftime("%Y-%m-%d %H:%M")
            row_str = (
                f"| {sig.approver} | "
                f"{status_emoji} {sig.status.value} | "
                f"{timestamp_str} | "
                f"{comments} |"
            )
            lines.append(row_str)
    else:
        lines.append("*No signatures yet*")
    lines.append("")

    # Completeness Check
    lines.append("## Completeness Check")
    lines.append("")
    is_complete_result = is_complete(packet)
    if is_complete_result:
        lines.append("✅ **Packet is complete**")
    else:
        missing = get_missing_fields(packet)
        lines.append("❌ **Packet is incomplete**")
        lines.append("")
        lines.append("**Missing fields:**")
        for field_name in missing:
            lines.append(f"- {field_name}")
    lines.append("")

    # Write to file
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w") as f:
        f.write("\n".join(lines))


def export_to_json(packet: PromotionPacket, filepath: str) -> None:
    """
    Export a promotion packet to JSON format.

    Creates a machine-parseable file suitable for automated processing.

    Args:
        packet: The promotion packet to export
        filepath: Path where the JSON file should be written
    """
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w") as f:
        json.dump(packet.to_dict(), f, indent=2)


def is_complete(packet: PromotionPacket) -> bool:
    """
    Check if a promotion packet has all required fields populated.

    Args:
        packet: The promotion packet to validate

    Returns:
        True if all required fields are present and valid
    """
    return len(get_missing_fields(packet)) == 0


def get_missing_fields(packet: PromotionPacket) -> list[str]:
    """
    Get a list of missing or invalid fields in a promotion packet.

    Args:
        packet: The promotion packet to check

    Returns:
        List of field names that are missing or invalid
    """
    missing = []

    # Check required string fields
    if not packet.candidate_version or packet.candidate_version == "unknown":
        missing.append("candidate_version")

    if not packet.baseline_version or packet.baseline_version == "unknown":
        missing.append("baseline_version")

    # Check metrics
    if not packet.summary_metrics:
        missing.append("summary_metrics (empty)")

    # Check safety checks
    if not packet.safety_checks:
        missing.append("safety_checks (empty)")

    # Check rollback plan
    if not packet.rollback_plan or packet.rollback_plan.strip() == "":
        missing.append("rollback_plan")

    # Check required approvers
    if not packet.required_approvers:
        missing.append("required_approvers (empty)")

    return missing


def add_signature(
    packet: PromotionPacket,
    approver: str,
    status: ApprovalStatus,
    comments: str | None = None,
) -> PromotionPacket:
    """
    Add an approval signature to a promotion packet.

    Args:
        packet: The promotion packet to modify
        approver: Name/identifier of the approver
        status: Approval status
        comments: Optional comments

    Returns:
        The modified packet (same instance, modified in-place)
    """
    signature = ApprovalSignature(
        approver=approver,
        timestamp=datetime.utcnow(),
        status=status,
        comments=comments,
    )
    packet.signatures.append(signature)

    # Update packet status based on signatures
    _update_packet_status(packet)

    return packet


def _update_packet_status(packet: PromotionPacket) -> None:
    """Update packet status based on current signatures."""
    if not packet.required_approvers:
        return

    # Check if any rejection
    for sig in packet.signatures:
        if sig.status == ApprovalStatus.REJECTED:
            packet.status = PacketStatus.REJECTED
            return

    # Check if all required approvers have approved
    approved_approvers = {
        sig.approver
        for sig in packet.signatures
        if sig.status == ApprovalStatus.APPROVED
    }

    if all(req in approved_approvers for req in packet.required_approvers):
        packet.status = PacketStatus.APPROVED
    elif any(sig.status == ApprovalStatus.PENDING for sig in packet.signatures):
        packet.status = PacketStatus.PENDING_APPROVAL


def is_approved(packet: PromotionPacket) -> bool:
    """
    Check if a promotion packet has all required approvals.

    Args:
        packet: The promotion packet to check

    Returns:
        True if all required approvers have signed with APPROVED status
    """
    if not packet.required_approvers:
        # If no approvers required, check if packet status is approved
        return packet.status == PacketStatus.APPROVED

    approved_approvers = {
        sig.approver
        for sig in packet.signatures
        if sig.status == ApprovalStatus.APPROVED
    }

    return all(req in approved_approvers for req in packet.required_approvers)
