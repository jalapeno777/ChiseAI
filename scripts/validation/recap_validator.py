#!/usr/bin/env python3
"""
Recap Validator Module

Validates recap messages against canonical outcomes in Redis and InfluxDB
to ensure G5 source verification passes.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, Optional


class GateStatus(str, Enum):
    """Gate validation status."""

    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"
    ERROR = "ERROR"


@dataclass
class GateResult:
    """Result of a gate validation."""

    gate_name: str
    status: GateStatus
    message: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        """Check if gate passed."""
        return self.status == GateStatus.PASS


@dataclass
class OutcomeSourceProof:
    """Proof of an outcome's existence in a source database."""

    outcome_id: str
    signal_id: str
    order_id: str
    pnl: float
    source_query: str
    source_database: str
    fill_id: Optional[str] = None
    timestamp_utc: str = ""

    # Patterns to redact from source_query
    SECRET_PATTERNS = [
        r"api_key\s*=\s*\S+",
        r"token\s*=\s*\S+",
        r"secret\s*=\s*\S+",
        r"password\s*=\s*\S+",
    ]

    def _redact_secrets(self, text: str) -> str:
        """Redact secrets from text."""
        result = text
        for pattern in self.SECRET_PATTERNS:
            result = re.sub(pattern, "[REDACTED]", result, flags=re.IGNORECASE)
        return result

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary with secrets redacted."""
        return {
            "outcome_id": self.outcome_id,
            "signal_id": self.signal_id,
            "order_id": self.order_id,
            "fill_id": self.fill_id,
            "timestamp_utc": self.timestamp_utc,
            "pnl": self.pnl,
            "source_query": self._redact_secrets(self.source_query),
            "source_database": self.source_database,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OutcomeSourceProof":
        """Create from dictionary."""
        return cls(
            outcome_id=data["outcome_id"],
            signal_id=data["signal_id"],
            order_id=data["order_id"],
            fill_id=data.get("fill_id"),
            timestamp_utc=data.get("timestamp_utc", ""),
            pnl=data["pnl"],
            source_query=data["source_query"],
            source_database=data["source_database"],
        )


@dataclass
class DiscordMessageEvidence:
    """Evidence from a Discord message."""

    message_id: str
    channel_id: str
    author_id: str
    content: str
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "message_id": self.message_id,
            "channel_id": self.channel_id,
            "author_id": self.author_id,
            "content": self.content,
            "timestamp": self.timestamp,
        }


@dataclass
class RecapValidationEvidence:
    """Evidence from validating a recap message."""

    recap_message_id: str
    recap_timestamp_utc: str
    outcome_proofs: list[OutcomeSourceProof]
    total_pnl: float
    trade_count: int
    win_count: int
    loss_count: int
    source_verified: bool
    discord_evidence: Optional[DiscordMessageEvidence] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "recap_message_id": self.recap_message_id,
            "recap_timestamp_utc": self.recap_timestamp_utc,
            "outcome_proofs": [p.to_dict() for p in self.outcome_proofs],
            "total_pnl": self.total_pnl,
            "trade_count": self.trade_count,
            "win_count": self.win_count,
            "loss_count": self.loss_count,
            "source_verified": self.source_verified,
            "discord_evidence": (
                self.discord_evidence.to_dict() if self.discord_evidence else None
            ),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RecapValidationEvidence":
        """Create from dictionary."""
        outcome_proofs = [
            OutcomeSourceProof.from_dict(p) for p in data.get("outcome_proofs", [])
        ]
        discord_evidence = None
        if data.get("discord_evidence"):
            discord_evidence = DiscordMessageEvidence(**data["discord_evidence"])
        return cls(
            recap_message_id=data["recap_message_id"],
            recap_timestamp_utc=data["recap_timestamp_utc"],
            outcome_proofs=outcome_proofs,
            total_pnl=data["total_pnl"],
            trade_count=data["trade_count"],
            win_count=data["win_count"],
            loss_count=data["loss_count"],
            source_verified=data["source_verified"],
            discord_evidence=discord_evidence,
        )


class RecapValidator:
    """
    Validates recap messages against canonical outcome sources.

    This validator checks that recap messages posted to Discord match
    the actual outcomes stored in Redis and InfluxDB.
    """

    # Patterns for extracting trade IDs from recap content
    TRADE_ID_PATTERNS = [
        r"Trade ID:\s*([A-Z0-9-]+)",
        r"trade_id:\s*([A-Z0-9-]+)",
        r"Order ID:\s*([A-Z0-9-]+)",
        r"#TRADE-([A-Z0-9-]+)",
        r"\[TRADE:([A-Z0-9-]+)\]",
        r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
    ]

    def __init__(
        self,
        redis_collector: Optional[Any] = None,
        influx_collector: Optional[Any] = None,
    ):
        """
        Initialize the RecapValidator.

        Args:
            redis_collector: Optional Redis delta collector for verifying outcomes
            influx_collector: Optional InfluxDB evidence collector for verifying outcomes
        """
        self.redis_collector = redis_collector
        self.influx_collector = influx_collector

    async def extract_trade_ids_from_recap(self, content: str) -> list[str]:
        """
        Extract trade IDs from recap message content.

        Args:
            content: The recap message content

        Returns:
            List of unique trade IDs found in the content
        """
        ids = []
        for pattern in self.TRADE_ID_PATTERNS:
            matches = re.findall(pattern, content, re.IGNORECASE)
            ids.extend(matches)

        # Remove duplicates while preserving order
        seen = set()
        unique_ids = []
        for id_val in ids:
            if id_val.upper() not in seen:
                seen.add(id_val.upper())
                unique_ids.append(id_val)

        return unique_ids

    async def verify_outcome_in_redis(
        self,
        trade_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> Optional[OutcomeSourceProof]:
        """
        Verify an outcome exists in Redis.

        Args:
            trade_id: The trade ID to verify
            start_time: Start of the time window
            end_time: End of the time window

        Returns:
            OutcomeSourceProof if found, None otherwise
        """
        if self.redis_collector is None:
            return None

        # Stub implementation - actual implementation would query Redis
        return None

    async def verify_outcome_in_influx(
        self,
        trade_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> Optional[OutcomeSourceProof]:
        """
        Verify an outcome exists in InfluxDB.

        Args:
            trade_id: The trade ID to verify
            start_time: Start of the time window
            end_time: End of the time window

        Returns:
            OutcomeSourceProof if found, None otherwise
        """
        if self.influx_collector is None:
            return None

        # Stub implementation - actual implementation would query InfluxDB
        return None

    async def validate_recap_source(
        self,
        recap_message: DiscordMessageEvidence,
        start_time: datetime,
        end_time: datetime,
    ) -> RecapValidationEvidence:
        """
        Validate a recap message against source databases.

        Args:
            recap_message: The Discord recap message evidence
            start_time: Start of the validation window
            end_time: End of the validation window

        Returns:
            RecapValidationEvidence with verification results
        """
        trade_ids = await self.extract_trade_ids_from_recap(recap_message.content)

        outcome_proofs = []
        total_pnl = 0.0
        win_count = 0
        loss_count = 0

        for trade_id in trade_ids:
            # Try Redis first
            proof = await self.verify_outcome_in_redis(trade_id, start_time, end_time)
            if proof is None:
                # Fall back to InfluxDB
                proof = await self.verify_outcome_in_influx(
                    trade_id, start_time, end_time
                )

            if proof:
                outcome_proofs.append(proof)
                total_pnl += proof.pnl
                if proof.pnl >= 0:
                    win_count += 1
                else:
                    loss_count += 1

        source_verified = len(outcome_proofs) > 0 and len(outcome_proofs) == len(
            trade_ids
        )

        return RecapValidationEvidence(
            recap_message_id=recap_message.message_id,
            recap_timestamp_utc=recap_message.timestamp,
            outcome_proofs=outcome_proofs,
            total_pnl=total_pnl,
            trade_count=len(trade_ids),
            win_count=win_count,
            loss_count=loss_count,
            source_verified=source_verified,
            discord_evidence=recap_message,
        )

    def validate_g5_recap(self, evidence: RecapValidationEvidence) -> GateResult:
        """
        Validate G5 gate for recap source verification.

        Args:
            evidence: The recap validation evidence

        Returns:
            GateResult with pass/fail status
        """
        # Check required fields
        if not evidence.recap_message_id:
            return GateResult(
                gate_name="G5_RECAP",
                status=GateStatus.FAIL,
                message="Missing recap message ID",
                evidence=evidence.to_dict(),
            )

        if not evidence.recap_timestamp_utc:
            return GateResult(
                gate_name="G5_RECAP",
                status=GateStatus.FAIL,
                message="Missing recap timestamp",
                evidence=evidence.to_dict(),
            )

        if not evidence.outcome_proofs:
            return GateResult(
                gate_name="G5_RECAP",
                status=GateStatus.FAIL,
                message="No outcome proofs found",
                evidence=evidence.to_dict(),
            )

        if not evidence.source_verified:
            return GateResult(
                gate_name="G5_RECAP",
                status=GateStatus.FAIL,
                message="Source verification failed - not all trades verified",
                evidence=evidence.to_dict(),
            )

        return GateResult(
            gate_name="G5_RECAP",
            status=GateStatus.PASS,
            message=f"Recap validated: {evidence.trade_count} trades, "
            f"PnL: {evidence.total_pnl:.2f}",
            evidence=evidence.to_dict(),
        )

    async def validate_recap_message(
        self,
        recap_message: DiscordMessageEvidence,
        start_time: datetime,
        end_time: datetime,
    ) -> GateResult:
        """
        Full validation of a recap message.

        Args:
            recap_message: The Discord recap message evidence
            start_time: Start of the validation window
            end_time: End of the validation window

        Returns:
            GateResult with pass/fail status
        """
        evidence = await self.validate_recap_source(recap_message, start_time, end_time)
        return self.validate_g5_recap(evidence)


def create_recap_validator(
    redis_collector: Optional[Any] = None,
    influx_collector: Optional[Any] = None,
) -> RecapValidator:
    """
    Factory function to create a RecapValidator.

    Args:
        redis_collector: Optional Redis delta collector
        influx_collector: Optional InfluxDB evidence collector

    Returns:
        Configured RecapValidator instance
    """
    return RecapValidator(
        redis_collector=redis_collector,
        influx_collector=influx_collector,
    )


async def main() -> int:
    """
    Main CLI entry point for recap validation.

    Validates recap messages against canonical outcomes in Redis and InfluxDB.

    Returns:
        Exit code (0 for success, 1 for validation failure)
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Validate Discord recap messages against canonical outcomes"
    )
    parser.add_argument(
        "--recap-content",
        type=str,
        help="Recap message content to validate",
    )
    parser.add_argument(
        "--recap-id",
        type=str,
        default="",
        help="Recap message ID",
    )
    parser.add_argument(
        "--start-time",
        type=str,
        help="Start time for validation window (ISO format)",
    )
    parser.add_argument(
        "--end-time",
        type=str,
        help="End time for validation window (ISO format)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output",
    )

    args = parser.parse_args()

    # Create validator
    validator = create_recap_validator()

    # Parse time window
    start_time = datetime.now(UTC) - timedelta(hours=24)
    end_time = datetime.now(UTC)

    if args.start_time:
        start_time = datetime.fromisoformat(args.start_time.replace("Z", "+00:00"))
    if args.end_time:
        end_time = datetime.fromisoformat(args.end_time.replace("Z", "+00:00"))

    # Create mock recap message if content provided
    if args.recap_content:
        recap_message = DiscordMessageEvidence(
            message_id=args.recap_id or str(uuid.uuid4()),
            channel_id="",
            author_id="",
            content=args.recap_content,
            timestamp=datetime.now(UTC).isoformat(),
        )

        # Validate
        result = await validator.validate_recap_message(
            recap_message, start_time, end_time
        )

        if args.verbose:
            print(f"Gate: {result.gate_name}")
            print(f"Status: {result.status.value}")
            print(f"Message: {result.message}")
            if result.evidence:
                print(f"Evidence: {json.dumps(result.evidence, indent=2)}")

        return 0 if result.passed else 1
    else:
        # No recap content provided - print help
        parser.print_help()
        return 0


if __name__ == "__main__":
    import asyncio
    import json
    import uuid

    exit_code = asyncio.run(main())
    exit(exit_code)
