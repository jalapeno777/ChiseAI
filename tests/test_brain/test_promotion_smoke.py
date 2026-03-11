"""Smoke tests for brain promotion module.

Verifies basic functionality and imports for the promotion gating system.
"""

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


class TestRequiredFieldSmoke:
    """Smoke tests for RequiredField class."""

    def test_field_creation(self) -> None:
        """Test creating a required field."""
        field = RequiredField(
            name="test_field",
            description="A test field",
            status=RequiredFieldStatus.PRESENT,
            value="test_value",
        )

        assert field.name == "test_field"
        assert field.description == "A test field"
        assert field.status == RequiredFieldStatus.PRESENT
        assert field.value == "test_value"

    def test_field_to_dict(self) -> None:
        """Test converting field to dict."""
        field = RequiredField(
            name="test",
            description="Test field",
            status=RequiredFieldStatus.VERIFIED,
            value=123,
        )

        data = field.to_dict()
        assert data["name"] == "test"
        assert data["status"] == "verified"
        assert data["value"] == 123

    def test_field_from_dict(self) -> None:
        """Test creating field from dict."""
        data = {
            "name": "test_field",
            "description": "Test description",
            "status": "present",
            "value": "test_value",
        }

        field = RequiredField.from_dict(data)
        assert field.name == "test_field"
        assert field.status == RequiredFieldStatus.PRESENT


class TestPromotionPacketSmoke:
    """Smoke tests for PromotionPacket class."""

    def test_packet_creation(self) -> None:
        """Test creating a promotion packet."""
        packet = PromotionPacket(version="1.0.0")

        assert packet.version == "1.0.0"
        assert packet.status == PromotionStatus.PENDING
        assert packet.created_at

    def test_packet_with_previous_version(self) -> None:
        """Test packet with previous version."""
        packet = PromotionPacket(version="1.1.0", previous_version="1.0.0")

        assert packet.version == "1.1.0"
        assert packet.previous_version == "1.0.0"

    def test_required_fields_initialized(self) -> None:
        """Test that required fields are auto-initialized."""
        packet = PromotionPacket(version="1.0.0")

        assert len(packet.required_fields) > 0
        assert "version_manifest" in packet.required_fields
        assert "evaluation_report" in packet.required_fields

    def test_completion_percentage(self) -> None:
        """Test completion percentage calculation."""
        packet = PromotionPacket(version="1.0.0")

        # Initially all fields are missing
        initial_pct = packet.completion_percentage
        assert initial_pct == 0.0

        # Mark one field as present
        packet.set_field("version_manifest", "data", RequiredFieldStatus.PRESENT)
        new_pct = packet.completion_percentage
        assert new_pct > 0.0

    def test_all_fields_complete(self) -> None:
        """Test all fields complete check."""
        packet = PromotionPacket(version="1.0.0")

        assert not packet.all_fields_complete

        # Mark all fields as present
        for name in packet.required_fields:
            packet.set_field(name, "data", RequiredFieldStatus.PRESENT)

        assert packet.all_fields_complete

    def test_approve_promotion(self) -> None:
        """Test approving a promotion."""
        packet = PromotionPacket(version="1.0.0")

        packet.approve("test_approver", "Looks good")

        assert packet.status == PromotionStatus.APPROVED
        assert packet.approver == "test_approver"
        assert packet.approval_notes == "Looks good"
        assert packet.approval_timestamp

    def test_reject_promotion(self) -> None:
        """Test rejecting a promotion."""
        packet = PromotionPacket(version="1.0.0")

        packet.reject("test_approver", "Issues found")

        assert packet.status == PromotionStatus.REJECTED
        assert packet.approver == "test_approver"
        assert packet.approval_notes == "Issues found"

    def test_override_promotion(self) -> None:
        """Test overriding a blocked promotion."""
        packet = PromotionPacket(version="1.0.0")
        packet.status = PromotionStatus.BLOCKED

        packet.override("admin", "Emergency override")

        assert packet.status == PromotionStatus.OVERRIDDEN
        assert packet.approver == "admin"

    def test_packet_to_dict(self) -> None:
        """Test converting packet to dict."""
        packet = PromotionPacket(
            version="1.0.0",
            previous_version="0.9.0",
            evaluation_passed=True,
        )

        data = packet.to_dict()
        assert data["version"] == "1.0.0"
        assert data["previous_version"] == "0.9.0"
        assert data["evaluation_passed"] is True

    def test_packet_from_dict(self) -> None:
        """Test creating packet from dict."""
        packet = PromotionPacket(version="1.0.0")
        packet.approve("test", "notes")

        data = packet.to_dict()
        restored = PromotionPacket.from_dict(data)

        assert restored.version == "1.0.0"
        assert restored.status == PromotionStatus.APPROVED
        assert restored.approver == "test"

    def test_to_markdown(self) -> None:
        """Test markdown generation."""
        packet = PromotionPacket(version="1.0.0")
        markdown = packet.to_markdown()

        assert "1.0.0" in markdown
        assert "PENDING" in markdown
        assert "version_manifest" in markdown


