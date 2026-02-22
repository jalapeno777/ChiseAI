"""
Tests for promotion_packet module.

ST-CHISE-003: Brain Promotion Packet - Evidence + Rollback
"""

import json
from datetime import datetime

from src.brain.promotion_packet import (
    ApprovalSignature,
    ApprovalStatus,
    PacketGenerator,
    PacketStatus,
    PromotionPacket,
    add_signature,
    export_to_json,
    export_to_markdown,
    get_missing_fields,
    is_approved,
    is_complete,
)


class TestPacketStatus:
    """Tests for PacketStatus enum."""

    def test_packet_status_values(self):
        """Test that PacketStatus has expected values."""
        assert PacketStatus.DRAFT.value == "draft"
        assert PacketStatus.PENDING_APPROVAL.value == "pending_approval"
        assert PacketStatus.APPROVED.value == "approved"
        assert PacketStatus.REJECTED.value == "rejected"

    def test_packet_status_enum_count(self):
        """Test that PacketStatus has exactly 4 values."""
        assert len(list(PacketStatus)) == 4


class TestApprovalStatus:
    """Tests for ApprovalStatus enum."""

    def test_approval_status_values(self):
        """Test that ApprovalStatus has expected values."""
        assert ApprovalStatus.PENDING.value == "pending"
        assert ApprovalStatus.APPROVED.value == "approved"
        assert ApprovalStatus.REJECTED.value == "rejected"

    def test_approval_status_enum_count(self):
        """Test that ApprovalStatus has exactly 3 values."""
        assert len(list(ApprovalStatus)) == 3


class TestApprovalSignature:
    """Tests for ApprovalSignature dataclass."""

    def test_creation(self):
        """Test basic creation of ApprovalSignature."""
        now = datetime.utcnow()
        sig = ApprovalSignature(
            approver="test_user",
            timestamp=now,
            status=ApprovalStatus.PENDING,
        )
        assert sig.approver == "test_user"
        assert sig.timestamp == now
        assert sig.status == ApprovalStatus.PENDING
        assert sig.comments is None

    def test_creation_with_comments(self):
        """Test creation with comments."""
        sig = ApprovalSignature(
            approver="test_user",
            timestamp=datetime.utcnow(),
            status=ApprovalStatus.APPROVED,
            comments="Looks good!",
        )
        assert sig.comments == "Looks good!"

    def test_to_dict(self):
        """Test serialization to dict."""
        now = datetime(2024, 1, 15, 10, 30, 0)
        sig = ApprovalSignature(
            approver="test_user",
            timestamp=now,
            status=ApprovalStatus.APPROVED,
            comments="Approved",
        )
        d = sig.to_dict()
        assert d["approver"] == "test_user"
        assert d["timestamp"] == "2024-01-15T10:30:00"
        assert d["status"] == "approved"
        assert d["comments"] == "Approved"

    def test_from_dict(self):
        """Test deserialization from dict."""
        data = {
            "approver": "test_user",
            "timestamp": "2024-01-15T10:30:00",
            "status": "approved",
            "comments": "Approved",
        }
        sig = ApprovalSignature.from_dict(data)
        assert sig.approver == "test_user"
        assert sig.timestamp == datetime(2024, 1, 15, 10, 30, 0)
        assert sig.status == ApprovalStatus.APPROVED
        assert sig.comments == "Approved"

    def test_round_trip(self):
        """Test round-trip serialization."""
        now = datetime.utcnow()
        original = ApprovalSignature(
            approver="test_user",
            timestamp=now,
            status=ApprovalStatus.REJECTED,
            comments="Needs work",
        )
        d = original.to_dict()
        restored = ApprovalSignature.from_dict(d)
        assert restored.approver == original.approver
        assert restored.timestamp == original.timestamp
        assert restored.status == original.status
        assert restored.comments == original.comments


