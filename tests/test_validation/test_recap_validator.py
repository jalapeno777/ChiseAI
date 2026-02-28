#!/usr/bin/env python3
"""
Tests for Recap Validator

Tests the RecapValidator class with mocked dependencies to ensure:
1. Recap messages are validated against canonical outcomes
2. Source proofs are generated correctly
3. G5 validation passes/fails as expected
4. Secrets are redacted from evidence
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from scripts.validation.recap_validator import (
    DiscordMessageEvidence,
    GateResult,
    GateStatus,
    OutcomeSourceProof,
    RecapValidationEvidence,
    RecapValidator,
    create_recap_validator,
)


class TestOutcomeSourceProof:
    """Tests for OutcomeSourceProof dataclass."""

    def test_basic_creation(self):
        """Test creating an OutcomeSourceProof."""
        proof = OutcomeSourceProof(
            outcome_id="OUT123",
            signal_id="SIG456",
            order_id="ORD789",
            fill_id="FILL001",
            timestamp_utc="2026-02-28T12:00:00Z",
            pnl=150.50,
            source_query="HGET outcome:OUT123 *",
            source_database="redis",
        )

        assert proof.outcome_id == "OUT123"
        assert proof.signal_id == "SIG456"
        assert proof.order_id == "ORD789"
        assert proof.fill_id == "FILL001"
        assert proof.timestamp_utc == "2026-02-28T12:00:00Z"
        assert proof.pnl == 150.50
        assert proof.source_query == "HGET outcome:OUT123 *"
        assert proof.source_database == "redis"

    def test_to_dict(self):
        """Test conversion to dictionary."""
        proof = OutcomeSourceProof(
            outcome_id="OUT123",
            signal_id="SIG456",
            order_id="ORD789",
            pnl=100.0,
            source_query="SELECT * FROM outcomes",
            source_database="influx",
        )

        data = proof.to_dict()

        assert data["outcome_id"] == "OUT123"
        assert data["signal_id"] == "SIG456"
        assert data["order_id"] == "ORD789"
        assert data["pnl"] == 100.0
        assert data["source_database"] == "influx"

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "outcome_id": "OUT123",
            "signal_id": "SIG456",
            "order_id": "ORD789",
            "fill_id": "FILL001",
            "timestamp_utc": "2026-02-28T12:00:00Z",
            "pnl": 150.50,
            "source_query": "HGET outcome:OUT123 *",
            "source_database": "redis",
        }

        proof = OutcomeSourceProof.from_dict(data)

        assert proof.outcome_id == "OUT123"
        assert proof.signal_id == "SIG456"
        assert proof.order_id == "ORD789"
        assert proof.fill_id == "FILL001"
        assert proof.pnl == 150.50

    def test_secrets_redaction_in_query(self):
        """Test that secrets are redacted from source_query."""
        proof = OutcomeSourceProof(
            outcome_id="OUT123",
            signal_id="SIG456",
            order_id="ORD789",
            pnl=100.0,
            source_query="SELECT * FROM outcomes WHERE api_key=secret123",
            source_database="influx",
        )

        data = proof.to_dict()
        # Secrets should be redacted in the dict output
        assert (
            "[REDACTED]" in data["source_query"]
            or "secret123" not in data["source_query"]
        )


class TestRecapValidationEvidence:
    """Tests for RecapValidationEvidence dataclass."""

    def test_basic_creation(self):
        """Test creating RecapValidationEvidence."""
        evidence = RecapValidationEvidence(
            recap_message_id="1234567890123456789",
            recap_timestamp_utc="2026-02-28T12:00:00Z",
            outcome_proofs=[],
            total_pnl=0.0,
            trade_count=0,
            win_count=0,
            loss_count=0,
            source_verified=False,
        )

        assert evidence.recap_message_id == "1234567890123456789"
        assert evidence.source_verified is False

    def test_with_outcome_proofs(self):
        """Test evidence with outcome proofs."""
        proof1 = OutcomeSourceProof(
            outcome_id="OUT1",
            signal_id="SIG1",
            order_id="ORD1",
            pnl=100.0,
            source_query="HGET outcome:OUT1 *",
            source_database="redis",
        )
        proof2 = OutcomeSourceProof(
            outcome_id="OUT2",
            signal_id="SIG2",
            order_id="ORD2",
            pnl=-50.0,
            source_query="SELECT * FROM outcomes",
            source_database="influx",
        )

        evidence = RecapValidationEvidence(
            recap_message_id="1234567890123456789",
            recap_timestamp_utc="2026-02-28T12:00:00Z",
            outcome_proofs=[proof1, proof2],
            total_pnl=50.0,
            trade_count=2,
            win_count=1,
            loss_count=1,
            source_verified=True,
        )

        assert len(evidence.outcome_proofs) == 2
        assert evidence.total_pnl == 50.0
        assert evidence.win_count == 1
        assert evidence.loss_count == 1
        assert evidence.source_verified is True

    def test_to_dict(self):
        """Test conversion to dictionary."""
        proof = OutcomeSourceProof(
            outcome_id="OUT1",
            signal_id="SIG1",
            order_id="ORD1",
            pnl=100.0,
            source_query="HGET outcome:OUT1 *",
            source_database="redis",
        )

        evidence = RecapValidationEvidence(
            recap_message_id="1234567890123456789",
            recap_timestamp_utc="2026-02-28T12:00:00Z",
            outcome_proofs=[proof],
            total_pnl=100.0,
            trade_count=1,
            win_count=1,
            loss_count=0,
            source_verified=True,
        )

        data = evidence.to_dict()

        assert data["recap_message_id"] == "1234567890123456789"
        assert data["total_pnl"] == 100.0
        assert data["trade_count"] == 1
        assert data["source_verified"] is True
        assert len(data["outcome_proofs"]) == 1

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "recap_message_id": "1234567890123456789",
            "recap_timestamp_utc": "2026-02-28T12:00:00Z",
            "outcome_proofs": [
                {
                    "outcome_id": "OUT1",
                    "signal_id": "SIG1",
                    "order_id": "ORD1",
                    "fill_id": None,
                    "timestamp_utc": "",
                    "pnl": 100.0,
                    "source_query": "HGET outcome:OUT1 *",
                    "source_database": "redis",
                }
            ],
            "total_pnl": 100.0,
            "trade_count": 1,
            "win_count": 1,
            "loss_count": 0,
            "source_verified": True,
        }

        evidence = RecapValidationEvidence.from_dict(data)

        assert evidence.recap_message_id == "1234567890123456789"
        assert len(evidence.outcome_proofs) == 1
        assert evidence.outcome_proofs[0].outcome_id == "OUT1"
        assert evidence.source_verified is True


class TestRecapValidatorInitialization:
    """Tests for RecapValidator initialization."""

    def test_init_without_collectors(self):
        """Test initialization without collectors."""
        validator = RecapValidator()

        assert validator.redis_collector is None
        assert validator.influx_collector is None

    def test_init_with_collectors(self):
        """Test initialization with collectors."""
        redis_mock = MagicMock()
        influx_mock = MagicMock()

        validator = RecapValidator(
            redis_collector=redis_mock,
            influx_collector=influx_mock,
        )

        assert validator.redis_collector is redis_mock
        assert validator.influx_collector is influx_mock

    def test_create_recap_validator(self):
        """Test factory function."""
        redis_mock = MagicMock()
        influx_mock = MagicMock()

        validator = create_recap_validator(redis_mock, influx_mock)

        assert isinstance(validator, RecapValidator)
        assert validator.redis_collector is redis_mock
        assert validator.influx_collector is influx_mock


class TestExtractTradeIds:
    """Tests for trade ID extraction."""

    @pytest.fixture
    def validator(self):
        return RecapValidator()

    @pytest.mark.asyncio
    async def test_extract_trade_id_pattern(self, validator):
        """Test extracting Trade ID: pattern."""
        content = "Trade ID: ABC123DEF Trade executed successfully"
        ids = await validator.extract_trade_ids_from_recap(content)

        assert "ABC123DEF" in ids

    @pytest.mark.asyncio
    async def test_extract_trade_id_lowercase(self, validator):
        """Test extracting lowercase trade_id pattern."""
        content = "trade_id: XYZ789 trade completed"
        ids = await validator.extract_trade_ids_from_recap(content)

        assert "XYZ789" in ids

    @pytest.mark.asyncio
    async def test_extract_order_id_pattern(self, validator):
        """Test extracting Order ID: pattern."""
        content = "Order ID: ORDER123 executed"
        ids = await validator.extract_trade_ids_from_recap(content)

        assert "ORDER123" in ids

    @pytest.mark.asyncio
    async def test_extract_hash_trade_pattern(self, validator):
        """Test extracting #TRADE- pattern."""
        content = "Trade #TRADE-ABC123 completed"
        ids = await validator.extract_trade_ids_from_recap(content)

        assert "ABC123" in ids

    @pytest.mark.asyncio
    async def test_extract_bracket_trade_pattern(self, validator):
        """Test extracting [TRADE: pattern."""
        content = "Trade [TRADE:XYZ789] closed"
        ids = await validator.extract_trade_ids_from_recap(content)

        assert "XYZ789" in ids

    @pytest.mark.asyncio
    async def test_extract_uuid(self, validator):
        """Test extracting UUID format."""
        content = "Outcome: 550e8400-e29b-41d4-a716-446655440000"
        ids = await validator.extract_trade_ids_from_recap(content)

        assert "550e8400-e29b-41d4-a716-446655440000" in ids

    @pytest.mark.asyncio
    async def test_extract_multiple_ids(self, validator):
        """Test extracting multiple trade IDs."""
        content = """
        Daily RECAP:
        Trade ID: TRADE001 - PnL: $100
        Trade ID: TRADE002 - PnL: -$50
        Order ID: ORDER003 - PnL: $75
        """
        ids = await validator.extract_trade_ids_from_recap(content)

        assert "TRADE001" in ids
        assert "TRADE002" in ids
        assert "ORDER003" in ids

    @pytest.mark.asyncio
    async def test_no_duplicates(self, validator):
        """Test that duplicate IDs are removed."""
        content = "Trade ID: ABC123 Trade ID: ABC123 Trade ID: ABC123"
        ids = await validator.extract_trade_ids_from_recap(content)

        assert ids.count("ABC123") == 1

    @pytest.mark.asyncio
    async def test_empty_content(self, validator):
        """Test extracting from empty content."""
        ids = await validator.extract_trade_ids_from_recap("")

        assert ids == []