class TestPromotionGateSmoke:
    """Smoke tests for PromotionGate class."""

    def test_gate_initialization(self) -> None:
        """Test initializing promotion gate."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gate = PromotionGate(tmpdir)
            assert gate.storage_path == Path(tmpdir)
            assert gate.allow_override is False

    def test_gate_with_override(self) -> None:
        """Test gate with override enabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gate = PromotionGate(tmpdir, allow_override=True)
            assert gate.allow_override is True

    def test_create_packet(self) -> None:
        """Test creating packet through gate."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gate = PromotionGate(tmpdir)
            packet = gate.create_packet("1.0.0", "0.9.0")

            assert packet.version == "1.0.0"
            assert packet.previous_version == "0.9.0"

    def test_check_promotion_allowed_all_pass(self) -> None:
        """Test promotion check when all criteria pass."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gate = PromotionGate(tmpdir)
            packet = gate.create_packet(
                "1.0.0",
                evaluation_passed=True,
                shadow_test_passed=True,
                latency_acceptable=True,
            )

            # Fill all required fields
            for name in packet.required_fields:
                packet.set_field(name, "data", RequiredFieldStatus.PRESENT)
            packet.approve("test", "approved")

            allowed, reason = gate.check_promotion_allowed(packet)
            assert allowed is True
            assert "allowed" in reason.lower()

    def test_check_promotion_blocked_evaluation(self) -> None:
        """Test promotion blocked by failed evaluation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gate = PromotionGate(tmpdir)
            packet = gate.create_packet(
                "1.0.0",
                evaluation_passed=False,
            )

            allowed, reason = gate.check_promotion_allowed(packet)
            assert allowed is False
            assert "evaluation" in reason.lower()

    def test_check_promotion_blocked_shadow(self) -> None:
        """Test promotion blocked by failed shadow test."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gate = PromotionGate(tmpdir)
            packet = gate.create_packet(
                "1.0.0",
                evaluation_passed=True,
                shadow_test_passed=False,
            )

            allowed, reason = gate.check_promotion_allowed(packet)
            assert allowed is False
            assert "shadow" in reason.lower()

    def test_check_promotion_blocked_latency(self) -> None:
        """Test promotion blocked by latency."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gate = PromotionGate(tmpdir)
            packet = gate.create_packet(
                "1.0.0",
                evaluation_passed=True,
                shadow_test_passed=True,
                latency_acceptable=False,
            )

            allowed, reason = gate.check_promotion_allowed(packet)
            assert allowed is False
            assert "latency" in reason.lower()

    def test_approve_promotion(self) -> None:
        """Test approving through gate."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gate = PromotionGate(tmpdir, allow_override=True)
            packet = gate.create_packet(
                "1.0.0",
                evaluation_passed=True,
                shadow_test_passed=True,
                latency_acceptable=True,
            )

            # Fill required fields
            for name in packet.required_fields:
                packet.set_field(name, "data", RequiredFieldStatus.PRESENT)

            approved = gate.approve_promotion("1.0.0", "approver", "Approved")
            assert approved.status == PromotionStatus.APPROVED

    def test_reject_promotion(self) -> None:
        """Test rejecting through gate."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gate = PromotionGate(tmpdir)
            packet = gate.create_packet("1.0.0")

            rejected = gate.reject_promotion("1.0.0", "approver", "Rejected")
            assert rejected.status == PromotionStatus.REJECTED

    def test_override_promotion(self) -> None:
        """Test override through gate."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gate = PromotionGate(tmpdir, allow_override=True)
            packet = gate.create_packet("1.0.0")

            overridden = gate.override_promotion("1.0.0", "admin", "Override")
            assert overridden.status == PromotionStatus.OVERRIDDEN

    def test_override_not_allowed(self) -> None:
        """Test override fails when not enabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gate = PromotionGate(tmpdir, allow_override=False)
            gate.create_packet("1.0.0")

            with pytest.raises(PromotionError):
                gate.override_promotion("1.0.0", "admin", "Override")

    def test_update_packet_status(self) -> None:
        """Test updating packet status."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gate = PromotionGate(tmpdir)
            gate.create_packet("1.0.0")

            updated = gate.update_packet_status(
                "1.0.0",
                evaluation_passed=True,
                shadow_test_passed=True,
                latency_acceptable=True,
            )

            assert updated.evaluation_passed is True
            assert updated.shadow_test_passed is True

    def test_load_packet(self) -> None:
        """Test loading packet from storage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gate = PromotionGate(tmpdir)
            gate.create_packet("1.0.0")

            loaded = gate.load_packet("1.0.0")
            assert loaded is not None
            assert loaded.version == "1.0.0"

    def test_load_nonexistent_packet(self) -> None:
        """Test loading non-existent packet."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gate = PromotionGate(tmpdir)

            loaded = gate.load_packet("9.9.9")
            assert loaded is None

    def test_list_packets(self) -> None:
        """Test listing packets."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gate = PromotionGate(tmpdir)
            gate.create_packet("1.0.0")
            gate.create_packet("1.1.0")

            packets = gate.list_packets()
            assert len(packets) == 2

    def test_list_packets_by_status(self) -> None:
        """Test listing packets filtered by status."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gate = PromotionGate(tmpdir, allow_override=True)
            gate.create_packet(
                "1.0.0",
                evaluation_passed=True,
                shadow_test_passed=True,
                latency_acceptable=True,
            )
            # Fill all required fields before approving
            packet = gate.load_packet("1.0.0")
            for name in packet.required_fields:
                packet.set_field(name, "data", RequiredFieldStatus.PRESENT)
            # Save the updated packet
            gate._save_packet(packet)
            gate.approve_promotion("1.0.0", "test", "approved")

            pending = gate.list_packets(status=PromotionStatus.PENDING)
            approved = gate.list_packets(status=PromotionStatus.APPROVED)

            assert len(pending) == 0
            assert len(approved) == 1


