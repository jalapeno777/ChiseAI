"""Promotion packet storage with version history and audit trail.

Provides persistence for promotion packets to support the ST-BT-003 requirement:
"Packets are stored with version history and audit trail".
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from execution.canary.promotion import PromotionPacket

# Default storage directory for promotion packets
DEFAULT_STORAGE_DIR = Path("docs/approvals/evolution-submissions")


@dataclass
class PacketVersion:
    """Represents a single version of a promotion packet.

    Attributes:
        version: Version number (1, 2, 3, ...)
        packet_id: Packet identifier
        status: Status at this version (pending/approved/rejected)
        approved_by: Approver identifier (if approved)
        approved_at: Approval timestamp (if approved)
        rejection_reason: Rejection reason (if rejected)
        created_at: Timestamp when this version was created
        metadata: Additional version metadata
    """

    version: int
    packet_id: str
    status: str
    approved_by: str | None = None
    approved_at: int | None = None
    rejection_reason: str | None = None
    created_at: int = field(default_factory=lambda: int(datetime.now().timestamp()))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "version": self.version,
            "packet_id": self.packet_id,
            "status": self.status,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at,
            "rejection_reason": self.rejection_reason,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PacketVersion:
        """Create from dictionary."""
        return cls(
            version=data["version"],
            packet_id=data["packet_id"],
            status=data["status"],
            approved_by=data.get("approved_by"),
            approved_at=data.get("approved_at"),
            rejection_reason=data.get("rejection_reason"),
            created_at=data["created_at"],
            metadata=data.get("metadata", {}),
        )


@dataclass
class PacketAuditEntry:
    """Audit trail entry for a promotion packet.

    Attributes:
        timestamp: When the action occurred
        action: Action performed (created, approved, rejected, updated)
        actor: Who performed the action
        details: Additional details about the action
    """

    timestamp: int = field(default_factory=lambda: int(datetime.now().timestamp()))
    action: str = ""
    actor: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp,
            "action": self.action,
            "actor": self.actor,
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PacketAuditEntry:
        """Create from dictionary."""
        return cls(
            timestamp=data["timestamp"],
            action=data["action"],
            actor=data.get("actor"),
            details=data.get("details", {}),
        )


@dataclass
class StoredPromotionPacket:
    """Complete stored promotion packet with version history and audit trail.

    Attributes:
        packet: The promotion packet data
        versions: Version history (append-only)
        audit_trail: Audit trail of all actions
    """

    packet: dict[str, Any]
    versions: list[dict[str, Any]] = field(default_factory=list)
    audit_trail: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "packet": self.packet,
            "versions": self.versions,
            "audit_trail": self.audit_trail,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StoredPromotionPacket:
        """Create from dictionary."""
        return cls(
            packet=data["packet"],
            versions=data.get("versions", []),
            audit_trail=data.get("audit_trail", []),
        )


class PromotionPacketStorage:
    """Storage for promotion packets with version history and audit trail.

    Stores packets as JSON files with:
    - Version history (append-only)
    - Audit trail (who approved, when, rejection reasons)
    - Query methods (get by packet_id, get latest for strategy)
    """

    def __init__(self, storage_dir: Path | str | None = None) -> None:
        """Initialize the storage.

        Args:
            storage_dir: Directory to store packets. Defaults to
                docs/approvals/evolution-submissions/
        """
        self.storage_dir = Path(storage_dir) if storage_dir else DEFAULT_STORAGE_DIR
        self._ensure_storage_dir()

    def _ensure_storage_dir(self) -> None:
        """Ensure storage directory exists."""
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _get_packet_path(self, packet_id: str) -> Path:
        """Get the file path for a packet.

        Args:
            packet_id: Packet identifier

        Returns:
            Path to packet file
        """
        # Use first 2 chars of packet_id as subdirectory for organization
        prefix = packet_id[:2] if len(packet_id) >= 2 else packet_id
        subdir = self.storage_dir / prefix
        subdir.mkdir(parents=True, exist_ok=True)
        return subdir / f"{packet_id}.json"

    def save_packet(
        self,
        packet: PromotionPacket,
        actor: str | None = None,
    ) -> StoredPromotionPacket:
        """Save or update a promotion packet.

        Args:
            packet: Promotion packet to save
            actor: Actor performing the action (for audit trail)

        Returns:
            Stored packet with version history
        """
        packet_path = self._get_packet_path(packet.packet_id)

        # Load existing packet if it exists
        stored = self._load_from_file(packet_path) if packet_path.exists() else None

        if stored is None:
            # Create new stored packet
            stored = StoredPromotionPacket(
                packet=packet.to_dict(),
                versions=[self._create_version_entry(packet, 1)],
                audit_trail=[self._create_audit_entry("created", actor)],
            )
        else:
            # Update existing packet - increment version
            existing_versions = [PacketVersion.from_dict(v) for v in stored.versions]
            new_version_num = (
                max(v.version for v in existing_versions) + 1
                if existing_versions
                else 1
            )

            # Update packet data
            stored.packet = packet.to_dict()

            # Add new version entry
            stored.versions.append(self._create_version_entry(packet, new_version_num))

            # Add audit entry
            stored.audit_trail.append(
                self._create_audit_entry("updated", actor, {"version": new_version_num})
            )

        # Write to file
        self._write_to_file(packet_path, stored)

        return stored

    def _create_version_entry(
        self,
        packet: PromotionPacket,
        version: int,
    ) -> dict[str, Any]:
        """Create a version entry for a packet."""
        return PacketVersion(
            version=version,
            packet_id=packet.packet_id,
            status=packet.status,
            approved_by=packet.approved_by,
            approved_at=packet.approved_at,
            rejection_reason=packet.metadata.get("rejection_reason"),
        ).to_dict()

    def _create_audit_entry(
        self,
        action: str,
        actor: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create an audit trail entry."""
        return PacketAuditEntry(
            action=action,
            actor=actor,
            details=details or {},
        ).to_dict()

    def record_approval(
        self,
        packet_id: str,
        approver: str,
    ) -> StoredPromotionPacket | None:
        """Record approval for a packet.

        Args:
            packet_id: Packet identifier
            approver: Approver identifier

        Returns:
            Updated stored packet or None if not found
        """
        packet_path = self._get_packet_path(packet_id)

        if not packet_path.exists():
            return None

        stored = self._load_from_file(packet_path)

        # Update the stored packet data directly
        stored.packet["status"] = "approved"
        stored.packet["approved_by"] = approver
        stored.packet["approved_at"] = int(datetime.now().timestamp())

        # Add new version entry
        existing_versions = [PacketVersion.from_dict(v) for v in stored.versions]
        new_version_num = (
            max(v.version for v in existing_versions) + 1 if existing_versions else 1
        )
        stored.versions.append(
            {
                "version": new_version_num,
                "packet_id": packet_id,
                "status": "approved",
                "approved_by": approver,
                "approved_at": stored.packet["approved_at"],
                "rejection_reason": None,
                "created_at": int(datetime.now().timestamp()),
                "metadata": {},
            }
        )

        # Add audit entry - use "updated" since this modifies an existing packet
        stored.audit_trail.append(
            {
                "timestamp": int(datetime.now().timestamp()),
                "action": "updated",
                "actor": approver,
                "details": {"version": new_version_num, "action": "approved"},
            }
        )

        # Write to file
        self._write_to_file(packet_path, stored)

        return stored

    def record_rejection(
        self,
        packet_id: str,
        reason: str,
        actor: str | None = None,
    ) -> StoredPromotionPacket | None:
        """Record rejection for a packet.

        Args:
            packet_id: Packet identifier
            reason: Rejection reason
            actor: Actor performing the rejection

        Returns:
            Updated stored packet or None if not found
        """
        packet_path = self._get_packet_path(packet_id)

        if not packet_path.exists():
            return None

        stored = self._load_from_file(packet_path)

        # Update the stored packet data directly
        stored.packet["status"] = "rejected"
        stored.packet["metadata"] = stored.packet.get("metadata", {})
        stored.packet["metadata"]["rejection_reason"] = reason

        # Add new version entry
        existing_versions = [PacketVersion.from_dict(v) for v in stored.versions]
        new_version_num = (
            max(v.version for v in existing_versions) + 1 if existing_versions else 1
        )
        stored.versions.append(
            {
                "version": new_version_num,
                "packet_id": packet_id,
                "status": "rejected",
                "approved_by": None,
                "approved_at": None,
                "rejection_reason": reason,
                "created_at": int(datetime.now().timestamp()),
                "metadata": {},
            }
        )

        # Add audit entry
        stored.audit_trail.append(
            {
                "timestamp": int(datetime.now().timestamp()),
                "action": "updated",
                "actor": actor,
                "details": {
                    "version": new_version_num,
                    "action": "rejected",
                    "reason": reason,
                },
            }
        )

        # Write to file
        self._write_to_file(packet_path, stored)

        return stored

    def get_packet(self, packet_id: str) -> PromotionPacket | None:
        """Get a promotion packet by ID.

        Args:
            packet_id: Packet identifier

        Returns:
            Promotion packet or None if not found
        """
        packet_path = self._get_packet_path(packet_id)

        if not packet_path.exists():
            return None

        stored = self._load_from_file(packet_path)
        return self._dict_to_packet(stored.packet)

    def get_stored_packet(self, packet_id: str) -> StoredPromotionPacket | None:
        """Get stored packet with version history and audit trail.

        Args:
            packet_id: Packet identifier

        Returns:
            Stored packet or None if not found
        """
        packet_path = self._get_packet_path(packet_id)

        if not packet_path.exists():
            return None

        return self._load_from_file(packet_path)

    def get_latest_for_strategy(self, strategy_id: str) -> PromotionPacket | None:
        """Get the latest packet for a strategy.

        Args:
            strategy_id: Strategy identifier

        Returns:
            Latest promotion packet for the strategy or None
        """
        # Search all files in storage directory
        latest_packet = None
        latest_timestamp = 0

        for json_file in self.storage_dir.rglob("*.json"):
            try:
                stored = self._load_from_file(json_file)
                if stored.packet.get("strategy_id") == strategy_id:
                    packet_timestamp = stored.packet.get("generated_at", 0)
                    if packet_timestamp > latest_timestamp:
                        latest_timestamp = packet_timestamp
                        latest_packet = self._dict_to_packet(stored.packet)
            except (json.JSONDecodeError, KeyError):
                continue

        return latest_packet

    def list_packets(
        self,
        strategy_id: str | None = None,
        status: str | None = None,
        limit: int | None = None,
    ) -> list[PromotionPacket]:
        """List promotion packets with optional filters.

        Args:
            strategy_id: Filter by strategy ID
            status: Filter by status
            limit: Maximum number of packets to return

        Returns:
            List of promotion packets
        """
        packets = []

        for json_file in self.storage_dir.rglob("*.json"):
            try:
                stored = self._load_from_file(json_file)
                packet_dict = stored.packet

                # Apply filters
                if strategy_id and packet_dict.get("strategy_id") != strategy_id:
                    continue
                if status and packet_dict.get("status") != status:
                    continue

                packet = self._dict_to_packet(packet_dict)
                packets.append(packet)
            except (json.JSONDecodeError, KeyError):
                continue

        # Sort by generated_at descending
        packets.sort(key=lambda p: p.generated_at, reverse=True)

        if limit:
            packets = packets[:limit]

        return packets

    def get_version_history(self, packet_id: str) -> list[PacketVersion]:
        """Get version history for a packet.

        Args:
            packet_id: Packet identifier

        Returns:
            List of packet versions (most recent first)
        """
        stored = self.get_stored_packet(packet_id)
        if stored is None:
            return []

        versions = [PacketVersion.from_dict(v) for v in stored.versions]
        return sorted(versions, key=lambda v: v.version, reverse=True)

    def get_audit_trail(self, packet_id: str) -> list[PacketAuditEntry]:
        """Get audit trail for a packet.

        Args:
            packet_id: Packet identifier

        Returns:
            List of audit entries (most recent first)
        """
        stored = self.get_stored_packet(packet_id)
        if stored is None:
            return []

        entries = [PacketAuditEntry.from_dict(e) for e in stored.audit_trail]
        # Sort by timestamp descending, but use list index as tiebreaker (later entries first)
        # This ensures consistent ordering when timestamps are equal
        sorted_entries = sorted(
            enumerate(entries), key=lambda x: (-x[1].timestamp, -x[0])
        )
        return [e for _, e in sorted_entries]

    def _load_from_file(self, path: Path) -> StoredPromotionPacket:
        """Load stored packet from file."""
        with open(path, "r") as f:
            data = json.load(f)
        return StoredPromotionPacket.from_dict(data)

    def _write_to_file(self, path: Path, stored: StoredPromotionPacket) -> None:
        """Write stored packet to file."""
        with open(path, "w") as f:
            json.dump(stored.to_dict(), f, indent=2)

    def _dict_to_packet(self, data: dict[str, Any]) -> PromotionPacket:
        """Convert dictionary to PromotionPacket."""
        from execution.canary.promotion import PromotionEvidence

        evidence_data = data.get("evidence")
        evidence = None
        if evidence_data:
            # Handle both dict and PromotionEvidence object
            if isinstance(evidence_data, dict):
                evidence = PromotionEvidence(
                    canary_duration_days=evidence_data["canary_duration_days"],
                    total_trades=evidence_data["total_trades"],
                    win_rate_pct=evidence_data["win_rate_pct"],
                    max_drawdown_pct=evidence_data["max_drawdown_pct"],
                    realized_pnl=evidence_data["realized_pnl"],
                    sharpe_ratio=evidence_data.get("sharpe_ratio"),
                    gate_check_summary=evidence_data.get("gate_check_summary", {}),
                    comparison_to_champion=evidence_data.get("comparison_to_champion"),
                )
            else:
                # Already a PromotionEvidence object
                evidence = evidence_data

        # Handle risk_assessment - could be dict or already processed
        risk_assessment = data.get("risk_assessment", {})
        if not isinstance(risk_assessment, dict):
            risk_assessment = {}

        # Handle rollback_plan - could be dict or already processed
        rollback_plan = data.get("rollback_plan", {})
        if not isinstance(rollback_plan, dict):
            rollback_plan = {}

        # Handle metadata - could be dict or already processed
        metadata = data.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}

        return PromotionPacket(
            packet_id=data["packet_id"],
            canary_id=data["canary_id"],
            strategy_id=data["strategy_id"],
            champion_strategy_id=data.get("champion_strategy_id"),
            status=data.get("status", "pending"),
            evidence=evidence,
            risk_assessment=risk_assessment,
            rollback_plan=rollback_plan,
            generated_at=data.get("generated_at", 0),
            approved_at=data.get("approved_at"),
            approved_by=data.get("approved_by"),
            metadata=metadata,
        )


def create_promotion_packet_storage(
    storage_dir: Path | str | None = None,
) -> PromotionPacketStorage:
    """Create a promotion packet storage instance.

    Args:
        storage_dir: Optional custom storage directory

    Returns:
        PromotionPacketStorage instance
    """
    return PromotionPacketStorage(storage_dir=storage_dir)