class TestPromotionPacket:
    """Tests for PromotionPacket dataclass."""

    def test_creation_minimal(self):
        """Test minimal creation of PromotionPacket."""
        packet = PromotionPacket(
            candidate_version="v2.0.0",
            baseline_version="v1.0.0",
        )
        assert packet.candidate_version == "v2.0.0"
        assert packet.baseline_version == "v1.0.0"
        assert packet.summary_metrics == {}
        assert packet.safety_checks == {}
        assert packet.rollback_plan == ""
        assert packet.required_approvers == []
        assert packet.signatures == []
        assert packet.status == PacketStatus.DRAFT

    def test_creation_full(self):
        """Test full creation of PromotionPacket."""
        now = datetime.utcnow()
        sig = ApprovalSignature(
            approver="admin",
            timestamp=now,
            status=ApprovalStatus.APPROVED,
        )
        packet = PromotionPacket(
            candidate_version="v2.0.0",
            baseline_version="v1.0.0",
            summary_metrics={"accuracy": 0.95},
            safety_checks={"tests_pass": True},
            rollback_plan="Rollback to v1.0.0",
            required_approvers=["admin", "lead"],
            signatures=[sig],
            created_at=now,
            status=PacketStatus.PENDING_APPROVAL,
        )
        assert packet.summary_metrics == {"accuracy": 0.95}
        assert packet.safety_checks == {"tests_pass": True}
        assert packet.rollback_plan == "Rollback to v1.0.0"
        assert packet.required_approvers == ["admin", "lead"]
        assert len(packet.signatures) == 1
        assert packet.status == PacketStatus.PENDING_APPROVAL

    def test_to_dict(self):
        """Test serialization to dict."""
        now = datetime(2024, 1, 15, 10, 30, 0)
        packet = PromotionPacket(
            candidate_version="v2.0.0",
            baseline_version="v1.0.0",
            summary_metrics={"accuracy": 0.95},
            created_at=now,
        )
        d = packet.to_dict()
        assert d["candidate_version"] == "v2.0.0"
        assert d["baseline_version"] == "v1.0.0"
        assert d["summary_metrics"] == {"accuracy": 0.95}
        assert d["status"] == "draft"
        assert d["created_at"] == "2024-01-15T10:30:00"

    def test_from_dict(self):
        """Test deserialization from dict."""
        data = {
            "candidate_version": "v2.0.0",
            "baseline_version": "v1.0.0",
            "summary_metrics": {"accuracy": 0.95},
            "safety_checks": {},
            "rollback_plan": "",
            "required_approvers": [],
            "signatures": [],
            "created_at": "2024-01-15T10:30:00",
            "status": "draft",
        }
        packet = PromotionPacket.from_dict(data)
        assert packet.candidate_version == "v2.0.0"
        assert packet.summary_metrics == {"accuracy": 0.95}
        assert packet.status == PacketStatus.DRAFT

    def test_round_trip(self):
        """Test round-trip serialization."""
        now = datetime.utcnow()
        original = PromotionPacket(
            candidate_version="v2.0.0",
            baseline_version="v1.0.0",
            summary_metrics={"accuracy": 0.95, "precision": 0.90},
            safety_checks={"tests_pass": True},
            rollback_plan="Plan here",
            required_approvers=["admin"],
            created_at=now,
            status=PacketStatus.PENDING_APPROVAL,
        )
        d = original.to_dict()
        restored = PromotionPacket.from_dict(d)
        assert restored.candidate_version == original.candidate_version
        assert restored.summary_metrics == original.summary_metrics
        assert restored.status == original.status


