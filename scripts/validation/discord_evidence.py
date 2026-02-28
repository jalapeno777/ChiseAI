#!/usr/bin/env python3
"""
Discord Evidence Collector for G5 Validation.

Collects and validates Discord message evidence for G5 gate validation:
- OPEN message with Discord message ID
- CLOSE message with Discord message ID
- RECAP message with Discord message ID
- All messages must be within proof window (30 minutes)
- Must link Discord messages to runtime trade IDs
- No manual Discord sends count for G5 pass

For PARTY-FORENSIC-003: G5 Discord Evidence Collection
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# Trading channel ID (can be overridden via env)
DEFAULT_TRADING_CHANNEL_ID = "1444447985378398459"
PROOF_WINDOW_MINUTES = 30


class GateStatus(str, Enum):
    """Status of a validation gate."""

    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"
    SKIP = "skip"


@dataclass
class DiscordMessageEvidence:
    """Evidence of a Discord message for validation.

    Attributes:
        message_id: Discord message snowflake ID
        channel_id: Discord channel ID
        channel_name: Channel name (e.g., "trading")
        timestamp_utc: ISO timestamp of message
        content_type: Message type - "OPEN", "CLOSE", or "RECAP"
        trade_id: Optional trade ID extracted from message
        content_snippet: First 100 chars of content (secrets redacted)
        author_id: Discord author ID
        author_name: Discord author username
        is_bot: Whether message was sent by a bot (required for G5)
    """

    message_id: str
    channel_id: str
    channel_name: str
    timestamp_utc: str
    content_type: str  # "OPEN", "CLOSE", "RECAP"
    trade_id: str | None = None
    content_snippet: str = ""
    author_id: str | None = None
    author_name: str | None = None
    is_bot: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "message_id": self.message_id,
            "channel_id": self.channel_id,
            "channel_name": self.channel_name,
            "timestamp_utc": self.timestamp_utc,
            "content_type": self.content_type,
            "trade_id": self.trade_id,
            "content_snippet": self.content_snippet,
            "author_id": self.author_id,
            "author_name": self.author_name,
            "is_bot": self.is_bot,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DiscordMessageEvidence:
        """Create from dictionary."""
        return cls(
            message_id=data["message_id"],
            channel_id=data["channel_id"],
            channel_name=data["channel_name"],
            timestamp_utc=data["timestamp_utc"],
            content_type=data["content_type"],
            trade_id=data.get("trade_id"),
            content_snippet=data.get("content_snippet", ""),
            author_id=data.get("author_id"),
            author_name=data.get("author_name"),
            is_bot=data.get("is_bot", False),
        )


@dataclass
class GateResult:
    """Result of a G5 validation gate.

    Attributes:
        gate_name: Name of the gate (e.g., "G5")
        status: Pass/fail/error/skip status
        message: Human-readable result message
        evidence: List of evidence supporting the result
        missing_types: List of missing message types (if any)
        details: Additional details dictionary
        timestamp: When validation was performed
    """

    gate_name: str = "G5"
    status: GateStatus = GateStatus.FAIL
    message: str = ""
    evidence: list[DiscordMessageEvidence] = field(default_factory=list)
    missing_types: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "gate_name": self.gate_name,
            "status": self.status.value,
            "message": self.message,
            "evidence": [e.to_dict() for e in self.evidence],
            "missing_types": self.missing_types,
            "details": self.details,
            "timestamp": self.timestamp,
        }

    @property
    def passed(self) -> bool:
        """Check if gate passed."""
        return self.status == GateStatus.PASS


class DiscordEvidenceCollector:
    """Collects Discord message evidence for G5 validation.

    Uses Discord bot API to retrieve messages from #trading channel
    and validates that required message types (OPEN, CLOSE, RECAP)
    are present with proper message IDs within the proof window.

    Attributes:
        bot_token: Discord bot token
        trading_channel_id: Trading channel ID to monitor
        _session: aiohttp ClientSession (lazy initialization)
    """

    REQUIRED_MESSAGE_TYPES = {"OPEN", "CLOSE", "RECAP"}
    DISCORD_API_BASE = "https://discord.com/api/v10"
    MAX_MESSAGES_PER_FETCH = 100

    def __init__(
        self,
        bot_token: str | None = None,
        trading_channel_id: str | None = None,
    ):
        """Initialize the collector.

        Args:
            bot_token: Discord bot token (falls back to DISCORD_BOT_TOKEN env var)
            trading_channel_id: Trading channel ID (falls back to TRADING_CHANNEL_ID env var)
        """
        self.bot_token = bot_token or os.getenv("DISCORD_BOT_TOKEN")
        self.trading_channel_id = (
            trading_channel_id
            or os.getenv("TRADING_CHANNEL_ID")
            or DEFAULT_TRADING_CHANNEL_ID
        )
        self._session: Any | None = None

    async def _get_session(self) -> Any:
        """Get or create aiohttp session.

        Returns:
            aiohttp ClientSession
        """
        if self._session is None:
            try:
                import aiohttp

                self._session = aiohttp.ClientSession()
            except ImportError:
                logger.error("aiohttp not installed")
                raise RuntimeError("aiohttp is required for Discord API calls")
        return self._session

    async def close(self) -> None:
        """Close the HTTP session."""
        if self._session:
            await self._session.close()
            self._session = None

    async def collect_messages(
        self,
        since: datetime,
        until: datetime,
    ) -> list[DiscordMessageEvidence]:
        """Collect messages from #trading within time window.

        Args:
            since: Start of time window (UTC)
            until: End of time window (UTC)

        Returns:
            List of DiscordMessageEvidence for relevant messages

        Raises:
            RuntimeError: If Discord API access fails
        """
        if not self.bot_token:
            raise RuntimeError("DISCORD_BOT_TOKEN not configured")

        evidence_list: list[DiscordMessageEvidence] = []
        session = await self._get_session()

        headers = {"Authorization": f"Bot {self.bot_token}"}

        # Calculate snowflake-based pagination
        # Discord uses snowflake IDs which are time-sortable
        after_snowflake = self._datetime_to_snowflake(since)
        before_snowflake = self._datetime_to_snowflake(until)

        url = (
            f"{self.DISCORD_API_BASE}/channels/{self.trading_channel_id}/messages"
            f"?limit={self.MAX_MESSAGES_PER_FETCH}"
        )

        if after_snowflake:
            url += f"&after={after_snowflake}"

        try:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 401:
                    raise RuntimeError("Discord bot token is invalid")
                elif resp.status == 403:
                    raise RuntimeError("Bot lacks permission to read channel messages")
                elif resp.status == 404:
                    raise RuntimeError(f"Channel {self.trading_channel_id} not found")
                elif resp.status != 200:
                    body = await resp.text()
                    raise RuntimeError(f"Discord API error: {resp.status} - {body}")

                messages = await resp.json()

            for msg in messages:
                evidence = self._parse_message(msg, since, until)
                if evidence:
                    evidence_list.append(evidence)

            logger.info(
                f"Collected {len(evidence_list)} relevant messages "
                f"from {since.isoformat()} to {until.isoformat()}"
            )

        except Exception as e:
            logger.error(f"Failed to collect Discord messages: {e}")
            raise

        return evidence_list

    def _datetime_to_snowflake(self, dt: datetime) -> str | None:
        """Convert datetime to Discord snowflake ID.

        Discord snowflakes are based on timestamp since Jan 1, 2015.
        This is approximate and used for pagination.

        Args:
            dt: Datetime to convert

        Returns:
            Approximate snowflake ID or None if too old
        """
        # Discord epoch: Jan 1, 2015 00:00:00 UTC
        discord_epoch = datetime(2015, 1, 1, tzinfo=UTC)
        if dt < discord_epoch:
            return None

        # Snowflake format: timestamp (42 bits) + internal worker ID + sequence
        # We just need approximate timestamp-based ID
        millis = int((dt - discord_epoch).total_seconds() * 1000)
        # Shift left 22 bits (for worker + sequence bits)
        return str(millis << 22)

    def _parse_message(
        self,
        msg: dict[str, Any],
        since: datetime,
        until: datetime,
    ) -> DiscordMessageEvidence | None:
        """Parse a Discord message into evidence.

        Args:
            msg: Raw Discord message dict
            since: Start of valid time window
            until: End of valid time window

        Returns:
            DiscordMessageEvidence if message is relevant, None otherwise
        """
        # Parse timestamp
        timestamp_str = msg.get("timestamp", "")
        try:
            # Discord timestamps are ISO 8601
            if timestamp_str.endswith("Z"):
                timestamp_str = timestamp_str[:-1] + "+00:00"
            msg_time = datetime.fromisoformat(timestamp_str.replace("+00:00", ""))
            msg_time = msg_time.replace(tzinfo=UTC)
        except (ValueError, TypeError):
            logger.warning(f"Could not parse timestamp: {timestamp_str}")
            return None

        # Check time window
        if msg_time < since or msg_time > until:
            return None

        # Get content and classify
        content = msg.get("content", "")
        embeds = msg.get("embeds", [])

        # Combine content and embed titles/descriptions for classification
        full_content = content
        for embed in embeds:
            if embed.get("title"):
                full_content += " " + embed["title"]
            if embed.get("description"):
                full_content += " " + embed["description"]

        content_type = self.classify_message(msg)
        if not content_type:
            return None

        # Extract trade ID
        trade_id = self.extract_trade_id(msg)

        # Create snippet with secrets redacted
        snippet = self._redact_secrets(full_content[:100])

        # Get author info
        author = msg.get("author", {})
        is_bot = author.get("bot", False)

        return DiscordMessageEvidence(
            message_id=msg.get("id", ""),
            channel_id=msg.get("channel_id", self.trading_channel_id),
            channel_name="trading",
            timestamp_utc=msg_time.isoformat(),
            content_type=content_type,
            trade_id=trade_id,
            content_snippet=snippet,
            author_id=author.get("id"),
            author_name=author.get("username"),
            is_bot=is_bot,
        )

    def classify_message(self, message: dict[str, Any]) -> str | None:
        """Classify message as OPEN, CLOSE, RECAP, or None.

        Looks for keywords in message content and embeds.

        Args:
            message: Raw Discord message dict

        Returns:
            Message type string or None if not a trade message
        """
        content = message.get("content", "").upper()
        embeds = message.get("embeds", [])

        # Also check embed titles and descriptions
        for embed in embeds:
            if embed.get("title"):
                content += " " + embed["title"].upper()
            if embed.get("description"):
                content += " " + embed["description"].upper()

        # Check for OPEN signals
        open_patterns = [
            r"\bOPEN\b",
            r"\bENTRY\b",
            r"\bLONG\b",
            r"\bSHORT\b",
            r"\bBUY\b",
            r"\bSELL\b",
            r"🎯\s*ENTRY",
            r"📈\s*LONG",
            r"📉\s*SHORT",
        ]
        for pattern in open_patterns:
            if re.search(pattern, content):
                # Make sure it's not a CLOSE message
                if not re.search(r"\b(CLOSE|EXIT|TP|SL|TAKE\s*PROFIT)\b", content):
                    return "OPEN"

        # Check for CLOSE signals
        close_patterns = [
            r"\bCLOSE\b",
            r"\bEXIT\b",
            r"\bTP\s*\d*\b",
            r"\bSL\b",
            r"\bTAKE\s*PROFIT\b",
            r"\bSTOP\s*LOSS\b",
            r"🎯\s*TP",
            r"🛑\s*SL",
            r"✅\s*(CLOSED|EXIT)",
        ]
        for pattern in close_patterns:
            if re.search(pattern, content):
                return "CLOSE"

        # Check for RECAP signals
        recap_patterns = [
            r"\bRECAP\b",
            r"\bSUMMARY\b",
            r"\bPERFORMANCE\b",
            r"\bP&L\b",
            r"\bPNL\b",
            r"\bDAILY\s*(REVIEW|SUMMARY)\b",
            r"📊\s*(RECAP|SUMMARY)",
            r"📈\s*PERFORMANCE",
        ]
        for pattern in recap_patterns:
            if re.search(pattern, content):
                return "RECAP"

        return None

    def extract_trade_id(self, message: dict[str, Any]) -> str | None:
        """Extract trade ID from message content/embeds.

        Looks for patterns like:
        - Trade ID: ABC123
        - trade_id: ABC123
        - #TRADE-ABC123
        - [TRADE:ABC123]

        Args:
            message: Raw Discord message dict

        Returns:
            Extracted trade ID or None
        """
        content = message.get("content", "")
        embeds = message.get("embeds", [])

        # Combine content sources
        full_content = content
        for embed in embeds:
            if embed.get("title"):
                full_content += " " + embed["title"]
            if embed.get("description"):
                full_content += " " + embed["description"]
            # Check embed fields
            for field in embed.get("fields", []):
                if field.get("name"):
                    full_content += " " + field["name"]
                if field.get("value"):
                    full_content += " " + field["value"]

        # Pattern: Trade ID: VALUE or trade_id: VALUE
        match = re.search(
            r"(?:trade[\s_-]?id|tid)[:\s]+([A-Z0-9][-A-Z0-9]{5,})",
            full_content,
            re.IGNORECASE,
        )
        if match:
            return match.group(1).upper()

        # Pattern: #TRADE-VALUE or [TRADE:VALUE]
        match = re.search(
            r"[#\[]TRADE[:-]?([A-Z0-9][-A-Z0-9]{5,})",
            full_content,
            re.IGNORECASE,
        )
        if match:
            return match.group(1).upper()

        # Pattern: UUID
        match = re.search(
            r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
            full_content,
            re.IGNORECASE,
        )
        if match:
            return match.group(1).lower()

        return None

    def _redact_secrets(self, text: str) -> str:
        """Redact secrets/tokens from text.

        Args:
            text: Text to redact

        Returns:
            Text with secrets replaced by [REDACTED]
        """
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
            r"(api[_-]?key|token|secret|password)[=:]\s*\S+",
            "[REDACTED]",
            text,
            flags=re.IGNORECASE,
        )
        return text

    def validate_g5(
        self,
        messages: list[DiscordMessageEvidence],
        proof_window_minutes: int = PROOF_WINDOW_MINUTES,
    ) -> GateResult:
        """Validate G5: Must have OPEN, CLOSE, RECAP with message IDs.

        G5 Requirements:
        1. At least one OPEN message from bot
        2. At least one CLOSE message from bot
        3. At least one RECAP message from bot
        4. All messages have Discord message IDs
        5. All messages within proof window

        Args:
            messages: List of collected evidence
            proof_window_minutes: Maximum age of messages in minutes

        Returns:
            GateResult with pass/fail status and evidence
        """
        now = datetime.now(UTC)
        cutoff = now - timedelta(minutes=proof_window_minutes)

        # Filter to messages within proof window and from bot
        valid_messages = [
            m
            for m in messages
            if datetime.fromisoformat(m.timestamp_utc) >= cutoff and m.is_bot
        ]

        # Group by content type
        found_types: set[str] = set()
        type_evidence: dict[str, DiscordMessageEvidence] = {}

        for msg in valid_messages:
            if msg.content_type in self.REQUIRED_MESSAGE_TYPES:
                found_types.add(msg.content_type)
                # Keep most recent of each type
                if msg.content_type not in type_evidence:
                    type_evidence[msg.content_type] = msg
                else:
                    existing = type_evidence[msg.content_type]
                    if datetime.fromisoformat(
                        msg.timestamp_utc
                    ) > datetime.fromisoformat(existing.timestamp_utc):
                        type_evidence[msg.content_type] = msg

        # Check for missing types
        missing_types = list(self.REQUIRED_MESSAGE_TYPES - found_types)

        # Build result
        evidence_list = list(type_evidence.values())

        # Check if all required types are present
        if not missing_types:
            # All types present - check message IDs
            missing_ids = [m for m in evidence_list if not m.message_id]
            if missing_ids:
                return GateResult(
                    status=GateStatus.FAIL,
                    message=f"Missing Discord message IDs for: {[m.content_type for m in missing_ids]}",
                    evidence=evidence_list,
                    missing_types=[],
                    details={
                        "proof_window_minutes": proof_window_minutes,
                        "valid_messages_count": len(valid_messages),
                        "missing_ids": [m.content_type for m in missing_ids],
                    },
                )

            # Success!
            trade_ids = [m.trade_id for m in evidence_list if m.trade_id]
            return GateResult(
                status=GateStatus.PASS,
                message="G5 validation passed: All required message types present with IDs",
                evidence=evidence_list,
                missing_types=[],
                details={
                    "proof_window_minutes": proof_window_minutes,
                    "valid_messages_count": len(valid_messages),
                    "trade_ids": trade_ids,
                    "message_ids": {
                        m.content_type: m.message_id for m in evidence_list
                    },
                },
            )

        # Missing required types
        return GateResult(
            status=GateStatus.FAIL,
            message=f"G5 validation failed: Missing message types: {missing_types}",
            evidence=evidence_list,
            missing_types=missing_types,
            details={
                "proof_window_minutes": proof_window_minutes,
                "valid_messages_count": len(valid_messages),
                "found_types": list(found_types),
            },
        )

    async def validate_g5_for_trade(
        self,
        trade_id: str,
        since: datetime,
        until: datetime,
    ) -> GateResult:
        """Validate G5 for a specific trade.

        Collects messages and validates that the specific trade has
        OPEN, CLOSE, and RECAP messages.

        Args:
            trade_id: Trade ID to validate
            since: Start of time window
            until: End of time window

        Returns:
            GateResult for this specific trade
        """
        messages = await self.collect_messages(since, until)

        # Filter to messages for this trade
        trade_messages = [
            m for m in messages if m.trade_id and m.trade_id.lower() == trade_id.lower()
        ]

        if not trade_messages:
            return GateResult(
                status=GateStatus.FAIL,
                message=f"No Discord messages found for trade {trade_id}",
                evidence=[],
                missing_types=list(self.REQUIRED_MESSAGE_TYPES),
                details={
                    "trade_id": trade_id,
                    "search_window": f"{since.isoformat()} to {until.isoformat()}",
                },
            )

        return self.validate_g5(trade_messages)


async def main() -> None:
    """CLI entry point for testing."""
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Discord Evidence Collector for G5")
    parser.add_argument(
        "--since",
        type=str,
        help="Start time (ISO format, e.g., 2024-01-01T00:00:00Z)",
    )
    parser.add_argument(
        "--until",
        type=str,
        help="End time (ISO format)",
    )
    parser.add_argument(
        "--trade-id",
        type=str,
        help="Filter to specific trade ID",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Run G5 validation",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output file for results (JSON)",
    )

    args = parser.parse_args()

    # Parse time window
    until = datetime.now(UTC)
    since = until - timedelta(minutes=PROOF_WINDOW_MINUTES)

    if args.until:
        until = datetime.fromisoformat(args.until.replace("Z", "+00:00"))
    if args.since:
        since = datetime.fromisoformat(args.since.replace("Z", "+00:00"))

    collector = DiscordEvidenceCollector()

    try:
        if args.trade_id:
            result = await collector.validate_g5_for_trade(args.trade_id, since, until)
        elif args.validate:
            messages = await collector.collect_messages(since, until)
            result = collector.validate_g5(messages)
        else:
            messages = await collector.collect_messages(since, until)
            result = {
                "messages": [m.to_dict() for m in messages],
                "count": len(messages),
            }

        output = json.dumps(
            result.to_dict() if isinstance(result, GateResult) else result,
            indent=2,
        )

        if args.output:
            with open(args.output, "w") as f:
                f.write(output)
            print(f"Results written to {args.output}")
        else:
            print(output)

    finally:
        await collector.close()


if __name__ == "__main__":
    asyncio.run(main())
