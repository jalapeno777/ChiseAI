"""Brain promotion module.

Provides promotion gating and human approval packet generation for
brain version promotion. Ensures CI blocks promotion on failed evaluations.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


logger = logging.getLogger(__name__)


class PromotionStatus(Enum):
    """Status of a promotion request."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    BLOCKED = "blocked"  # Blocked by failed evaluation
    OVERRIDDEN = "overridden"  # Human override of block


class RequiredFieldStatus(Enum):
    """Status of a required field in the promotion packet."""

    MISSING = "missing"
    PRESENT = "present"
    VERIFIED = "verified"


@dataclass
class RequiredField:
    """A required field in the promotion packet.

    Attributes:
        name: Field name
        description: Field description
        status: Field status
        value: Field value
    """

    name: str
    description: str
    status: RequiredFieldStatus
    value: Any = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "value": self.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RequiredField:
        """Create from dictionary."""
        return cls(
            name=data["name"],
            description=data["description"],
            status=RequiredFieldStatus(data.get("status", "missing")),
            value=data.get("value"),
        )


@dataclass
class PromotionPacket:
    """Human approval packet for brain version promotion.

    This packet contains all required information for human review
    and approval of a brain version promotion.

    Attributes:
        version: Brain version being promoted
        previous_version: Previous active version
        evaluation_passed: Whether evaluation passed
        shadow_test_passed: Whether shadow testing passed
        latency_acceptable: Whether latency is within limits
        required_fields: Dictionary of required fields and their status
        risk_assessment: Risk assessment summary
        rollback_plan: Rollback plan description
        approver: Name of approver (filled on approval)
        approval_timestamp: ISO timestamp of approval
        approval_notes: Notes from approver
        created_at: ISO timestamp when packet was created
        status: Promotion status
    """

    version: str
    previous_version: str | None = None
    evaluation_passed: bool = False
    shadow_test_passed: bool = False
    latency_acceptable: bool = False
    required_fields: dict[str, RequiredField] = field(default_factory=dict)
    risk_assessment: str = ""
    rollback_plan: str = ""
    approver: str | None = None
    approval_timestamp: str | None = None
    approval_notes: str = ""
    created_at: str = ""
    status: PromotionStatus = PromotionStatus.PENDING

    # Required field definitions
    REQUIRED_FIELD_NAMES = {
        "version_manifest": "Brain version manifest with all dependencies",
        "evaluation_report": "Full evaluation report with metrics",
        "shadow_test_report": "Shadow testing results and comparison",
        "performance_baseline": "Performance comparison to previous version",
        "risk_analysis": "Risk analysis and mitigation strategies",
        "rollback_procedure": "Detailed rollback procedure",
        "monitoring_plan": "Post-deployment monitoring plan",
        "test_coverage": "Test coverage report",
    }

    def __post_init__(self) -> None:
        """Initialize required fields if not provided."""
        if not self.required_fields:
            self.required_fields = {
                name: RequiredField(
                    name=name,
                    description=description,
                    status=RequiredFieldStatus.MISSING,
                )
                for name, description in self.REQUIRED_FIELD_NAMES.items()
            }

        if not self.created_at:
            self.created_at = datetime.now(UTC).isoformat()

        if isinstance(self.status, str):
            self.status = PromotionStatus(self.status)

    @property
    def all_fields_complete(self) -> bool:
        """Check if all required fields are present or verified."""
        return all(
            field.status in (RequiredFieldStatus.PRESENT, RequiredFieldStatus.VERIFIED)
            for field in self.required_fields.values()
        )

    @property
    def completion_percentage(self) -> float:
        """Calculate completion percentage of required fields."""
        if not self.required_fields:
            return 0.0

        complete = sum(
            1
            for field in self.required_fields.values()
            if field.status
            in (RequiredFieldStatus.PRESENT, RequiredFieldStatus.VERIFIED)
        )
        return (complete / len(self.required_fields)) * 100

    def set_field(
        self,
        name: str,
        value: Any,
        status: RequiredFieldStatus = RequiredFieldStatus.PRESENT,
    ) -> None:
        """Set a required field value.

        Args:
            name: Field name
            value: Field value
            status: Field status
        """
        if name in self.required_fields:
            self.required_fields[name].value = value
            self.required_fields[name].status = status
        else:
            # Add custom field
            self.required_fields[name] = RequiredField(
                name=name, description="Custom field", status=status, value=value
            )

    def approve(self, approver: str, notes: str = "") -> None:
        """Approve the promotion.

        Args:
            approver: Name of approver
            notes: Approval notes
        """
        self.approver = approver
        self.approval_timestamp = datetime.now(UTC).isoformat()
        self.approval_notes = notes
        self.status = PromotionStatus.APPROVED

    def reject(self, approver: str, notes: str = "") -> None:
        """Reject the promotion.

        Args:
            approver: Name of approver
            notes: Rejection notes
        """
        self.approver = approver
        self.approval_timestamp = datetime.now(UTC).isoformat()
        self.approval_notes = notes
        self.status = PromotionStatus.REJECTED

    def override(self, approver: str, notes: str = "") -> None:
        """Override a blocked promotion (requires explicit human approval).

        Args:
            approver: Name of approver
            notes: Override justification notes
        """
        self.approver = approver
        self.approval_timestamp = datetime.now(UTC).isoformat()
        self.approval_notes = notes
        self.status = PromotionStatus.OVERRIDDEN

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "version": self.version,
            "previous_version": self.previous_version,
            "evaluation_passed": self.evaluation_passed,
            "shadow_test_passed": self.shadow_test_passed,
            "latency_acceptable": self.latency_acceptable,
            "required_fields": {
                name: field.to_dict() for name, field in self.required_fields.items()
            },
            "risk_assessment": self.risk_assessment,
            "rollback_plan": self.rollback_plan,
            "approver": self.approver,
            "approval_timestamp": self.approval_timestamp,
            "approval_notes": self.approval_notes,
            "created_at": self.created_at,
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PromotionPacket:
        """Create from dictionary."""
        packet = cls(
            version=data["version"],
            previous_version=data.get("previous_version"),
            evaluation_passed=data.get("evaluation_passed", False),
            shadow_test_passed=data.get("shadow_test_passed", False),
            latency_acceptable=data.get("latency_acceptable", False),
            risk_assessment=data.get("risk_assessment", ""),
            rollback_plan=data.get("rollback_plan", ""),
            approver=data.get("approver"),
            approval_timestamp=data.get("approval_timestamp"),
            approval_notes=data.get("approval_notes", ""),
            created_at=data.get("created_at", ""),
            status=PromotionStatus(data.get("status", "pending")),
        )

        # Restore required fields
        fields_data = data.get("required_fields", {})
        packet.required_fields = {
            name: RequiredField.from_dict(field_data)
            for name, field_data in fields_data.items()
        }

        return packet

    def to_markdown(self) -> str:
        """Generate a markdown representation for human review."""
        lines = [
            f"# Brain Version Promotion Packet: {self.version}",
            "",
            "## Summary",
            f"- **Version:** {self.version}",
            f"- **Previous Version:** {self.previous_version or 'N/A'}",
            f"- **Status:** {self.status.value.upper()}",
            f"- **Created:** {self.created_at}",
            "",
            "## Validation Results",
            f"- **Evaluation Passed:** {'✅' if self.evaluation_passed else '❌'}",
            f"- **Shadow Test Passed:** {'✅' if self.shadow_test_passed else '❌'}",
            f"- **Latency Acceptable:** {'✅' if self.latency_acceptable else '❌'}",
            "",
            "## Required Fields",
            f"**Completion:** {self.completion_percentage:.1f}%",
            "",
            "| Field | Status | Description |",
            "|-------|--------|-------------|",
        ]

        for name, field_name in self.required_fields.items():
            status_icon = {
                RequiredFieldStatus.MISSING: "❌",
                RequiredFieldStatus.PRESENT: "✅",
                RequiredFieldStatus.VERIFIED: "✅✅",
            }.get(field_name.status, "❌")
            lines.append(
                f"| {name} | {status_icon} {field_name.status.value} | {field_name.description} |"
            )

        lines.extend(
            [
                "",
                "## Risk Assessment",
                self.risk_assessment or "*Not provided*",
                "",
                "## Rollback Plan",
                self.rollback_plan or "*Not provided*",
                "",
                "## Approval",
            ]
        )

        if self.approver:
            lines.extend(
                [
                    f"- **Approver:** {self.approver}",
                    f"- **Timestamp:** {self.approval_timestamp}",
                    f"- **Notes:** {self.approval_notes}",
                ]
            )
        else:
            lines.append("*Pending approval*")

        return "\n".join(lines)


