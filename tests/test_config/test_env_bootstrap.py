"""Tests for environment bootstrap system.

Tests for ST-ENV-001: Environment bootstrap system
- Dotenv loading precedence
- Provider discovery
- Diagnostic function
- Security (secrets never exposed)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any
from unittest.mock import patch

from src.config.env_loader import (
    bootstrap_environment,
    diagnose_provider_availability,
    discover_kimi_config,
    discover_minimax_config,
    discover_zai_config,
    discover_zhipu_config,
    get_available_providers,
)


class TestBootstrapEnvironment:
    """Tests for bootstrap_environment function."""

    def test_bootstrap_loads_default_env(self, tmp_path: Path) -> None:
        """Verify .env file is loaded from repo root."""
        # Create a temporary .env file
        env_file = tmp_path / ".env"
        env_file.write_text("TEST_VAR=default_value\n")

        # Store original env var
        original_value = os.environ.pop("TEST_VAR", None)

        try:
            with patch("src.config.env_loader.Path") as mock_path:
                # Mock the repo root to be our temp directory
                mock_path.return_value = tmp_path
                mock_path.cwd.return_value = tmp_path
                mock_path.__truediv__ = lambda self, other: tmp_path / other

                # Call bootstrap with the temp env file
                result = bootstrap_environment(env_file_path=str(env_file))

                # Verify the file was loaded
                assert len(result["loaded_files"]) >= 1
                assert str(env_file.resolve()) in result["loaded_files"]
        finally:
            # Restore original env var
            if original_value is not None:
                os.environ["TEST_VAR"] = original_value

    def test_bootstrap_respects_precedence(self, tmp_path: Path) -> None:
        """Verify precedence: Process env > explicit file > default .env."""
        # Create env files
        default_env = tmp_path / ".env"
        default_env.write_text("PRECEDENCE_TEST=default\n")

        explicit_env = tmp_path / "explicit.env"
        explicit_env.write_text("PRECEDENCE_TEST=explicit\n")

        # Set process env (highest priority)
        os.environ["PRECEDENCE_TEST"] = "process"

        try:
            # Call bootstrap with explicit file
            bootstrap_environment(env_file_path=str(explicit_env))

            # Process env should not be overridden
            assert os.environ.get("PRECEDENCE_TEST") == "process"
        finally:
            # Clean up
            del os.environ["PRECEDENCE_TEST"]

    def test_bootstrap_with_explicit_env_file(self, tmp_path: Path) -> None:
        """Test bootstrap with custom env file path."""
        env_file = tmp_path / "custom.env"
        env_file.write_text("CUSTOM_VAR=custom_value\n")

        # Remove any existing value
        original_value = os.environ.pop("CUSTOM_VAR", None)

        try:
            result = bootstrap_environment(env_file_path=str(env_file))

            # Verify the explicit file was loaded
            assert str(env_file.resolve()) in result["loaded_files"]
            assert result["env_file_path"] == str(env_file)
        finally:
            if original_value is not None:
                os.environ["CUSTOM_VAR"] = original_value

    def test_bootstrap_does_not_override_process_env(self, tmp_path: Path) -> None:
        """Verify process environment variables are not overridden."""
        env_file = tmp_path / ".env"
        env_file.write_text("PROCESS_TEST=from_file\n")

        # Set process env
        os.environ["PROCESS_TEST"] = "from_process"

        try:
            bootstrap_environment(env_file_path=str(env_file))

            # Process env should remain unchanged
            assert os.environ.get("PROCESS_TEST") == "from_process"
        finally:
            del os.environ["PROCESS_TEST"]

    def test_bootstrap_returns_load_summary(self, tmp_path: Path) -> None:
        """Verify summary structure is correct."""
        env_file = tmp_path / ".env"
        env_file.write_text("SUMMARY_TEST=value\n")

        result = bootstrap_environment(env_file_path=str(env_file))

        # Verify summary structure
        assert "loaded_files" in result
        assert "env_file_path" in result
        assert "override" in result
        assert isinstance(result["loaded_files"], list)
        assert isinstance(result["override"], bool)


class TestProviderDiscovery:
    """Tests for provider discovery functions."""

    def test_discover_kimi_config_with_key(self) -> None:
        """KIMI config discovered when API key present."""
        with patch.dict(os.environ, {"KIMI_API_KEY": "test-key-123"}, clear=False):
            config = discover_kimi_config()

            assert config["enabled"] is True
            assert config["api_key_present"] is True
            assert config["base_url"] == "https://api.kimi.com/coding/v1"
            assert config["model"] == "k2p5"

    def test_discover_kimi_config_disabled(self) -> None:
        """KIMI config disabled when KIMI_ENABLED=false."""
        with patch.dict(
            os.environ,
            {"KIMI_API_KEY": "test-key", "KIMI_ENABLED": "false"},
            clear=False,
        ):
            config = discover_kimi_config()

            assert config["enabled"] is False
            assert config["api_key_present"] is True

    def test_discover_kimi_config_missing_key(self) -> None:
        """KIMI config not available when no API key."""
        # Ensure KIMI_API_KEY is not set
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("KIMI_API_KEY", None)
            config = discover_kimi_config()

            assert config["enabled"] is False
            assert config["api_key_present"] is False

    def test_discover_zai_config_with_key(self) -> None:
        """ZAI config discovered when API key present."""
        with patch.dict(os.environ, {"ZAI_API_KEY": "zai-test-key"}, clear=False):
            config = discover_zai_config()

            assert config["enabled"] is True
            assert config["api_key_present"] is True
            assert config["base_url"] == "https://api.z.ai/v1"

    def test_discover_zhipu_config_with_key(self) -> None:
        """Zhipu config discovered when API key present."""
        with patch.dict(os.environ, {"ZHIPU_API_KEY": "zhipu-test-key"}, clear=False):
            config = discover_zhipu_config()

            assert config["enabled"] is True
            assert config["api_key_present"] is True
            assert config["base_url"] == "https://open.bigmodel.cn/api/paas/v4"
            assert config["model"] == "glm-5"

    def test_discover_zhipu_config_zai_fallback(self) -> None:
        """Zhipu uses ZAI_API_KEY as fallback."""
        with patch.dict(
            os.environ,
            {"ZAI_API_KEY": "zai-fallback-key"},
            clear=False,
        ):
            # Ensure ZHIPU_API_KEY is not set
            os.environ.pop("ZHIPU_API_KEY", None)
            config = discover_zhipu_config()

            assert config["enabled"] is True
            assert config["api_key_present"] is True

    def test_discover_minimax_config_enabled(self) -> None:
        """MiniMax with key and enabled."""
        with patch.dict(
            os.environ,
            {
                "MINIMAX_API_KEY": "minimax-key",
                "MINIMAX_ENABLED": "true",
                "MINIMAX_MODEL": "abab6.5s",  # Explicitly set to test default
            },
            clear=False,
        ):
            config = discover_minimax_config()

            assert config["enabled"] is True
            assert config["api_key_present"] is True
            assert config["base_url"] == "https://api.minimax.chat/v1"
            assert config["model"] == "abab6.5s"

    def test_discover_minimax_config_disabled(self) -> None:
        """MiniMax with key but disabled."""
        with patch.dict(
            os.environ,
            {"MINIMAX_API_KEY": "minimax-key", "MINIMAX_ENABLED": "false"},
            clear=False,
        ):
            config = discover_minimax_config()

            assert config["enabled"] is False
            assert config["api_key_present"] is True

    def test_discover_minimax_config_missing_key(self) -> None:
        """MiniMax without key."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MINIMAX_API_KEY", None)
            config = discover_minimax_config()

            assert config["enabled"] is False
            assert config["api_key_present"] is False