class TestPacketGenerator:
    """Tests for PacketGenerator class."""

    def test_creation(self):
        """Test PacketGenerator creation."""
        gen = PacketGenerator()
        assert gen is not None

    def test_creation_with_custom_template(self):
        """Test PacketGenerator with custom rollback template."""
        template = "Custom rollback for {candidate_version}"
        gen = PacketGenerator(rollback_template=template)
        assert gen.rollback_template == template

    def test_generate_basic(self):
        """Test basic packet generation."""
        gen = PacketGenerator()
        eval_results = {
            "version": "v2.0.0",
            "metrics": {
                "accuracy": 0.95,
                "precision": 0.90,
            },
        }
        packet = gen.generate(
            evaluation_results=eval_results,
            baseline_version="v1.0.0",
        )
        assert packet.candidate_version == "v2.0.0"
        assert packet.baseline_version == "v1.0.0"
        assert packet.summary_metrics["accuracy"] == 0.95
        assert packet.summary_metrics["precision"] == 0.90

    def test_generate_with_safety_checks(self):
        """Test packet generation with safety checks."""
        gen = PacketGenerator()
        eval_results = {
            "version": "v2.0.0",
            "safety_checks": {
                "no_regression_on_critical_metrics": True,
                "passes_all_unit_tests": True,
            },
        }
        packet = gen.generate(
            evaluation_results=eval_results, baseline_version="v1.0.0"
        )
        assert packet.safety_checks["no_regression_on_critical_metrics"] is True
        assert packet.safety_checks["passes_all_unit_tests"] is True

    def test_generate_with_leaderboard(self):
        """Test packet generation with leaderboard data."""
        gen = PacketGenerator()
        eval_results = {"version": "v2.0.0"}
        leaderboard = {"rank": 1, "score": 0.95}
        packet = gen.generate(
            evaluation_results=eval_results,
            leaderboard=leaderboard,
            baseline_version="v1.0.0",
        )
        assert packet.candidate_version == "v2.0.0"

    def test_generate_with_required_approvers(self):
        """Test packet generation with required approvers."""
        gen = PacketGenerator()
        eval_results = {"version": "v2.0.0"}
        packet = gen.generate(
            evaluation_results=eval_results,
            baseline_version="v1.0.0",
            required_approvers=["admin", "lead"],
        )
        assert packet.required_approvers == ["admin", "lead"]

    def test_generate_rollback_plan_populated(self):
        """Test that rollback plan is populated."""
        gen = PacketGenerator()
        eval_results = {"version": "v2.0.0"}
        packet = gen.generate(
            evaluation_results=eval_results,
            baseline_version="v1.0.0",
        )
        assert packet.rollback_plan != ""
        assert "v2.0.0" in packet.rollback_plan
        assert "v1.0.0" in packet.rollback_plan

    def test_extract_metrics_from_nested_metrics(self):
        """Test metric extraction from nested metrics dict."""
        gen = PacketGenerator()
        eval_results = {
            "version": "v2.0.0",
            "metrics": {
                "accuracy": 0.95,
                "win_rate": 0.75,
                "sharpe": 1.5,
            },
        }
        metrics = gen._extract_metrics(eval_results)
        assert metrics["accuracy"] == 0.95
        assert metrics["win_rate"] == 0.75
        assert metrics["sharpe"] == 1.5

    def test_extract_metrics_from_root(self):
        """Test metric extraction from root level."""
        gen = PacketGenerator()
        eval_results = {
            "version": "v2.0.0",
            "accuracy": 0.95,
            "precision": 0.90,
        }
        metrics = gen._extract_metrics(eval_results)
        assert metrics["accuracy"] == 0.95
        assert metrics["precision"] == 0.90

    def test_extract_metrics_ignores_invalid(self):
        """Test that invalid metric values are ignored."""
        gen = PacketGenerator()
        eval_results = {
            "version": "v2.0.0",
            "metrics": {
                "accuracy": "invalid",
                "precision": 0.90,
            },
        }
        metrics = gen._extract_metrics(eval_results)
        assert "accuracy" not in metrics
        assert metrics["precision"] == 0.90

    def test_extract_safety_checks_from_safety_checks_key(self):
        """Test safety check extraction from safety_checks key."""
        gen = PacketGenerator()
        eval_results = {
            "version": "v2.0.0",
            "safety_checks": {
                "no_regression_on_critical_metrics": True,
            },
        }
        checks = gen._extract_safety_checks(eval_results)
        assert checks["no_regression_on_critical_metrics"] is True

    def test_extract_safety_checks_from_checks_key(self):
        """Test safety check extraction from checks key."""
        gen = PacketGenerator()
        eval_results = {
            "version": "v2.0.0",
            "checks": {
                "passes_all_unit_tests": True,
            },
        }
        checks = gen._extract_safety_checks(eval_results)
        assert checks["passes_all_unit_tests"] is True


