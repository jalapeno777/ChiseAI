"""Tests for checkpoint manager module.

Tests the CheckpointManager, CheckpointConfig, and CheckpointReport classes.

Story: PAPER-GOVERNANCE-001
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.governance.checkpoint.checkpoint import (
    CheckpointConfig,
    CheckpointManager,
    CheckpointReport,
    run_checkpoint,
    run_checkpoint_sync,
)
from src.governance.checkpoint.gates import GateChecker, GateResult, GateSummary


class TestCheckpointConfig:
    """Tests for CheckpointConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = CheckpointConfig()

        assert config.redis_host is not None
        assert config.redis_port is not None
        assert config.archive_dir is not None
        assert config.auto_notify is True
        assert config.auto_archive is True

    def test_custom_config(self):
        """Test custom configuration values."""
        config = CheckpointConfig(
            redis_host="custom-host",
            redis_port=1234,
            discord_channel_id="123456",
            discord_bot_token="test-token",
            discord_webhook_url="https://example.com/webhook",
            archive_dir="/custom/archive",
            auto_notify=False,
            auto_archive=False,
        )

        assert config.redis_host == "custom-host"
        assert config.redis_port == 1234
        assert config.discord_channel_id == "123456"
        assert config.discord_bot_token == "test-token"
        assert config.discord_webhook_url == "https://example.com/webhook"
        assert config.archive_dir == "/custom/archive"
        assert config.auto_notify is False
        assert config.auto_archive is False

    def test_config_from_env(self, monkeypatch):
        """Test configuration from environment variables."""
        monkeypatch.setenv("REDIS_HOST", "env-host")
        monkeypatch.setenv("REDIS_PORT", "9999")
        monkeypatch.setenv("CHECKPOINT_ARCHIVE_DIR", "/env/archive")

        config = CheckpointConfig()

        assert config.redis_host == "env-host"
        assert config.redis_port == 9999
        assert config.archive_dir == "/env/archive"


