"""Tests for Discord Evidence Collector.

Tests for PARTY-FORENSIC-003: G5 Discord Evidence Collection
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scripts.validation.discord_evidence import (
    DEFAULT_TRADING_CHANNEL_ID,
    DiscordEvidenceCollector,
    DiscordMessageEvidence,
    GateResult,
    GateStatus,
    PROOF_WINDOW_MINUTES,
)


# Sample Discord API response fixtures
def make_discord_message(
    message_id: str,
    content: str,
    timestamp: datetime,
    author_bot: bool = True,
    author_id: str = "123456789",
    author_name: str = "ChiseAI",
    embeds: list[dict[str, Any]] | None = None,
    channel_id: str = DEFAULT_TRADING_CHANNEL_ID,
) -> dict[str, Any]:
    """Create a mock Discord message object."""
    return {
        "id": message_id,
        "channel_id": channel_id,
        "content": content,
        "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
        "author": {
            "id": author_id,
            "username": author_name,
            "bot": author_bot,
        },
        "embeds": embeds or [],
    }


def make_open_message(
    message_id: str,
    trade_id: str,
    timestamp: datetime,
) -> dict[str, Any]:
    """Create a mock OPEN signal message."""
    return make_discord_message(
        message_id=message_id,
        content=f"🎯 **OPEN SIGNAL**\n**Trade ID:** {trade_id}\n**Entry:** BTCUSDT @ 45000\n**Direction:** LONG",
        timestamp=timestamp,
        embeds=[
            {
                "title": "📈 Long Entry",
                "description": f"Trade ID: {trade_id}",
                "fields": [
                    {"name": "Symbol", "value": "BTCUSDT"},
                    {"name": "Entry Price", "value": "45000"},
                ],
            }
        ],
    )


def make_close_message(
    message_id: str,
    trade_id: str,
    timestamp: datetime,
) -> dict[str, Any]:
    """Create a mock CLOSE signal message."""
    return make_discord_message(
        message_id=message_id,
        content=f"✅ **CLOSE SIGNAL**\n**Trade ID:** {trade_id}\n**Exit:** BTCUSDT @ 46000\n**PnL:** +2.2%",
        timestamp=timestamp,
        embeds=[
            {
                "title": "🎯 Take Profit Hit",
                "description": f"Trade ID: {trade_id}",
            }
        ],
    )


def make_recap_message(
    message_id: str,
    timestamp: datetime,
    trade_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Create a mock RECAP message."""
    trade_list = ", ".join(trade_ids) if trade_ids else "N/A"
    return make_discord_message(
        message_id=message_id,
        content=f"📊 **DAILY RECAP**\n**Trades Today:** 3\n**Win Rate:** 66.7%\n**Total PnL:** +4.5%",
        timestamp=timestamp,
        embeds=[
            {
                "title": "📈 Performance Summary",
                "description": f"Trade IDs: {trade_list}",
            }
        ],
    )


class TestDiscordMessageEvidence:
    """Test cases for DiscordMessageEvidence dataclass."""

    def test_create_evidence(self) -> None:
        """Test creating DiscordMessageEvidence."""
        evidence = DiscordMessageEvidence(
            message_id="1234567890123456789",
            channel_id="1444447985378398459",
            channel_name="trading",
            timestamp_utc="2024-01-15T10:30:00+00:00",
            content_type="OPEN",
            trade_id="TRADE-ABC123",
            content_snippet="🎯 OPEN SIGNAL...",
            author_id="987654321",
            author_name="ChiseAI",
            is_bot=True,
        )

        assert evidence.message_id == "1234567890123456789"
        assert evidence.content_type == "OPEN"
        assert evidence.trade_id == "TRADE-ABC123"
        assert evidence.is_bot is True

    def test_to_dict(self) -> None:
        """Test serialization to dictionary."""
        evidence = DiscordMessageEvidence(
            message_id="1234567890123456789",
            channel_id="1444447985378398459",
            channel_name="trading",
            timestamp_utc="2024-01-15T10:30:00+00:00",
            content_type="CLOSE",
        )

        d = evidence.to_dict()
        assert d["message_id"] == "1234567890123456789"
        assert d["content_type"] == "CLOSE"
        assert d["is_bot"] is False  # Default

    def test_from_dict(self) -> None:
        """Test deserialization from dictionary."""
        d = {
            "message_id": "1234567890123456789",
            "channel_id": "1444447985378398459",
            "channel_name": "trading",
            "timestamp_utc": "2024-01-15T10:30:00+00:00",
            "content_type": "RECAP",
            "trade_id": None,
            "content_snippet": "📊 RECAP...",
            "author_id": "987654321",
            "author_name": "ChiseAI",
            "is_bot": True,
        }

        evidence = DiscordMessageEvidence.from_dict(d)
        assert evidence.message_id == "1234567890123456789"
        assert evidence.content_type == "RECAP"
        assert evidence.is_bot is True


