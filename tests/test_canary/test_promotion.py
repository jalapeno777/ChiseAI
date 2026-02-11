"""Tests for promotion packet generator."""

from execution.canary.gate_evaluator import GateEvaluator
from execution.canary.models import CanaryStatus, GateCriteria, create_canary_deployment
from execution.canary.promotion import (
    PromotionEvidence,
    PromotionPacket,
    PromotionPacketGenerator,
    create_promotion_packet_generator,
)


class TestPromotionEvidence:
    """Test PromotionEvidence class."""

    def test_to_dict(self):
        """Test serialization to dict."""
        evidence = PromotionEvidence(
            canary_duration_days=7.5,
            total_trades=25,
            win_rate_pct=60.0,
            max_drawdown_pct=3.5,
            realized_pnl=500.0,
            sharpe_ratio=1.5,
            gate_check_summary={"all_gates_passed": True},
        )

        data = evidence.to_dict()
        assert data["canary_duration_days"] == 7.5
        assert data["total_trades"] == 25
        assert data["win_rate_pct"] == 60.0
        assert data["max_drawdown_pct"] == 3.5
        assert data["realized_pnl"] == 500.0
        assert data["sharpe_ratio"] == 1.5
        assert data["gate_check_summary"]["all_gates_passed"] is True


class TestPromotionPacket:
    """Test PromotionPacket class."""

    def test_initial_status(self):
        """Test initial packet status."""
        packet = PromotionPacket(
            packet_id="packet-001",
            canary_id="canary-001",
            strategy_id="strategy-v2",
            champion_strategy_id="strategy-v1",
        )

        assert packet.status == "pending"
        assert packet.approved_by is None
        assert packet.approved_at is None

    def test_approve(self):
        """Test approving a packet."""
        packet = PromotionPacket(
            packet_id="packet-001",
            canary_id="canary-001",
            strategy_id="strategy-v2",
            champion_strategy_id="strategy-v1",
        )

        packet.approve("user@example.com")

        assert packet.status == "approved"
        assert packet.approved_by == "user@example.com"
        assert packet.approved_at is not None

    def test_reject(self):
        """Test rejecting a packet."""
        packet = PromotionPacket(
            packet_id="packet-001",
            canary_id="canary-001",
            strategy_id="strategy-v2",
            champion_strategy_id="strategy-v1",
        )

        packet.reject("Insufficient evidence")

        assert packet.status == "rejected"
        assert packet.metadata["rejection_reason"] == "Insufficient evidence"

    def test_to_dict(self):
        """Test serialization to dict."""
        packet = PromotionPacket(
            packet_id="packet-001",
            canary_id="canary-001",
            strategy_id="strategy-v2",
            champion_strategy_id="strategy-v1",
            status="pending",
        )

        data = packet.to_dict()
        assert data["packet_id"] == "packet-001"
        assert data["canary_id"] == "canary-001"
        assert data["strategy_id"] == "strategy-v2"
        assert data["champion_strategy_id"] == "strategy-v1"
        assert data["status"] == "pending"


