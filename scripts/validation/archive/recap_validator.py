#!/usr/bin/env python3
"""
Recap Validator for G5 Validation

Validates that recap messages prove source from canonical outcomes
generated in the same run. This ensures:

1. Recap messages reference actual canonical outcomes (Redis/Influx)
2. All outcomes are verified against canonical storage
3. Timestamps are UTC and within proof window
4. Secrets are redacted from all evidence
5. Missing source proof = G5 RECAP FAIL

For PARTY-FORENSIC-006: G5 Recap Source Validation
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class GateStatus(str, Enum):
    """Status of a validation gate."""

    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"
    SKIP = "skip"


class SourceDatabase(str, Enum):
    """Canonical source database for outcomes."""

    REDIS = "redis"
    INFLUXDB = "influx"


@dataclass
class OutcomeSourceProof:
    """Proof that an outcome exists in canonical storage.

    Attributes:
        outcome_id: Unique outcome identifier
        signal_id: Signal ID that generated this outcome
        order_id: Order ID associated with this outcome
        fill_id: Fill ID (if filled)
        timestamp_utc: ISO timestamp of outcome (UTC)
        pnl: Profit/loss for this outcome
        source_query: The query used to retrieve this outcome
        source_database: Which database ("redis" or "influx")
    """

    outcome_id: str
    signal_id: str
    order_id: str
    fill_id: str | None = None
    timestamp_utc: str = ""
    pnl: float = 0.0
    source_query: str = ""
    source_database: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
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
    def from_dict(cls, data: dict[str, Any]) -> OutcomeSourceProof:
        """Create from dictionary."""
        return cls(
            outcome_id=data["outcome_id"],
            signal_id=data["signal_id"],
            order_id=data["order_id"],
            fill_id=data.get("fill_id"),
            timestamp_utc=data.get("timestamp_utc", ""),
            pnl=data.get("pnl", 0.0),
            source_query=data.get("source_query", ""),
            source_database=data.get("source_database", ""),
        )

    @staticmethod
    def _redact_secrets(text: str) -> str:
        """Redact secrets/tokens from text."""
        # Redact Discord tokens
        text = re.sub(
            r"[A-Za-z0-9_-]{23,28}\.[A-Za-z0-9_-]{6,7}\.[A-Za-z0-9_-]{27,}",
            "[REDACTED]",
            text,
        )
        # Redact webhook URLs
        text = re.sub(
            r"https?://discord\.com/api/webhooks/\d+/[A-Za-z0-9_-]+",
            "[REDACTED_WEBHOOK]",
            text,
        )
        # Redact API keys
        text = re.sub(
            r"(api[_-]?key|token|secret|password)[=:]",
            "[REDACTED]=",
            text,
            flags=re.IGNORECASE,
        )
        return text


@dataclass
class RecapValidationEvidence:
    """Complete evidence for recap validation.

    Attributes:
        recap_message_id: Discord message ID of the recap
        recap_timestamp_utc: ISO timestamp of recap (UTC)
        outcome_proofs: List of verified outcome proofs
        total_pnl: Total P&L from all outcomes
        trade_count: Number of trades
        win_count: Number of winning trades
        loss_count: Number of losing trades
        source_verified: Whether all outcomes verified against canonical storage
    """

    recap_message_id: str
    recap_timestamp_utc: str
    outcome_proofs: list[OutcomeSourceProof] = field(default_factory=list)
    total_pnl: float = 0.0
    trade_count: int = 0
    win_count: int = 0
    loss_count: int = 0
    source_verified: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "recap_message_id": self.recap_message_id,
            "recap_timestamp_utc": self.recap_timestamp_utc,
            "outcome_proofs": [p.to_dict() for p in self.outcome_proofs],
            "total_pnl": self.total_pnl,
            "trade_count": self.trade_count,
            "win_count": self.win_count,
            "loss_count": self.loss_count,
            "source_verified": self.source_verified,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RecapValidationEvidence:
        """Create from dictionary."""
        return cls(
            recap_message_id=data["recap_message_id"],
            recap_timestamp_utc=data["recap_timestamp_utc"],
            outcome_proofs=[
                OutcomeSourceProof.from_dict(p) for p in data.get("outcome_proofs", [])
            ],
            total_pnl=data.get("total_pnl", 0.0),
            trade_count=data.get("trade_count", 0),
            win_count=data.get("win_count", 0),
            loss_count=data.get("loss_count", 0),
            source_verified=data.get("source_verified", False),
        )


@dataclass
class GateResult:
    """Result of a G5 validation gate.

    Attributes:
        gate_name: Name of the gate (e.g., "G5_RECAP")
        status: Pass/fail/error/skip status
        message: Human-readable result message
        evidence: Recap validation evidence
        details: Additional details dictionary
        timestamp: When validation was performed
    """

    gate_name: str = "G5_RECAP"
    status: GateStatus = GateStatus.FAIL
    message: str = ""
    evidence: RecapValidationEvidence | None = None
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "gate_name": self.gate_name,
            "status": self.status.value,
            "message": self.message,
            "evidence": self.evidence.to_dict() if self.evidence else None,
            "details": self.details,
            "timestamp": self.timestamp,
        }

    @property
    def passed(self) -> bool:
        """Check if gate passed."""
        return self.status == GateStatus.PASS


@dataclass
class DiscordMessageEvidence:
    """Evidence of a Discord message (for compatibility with discord_evidence.py).

    Attributes:
        message_id: Discord message snowflake ID
        channel_id: Discord channel ID
        channel_name: Channel name
        timestamp_utc: ISO timestamp of message
        content_type: Message type - "OPEN", "CLOSE", or "RECAP"
        trade_id: Optional trade ID extracted from message
        content_snippet: First 100 chars of content (secrets redacted)
        author_id: Discord author ID
        author_name: Discord author username
        is_bot: Whether message was sent by a bot
    """

    message_id: str
    channel_id: str
    channel_name: str
    timestamp_utc: str
    content_type: str
    trade_id: str | None = None
    content_snippet: str = ""
    author_id: str | None = None
    author_name: str | None = None
    is_bot: bool = False


class RecapValidator:
    """Validates that recap messages prove source from canonical outcomes.

    This validator ensures that recap messages reference actual outcomes
    stored in canonical storage (Redis or InfluxDB), not fabricated data.

    Attributes:
        redis_collector: Collector for Redis evidence
        influx_collector: Collector for InfluxDB evidence
    """

    def __init__(
        self,
        redis_collector: Any | None = None,
        influx_collector: Any | None = None,
    ):
        """Initialize the validator.

        Args:
            redis_collector: RedisDeltaCollector instance for Redis queries
            influx_collector: InfluxEvidenceCollector instance for Influx queries
        """
        self.redis_collector = redis_collector
        self.influx_collector = influx_collector

    async def validate_recap_source(
        self,
        recap_message: DiscordMessageEvidence,
        proof_window_start: datetime,
        proof_window_end: datetime,
    ) -> RecapValidationEvidence:
        """Validate that a recap message sources from canonical outcomes.

        Steps:
        1. Extract trade IDs from recap message
        2. Query canonical storage (Redis/Influx) for those outcomes
        3. Verify all claimed outcomes exist in canonical storage
        4. Verify timestamps are within proof window
        5. Build source proof for each outcome

        Args:
            recap_message: The recap message evidence to validate
            proof_window_start: Start of valid proof window (UTC)
            proof_window_end: End of valid proof window (UTC)

        Returns:
            RecapValidationEvidence with all verification results
        """
        # Extract trade IDs from recap content
        trade_ids = await self.extract_trade_ids_from_recap(
            recap_message.content_snippet
        )

        outcome_proofs: list[OutcomeSourceProof] = []
        total_pnl = 0.0
        win_count = 0
        loss_count = 0
        all_verified = True

        # Verify each trade ID against canonical storage
        for trade_id in trade_ids:
            # Try Redis first
            proof = await self.verify_outcome_in_redis(
                trade_id, proof_window_start, proof_window_end
            )

            # If not in Redis, try InfluxDB
            if proof is None:
                proof = await self.verify_outcome_in_influx(
                    trade_id, proof_window_start, proof_window_end
                )

            if proof:
                outcome_proofs.append(proof)
                total_pnl += proof.pnl
                if proof.pnl > 0:
                    win_count += 1
                elif proof.pnl < 0:
                    loss_count += 1
            else:
                # Trade ID claimed in recap but not found in canonical storage
                all_verified = False
                logger.warning(
                    f"Trade {trade_id} claimed in recap but not found in canonical storage"
                )

        return RecapValidationEvidence(
            recap_message_id=recap_message.message_id,
            recap_timestamp_utc=recap_message.timestamp_utc,
            outcome_proofs=outcome_proofs,
            total_pnl=round(total_pnl, 8),
            trade_count=len(outcome_proofs),
            win_count=win_count,
            loss_count=loss_count,
            source_verified=all_verified and len(outcome_proofs) > 0,
        )

    async def extract_trade_ids_from_recap(self, recap_content: str) -> list[str]:
        """Extract trade IDs mentioned in recap message.

        Looks for patterns like:
        - Trade ID: ABC123
        - trade_id: ABC123
        - #TRADE-ABC123
        - [TRADE:ABC123]
        - UUID format

        Args:
            recap_content: Content of the recap message

        Returns:
            List of extracted trade IDs
        """
        trade_ids: list[str] = []

        # Pattern: Trade ID: VALUE or trade_id: VALUE
        matches = re.findall(
            r"(?:trade[_\s-]?id|tid)[\s:]+([A-Z0-9][-_A-Z0-9]{5,})",
            recap_content,
            re.IGNORECASE,
        )
        trade_ids.extend([m.upper() for m in matches])

        # Pattern: #TRADE-VALUE or [TRADE:VALUE]
        matches = re.findall(
            r"[#\[]TRADE[:-]?([A-Z0-9][-_A-Z0-9]{5,})",
            recap_content,
            re.IGNORECASE,
        )
        trade_ids.extend([m.upper() for m in matches])

        # Pattern: UUID
        matches = re.findall(
            r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
            recap_content,
            re.IGNORECASE,
        )
        trade_ids.extend([m.lower() for m in matches])

        # Pattern: Order ID: VALUE
        matches = re.findall(
            r"(?:order[_\s-]?id|oid)[\s:]+([A-Z0-9][-_A-Z0-9]{5,})",
            recap_content,
            re.IGNORECASE,
        )
        trade_ids.extend([m.upper() for m in matches])

        # Remove duplicates while preserving order
        seen = set()
        unique_ids = []
        for tid in trade_ids:
            if tid not in seen:
                seen.add(tid)
                unique_ids.append(tid)

        return unique_ids

    async def verify_outcome_in_redis(
        self,
        trade_id: str,
        window_start: datetime,
        window_end: datetime,
    ) -> OutcomeSourceProof | None:
        """Verify outcome exists in Redis within time window.

        Args:
            trade_id: Trade ID to look up
            window_start: Start of valid time window (UTC)
            window_end: End of valid time window (UTC)

        Returns:
            OutcomeSourceProof if found and valid, None otherwise
        """
        if self.redis_collector is None:
            return None

        try:
            # Query Redis for outcome data
            # Expected key pattern: outcome:{trade_id} or trade:{trade_id}:outcome
            outcome_data = await self._query_redis_outcome(trade_id)

            if not outcome_data:
                return None

            # Check timestamp is within window
            outcome_ts_str = outcome_data.get("timestamp_utc", "")
            if outcome_ts_str:
                try:
                    outcome_ts = datetime.fromisoformat(
                        outcome_ts_str.replace("Z", "+00:00")
                    )
                    if outcome_ts < window_start or outcome_ts > window_end:
                        logger.debug(
                            f"Outcome {trade_id} outside proof window: {outcome_ts}"
                        )
                        return None
                except ValueError:
                    logger.warning(f"Invalid timestamp format: {outcome_ts_str}")
                    return None

            return OutcomeSourceProof(
                outcome_id=outcome_data.get("outcome_id", trade_id),
                signal_id=outcome_data.get("signal_id", ""),
                order_id=outcome_data.get("order_id", trade_id),
                fill_id=outcome_data.get("fill_id"),
                timestamp_utc=outcome_ts_str,
                pnl=float(outcome_data.get("pnl", 0.0)),
                source_query=f"HGET outcome:{trade_id} *",
                source_database=SourceDatabase.REDIS.value,
            )

        except Exception as e:
            logger.error(f"Error querying Redis for {trade_id}: {e}")
            return None

    async def verify_outcome_in_influx(
        self,
        trade_id: str,
        window_start: datetime,
        window_end: datetime,
    ) -> OutcomeSourceProof | None:
        """Verify outcome exists in InfluxDB within time window.

        Args:
            trade_id: Trade ID to look up
            window_start: Start of valid time window (UTC)
            window_end: End of valid time window (UTC)

        Returns:
            OutcomeSourceProof if found and valid, None otherwise
        """
        if self.influx_collector is None:
            return None

        try:
            # Query InfluxDB for outcome data
            query = self._build_influx_outcome_query(trade_id, window_start, window_end)
            outcome_data = await self._query_influx_outcome(query)

            if not outcome_data:
                return None

            return OutcomeSourceProof(
                outcome_id=outcome_data.get("outcome_id", trade_id),
                signal_id=outcome_data.get("signal_id", ""),
                order_id=outcome_data.get("order_id", trade_id),
                fill_id=outcome_data.get("fill_id"),
                timestamp_utc=outcome_data.get("timestamp", ""),
                pnl=float(outcome_data.get("pnl", 0.0)),
                source_query=query,
                source_database=SourceDatabase.INFLUXDB.value,
            )

        except Exception as e:
            logger.error(f"Error querying InfluxDB for {trade_id}: {e}")
            return None

    async def _query_redis_outcome(self, trade_id: str) -> dict[str, Any] | None:
        """Query Redis for outcome data.

        Args:
            trade_id: Trade ID to query

        Returns:
            Outcome data dict or None if not found
        """
        if self.redis_collector is None:
            return None

        # Try different key patterns
        key_patterns = [
            f"outcome:{trade_id}",
            f"trade:{trade_id}:outcome",
            f"trades:{trade_id}",
            f"fills:{trade_id}",
        ]

        for key in key_patterns:
            try:
                # Use hgetall if collector supports it
                if hasattr(self.redis_collector, "hgetall"):
                    data = self.redis_collector.hgetall(key)
                    if data:
                        return {
                            k.decode() if isinstance(k, bytes) else k: (
                                v.decode() if isinstance(v, bytes) else v
                            )
                            for k, v in data.items()
                        }
                # Try get for string values
                elif hasattr(self.redis_collector, "get"):
                    data = self.redis_collector.get(key)
                    if data:
                        import json

                        value = data.decode() if isinstance(data, bytes) else data
                        return (
                            json.loads(value)
                            if value.startswith("{")
                            else {"value": value}
                        )
            except Exception as e:
                logger.debug(f"Redis query failed for key {key}: {e}")
                continue

        return None

    def _build_influx_outcome_query(
        self,
        trade_id: str,
        window_start: datetime,
        window_end: datetime,
    ) -> str:
        """Build InfluxQL query for outcome data.

        Args:
            trade_id: Trade ID to query
            window_start: Start of time window
            window_end: End of time window

        Returns:
            InfluxQL query string
        """
        start_str = window_start.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_str = window_end.strftime("%Y-%m-%dT%H:%M:%SZ")

        return f"""
        SELECT *
        FROM "outcomes"
        WHERE ("trade_id" = '{trade_id}' OR "order_id" = '{trade_id}' OR "fill_id" = '{trade_id}')
        AND time >= '{start_str}'
        AND time <= '{end_str}'
        """

    async def _query_influx_outcome(self, query: str) -> dict[str, Any] | None:
        """Query InfluxDB for outcome data.

        Args:
            query: InfluxQL query

        Returns:
            Outcome data dict or None if not found
        """
        if self.influx_collector is None:
            return None

        try:
            if hasattr(self.influx_collector, "query"):
                result = self.influx_collector.query(query)
                points = list(result.get_points()) if result else []
                if points:
                    return points[0]  # Return first matching point
            elif hasattr(self.influx_collector, "execute_query"):
                result = await self.influx_collector.execute_query(query)
                if result and len(result) > 0:
                    return result[0]
        except Exception as e:
            logger.error(f"InfluxDB query failed: {e}")

        return None

    def validate_g5_recap(self, evidence: RecapValidationEvidence) -> GateResult:
        """G5 Recap validation.

        Requirements:
        - Must have recap message with ID
        - Must source from canonical outcomes
        - All outcomes must be verified
        - Must be within proof window
        - Missing source proof = G5 RECAP FAIL

        Args:
            evidence: Recap validation evidence to evaluate

        Returns:
            GateResult with pass/fail status
        """
        validation_errors: list[str] = []
        details: dict[str, Any] = {}

        # Check 1: Must have recap message ID
        if not evidence.recap_message_id:
            validation_errors.append("Missing recap message ID")

        # Check 2: Must have outcome proofs
        if not evidence.outcome_proofs:
            validation_errors.append(
                "No outcome proofs found - recap has no source evidence"
            )

        # Check 3: All outcomes must be verified
        if not evidence.source_verified:
            validation_errors.append(
                "Source verification failed - not all outcomes verified against canonical storage"
            )

        # Check 4: Must have valid timestamp
        if not evidence.recap_timestamp_utc:
            validation_errors.append("Missing recap timestamp")
        else:
            try:
                recap_ts = datetime.fromisoformat(
                    evidence.recap_timestamp_utc.replace("Z", "+00:00")
                )
                details["recap_timestamp"] = recap_ts.isoformat()
            except ValueError:
                validation_errors.append(
                    f"Invalid recap timestamp format: {evidence.recap_timestamp_utc}"
                )

        # Build details
        details.update(
            {
                "trade_count": evidence.trade_count,
                "outcome_count": len(evidence.outcome_proofs),
                "total_pnl": evidence.total_pnl,
                "win_count": evidence.win_count,
                "loss_count": evidence.loss_count,
                "source_verified": evidence.source_verified,
                "recap_message_id": evidence.recap_message_id,
            }
        )

        # Determine status
        if validation_errors:
            return GateResult(
                gate_name="G5_RECAP",
                status=GateStatus.FAIL,
                message=f"G5 RECAP FAIL: {'; '.join(validation_errors)}",
                evidence=evidence,
                details=details,
            )

        return GateResult(
            gate_name="G5_RECAP",
            status=GateStatus.PASS,
            message="G5 RECAP PASS: Recap message verified against canonical outcomes",
            evidence=evidence,
            details=details,
        )

    async def validate_recap_message(
        self,
        recap_message: DiscordMessageEvidence,
        proof_window_start: datetime,
        proof_window_end: datetime,
    ) -> GateResult:
        """Complete validation of a recap message.

        Combines source validation and G5 validation in one call.

        Args:
            recap_message: The recap message to validate
            proof_window_start: Start of valid proof window (UTC)
            proof_window_end: End of valid proof window (UTC)

        Returns:
            GateResult with pass/fail status
        """
        # First, validate the source
        evidence = await self.validate_recap_source(
            recap_message, proof_window_start, proof_window_end
        )

        # Then run G5 validation
        return self.validate_g5_recap(evidence)


# Convenience functions for integration


def create_recap_validator(
    redis_collector: Any | None = None,
    influx_collector: Any | None = None,
) -> RecapValidator:
    """Create a RecapValidator with the given collectors.

    Args:
        redis_collector: Redis collector instance
        influx_collector: InfluxDB collector instance

    Returns:
        Configured RecapValidator
    """
    return RecapValidator(
        redis_collector=redis_collector,
        influx_collector=influx_collector,
    )


async def main() -> None:
    """CLI entry point for testing."""
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Recap Validator for G5")
    parser.add_argument(
        "--recap-content",
        type=str,
        help="Recap message content to validate",
    )
    parser.add_argument(
        "--recap-message-id",
        type=str,
        help="Discord message ID",
    )
    parser.add_argument(
        "--window-start",
        type=str,
        help="Proof window start (ISO format)",
    )
    parser.add_argument(
        "--window-end",
        type=str,
        help="Proof window end (ISO format)",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output file for results (JSON)",
    )

    args = parser.parse_args()

    # Create validator (without collectors for dry-run)
    validator = RecapValidator()

    # Parse time window
    now = datetime.now(UTC)
    window_start = now - timedelta(minutes=30)
    window_end = now

    if args.window_start:
        window_start = datetime.fromisoformat(args.window_start.replace("Z", "+00:00"))
    if args.window_end:
        window_end = datetime.fromisoformat(args.window_end.replace("Z", "+00:00"))

    # Create mock recap message
    recap = DiscordMessageEvidence(
        message_id=args.recap_message_id or "1234567890123456789",
        channel_id="1444447985378398459",
        channel_name="trading",
        timestamp_utc=now.isoformat(),
        content_type="RECAP",
        content_snippet=args.recap_content or "Daily RECAP - Trade ID: TEST123",
        is_bot=True,
    )

    # Run validation
    result = await validator.validate_recap_message(recap, window_start, window_end)

    output = json.dumps(result.to_dict(), indent=2)

    if args.output:
        with open(args.output, "w") as f:
            f.write(output)
        print(f"Results written to {args.output}")
    else:
        print(output)


if __name__ == "__main__":
    asyncio.run(main())