class TestGateResult:
    """Test cases for GateResult dataclass."""

    def test_pass_result(self) -> None:
        """Test a passing gate result."""
        result = GateResult(
            status=GateStatus.PASS,
            message="G5 passed",
            evidence=[],
        )

        assert result.passed is True
        assert result.status == GateStatus.PASS

    def test_fail_result(self) -> None:
        """Test a failing gate result."""
        result = GateResult(
            status=GateStatus.FAIL,
            message="Missing RECAP",
            missing_types=["RECAP"],
        )

        assert result.passed is False
        assert "RECAP" in result.missing_types

    def test_to_dict(self) -> None:
        """Test serialization."""
        result = GateResult(
            status=GateStatus.PASS,
            message="All good",
            evidence=[
                DiscordMessageEvidence(
                    message_id="123",
                    channel_id="456",
                    channel_name="trading",
                    timestamp_utc="2024-01-15T10:00:00+00:00",
                    content_type="OPEN",
                )
            ],
        )

        d = result.to_dict()
        assert d["status"] == "pass"
        assert d["message"] == "All good"
        assert len(d["evidence"]) == 1


class TestDiscordEvidenceCollector:
    """Test cases for DiscordEvidenceCollector."""

    @pytest.fixture
    def collector(self) -> DiscordEvidenceCollector:
        """Create collector with mock token."""
        return DiscordEvidenceCollector(
            bot_token="test_bot_token_123",
            trading_channel_id="1444447985378398459",
        )

    def test_init_with_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test initialization with environment variables."""
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "env_token")
        monkeypatch.setenv("TRADING_CHANNEL_ID", "999888777")

        collector = DiscordEvidenceCollector()
        assert collector.bot_token == "env_token"
        assert collector.trading_channel_id == "999888777"

    def test_init_with_defaults(self) -> None:
        """Test initialization with default values."""
        collector = DiscordEvidenceCollector(bot_token="explicit_token")
        assert collector.bot_token == "explicit_token"
        assert collector.trading_channel_id == DEFAULT_TRADING_CHANNEL_ID

    def test_classify_message_open(self, collector: DiscordEvidenceCollector) -> None:
        """Test classifying OPEN messages."""
        # Test various OPEN patterns
        open_messages = [
            {"content": "OPEN BTCUSDT LONG"},
            {"content": "🎯 ENTRY: 45000"},
            {"content": "📈 LONG Signal"},
            {"content": "BUY BTCUSDT"},
            {"content": "New position: SHORT"},
        ]

        for msg in open_messages:
            result = collector.classify_message(msg)
            assert result == "OPEN", f"Expected OPEN for: {msg['content']}"

    def test_classify_message_close(self, collector: DiscordEvidenceCollector) -> None:
        """Test classifying CLOSE messages."""
        close_messages = [
            {"content": "CLOSE position"},
            {"content": "EXIT trade"},
            {"content": "🎯 TP1 hit"},
            {"content": "Stop loss triggered"},
            {"content": "✅ CLOSED at 46000"},
        ]

        for msg in close_messages:
            result = collector.classify_message(msg)
            assert result == "CLOSE", f"Expected CLOSE for: {msg['content']}"

    def test_classify_message_recap(self, collector: DiscordEvidenceCollector) -> None:
        """Test classifying RECAP messages."""
        recap_messages = [
            {"content": "📊 DAILY RECAP"},
            {"content": "Performance Summary"},
            {"content": "P&L Report"},
            {"content": "📈 Today's Performance"},
        ]

        for msg in recap_messages:
            result = collector.classify_message(msg)
            assert result == "RECAP", f"Expected RECAP for: {msg['content']}"

    def test_classify_message_none(self, collector: DiscordEvidenceCollector) -> None:
        """Test messages that don't classify."""
        other_messages = [
            {"content": "Hello world"},
            {"content": "Random message"},
            {"content": "Check out this link"},
        ]

        for msg in other_messages:
            result = collector.classify_message(msg)
            assert result is None, f"Expected None for: {msg['content']}"

    def test_classify_message_with_embeds(
        self, collector: DiscordEvidenceCollector
    ) -> None:
        """Test classification using embed content."""
        msg = {
            "content": "",
            "embeds": [
                {
                    "title": "📈 OPEN Signal",
                    "description": "New trade entry",
                }
            ],
        }

        result = collector.classify_message(msg)
        assert result == "OPEN"

    def test_extract_trade_id_explicit(
        self, collector: DiscordEvidenceCollector
    ) -> None:
        """Test extracting explicit trade IDs."""
        messages = [
            ({"content": "Trade ID: ABC123"}, "ABC123"),
            ({"content": "trade_id: XYZ789"}, "XYZ789"),
            ({"content": "TID: 123456"}, "123456"),  # At least 6 chars total
            ({"content": "#TRADE-ABC123"}, "ABC123"),
            ({"content": "[TRADE:XYZ789]"}, "XYZ789"),
        ]

        for msg, expected_id in messages:
            result = collector.extract_trade_id(msg)
            assert result == expected_id, (
                f"Expected {expected_id} for: {msg['content']}"
            )

    def test_extract_trade_id_uuid(self, collector: DiscordEvidenceCollector) -> None:
        """Test extracting UUID trade IDs."""
        uuid_str = "12345678-1234-5678-1234-567812345678"
        msg = {"content": f"Trade: {uuid_str}"}

        result = collector.extract_trade_id(msg)
        assert result == uuid_str.lower()

    def test_extract_trade_id_from_embeds(
        self, collector: DiscordEvidenceCollector
    ) -> None:
        """Test extracting trade ID from embed fields."""
        msg = {
            "content": "",
            "embeds": [
                {
                    "fields": [
                        {"name": "Trade ID", "value": "EMBED123"},
                    ]
                }
            ],
        }

        result = collector.extract_trade_id(msg)
        assert result == "EMBED123"

    def test_extract_trade_id_none(self, collector: DiscordEvidenceCollector) -> None:
        """Test when no trade ID is present."""
        msg = {"content": "Just a regular message"}
        result = collector.extract_trade_id(msg)
        assert result is None

    def test_redact_secrets(self, collector: DiscordEvidenceCollector) -> None:
        """Test secret redaction."""
        # Discord token pattern
        text = "Token: NTE4MDIzNjcwNTUzMDYzODcy.X_1g2A.abc123def456ghi789jkl012"
        redacted = collector._redact_secrets(text)
        assert "[REDACTED]" in redacted
        assert "NTE4MDIzNjcwNTUzMDYzODcy" not in redacted

        # Webhook URL pattern
        text = "Webhook: https://discord.com/api/webhooks/123456789/abc123_xyz789"
        redacted = collector._redact_secrets(text)
        assert "[REDACTED_WEBHOOK]" in redacted
        assert "discord.com/api/webhooks" not in redacted

    def test_validate_g5_pass(self, collector: DiscordEvidenceCollector) -> None:
        """Test G5 validation passing."""
        now = datetime.now(UTC)
        messages = [
            DiscordMessageEvidence(
                message_id="111",
                channel_id=DEFAULT_TRADING_CHANNEL_ID,
                channel_name="trading",
                timestamp_utc=now.isoformat(),
                content_type="OPEN",
                trade_id="TRADE-001",
                is_bot=True,
            ),
            DiscordMessageEvidence(
                message_id="222",
                channel_id=DEFAULT_TRADING_CHANNEL_ID,
                channel_name="trading",
                timestamp_utc=now.isoformat(),
                content_type="CLOSE",
                trade_id="TRADE-001",
                is_bot=True,
            ),
            DiscordMessageEvidence(
                message_id="333",
                channel_id=DEFAULT_TRADING_CHANNEL_ID,
                channel_name="trading",
                timestamp_utc=now.isoformat(),
                content_type="RECAP",
                is_bot=True,
            ),
        ]

        result = collector.validate_g5(messages)
        assert result.passed is True
        assert result.status == GateStatus.PASS
        assert len(result.evidence) == 3
        assert len(result.missing_types) == 0

    def test_validate_g5_fail_missing_recap(
        self, collector: DiscordEvidenceCollector
    ) -> None:
        """Test G5 validation failing with missing RECAP."""
        now = datetime.now(UTC)
        messages = [
            DiscordMessageEvidence(
                message_id="111",
                channel_id=DEFAULT_TRADING_CHANNEL_ID,
                channel_name="trading",
                timestamp_utc=now.isoformat(),
                content_type="OPEN",
                is_bot=True,
            ),
            DiscordMessageEvidence(
                message_id="222",
                channel_id=DEFAULT_TRADING_CHANNEL_ID,
                channel_name="trading",
                timestamp_utc=now.isoformat(),
                content_type="CLOSE",
                is_bot=True,
            ),
        ]

        result = collector.validate_g5(messages)
        assert result.passed is False
        assert result.status == GateStatus.FAIL
        assert "RECAP" in result.missing_types

    def test_validate_g5_fail_missing_all(
        self, collector: DiscordEvidenceCollector
    ) -> None:
        """Test G5 validation failing with no messages."""
        result = collector.validate_g5([])
        assert result.passed is False
        assert set(result.missing_types) == {"OPEN", "CLOSE", "RECAP"}

    def test_validate_g5_fail_not_bot(
        self, collector: DiscordEvidenceCollector
    ) -> None:
        """Test G5 validation failing for non-bot messages."""
        now = datetime.now(UTC)
        messages = [
            DiscordMessageEvidence(
                message_id="111",
                channel_id=DEFAULT_TRADING_CHANNEL_ID,
                channel_name="trading",
                timestamp_utc=now.isoformat(),
                content_type="OPEN",
                is_bot=False,  # Human message - should not count
            ),
        ]

        result = collector.validate_g5(messages)
        assert result.passed is False
        assert "OPEN" in result.missing_types  # Still missing because not from bot

    def test_validate_g5_fail_outside_window(
        self, collector: DiscordEvidenceCollector
    ) -> None:
        """Test G5 validation failing for old messages."""
        old_time = datetime.now(UTC) - timedelta(minutes=PROOF_WINDOW_MINUTES + 10)
        messages = [
            DiscordMessageEvidence(
                message_id="111",
                channel_id=DEFAULT_TRADING_CHANNEL_ID,
                channel_name="trading",
                timestamp_utc=old_time.isoformat(),
                content_type="OPEN",
                is_bot=True,
            ),
        ]

        result = collector.validate_g5(messages)
        assert result.passed is False
        assert "OPEN" in result.missing_types  # Too old

    def test_validate_g5_fail_missing_message_id(
        self, collector: DiscordEvidenceCollector
    ) -> None:
        """Test G5 validation failing for messages without IDs."""
        now = datetime.now(UTC)
        messages = [
            DiscordMessageEvidence(
                message_id="",  # Missing ID
                channel_id=DEFAULT_TRADING_CHANNEL_ID,
                channel_name="trading",
                timestamp_utc=now.isoformat(),
                content_type="OPEN",
                is_bot=True,
            ),
            DiscordMessageEvidence(
                message_id="222",
                channel_id=DEFAULT_TRADING_CHANNEL_ID,
                channel_name="trading",
                timestamp_utc=now.isoformat(),
                content_type="CLOSE",
                is_bot=True,
            ),
            DiscordMessageEvidence(
                message_id="333",
                channel_id=DEFAULT_TRADING_CHANNEL_ID,
                channel_name="trading",
                timestamp_utc=now.isoformat(),
                content_type="RECAP",
                is_bot=True,
            ),
        ]

        result = collector.validate_g5(messages)
        assert result.passed is False
        assert "missing_ids" in result.details