class PromotionError(Exception):
    """Base exception for promotion errors."""

    pass


class PromotionBlockedError(PromotionError):
    """Raised when promotion is blocked by failed evaluation."""

    pass


class PromotionGate:
    """Gates promotion based on evaluation results and required fields.

    The promotion gate ensures:
    1. Evaluation must pass before promotion
    2. Shadow testing must pass
    3. Latency must be within acceptable limits
    4. All required fields in promotion packet must be complete
    5. Human approval is required

    Attributes:
        storage_path: Directory for storing promotion packets
        allow_override: Whether to allow human override of blocks

    Examples:
        >>> gate = PromotionGate("/path/to/packets")
        >>> packet = gate.create_packet("1.1.0", "1.0.0")
        >>> gate.check_promotion_allowed(packet)
        False  # Evaluation not passed
    """

    def __init__(
        self,
        storage_path: str | Path,
        allow_override: bool = False,
    ) -> None:
        """Initialize the promotion gate.

        Args:
            storage_path: Directory to store promotion packets
            allow_override: Whether to allow human override of blocks
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.allow_override = allow_override

    def create_packet(
        self,
        version: str,
        previous_version: str | None = None,
        evaluation_passed: bool = False,
        shadow_test_passed: bool = False,
        latency_acceptable: bool = False,
    ) -> PromotionPacket:
        """Create a new promotion packet.

        Args:
            version: Brain version to promote
            previous_version: Previous active version
            evaluation_passed: Whether evaluation passed
            shadow_test_passed: Whether shadow testing passed
            latency_acceptable: Whether latency is acceptable

        Returns:
            New PromotionPacket
        """
        packet = PromotionPacket(
            version=version,
            previous_version=previous_version,
            evaluation_passed=evaluation_passed,
            shadow_test_passed=shadow_test_passed,
            latency_acceptable=latency_acceptable,
        )

        # Save packet
        self._save_packet(packet)

        return packet

    def check_promotion_allowed(
        self,
        packet: PromotionPacket,
        require_human_approval: bool = True,
    ) -> tuple[bool, str]:
        """Check if promotion is allowed.

        Args:
            packet: Promotion packet to check
            require_human_approval: Whether human approval is required

        Returns:
            Tuple of (allowed, reason)
        """
        # Check evaluation passed (non-bypassable without override)
        if not packet.evaluation_passed:
            if packet.status == PromotionStatus.OVERRIDDEN and self.allow_override:
                return True, "Promotion allowed via human override"
            return False, "Evaluation did not pass - promotion blocked"

        # Check shadow test passed
        if not packet.shadow_test_passed:
            return False, "Shadow testing did not pass"

        # Check latency acceptable
        if not packet.latency_acceptable:
            return False, "Latency overhead exceeds acceptable limits"

        # Check all required fields complete
        if not packet.all_fields_complete:
            return (
                False,
                f"Required fields incomplete ({packet.completion_percentage:.1f}%)",
            )

        # Check human approval
        if require_human_approval:
            if packet.status not in (
                PromotionStatus.APPROVED,
                PromotionStatus.OVERRIDDEN,
            ):
                return False, "Human approval required"

        return True, "Promotion allowed"

    def approve_promotion(
        self,
        version: str,
        approver: str,
        notes: str = "",
    ) -> PromotionPacket:
        """Approve a promotion.

        Args:
            version: Brain version to approve
            approver: Name of approver
            notes: Approval notes

        Returns:
            Updated PromotionPacket

        Raises:
            PromotionBlockedError: If evaluation failed and override not allowed
        """
        packet = self.load_packet(version)
        if packet is None:
            raise PromotionError(f"Promotion packet not found for version {version}")

        # Check if blocked
        allowed, reason = self.check_promotion_allowed(
            packet, require_human_approval=False
        )
        if not allowed and not self.allow_override:
            raise PromotionBlockedError(f"Cannot approve: {reason}")

        packet.approve(approver, notes)
        self._save_packet(packet)

        logger.info(f"Promotion approved for {version} by {approver}")
        return packet

    def reject_promotion(
        self,
        version: str,
        approver: str,
        notes: str = "",
    ) -> PromotionPacket:
        """Reject a promotion.

        Args:
            version: Brain version to reject
            approver: Name of approver
            notes: Rejection notes

        Returns:
            Updated PromotionPacket
        """
        packet = self.load_packet(version)
        if packet is None:
            raise PromotionError(f"Promotion packet not found for version {version}")

        packet.reject(approver, notes)
        self._save_packet(packet)

        logger.info(f"Promotion rejected for {version} by {approver}")
        return packet

    def override_promotion(
        self,
        version: str,
        approver: str,
        notes: str = "",
    ) -> PromotionPacket:
        """Override a blocked promotion (requires explicit human approval).

        Args:
            version: Brain version to override
            approver: Name of approver
            notes: Override justification

        Returns:
            Updated PromotionPacket

        Raises:
            PromotionError: If override is not allowed
        """
        if not self.allow_override:
            raise PromotionError("Override is not enabled for this promotion gate")

        packet = self.load_packet(version)
        if packet is None:
            raise PromotionError(f"Promotion packet not found for version {version}")

        packet.override(approver, notes)
        self._save_packet(packet)

        logger.warning(f"Promotion override applied for {version} by {approver}")
        return packet

    def update_packet_status(
        self,
        version: str,
        evaluation_passed: bool | None = None,
        shadow_test_passed: bool | None = None,
        latency_acceptable: bool | None = None,
    ) -> PromotionPacket:
        """Update packet with test results.

        Args:
            version: Brain version
            evaluation_passed: Updated evaluation status
            shadow_test_passed: Updated shadow test status
            latency_acceptable: Updated latency status

        Returns:
            Updated PromotionPacket
        """
        packet = self.load_packet(version)
        if packet is None:
            raise PromotionError(f"Promotion packet not found for version {version}")

        if evaluation_passed is not None:
            packet.evaluation_passed = evaluation_passed
        if shadow_test_passed is not None:
            packet.shadow_test_passed = shadow_test_passed
        if latency_acceptable is not None:
            packet.latency_acceptable = latency_acceptable

        # Update status if evaluation failed
        if not packet.evaluation_passed and packet.status == PromotionStatus.PENDING:
            packet.status = PromotionStatus.BLOCKED

        self._save_packet(packet)
        return packet

    def _save_packet(self, packet: PromotionPacket) -> None:
        """Save promotion packet to storage."""
        packet_file = self.storage_path / f"promotion_{packet.version}.json"
        with open(packet_file, "w", encoding="utf-8") as f:
            json.dump(packet.to_dict(), f, indent=2)

        # Also save markdown version for human review
        md_file = self.storage_path / f"promotion_{packet.version}.md"
        with open(md_file, "w", encoding="utf-8") as f:
            f.write(packet.to_markdown())

    def load_packet(self, version: str) -> PromotionPacket | None:
        """Load a promotion packet from storage.

        Args:
            version: Brain version

        Returns:
            PromotionPacket if found, None otherwise
        """
        packet_file = self.storage_path / f"promotion_{version}.json"
        if not packet_file.exists():
            return None

        try:
            with open(packet_file, encoding="utf-8") as f:
                data = json.load(f)
                return PromotionPacket.from_dict(data)
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to load promotion packet for {version}: {e}")
            return None

    def list_packets(
        self, status: PromotionStatus | None = None
    ) -> list[PromotionPacket]:
        """List promotion packets.

        Args:
            status: Filter by status (optional)

        Returns:
            List of PromotionPacket objects
        """
        packets = []

        for packet_file in self.storage_path.glob("promotion_*.json"):
            try:
                with open(packet_file, encoding="utf-8") as f:
                    data = json.load(f)
                    packet = PromotionPacket.from_dict(data)
                    if status is None or packet.status == status:
                        packets.append(packet)
            except (json.JSONDecodeError, KeyError) as e:
                logger.error(f"Failed to load packet from {packet_file}: {e}")

        # Sort by created_at descending
        packets.sort(key=lambda p: p.created_at, reverse=True)
        return packets