class TestVerifyOutcomeInRedis:
    """Tests for Redis outcome verification."""

    @pytest.fixture
    def validator(self):
        redis_mock = MagicMock()
        return RecapValidator(redis_collector=redis_mock)

    @pytest.fixture
    def window(self):
        now = datetime.now(UTC)
        return now - timedelta(minutes=30), now

    @pytest.mark.asyncio
    async def test_no_redis_collector(self, validator, window):
        """Test returns None when no Redis collector."""
        validator.redis_collector = None
        proof = await validator.verify_outcome_in_redis(
            "TRADE123", window[0], window[1]
        )

        assert proof is None

    @pytest.mark.asyncio
    async def test_outcome_found(self, validator, window):
        """Test successful outcome verification."""
        outcome_data = {
            "outcome_id": "OUT123",
            "signal_id": "SIG456",
            "order_id": "ORD789",
            "fill_id": "FILL001",
            "timestamp_utc": (window[0] + timedelta(minutes=5)).isoformat(),
            "pnl": "150.50",
        }

        with patch.object(
            validator, "_query_redis_outcome", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = outcome_data
            proof = await validator.verify_outcome_in_redis(
                "TRADE123", window[0], window[1]
            )

        assert proof is not None
        assert proof.outcome_id == "OUT123"
        assert proof.signal_id == "SIG456"
        assert proof.order_id == "ORD789"
        assert proof.fill_id == "FILL001"
        assert proof.pnl == 150.50
        assert proof.source_database == "redis"

    @pytest.mark.asyncio
    async def test_outside_window(self, validator, window):
        """Test outcome outside time window returns None."""
        outcome_data = {
            "outcome_id": "OUT123",
            "timestamp_utc": (window[0] - timedelta(hours=1)).isoformat(),
            "pnl": "150.50",
        }

        with patch.object(
            validator, "_query_redis_outcome", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = outcome_data
            proof = await validator.verify_outcome_in_redis(
                "TRADE123", window[0], window[1]
            )

        assert proof is None

    @pytest.mark.asyncio
    async def test_not_found(self, validator, window):
        """Test outcome not found returns None."""
        with patch.object(
            validator, "_query_redis_outcome", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = None
            proof = await validator.verify_outcome_in_redis(
                "TRADE123", window[0], window[1]
            )

        assert proof is None


class TestVerifyOutcomeInInflux:
    """Tests for InfluxDB outcome verification."""

    @pytest.fixture
    def validator(self):
        influx_mock = MagicMock()
        return RecapValidator(influx_collector=influx_mock)

    @pytest.fixture
    def window(self):
        now = datetime.now(UTC)
        return now - timedelta(minutes=30), now

    @pytest.mark.asyncio
    async def test_no_influx_collector(self, validator, window):
        """Test returns None when no Influx collector."""
        validator.influx_collector = None
        proof = await validator.verify_outcome_in_influx(
            "TRADE123", window[0], window[1]
        )

        assert proof is None

    @pytest.mark.asyncio
    async def test_outcome_found(self, validator, window):
        """Test successful outcome verification."""
        outcome_data = {
            "outcome_id": "OUT123",
            "signal_id": "SIG456",
            "order_id": "ORD789",
            "fill_id": "FILL001",
            "timestamp": (window[0] + timedelta(minutes=5)).isoformat(),
            "pnl": 150.50,
        }

        with patch.object(
            validator, "_query_influx_outcome", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = outcome_data
            proof = await validator.verify_outcome_in_influx(
                "TRADE123", window[0], window[1]
            )

        assert proof is not None
        assert proof.outcome_id == "OUT123"
        assert proof.pnl == 150.50
        assert proof.source_database == "influx"


class TestValidateRecapSource:
    """Tests for validate_recap_source method."""

    @pytest.fixture
    def validator(self):
        redis_mock = MagicMock()
        influx_mock = MagicMock()
        return RecapValidator(redis_collector=redis_mock, influx_collector=influx_mock)

    @pytest.fixture
    def recap_message(self):
        return DiscordMessageEvidence(
            message_id="1234567890123456789",
            channel_id="1444447985378398459",
            channel_name="trading",
            timestamp_utc=datetime.now(UTC).isoformat(),
            content_type="RECAP",
            content_snippet="Daily RECAP - Trade ID: TRADE001, Trade ID: TRADE002",
            is_bot=True,
        )

    @pytest.fixture
    def window(self):
        now = datetime.now(UTC)
        return now - timedelta(minutes=30), now

    @pytest.mark.asyncio
    async def test_valid_recap(self, validator, recap_message, window):
        """Test validation with verified outcomes."""
        proof1 = OutcomeSourceProof(
            outcome_id="OUT1",
            signal_id="SIG1",
            order_id="TRADE001",
            pnl=100.0,
            source_query="HGET outcome:OUT1 *",
            source_database="redis",
        )
        proof2 = OutcomeSourceProof(
            outcome_id="OUT2",
            signal_id="SIG2",
            order_id="TRADE002",
            pnl=-50.0,
            source_query="SELECT * FROM outcomes",
            source_database="influx",
        )

        with patch.object(
            validator, "verify_outcome_in_redis", new_callable=AsyncMock
        ) as mock_redis:
            mock_redis.side_effect = [proof1, None]  # First found in Redis, second not

            with patch.object(
                validator, "verify_outcome_in_influx", new_callable=AsyncMock
            ) as mock_influx:
                mock_influx.side_effect = [proof2]  # Second found in Influx

                evidence = await validator.validate_recap_source(
                    recap_message, window[0], window[1]
                )

        assert evidence.recap_message_id == "1234567890123456789"
        assert len(evidence.outcome_proofs) == 2
        assert evidence.total_pnl == 50.0
        assert evidence.win_count == 1
        assert evidence.loss_count == 1
        assert evidence.source_verified is True

    @pytest.mark.asyncio
    async def test_missing_outcome(self, validator, recap_message, window):
        """Test validation when an outcome is missing."""
        proof1 = OutcomeSourceProof(
            outcome_id="OUT1",
            signal_id="SIG1",
            order_id="TRADE001",
            pnl=100.0,
            source_query="HGET outcome:OUT1 *",
            source_database="redis",
        )

        with patch.object(
            validator, "verify_outcome_in_redis", new_callable=AsyncMock
        ) as mock_redis:
            mock_redis.side_effect = [proof1, None]

            with patch.object(
                validator, "verify_outcome_in_influx", new_callable=AsyncMock
            ) as mock_influx:
                mock_influx.return_value = None  # Second not found anywhere

                evidence = await validator.validate_recap_source(
                    recap_message, window[0], window[1]
                )

        assert len(evidence.outcome_proofs) == 1
        assert evidence.source_verified is False  # Not all verified

    @pytest.mark.asyncio
    async def test_no_trade_ids(self, validator, window):
        """Test validation when no trade IDs found."""
        recap = DiscordMessageEvidence(
            message_id="1234567890123456789",
            channel_id="1444447985378398459",
            channel_name="trading",
            timestamp_utc=datetime.now(UTC).isoformat(),
            content_type="RECAP",
            content_snippet="Daily RECAP - No trades today",
            is_bot=True,
        )

        evidence = await validator.validate_recap_source(recap, window[0], window[1])

        assert evidence.trade_count == 0
        assert evidence.source_verified is False


class TestValidateG5Recap:
    """Tests for G5 recap validation."""

    @pytest.fixture
    def validator(self):
        return RecapValidator()

    def test_pass_with_valid_evidence(self, validator):
        """Test G5 pass with valid evidence."""
        proof = OutcomeSourceProof(
            outcome_id="OUT1",
            signal_id="SIG1",
            order_id="ORD1",
            pnl=100.0,
            source_query="HGET outcome:OUT1 *",
            source_database="redis",
        )

        evidence = RecapValidationEvidence(
            recap_message_id="1234567890123456789",
            recap_timestamp_utc=datetime.now(UTC).isoformat(),
            outcome_proofs=[proof],
            total_pnl=100.0,
            trade_count=1,
            win_count=1,
            loss_count=0,
            source_verified=True,
        )

        result = validator.validate_g5_recap(evidence)

        assert result.status == GateStatus.PASS
        assert "PASS" in result.message
        assert result.evidence is evidence

    def test_fail_missing_message_id(self, validator):
        """Test G5 fail when recap message ID missing."""
        evidence = RecapValidationEvidence(
            recap_message_id="",
            recap_timestamp_utc=datetime.now(UTC).isoformat(),
            outcome_proofs=[],
            source_verified=False,
        )

        result = validator.validate_g5_recap(evidence)

        assert result.status == GateStatus.FAIL
        assert "Missing recap message ID" in result.message

    def test_fail_no_outcome_proofs(self, validator):
        """Test G5 fail when no outcome proofs."""
        evidence = RecapValidationEvidence(
            recap_message_id="1234567890123456789",
            recap_timestamp_utc=datetime.now(UTC).isoformat(),
            outcome_proofs=[],
            source_verified=False,
        )

        result = validator.validate_g5_recap(evidence)

        assert result.status == GateStatus.FAIL
        assert "No outcome proofs" in result.message

    def test_fail_source_not_verified(self, validator):
        """Test G5 fail when source not verified."""
        proof = OutcomeSourceProof(
            outcome_id="OUT1",
            signal_id="SIG1",
            order_id="ORD1",
            pnl=100.0,
            source_query="HGET outcome:OUT1 *",
            source_database="redis",
        )

        evidence = RecapValidationEvidence(
            recap_message_id="1234567890123456789",
            recap_timestamp_utc=datetime.now(UTC).isoformat(),
            outcome_proofs=[proof],
            total_pnl=100.0,
            trade_count=1,
            source_verified=False,  # Not verified
        )

        result = validator.validate_g5_recap(evidence)

        assert result.status == GateStatus.FAIL
        assert "Source verification failed" in result.message

    def test_fail_missing_timestamp(self, validator):
        """Test G5 fail when recap timestamp missing."""
        proof = OutcomeSourceProof(
            outcome_id="OUT1",
            signal_id="SIG1",
            order_id="ORD1",
            pnl=100.0,
            source_query="HGET outcome:OUT1 *",
            source_database="redis",
        )

        evidence = RecapValidationEvidence(
            recap_message_id="1234567890123456789",
            recap_timestamp_utc="",  # Missing
            outcome_proofs=[proof],
            total_pnl=100.0,
            trade_count=1,
            source_verified=True,
        )

        result = validator.validate_g5_recap(evidence)

        assert result.status == GateStatus.FAIL
        assert "Missing recap timestamp" in result.message

    def test_passed_property(self, validator):
        """Test GateResult.passed property."""
        pass_result = GateResult(status=GateStatus.PASS)
        fail_result = GateResult(status=GateStatus.FAIL)

        assert pass_result.passed is True
        assert fail_result.passed is False


class TestValidateRecapMessage:
    """Tests for complete recap message validation."""

    @pytest.fixture
    def validator(self):
        redis_mock = MagicMock()
        influx_mock = MagicMock()
        return RecapValidator(redis_collector=redis_mock, influx_collector=influx_mock)

    @pytest.fixture
    def recap_message(self):
        return DiscordMessageEvidence(
            message_id="1234567890123456789",
            channel_id="1444447985378398459",
            channel_name="trading",
            timestamp_utc=datetime.now(UTC).isoformat(),
            content_type="RECAP",
            content_snippet="Daily RECAP - Trade ID: TRADE001 - PnL: $100",
            is_bot=True,
        )

    @pytest.fixture
    def window(self):
        now = datetime.now(UTC)
        return now - timedelta(minutes=30), now

    @pytest.mark.asyncio
    async def test_full_validation_pass(self, validator, recap_message, window):
        """Test complete validation that passes."""
        proof = OutcomeSourceProof(
            outcome_id="OUT1",
            signal_id="SIG1",
            order_id="TRADE001",
            pnl=100.0,
            source_query="HGET outcome:OUT1 *",
            source_database="redis",
        )

        with patch.object(
            validator, "verify_outcome_in_redis", new_callable=AsyncMock
        ) as mock_redis:
            mock_redis.return_value = proof

            result = await validator.validate_recap_message(
                recap_message, window[0], window[1]
            )

        assert result.status == GateStatus.PASS
        assert result.evidence is not None
        assert result.evidence.trade_count == 1
        assert result.evidence.total_pnl == 100.0

    @pytest.mark.asyncio
    async def test_full_validation_fail(self, validator, recap_message, window):
        """Test complete validation that fails."""
        with patch.object(
            validator, "verify_outcome_in_redis", new_callable=AsyncMock
        ) as mock_redis:
            mock_redis.return_value = None

            with patch.object(
                validator, "verify_outcome_in_influx", new_callable=AsyncMock
            ) as mock_influx:
                mock_influx.return_value = None

                result = await validator.validate_recap_message(
                    recap_message, window[0], window[1]
                )

        assert result.status == GateStatus.FAIL
        assert "No outcome proofs" in result.message


class TestIntegration:
    """Integration-style tests."""

    @pytest.mark.asyncio
    async def test_end_to_end_validation(self):
        """Test end-to-end validation flow."""
        # Create validator with mocked collectors
        redis_mock = MagicMock()
        influx_mock = MagicMock()
        validator = RecapValidator(
            redis_collector=redis_mock,
            influx_collector=influx_mock,
        )

        # Create recap message
        recap = DiscordMessageEvidence(
            message_id="1234567890123456789",
            channel_id="1444447985378398459",
            channel_name="trading",
            timestamp_utc=datetime.now(UTC).isoformat(),
            content_type="RECAP",
            content_snippet="""
            Daily Trading RECAP
            Trade ID: BTC001 - Long BTC - PnL: $150
            Trade ID: ETH002 - Short ETH - PnL: -$50
            Total PnL: $100
            """,
            is_bot=True,
        )

        # Set up window
        now = datetime.now(UTC)
        window_start = now - timedelta(minutes=30)
        window_end = now

        # Mock Redis to return first outcome
        with patch.object(
            validator, "_query_redis_outcome", new_callable=AsyncMock
        ) as mock_redis_query:
            mock_redis_query.side_effect = [
                {
                    "outcome_id": "OUT_BTC001",
                    "signal_id": "SIG_BTC001",
                    "order_id": "BTC001",
                    "timestamp_utc": (window_start + timedelta(minutes=5)).isoformat(),
                    "pnl": "150.0",
                },
                None,  # ETH002 not in Redis
            ]

            # Mock Influx to return second outcome
            with patch.object(
                validator, "_query_influx_outcome", new_callable=AsyncMock
            ) as mock_influx_query:
                mock_influx_query.return_value = {
                    "outcome_id": "OUT_ETH002",
                    "signal_id": "SIG_ETH002",
                    "order_id": "ETH002",
                    "timestamp": (window_start + timedelta(minutes=10)).isoformat(),
                    "pnl": -50.0,
                }

                # Run validation
                result = await validator.validate_recap_message(
                    recap, window_start, window_end
                )

        # Verify results
        assert result.status == GateStatus.PASS
        assert result.evidence is not None
        assert result.evidence.recap_message_id == "1234567890123456789"
        assert result.evidence.trade_count == 2
        assert result.evidence.total_pnl == 100.0
        assert result.evidence.win_count == 1
        assert result.evidence.loss_count == 1
        assert result.evidence.source_verified is True

        # Verify outcome proofs
        proofs = result.evidence.outcome_proofs
        assert len(proofs) == 2

        # Check first proof (from Redis)
        btc_proof = next(p for p in proofs if p.order_id == "BTC001")
        assert btc_proof.source_database == "redis"
        assert btc_proof.pnl == 150.0

        # Check second proof (from Influx)
        eth_proof = next(p for p in proofs if p.order_id == "ETH002")
        assert eth_proof.source_database == "influx"
        assert eth_proof.pnl == -50.0

    @pytest.mark.asyncio
    async def test_serialization_roundtrip(self):
        """Test that evidence can be serialized and deserialized."""
        proof = OutcomeSourceProof(
            outcome_id="OUT1",
            signal_id="SIG1",
            order_id="ORD1",
            fill_id="FILL001",
            timestamp_utc="2026-02-28T12:00:00Z",
            pnl=100.0,
            source_query="HGET outcome:OUT1 *",
            source_database="redis",
        )

        evidence = RecapValidationEvidence(
            recap_message_id="1234567890123456789",
            recap_timestamp_utc="2026-02-28T12:00:00Z",
            outcome_proofs=[proof],
            total_pnl=100.0,
            trade_count=1,
            win_count=1,
            loss_count=0,
            source_verified=True,
        )

        # Serialize
        data = evidence.to_dict()
        json_str = json.dumps(data)

        # Deserialize
        loaded_data = json.loads(json_str)
        loaded_evidence = RecapValidationEvidence.from_dict(loaded_data)

        # Verify
        assert loaded_evidence.recap_message_id == evidence.recap_message_id
        assert loaded_evidence.total_pnl == evidence.total_pnl
        assert loaded_evidence.source_verified == evidence.source_verified
        assert len(loaded_evidence.outcome_proofs) == 1
        assert loaded_evidence.outcome_proofs[0].outcome_id == "OUT1"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