class TestExportToMarkdown:
    """Tests for export_to_markdown function."""

    def test_export_creates_file(self, tmp_path):
        """Test that export creates a file."""
        packet = PromotionPacket(
            candidate_version="v2.0.0",
            baseline_version="v1.0.0",
        )
        filepath = tmp_path / "packet.md"
        export_to_markdown(packet, str(filepath))
        assert filepath.exists()

    def test_export_contains_version_info(self, tmp_path):
        """Test that export contains version information."""
        packet = PromotionPacket(
            candidate_version="v2.0.0",
            baseline_version="v1.0.0",
        )
        filepath = tmp_path / "packet.md"
        export_to_markdown(packet, str(filepath))
        content = filepath.read_text()
        assert "v2.0.0" in content
        assert "v1.0.0" in content

    def test_export_contains_metrics(self, tmp_path):
        """Test that export contains metrics."""
        packet = PromotionPacket(
            candidate_version="v2.0.0",
            baseline_version="v1.0.0",
            summary_metrics={"accuracy": 0.95, "precision": 0.90},
        )
        filepath = tmp_path / "packet.md"
        export_to_markdown(packet, str(filepath))
        content = filepath.read_text()
        assert "accuracy" in content.lower()
        assert "precision" in content.lower()

    def test_export_contains_safety_checks(self, tmp_path):
        """Test that export contains safety checks."""
        packet = PromotionPacket(
            candidate_version="v2.0.0",
            baseline_version="v1.0.0",
            safety_checks={"tests_pass": True, "lint_pass": False},
        )
        filepath = tmp_path / "packet.md"
        export_to_markdown(packet, str(filepath))
        content = filepath.read_text()
        assert "tests_pass" in content or "Tests Pass" in content

    def test_export_contains_rollback_plan(self, tmp_path):
        """Test that export contains rollback plan."""
        packet = PromotionPacket(
            candidate_version="v2.0.0",
            baseline_version="v1.0.0",
            rollback_plan="# Rollback\n\nSteps here",
        )
        filepath = tmp_path / "packet.md"
        export_to_markdown(packet, str(filepath))
        content = filepath.read_text()
        assert "Rollback" in content

    def test_export_contains_signatures(self, tmp_path):
        """Test that export contains signatures."""
        sig = ApprovalSignature(
            approver="admin",
            timestamp=datetime(2024, 1, 15, 10, 30, 0),
            status=ApprovalStatus.APPROVED,
        )
        packet = PromotionPacket(
            candidate_version="v2.0.0",
            baseline_version="v1.0.0",
            signatures=[sig],
        )
        filepath = tmp_path / "packet.md"
        export_to_markdown(packet, str(filepath))
        content = filepath.read_text()
        assert "admin" in content

    def test_export_creates_parent_directories(self, tmp_path):
        """Test that export creates parent directories."""
        packet = PromotionPacket(
            candidate_version="v2.0.0",
            baseline_version="v1.0.0",
        )
        filepath = tmp_path / "subdir" / "nested" / "packet.md"
        export_to_markdown(packet, str(filepath))
        assert filepath.exists()