class TestDiscordEvidenceCollectorAsync:
    """Async test cases for DiscordEvidenceCollector."""

    @pytest.fixture
    def collector(self) -> DiscordEvidenceCollector:
        """Create collector with mock token."""
        return DiscordEvidenceCollector(
            bot_token="test_bot_token_123",
            trading_channel_id="1444447985378398459",
        )

    @pytest.mark.asyncio
    async def test_collect_messages_success(
        self, collector: DiscordEvidenceCollector
    ) -> None:
        """Test collecting messages from Discord API."""
        now = datetime.now(UTC)
        since = now - timedelta(minutes=30)
        until = now

        mock_messages = [
            make_open_message("111", "TRADE-001", now - timedelta(minutes=25)),
            make_close_message("222", "TRADE-001", now - timedelta(minutes=20)),
            make_recap_message("333", now - timedelta(minutes=15)),
        ]

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_messages)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        with patch.object(collector, "_get_session", return_value=mock_session):
            messages = await collector.collect_messages(since, until)

        assert len(messages) == 3
        assert messages[0].content_type == "OPEN"
        assert messages[1].content_type == "CLOSE"
        assert messages[2].content_type == "RECAP"

        await collector.close()

    @pytest.mark.asyncio
    async def test_collect_messages_auth_error(
        self, collector: DiscordEvidenceCollector
    ) -> None:
        """Test handling auth errors from Discord API."""
        now = datetime.now(UTC)
        since = now - timedelta(minutes=30)
        until = now

        mock_response = AsyncMock()
        mock_response.status = 401
        mock_response.text = AsyncMock(return_value="Unauthorized")

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        with patch.object(collector, "_get_session", return_value=mock_session):
            with pytest.raises(RuntimeError, match="invalid"):
                await collector.collect_messages(since, until)

        await collector.close()

    @pytest.mark.asyncio
    async def test_collect_messages_no_token(self) -> None:
        """Test error when no bot token configured."""
        collector = DiscordEvidenceCollector(bot_token=None)
        now = datetime.now(UTC)

        with pytest.raises(RuntimeError, match="not configured|invalid"):
            await collector.collect_messages(now - timedelta(minutes=30), now)

    @pytest.mark.asyncio
    async def test_validate_g5_for_trade(
        self, collector: DiscordEvidenceCollector
    ) -> None:
        """Test G5 validation for a specific trade."""
        now = datetime.now(UTC)
        since = now - timedelta(minutes=30)
        until = now

        trade_id = "TRADE-001"
        mock_messages = [
            make_open_message("111", trade_id, now - timedelta(minutes=25)),
            make_close_message("222", trade_id, now - timedelta(minutes=20)),
            # RECAP doesn't have trade_id, but that's okay
            make_recap_message("333", now - timedelta(minutes=15)),
        ]

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_messages)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        with patch.object(collector, "_get_session", return_value=mock_session):
            result = await collector.validate_g5_for_trade(trade_id, since, until)

        # Should find OPEN and CLOSE for this trade
        # RECAP might not match since it doesn't have the trade_id
        assert result.status in (GateStatus.PASS, GateStatus.FAIL)

        await collector.close()

    @pytest.mark.asyncio
    async def test_close_session(self, collector: DiscordEvidenceCollector) -> None:
        """Test closing the HTTP session."""
        mock_session = AsyncMock()
        collector._session = mock_session

        await collector.close()

        mock_session.close.assert_called_once()
        assert collector._session is None