class TestPromotionPacketGenerator:
    """Test PromotionPacketGenerator class."""

    def test_init_default_evaluator(self):
        """Test initialization with default evaluator."""
        generator = PromotionPacketGenerator()
        assert isinstance(generator.gate_evaluator, GateEvaluator)

    def test_init_custom_evaluator(self):
        """Test initialization with custom evaluator."""
        criteria = GateCriteria(max_drawdown_pct=3.0)
        evaluator = GateEvaluator(criteria=criteria)
        generator = PromotionPacketGenerator(gate_evaluator=evaluator)
        assert generator.gate_evaluator is evaluator

    def test_generate_packet_not_ready(self):
        """Test generating packet when canary not ready."""
        generator = PromotionPacketGenerator()
        canary = create_canary_deployment(
            canary_id="canary-001",
            strategy_id="strategy-v2",
        )
        canary.start(initial_equity=10000.0)
        # Status is RUNNING, not PASSED

        packet = generator.generate_packet(canary, "packet-001")
        assert packet is None

    def test_generate_packet_ready(self):
        """Test generating packet when canary is ready."""
        generator = PromotionPacketGenerator()
        canary = create_canary_deployment(
            canary_id="canary-001",
            strategy_id="strategy-v2",
            champion_strategy_id="strategy-v1",
        )
        canary.start(initial_equity=10000.0)
        canary.status = CanaryStatus.PASSED

        # Add some trades
        for _ in range(12):
            canary.metrics.record_trade(100.0)
        for _ in range(8):
            canary.metrics.record_trade(-50.0)

        packet = generator.generate_packet(canary, "packet-001")

        assert packet is not None
        assert packet.packet_id == "packet-001"
        assert packet.canary_id == "canary-001"
        assert packet.strategy_id == "strategy-v2"
        assert packet.champion_strategy_id == "strategy-v1"
        assert packet.status == "pending"
        assert packet.evidence is not None

    def test_generate_packet_evidence(self):
        """Test evidence collection in generated packet."""
        generator = PromotionPacketGenerator()
        canary = create_canary_deployment(
            canary_id="canary-001",
            strategy_id="strategy-v2",
            champion_strategy_id="strategy-v1",
        )
        canary.start(initial_equity=10000.0)
        canary.status = CanaryStatus.PASSED

        # Add trades
        for _ in range(12):
            canary.metrics.record_trade(100.0)
        for _ in range(8):
            canary.metrics.record_trade(-50.0)

        packet = generator.generate_packet(canary, "packet-001")

        evidence = packet.evidence
        assert evidence is not None
        assert evidence.total_trades == 20
        assert evidence.win_rate_pct == 60.0
        assert evidence.gate_check_summary is not None

    def test_generate_packet_risk_assessment(self):
        """Test risk assessment in generated packet."""
        generator = PromotionPacketGenerator()
        canary = create_canary_deployment(
            canary_id="canary-001",
            strategy_id="strategy-v2",
            champion_strategy_id="strategy-v1",
        )
        canary.start(initial_equity=10000.0)
        canary.status = CanaryStatus.PASSED

        packet = generator.generate_packet(canary, "packet-001")

        assert "drawdown_risk" in packet.risk_assessment
        assert "win_rate_stability" in packet.risk_assessment
        assert "sample_size" in packet.risk_assessment
        assert "assessment_summary" in packet.risk_assessment

    def test_generate_packet_rollback_plan(self):
        """Test rollback plan in generated packet."""
        generator = PromotionPacketGenerator()
        canary = create_canary_deployment(
            canary_id="canary-001",
            strategy_id="strategy-v2",
            champion_strategy_id="strategy-v1",
        )
        canary.start(initial_equity=10000.0)
        canary.status = CanaryStatus.PASSED

        packet = generator.generate_packet(canary, "packet-001")

        assert "rollback_target" in packet.rollback_plan
        assert "rollback_steps" in packet.rollback_plan
        assert "estimated_rollback_time" in packet.rollback_plan
        assert "verification_steps" in packet.rollback_plan

    def test_generate_markdown_packet(self):
        """Test Markdown packet generation."""
        generator = PromotionPacketGenerator()
        canary = create_canary_deployment(
            canary_id="canary-001",
            strategy_id="strategy-v2",
            champion_strategy_id="strategy-v1",
        )
        canary.start(initial_equity=10000.0)
        canary.status = CanaryStatus.PASSED

        # Add trades
        for _ in range(12):
            canary.metrics.record_trade(100.0)
        for _ in range(8):
            canary.metrics.record_trade(-50.0)

        packet = generator.generate_packet(canary, "packet-001")
        markdown = generator.generate_markdown_packet(packet)

        assert "# Promotion Packet: strategy-v2" in markdown
        assert "Packet ID:** packet-001" in markdown
        assert "Status:** PENDING" in markdown
        assert "Key Metrics" in markdown
        assert "Risk Assessment" in markdown
        assert "Rollback Plan" in markdown
        assert "Approval" in markdown

    def test_generate_markdown_with_high_drawdown_risk(self):
        """Test Markdown generation with high drawdown risk."""
        generator = PromotionPacketGenerator()
        canary = create_canary_deployment(
            canary_id="canary-001",
            strategy_id="strategy-v2",
            champion_strategy_id="strategy-v1",
        )
        canary.start(initial_equity=10000.0)
        canary.status = CanaryStatus.PASSED
        canary.metrics.max_drawdown_pct = 4.8  # Close to 5% threshold

        packet = generator.generate_packet(canary, "packet-001")
        markdown = generator.generate_markdown_packet(packet)

        assert "strategy-v2" in markdown
        assert "Risk Assessment" in markdown


class TestCreatePromotionPacketGenerator:
    """Test create_promotion_packet_generator factory function."""

    def test_create_with_defaults(self):
        """Test creating generator with defaults."""
        generator = create_promotion_packet_generator()
        assert isinstance(generator, PromotionPacketGenerator)

    def test_create_with_evaluator(self):
        """Test creating generator with custom evaluator."""
        criteria = GateCriteria(max_drawdown_pct=3.0)
        evaluator = GateEvaluator(criteria=criteria)
        generator = create_promotion_packet_generator(gate_evaluator=evaluator)
        assert generator.gate_evaluator is evaluator