class TestExportToJson:
    """Tests for export_to_json function."""

    def test_export_creates_file(self, tmp_path):
        """Test that export creates a file."""
        packet = PromotionPacket(
            candidate_version="v2.0.0",
            baseline_version="v1.0.0",
        )
        filepath = tmp_path / "packet.json"
        export_to_json(packet, str(filepath))
        assert filepath.exists()

    def test_export_valid_json(self, tmp_path):
        """Test that export creates valid JSON."""
        packet = PromotionPacket(
            candidate_version="v2.0.0",
            baseline_version="v1.0.0",
            summary_metrics={"accuracy": 0.95},
        )
        filepath = tmp_path / "packet.json"
        export_to_json(packet, str(filepath))
        content = filepath.read_text()
        data = json.loads(content)
        assert data["candidate_version"] == "v2.0.0"
        assert data["summary_metrics"]["accuracy"] == 0.95

    def test_export_round_trip(self, tmp_path):
        """Test that exported JSON can be reimported."""
        now = datetime.utcnow()
        original = PromotionPacket(
            candidate_version="v2.0.0",
            baseline_version="v1.0.0",
            summary_metrics={"accuracy": 0.95},
            created_at=now,
        )
        filepath = tmp_path / "packet.json"
        export_to_json(original, str(filepath))

        # Read back
        with open(filepath) as f:
            data = json.load(f)
        restored = PromotionPacket.from_dict(data)

        assert restored.candidate_version == original.candidate_version
        assert restored.summary_metrics == original.summary_metrics

    def test_export_creates_parent_directories(self, tmp_path):
        """Test that export creates parent directories."""
        packet = PromotionPacket(
            candidate_version="v2.0.0",
            baseline_version="v1.0.0",
        )
        filepath = tmp_path / "subdir" / "nested" / "packet.json"
        export_to_json(packet, str(filepath))
        assert filepath.exists()


class TestIsComplete:
    """Tests for is_complete function."""

    def test_complete_packet(self):
        """Test that a complete packet returns True."""
        packet = PromotionPacket(
            candidate_version="v2.0.0",
            baseline_version="v1.0.0",
            summary_metrics={"accuracy": 0.95},
            safety_checks={"tests_pass": True},
            rollback_plan="Plan here",
            required_approvers=["admin"],
        )
        assert is_complete(packet) is True

    def test_missing_candidate_version(self):
        """Test that missing candidate version makes packet incomplete."""
        packet = PromotionPacket(
            candidate_version="",
            baseline_version="v1.0.0",
            summary_metrics={"accuracy": 0.95},
            safety_checks={"tests_pass": True},
            rollback_plan="Plan",
            required_approvers=["admin"],
        )
        assert is_complete(packet) is False

    def test_unknown_candidate_version(self):
        """Test that 'unknown' candidate version makes packet incomplete."""
        packet = PromotionPacket(
            candidate_version="unknown",
            baseline_version="v1.0.0",
            summary_metrics={"accuracy": 0.95},
            safety_checks={"tests_pass": True},
            rollback_plan="Plan",
            required_approvers=["admin"],
        )
        assert is_complete(packet) is False

    def test_missing_baseline_version(self):
        """Test that missing baseline version makes packet incomplete."""
        packet = PromotionPacket(
            candidate_version="v2.0.0",
            baseline_version="",
            summary_metrics={"accuracy": 0.95},
            safety_checks={"tests_pass": True},
            rollback_plan="Plan",
            required_approvers=["admin"],
        )
        assert is_complete(packet) is False

    def test_missing_summary_metrics(self):
        """Test that empty summary metrics makes packet incomplete."""
        packet = PromotionPacket(
            candidate_version="v2.0.0",
            baseline_version="v1.0.0",
            summary_metrics={},
            safety_checks={"tests_pass": True},
            rollback_plan="Plan",
            required_approvers=["admin"],
        )
        assert is_complete(packet) is False

    def test_missing_safety_checks(self):
        """Test that empty safety checks makes packet incomplete."""
        packet = PromotionPacket(
            candidate_version="v2.0.0",
            baseline_version="v1.0.0",
            summary_metrics={"accuracy": 0.95},
            safety_checks={},
            rollback_plan="Plan",
            required_approvers=["admin"],
        )
        assert is_complete(packet) is False

    def test_missing_rollback_plan(self):
        """Test that empty rollback plan makes packet incomplete."""
        packet = PromotionPacket(
            candidate_version="v2.0.0",
            baseline_version="v1.0.0",
            summary_metrics={"accuracy": 0.95},
            safety_checks={"tests_pass": True},
            rollback_plan="",
            required_approvers=["admin"],
        )
        assert is_complete(packet) is False

    def test_missing_required_approvers(self):
        """Test that empty required approvers makes packet incomplete."""
        packet = PromotionPacket(
            candidate_version="v2.0.0",
            baseline_version="v1.0.0",
            summary_metrics={"accuracy": 0.95},
            safety_checks={"tests_pass": True},
            rollback_plan="Plan",
            required_approvers=[],
        )
        assert is_complete(packet) is False


