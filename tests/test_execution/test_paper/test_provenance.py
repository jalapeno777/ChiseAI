"""Tests for signal provenance data model.

For PAPER-2025-002: Signal Provenance
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from execution.paper.provenance import (
    DecisionReason,
    ExecutionDecision,
    ProvenanceRecord,
    ProvenanceStage,
    SignalProvenance,
)


class TestDecisionReason:
    """Tests for DecisionReason enum."""

    def test_all_reason_codes_exist(self) -> None:
        """Verify all 8 required reason codes are defined."""
        expected_reasons = {
            "SIGNAL_ACCEPTED",
            "RISK_REJECTED",
            "LOW_CONFIDENCE",
            "SYMBOL_OCCUPIED",
            "KILL_SWITCH_ACTIVE",
            "MAX_POSITION_LIMIT",
            "INVALID_SIGNAL",
            "SYSTEM_ERROR",
        }
        actual_reasons = {r.name for r in DecisionReason}
        assert actual_reasons == expected_reasons

    def test_reason_code_values(self) -> None:
        """Verify reason code values are normalized snake_case strings."""
        expected_values = {
            DecisionReason.SIGNAL_ACCEPTED: "signal_accepted",
            DecisionReason.RISK_REJECTED: "risk_rejected",
            DecisionReason.LOW_CONFIDENCE: "low_confidence",
            DecisionReason.SYMBOL_OCCUPIED: "symbol_occupied",
            DecisionReason.KILL_SWITCH_ACTIVE: "kill_switch_active",
            DecisionReason.MAX_POSITION_LIMIT: "max_position_limit",
            DecisionReason.INVALID_SIGNAL: "invalid_signal",
            DecisionReason.SYSTEM_ERROR: "system_error",
        }
        for reason, expected_value in expected_values.items():
            assert reason.value == expected_value

    def test_reason_code_uniqueness(self) -> None:
        """Verify all reason code values are unique."""
        values = [r.value for r in DecisionReason]
        assert len(values) == len(set(values)), "Reason code values must be unique"

    def test_reason_code_from_string(self) -> None:
        """Verify reason codes can be created from string values."""
        assert DecisionReason("signal_accepted") == DecisionReason.SIGNAL_ACCEPTED
        assert DecisionReason("risk_rejected") == DecisionReason.RISK_REJECTED
        assert DecisionReason("system_error") == DecisionReason.SYSTEM_ERROR


class TestProvenanceStage:
    """Tests for ProvenanceStage enum."""

    def test_all_stages_exist(self) -> None:
        """Verify all 7 required stages are defined."""
        expected_stages = {
            "RECEIVED",
            "KILL_SWITCH_CHECK",
            "SYMBOL_REGISTRY_CHECK",
            "RISK_VALIDATION",
            "ORDER_PLACEMENT",
            "COMPLETED",
            "REJECTED",
        }
        actual_stages = {s.name for s in ProvenanceStage}
        assert actual_stages == expected_stages

    def test_stage_values(self) -> None:
        """Verify stage values are normalized snake_case strings."""
        expected_values = {
            ProvenanceStage.RECEIVED: "received",
            ProvenanceStage.KILL_SWITCH_CHECK: "kill_switch_check",
            ProvenanceStage.SYMBOL_REGISTRY_CHECK: "symbol_registry_check",
            ProvenanceStage.RISK_VALIDATION: "risk_validation",
            ProvenanceStage.ORDER_PLACEMENT: "order_placement",
            ProvenanceStage.COMPLETED: "completed",
            ProvenanceStage.REJECTED: "rejected",
        }
        for stage, expected_value in expected_values.items():
            assert stage.value == expected_value

    def test_stage_uniqueness(self) -> None:
        """Verify all stage values are unique."""
        values = [s.value for s in ProvenanceStage]
        assert len(values) == len(set(values)), "Stage values must be unique"

    def test_stage_from_string(self) -> None:
        """Verify stages can be created from string values."""
        assert ProvenanceStage("received") == ProvenanceStage.RECEIVED
        assert ProvenanceStage("risk_validation") == ProvenanceStage.RISK_VALIDATION
        assert ProvenanceStage("completed") == ProvenanceStage.COMPLETED


class TestSignalProvenance:
    """Tests for SignalProvenance dataclass."""

    @pytest.fixture
    def sample_provenance(self) -> SignalProvenance:
        """Create a sample SignalProvenance for testing."""
        return SignalProvenance(
            provenance_id="prov-001",
            signal_id="sig-001",
            generation_timestamp=datetime(2026, 3, 4, 12, 0, 0, tzinfo=UTC),
            source_strategy="momentum_v1",
            source_version="1.2.3",
            confidence_factors={"rsi": 0.85, "macd": 0.72, "markov": 0.91},
            market_conditions={
                "volatility_regime": "high",
                "trend_state": "uptrend",
            },
        )

    def test_signal_provenance_creation(
        self, sample_provenance: SignalProvenance
    ) -> None:
        """Verify SignalProvenance can be created with all fields."""
        assert sample_provenance.provenance_id == "prov-001"
        assert sample_provenance.signal_id == "sig-001"
        assert sample_provenance.source_strategy == "momentum_v1"
        assert sample_provenance.source_version == "1.2.3"
        assert sample_provenance.confidence_factors["rsi"] == 0.85
        assert sample_provenance.market_conditions["volatility_regime"] == "high"

    def test_signal_provenance_defaults(self) -> None:
        """Verify SignalProvenance has correct defaults for optional fields."""
        provenance = SignalProvenance(
            provenance_id="prov-002",
            signal_id="sig-002",
            generation_timestamp=datetime.now(UTC),
            source_strategy="test_strategy",
            source_version="1.0.0",
        )
        assert provenance.confidence_factors == {}
        assert provenance.market_conditions == {}

    def test_signal_provenance_timestamp_normalization(self) -> None:
        """Verify naive timestamps are converted to UTC."""
        naive_time = datetime(2026, 3, 4, 12, 0, 0)
        provenance = SignalProvenance(
            provenance_id="prov-003",
            signal_id="sig-003",
            generation_timestamp=naive_time,
            source_strategy="test",
            source_version="1.0.0",
        )
        assert provenance.generation_timestamp.tzinfo == UTC

    def test_signal_provenance_confidence_validation(self) -> None:
        """Verify confidence factors must be in valid range."""
        with pytest.raises(ValueError, match="must be between 0.0 and 1.0"):
            SignalProvenance(
                provenance_id="prov-004",
                signal_id="sig-004",
                generation_timestamp=datetime.now(UTC),
                source_strategy="test",
                source_version="1.0.0",
                confidence_factors={"rsi": 1.5},  # Invalid: > 1.0
            )

        with pytest.raises(ValueError, match="must be between 0.0 and 1.0"):
            SignalProvenance(
                provenance_id="prov-005",
                signal_id="sig-005",
                generation_timestamp=datetime.now(UTC),
                source_strategy="test",
                source_version="1.0.0",
                confidence_factors={"rsi": -0.1},  # Invalid: < 0.0
            )

    def test_signal_provenance_to_dict(
        self, sample_provenance: SignalProvenance
    ) -> None:
        """Verify to_dict produces correct serialization."""
        data = sample_provenance.to_dict()
        assert data["provenance_id"] == "prov-001"
        assert data["signal_id"] == "sig-001"
        assert data["source_strategy"] == "momentum_v1"
        assert data["confidence_factors"]["rsi"] == 0.85
        assert isinstance(data["generation_timestamp"], str)

    def test_signal_provenance_from_dict(self) -> None:
        """Verify from_dict correctly deserializes."""
        data: dict[str, Any] = {
            "provenance_id": "prov-006",
            "signal_id": "sig-006",
            "generation_timestamp": "2026-03-04T12:00:00+00:00",
            "source_strategy": "mean_reversion",
            "source_version": "2.0.0",
            "confidence_factors": {"bollinger": 0.78},
            "market_conditions": {"regime": "ranging"},
        }
        provenance = SignalProvenance.from_dict(data)
        assert provenance.provenance_id == "prov-006"
        assert provenance.signal_id == "sig-006"
        assert provenance.source_strategy == "mean_reversion"
        assert provenance.confidence_factors["bollinger"] == 0.78

    def test_signal_provenance_roundtrip(
        self, sample_provenance: SignalProvenance
    ) -> None:
        """Verify serialization roundtrip preserves data."""
        data = sample_provenance.to_dict()
        restored = SignalProvenance.from_dict(data)
        assert restored.provenance_id == sample_provenance.provenance_id
        assert restored.signal_id == sample_provenance.signal_id
        assert restored.confidence_factors == sample_provenance.confidence_factors


class TestExecutionDecision:
    """Tests for ExecutionDecision dataclass."""

    @pytest.fixture
    def sample_decision(self) -> ExecutionDecision:
        """Create a sample ExecutionDecision for testing."""
        return ExecutionDecision(
            decision_id="dec-001",
            signal_id="sig-001",
            decision_timestamp=datetime(2026, 3, 4, 12, 1, 0, tzinfo=UTC),
            decision_reason=DecisionReason.SIGNAL_ACCEPTED,
            decision_details={"risk_score": 0.23, "position_size": 1.0},
        )

    def test_execution_decision_creation(
        self, sample_decision: ExecutionDecision
    ) -> None:
        """Verify ExecutionDecision can be created with all fields."""
        assert sample_decision.decision_id == "dec-001"
        assert sample_decision.signal_id == "sig-001"
        assert sample_decision.decision_reason == DecisionReason.SIGNAL_ACCEPTED
        assert sample_decision.decision_details["risk_score"] == 0.23

    def test_execution_decision_defaults(self) -> None:
        """Verify ExecutionDecision has correct defaults."""
        decision = ExecutionDecision(
            decision_id="dec-002",
            signal_id="sig-002",
            decision_timestamp=datetime.now(UTC),
            decision_reason=DecisionReason.RISK_REJECTED,
        )
        assert decision.decision_details == {}

    def test_execution_decision_timestamp_normalization(self) -> None:
        """Verify naive timestamps are converted to UTC."""
        naive_time = datetime(2026, 3, 4, 12, 0, 0)
        decision = ExecutionDecision(
            decision_id="dec-003",
            signal_id="sig-003",
            decision_timestamp=naive_time,
            decision_reason=DecisionReason.LOW_CONFIDENCE,
        )
        assert decision.decision_timestamp.tzinfo == UTC

    def test_execution_decision_reason_normalization(self) -> None:
        """Verify string reason is converted to enum."""
        decision = ExecutionDecision(
            decision_id="dec-004",
            signal_id="sig-004",
            decision_timestamp=datetime.now(UTC),
            decision_reason="kill_switch_active",  # String instead of enum
        )
        assert decision.decision_reason == DecisionReason.KILL_SWITCH_ACTIVE

    def test_execution_decision_to_dict(
        self, sample_decision: ExecutionDecision
    ) -> None:
        """Verify to_dict produces correct serialization."""
        data = sample_decision.to_dict()
        assert data["decision_id"] == "dec-001"
        assert data["signal_id"] == "sig-001"
        assert data["decision_reason"] == "signal_accepted"
        assert data["decision_details"]["risk_score"] == 0.23

    def test_execution_decision_from_dict(self) -> None:
        """Verify from_dict correctly deserializes."""
        data: dict[str, Any] = {
            "decision_id": "dec-005",
            "signal_id": "sig-005",
            "decision_timestamp": "2026-03-04T12:00:00+00:00",
            "decision_reason": "symbol_occupied",
            "decision_details": {"existing_position": "BTCUSDT"},
        }
        decision = ExecutionDecision.from_dict(data)
        assert decision.decision_id == "dec-005"
        assert decision.decision_reason == DecisionReason.SYMBOL_OCCUPIED

    def test_execution_decision_roundtrip(
        self, sample_decision: ExecutionDecision
    ) -> None:
        """Verify serialization roundtrip preserves data."""
        data = sample_decision.to_dict()
        restored = ExecutionDecision.from_dict(data)
        assert restored.decision_id == sample_decision.decision_id
        assert restored.decision_reason == sample_decision.decision_reason
        assert restored.decision_details == sample_decision.decision_details


class TestProvenanceRecord:
    """Tests for ProvenanceRecord class."""

    @pytest.fixture
    def sample_record(self) -> ProvenanceRecord:
        """Create a sample ProvenanceRecord for testing."""
        return ProvenanceRecord(signal_id="sig-001")

    @pytest.fixture
    def sample_provenance(self) -> SignalProvenance:
        """Create a sample SignalProvenance for testing."""
        return SignalProvenance(
            provenance_id="prov-001",
            signal_id="sig-001",
            generation_timestamp=datetime(2026, 3, 4, 12, 0, 0, tzinfo=UTC),
            source_strategy="momentum_v1",
            source_version="1.2.3",
        )

    @pytest.fixture
    def sample_decision(self) -> ExecutionDecision:
        """Create a sample ExecutionDecision for testing."""
        return ExecutionDecision(
            decision_id="dec-001",
            signal_id="sig-001",
            decision_timestamp=datetime(2026, 3, 4, 12, 1, 0, tzinfo=UTC),
            decision_reason=DecisionReason.SIGNAL_ACCEPTED,
        )

    def test_provenance_record_creation(self, sample_record: ProvenanceRecord) -> None:
        """Verify ProvenanceRecord can be created."""
        assert sample_record.signal_id == "sig-001"
        assert sample_record.provenance is None
        assert sample_record.decisions == []
        assert sample_record.stages == []

    def test_capture_signal(
        self,
        sample_record: ProvenanceRecord,
        sample_provenance: SignalProvenance,
    ) -> None:
        """Verify capture_signal stores provenance and stage."""
        result = sample_record.capture_signal(sample_provenance)
        assert sample_record.provenance == sample_provenance
        assert ProvenanceStage.RECEIVED in sample_record.stages
        assert result == sample_provenance

    def test_capture_signal_custom_stage(
        self,
        sample_record: ProvenanceRecord,
        sample_provenance: SignalProvenance,
    ) -> None:
        """Verify capture_signal accepts custom stage."""
        sample_record.capture_signal(sample_provenance, ProvenanceStage.RISK_VALIDATION)
        assert ProvenanceStage.RISK_VALIDATION in sample_record.stages

    def test_capture_decision(
        self,
        sample_record: ProvenanceRecord,
        sample_decision: ExecutionDecision,
    ) -> None:
        """Verify capture_decision stores decision."""
        result = sample_record.capture_decision("sig-001", sample_decision)
        assert len(sample_record.decisions) == 1
        assert sample_record.decisions[0] == sample_decision
        assert result == sample_decision

    def test_capture_decision_signal_mismatch(
        self,
        sample_record: ProvenanceRecord,
        sample_decision: ExecutionDecision,
    ) -> None:
        """Verify capture_decision raises on signal ID mismatch."""
        with pytest.raises(ValueError, match="Signal ID mismatch"):
            sample_record.capture_decision("wrong-sig", sample_decision)

    def test_capture_decision_with_details(
        self,
        sample_record: ProvenanceRecord,
        sample_decision: ExecutionDecision,
    ) -> None:
        """Verify capture_decision merges additional details."""
        extra_details = {"extra": "info"}
        sample_record.capture_decision("sig-001", sample_decision, extra_details)
        assert sample_record.decisions[0].decision_details["extra"] == "info"

    def test_add_stage(self, sample_record: ProvenanceRecord) -> None:
        """Verify add_stage appends stage."""
        sample_record.add_stage(ProvenanceStage.KILL_SWITCH_CHECK)
        sample_record.add_stage(ProvenanceStage.RISK_VALIDATION)
        assert len(sample_record.stages) == 2
        assert sample_record.stages[0] == ProvenanceStage.KILL_SWITCH_CHECK

    def test_get_provenance(
        self,
        sample_record: ProvenanceRecord,
        sample_provenance: SignalProvenance,
        sample_decision: ExecutionDecision,
    ) -> None:
        """Verify get_provenance returns complete data."""
        sample_record.capture_signal(sample_provenance)
        sample_record.capture_decision("sig-001", sample_decision)
        sample_record.add_stage(ProvenanceStage.COMPLETED)

        data = sample_record.get_provenance("sig-001")
        assert data["signal_id"] == "sig-001"
        assert data["provenance"] is not None
        assert len(data["decisions"]) == 1
        assert data["stages"] == ["received", "completed"]

    def test_get_provenance_signal_mismatch(
        self, sample_record: ProvenanceRecord
    ) -> None:
        """Verify get_provenance raises on signal ID mismatch."""
        with pytest.raises(ValueError, match="Signal ID mismatch"):
            sample_record.get_provenance("wrong-sig")

    def test_provenance_record_to_dict(
        self,
        sample_record: ProvenanceRecord,
        sample_provenance: SignalProvenance,
    ) -> None:
        """Verify to_dict produces correct serialization."""
        sample_record.capture_signal(sample_provenance)
        data = sample_record.to_dict()
        assert data["signal_id"] == "sig-001"
        assert data["provenance"] is not None
        assert isinstance(data["created_at"], str)

    def test_provenance_record_from_dict(self) -> None:
        """Verify from_dict correctly deserializes."""
        data: dict[str, Any] = {
            "signal_id": "sig-007",
            "provenance": {
                "provenance_id": "prov-007",
                "signal_id": "sig-007",
                "generation_timestamp": "2026-03-04T12:00:00+00:00",
                "source_strategy": "test",
                "source_version": "1.0.0",
                "confidence_factors": {},
                "market_conditions": {},
            },
            "decisions": [],
            "stages": [],
            "created_at": "2026-03-04T12:00:00+00:00",
            "updated_at": "2026-03-04T12:00:00+00:00",
        }
        record = ProvenanceRecord.from_dict(data)
        assert record.signal_id == "sig-007"
        assert record.provenance is not None
        assert record.provenance.source_strategy == "test"

    def test_provenance_record_roundtrip(
        self,
        sample_record: ProvenanceRecord,
        sample_provenance: SignalProvenance,
        sample_decision: ExecutionDecision,
    ) -> None:
        """Verify serialization roundtrip preserves data."""
        sample_record.capture_signal(sample_provenance)
        sample_record.capture_decision("sig-001", sample_decision)
        sample_record.add_stage(ProvenanceStage.COMPLETED)

        data = sample_record.to_dict()
        restored = ProvenanceRecord.from_dict(data)
        assert restored.signal_id == sample_record.signal_id
        assert restored.provenance is not None
        assert len(restored.decisions) == 1
        assert len(restored.stages) == 2

    def test_timestamp_normalization(self) -> None:
        """Verify naive timestamps are converted to UTC."""
        naive_time = datetime(2026, 3, 4, 12, 0, 0)
        record = ProvenanceRecord(
            signal_id="sig-008",
            created_at=naive_time,
            updated_at=naive_time,
        )
        assert record.created_at.tzinfo == UTC
        assert record.updated_at.tzinfo == UTC


class TestProvenanceIntegration:
    """Integration tests for the complete provenance flow."""

    def test_full_signal_lifecycle(self) -> None:
        """Test a complete signal lifecycle from receipt to completion."""
        # Create record
        record = ProvenanceRecord(signal_id="sig-lifecycle-001")

        # Capture signal provenance
        provenance = SignalProvenance(
            provenance_id="prov-lifecycle-001",
            signal_id="sig-lifecycle-001",
            generation_timestamp=datetime.now(UTC),
            source_strategy="trend_following",
            source_version="3.1.4",
            confidence_factors={"ema_cross": 0.88, "volume": 0.75},
            market_conditions={"volatility_regime": "low", "trend": "up"},
        )
        record.capture_signal(provenance, ProvenanceStage.RECEIVED)

        # Simulate pipeline stages
        record.add_stage(ProvenanceStage.KILL_SWITCH_CHECK)
        record.add_stage(ProvenanceStage.SYMBOL_REGISTRY_CHECK)
        record.add_stage(ProvenanceStage.RISK_VALIDATION)

        # Capture decisions
        record.capture_decision(
            "sig-lifecycle-001",
            ExecutionDecision(
                decision_id="dec-ks-001",
                signal_id="sig-lifecycle-001",
                decision_timestamp=datetime.now(UTC),
                decision_reason=DecisionReason.SIGNAL_ACCEPTED,
                decision_details={"kill_switch": "inactive"},
            ),
        )

        record.capture_decision(
            "sig-lifecycle-001",
            ExecutionDecision(
                decision_id="dec-risk-001",
                signal_id="sig-lifecycle-001",
                decision_timestamp=datetime.now(UTC),
                decision_reason=DecisionReason.SIGNAL_ACCEPTED,
                decision_details={"risk_score": 0.15, "max_position_ok": True},
            ),
        )

        # Complete
        record.add_stage(ProvenanceStage.ORDER_PLACEMENT)
        record.add_stage(ProvenanceStage.COMPLETED)

        # Verify
        data = record.get_provenance("sig-lifecycle-001")
        assert data["signal_id"] == "sig-lifecycle-001"
        assert len(data["stages"]) == 6
        assert len(data["decisions"]) == 2
        assert data["stages"][-1] == "completed"

    def test_rejected_signal_flow(self) -> None:
        """Test a signal that gets rejected."""
        record = ProvenanceRecord(signal_id="sig-reject-001")

        provenance = SignalProvenance(
            provenance_id="prov-reject-001",
            signal_id="sig-reject-001",
            generation_timestamp=datetime.now(UTC),
            source_strategy="mean_reversion",
            source_version="2.0.0",
        )
        record.capture_signal(provenance)
        record.add_stage(ProvenanceStage.KILL_SWITCH_CHECK)

        # Reject due to kill switch
        record.capture_decision(
            "sig-reject-001",
            ExecutionDecision(
                decision_id="dec-reject-001",
                signal_id="sig-reject-001",
                decision_timestamp=datetime.now(UTC),
                decision_reason=DecisionReason.KILL_SWITCH_ACTIVE,
                decision_details={"kill_switch_reason": "manual_override"},
            ),
        )
        record.add_stage(ProvenanceStage.REJECTED)

        data = record.get_provenance("sig-reject-001")
        assert data["stages"][-1] == "rejected"
        assert data["decisions"][0]["decision_reason"] == "kill_switch_active"

    def test_all_reason_codes_used(self) -> None:
        """Verify all reason codes can be used in decisions."""
        record = ProvenanceRecord(signal_id="sig-all-reasons")

        for i, reason in enumerate(DecisionReason):
            decision = ExecutionDecision(
                decision_id=f"dec-all-{i}",
                signal_id="sig-all-reasons",
                decision_timestamp=datetime.now(UTC),
                decision_reason=reason,
            )
            record.capture_decision("sig-all-reasons", decision)

        assert len(record.decisions) == len(DecisionReason)

    def test_all_stages_used(self) -> None:
        """Verify all stages can be added."""
        record = ProvenanceRecord(signal_id="sig-all-stages")

        for stage in ProvenanceStage:
            record.add_stage(stage)

        assert len(record.stages) == len(ProvenanceStage)
