"""Tests for canary auto-evaluation system."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from execution.canary.gate_evaluator import GateEvaluator
from execution.canary.models import (
    CanaryDeployment,
    CanaryMetrics,
    CanaryStatus,
    GateCriteria,
)
from execution.canary.monitor import CanaryMonitor
from execution.canary.promotion import PromotionPacket, PromotionPacketGenerator


class TestPassFailSummaryGeneration:
    """Tests for pass/fail summary generation."""

    def test_generate_pass_fail_summary_all_pass(self):
        """Test summary when all gates pass."""
        evaluator = GateEvaluator()

        # Create a canary that will pass all gates
        canary = CanaryDeployment(
            canary_id="test-001",
            strategy_id="strategy-001",
            status=CanaryStatus.RUNNING,
            start_time=int(datetime.now().timestamp())
            - (8 * 24 * 60 * 60),  # 8 days ago
            criteria=GateCriteria(duration_days=7, min_trades=5),
        )
        # Set metrics that will pass
        canary.metrics = CanaryMetrics(
            total_trades=10,
            winning_trades=6,
            losing_trades=4,
            max_drawdown_pct=3.0,  # Below 5% threshold
        )

        summary = evaluator.generate_pass_fail_summary(canary)

        assert summary["status"] == "PASS"
        assert summary["canary_id"] == "test-001"
        assert summary["strategy_id"] == "strategy-001"
        assert summary["gate_summary"]["pass"] == 3
        assert summary["gate_summary"]["fail"] == 0
        assert summary["gate_summary"]["pending"] == 0
        assert summary["can_promote"] is True
        assert summary["should_rollback"] is False

    def test_generate_pass_fail_summary_with_failures(self):
        """Test summary when gates fail."""
        evaluator = GateEvaluator()

        canary = CanaryDeployment(
            canary_id="test-002",
            strategy_id="strategy-002",
            status=CanaryStatus.RUNNING,
            start_time=int(datetime.now().timestamp()),  # Just started
            criteria=GateCriteria(duration_days=7, min_trades=5),
        )
        # Set metrics that will fail
        canary.metrics = CanaryMetrics(
            total_trades=10,
            winning_trades=3,  # 30% win rate, below 55%
            losing_trades=7,
            max_drawdown_pct=6.0,  # Above 5% threshold
        )

        summary = evaluator.generate_pass_fail_summary(canary)

        assert summary["status"] == "FAIL"
        assert summary["gate_summary"]["pass"] == 0
        assert summary["gate_summary"]["fail"] >= 1
        assert summary["can_promote"] is False
        assert summary["should_rollback"] is True
        assert len(summary["reasons"]) > 0

    def test_generate_pass_fail_summary_pending(self):
        """Test summary when gates are pending."""
        evaluator = GateEvaluator()

        canary = CanaryDeployment(
            canary_id="test-003",
            strategy_id="strategy-003",
            status=CanaryStatus.RUNNING,
            start_time=int(datetime.now().timestamp())
            - (3 * 24 * 60 * 60),  # 3 days ago
            criteria=GateCriteria(duration_days=7, min_trades=5),
        )
        # Set metrics that will be pending (not enough duration)
        canary.metrics = CanaryMetrics(
            total_trades=3,  # Below min_trades
            winning_trades=2,
            losing_trades=1,
            max_drawdown_pct=2.0,
        )

        summary = evaluator.generate_pass_fail_summary(canary)

        assert summary["status"] == "PENDING"
        assert summary["gate_summary"]["pending"] >= 1
        assert summary["can_promote"] is False
        assert summary["should_rollback"] is False

    def test_generate_pass_fail_summary_has_gate_details(self):
        """Test that summary includes gate details."""
        evaluator = GateEvaluator()

        canary = CanaryDeployment(
            canary_id="test-004",
            strategy_id="strategy-004",
            status=CanaryStatus.RUNNING,
            start_time=int(datetime.now().timestamp()),
        )
        canary.metrics = CanaryMetrics(total_trades=0)

        summary = evaluator.generate_pass_fail_summary(canary)

        assert "gate_details" in summary
        assert len(summary["gate_details"]) == 3
        for gate in summary["gate_details"]:
            assert "gate_name" in gate
            assert "result" in gate
            assert "message" in gate


class TestShouldAutoPromote:
    """Tests for should_auto_promote method."""

    def test_should_auto_promote_returns_true_when_all_pass(self):
        """Test auto-promote returns True when all gates pass."""
        evaluator = GateEvaluator()

        canary = CanaryDeployment(
            canary_id="test-001",
            strategy_id="strategy-001",
            status=CanaryStatus.RUNNING,
            start_time=int(datetime.now().timestamp()) - (8 * 24 * 60 * 60),
            criteria=GateCriteria(duration_days=7, min_trades=5),
        )
        canary.metrics = CanaryMetrics(
            total_trades=10,
            winning_trades=6,
            losing_trades=4,
            max_drawdown_pct=3.0,
        )

        should_promote, summary = evaluator.should_auto_promote(canary)

        assert should_promote is True
        assert summary["status"] == "PASS"
        assert summary["gate_summary"]["pass"] == summary["gate_summary"]["total"]

    def test_should_auto_promote_returns_false_when_any_pending(self):
        """Test auto-promote returns False when any gate is pending."""
        evaluator = GateEvaluator()

        canary = CanaryDeployment(
            canary_id="test-002",
            strategy_id="strategy-002",
            status=CanaryStatus.RUNNING,
            start_time=int(datetime.now().timestamp()),  # Just started
        )
        canary.metrics = CanaryMetrics(total_trades=0)

        should_promote, summary = evaluator.should_auto_promote(canary)

        assert should_promote is False
        assert summary["status"] == "PENDING"

    def test_should_auto_promote_returns_false_when_any_fail(self):
        """Test auto-promote returns False when any gate fails."""
        evaluator = GateEvaluator()

        canary = CanaryDeployment(
            canary_id="test-003",
            strategy_id="strategy-003",
            status=CanaryStatus.RUNNING,
            start_time=int(datetime.now().timestamp()) - (8 * 24 * 60 * 60),
            criteria=GateCriteria(duration_days=7, min_trades=5),
        )
        canary.metrics = CanaryMetrics(
            total_trades=10,
            winning_trades=3,
            losing_trades=7,
            max_drawdown_pct=6.0,  # Exceeds threshold
        )

        should_promote, summary = evaluator.should_auto_promote(canary)

        assert should_promote is False
        assert summary["status"] == "FAIL"


class TestArtifactGeneration:
    """Tests for evaluation artifact generation."""

    def test_generate_evaluation_artifact_creates_files(self):
        """Test that artifacts are created on disk."""
        evaluator = GateEvaluator()

        canary = CanaryDeployment(
            canary_id="test-001",
            strategy_id="strategy-001",
            status=CanaryStatus.RUNNING,
            start_time=int(datetime.now().timestamp()),
        )
        canary.metrics = CanaryMetrics(total_trades=0)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            artifacts = evaluator.generate_evaluation_artifact(canary, output_dir)

            # Check that files were created
            assert artifacts["json"].exists()
            assert artifacts["markdown"].exists()

            # Check JSON structure
            json_data = json.loads(artifacts["json"].read_text())
            assert "evaluation" in json_data
            assert "pass_fail_summary" in json_data
            assert json_data["evaluation"]["canary_id"] == "test-001"

            # Check markdown content
            md_content = artifacts["markdown"].read_text()
            assert "# Canary Evaluation Summary" in md_content
            assert "test-001" in md_content

    def test_generate_evaluation_artifact_uses_default_path(self):
        """Test that default path is used when not specified."""
        evaluator = GateEvaluator()

        canary = CanaryDeployment(
            canary_id="test-artifact",
            strategy_id="strategy-001",
        )
        canary.metrics = CanaryMetrics(total_trades=0)

        with tempfile.TemporaryDirectory():
            with patch.object(Path, "mkdir", lambda *args, **kwargs: None):
                with patch.object(Path, "write_text"):
                    artifacts = evaluator.generate_evaluation_artifact(canary)

                    # Check default path structure
                    assert "reports/canary/test-artifact/evaluations" in str(
                        artifacts["json"]
                    )


class TestAutoEvaluationScheduling:
    """Tests for auto-evaluation scheduling."""

    def test_schedule_auto_evaluation_creates_config(self):
        """Test that schedule config is created."""
        monitor = CanaryMonitor()

        config = monitor.schedule_auto_evaluation(cron_interval_minutes=10)

        assert config["interval_minutes"] == 10
        assert config["enabled"] is True
        assert "scheduled_at" in config
        assert "next_evaluation_at" in config

    def test_schedule_auto_evaluation_with_custom_interval(self):
        """Test schedule with custom interval."""
        monitor = CanaryMonitor()

        config = monitor.schedule_auto_evaluation(cron_interval_minutes=30)

        assert config["interval_minutes"] == 30
        next_eval = config["next_evaluation_at"]
        scheduled = config["scheduled_at"]
        assert next_eval == scheduled + (30 * 60)

    @pytest.mark.asyncio
    async def test_run_auto_evaluation_processes_active_canaries(self):
        """Test that auto-evaluation processes active canaries."""
        monitor = CanaryMonitor()

        # Add active canaries
        canary1 = CanaryDeployment(
            canary_id="test-active-1",
            strategy_id="strategy-1",
            status=CanaryStatus.RUNNING,
            start_time=int(datetime.now().timestamp()),
        )
        canary1.metrics = CanaryMetrics(total_trades=0)
        monitor.register_canary(canary1)

        canary2 = CanaryDeployment(
            canary_id="test-active-2",
            strategy_id="strategy-2",
            status=CanaryStatus.PENDING,
            start_time=int(datetime.now().timestamp()),
        )
        canary2.metrics = CanaryMetrics(total_trades=0)
        monitor.register_canary(canary2)

        # Add completed canary (should not be evaluated)
        canary3 = CanaryDeployment(
            canary_id="test-completed",
            strategy_id="strategy-3",
            status=CanaryStatus.PASSED,
        )
        monitor.register_canary(canary3)

        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir)
            results = await monitor.run_auto_evaluation(storage_path=storage_path)

            assert len(results) == 2  # Only active canaries
            assert all(
                r["canary_id"] in ["test-active-1", "test-active-2"] for r in results
            )

    @pytest.mark.asyncio
    async def test_run_auto_evaluation_handles_no_active_canaries(self):
        """Test behavior when no active canaries exist."""
        monitor = CanaryMonitor()

        results = await monitor.run_auto_evaluation()

        assert results == []

    @pytest.mark.asyncio
    async def test_run_auto_evaluation_updates_canary_status(self):
        """Test that evaluation updates canary status."""
        monitor = CanaryMonitor()

        canary = CanaryDeployment(
            canary_id="test-pass",
            strategy_id="strategy-1",
            status=CanaryStatus.RUNNING,
            start_time=int(datetime.now().timestamp()) - (8 * 24 * 60 * 60),
            criteria=GateCriteria(duration_days=7, min_trades=5),
        )
        canary.metrics = CanaryMetrics(
            total_trades=10,
            winning_trades=6,
            losing_trades=4,
            max_drawdown_pct=3.0,
        )
        monitor.register_canary(canary)

        await monitor.run_auto_evaluation()

        assert canary.status == CanaryStatus.PASSED


class TestAlertOnStatusChange:
    """Tests for status change alerting."""

    @pytest.mark.asyncio
    async def test_alert_on_status_change_triggers_on_transition(self):
        """Test alert is triggered on PENDING -> PASS transition."""
        monitor = CanaryMonitor()

        canary = CanaryDeployment(
            canary_id="test-001",
            strategy_id="strategy-001",
            status=CanaryStatus.PASSED,
        )

        evaluation = {
            "previous_status": "running",
            "status": "PASS",
            "can_promote": True,
            "should_rollback": False,
            "reasons": [],
            "timestamp": int(datetime.now().timestamp()),
        }

        alert = await monitor.alert_on_status_change(canary, evaluation)

        assert alert is not None
        assert alert["alert_type"] == "canary_status_change"
        assert alert["canary_id"] == "test-001"
        assert alert["previous_status"] == "running"
        assert alert["current_status"] == "PASS"

    @pytest.mark.asyncio
    async def test_alert_on_status_change_no_alert_on_no_change(self):
        """Test no alert when status doesn't change."""
        monitor = CanaryMonitor()

        canary = CanaryDeployment(
            canary_id="test-001",
            strategy_id="strategy-001",
            status=CanaryStatus.RUNNING,
        )

        evaluation = {
            "previous_status": "running",
            "status": "PENDING",
            "can_promote": False,
            "should_rollback": False,
            "reasons": ["Duration pending"],
            "timestamp": int(datetime.now().timestamp()),
        }

        alert = await monitor.alert_on_status_change(canary, evaluation)

        assert alert is None

    @pytest.mark.asyncio
    async def test_alert_on_status_change_includes_reasons(self):
        """Test alert includes failure reasons."""
        monitor = CanaryMonitor()

        canary = CanaryDeployment(
            canary_id="test-001",
            strategy_id="strategy-001",
            status=CanaryStatus.FAILED,
        )

        evaluation = {
            "previous_status": "running",
            "status": "FAIL",
            "can_promote": False,
            "should_rollback": True,
            "reasons": ["Drawdown exceeded threshold"],
            "timestamp": int(datetime.now().timestamp()),
        }

        alert = await monitor.alert_on_status_change(canary, evaluation)

        assert alert is not None
        assert "Drawdown exceeded threshold" in alert["reasons"]
        assert alert["should_rollback"] is True


