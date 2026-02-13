"""Tests for promotion packet storage."""

import json
import tempfile
from datetime import datetime

import pytest

from execution.canary.models import CanaryStatus
from execution.canary.promotion import (
    PromotionEvidence,
    PromotionPacket,
    PromotionPacketGenerator,
)
from execution.canary.promotion_storage import (
    PacketAuditEntry,
    PacketVersion,
    PromotionPacketStorage,
    StoredPromotionPacket,
    create_promotion_packet_storage,
)


class TestPacketVersion:
    """Test PacketVersion dataclass."""

    def test_to_dict(self):
        """Test serialization to dict."""
        version = PacketVersion(
            version=1,
            packet_id="packet-001",
            status="approved",
            approved_by="admin@example.com",
            approved_at=1234567890,
        )

        data = version.to_dict()
        assert data["version"] == 1
        assert data["packet_id"] == "packet-001"
        assert data["status"] == "approved"
        assert data["approved_by"] == "admin@example.com"
        assert data["approved_at"] == 1234567890

    def test_from_dict(self):
        """Test deserialization from dict."""
        data = {
            "version": 2,
            "packet_id": "packet-001",
            "status": "rejected",
            "rejection_reason": "Insufficient evidence",
            "created_at": 1234567890,
            "metadata": {},
        }

        version = PacketVersion.from_dict(data)
        assert version.version == 2
        assert version.packet_id == "packet-001"
        assert version.status == "rejected"
        assert version.rejection_reason == "Insufficient evidence"


class TestPacketAuditEntry:
    """Test PacketAuditEntry dataclass."""

    def test_to_dict(self):
        """Test serialization to dict."""
        entry = PacketAuditEntry(
            action="approved",
            actor="admin@example.com",
            details={"version": 1},
        )

        data = entry.to_dict()
        assert data["action"] == "approved"
        assert data["actor"] == "admin@example.com"
        assert data["details"]["version"] == 1

    def test_from_dict(self):
        """Test deserialization from dict."""
        data = {
            "timestamp": 1234567890,
            "action": "created",
            "actor": "system",
            "details": {},
        }

        entry = PacketAuditEntry.from_dict(data)
        assert entry.timestamp == 1234567890
        assert entry.action == "created"
        assert entry.actor == "system"


class TestStoredPromotionPacket:
    """Test StoredPromotionPacket dataclass."""

    def test_to_dict(self):
        """Test serialization to dict."""
        stored = StoredPromotionPacket(
            packet={"packet_id": "p1", "status": "pending"},
            versions=[
                {
                    "version": 1,
                    "packet_id": "p1",
                    "status": "pending",
                    "created_at": 123,
                }
            ],
            audit_trail=[{"timestamp": 123, "action": "created"}],
        )

        data = stored.to_dict()
        assert data["packet"]["packet_id"] == "p1"
        assert len(data["versions"]) == 1
        assert len(data["audit_trail"]) == 1

    def test_from_dict(self):
        """Test deserialization from dict."""
        data = {
            "packet": {"packet_id": "p1", "status": "approved"},
            "versions": [
                {
                    "version": 1,
                    "packet_id": "p1",
                    "status": "pending",
                    "created_at": 123,
                }
            ],
            "audit_trail": [{"timestamp": 123, "action": "approved"}],
        }

        stored = StoredPromotionPacket.from_dict(data)
        assert stored.packet["packet_id"] == "p1"
        assert stored.packet["status"] == "approved"


