"""Promotion packet integration for canary deployments.

Integrates with the promotion packet workflow (ST-BT-003) to generate
human-readable promotion packets with evidence for paper full approval.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from execution.canary.gate_evaluator import GateEvaluator
from execution.canary.models import CanaryDeployment, CanaryStatus, GateCriteria


@dataclass
class PromotionEvidence:
    """Evidence collected for promotion decision.

    Attributes:
        canary_duration_days: Actual canary duration in days
        total_trades: Total number of trades
        win_rate_pct: Win rate percentage
        max_drawdown_pct: Maximum drawdown percentage
        realized_pnl: Realized profit/loss
        sharpe_ratio: Sharpe ratio if available
        gate_check_summary: Summary of gate check results
        comparison_to_champion: Comparison with champion strategy (if available)
    """

    canary_duration_days: float
    total_trades: int
    win_rate_pct: float
    max_drawdown_pct: float
    realized_pnl: float
    sharpe_ratio: float | None
    gate_check_summary: dict[str, Any]
    comparison_to_champion: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "canary_duration_days": round(self.canary_duration_days, 2),
            "total_trades": self.total_trades,
            "win_rate_pct": round(self.win_rate_pct, 4),
            "max_drawdown_pct": round(self.max_drawdown_pct, 4),
            "realized_pnl": round(self.realized_pnl, 8),
            "sharpe_ratio": round(self.sharpe_ratio, 4) if self.sharpe_ratio else None,
            "gate_check_summary": self.gate_check_summary,
            "comparison_to_champion": self.comparison_to_champion,
        }


@dataclass
class PromotionPacket:
    """Promotion packet for human approval.

    Attributes:
        packet_id: Unique packet identifier
        canary_id: Reference to canary deployment
        strategy_id: Strategy being promoted
        champion_strategy_id: Current champion strategy
        status: Packet status (pending/approved/rejected)
        evidence: Collected evidence
        risk_assessment: Risk assessment summary
        rollback_plan: Rollback plan details
        generated_at: Generation timestamp
        approved_at: Approval timestamp (if approved)
        approved_by: Approver identifier (if approved)
        metadata: Additional metadata
    """

    packet_id: str
    canary_id: str
    strategy_id: str
    champion_strategy_id: str | None
    status: str = "pending"
    evidence: PromotionEvidence | None = None
    risk_assessment: dict[str, Any] = field(default_factory=dict)
    rollback_plan: dict[str, Any] = field(default_factory=dict)
    generated_at: int = field(default_factory=lambda: int(datetime.now().timestamp()))
    approved_at: int | None = None
    approved_by: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "packet_id": self.packet_id,
            "canary_id": self.canary_id,
            "strategy_id": self.strategy_id,
            "champion_strategy_id": self.champion_strategy_id,
            "status": self.status,
            "evidence": self.evidence.to_dict() if self.evidence else None,
            "risk_assessment": self.risk_assessment,
            "rollback_plan": self.rollback_plan,
            "generated_at": self.generated_at,
            "approved_at": self.approved_at,
            "approved_by": self.approved_by,
            "metadata": self.metadata,
        }

    def approve(self, approver: str) -> None:
        """Mark packet as approved.

        Args:
            approver: Identifier of approver
        """
        self.status = "approved"
        self.approved_by = approver
        self.approved_at = int(datetime.now().timestamp())

    def reject(self, reason: str) -> None:
        """Mark packet as rejected.

        Args:
            reason: Rejection reason
        """
        self.status = "rejected"
        self.metadata["rejection_reason"] = reason


class PromotionPacketGenerator:
    """Generates promotion packets for canary deployments.

    This class provides:
    - Evidence collection from canary metrics
    - Risk assessment generation
    - Rollback plan documentation
    - Human-readable packet generation
    """

    def __init__(self, gate_evaluator: GateEvaluator | None = None) -> None:
        """Initialize the packet generator.

        Args:
            gate_evaluator: Gate evaluator for final validation
        """
        self.gate_evaluator = gate_evaluator or GateEvaluator()

    def generate_packet(
        self,
        canary: CanaryDeployment,
        packet_id: str,
    ) -> PromotionPacket | None:
        """Generate a promotion packet for a canary.

        Args:
            canary: Canary deployment to generate packet for
            packet_id: Unique packet identifier

        Returns:
            Promotion packet or None if canary not ready
        """
        # Verify canary is ready for promotion
        can_promote, reasons = canary.can_promote()
        if not can_promote:
            return None

        # Collect evidence
        evidence = self._collect_evidence(canary)

        # Generate risk assessment
        risk_assessment = self._generate_risk_assessment(canary)

        # Generate rollback plan
        rollback_plan = self._generate_rollback_plan(canary)

        return PromotionPacket(
            packet_id=packet_id,
            canary_id=canary.canary_id,
            strategy_id=canary.strategy_id,
            champion_strategy_id=canary.champion_strategy_id,
            status="pending",
            evidence=evidence,
            risk_assessment=risk_assessment,
            rollback_plan=rollback_plan,
        )

    def _collect_evidence(self, canary: CanaryDeployment) -> PromotionEvidence:
        """Collect evidence from canary deployment.

        Args:
            canary: Canary deployment

        Returns:
            Collected evidence
        """
        metrics = canary.metrics
        duration_seconds = canary.end_time - canary.start_time
        duration_days = duration_seconds / (24 * 60 * 60)

        # Generate gate check summary
        gate_eval_report = self.gate_evaluator.generate_evaluation_report(canary)
        gate_check_summary = {
            "all_gates_passed": True,
            "gate_results": gate_eval_report.get("gate_checks", []),
            "final_status": gate_eval_report.get("evaluated_status"),
        }

        return PromotionEvidence(
            canary_duration_days=duration_days,
            total_trades=metrics.total_trades,
            win_rate_pct=metrics.win_rate_pct,
            max_drawdown_pct=metrics.max_drawdown_pct,
            realized_pnl=metrics.realized_pnl,
            sharpe_ratio=metrics.sharpe_ratio,
            gate_check_summary=gate_check_summary,
            comparison_to_champion=None,  # Would be populated from strategy registry
        )

    def _generate_risk_assessment(self, canary: CanaryDeployment) -> dict[str, Any]:
        """Generate risk assessment for canary.

        Args:
            canary: Canary deployment

        Returns:
            Risk assessment dictionary
        """
        metrics = canary.metrics

        # Assess drawdown risk
        drawdown_risk = "LOW"
        if metrics.max_drawdown_pct > canary.criteria.max_drawdown_pct * 0.8:
            drawdown_risk = "MEDIUM"
        if metrics.max_drawdown_pct > canary.criteria.max_drawdown_pct * 0.9:
            drawdown_risk = "HIGH"

        # Assess win rate stability
        win_rate_stability = "STABLE"
        if metrics.total_trades < canary.criteria.min_trades * 2:
            win_rate_stability = "LOW_CONFIDENCE"

        return {
            "drawdown_risk": drawdown_risk,
            "win_rate_stability": win_rate_stability,
            "sample_size": metrics.total_trades,
            "allocation_pct": canary.allocation_pct,
            "max_drawdown_observed": round(metrics.max_drawdown_pct, 4),
            "win_rate_observed": round(metrics.win_rate_pct, 4),
            "assessment_summary": (
                f"Canary completed with {metrics.max_drawdown_pct:.2f}% max drawdown "
                f"and {metrics.win_rate_pct:.2f}% win rate over "
                f"{canary.criteria.duration_days} days"
            ),
        }

    def _generate_rollback_plan(self, canary: CanaryDeployment) -> dict[str, Any]:
        """Generate rollback plan for canary.

        Args:
            canary: Canary deployment

        Returns:
            Rollback plan dictionary
        """
        return {
            "rollback_target": canary.champion_strategy_id or "previous_champion",
            "rollback_trigger": "human_decision_or_performance_degradation",
            "rollback_steps": [
                "1. Halt new position openings for candidate strategy",
                "2. Close existing positions at market or next signal",
                "3. Activate champion strategy for new signals",
                "4. Verify champion is receiving and processing signals",
                "5. Update registry to reflect rollback",
            ],
            "estimated_rollback_time": "5 minutes",
            "verification_steps": [
                "- Confirm no pending orders for candidate",
                "- Confirm champion is generating signals",
                "- Verify portfolio state consistency",
            ],
        }

    def generate_markdown_packet(self, packet: PromotionPacket) -> str:
        """Generate human-readable Markdown promotion packet.

        Args:
            packet: Promotion packet

        Returns:
            Markdown formatted packet
        """
        evidence = packet.evidence

        markdown = f"""# Promotion Packet: {packet.strategy_id}

