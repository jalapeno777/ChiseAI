"""Unit tests for preflight_check in full_cycle.py."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from autonomous_cognition.full_cycle import preflight_check


class TestPreflightCheck:
    """Tests for preflight_check function."""

    def test_preflight_check_passes_when_all_checks_succeed(self) -> None:
        """When Redis, Qdrant, config, and output dir are all OK, preflight_check returns True."""
        mock_redis = MagicMock()
        mock_redis.ping.return_value = True
        mock_qdrant = MagicMock()
        mock_qdrant.get_collections.return_value = MagicMock()

        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch(
                "autonomous_cognition.full_cycle._get_repo_root",
                return_value=Path(tmp_dir),
            ):
                # Create a config file
                config_dir = Path(tmp_dir) / "config"
                config_dir.mkdir()
                (config_dir / "autocog.yaml").write_text(
                    "test: value", encoding="utf-8"
                )

                result = preflight_check(
                    redis_client=mock_redis,
                    qdrant_client=mock_qdrant,
                    notify_discord=False,
                )

        assert result is True
        mock_redis.ping.assert_called_once()
        mock_qdrant.get_collections.assert_called_once()

    def test_preflight_check_fails_when_redis_is_none(self) -> None:
        """When redis_client is None, preflight_check logs error and exits with code 1.

        Redis is required for cycle operation (belief store, state persistence).
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch(
                "autonomous_cognition.full_cycle._get_repo_root",
                return_value=Path(tmp_dir),
            ):
                with pytest.raises(SystemExit) as exc_info:
                    preflight_check(
                        redis_client=None,
                        qdrant_client=None,
                        notify_discord=False,
                    )

        assert exc_info.value.code == 1

    def test_preflight_check_passes_when_qdrant_is_none(self) -> None:
        """When qdrant_client is None (optional), preflight still passes if Redis works."""
        mock_redis = MagicMock()
        mock_redis.ping.return_value = True

        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch(
                "autonomous_cognition.full_cycle._get_repo_root",
                return_value=Path(tmp_dir),
            ):
                result = preflight_check(
                    redis_client=mock_redis,
                    qdrant_client=None,
                    notify_discord=False,
                )

        assert result is True

    def test_preflight_check_fails_and_exits_when_redis_ping_fails(self) -> None:
        """When Redis ping fails, preflight_check logs error and exits with code 1."""
        mock_redis = MagicMock()
        mock_redis.ping.side_effect = ConnectionError("Redis connection refused")

        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch(
                "autonomous_cognition.full_cycle._get_repo_root",
                return_value=Path(tmp_dir),
            ):
                with pytest.raises(SystemExit) as exc_info:
                    preflight_check(
                        redis_client=mock_redis,
                        qdrant_client=None,
                        notify_discord=False,
                    )

        assert exc_info.value.code == 1

    def test_preflight_check_fails_and_exits_when_qdrant_fails(self) -> None:
        """When Qdrant get_collections fails, preflight_check logs error and exits with code 1."""
        mock_qdrant = MagicMock()
        mock_qdrant.get_collections.side_effect = ConnectionError(
            "Qdrant connection refused"
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch(
                "autonomous_cognition.full_cycle._get_repo_root",
                return_value=Path(tmp_dir),
            ):
                with pytest.raises(SystemExit) as exc_info:
                    preflight_check(
                        redis_client=None,
                        qdrant_client=mock_qdrant,
                        notify_discord=False,
                    )

        assert exc_info.value.code == 1

    def test_preflight_check_fails_and_exits_when_output_dir_not_writable(self) -> None:
        """When output directory cannot be created/written, preflight_check exits with code 1."""
        mock_redis = MagicMock()
        mock_redis.ping.return_value = True

        with tempfile.TemporaryDirectory() as tmp_dir:
            # Make the output directory read-only
            output_dir = Path(tmp_dir) / "_bmad-output" / "autocog" / "cycles"
            output_dir.mkdir(parents=True, exist_ok=True)
            output_dir.chmod(0o444)  # Read-only

            # Also need config dir
            config_dir = Path(tmp_dir) / "config"
            config_dir.mkdir()
            (config_dir / "autocog.yaml").write_text("test: value", encoding="utf-8")

            with patch(
                "autonomous_cognition.full_cycle._get_repo_root",
                return_value=Path(tmp_dir),
            ):
                with pytest.raises(SystemExit) as exc_info:
                    preflight_check(
                        redis_client=mock_redis,
                        qdrant_client=None,
                        notify_discord=False,
                    )

            # Restore permissions for cleanup
            output_dir.chmod(0o755)

        assert exc_info.value.code == 1

    def test_preflight_check_sends_discord_notification_on_failure(self) -> None:
        """When preflight fails and notify_discord=True, Discord notification is sent."""
        mock_redis = MagicMock()
        mock_redis.ping.side_effect = ConnectionError("Redis connection refused")

        mock_notifier = MagicMock()
        mock_notifier.notify_autocog_event.return_value = None
        mock_notifier.close.return_value = None

        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch(
                "autonomous_cognition.full_cycle._get_repo_root",
                return_value=Path(tmp_dir),
            ):
                with patch(
                    "autonomous_cognition.full_cycle.DiscordNotifier",
                    return_value=mock_notifier,
                ):
                    mock_loop = MagicMock()

                    async def mock_run_until(coro):
                        return coro

                    mock_loop.run_until_complete.side_effect = mock_run_until
                    with patch("asyncio.new_event_loop", return_value=mock_loop):
                        with pytest.raises(SystemExit):
                            preflight_check(
                                redis_client=mock_redis,
                                qdrant_client=None,
                                notify_discord=True,
                            )

        # Verify Discord notifier was called
        mock_notifier.notify_autocog_event.assert_called_once()
        call_kwargs = mock_notifier.notify_autocog_event.call_args.kwargs
        assert call_kwargs["event_type"] == "preflight_failed"
        assert call_kwargs["severity"] == "critical"
        assert "Redis connection refused" in call_kwargs["impact"]

    def test_preflight_check_with_multiple_failures_reports_both(self) -> None:
        """When both Redis and Qdrant fail, both failures are captured in Discord notification."""
        mock_redis = MagicMock()
        mock_redis.ping.side_effect = ConnectionError("Connection reset")
        mock_qdrant = MagicMock()
        mock_qdrant.get_collections.side_effect = ConnectionError("Qdrant timeout")

        mock_notifier = MagicMock()
        mock_notifier.notify_autocog_event.return_value = None
        mock_notifier.close.return_value = None

        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch(
                "autonomous_cognition.full_cycle._get_repo_root",
                return_value=Path(tmp_dir),
            ):
                with patch(
                    "autonomous_cognition.full_cycle.DiscordNotifier",
                    return_value=mock_notifier,
                ):
                    mock_loop = MagicMock()

                    async def mock_run_until(coro):
                        return coro

                    mock_loop.run_until_complete.side_effect = mock_run_until
                    with patch("asyncio.new_event_loop", return_value=mock_loop):
                        with pytest.raises(SystemExit):
                            preflight_check(
                                redis_client=mock_redis,
                                qdrant_client=mock_qdrant,
                                notify_discord=True,
                            )

        # Verify both failures were reported in the impact
        call_kwargs = mock_notifier.notify_autocog_event.call_args.kwargs
        impact = call_kwargs["impact"]
        assert "Redis ping failed: Connection reset" in impact
        assert "Qdrant connectivity failed: Qdrant timeout" in impact
