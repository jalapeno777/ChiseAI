"""Tests for live gating audit logger.

Tests audit trail logging for trades, approvals, and state changes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from execution.live_gating.audit_logger import (
    ApprovalAuditRecord,
    LiveTradeAuditLogger,
    StateChangeAuditRecord,
    TradeAuditRecord,
)
from execution.live_gating.gate_manager import (
    ApprovalPacket,
    LiveTradingState,
    PaperTradingEvidence,
)


class TestTradeAuditRecord:
    """Test TradeAuditRecord dataclass."""

    def test_creation(self):
        """Test record creation."""
        now = datetime.now(UTC)
        record = TradeAuditRecord(
            timestamp=now,
            trade_id="TRADE-001",
            symbol="BTCUSDT",
            side="buy",
            price=50000.0,
            quantity=0.1,
            reason="Grid signal",
        )
        assert record.trade_id == "TRADE-001"
        assert record.symbol == "BTCUSDT"
        assert record.environment == "live"

    def test_to_dict(self):
        """Test serialization."""
        now = datetime.now(UTC)
        record = TradeAuditRecord(
            timestamp=now,
            trade_id="TRADE-001",
            symbol="BTCUSDT",
            side="buy",
            price=50000.0,
            quantity=0.1,
            reason="Grid signal",
            pnl=100.0,
            fees=1.0,
        )
        d = record.to_dict()
        assert d["trade_id"] == "TRADE-001"
        assert d["price"] == 50000.0
        assert d["pnl"] == 100.0


class TestApprovalAuditRecord:
    """Test ApprovalAuditRecord dataclass."""

    def test_creation(self):
        """Test record creation."""
        now = datetime.now(UTC)
        record = ApprovalAuditRecord(
            timestamp=now,
            approver_id="admin",
            request_id="REQ-001",
            signature="abc123",
        )
        assert record.approver_id == "admin"
        assert record.signature == "abc123"

    def test_to_dict_masks_signature(self):
        """Test signature is masked in dict."""
        now = datetime.now(UTC)
        record = ApprovalAuditRecord(
            timestamp=now,
            approver_id="admin",
            request_id="REQ-001",
            signature="a" * 32,
        )
        d = record.to_dict()
        assert "..." in d["signature"]
        assert len(d["signature"]) < 32


class TestStateChangeAuditRecord:
    """Test StateChangeAuditRecord dataclass."""

    def test_creation(self):
        """Test record creation."""
        now = datetime.now(UTC)
        record = StateChangeAuditRecord(
            timestamp=now,
            old_state="disabled",
            new_state="active",
            reason="Approved",
        )
        assert record.old_state == "disabled"
        assert record.new_state == "active"


class TestLiveTradeAuditLoggerInitialization:
    """Test audit logger initialization."""

    def test_default_initialization(self):
        """Test default initialization."""
        logger = LiveTradeAuditLogger()
        assert logger._measurement == "live_trading_audit"
        assert logger._bucket == "chiseai"

    def test_custom_initialization(self):
        """Test custom initialization."""
        logger = LiveTradeAuditLogger(
            bucket="custom_bucket",
            measurement="custom_measurement",
        )
        assert logger._measurement == "custom_measurement"
        assert logger._bucket == "custom_bucket"


class TestLogTrade:
    """Test trade logging."""

    @pytest.mark.asyncio
    async def test_log_trade_success(self):
        """Test successful trade logging."""
        logger = LiveTradeAuditLogger()

        # Mock the write method
        with patch.object(logger, "_write_point", return_value=True) as mock_write:
            result = await logger.log_trade(
                timestamp=datetime.now(UTC),
                price=50000.0,
                quantity=0.1,
                reason="Grid signal: buy level 3",
                symbol="BTCUSDT",
                side="buy",
                trade_id="TRADE-001",
                pnl=0.0,
                fees=0.5,
            )
            assert result is True
            assert logger._trade_count == 1
            mock_write.assert_called_once()

    @pytest.mark.asyncio
    async def test_log_trade_failure(self):
        """Test trade logging failure."""
        logger = LiveTradeAuditLogger()

        with patch.object(logger, "_write_point", return_value=False):
            result = await logger.log_trade(
                timestamp=datetime.now(UTC),
                price=50000.0,
                quantity=0.1,
                reason="Test",
            )
            assert result is False
            # _failed_writes is only incremented on exception, not on False return
            # The write_point method returns False but doesn't increment counter
            # when there's no exception - this is the expected behavior

    @pytest.mark.asyncio
    async def test_log_trade_with_metadata(self):
        """Test trade logging with metadata."""
        logger = LiveTradeAuditLogger()

        with patch.object(logger, "_write_point", return_value=True):
            result = await logger.log_trade(
                timestamp=datetime.now(UTC),
                price=50000.0,
                quantity=0.1,
                reason="Grid signal",
                metadata={"grid_level": 3, "strategy": "grid_v1"},
            )
            assert result is True


class TestLogApproval:
    """Test approval logging."""

    @pytest.mark.asyncio
    async def test_log_approval_success(self):
        """Test successful approval logging."""
        logger = LiveTradeAuditLogger()
        now = datetime.now(UTC)

        evidence = PaperTradingEvidence(
            duration_days=35.0,
            total_trades=100,
            win_rate_pct=55.0,
            sharpe_ratio=1.5,
            max_drawdown_pct=8.0,
            realized_pnl=1000.0,
            start_date=now,
            end_date=now,
            strategy_id="test-strategy",
        )
        packet = ApprovalPacket(
            approver_id="admin",
            timestamp=now,
            signature="a" * 32,
            paper_evidence=evidence,
            request_id="REQ-001",
            approval_notes="Approved for live trading",
        )

        with patch.object(logger, "_write_point", return_value=True):
            result = await logger.log_approval(packet)
            assert result is True
            assert logger._approval_count == 1

    @pytest.mark.asyncio
    async def test_log_approval_failure(self):
        """Test approval logging failure."""
        logger = LiveTradeAuditLogger()
        now = datetime.now(UTC)

        evidence = PaperTradingEvidence(
            duration_days=35.0,
            total_trades=100,
            win_rate_pct=55.0,
            sharpe_ratio=1.5,
            max_drawdown_pct=8.0,
            realized_pnl=1000.0,
            start_date=now,
            end_date=now,
        )
        packet = ApprovalPacket(
            approver_id="admin",
            timestamp=now,
            signature="a" * 32,
            paper_evidence=evidence,
            request_id="REQ-001",
        )

        with patch.object(logger, "_write_point", return_value=False):
            result = await logger.log_approval(packet)
            assert result is False


class TestLogStateChange:
    """Test state change logging."""

    @pytest.mark.asyncio
    async def test_log_state_change_success(self):
        """Test successful state change logging."""
        logger = LiveTradeAuditLogger()

        with patch.object(logger, "_write_point", return_value=True):
            result = await logger.log_state_change(
                old_state=LiveTradingState.ACTIVE,
                new_state=LiveTradingState.DISABLED,
                reason="Kill-switch triggered",
                triggered_by="kill_switch",
            )
            assert result is True
            assert logger._state_change_count == 1

    @pytest.mark.asyncio
    async def test_log_state_change_with_strings(self):
        """Test state change logging with string states."""
        logger = LiveTradeAuditLogger()

        with patch.object(logger, "_write_point", return_value=True):
            result = await logger.log_state_change(
                old_state="disabled",
                new_state="pending_approval",
                reason="Approval requested",
            )
            assert result is True

    @pytest.mark.asyncio
    async def test_log_state_change_failure(self):
        """Test state change logging failure."""
        logger = LiveTradeAuditLogger()

        with patch.object(logger, "_write_point", return_value=False):
            result = await logger.log_state_change(
                old_state=LiveTradingState.ACTIVE,
                new_state=LiveTradingState.DISABLED,
                reason="Test",
            )
            assert result is False


class TestCreatePoint:
    """Test InfluxDB point creation."""

    def test_create_point_with_influxdb(self):
        """Test point creation with InfluxDB available."""
        logger = LiveTradeAuditLogger()

        # Mock influxdb_client
        mock_point = MagicMock()
        mock_point.tag = MagicMock(return_value=mock_point)
        mock_point.field = MagicMock(return_value=mock_point)
        mock_point.time = MagicMock(return_value=mock_point)

        with patch("influxdb_client.Point", return_value=mock_point):
            point = logger._create_point(
                record_type="trade",
                fields={"price": 50000.0, "quantity": 0.1},
                tags={"symbol": "BTCUSDT"},
                timestamp=datetime.now(UTC),
            )
            assert point is mock_point

    def test_create_point_without_influxdb(self):
        """Test point creation fallback without InfluxDB."""
        logger = LiveTradeAuditLogger()

        # Simulate ImportError
        with patch("builtins.__import__", side_effect=ImportError):
            point = logger._create_point(
                record_type="trade",
                fields={"price": 50000.0},
                tags={"symbol": "BTCUSDT"},
                timestamp=datetime.now(UTC),
            )
            assert point["measurement"] == "live_trading_audit"
            assert point["tags"]["record_type"] == "trade"


class TestWritePoint:
    """Test point writing."""

    @pytest.mark.asyncio
    async def test_write_point_with_client(self):
        """Test writing with InfluxDB client."""
        mock_client = MagicMock()
        mock_write_api = MagicMock()
        mock_client.write_api.return_value = mock_write_api

        logger = LiveTradeAuditLogger(influxdb_client=mock_client)

        point = {"test": "data"}
        result = await logger._write_point(point)
        assert result is True

    @pytest.mark.asyncio
    async def test_write_point_without_client(self):
        """Test writing without client buffers data."""
        logger = LiveTradeAuditLogger()

        point = {"test": "data"}
        result = await logger._write_point(point)
        assert result is True
        assert len(logger._buffer) == 1

    @pytest.mark.asyncio
    async def test_write_point_failure(self):
        """Test write failure handling."""
        mock_client = MagicMock()
        mock_client.write_api.side_effect = Exception("Connection failed")

        logger = LiveTradeAuditLogger(influxdb_client=mock_client)

        point = {"test": "data"}
        result = await logger._write_point(point)
        assert result is False
        assert logger._failed_writes == 1


class TestBufferManagement:
    """Test buffer management."""

    @pytest.mark.asyncio
    async def test_buffer_size_limit(self):
        """Test buffer size limit enforcement."""
        logger = LiveTradeAuditLogger()
        logger._buffer_max_size = 5

        # Add more items than max
        for i in range(10):
            await logger._write_point({"index": i})

        assert len(logger._buffer) == 5
        # Should keep most recent
        assert logger._buffer[-1]["index"] == 9

    @pytest.mark.asyncio
    async def test_flush_buffer(self):
        """Test buffer flushing."""
        mock_client = MagicMock()
        mock_write_api = MagicMock()
        mock_client.write_api.return_value = mock_write_api

        logger = LiveTradeAuditLogger(influxdb_client=mock_client)

        # Add items to buffer
        for i in range(5):
            logger._buffer.append({"index": i})

        flushed = await logger.flush_buffer()
        assert flushed == 5
        assert len(logger._buffer) == 0

    @pytest.mark.asyncio
    async def test_flush_buffer_partial_failure(self):
        """Test buffer flush with partial failures."""
        mock_client = MagicMock()
        mock_write_api = MagicMock()
        # Fail on 3rd write
        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 3:
                raise Exception("Write failed")

        mock_write_api.write.side_effect = side_effect
        mock_client.write_api.return_value = mock_write_api

        logger = LiveTradeAuditLogger(influxdb_client=mock_client)

        for i in range(5):
            logger._buffer.append({"index": i})

        flushed = await logger.flush_buffer()
        assert flushed == 4  # 4 succeeded
        assert len(logger._buffer) == 1  # 1 remaining


class TestStatistics:
    """Test statistics methods."""

    def test_get_stats(self):
        """Test getting statistics."""
        logger = LiveTradeAuditLogger()
        logger._trade_count = 10
        logger._approval_count = 2
        logger._state_change_count = 5
        logger._failed_writes = 1

        stats = logger.get_stats()
        assert stats["trade_count"] == 10
        assert stats["approval_count"] == 2
        assert stats["state_change_count"] == 5
        assert stats["failed_writes"] == 1
        assert stats["measurement"] == "live_trading_audit"