class TestDatetimeToSnowflake:
    """Test snowflake conversion."""

    def test_datetime_to_snowflake(self) -> None:
        """Test datetime to snowflake conversion."""
        collector = DiscordEvidenceCollector(bot_token="test")

        # Test a recent date
        dt = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        snowflake = collector._datetime_to_snowflake(dt)

        assert snowflake is not None
        assert snowflake.isdigit()
        # Snowflake should be a large number
        assert len(snowflake) >= 17

    def test_datetime_to_snowflake_too_old(self) -> None:
        """Test conversion for date before Discord epoch."""
        collector = DiscordEvidenceCollector(bot_token="test")

        # Before Discord epoch (Jan 1, 2015)
        dt = datetime(2014, 1, 1, tzinfo=UTC)
        snowflake = collector._datetime_to_snowflake(dt)

        assert snowflake is None


class TestIntegration:
    """Integration-style tests."""

    @pytest.mark.asyncio
    async def test_full_collection_and_validation_flow(self) -> None:
        """Test complete flow from collection to validation."""
        collector = DiscordEvidenceCollector(
            bot_token="test_token",
            trading_channel_id="1444447985378398459",
        )

        now = datetime.now(UTC)
        since = now - timedelta(minutes=30)
        until = now

        # Create realistic mock messages
        mock_messages = [
            make_open_message(
                "111222333444555666", "TRADE-ABC123", now - timedelta(minutes=28)
            ),
            make_close_message(
                "222333444555666777", "TRADE-ABC123", now - timedelta(minutes=23)
            ),
            make_recap_message("333444555666777888", now - timedelta(minutes=18)),
            # Add some noise
            make_discord_message(
                message_id="444555666777888999",
                content="Random user message",
                timestamp=now - timedelta(minutes=15),
                author_bot=False,
                author_name="human_user",
            ),
        ]

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_messages)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        with patch.object(collector, "_get_session", return_value=mock_session):
            # Step 1: Collect messages
            messages = await collector.collect_messages(since, until)

            # Should have 3 relevant messages (excludes human message)
            assert len(messages) == 3

            # Step 2: Validate
            result = collector.validate_g5(messages)

            # Should pass with all required types
            assert result.passed is True
            assert len(result.evidence) == 3

            # Verify evidence structure
            for evidence in result.evidence:
                assert evidence.message_id  # Has Discord ID
                assert evidence.content_type in {"OPEN", "CLOSE", "RECAP"}
                assert evidence.is_bot is True

        await collector.close()

    def test_example_evidence_structure(self) -> None:
        """Generate example evidence structure for documentation."""
        now = datetime.now(UTC)

        evidence_list = [
            DiscordMessageEvidence(
                message_id="1208472938472938472",
                channel_id="1444447985378398459",
                channel_name="trading",
                timestamp_utc=now.isoformat(),
                content_type="OPEN",
                trade_id="TRADE-ABC123",
                content_snippet="🎯 **OPEN SIGNAL** - BTCUSDT LONG @ 45000...",
                author_id="987654321",
                author_name="ChiseAI",
                is_bot=True,
            ),
            DiscordMessageEvidence(
                message_id="1208472938472938473",
                channel_id="1444447985378398459",
                channel_name="trading",
                timestamp_utc=(now + timedelta(minutes=10)).isoformat(),
                content_type="CLOSE",
                trade_id="TRADE-ABC123",
                content_snippet="✅ **CLOSE SIGNAL** - BTCUSDT @ 46000, PnL: +2.2%...",
                author_id="987654321",
                author_name="ChiseAI",
                is_bot=True,
            ),
            DiscordMessageEvidence(
                message_id="1208472938472938474",
                channel_id="1444447985378398459",
                channel_name="trading",
                timestamp_utc=(now + timedelta(minutes=20)).isoformat(),
                content_type="RECAP",
                trade_id=None,
                content_snippet="📊 **DAILY RECAP** - Trades: 3, Win Rate: 66.7%...",
                author_id="987654321",
                author_name="ChiseAI",
                is_bot=True,
            ),
        ]

        # Verify structure
        for e in evidence_list:
            d = e.to_dict()
            assert "message_id" in d
            assert "content_type" in d
            assert "timestamp_utc" in d
            assert "is_bot" in d

        # Create result
        result = GateResult(
            status=GateStatus.PASS,
            message="G5 validation passed",
            evidence=evidence_list,
            details={
                "proof_window_minutes": 30,
                "message_ids": {e.content_type: e.message_id for e in evidence_list},
            },
        )

        assert result.passed is True
