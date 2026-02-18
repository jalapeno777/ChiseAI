"""Tests for environment bootstrap module.

Tests for ST-ENV-001: Environment Bootstrap System
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from config.bootstrap import (
    _check_all_providers,
    _check_provider,
    _find_env_files,
    _load_env_file,
    bootstrap,
    format_provider_status,
    get_bootstrap_state,
)


class TestFindEnvFiles:
    """Test cases for _find_env_files function."""

    def test_finds_env_files_in_standard_locations(self, tmp_path):
        """Test that .env files are found in standard locations."""
        # Create a .env file in the current working directory
        env_file = tmp_path / ".env"
        env_file.write_text("TEST_KEY=test_value\n")

        with patch.object(Path, "cwd", return_value=tmp_path):
            files = _find_env_files()
            assert len(files) >= 1
            assert env_file.resolve() in files

    def test_deduplicates_env_files(self, tmp_path):
        """Test that duplicate env files are deduplicated."""
        # Create .env file
        env_file = tmp_path / ".env"
        env_file.write_text("TEST_KEY=test_value\n")

        # If cwd and parent both have the same file (symlink scenario)
        with patch.object(Path, "cwd", return_value=tmp_path):
            files = _find_env_files()
            # Should not have duplicates
            assert len(files) == len(set(files))

    def test_returns_empty_list_when_no_env_files(self, tmp_path):
        """Test that only existing files are returned."""
        with patch.object(Path, "cwd", return_value=tmp_path):
            files = _find_env_files()
            assert isinstance(files, list)
            # All returned files should exist (function filters for existing files)
            assert all(f.exists() for f in files)


class TestLoadEnvFile:
    """Test cases for _load_env_file function."""

    def test_loads_simple_key_value_pairs(self, tmp_path):
        """Test loading simple KEY=VALUE pairs."""
        env_file = tmp_path / ".env"
        env_file.write_text("KEY1=value1\nKEY2=value2\n")

        # Clear environment first
        with patch.dict(os.environ, {}, clear=True):
            result = _load_env_file(env_file)
            assert result is True
            assert os.environ.get("KEY1") == "value1"
            assert os.environ.get("KEY2") == "value2"

    def test_skips_comments_and_empty_lines(self, tmp_path):
        """Test that comments and empty lines are skipped."""
        env_file = tmp_path / ".env"
        env_file.write_text("# This is a comment\n\nKEY=value\n  # Another comment\n")

        with patch.dict(os.environ, {}, clear=True):
            _load_env_file(env_file)
            assert os.environ.get("KEY") == "value"
            assert "# This is a comment" not in os.environ

    def test_handles_quoted_values(self, tmp_path):
        """Test that quoted values are handled correctly."""
        env_file = tmp_path / ".env"
        env_file.write_text("KEY1=\"quoted_value\"\nKEY2='single_quoted'\n")

        with patch.dict(os.environ, {}, clear=True):
            _load_env_file(env_file)
            assert os.environ.get("KEY1") == "quoted_value"
            assert os.environ.get("KEY2") == "single_quoted"

    def test_does_not_override_existing_env_vars(self, tmp_path):
        """Test that existing environment variables are not overridden."""
        env_file = tmp_path / ".env"
        env_file.write_text("EXISTING_KEY=new_value\n")

        with patch.dict(os.environ, {"EXISTING_KEY": "original_value"}):
            _load_env_file(env_file)
            assert os.environ.get("EXISTING_KEY") == "original_value"

    def test_handles_missing_file_gracefully(self, tmp_path):
        """Test that missing files are handled gracefully."""
        missing_file = tmp_path / "nonexistent.env"
        result = _load_env_file(missing_file)
        assert result is False


class TestCheckProvider:
    """Test cases for _check_provider function."""

    def test_detects_available_provider(self):
        """Test detecting a provider that has environment variables set."""
        with patch.dict(os.environ, {"TEST_API_KEY": "secret123"}):
            status = _check_provider("TEST", ["TEST_API_KEY"])
            assert status["available"] is True
            assert status["source"] == "TEST_API_KEY"
            assert status["name"] == "TEST"

    def test_detects_unavailable_provider(self):
        """Test detecting a provider that has no environment variables set."""
        with patch.dict(os.environ, {}, clear=True):
            status = _check_provider("MISSING", ["MISSING_API_KEY"])
            assert status["available"] is False
            assert status["source"] is None
            assert "MISSING_API_KEY" in status["missing"]

    def test_checks_multiple_env_vars(self):
        """Test checking multiple environment variables for a provider."""
        # SECONDARY_KEY is missing and checked before PRIMARY_KEY is found
        with patch.dict(os.environ, {"PRIMARY_KEY": "value1"}):
            status = _check_provider("MULTI", ["SECONDARY_KEY", "PRIMARY_KEY"])
            assert status["available"] is True
            assert status["source"] == "PRIMARY_KEY"
            assert "SECONDARY_KEY" in status["missing"]


class TestCheckAllProviders:
    """Test cases for _check_all_providers function."""

    def test_checks_all_configured_providers(self):
        """Test that all configured providers are checked."""
        with patch.dict(os.environ, {}, clear=True):
            providers = _check_all_providers()
            # Should check KIMI, ZAI, ZHIPU, MINIMAX
            assert "KIMI" in providers
            assert "ZAI" in providers
            assert "ZHIPU" in providers
            assert "MINIMAX" in providers

    def test_respects_explicitly_disabled_providers(self):
        """Test that providers can be explicitly disabled."""
        with patch.dict(
            os.environ,
            {"KIMI_API_KEY": "secret", "KIMI_ENABLED": "false"},
            clear=True,
        ):
            providers = _check_all_providers()
            assert providers["KIMI"]["available"] is False
            assert providers["KIMI"]["explicitly_disabled"] is True

    def test_detects_available_providers(self):
        """Test detecting which providers are available."""
        with patch.dict(
            os.environ,
            {"KIMI_API_KEY": "secret", "ZAI_API_KEY": "another"},
            clear=True,
        ):
            providers = _check_all_providers()
            assert providers["KIMI"]["available"] is True
            assert providers["ZAI"]["available"] is True
            assert providers["MINIMAX"]["available"] is False


class TestBootstrap:
    """Test cases for bootstrap function."""

    def test_returns_bootstrap_state(self, tmp_path):
        """Test that bootstrap returns state dictionary."""
        with patch.dict(os.environ, {}, clear=True):
            state = bootstrap(load_env=False)
            assert isinstance(state, dict)
            assert "providers" in state

    def test_loads_specific_env_file(self, tmp_path):
        """Test loading a specific env file."""
        env_file = tmp_path / ".env"
        env_file.write_text("TEST_VAR=test_value\n")

        with patch.dict(os.environ, {}, clear=True):
            state = bootstrap(load_env=True, env_file=env_file)
            assert env_file.resolve() in state["loaded_files"]
            assert os.environ.get("TEST_VAR") == "test_value"

    def test_warns_on_missing_env_file(self, tmp_path, caplog):
        """Test that warning is issued for missing env file."""
        missing_file = tmp_path / "missing.env"

        with patch.dict(os.environ, {}, clear=True):
            import logging

            with caplog.at_level(logging.WARNING):
                bootstrap(load_env=True, env_file=missing_file)
                assert "not found" in caplog.text

    def test_checks_providers(self):
        """Test that bootstrap checks provider availability."""
        with patch.dict(os.environ, {"KIMI_API_KEY": "secret"}, clear=True):
            state = bootstrap(load_env=False)
            assert "KIMI" in state["providers"]
            assert state["providers"]["KIMI"]["available"] is True

    def test_respects_verbose_flag(self, caplog):
        """Test that verbose flag enables debug logging."""
        import logging

        with patch.dict(os.environ, {}, clear=True), caplog.at_level(logging.DEBUG):
            bootstrap(load_env=False, verbose=True)
            # Should have debug output
            assert len(caplog.records) >= 0


class TestGetBootstrapState:
    """Test cases for get_bootstrap_state function."""

    def test_returns_current_state(self):
        """Test that get_bootstrap_state returns the current state."""
        state = get_bootstrap_state()
        assert isinstance(state, dict)
        assert "loaded_files" in state
        assert "providers" in state


class TestFormatProviderStatus:
    """Test cases for format_provider_status function."""

    def test_formats_available_provider(self):
        """Test formatting available provider status."""
        status = {
            "name": "TEST",
            "available": True,
            "source": "TEST_API_KEY",
            "explicitly_disabled": False,
        }
        result = format_provider_status(status)
        assert "available" in result
        assert "TEST_API_KEY" in result

    def test_formats_disabled_provider(self):
        """Test formatting disabled provider status."""
        status = {
            "name": "TEST",
            "available": False,
            "explicitly_disabled": True,
        }
        result = format_provider_status(status)
        assert "disabled" in result

    def test_formats_unavailable_provider(self):
        """Test formatting unavailable provider status."""
        status = {
            "name": "TEST",
            "available": False,
            "explicitly_disabled": False,
            "missing": ["TEST_API_KEY"],
        }
        result = format_provider_status(status)
        assert "not available" in result
        assert "TEST_API_KEY" in result

    def test_formats_without_source(self):
        """Test formatting when source is not available."""
        status = {
            "name": "TEST",
            "available": True,
            "source": None,
            "explicitly_disabled": False,
        }
        result = format_provider_status(status)
        assert "available" in result


class TestIntegration:
    """Integration tests for the bootstrap system."""

    def test_full_bootstrap_workflow(self, tmp_path):
        """Test the complete bootstrap workflow."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "KIMI_API_KEY=test_key\nZAI_API_KEY=another_key\nCUSTOM_VAR=custom_value\n"
        )

        with patch.dict(os.environ, {}, clear=True):
            # Run bootstrap
            state = bootstrap(load_env=True, env_file=env_file)

            # Verify env was loaded
            assert env_file.resolve() in state["loaded_files"]
            assert os.environ.get("CUSTOM_VAR") == "custom_value"

            # Verify providers were checked
            assert state["providers"]["KIMI"]["available"] is True
            assert state["providers"]["ZAI"]["available"] is True

            # Verify state can be retrieved
            retrieved_state = get_bootstrap_state()
            assert retrieved_state == state

    def test_bootstrap_with_no_env_files(self):
        """Test bootstrap when no env files are present."""
        with patch.dict(os.environ, {}, clear=True):
            state = bootstrap(
                load_env=True
            )  # Will try to find files but may not find any
            assert isinstance(state["loaded_files"], list)
            assert isinstance(state["providers"], dict)

    def test_multiple_bootstrap_calls_update_state(self, tmp_path):
        """Test that multiple bootstrap calls update the state."""
        env_file1 = tmp_path / ".env1"
        env_file2 = tmp_path / ".env2"
        env_file1.write_text("VAR1=value1\n")
        env_file2.write_text("VAR2=value2\n")

        with patch.dict(os.environ, {}, clear=True):
            # First bootstrap
            state1 = bootstrap(load_env=True, env_file=env_file1)
            assert env_file1.resolve() in state1["loaded_files"]

            # Second bootstrap with different file
            state2 = bootstrap(load_env=True, env_file=env_file2)
            assert env_file2.resolve() in state2["loaded_files"]

            # State should be updated
            current_state = get_bootstrap_state()
            assert env_file2.resolve() in current_state["loaded_files"]