**Packet ID:** {packet.packet_id}  
**Generated:** {datetime.fromtimestamp(packet.generated_at).isoformat()}  
**Status:** {packet.status.upper()}

---

## Executive Summary

Strategy `{packet.strategy_id}` has completed canary testing and is requesting promotion to paper full.

"""

        if evidence:
            markdown += f"""### Key Metrics

| Metric | Value | Threshold | Status |
|--------|-------|-----------|--------|
| Duration | {evidence.canary_duration_days:.2f} days | {packet.evidence.gate_check_summary.get("gate_results", [{}])[2].get("threshold_value", 7) if packet.evidence else 7} days | ✅ PASS |
| Win Rate | {evidence.win_rate_pct:.2f}% | {packet.evidence.gate_check_summary.get("gate_results", [{}])[1].get("threshold_value", 55) if packet.evidence else 55}% | ✅ PASS |
| Max Drawdown | {evidence.max_drawdown_pct:.2f}% | ≤{packet.evidence.gate_check_summary.get("gate_results", [{}])[0].get("threshold_value", 5) if packet.evidence else 5}% | ✅ PASS |
| Total Trades | {evidence.total_trades} | - | - |
| Realized PnL | {evidence.realized_pnl:.8f} | - | - |

"""

        markdown += f"""---

