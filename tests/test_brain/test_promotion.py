"""Tests for brain promotion module."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from brain.promotion import (
    PromotionBlockedError,
    PromotionError,
    PromotionGate,
    PromotionPacket,
    PromotionStatus,
    RequiredField,
    RequiredFieldStatus,
)


class TestRequiredField:
    """Tests for RequiredField class."""

    def test_creation(self) -> None:
        """Test basic creation."""
        field = RequiredField(
            name="test_field",
            description="A test field",
            status=RequiredFieldStatus.PRESENT,
            value="test_value",
        )
        assert field.name == "test_field"
        assert field.status == RequiredFieldStatus.PRESENT

    def test_to_dict(self) -> None:
        """Test serialization."""
        field = RequiredField(
            name="test_field",
            description="A test field",
            status=RequiredFieldStatus.VERIFIED,
            value={"key": "value"},
        )
        data = field.to_dict()
        assert data["name"] == "test_field"
        assert data["status"] == "verified"
        assert data["value"] == {"key": "value"}

    def test_from_dict(self) -> None:
        """Test deserialization."""
        data = {
            "name": "test_field",
            "description": "A test field",
            "status": "present",
            "value": "test_value",
        }
        field = RequiredField.from_dict(data)
        assert field.name == "test_field"
        assert field.status == RequiredFieldStatus.PRESENT


class TestPromotionPacket:
    """Tests for PromotionPacket class."""

    def test_creation(self) -> None:
        """Test basic creation."""
        packet = PromotionPacket(version="1.0.0")
        assert packet.version == "1.0.0"
        assert packet.status == PromotionStatus.PENDING
        assert len(packet.required_fields) == 8  # All required fields initialized

    def test_all_fields_complete(self) -> None:
        """Test checking if all fields are complete."""
        packet = PromotionPacket(version="1.0.0")
        assert packet.all_fields_complete is False

        # Mark all fields as present
        for name in packet.required_fields:
            packet.set_field(name, "value", RequiredFieldStatus.PRESENT)

        assert packet.all_fields_complete is True

    def test_completion_percentage(self) -> None:
        """Test completion percentage calculation."""
        packet = PromotionPacket(version="1.0.0")
        assert packet.completion_percentage == 0.0

        # Mark half the fields
        fields = list(packet.required_fields.keys())
        for name in fields[:4]:
            packet.set_field(name, "value", RequiredFieldStatus.PRESENT)

        assert packet.completion_percentage == 50.0

    def test_set_field(self) -> None:
        """Test setting field values."""
        packet = PromotionPacket(version="1.0.0")
        packet.set_field("evaluation_report", "report_data")

        assert packet.required_fields["evaluation_report"].value == "report_data"
        assert (
            packet.required_fields["evaluation_report"].status
            == RequiredFieldStatus.PRESENT
        )

    def test_set_custom_field(self) -> None:
        """Test setting a custom field."""
        packet = PromotionPacket(version="1.0.0")
        packet.set_field("custom_field", "custom_value")

        assert "custom_field" in packet.required_fields
        assert packet.required_fields["custom_field"].value == "custom_value"

    def test_approve(self) -> None:
        """Test approval."""
        packet = PromotionPacket(version="1.0.0")
        packet.approve(approver="test_user", notes="LGTM")

        assert packet.status == PromotionStatus.APPROVED
        assert packet.approver == "test_user"
        assert packet.approval_notes == "LGTM"
        assert packet.approval_timestamp is not None

    def test_reject(self) -> None:
        """Test rejection."""
        packet = PromotionPacket(version="1.0.0")
        packet.reject(approver="test_user", notes="Issues found")

        assert packet.status == PromotionStatus.REJECTED
        assert packet.approver == "test_user"
        assert packet.approval_notes == "Issues found"

    def test_override(self) -> None:
        """Test override."""
        packet = PromotionPacket(version="1.0.0")
        packet.override(approver="admin", notes="Emergency override")

        assert packet.status == PromotionStatus.OVERRIDDEN
        assert packet.approver == "admin"

    def test_to_dict(self) -> None:
        """Test serialization."""
        packet = PromotionPacket(
            version="1.0.0",
            evaluation_passed=True,
            shadow_test_passed=True,
        )
        data = packet.to_dict()
        assert data["version"] == "1.0.0"
        assert data["evaluation_passed"] is True
        assert data["status"] == "pending"
        assert "required_fields" in data

    def test_from_dict(self) -> None:
        """Test deserialization."""
        data = {
            "version": "1.0.0",
            "previous_version": "0.9.0",
            "evaluation_passed": True,
            "shadow_test_passed": True,
            "latency_acceptable": True,
            "required_fields": {},
            "created_at": "2024-01-01T00:00:00Z",
            "status": "approved",
            "approver": "test_user",
        }
        packet = PromotionPacket.from_dict(data)
        assert packet.version == "1.0.0"
        assert packet.status == PromotionStatus.APPROVED
        assert packet.approver == "test_user"

    def test_to_markdown(self) -> None:
        """Test markdown generation."""
        packet = PromotionPacket(
            version="1.0.0",
            evaluation_passed=True,
            shadow_test_passed=True,
            latency_acceptable=True,
        )
        md = packet.to_markdown()

        assert "# Brain Version Promotion Packet: 1.0.0" in md
        assert "**Version:** 1.0.0" in md
        assert "**Evaluation Passed:**" in md
        assert "## Required Fields" in md


class TestPromotionGate:
    """Tests for PromotionGate class."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for promotion storage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_creation(self, temp_dir: str) -> None:
        """Test basic creation."""
        gate = PromotionGate(temp_dir)
        assert gate.allow_override is False

    def test_creation_with_override(self, temp_dir: str) -> None:
        """Test creation with override enabled."""
        gate = PromotionGate(temp_dir, allow_override=True)
        assert gate.allow_override is True

    def test_create_packet(self, temp_dir: str) -> None:
        """Test creating a promotion packet."""
        gate = PromotionGate(temp_dir)
        packet = gate.create_packet(
            version="1.0.0",
            previous_version="0.9.0",
            evaluation_passed=True,
        )

        assert packet.version == "1.0.0"
        assert packet.previous_version == "0.9.0"
        assert packet.evaluation_passed is True

        # Verify file was created
        packet_file = Path(temp_dir) / "promotion_1.0.0.json"
        assert packet_file.exists()

    def test_check_promotion_allowed_all_pass(self, temp_dir: str) -> None:
        """Test promotion allowed when all checks pass."""
        gate = PromotionGate(temp_dir)
        packet = PromotionPacket(
            version="1.0.0",
            evaluation_passed=True,
            shadow_test_passed=True,
            latency_acceptable=True,
        )
        # Mark all required fields complete
        for name in packet.required_fields:
            packet.set_field(name, "value", RequiredFieldStatus.PRESENT)
        packet.approve(approver="test_user")

        allowed, reason = gate.check_promotion_allowed(packet)
        assert allowed is True
        assert "allowed" in reason.lower()

    def test_check_promotion_blocked_by_evaluation(self, temp_dir: str) -> None:
        """Test promotion blocked when evaluation fails."""
        gate = PromotionGate(temp_dir)
        packet = PromotionPacket(
            version="1.0.0",
            evaluation_passed=False,
        )

        allowed, reason = gate.check_promotion_allowed(packet)
        assert allowed is False
        assert "evaluation" in reason.lower()

    def test_check_promotion_blocked_by_shadow_test(self, temp_dir: str) -> None:
        """Test promotion blocked when shadow test fails."""
        gate = PromotionGate(temp_dir)
        packet = PromotionPacket(
            version="1.0.0",
            evaluation_passed=True,
            shadow_test_passed=False,
        )

        allowed, reason = gate.check_promotion_allowed(packet)
        assert allowed is False
        assert "shadow" in reason.lower()

    def test_check_promotion_blocked_by_latency(self, temp_dir: str) -> None:
        """Test promotion blocked when latency is unacceptable."""
        gate = PromotionGate(temp_dir)
        packet = PromotionPacket(
            version="1.0.0",
            evaluation_passed=True,
            shadow_test_passed=True,
            latency_acceptable=False,
        )

        allowed, reason = gate.check_promotion_allowed(packet)
        assert allowed is False
        assert "latency" in reason.lower()

    def test_check_promotion_blocked_by_incomplete_fields(self, temp_dir: str) -> None:
        """Test promotion blocked when required fields are incomplete."""
        gate = PromotionGate(temp_dir)
        packet = PromotionPacket(
            version="1.0.0",
            evaluation_passed=True,
            shadow_test_passed=True,
            latency_acceptable=True,
        )
        # Don't mark fields complete

        allowed, reason = gate.check_promotion_allowed(packet)
        assert allowed is False
        assert "incomplete" in reason.lower()

    def test_check_promotion_requires_approval(self, temp_dir: str) -> None:
        """Test promotion requires human approval."""
        gate = PromotionGate(temp_dir)
        packet = PromotionPacket(
            version="1.0.0",
            evaluation_passed=True,
            shadow_test_passed=True,
            latency_acceptable=True,
        )
        for name in packet.required_fields:
            packet.set_field(name, "value", RequiredFieldStatus.PRESENT)
        # Don't approve

        allowed, reason = gate.check_promotion_allowed(packet)
        assert allowed is False
        assert "approval" in reason.lower()

    def test_approve_promotion(self, temp_dir: str) -> None:
        """Test approving a promotion."""
        gate = PromotionGate(temp_dir)
        gate.create_packet(version="1.0.0", evaluation_passed=True)

        packet = gate.approve_promotion("1.0.0", "test_user", "LGTM")
        assert packet.status == PromotionStatus.APPROVED
        assert packet.approver == "test_user"

    def test_approve_promotion_blocked(self, temp_dir: str) -> None:
        """Test that approving blocked promotion raises error."""
        gate = PromotionGate(temp_dir, allow_override=False)
        gate.create_packet(version="1.0.0", evaluation_passed=False)

        with pytest.raises(PromotionBlockedError):
            gate.approve_promotion("1.0.0", "test_user")

    def test_reject_promotion(self, temp_dir: str) -> None:
        """Test rejecting a promotion."""
        gate = PromotionGate(temp_dir)
        gate.create_packet(version="1.0.0")

        packet = gate.reject_promotion("1.0.0", "test_user", "Issues found")
        assert packet.status == PromotionStatus.REJECTED
        assert packet.approval_notes == "Issues found"

    def test_override_promotion(self, temp_dir: str) -> None:
        """Test overriding a blocked promotion."""
        gate = PromotionGate(temp_dir, allow_override=True)
        gate.create_packet(version="1.0.0", evaluation_passed=False)

        packet = gate.override_promotion("1.0.0", "admin", "Emergency")
        assert packet.status == PromotionStatus.OVERRIDDEN
        assert packet.approver == "admin"

    def test_override_not_allowed(self, temp_dir: str) -> None:
        """Test that override raises error when not allowed."""
        gate = PromotionGate(temp_dir, allow_override=False)
        gate.create_packet(version="1.0.0")

        with pytest.raises(PromotionError):
            gate.override_promotion("1.0.0", "admin")

    def test_load_packet(self, temp_dir: str) -> None:
        """Test loading a packet."""
        gate = PromotionGate(temp_dir)
        gate.create_packet(version="1.0.0", evaluation_passed=True)

        loaded = gate.load_packet("1.0.0")
        assert loaded is not None
        assert loaded.version == "1.0.0"
        assert loaded.evaluation_passed is True

    def test_load_packet_not_found(self, temp_dir: str) -> None:
        """Test loading non-existent packet."""
        gate = PromotionGate(temp_dir)
        loaded = gate.load_packet("1.0.0")
        assert loaded is None

    def test_list_packets(self, temp_dir: str) -> None:
        """Test listing packets."""
        gate = PromotionGate(temp_dir)
        gate.create_packet(version="1.0.0")
        gate.create_packet(version="1.1.0")

        packets = gate.list_packets()
        assert len(packets) == 2

    def test_list_packets_by_status(self, temp_dir: str) -> None:
        """Test listing packets filtered by status."""
        gate = PromotionGate(temp_dir)
        gate.create_packet(version="1.0.0")
        gate.approve_promotion("1.0.0", "test_user")
        gate.create_packet(version="1.1.0")

        approved = gate.list_packets(status=PromotionStatus.APPROVED)
        assert len(approved) == 1
        assert approved[0].version == "1.0.0"