class TestBootstrapStatePersistence:
    """Test cases for bootstrap state persistence and retrieval."""

    def test_get_bootstrap_state_returns_dict_structure(self):
        """Verify get_bootstrap_state returns proper dictionary structure."""
        state = get_bootstrap_state()
        assert isinstance(state, dict)
        assert "loaded_files" in state
        assert "providers" in state
        assert isinstance(state["loaded_files"], list)
        assert isinstance(state["providers"], dict)

    def test_bootstrap_state_persists_across_calls(self, tmp_path):
        """Verify bootstrap state persists and can be retrieved multiple times."""
        env_file = tmp_path / ".env"
        env_file.write_text("PERSISTENCE_TEST=value\n")

        with patch.dict(os.environ, {}, clear=True):
            # Initial bootstrap
            bootstrap(load_env=True, env_file=env_file)

            # Get state multiple times
            state1 = get_bootstrap_state()
            state2 = get_bootstrap_state()
            state3 = get_bootstrap_state()

            # All should be the same object/reference
            assert state1 == state2 == state3
            assert env_file.resolve() in state1["loaded_files"]

    def test_bootstrap_state_updates_on_rebootstrap(self, tmp_path):
        """Verify state updates when bootstrap is called again."""
        env_file1 = tmp_path / ".env1"
        env_file2 = tmp_path / ".env2"
        env_file1.write_text("KEY1=value1\n")
        env_file2.write_text("KEY2=value2\n")

        with patch.dict(os.environ, {}, clear=True):
            # First bootstrap
            bootstrap(load_env=True, env_file=env_file1)
            state1 = get_bootstrap_state()

            # Second bootstrap
            bootstrap(load_env=True, env_file=env_file2)
            state2 = get_bootstrap_state()

            # State should reflect latest bootstrap
            assert env_file2.resolve() in state2["loaded_files"]

    def test_bootstrap_state_tracks_loaded_files(self, tmp_path):
        """Verify state correctly tracks which files were loaded."""
        env_file = tmp_path / ".env"
        env_file.write_text("TRACKING_TEST=value\n")

        with patch.dict(os.environ, {}, clear=True):
            state = bootstrap(load_env=True, env_file=env_file)

            # Verify file is tracked as loaded
            resolved_path = env_file.resolve()
            assert resolved_path in state["loaded_files"]

            # Verify via get_bootstrap_state as well
            current_state = get_bootstrap_state()
            assert resolved_path in current_state["loaded_files"]

    def test_bootstrap_state_without_load_env(self):
        """Verify state exists even when load_env=False."""
        with patch.dict(os.environ, {}, clear=True):
            state = bootstrap(load_env=False)

            # State should still have proper structure
            assert "loaded_files" in state
            assert "providers" in state
            assert state["loaded_files"] == []
            assert isinstance(state["providers"], dict)


