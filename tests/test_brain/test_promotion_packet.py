"""Tests for brain promotion packet (ST-CHISE-003).

Tests cover:
- Packet generation from evaluation results
- Safety check verification
- Rollback plan creation
- Approval workflow
- Export formats (Markdown and JSON)
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src.brain.batch_evaluator import (
    EvaluationMetrics,
    EvaluationResult,
    EvaluationStatus,
)
from src.brain.promotion_packet import (
    ApprovalRecord,
    PacketStatus,
    PromotionPacket,
    PromotionPacketGenerator,
    RollbackPlan,
    RollbackStep,
    SafetyCheck,
    SafetyCheckStatus,
)


class TestSafetyCheck:
    """Test SafetyCheck dataclass."""

    def test_creation(self):
        """Test safety check creation."""
        check = SafetyCheck(
            name="Test Check",
            description="A test safety check",
            status=SafetyCheckStatus.PASSED,
            details="All good",
        )
        assert check.name == "Test Check"
        assert check.status == SafetyCheckStatus.PASSED

    def test_to_dict(self):
        """Test conversion to dictionary."""
        check = SafetyCheck(
            name="Test Check",
            description="A test",
            status=SafetyCheckStatus.PASSED,
            checked_at=datetime.utcnow(),
        )
        data = check.to_dict()
        assert data["name"] == "Test Check"
        assert data["status"] == "passed"

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "name": "Test Check",
            "description": "A test",
            "status": "passed",
            "details": "OK",
            "checked_at": datetime.utcnow().isoformat(),
        }
        check = SafetyCheck.from_dict(data)
        assert check.name == "Test Check"
        assert check.status == SafetyCheckStatus.PASSED


class TestRollbackStep:
    """Test RollbackStep dataclass."""

    def test_creation(self):
        """Test rollback step creation."""
        step = RollbackStep(
            step_number=1,
            description="Stop signals",
            command="stop --all",
            verification_command="check --status",
            expected_result="stopped",
            estimated_time_seconds=30,
        )
        assert step.step_number == 1
        assert step.description == "Stop signals"

    def test_to_dict(self):
        """Test conversion to dictionary."""
        step = RollbackStep(
            step_number=1,
            description="Stop signals",
            command="stop",
            verification_command="check",
            expected_result="done",
            estimated_time_seconds=30,
            requires_confirmation=True,
        )
        data = step.to_dict()
        assert data["step_number"] == 1
        assert data["requires_confirmation"] is True


class TestRollbackPlan:
    """Test RollbackPlan dataclass."""

    def test_creation(self):
        """Test rollback plan creation."""
        plan = RollbackPlan(
            trigger_conditions=["ECE > 0.15"],
            steps=[
                RollbackStep(1, "Step 1", "cmd1", "verify1", "ok", 30),
                RollbackStep(2, "Step 2", "cmd2", "verify2", "ok", 60),
            ],
            tested_in_dev=True,
            tested_at=datetime.utcnow(),
        )
        assert len(plan.trigger_conditions) == 1
        assert plan.estimated_total_time_seconds == 90

    def test_to_dict(self):
        """Test conversion to dictionary."""
        plan = RollbackPlan(
            trigger_conditions=["Condition 1"],
            steps=[RollbackStep(1, "Step", "cmd", "verify", "ok", 30)],
        )
        data = plan.to_dict()
        assert len(data["trigger_conditions"]) == 1
        assert len(data["steps"]) == 1

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "trigger_conditions": ["Condition 1"],
            "steps": [
                {
                    "step_number": 1,
                    "description": "Step",
                    "command": "cmd",
                    "verification_command": "verify",
                    "expected_result": "ok",
                    "estimated_time_seconds": 30,
                    "requires_confirmation": False,
                }
            ],
            "estimated_total_time_seconds": 30,
            "tested_in_dev": True,
            "tested_at": datetime.utcnow().isoformat(),
        }
        plan = RollbackPlan.from_dict(data)
        assert len(plan.steps) == 1
        assert plan.tested_in_dev is True


class TestPromotionPacket:
    """Test PromotionPacket functionality."""

    @pytest.fixture
    def sample_evaluation_result(self):
        """Create a sample evaluation result."""
        return EvaluationResult(
            brain_version="v2.0.0",
            brain_name="Test Brain",
            status=EvaluationStatus.COMPLETED,
            metrics=EvaluationMetrics(
                accuracy=0.85,
                precision=0.80,
                recall=0.75,
                f1_score=0.77,
                win_rate=0.65,
                sharpe_ratio=1.2,
                max_drawdown=0.10,
            ),
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            duration_seconds=120.0,
        )

    @pytest.fixture
    def sample_packet(self, sample_evaluation_result):
        """Create a sample promotion packet."""
        return PromotionPacket(
            packet_id="PROMO-123",
            brain_version="v2.0.0",
            brain_name="Test Brain",
            created_at=datetime.utcnow(),
            evaluation_result=sample_evaluation_result,
            safety_checks=[
                SafetyCheck(
                    name="Accuracy Check",
                    description="Accuracy >= 70%",
                    status=SafetyCheckStatus.PASSED,
                    details="85% achieved",
                ),
            ],
            rollback_plan=RollbackPlan(
                trigger_conditions=["ECE > 0.15"],
                steps=[RollbackStep(1, "Stop", "stop", "check", "ok", 30)],
            ),
        )

    def test_creation(self, sample_evaluation_result):
        """Test packet creation."""
        packet = PromotionPacket(
            packet_id="",
            brain_version="v2.0.0",
            brain_name="Test Brain",
            created_at=datetime.utcnow(),
            evaluation_result=sample_evaluation_result,
        )
        assert packet.brain_version == "v2.0.0"
        assert packet.packet_id  # Auto-generated
        assert packet.expires_at  # Auto-set to 7 days

    def test_to_dict(self, sample_packet):
        """Test conversion to dictionary."""
        data = sample_packet.to_dict()
        assert data["brain_version"] == "v2.0.0"
        assert data["status"] == "draft"
        assert "evaluation_result" in data
        assert "safety_checks" in data

    def test_to_json(self, sample_packet):
        """Test JSON export."""
        json_str = sample_packet.to_json()
        data = json.loads(json_str)
        assert data["brain_version"] == "v2.0.0"

    def test_to_markdown(self, sample_packet):
        """Test Markdown export."""
        md = sample_packet.to_markdown()
        assert "# Brain Promotion Packet" in md
        assert "v2.0.0" in md
        assert "## Safety Checks" in md
        assert "## Rollback Plan" in md
        assert "## Human Approval" in md

    def test_verify_completeness_pass(self, sample_packet):
        """Test completeness check passes."""
        is_complete, missing = sample_packet.verify_completeness()
        assert is_complete is True
        assert missing == []

    def test_verify_completeness_fail_missing_evaluation(
        self, sample_evaluation_result
    ):
        """Test completeness check fails on incomplete evaluation."""
        sample_evaluation_result.status = EvaluationStatus.FAILED
        packet = PromotionPacket(
            packet_id="PROMO-123",
            brain_version="v2.0.0",
            brain_name="Test Brain",
            created_at=datetime.utcnow(),
            evaluation_result=sample_evaluation_result,
            safety_checks=[SafetyCheck("Test", "Test", SafetyCheckStatus.PASSED)],
            rollback_plan=RollbackPlan(
                steps=[RollbackStep(1, "Step", "cmd", "v", "ok", 30)]
            ),
        )
        is_complete, missing = packet.verify_completeness()
        assert is_complete is False
        assert any("evaluation" in m.lower() for m in missing)

    def test_verify_completeness_fail_missing_safety_checks(
        self, sample_evaluation_result
    ):
        """Test completeness check fails on missing safety checks."""
        packet = PromotionPacket(
            packet_id="PROMO-123",
            brain_version="v2.0.0",
            brain_name="Test Brain",
            created_at=datetime.utcnow(),
            evaluation_result=sample_evaluation_result,
            safety_checks=[],  # Missing
            rollback_plan=RollbackPlan(
                steps=[RollbackStep(1, "Step", "cmd", "v", "ok", 30)]
            ),
        )
        is_complete, missing = packet.verify_completeness()
        assert is_complete is False
        assert any("safety" in m.lower() for m in missing)

    def test_verify_completeness_fail_missing_rollback_steps(
        self, sample_evaluation_result
    ):
        """Test completeness check fails on missing rollback steps."""
        packet = PromotionPacket(
            packet_id="PROMO-123",
            brain_version="v2.0.0",
            brain_name="Test Brain",
            created_at=datetime.utcnow(),
            evaluation_result=sample_evaluation_result,
            safety_checks=[SafetyCheck("Test", "Test", SafetyCheckStatus.PASSED)],
            rollback_plan=RollbackPlan(steps=[]),  # Missing
        )
        is_complete, missing = packet.verify_completeness()
        assert is_complete is False
        assert any("rollback" in m.lower() for m in missing)

    def test_verify_completeness_fail_failed_safety_check(
        self, sample_evaluation_result
    ):
        """Test completeness check fails on failed safety check."""
        packet = PromotionPacket(
            packet_id="PROMO-123",
            brain_version="v2.0.0",
            brain_name="Test Brain",
            created_at=datetime.utcnow(),
            evaluation_result=sample_evaluation_result,
            safety_checks=[SafetyCheck("Test", "Test", SafetyCheckStatus.FAILED)],
            rollback_plan=RollbackPlan(
                steps=[RollbackStep(1, "Step", "cmd", "v", "ok", 30)]
            ),
        )
        is_complete, missing = packet.verify_completeness()
        assert is_complete is False
        assert any("failed" in m.lower() for m in missing)

    def test_approve(self, sample_packet):
        """Test approval workflow."""
        sample_packet.approve(
            approver_name="John Doe",
            approver_email="john@example.com",
            comments="Looks good!",
        )

        assert sample_packet.status == PacketStatus.APPROVED
        assert sample_packet.approval is not None
        assert sample_packet.approval.approver_name == "John Doe"
        assert sample_packet.approval.signature  # Auto-generated

    def test_approve_incomplete_packet_fails(self, sample_evaluation_result):
        """Test that approving incomplete packet fails."""
        packet = PromotionPacket(
            packet_id="PROMO-123",
            brain_version="v2.0.0",
            brain_name="Test Brain",
            created_at=datetime.utcnow(),
            evaluation_result=sample_evaluation_result,
            safety_checks=[],  # Missing
            rollback_plan=RollbackPlan(),
        )

        with pytest.raises(ValueError, match="Cannot approve incomplete"):
            packet.approve("John Doe", "john@example.com")

    def test_reject(self, sample_packet):
        """Test rejection."""
        sample_packet.reject("Failed safety checks")
        assert sample_packet.status == PacketStatus.REJECTED

    def test_is_expired(self, sample_evaluation_result):
        """Test expiration check."""
        packet = PromotionPacket(
            packet_id="PROMO-123",
            brain_version="v2.0.0",
            brain_name="Test Brain",
            created_at=datetime.utcnow(),
            evaluation_result=sample_evaluation_result,
            expires_at=datetime.utcnow() - timedelta(days=1),  # Expired
        )
        assert packet.is_expired() is True

    def test_is_not_expired(self, sample_evaluation_result):
        """Test non-expired packet."""
        packet = PromotionPacket(
            packet_id="PROMO-123",
            brain_version="v2.0.0",
            brain_name="Test Brain",
            created_at=datetime.utcnow(),
            evaluation_result=sample_evaluation_result,
            expires_at=datetime.utcnow() + timedelta(days=7),
        )
        assert packet.is_expired() is False

    def test_save_and_load(self, sample_packet, tmp_path):
        """Test saving and loading packet."""
        sample_packet.save(tmp_path)

        # Check both files created
        json_file = tmp_path / f"{sample_packet.packet_id}.json"
        md_file = tmp_path / f"{sample_packet.packet_id}.md"

        assert json_file.exists()
        assert md_file.exists()

        # Load and verify
        loaded = PromotionPacket.load(sample_packet.packet_id, tmp_path)
        assert loaded is not None
        assert loaded.brain_version == sample_packet.brain_version

    def test_load_nonexistent(self, tmp_path):
        """Test loading non-existent packet."""
        loaded = PromotionPacket.load("NONEXISTENT", tmp_path)
        assert loaded is None

    def test_from_dict(self, sample_evaluation_result):
        """Test creation from dictionary."""
        packet = PromotionPacket(
            packet_id="PROMO-123",
            brain_version="v2.0.0",
            brain_name="Test Brain",
            created_at=datetime.utcnow(),
            evaluation_result=sample_evaluation_result,
            safety_checks=[SafetyCheck("Test", "Test", SafetyCheckStatus.PASSED)],
            rollback_plan=RollbackPlan(
                steps=[RollbackStep(1, "Step", "cmd", "v", "ok", 30)]
            ),
        )

        data = packet.to_dict()
        loaded = PromotionPacket.from_dict(data)

        assert loaded.brain_version == "v2.0.0"
        assert len(loaded.safety_checks) == 1


class TestPromotionPacketGenerator:
    """Test PromotionPacketGenerator."""

    @pytest.fixture
    def generator(self, tmp_path):
        """Create packet generator."""
        return PromotionPacketGenerator(packets_dir=tmp_path)

    @pytest.fixture
    def sample_evaluation_result(self):
        """Create sample evaluation result."""
        return EvaluationResult(
            brain_version="v2.0.0",
            brain_name="Test Brain",
            status=EvaluationStatus.COMPLETED,
            metrics=EvaluationMetrics(
                accuracy=0.85,
                precision=0.80,
                recall=0.75,
                f1_score=0.77,
                win_rate=0.65,
                sharpe_ratio=1.2,
                max_drawdown=0.10,
            ),
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            duration_seconds=120.0,
        )

    def test_generate_packet(self, generator, sample_evaluation_result):
        """Test packet generation."""
        packet = generator.generate_packet(sample_evaluation_result)

        assert packet.brain_version == "v2.0.0"
        assert packet.status == PacketStatus.PENDING_APPROVAL
        assert len(packet.safety_checks) > 0
        assert len(packet.rollback_plan.steps) > 0
        assert len(packet.rollback_plan.trigger_conditions) > 0

    def test_generate_packet_with_baseline(self, generator, sample_evaluation_result):
        """Test packet generation with baseline comparison."""
        baseline = EvaluationResult(
            brain_version="v1.0.0",
            brain_name="Baseline",
            status=EvaluationStatus.COMPLETED,
            metrics=EvaluationMetrics(
                accuracy=0.80,
                f1_score=0.75,
                win_rate=0.60,
            ),
            started_at=datetime.utcnow(),
        )

        packet = generator.generate_packet(
            sample_evaluation_result,
            comparison_baseline=baseline,
        )

        assert packet.comparison_baseline == "v1.0.0"
        assert "accuracy" in packet.improvement_summary
        assert abs(packet.improvement_summary["accuracy"] - 0.05) < 0.001  # 0.85 - 0.80

    def test_default_safety_checks(self, generator, sample_evaluation_result):
        """Test default safety checks are created."""
        packet = generator.generate_packet(sample_evaluation_result)

        check_names = [sc.name for sc in packet.safety_checks]
        assert "Minimum Accuracy Threshold" in check_names
        assert "Minimum Win Rate" in check_names
        assert "Maximum Drawdown" in check_names
        assert "Evaluation Completion" in check_names
        assert "Sharpe Ratio" in check_names

    def test_default_rollback_plan(self, generator, sample_evaluation_result):
        """Test default rollback plan is created."""
        packet = generator.generate_packet(sample_evaluation_result)

        plan = packet.rollback_plan
        assert len(plan.trigger_conditions) > 0
        assert len(plan.steps) > 0
        assert plan.estimated_total_time_seconds > 0

        # Check for specific trigger conditions
        assert any("ECE" in tc for tc in plan.trigger_conditions)
        assert any("safety" in tc.lower() for tc in plan.trigger_conditions)

    def test_default_safety_checks_pass(self, generator, sample_evaluation_result):
        """Test that default safety checks pass with good metrics."""
        packet = generator.generate_packet(sample_evaluation_result)

        for check in packet.safety_checks:
            assert check.status == SafetyCheckStatus.PASSED

    def test_default_safety_checks_fail(self, generator):
        """Test that default safety checks fail with poor metrics."""
        poor_result = EvaluationResult(
            brain_version="v2.0.0",
            brain_name="Poor Brain",
            status=EvaluationStatus.COMPLETED,
            metrics=EvaluationMetrics(
                accuracy=0.60,  # Below 70%
                win_rate=0.50,  # Below 55%
                max_drawdown=0.20,  # Above 15%
                sharpe_ratio=0.8,  # Below 1.0
            ),
            started_at=datetime.utcnow(),
        )

        packet = generator.generate_packet(poor_result)

        failed_checks = [
            sc for sc in packet.safety_checks if sc.status == SafetyCheckStatus.FAILED
        ]
        assert len(failed_checks) > 0