class TestGetMissingFields:
    """Tests for get_missing_fields function."""

    def test_no_missing_fields(self):
        """Test that complete packet has no missing fields."""
        packet = PromotionPacket(
            candidate_version="v2.0.0",
            baseline_version="v1.0.0",
            summary_metrics={"accuracy": 0.95},
            safety_checks={"tests_pass": True},
            rollback_plan="Plan",
            required_approvers=["admin"],
        )
        missing = get_missing_fields(packet)
        assert missing == []

    def test_missing_candidate_version_reported(self):
        """Test that missing candidate version is reported."""
        packet = PromotionPacket(
            candidate_version="",
            baseline_version="v1.0.0",
            summary_metrics={"accuracy": 0.95},
            safety_checks={"tests_pass": True},
            rollback_plan="Plan",
            required_approvers=["admin"],
        )
        missing = get_missing_fields(packet)
        assert "candidate_version" in missing

    def test_missing_baseline_version_reported(self):
        """Test that missing baseline version is reported."""
        packet = PromotionPacket(
            candidate_version="v2.0.0",
            baseline_version="unknown",
            summary_metrics={"accuracy": 0.95},
            safety_checks={"tests_pass": True},
            rollback_plan="Plan",
            required_approvers=["admin"],
        )
        missing = get_missing_fields(packet)
        assert "baseline_version" in missing

    def test_missing_metrics_reported(self):
        """Test that empty metrics is reported."""
        packet = PromotionPacket(
            candidate_version="v2.0.0",
            baseline_version="v1.0.0",
            summary_metrics={},
            safety_checks={"tests_pass": True},
            rollback_plan="Plan",
            required_approvers=["admin"],
        )
        missing = get_missing_fields(packet)
        assert any("summary_metrics" in m for m in missing)

    def test_multiple_missing_fields(self):
        """Test that multiple missing fields are all reported."""
        packet = PromotionPacket(
            candidate_version="",
            baseline_version="unknown",
            summary_metrics={},
            safety_checks={},
            rollback_plan="",
            required_approvers=[],
        )
        missing = get_missing_fields(packet)
        assert len(missing) >= 5