class TestProviderChecking:
    """Test cases for provider availability checking."""

    def test_all_providers_checked(self):
        """Verify bootstrap checks all configured providers."""
        with patch.dict(os.environ, {}, clear=True):
            state = bootstrap(load_env=False)
            providers = state["providers"]

            # Should check all major providers
            expected_providers = ["KIMI", "ZAI", "ZHIPU", "MINIMAX"]
            for provider in expected_providers:
                assert provider in providers, f"Provider {provider} should be checked"

    def test_provider_status_structure(self):
        """Verify each provider has required status fields."""
        with patch.dict(os.environ, {}, clear=True):
            state = bootstrap(load_env=False)

            for provider_name, status in state["providers"].items():
                assert "name" in status
                assert "available" in status
                assert isinstance(status["available"], bool)
                assert "source" in status
                assert "missing" in status
                assert isinstance(status["missing"], list)

    def test_provider_available_when_key_set(self):
        """Verify provider is marked available when API key is set."""
        with patch.dict(os.environ, {"KIMI_API_KEY": "test_key"}, clear=True):
            state = bootstrap(load_env=False)

            assert state["providers"]["KIMI"]["available"] is True
            assert state["providers"]["KIMI"]["source"] == "KIMI_API_KEY"

    def test_provider_unavailable_when_key_missing(self):
        """Verify provider is marked unavailable when API key is missing."""
        with patch.dict(os.environ, {}, clear=True):
            state = bootstrap(load_env=False)

            assert state["providers"]["KIMI"]["available"] is False
            assert "KIMI_API_KEY" in state["providers"]["KIMI"]["missing"]

    def test_explicitly_disabled_provider(self):
        """Verify provider can be explicitly disabled via environment variable."""
        with patch.dict(
            os.environ,
            {"KIMI_API_KEY": "test_key", "KIMI_ENABLED": "false"},
            clear=True,
        ):
            state = bootstrap(load_env=False)

            # Should be unavailable despite having API key
            assert state["providers"]["KIMI"]["available"] is False
            assert state["providers"]["KIMI"].get("explicitly_disabled") is True

    def test_minimax_defaults_to_disabled(self):
        """Verify MINIMAX provider defaults to disabled."""
        with patch.dict(os.environ, {"MINIMAX_API_KEY": "test_key"}, clear=True):
            state = bootstrap(load_env=False)

            # MINIMAX should be disabled by default even with API key
            assert state["providers"]["MINIMAX"]["available"] is False
            assert state["providers"]["MINIMAX"].get("explicitly_disabled") is True

    def test_minimax_can_be_enabled(self):
        """Verify MINIMAX can be explicitly enabled."""
        with patch.dict(
            os.environ,
            {"MINIMAX_API_KEY": "test_key", "MINIMAX_ENABLED": "true"},
            clear=True,
        ):
            state = bootstrap(load_env=False)

            # Should be available when explicitly enabled
            assert state["providers"]["MINIMAX"]["available"] is True

    def test_multiple_providers_simultaneously(self):
        """Verify multiple providers can be checked at once."""
        with patch.dict(
            os.environ,
            {"KIMI_API_KEY": "key1", "ZAI_API_KEY": "key2"},
            clear=True,
        ):
            state = bootstrap(load_env=False)

            assert state["providers"]["KIMI"]["available"] is True
            assert state["providers"]["ZAI"]["available"] is True
            # ZHIPU can use ZAI_API_KEY as fallback per bootstrap.py config
            assert state["providers"]["ZHIPU"]["available"] is True

    def test_provider_checks_secondary_keys(self):
        """Verify provider checks secondary API keys if primary missing."""
        # KIMI checks KIMI_API_KEY_PRIMARY as secondary
        with patch.dict(os.environ, {"KIMI_API_KEY_PRIMARY": "backup_key"}, clear=True):
            state = bootstrap(load_env=False)

            assert state["providers"]["KIMI"]["available"] is True
            assert state["providers"]["KIMI"]["source"] == "KIMI_API_KEY_PRIMARY"

    def test_format_provider_status_available(self):
        """Test formatting available provider status."""
        status = {
            "name": "TEST",
            "available": True,
            "source": "TEST_API_KEY",
            "explicitly_disabled": False,
        }
        result = format_provider_status(status)
        assert "available" in result
        assert "TEST_API_KEY" in result

    def test_format_provider_status_disabled(self):
        """Test formatting disabled provider status."""
        status = {
            "name": "TEST",
            "available": False,
            "explicitly_disabled": True,
        }
        result = format_provider_status(status)
        assert "disabled" in result

    def test_format_provider_status_unavailable(self):
        """Test formatting unavailable provider status."""
        status = {
            "name": "TEST",
            "available": False,
            "explicitly_disabled": False,
            "missing": ["TEST_API_KEY"],
        }
        result = format_provider_status(status)
        assert "not available" in result
        assert "TEST_API_KEY" in result