class TestPromotionPacketGeneration:
    """Tests for auto-promotion packet generation."""

    def test_generate_auto_promotion_packet_returns_none_if_not_ready(self):
        """Test that None is returned when canary is not ready."""
        generator = PromotionPacketGenerator()

        canary = CanaryDeployment(
            canary_id="test-001",
            strategy_id="strategy-001",
            status=CanaryStatus.RUNNING,
            start_time=int(datetime.now().timestamp()),  # Not enough duration
        )
        canary.metrics = CanaryMetrics(total_trades=0)

        packet = generator.generate_auto_promotion_packet(canary, "packet-001")

        assert packet is None

    def test_generate_auto_promotion_packet_creates_packet_when_ready(self):
        """Test packet is created when canary passes all gates."""
        generator = PromotionPacketGenerator()

        canary = CanaryDeployment(
            canary_id="test-001",
            strategy_id="strategy-001",
            status=CanaryStatus.PASSED,
            start_time=int(datetime.now().timestamp()) - (8 * 24 * 60 * 60),
            criteria=GateCriteria(duration_days=7, min_trades=5),
        )
        canary.metrics = CanaryMetrics(
            total_trades=10,
            winning_trades=6,
            losing_trades=4,
            max_drawdown_pct=3.0,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            packet = generator.generate_auto_promotion_packet(
                canary, "packet-001", output_dir=output_dir
            )

            assert packet is not None
            assert packet.packet_id == "packet-001"
            assert packet.canary_id == "test-001"
            assert packet.strategy_id == "strategy-001"
            assert packet.metadata.get("auto_generated") is True

            # Check files were created
            assert (output_dir / "packet-001.json").exists()
            assert (output_dir / "packet-001.md").exists()

    def test_generate_auto_promotion_packet_includes_summary(self):
        """Test packet metadata includes evaluation summary."""
        generator = PromotionPacketGenerator()

        canary = CanaryDeployment(
            canary_id="test-001",
            strategy_id="strategy-001",
            status=CanaryStatus.PASSED,
            start_time=int(datetime.now().timestamp()) - (8 * 24 * 60 * 60),
            criteria=GateCriteria(duration_days=7, min_trades=5),
        )
        canary.metrics = CanaryMetrics(
            total_trades=10,
            winning_trades=6,
            losing_trades=4,
            max_drawdown_pct=3.0,
        )

        packet = generator.generate_auto_promotion_packet(canary, "packet-001")

        assert packet is not None
        assert "evaluation_summary" in packet.metadata
        assert packet.metadata["generated_by"] == "auto_promotion_system"


class TestQueueForHumanApproval:
    """Tests for queuing packets for human approval."""

    def test_queue_for_human_approval_updates_status(self):
        """Test that packet status is updated to pending_approval."""
        generator = PromotionPacketGenerator()

        packet = PromotionPacket(
            packet_id="packet-001",
            canary_id="test-001",
            strategy_id="strategy-001",
            champion_strategy_id="champion-001",
            status="pending",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir)
            result = generator.queue_for_human_approval(packet, storage_path)

            assert result["status"] == "pending_approval"
            assert packet.status == "pending_approval"
            assert "queued_at" in packet.metadata

    def test_queue_for_human_approval_saves_to_disk(self):
        """Test that queued packet is saved to disk."""
        generator = PromotionPacketGenerator()

        packet = PromotionPacket(
            packet_id="packet-001",
            canary_id="test-001",
            strategy_id="strategy-001",
            champion_strategy_id="champion-001",
            status="pending",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir)
            result = generator.queue_for_human_approval(packet, storage_path)

            queued_path = Path(result["queued_path"])
            assert queued_path.exists()

            data = json.loads(queued_path.read_text())
            assert data["queue_status"] == "pending_approval"
            assert data["packet"]["packet_id"] == "packet-001"

    def test_queue_for_human_approval_returns_queue_info(self):
        """Test that queue info is returned."""
        generator = PromotionPacketGenerator()

        packet = PromotionPacket(
            packet_id="packet-001",
            canary_id="test-001",
            strategy_id="strategy-001",
            champion_strategy_id="champion-001",
            status="pending",
        )

        result = generator.queue_for_human_approval(packet)

        assert result["packet_id"] == "packet-001"
        assert result["canary_id"] == "test-001"
        assert result["strategy_id"] == "strategy-001"
        assert result["queued_at"] is not None


class TestIntegration:
    """Integration tests for the complete auto-evaluation flow."""

    @pytest.mark.asyncio
    async def test_full_auto_evaluation_flow(self):
        """Test complete flow from evaluation to packet generation."""
        # Setup
        evaluator = GateEvaluator()
        monitor = CanaryMonitor()
        generator = PromotionPacketGenerator(evaluator)

        # Create passing canary
        canary = CanaryDeployment(
            canary_id="integration-test",
            strategy_id="strategy-001",
            status=CanaryStatus.RUNNING,
            start_time=int(datetime.now().timestamp()) - (8 * 24 * 60 * 60),
            criteria=GateCriteria(duration_days=7, min_trades=5),
        )
        canary.metrics = CanaryMetrics(
            total_trades=10,
            winning_trades=6,
            losing_trades=4,
            max_drawdown_pct=3.0,
        )
        monitor.register_canary(canary)

        with tempfile.TemporaryDirectory() as tmpdir:
            reports_dir = Path(tmpdir)

            # Step 1: Run auto-evaluation
            results = await monitor.run_auto_evaluation(storage_path=reports_dir)

            assert len(results) == 1
            assert results[0]["status"] == "PASS"
            assert canary.status == CanaryStatus.PASSED

            # Step 2: Generate promotion packet
            packet = generator.generate_auto_promotion_packet(
                canary, "packet-001", output_dir=reports_dir / "promotion_packets"
            )

            assert packet is not None

            # Step 3: Queue for approval
            queue_result = generator.queue_for_human_approval(
                packet, storage_path=reports_dir / "promotion_packets"
            )

            assert queue_result["status"] == "pending_approval"

    def test_evaluation_artifact_format(self):
        """Test that evaluation artifact has correct format."""
        evaluator = GateEvaluator()

        canary = CanaryDeployment(
            canary_id="format-test",
            strategy_id="strategy-001",
            status=CanaryStatus.RUNNING,
            start_time=int(datetime.now().timestamp()),
        )
        canary.metrics = CanaryMetrics(total_trades=0)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            artifacts = evaluator.generate_evaluation_artifact(canary, output_dir)

            # Load and verify JSON structure
            json_data = json.loads(artifacts["json"].read_text())

            # Check top-level structure
            assert "evaluation" in json_data
            assert "pass_fail_summary" in json_data
            assert "generated_at" in json_data

            # Check evaluation structure
            eval_data = json_data["evaluation"]
            assert "canary_id" in eval_data
            assert "strategy_id" in eval_data
            assert "status" in eval_data
            assert "evaluated_status" in eval_data
            assert "metrics" in eval_data
            assert "gate_checks" in eval_data
            assert "can_promote" in eval_data
            assert "should_rollback" in eval_data
            assert "timestamp" in eval_data

            # Check pass/fail summary structure
            summary = json_data["pass_fail_summary"]
            assert "status" in summary
            assert "gate_summary" in summary
            assert "pass" in summary["gate_summary"]
            assert "fail" in summary["gate_summary"]
            assert "pending" in summary["gate_summary"]
            assert "total" in summary["gate_summary"]
            assert "reasons" in summary
            assert "gate_details" in summary