## Risk Assessment

"""

        if packet.risk_assessment:
            markdown += f"""**Drawdown Risk:** {packet.risk_assessment.get("drawdown_risk", "N/A")}  
**Win Rate Stability:** {packet.risk_assessment.get("win_rate_stability", "N/A")}  
**Sample Size:** {packet.risk_assessment.get("sample_size", "N/A")} trades

{packet.risk_assessment.get("assessment_summary", "")}

"""

        markdown += f"""---

## Rollback Plan

**Rollback Target:** {packet.rollback_plan.get("rollback_target", "N/A")}  
**Estimated Time:** {packet.rollback_plan.get("estimated_rollback_time", "N/A")}

### Steps

"""

        for step in packet.rollback_plan.get("rollback_steps", []):
            markdown += f"- {step}\n"

        markdown += """
### Verification

"""

        for step in packet.rollback_plan.get("verification_steps", []):
            markdown += f"- {step}\n"

        markdown += f"""

---

## Approval

- [ ] I have reviewed the evidence
- [ ] I understand the risks
- [ ] I approve promotion to paper full

**Approved By:** _________________  
**Date:** _________________

---

*This packet was auto-generated by the ChiseAI Canary System*
"""

        return markdown


def create_promotion_packet_generator(
    gate_evaluator: GateEvaluator | None = None,
) -> PromotionPacketGenerator:
    """Create a promotion packet generator.

    Args:
        gate_evaluator: Gate evaluator instance

    Returns:
        New PromotionPacketGenerator instance
    """
    return PromotionPacketGenerator(gate_evaluator=gate_evaluator)