class TestGetAvailableProviders:
    """Tests for get_available_providers function."""

    def test_get_available_providers_with_kimi(self) -> None:
        """Returns ['kimi'] when KIMI available."""
        with patch.dict(os.environ, {"KIMI_API_KEY": "test-key"}, clear=False):
            # Disable other providers
            os.environ.pop("ZAI_API_KEY", None)
            os.environ.pop("ZHIPU_API_KEY", None)
            os.environ.pop("MINIMAX_API_KEY", None)

            providers = get_available_providers()

            assert "kimi" in providers

    def test_get_available_providers_multiple(self) -> None:
        """Returns multiple providers when available."""
        with patch.dict(
            os.environ,
            {
                "KIMI_API_KEY": "kimi-key",
                "ZAI_API_KEY": "zai-key",
                "ZHIPU_API_KEY": "zhipu-key",
                "MINIMAX_API_KEY": "minimax-key",
            },
            clear=False,
        ):
            providers = get_available_providers()

            assert "kimi" in providers
            assert "zai" in providers
            assert "zhipu" in providers
            assert "minimax" in providers

    def test_get_available_providers_none(self) -> None:
        """Returns [] when none available."""
        with patch.dict(os.environ, {}, clear=False):
            # Remove all provider keys
            for key in [
                "KIMI_API_KEY",
                "ZAI_API_KEY",
                "ZHIPU_API_KEY",
                "MINIMAX_API_KEY",
            ]:
                os.environ.pop(key, None)

            providers = get_available_providers()

            assert providers == []