class TestCheckpointReport:
    """Tests for CheckpointReport dataclass."""

    def test_report_creation(self, sample_gate_summary):
        """Test creating a checkpoint report."""
        now = datetime.now(UTC)
        from src.governance.checkpoint.evidence import CheckpointEvidence
        from src.governance.checkpoint.state import (
            CheckpointRecord,
            CheckpointState,
            CheckpointStatus,
        )

        evidence = CheckpointEvidence(
            checkpoint_id="checkpoint-001",
            timestamp=now,
            summary=sample_gate_summary,
        )

        record = CheckpointRecord(
            checkpoint_id="checkpoint-001",
            state=CheckpointState.COMPLETED,
            status=CheckpointStatus.HEALTHY,
            created_at=now,
        )

        report = CheckpointReport(
            checkpoint_id="checkpoint-001",
            timestamp=now,
            summary=sample_gate_summary,
            evidence=evidence,
            record=record,
            discord_posted=True,
            archived=True,
        )

        assert report.checkpoint_id == "checkpoint-001"
        assert report.timestamp == now
        assert report.summary == sample_gate_summary
        assert report.evidence == evidence
        assert report.record == record
        assert report.discord_posted is True
        assert report.archived is True

    def test_report_success_property(self, sample_gate_summary):
        """Test success property."""
        now = datetime.now(UTC)
        from src.governance.checkpoint.evidence import CheckpointEvidence
        from src.governance.checkpoint.state import (
            CheckpointRecord,
            CheckpointState,
            CheckpointStatus,
        )

        evidence = CheckpointEvidence(
            checkpoint_id="checkpoint-001",
            timestamp=now,
            summary=sample_gate_summary,
        )

        record = CheckpointRecord(
            checkpoint_id="checkpoint-001",
            state=CheckpointState.COMPLETED,
            status=CheckpointStatus.HEALTHY,
            created_at=now,
        )

        report = CheckpointReport(
            checkpoint_id="checkpoint-001",
            timestamp=now,
            summary=sample_gate_summary,
            evidence=evidence,
            record=record,
        )

        assert report.success is True

    def test_report_failure_property(self, sample_gate_summary_with_failures):
        """Test success property with failures."""
        now = datetime.now(UTC)
        from src.governance.checkpoint.evidence import CheckpointEvidence
        from src.governance.checkpoint.state import (
            CheckpointRecord,
            CheckpointState,
            CheckpointStatus,
        )

        evidence = CheckpointEvidence(
            checkpoint_id="checkpoint-001",
            timestamp=now,
            summary=sample_gate_summary_with_failures,
        )

        record = CheckpointRecord(
            checkpoint_id="checkpoint-001",
            state=CheckpointState.FAILED,
            status=CheckpointStatus.CRITICAL,
            created_at=now,
        )

        report = CheckpointReport(
            checkpoint_id="checkpoint-001",
            timestamp=now,
            summary=sample_gate_summary_with_failures,
            evidence=evidence,
            record=record,
        )

        assert report.success is False

    def test_report_status_healthy(self, sample_gate_summary):
        """Test status property when healthy."""
        now = datetime.now(UTC)
        from src.governance.checkpoint.evidence import CheckpointEvidence
        from src.governance.checkpoint.state import (
            CheckpointRecord,
            CheckpointState,
            CheckpointStatus,
        )

        evidence = CheckpointEvidence(
            checkpoint_id="checkpoint-001",
            timestamp=now,
            summary=sample_gate_summary,
        )

        record = CheckpointRecord(
            checkpoint_id="checkpoint-001",
            state=CheckpointState.COMPLETED,
            status=CheckpointStatus.HEALTHY,
            created_at=now,
        )

        report = CheckpointReport(
            checkpoint_id="checkpoint-001",
            timestamp=now,
            summary=sample_gate_summary,
            evidence=evidence,
            record=record,
        )

        assert report.status == "HEALTHY"

    def test_report_status_degraded(self):
        """Test status property when degraded."""
        now = datetime.now(UTC)
        from src.governance.checkpoint.evidence import CheckpointEvidence
        from src.governance.checkpoint.state import (
            CheckpointRecord,
            CheckpointState,
            CheckpointStatus,
        )

        results = [
            GateResult(gate="G1", status="⚠️ CHECK", detail="Check", timestamp=now),
        ]
        summary = GateSummary(
            results=results,
            pass_count=0,
            fail_count=0,
            check_count=1,
            timestamp=now,
        )

        evidence = CheckpointEvidence(
            checkpoint_id="checkpoint-001",
            timestamp=now,
            summary=summary,
        )

        record = CheckpointRecord(
            checkpoint_id="checkpoint-001",
            state=CheckpointState.COMPLETED,
            status=CheckpointStatus.DEGRADED,
            created_at=now,
        )

        report = CheckpointReport(
            checkpoint_id="checkpoint-001",
            timestamp=now,
            summary=summary,
            evidence=evidence,
            record=record,
        )

        assert report.status == "DEGRADED"

    def test_report_status_failed(self, sample_gate_summary_with_failures):
        """Test status property when failed."""
        now = datetime.now(UTC)
        from src.governance.checkpoint.evidence import CheckpointEvidence
        from src.governance.checkpoint.state import (
            CheckpointRecord,
            CheckpointState,
            CheckpointStatus,
        )

        evidence = CheckpointEvidence(
            checkpoint_id="checkpoint-001",
            timestamp=now,
            summary=sample_gate_summary_with_failures,
        )

        record = CheckpointRecord(
            checkpoint_id="checkpoint-001",
            state=CheckpointState.FAILED,
            status=CheckpointStatus.CRITICAL,
            created_at=now,
        )

        report = CheckpointReport(
            checkpoint_id="checkpoint-001",
            timestamp=now,
            summary=sample_gate_summary_with_failures,
            evidence=evidence,
            record=record,
        )

        assert report.status == "FAILED"


class TestCheckpointManagerInitialization:
    """Tests for CheckpointManager initialization."""

    def test_default_initialization(self):
        """Test manager with default config."""
        manager = CheckpointManager()

        assert manager.config is not None
        assert manager._gate_checker is not None
        assert manager._evidence_collector is not None
        assert manager._state_manager is not None

    def test_custom_config(self):
        """Test manager with custom config."""
        config = CheckpointConfig(redis_host="custom-host")
        manager = CheckpointManager(config=config)

        assert manager.config.redis_host == "custom-host"