class TestAddSignature:
    """Tests for add_signature function."""

    def test_add_signature_increases_count(self):
        """Test that adding signature increases signature count."""
        packet = PromotionPacket(
            candidate_version="v2.0.0",
            baseline_version="v1.0.0",
        )
        assert len(packet.signatures) == 0
        add_signature(packet, "admin", ApprovalStatus.PENDING)
        assert len(packet.signatures) == 1

    def test_add_signature_sets_approver(self):
        """Test that signature has correct approver."""
        packet = PromotionPacket(
            candidate_version="v2.0.0",
            baseline_version="v1.0.0",
        )
        add_signature(packet, "admin", ApprovalStatus.APPROVED)
        assert packet.signatures[0].approver == "admin"

    def test_add_signature_sets_status(self):
        """Test that signature has correct status."""
        packet = PromotionPacket(
            candidate_version="v2.0.0",
            baseline_version="v1.0.0",
        )
        add_signature(packet, "admin", ApprovalStatus.REJECTED)
        assert packet.signatures[0].status == ApprovalStatus.REJECTED

    def test_add_signature_sets_comments(self):
        """Test that signature has correct comments."""
        packet = PromotionPacket(
            candidate_version="v2.0.0",
            baseline_version="v1.0.0",
        )
        add_signature(packet, "admin", ApprovalStatus.APPROVED, "Great work!")
        assert packet.signatures[0].comments == "Great work!"

    def test_add_signature_sets_timestamp(self):
        """Test that signature has timestamp."""
        packet = PromotionPacket(
            candidate_version="v2.0.0",
            baseline_version="v1.0.0",
        )
        before = datetime.utcnow()
        add_signature(packet, "admin", ApprovalStatus.APPROVED)
        after = datetime.utcnow()
        assert before <= packet.signatures[0].timestamp <= after

    def test_add_signature_returns_packet(self):
        """Test that add_signature returns the packet."""
        packet = PromotionPacket(
            candidate_version="v2.0.0",
            baseline_version="v1.0.0",
        )
        result = add_signature(packet, "admin", ApprovalStatus.APPROVED)
        assert result is packet

    def test_add_signature_updates_status_to_pending(self):
        """Test that adding pending signature updates packet status."""
        packet = PromotionPacket(
            candidate_version="v2.0.0",
            baseline_version="v1.0.0",
            required_approvers=["admin"],
        )
        add_signature(packet, "admin", ApprovalStatus.PENDING)
        assert packet.status == PacketStatus.PENDING_APPROVAL

    def test_add_signature_updates_status_to_rejected(self):
        """Test that rejection updates packet status to rejected."""
        packet = PromotionPacket(
            candidate_version="v2.0.0",
            baseline_version="v1.0.0",
            required_approvers=["admin", "lead"],
        )
        add_signature(packet, "admin", ApprovalStatus.REJECTED)
        assert packet.status == PacketStatus.REJECTED

    def test_add_signature_updates_status_to_approved(self):
        """Test that all approvals updates packet status to approved."""
        packet = PromotionPacket(
            candidate_version="v2.0.0",
            baseline_version="v1.0.0",
            required_approvers=["admin"],
        )
        add_signature(packet, "admin", ApprovalStatus.APPROVED)
        assert packet.status == PacketStatus.APPROVED