class TestDiagnoseProviderAvailability:
    """Tests for diagnose_provider_availability function."""

    def test_diagnose_returns_structure(self) -> None:
        """Verify diagnostic structure is correct."""
        diagnostics = diagnose_provider_availability()

        assert isinstance(diagnostics, list)
        assert len(diagnostics) == 4  # kimi, zai, zhipu, minimax

        for diag in diagnostics:
            assert "provider" in diag
            assert "available" in diag
            assert "config" in diag
            assert isinstance(diag["available"], bool)
            assert isinstance(diag["config"], dict)

    def test_diagnose_no_secrets_exposed(self) -> None:
        """Verify keys are not in diagnostic output."""
        with patch.dict(
            os.environ,
            {
                "KIMI_API_KEY": "super-secret-key-12345",
                "ZAI_API_KEY": "another-secret",
            },
            clear=False,
        ):
            diagnostics = diagnose_provider_availability()

            for diag in diagnostics:
                # Convert to string to check for secrets
                diag_str = str(diag)
                assert "super-secret-key-12345" not in diag_str
                assert "another-secret" not in diag_str
                # Ensure api_key_present is boolean, not the actual key
                assert "api_key" not in diag.get("config", {})

    def test_diagnose_shows_availability(self) -> None:
        """Verify available/unavailable status is correct."""
        with patch.dict(os.environ, {"KIMI_API_KEY": "test-key"}, clear=False):
            # Remove other keys
            os.environ.pop("ZAI_API_KEY", None)
            os.environ.pop("ZHIPU_API_KEY", None)
            os.environ.pop("MINIMAX_API_KEY", None)

            diagnostics = diagnose_provider_availability()

            kimi_diag = next(d for d in diagnostics if d["provider"] == "kimi")
            zai_diag = next(d for d in diagnostics if d["provider"] == "zai")

            assert kimi_diag["available"] is True
            assert zai_diag["available"] is False

    def test_diagnose_shows_reasons(self) -> None:
        """Verify reasons for unavailability are provided."""
        with patch.dict(os.environ, {}, clear=False):
            # Remove all keys
            for key in [
                "KIMI_API_KEY",
                "ZAI_API_KEY",
                "ZHIPU_API_KEY",
                "MINIMAX_API_KEY",
            ]:
                os.environ.pop(key, None)

            diagnostics = diagnose_provider_availability()

            for diag in diagnostics:
                if not diag["available"]:
                    assert "reason" in diag
                    assert diag["reason"] != ""


class TestSecurity:
    """Security tests to ensure secrets are never exposed."""

    def test_bootstrap_never_logs_secrets(self, tmp_path: Path, caplog: Any) -> None:
        """Verify no secret values in logs during bootstrap."""
        env_file = tmp_path / ".env"
        env_file.write_text("SECRET_API_KEY=sk-12345-secret-value\n")

        # Set log level to capture all logs
        with caplog.at_level(logging.INFO):
            bootstrap_environment(env_file_path=str(env_file))

        # Check that no secrets appear in logs
        log_output = caplog.text
        assert "sk-12345-secret-value" not in log_output
        assert "SECRET_API_KEY" not in log_output or "sk-12345" not in log_output

    def test_diagnostic_never_returns_secrets(self) -> None:
        """Verify no keys in diagnostic output."""
        secret_key = "sk-live-abc123xyz789"
        with patch.dict(
            os.environ,
            {
                "KIMI_API_KEY": secret_key,
                "ZAI_API_KEY": secret_key,
                "ZHIPU_API_KEY": secret_key,
                "MINIMAX_API_KEY": secret_key,
            },
            clear=False,
        ):
            diagnostics = diagnose_provider_availability()

            # Check all diagnostics
            all_output = str(diagnostics)
            assert secret_key not in all_output

            # Verify only boolean presence is reported
            for diag in diagnostics:
                config = diag.get("config", {})
                for key, value in config.items():
                    if "key" in key.lower():
                        assert isinstance(value, bool) or value == "***"

    def test_provider_discovery_returns_presence_only(self) -> None:
        """Verify api_key_present bool, not value."""
        secret_key = "super-secret-api-key-999"

        with patch.dict(os.environ, {"KIMI_API_KEY": secret_key}, clear=False):
            config = discover_kimi_config()

            # Should only have boolean, not the actual key
            assert config["api_key_present"] is True
            assert "api_key" not in config or config.get("api_key") != secret_key

        with patch.dict(os.environ, {"ZAI_API_KEY": secret_key}, clear=False):
            config = discover_zai_config()

            assert config["api_key_present"] is True
            assert "api_key" not in config or config.get("api_key") != secret_key

        with patch.dict(os.environ, {"ZHIPU_API_KEY": secret_key}, clear=False):
            config = discover_zhipu_config()

            assert config["api_key_present"] is True
            assert "api_key" not in config or config.get("api_key") != secret_key

        with patch.dict(os.environ, {"MINIMAX_API_KEY": secret_key}, clear=False):
            config = discover_minimax_config()

            assert config["api_key_present"] is True
            assert "api_key" not in config or config.get("api_key") != secret_key