class TestCheckpointManagerRun:
    """Tests for running checkpoints."""

    @pytest.mark.asyncio
    async def test_run_checkpoint_success(self, mock_redis_client, sample_gate_summary):
        """Test running a successful checkpoint."""
        config = CheckpointConfig(auto_notify=False, auto_archive=False)
        manager = CheckpointManager(config=config)

        # Mock the gate checker
        manager._gate_checker = MagicMock(spec=GateChecker)
        manager._gate_checker.run_all_checks.return_value = sample_gate_summary

        # Mock the state manager
        from src.governance.checkpoint.state import (
            CheckpointRecord,
            CheckpointState,
            CheckpointStatus,
        )

        mock_record = CheckpointRecord(
            checkpoint_id="checkpoint-001",
            state=CheckpointState.COMPLETED,
            status=CheckpointStatus.HEALTHY,
            created_at=datetime.now(UTC),
        )
        manager._state_manager = MagicMock()
        manager._state_manager.create_checkpoint.return_value = mock_record
        manager._state_manager.start_checkpoint.return_value = mock_record
        manager._state_manager.complete_checkpoint.return_value = mock_record
        manager._state_manager.get_checkpoint.return_value = mock_record

        # Mock the evidence collector
        from src.governance.checkpoint.evidence import CheckpointEvidence

        mock_evidence = CheckpointEvidence(
            checkpoint_id="checkpoint-001",
            timestamp=datetime.now(UTC),
            summary=sample_gate_summary,
        )
        manager._evidence_collector = MagicMock()
        manager._evidence_collector.collect_and_store.return_value = mock_evidence

        report = await manager.run_checkpoint(
            checkpoint_id="checkpoint-001",
            metadata={"trigger": "test"},
        )

        assert report.checkpoint_id == "checkpoint-001"
        assert report.success is True
        assert report.discord_posted is False
        assert report.archived is False

    @pytest.mark.asyncio
    async def test_run_checkpoint_with_failure(
        self, mock_redis_client, sample_gate_summary_with_failures
    ):
        """Test running a checkpoint with failures."""
        config = CheckpointConfig(auto_notify=False, auto_archive=False)
        manager = CheckpointManager(config=config)

        # Mock the gate checker
        manager._gate_checker = MagicMock(spec=GateChecker)
        manager._gate_checker.run_all_checks.return_value = (
            sample_gate_summary_with_failures
        )

        # Mock the state manager
        from src.governance.checkpoint.state import (
            CheckpointRecord,
            CheckpointState,
            CheckpointStatus,
        )

        mock_record = CheckpointRecord(
            checkpoint_id="checkpoint-001",
            state=CheckpointState.FAILED,
            status=CheckpointStatus.CRITICAL,
            created_at=datetime.now(UTC),
        )
        manager._state_manager = MagicMock()
        manager._state_manager.create_checkpoint.return_value = mock_record
        manager._state_manager.start_checkpoint.return_value = mock_record
        manager._state_manager.complete_checkpoint.return_value = mock_record
        manager._state_manager.get_checkpoint.return_value = mock_record

        # Mock the evidence collector
        from src.governance.checkpoint.evidence import CheckpointEvidence

        mock_evidence = CheckpointEvidence(
            checkpoint_id="checkpoint-001",
            timestamp=datetime.now(UTC),
            summary=sample_gate_summary_with_failures,
        )
        manager._evidence_collector = MagicMock()
        manager._evidence_collector.collect_and_store.return_value = mock_evidence

        report = await manager.run_checkpoint(checkpoint_id="checkpoint-001")

        assert report.success is False
        assert report.summary.fail_count == 1

    @pytest.mark.asyncio
    async def test_run_checkpoint_exception(self, mock_redis_client):
        """Test handling exception during checkpoint."""
        config = CheckpointConfig(auto_notify=False, auto_archive=False)
        manager = CheckpointManager(config=config)

        from src.governance.checkpoint.state import (
            CheckpointRecord,
            CheckpointState,
            CheckpointStatus,
        )

        mock_record = CheckpointRecord(
            checkpoint_id="checkpoint-001",
            state=CheckpointState.PENDING,
            status=CheckpointStatus.UNKNOWN,
            created_at=datetime.now(UTC),
        )
        manager._state_manager = MagicMock()
        manager._state_manager.create_checkpoint.return_value = mock_record
        manager._state_manager.start_checkpoint.return_value = mock_record
        manager._state_manager.fail_checkpoint.return_value = mock_record

        # Make gate checker raise exception
        manager._gate_checker = MagicMock(spec=GateChecker)
        manager._gate_checker.run_all_checks.side_effect = Exception("Test error")

        with pytest.raises(Exception, match="Test error"):
            await manager.run_checkpoint(checkpoint_id="checkpoint-001")

        manager._state_manager.fail_checkpoint.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_checkpoint_with_notify(
        self, mock_redis_client, sample_gate_summary
    ):
        """Test running checkpoint with Discord notification."""
        config = CheckpointConfig(
            auto_notify=True,
            auto_archive=False,
            discord_webhook_url="https://example.com/webhook",
        )
        manager = CheckpointManager(config=config)

        # Mock components
        manager._gate_checker = MagicMock(spec=GateChecker)
        manager._gate_checker.run_all_checks.return_value = sample_gate_summary

        from src.governance.checkpoint.state import (
            CheckpointRecord,
            CheckpointState,
            CheckpointStatus,
        )

        mock_record = CheckpointRecord(
            checkpoint_id="checkpoint-001",
            state=CheckpointState.COMPLETED,
            status=CheckpointStatus.HEALTHY,
            created_at=datetime.now(UTC),
        )
        manager._state_manager = MagicMock()
        manager._state_manager.create_checkpoint.return_value = mock_record
        manager._state_manager.start_checkpoint.return_value = mock_record
        manager._state_manager.complete_checkpoint.return_value = mock_record
        manager._state_manager.get_checkpoint.return_value = mock_record

        from src.governance.checkpoint.evidence import CheckpointEvidence

        mock_evidence = CheckpointEvidence(
            checkpoint_id="checkpoint-001",
            timestamp=datetime.now(UTC),
            summary=sample_gate_summary,
        )
        manager._evidence_collector = MagicMock()
        manager._evidence_collector.collect_and_store.return_value = mock_evidence

        # Mock the Discord post
        manager._post_discord = AsyncMock(return_value=True)

        report = await manager.run_checkpoint(checkpoint_id="checkpoint-001")

        assert report.discord_posted is True

    @pytest.mark.asyncio
    async def test_run_quick_check(self, sample_gate_summary):
        """Test running a quick check."""
        manager = CheckpointManager()
        manager._gate_checker = MagicMock(spec=GateChecker)
        manager._gate_checker.run_all_checks.return_value = sample_gate_summary

        summary = await manager.run_quick_check()

        assert summary == sample_gate_summary