class TestIsApproved:
    """Tests for is_approved function."""

    def test_no_required_approvers_and_status_approved(self):
        """Test approved when no required approvers and status is approved."""
        packet = PromotionPacket(
            candidate_version="v2.0.0",
            baseline_version="v1.0.0",
            required_approvers=[],
            status=PacketStatus.APPROVED,
        )
        assert is_approved(packet) is True

    def test_no_required_approvers_and_status_not_approved(self):
        """Test not approved when no required approvers but status not approved."""
        packet = PromotionPacket(
            candidate_version="v2.0.0",
            baseline_version="v1.0.0",
            required_approvers=[],
            status=PacketStatus.DRAFT,
        )
        assert is_approved(packet) is False

    def test_single_approver_approved(self):
        """Test approved when single required approver has approved."""
        packet = PromotionPacket(
            candidate_version="v2.0.0",
            baseline_version="v1.0.0",
            required_approvers=["admin"],
        )
        sig = ApprovalSignature(
            approver="admin",
            timestamp=datetime.utcnow(),
            status=ApprovalStatus.APPROVED,
        )
        packet.signatures.append(sig)
        assert is_approved(packet) is True

    def test_single_approver_pending(self):
        """Test not approved when single required approver is pending."""
        packet = PromotionPacket(
            candidate_version="v2.0.0",
            baseline_version="v1.0.0",
            required_approvers=["admin"],
        )
        sig = ApprovalSignature(
            approver="admin",
            timestamp=datetime.utcnow(),
            status=ApprovalStatus.PENDING,
        )
        packet.signatures.append(sig)
        assert is_approved(packet) is False

    def test_multiple_approvers_all_approved(self):
        """Test approved when all required approvers have approved."""
        packet = PromotionPacket(
            candidate_version="v2.0.0",
            baseline_version="v1.0.0",
            required_approvers=["admin", "lead"],
        )
        packet.signatures.append(
            ApprovalSignature(
                approver="admin",
                timestamp=datetime.utcnow(),
                status=ApprovalStatus.APPROVED,
            )
        )
        packet.signatures.append(
            ApprovalSignature(
                approver="lead",
                timestamp=datetime.utcnow(),
                status=ApprovalStatus.APPROVED,
            )
        )
        assert is_approved(packet) is True

    def test_multiple_approvers_partial(self):
        """Test not approved when only some required approvers have approved."""
        packet = PromotionPacket(
            candidate_version="v2.0.0",
            baseline_version="v1.0.0",
            required_approvers=["admin", "lead"],
        )
        packet.signatures.append(
            ApprovalSignature(
                approver="admin",
                timestamp=datetime.utcnow(),
                status=ApprovalStatus.APPROVED,
            )
        )
        assert is_approved(packet) is False

    def test_approver_not_in_required_list(self):
        """Test not approved when approver is not in required list."""
        packet = PromotionPacket(
            candidate_version="v2.0.0",
            baseline_version="v1.0.0",
            required_approvers=["admin"],
        )
        packet.signatures.append(
            ApprovalSignature(
                approver="other",
                timestamp=datetime.utcnow(),
                status=ApprovalStatus.APPROVED,
            )
        )
        assert is_approved(packet) is False

    def test_rejected_signature_not_approved(self):
        """Test not approved when signature is rejected."""
        packet = PromotionPacket(
            candidate_version="v2.0.0",
            baseline_version="v1.0.0",
            required_approvers=["admin"],
        )
        packet.signatures.append(
            ApprovalSignature(
                approver="admin",
                timestamp=datetime.utcnow(),
                status=ApprovalStatus.REJECTED,
            )
        )
        assert is_approved(packet) is False


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_approvers_list(self):
        """Test behavior with empty approvers list."""
        packet = PromotionPacket(
            candidate_version="v2.0.0",
            baseline_version="v1.0.0",
            required_approvers=[],
            status=PacketStatus.APPROVED,
        )
        assert is_approved(packet) is True
        assert is_complete(packet) is False  # Still incomplete due to other fields

    def test_partial_approval_with_rejection(self):
        """Test partial approval when one approver rejects."""
        packet = PromotionPacket(
            candidate_version="v2.0.0",
            baseline_version="v1.0.0",
            required_approvers=["admin", "lead"],
        )
        add_signature(packet, "admin", ApprovalStatus.APPROVED)
        add_signature(packet, "lead", ApprovalStatus.REJECTED)
        assert is_approved(packet) is False
        assert packet.status == PacketStatus.REJECTED

    def test_whitespace_rollback_plan(self):
        """Test that whitespace-only rollback plan is treated as missing."""
        packet = PromotionPacket(
            candidate_version="v2.0.0",
            baseline_version="v1.0.0",
            summary_metrics={"accuracy": 0.95},
            safety_checks={"tests_pass": True},
            rollback_plan="   \n\t  ",
            required_approvers=["admin"],
        )
        assert is_complete(packet) is False
        assert "rollback_plan" in get_missing_fields(packet)

    def test_signature_with_no_comments(self):
        """Test signature without comments."""
        sig = ApprovalSignature(
            approver="admin",
            timestamp=datetime.utcnow(),
            status=ApprovalStatus.APPROVED,
            comments=None,
        )
        d = sig.to_dict()
        assert d["comments"] is None
        restored = ApprovalSignature.from_dict(d)
        assert restored.comments is None

    def test_metrics_with_non_standard_values(self):
        """Test metrics with various numeric formats."""
        gen = PacketGenerator()
        eval_results = {
            "version": "v2.0.0",
            "metrics": {
                "accuracy": 0.95,
                "sharpe": 1.5,
                "max_drawdown": -0.25,
            },
        }
        packet = gen.generate(eval_results, baseline_version="v1.0.0")
        assert packet.summary_metrics["accuracy"] == 0.95
        assert packet.summary_metrics["sharpe"] == 1.5
        assert packet.summary_metrics["max_drawdown"] == -0.25

    def test_unknown_version_in_evaluation(self):
        """Test handling of unknown version in evaluation results."""
        gen = PacketGenerator()
        eval_results = {
            "version": "unknown",
        }
        packet = gen.generate(eval_results, baseline_version="v1.0.0")
        assert packet.candidate_version == "unknown"
        assert is_complete(packet) is False