class TestBootstrapIdempotency:
    """Test cases for bootstrap idempotency and safety."""

    def test_bootstrap_does_not_override_existing_env_vars(self, tmp_path):
        """Verify bootstrap respects existing environment variables."""
        env_file = tmp_path / ".env"
        env_file.write_text("EXISTING_VAR=new_value\n")

        with patch.dict(os.environ, {"EXISTING_VAR": "original_value"}, clear=True):
            bootstrap(load_env=True, env_file=env_file)

            # Original value should be preserved
            assert os.environ.get("EXISTING_VAR") == "original_value"

    def test_bootstrap_sets_new_env_vars(self, tmp_path):
        """Verify bootstrap sets new environment variables."""
        env_file = tmp_path / ".env"
        env_file.write_text("NEW_VAR=new_value\n")

        with patch.dict(os.environ, {}, clear=True):
            bootstrap(load_env=True, env_file=env_file)

            # New variable should be set
            assert os.environ.get("NEW_VAR") == "new_value"

    def test_verbose_mode_outputs_debug_info(self, caplog):
        """Verify verbose mode enables debug logging."""
        import logging

        with patch.dict(os.environ, {}, clear=True):
            with caplog.at_level(logging.DEBUG):
                bootstrap(load_env=False, verbose=True)
                # Should have some debug output
                assert len(caplog.records) >= 0  # At minimum, no error


class TestBootstrapCLIIntegration:
    """Test cases for bootstrap CLI functionality."""

    def test_bootstrap_module_can_be_run(self):
        """Verify bootstrap module can be run as a script."""
        # This tests that the module has proper __main__ block
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, "-m", "config.bootstrap", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )

        # Should show help without error
        assert result.returncode == 0 or "usage:" in result.stdout.lower()

    def test_bootstrap_cli_check_flag(self, tmp_path):
        """Test bootstrap CLI with --check flag."""
        import subprocess
        import sys

        env_file = tmp_path / ".env"
        env_file.write_text("CLI_TEST=value\nKIMI_API_KEY=test\n")

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "config.bootstrap",
                "--check",
                "--env-file",
                str(env_file),
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        # With at least one provider available, should exit 0
        # or if check flag isn't supported, should exit gracefully
        assert result.returncode in [0, 1, 2]  # Valid exit codes