class TestCheckpointManagerDiscord:
    """Tests for Discord notification functionality."""

    @pytest.mark.asyncio
    async def test_notify_discord_not_configured(self, sample_gate_summary):
        """Test notification when Discord is not configured."""
        config = CheckpointConfig(
            discord_webhook_url="",
            discord_bot_token="",
        )
        manager = CheckpointManager(config=config)

        from src.governance.checkpoint.evidence import CheckpointEvidence

        evidence = CheckpointEvidence(
            checkpoint_id="checkpoint-001",
            timestamp=datetime.now(UTC),
            summary=sample_gate_summary,
        )

        result = await manager._notify_discord(evidence)

        assert result is False

    @pytest.mark.asyncio
    async def test_post_discord_webhook_success(self, sample_gate_summary):
        """Test posting to Discord via webhook."""
        config = CheckpointConfig(discord_webhook_url="https://example.com/webhook")
        manager = CheckpointManager(config=config)

        # Mock aiohttp - session.post returns an async context manager
        mock_response = MagicMock()
        mock_response.status = 200

        # Create an async context manager for the response
        class AsyncContextManager:
            async def __aenter__(self):
                return mock_response

            async def __aexit__(self, *args):
                return False

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=AsyncContextManager())

        # Create an async context manager for the session
        class SessionContextManager:
            async def __aenter__(self):
                return mock_session

            async def __aexit__(self, *args):
                return False

        with patch("aiohttp.ClientSession", return_value=SessionContextManager()):
            result = await manager._post_webhook("Test message")

        assert result is True

    @pytest.mark.asyncio
    async def test_post_discord_webhook_failure(self, sample_gate_summary):
        """Test posting to Discord with failure response."""
        config = CheckpointConfig(discord_webhook_url="https://example.com/webhook")
        manager = CheckpointManager(config=config)

        # Mock aiohttp with failure - session.post returns an async context manager
        mock_response = MagicMock()
        mock_response.status = 400

        # Create an async context manager for the response
        class AsyncContextManager:
            async def __aenter__(self):
                return mock_response

            async def __aexit__(self, *args):
                return False

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=AsyncContextManager())

        # Create an async context manager for the session
        class SessionContextManager:
            async def __aenter__(self):
                return mock_session

            async def __aexit__(self, *args):
                return False

        with patch("aiohttp.ClientSession", return_value=SessionContextManager()):
            result = await manager._post_webhook("Test message")

        assert result is False

    @pytest.mark.asyncio
    async def test_post_discord_bot_api_success(self, sample_gate_summary):
        """Test posting to Discord via bot API."""
        config = CheckpointConfig(
            discord_bot_token="test-token",
            discord_channel_id="123456",
        )
        manager = CheckpointManager(config=config)

        # Mock aiohttp - session.post returns an async context manager
        mock_response = MagicMock()
        mock_response.status = 200

        # Create an async context manager for the response
        class AsyncContextManager:
            async def __aenter__(self):
                return mock_response

            async def __aexit__(self, *args):
                return False

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=AsyncContextManager())

        # Create an async context manager for the session
        class SessionContextManager:
            async def __aenter__(self):
                return mock_session

            async def __aexit__(self, *args):
                return False

        with patch("aiohttp.ClientSession", return_value=SessionContextManager()):
            result = await manager._post_bot_api("Test message")

        assert result is True