class TestPromotionPacketStorage:
    """Test PromotionPacketStorage class."""

    @pytest.fixture
    def storage(self, tmp_path):
        """Create storage with temporary directory."""
        return PromotionPacketStorage(storage_dir=tmp_path)

    @pytest.fixture
    def sample_packet(self):
        """Create a sample promotion packet."""
        return PromotionPacket(
            packet_id="test-packet-001",
            canary_id="canary-001",
            strategy_id="strategy-v2",
            champion_strategy_id="strategy-v1",
            status="pending",
            evidence=PromotionEvidence(
                canary_duration_days=7.5,
                total_trades=20,
                win_rate_pct=60.0,
                max_drawdown_pct=3.5,
                realized_pnl=500.0,
                sharpe_ratio=1.5,
                gate_check_summary={"all_gates_passed": True},
            ),
            risk_assessment={"drawdown_risk": "LOW"},
            rollback_plan={"rollback_target": "strategy-v1"},
        )

    def test_save_new_packet(self, storage, sample_packet):
        """Test saving a new packet."""
        stored = storage.save_packet(sample_packet)

        assert stored is not None
        assert stored.packet["packet_id"] == "test-packet-001"
        assert len(stored.versions) == 1
        assert stored.versions[0]["version"] == 1
        assert len(stored.audit_trail) == 1
        assert stored.audit_trail[0]["action"] == "created"

    def test_get_packet(self, storage, sample_packet):
        """Test retrieving a packet."""
        storage.save_packet(sample_packet)

        retrieved = storage.get_packet("test-packet-001")

        assert retrieved is not None
        assert retrieved.packet_id == "test-packet-001"
        assert retrieved.strategy_id == "strategy-v2"

    def test_get_packet_not_found(self, storage):
        """Test retrieving non-existent packet."""
        result = storage.get_packet("non-existent")
        assert result is None

    def test_update_packet_version(self, storage, sample_packet):
        """Test that updating creates new version."""
        storage.save_packet(sample_packet)

        # Update the packet
        sample_packet.status = "approved"
        sample_packet.approve("admin@example.com")
        stored = storage.save_packet(sample_packet)

        assert len(stored.versions) == 2
        assert stored.versions[1]["version"] == 2
        assert stored.versions[1]["status"] == "approved"

    def test_record_approval(self, storage, sample_packet):
        """Test recording approval."""
        storage.save_packet(sample_packet)

        stored = storage.record_approval("test-packet-001", "admin@example.com")

        assert stored is not None
        assert stored.packet["status"] == "approved"
        assert stored.packet["approved_by"] == "admin@example.com"
        assert stored.packet["approved_at"] is not None

    def test_record_rejection(self, storage, sample_packet):
        """Test recording rejection."""
        storage.save_packet(sample_packet)

        stored = storage.record_rejection(
            "test-packet-001", "Insufficient evidence", "reviewer@example.com"
        )

        assert stored is not None
        assert stored.packet["status"] == "rejected"
        assert stored.packet["metadata"]["rejection_reason"] == "Insufficient evidence"

    def test_get_version_history(self, storage, sample_packet):
        """Test retrieving version history."""
        storage.save_packet(sample_packet)

        sample_packet.status = "approved"
        sample_packet.approve("admin@example.com")
        storage.save_packet(sample_packet)

        versions = storage.get_version_history("test-packet-001")

        assert len(versions) == 2
        assert versions[0].version == 2  # Most recent first
        assert versions[0].status == "approved"
        assert versions[1].version == 1

    def test_get_audit_trail(self, storage, sample_packet):
        """Test retrieving audit trail."""
        storage.save_packet(sample_packet, actor="creator@example.com")
        storage.record_approval("test-packet-001", "approver@example.com")

        entries = storage.get_audit_trail("test-packet-001")

        assert len(entries) == 2
        assert entries[0].action == "updated"  # Most recent first
        assert entries[0].actor == "approver@example.com"
        assert entries[1].action == "created"

    def test_list_packets(self, storage, sample_packet):
        """Test listing packets."""
        storage.save_packet(sample_packet)

        # Create another packet for different strategy
        packet2 = PromotionPacket(
            packet_id="test-packet-002",
            canary_id="canary-002",
            strategy_id="strategy-v3",
            champion_strategy_id="strategy-v1",
            status="pending",
        )
        storage.save_packet(packet2)

        packets = storage.list_packets()
        assert len(packets) == 2

    def test_list_packets_filter_by_status(self, storage, sample_packet):
        """Test filtering packets by status."""
        storage.save_packet(sample_packet)

        sample_packet.status = "approved"
        sample_packet.approve("admin@example.com")
        storage.save_packet(sample_packet)

        pending = storage.list_packets(status="pending")
        approved = storage.list_packets(status="approved")

        assert len(pending) == 0
        assert len(approved) == 1

    def test_list_packets_filter_by_strategy(self, storage, sample_packet):
        """Test filtering packets by strategy."""
        storage.save_packet(sample_packet)

        packet2 = PromotionPacket(
            packet_id="test-packet-002",
            canary_id="canary-002",
            strategy_id="strategy-v3",
            champion_strategy_id="strategy-v1",
            status="pending",
        )
        storage.save_packet(packet2)

        v2_packets = storage.list_packets(strategy_id="strategy-v2")
        v3_packets = storage.list_packets(strategy_id="strategy-v3")

        assert len(v2_packets) == 1
        assert v2_packets[0].strategy_id == "strategy-v2"
        assert len(v3_packets) == 1
        assert v3_packets[0].strategy_id == "strategy-v3"

    def test_get_latest_for_strategy(self, storage, sample_packet):
        """Test getting latest packet for a strategy."""
        storage.save_packet(sample_packet)

        # Create another packet for same strategy but later
        packet2 = PromotionPacket(
            packet_id="test-packet-002",
            canary_id="canary-002",
            strategy_id="strategy-v2",
            champion_strategy_id="strategy-v1",
            status="pending",
        )
        packet2.generated_at = int(datetime.now().timestamp()) + 1000
        storage.save_packet(packet2)

        latest = storage.get_latest_for_strategy("strategy-v2")

        assert latest is not None
        assert latest.packet_id == "test-packet-002"

    def test_get_latest_for_strategy_not_found(self, storage):
        """Test getting latest packet for non-existent strategy."""
        result = storage.get_latest_for_strategy("non-existent-strategy")
        assert result is None


class TestCreatePromotionPacketStorage:
    """Test create_promotion_packet_storage factory."""

    def test_create_with_defaults(self):
        """Test creating storage with defaults."""
        storage = create_promotion_packet_storage()
        assert isinstance(storage, PromotionPacketStorage)

    def test_create_with_custom_dir(self, tmp_path):
        """Test creating storage with custom directory."""
        storage = create_promotion_packet_storage(storage_dir=tmp_path)
        assert storage.storage_dir == tmp_path


class TestStorageIntegration:
    """Integration tests for storage with PromotionPacketGenerator."""

    def test_storage_with_generator(self, tmp_path):
        """Test saving packets generated by PromotionPacketGenerator."""
        from execution.canary.models import create_canary_deployment

        storage = PromotionPacketStorage(storage_dir=tmp_path)
        generator = PromotionPacketGenerator()

        # Create a canary that passed
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

        # Generate packet
        packet = generator.generate_packet(canary, "packet-001")
        assert packet is not None

        # Save to storage
        stored = storage.save_packet(packet, actor="system")
        assert stored is not None

        # Retrieve and verify
        retrieved = storage.get_packet("packet-001")
        assert retrieved is not None
        assert retrieved.strategy_id == "strategy-v2"
        assert retrieved.evidence is not None
        assert retrieved.evidence.total_trades == 20

        # Verify version history
        versions = storage.get_version_history("packet-001")
        assert len(versions) == 1

        # Verify audit trail
        audit = storage.get_audit_trail("packet-001")
        assert len(audit) == 1
        assert audit[0].action == "created"