class TestPromotionStatusSmoke:
    """Smoke tests for PromotionStatus enum."""

    def test_status_values(self) -> None:
        """Test status enum values."""
        assert PromotionStatus.PENDING.value == "pending"
        assert PromotionStatus.APPROVED.value == "approved"
        assert PromotionStatus.REJECTED.value == "rejected"
        assert PromotionStatus.BLOCKED.value == "blocked"
        assert PromotionStatus.OVERRIDDEN.value == "overridden"


class TestPromotionPacketSerializationSmoke:
    """Smoke tests for promotion packet serialization."""

    def test_packet_serialization_roundtrip(self) -> None:
        """Test that packets can be serialized and deserialized correctly."""
        # Create a packet with all field types populated
        packet = PromotionPacket(
            version="2.0.0",
            previous_version="1.0.0",
            evaluation_passed=True,
            shadow_test_passed=True,
            latency_acceptable=True,
            risk_assessment="Low risk",
            rollback_plan="Rollback to v1.0.0",
        )

        # Set all required fields
        for name in packet.required_fields:
            packet.set_field(name, f"data_for_{name}", RequiredFieldStatus.VERIFIED)

        # Approve the packet
        packet.approve("test_approver", "Approved for production")

        # Serialize to dict
        data = packet.to_dict()

        # Deserialize from dict
        restored = PromotionPacket.from_dict(data)

        # Verify all fields are correctly restored
        assert restored.version == packet.version
        assert restored.previous_version == packet.previous_version
        assert restored.evaluation_passed == packet.evaluation_passed
        assert restored.shadow_test_passed == packet.shadow_test_passed
        assert restored.latency_acceptable == packet.latency_acceptable
        assert restored.risk_assessment == packet.risk_assessment
        assert restored.rollback_plan == packet.rollback_plan
        assert restored.approver == packet.approver
        assert restored.approval_notes == packet.approval_notes
        assert restored.status == packet.status
        assert restored.all_fields_complete == packet.all_fields_complete
        assert restored.completion_percentage == packet.completion_percentage

        # Verify required fields are restored
        assert len(restored.required_fields) == len(packet.required_fields)
        for name in packet.required_fields:
            assert name in restored.required_fields
            assert (
                restored.required_fields[name].status
                == packet.required_fields[name].status
            )
            assert (
                restored.required_fields[name].value
                == packet.required_fields[name].value
            )

    def test_packet_with_all_field_types(self) -> None:
        """Test packet serialization with all possible field types."""
        packet = PromotionPacket(version="3.0.0")

        # Test with various value types
        test_values = [
            ("string_field", "test string"),
            ("int_field", 42),
            ("float_field", 3.14159),
            ("bool_field", True),
            ("list_field", ["item1", "item2", "item3"]),
            ("dict_field", {"key1": "value1", "key2": "value2"}),
            ("nested_dict", {"outer": {"inner": "value"}}),
            ("none_field", None),
        ]

        for field_name, value in test_values:
            packet.set_field(field_name, value, RequiredFieldStatus.PRESENT)

        # Serialize and deserialize
        data = packet.to_dict()
        restored = PromotionPacket.from_dict(data)

        # Verify all custom fields are restored correctly
        for field_name, expected_value in test_values:
            assert field_name in restored.required_fields
            assert restored.required_fields[field_name].value == expected_value
            assert (
                restored.required_fields[field_name].status
                == RequiredFieldStatus.PRESENT
            )


class TestPromotionExceptionsSmoke:
    """Smoke tests for promotion exceptions."""

    def test_promotion_error_is_exception(self) -> None:
        """Test PromotionError is an Exception."""
        assert issubclass(PromotionError, Exception)

    def test_promotion_blocked_error(self) -> None:
        """Test PromotionBlockedError is PromotionError."""
        assert issubclass(PromotionBlockedError, PromotionError)