class TestCheckpointManagerQueries:
    """Tests for query methods."""

    def test_get_latest_checkpoint(self, sample_checkpoint_record):
        """Test getting latest checkpoint."""
        manager = CheckpointManager()
        manager._state_manager = MagicMock()
        manager._state_manager.get_active_checkpoint.return_value = (
            sample_checkpoint_record
        )

        result = manager.get_latest_checkpoint()

        assert result == sample_checkpoint_record

    def test_get_checkpoint_history(self, sample_checkpoint_record):
        """Test getting checkpoint history."""
        manager = CheckpointManager()
        manager._state_manager = MagicMock()
        manager._state_manager.get_checkpoint_history.return_value = [
            sample_checkpoint_record
        ]

        history = manager.get_checkpoint_history(limit=10)

        assert len(history) == 1
        assert history[0] == sample_checkpoint_record
        manager._state_manager.get_checkpoint_history.assert_called_once_with(limit=10)

    def test_is_healthy_from_latest(self, sample_checkpoint_record):
        """Test is_healthy using latest checkpoint."""
        manager = CheckpointManager()
        manager._state_manager = MagicMock()

        from src.governance.checkpoint.gates import GateResult

        now = datetime.now(UTC)
        sample_checkpoint_record.summary = GateSummary(
            results=[GateResult(gate="G1", status="✅ PASS", detail="", timestamp=now)],
            pass_count=1,
            fail_count=0,
            check_count=0,
            timestamp=now,
        )
        manager._state_manager.get_active_checkpoint.return_value = (
            sample_checkpoint_record
        )

        result = manager.is_healthy()

        assert result is True

    def test_is_healthy_from_fresh_check(self):
        """Test is_healthy with fresh check when no latest."""
        manager = CheckpointManager()
        manager._state_manager = MagicMock()
        manager._state_manager.get_active_checkpoint.return_value = None

        now = datetime.now(UTC)
        manager._gate_checker = MagicMock()
        manager._gate_checker.run_all_checks.return_value = GateSummary(
            results=[GateResult(gate="G1", status="✅ PASS", detail="", timestamp=now)],
            pass_count=1,
            fail_count=0,
            check_count=0,
            timestamp=now,
        )

        result = manager.is_healthy()

        assert result is True
        manager._gate_checker.run_all_checks.assert_called_once()

    def test_get_failing_gates(self):
        """Test getting failing gates."""
        manager = CheckpointManager()
        manager._gate_checker = MagicMock()
        manager._gate_checker.get_failing_gates.return_value = ["G4", "G5"]

        result = manager.get_failing_gates()

        assert result == ["G4", "G5"]


class TestCheckpointManagerScheduled:
    """Tests for scheduled checkpoint execution."""

    @pytest.mark.asyncio
    async def test_run_scheduled_checkpoint_success(self, sample_gate_summary):
        """Test scheduled checkpoint that passes."""
        manager = CheckpointManager()

        from src.governance.checkpoint.evidence import CheckpointEvidence
        from src.governance.checkpoint.state import (
            CheckpointRecord,
            CheckpointState,
            CheckpointStatus,
        )

        mock_record = CheckpointRecord(
            checkpoint_id="checkpoint-001",
            state=CheckpointState.COMPLETED,
            status=CheckpointStatus.HEALTHY,
            created_at=datetime.now(UTC),
        )

        mock_evidence = CheckpointEvidence(
            checkpoint_id="checkpoint-001",
            timestamp=datetime.now(UTC),
            summary=sample_gate_summary,
        )

        manager._gate_checker = MagicMock()
        manager._gate_checker.run_all_checks.return_value = sample_gate_summary

        manager._state_manager = MagicMock()
        manager._state_manager.create_checkpoint.return_value = mock_record
        manager._state_manager.start_checkpoint.return_value = mock_record
        manager._state_manager.complete_checkpoint.return_value = mock_record
        manager._state_manager.get_checkpoint.return_value = mock_record

        manager._evidence_collector = MagicMock()
        manager._evidence_collector.collect_and_store.return_value = mock_evidence

        manager._notify_discord = AsyncMock(return_value=False)

        exit_code = await manager.run_scheduled_checkpoint()

        assert exit_code == 0

    @pytest.mark.asyncio
    async def test_run_scheduled_checkpoint_failure(
        self, sample_gate_summary_with_failures
    ):
        """Test scheduled checkpoint that fails."""
        manager = CheckpointManager()

        from src.governance.checkpoint.evidence import CheckpointEvidence
        from src.governance.checkpoint.state import (
            CheckpointRecord,
            CheckpointState,
            CheckpointStatus,
        )

        mock_record = CheckpointRecord(
            checkpoint_id="checkpoint-001",
            state=CheckpointState.FAILED,
            status=CheckpointStatus.CRITICAL,
            created_at=datetime.now(UTC),
        )

        mock_evidence = CheckpointEvidence(
            checkpoint_id="checkpoint-001",
            timestamp=datetime.now(UTC),
            summary=sample_gate_summary_with_failures,
        )

        manager._gate_checker = MagicMock()
        manager._gate_checker.run_all_checks.return_value = (
            sample_gate_summary_with_failures
        )

        manager._state_manager = MagicMock()
        manager._state_manager.create_checkpoint.return_value = mock_record
        manager._state_manager.start_checkpoint.return_value = mock_record
        manager._state_manager.complete_checkpoint.return_value = mock_record
        manager._state_manager.get_checkpoint.return_value = mock_record

        manager._evidence_collector = MagicMock()
        manager._evidence_collector.collect_and_store.return_value = mock_evidence

        manager._notify_discord = AsyncMock(return_value=False)

        exit_code = await manager.run_scheduled_checkpoint()

        assert exit_code == 1

    @pytest.mark.asyncio
    async def test_run_scheduled_checkpoint_exception(self):
        """Test scheduled checkpoint with exception."""
        manager = CheckpointManager()

        from src.governance.checkpoint.state import (
            CheckpointRecord,
            CheckpointState,
            CheckpointStatus,
        )

        mock_record = CheckpointRecord(
            checkpoint_id="checkpoint-001",
            state=CheckpointState.PENDING,
            status=CheckpointStatus.UNKNOWN,
            created_at=datetime.now(UTC),
        )

        manager._state_manager = MagicMock()
        manager._state_manager.create_checkpoint.return_value = mock_record

        manager._gate_checker = MagicMock()
        manager._gate_checker.run_all_checks.side_effect = Exception("Test error")

        exit_code = await manager.run_scheduled_checkpoint()

        assert exit_code == 1


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    @pytest.mark.asyncio
    async def test_run_checkpoint_function(
        self, mock_redis_client, sample_gate_summary
    ):
        """Test run_checkpoint convenience function."""
        with patch(
            "src.governance.checkpoint.checkpoint.CheckpointManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager_class.return_value = mock_manager

            mock_report = MagicMock()
            mock_report.success = True
            mock_manager.run_checkpoint = AsyncMock(return_value=mock_report)

            report = await run_checkpoint(
                checkpoint_id="test-001",
                metadata={"source": "convenience"},
                notify=False,
            )

            assert report.success is True
            mock_manager.run_checkpoint.assert_called_once_with(
                checkpoint_id="test-001",
                metadata={"source": "convenience"},
                notify=False,
            )

    def test_run_checkpoint_sync_function(self, mock_redis_client, sample_gate_summary):
        """Test run_checkpoint_sync convenience function."""
        with patch("src.governance.checkpoint.checkpoint.run_checkpoint") as mock_run:
            mock_report = MagicMock()
            mock_report.success = True
            mock_run.return_value = mock_report

            with patch("asyncio.run", return_value=mock_report):
                report = run_checkpoint_sync(
                    checkpoint_id="test-001",
                    metadata={"source": "convenience"},
                )

                assert report.success is True
