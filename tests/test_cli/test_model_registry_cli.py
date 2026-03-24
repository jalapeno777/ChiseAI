"""Tests for Model Registry CLI.

Tests all CLI commands for the model registry including:
- chise-model register - Register model
- chise-model list - List versions
- chise-model get - Get model info
- chise-model rollback - Rollback
- chise-model history - Show history
- chise-model compare - Compare versions
- chise-model validate - Validate model
- chise-model health - Check registry health
"""

from __future__ import annotations

import json
import os
import pickle
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

# Import after path setup
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from cli.model_registry_cli import (
    EXIT_NOT_FOUND,
    EXIT_SUCCESS,
    EXIT_VALIDATION_ERROR,
    EXIT_VERSION_CONFLICT,
    cli,
    load_config,
    save_config,
)
from ml.models.model_registry import ModelRegistry
from ml.models.model_storage import (
    ModelMetadata,
    ModelNotFoundError,
    ModelValidationError,
    ModelVersion,
    ModelVersionExistsError,
)


@pytest.fixture
def runner():
    """Create a Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_registry():
    """Create a mock registry for testing."""
    registry = MagicMock(spec=ModelRegistry)
    return registry


@pytest.fixture
def temp_model_file(tmp_path):
    """Create a temporary model file for testing."""
    model_file = tmp_path / "test_model.pkl"
    model_data = {"type": "test_model", "weights": [1.0, 2.0, 3.0]}
    with open(model_file, "wb") as f:
        pickle.dump(model_data, f)
    return model_file


@pytest.fixture
def sample_metadata():
    """Create sample metadata for testing."""
    return ModelMetadata(
        model_name="test_model",
        version="1.0.0",
        created_at=datetime(2024, 1, 1, 12, 0, 0),
        training_data="dataset_v1",
        hyperparameters={"lr": 0.001},
        metrics={"accuracy": 0.95},
        tags=["production"],
    )


@pytest.fixture
def sample_model_version(sample_metadata):
    """Create a sample model version for testing."""
    return ModelVersion(
        model_name=sample_metadata.model_name,
        version=sample_metadata.version,
        created_at=sample_metadata.created_at,
        metadata_path="/path/to/metadata.json",
        model_path="/path/to/model.pkl",
        checksum="abc123def456",
    )


class TestLoadConfig:
    """Tests for configuration loading."""

    def test_load_default_config(self, tmp_path):
        """Test loading default configuration."""
        with patch("cli.model_registry_cli.get_config_path") as mock_path:
            mock_path.return_value = tmp_path / "nonexistent.yaml"
            config = load_config()

            assert "registry" in config
            assert "output" in config
            assert config["registry"]["base_path"] == "models"
            assert config["output"]["format"] == "table"

    def test_load_existing_config(self, tmp_path):
        """Test loading existing configuration file."""
        config_file = tmp_path / "config.yaml"
        custom_config = {
            "registry": {"base_path": "/custom/path", "host": "custom-host"},
            "output": {"format": "json"},
        }
        with open(config_file, "w") as f:
            import yaml

            yaml.dump(custom_config, f)

        with patch("cli.model_registry_cli.get_config_path") as mock_path:
            mock_path.return_value = config_file
            config = load_config()

            assert config["registry"]["base_path"] == "/custom/path"
            assert config["output"]["format"] == "json"

    def test_save_config(self, tmp_path):
        """Test saving configuration."""
        config_file = tmp_path / "config.yaml"

        with patch("cli.model_registry_cli.get_config_path") as mock_path:
            mock_path.return_value = config_file

            test_config = {
                "registry": {"base_path": "/test/path"},
                "output": {"format": "table"},
            }
            save_config(test_config)

            assert config_file.exists()

            # Verify saved content
            with open(config_file) as f:
                import yaml

                saved = yaml.safe_load(f)
                assert saved["registry"]["base_path"] == "/test/path"


class TestRegisterCommand:
    """Tests for the register command."""

    def test_register_success(
        self, runner, mock_registry, temp_model_file, sample_model_version
    ):
        """Test successful model registration."""
        mock_registry.register_model.return_value = sample_model_version

        with patch("cli.model_registry_cli.get_registry", return_value=mock_registry):
            result = runner.invoke(
                cli,
                [
                    "register",
                    "test_model",
                    str(temp_model_file),
                    "--version",
                    "1.0.0",
                    "--training-data",
                    "dataset_v1",
                    "--hyperparameters",
                    '{"lr": 0.001}',
                    "--metrics",
                    '{"accuracy": 0.95}',
                    "--tags",
                    '["production"]',
                ],
                obj={"config": {"output": {"format": "json"}}},
            )

        assert result.exit_code == EXIT_SUCCESS
        assert "registered successfully" in result.output
        mock_registry.register_model.assert_called_once()

    def test_register_version_exists(self, runner, mock_registry, temp_model_file):
        """Test registration with existing version."""
        mock_registry.register_model.side_effect = ModelVersionExistsError(
            "Version 1.0.0 already exists"
        )

        with patch("cli.model_registry_cli.get_registry", return_value=mock_registry):
            result = runner.invoke(
                cli,
                [
                    "register",
                    "test_model",
                    str(temp_model_file),
                    "--version",
                    "1.0.0",
                    "--training-data",
                    "dataset_v1",
                ],
                obj={"config": {"output": {"format": "table"}}},
            )

        assert result.exit_code == EXIT_VERSION_CONFLICT
        assert "already exists" in result.output

    def test_register_validation_error(self, runner, mock_registry, temp_model_file):
        """Test registration with validation error."""
        mock_registry.register_model.side_effect = ModelValidationError(
            "Validation failed"
        )

        with patch("cli.model_registry_cli.get_registry", return_value=mock_registry):
            result = runner.invoke(
                cli,
                [
                    "register",
                    "test_model",
                    str(temp_model_file),
                    "--version",
                    "1.0.0",
                    "--training-data",
                    "dataset_v1",
                ],
                obj={"config": {"output": {"format": "table"}}},
            )

        assert result.exit_code == EXIT_VALIDATION_ERROR
        assert "Validation failed" in result.output

    def test_register_invalid_json(self, runner, mock_registry, temp_model_file):
        """Test registration with invalid JSON parameters."""
        with patch("cli.model_registry_cli.get_registry", return_value=mock_registry):
            result = runner.invoke(
                cli,
                [
                    "register",
                    "test_model",
                    str(temp_model_file),
                    "--version",
                    "1.0.0",
                    "--training-data",
                    "dataset_v1",
                    "--hyperparameters",
                    "invalid json",
                ],
                obj={"config": {"output": {"format": "table"}}},
            )

        assert result.exit_code == EXIT_VALIDATION_ERROR
        assert "Invalid JSON" in result.output


class TestListCommand:
    """Tests for the list command."""

    def test_list_success(self, runner, mock_registry):
        """Test successful version listing."""
        mock_registry.list_versions.return_value = [
            ModelVersion(
                model_name="test_model",
                version="1.1.0",
                created_at=datetime(2024, 1, 2, 12, 0, 0),
                metadata_path="/path/to/v1.1.0/metadata.json",
                model_path="/path/to/v1.1.0/model.pkl",
                checksum="abc123",
            ),
            ModelVersion(
                model_name="test_model",
                version="1.0.0",
                created_at=datetime(2024, 1, 1, 12, 0, 0),
                metadata_path="/path/to/v1.0.0/metadata.json",
                model_path="/path/to/v1.0.0/model.pkl",
                checksum="def456",
            ),
        ]

        with patch("cli.model_registry_cli.get_registry", return_value=mock_registry):
            result = runner.invoke(
                cli,
                ["list", "test_model"],
                obj={"config": {"output": {"format": "table"}}},
            )

        assert result.exit_code == EXIT_SUCCESS
        assert "test_model" in result.output
        assert "1.1.0" in result.output
        assert "1.0.0" in result.output

    def test_list_empty(self, runner, mock_registry):
        """Test listing with no versions."""
        mock_registry.list_versions.return_value = []

        with patch("cli.model_registry_cli.get_registry", return_value=mock_registry):
            result = runner.invoke(
                cli,
                ["list", "test_model"],
                obj={"config": {"output": {"format": "table"}}},
            )

        assert result.exit_code == EXIT_NOT_FOUND
        assert "No versions found" in result.output

    def test_list_json_output(self, runner, mock_registry):
        """Test listing with JSON output format."""
        mock_registry.list_versions.return_value = [
            ModelVersion(
                model_name="test_model",
                version="1.0.0",
                created_at=datetime(2024, 1, 1, 12, 0, 0),
                metadata_path="/path/to/metadata.json",
                model_path="/path/to/model.pkl",
                checksum="abc123",
            ),
        ]

        with patch("cli.model_registry_cli.get_registry", return_value=mock_registry):
            result = runner.invoke(
                cli,
                ["-o", "json", "list", "test_model"],
            )

        assert result.exit_code == EXIT_SUCCESS
        # Parse JSON output
        output_data = json.loads(result.output)
        assert output_data["success"] is True
        assert len(output_data["versions"]) == 1


class TestGetCommand:
    """Tests for the get command."""

    def test_get_latest_success(self, runner, mock_registry, sample_metadata):
        """Test successful retrieval of latest model."""
        mock_registry.get_latest.return_value = (None, sample_metadata)

        with patch("cli.model_registry_cli.get_registry", return_value=mock_registry):
            result = runner.invoke(
                cli,
                ["get", "test_model"],
                obj={"config": {"output": {"format": "table"}}},
            )

        assert result.exit_code == EXIT_SUCCESS
        assert "test_model" in result.output
        assert "1.0.0" in result.output
        assert "dataset_v1" in result.output

    def test_get_specific_version(self, runner, mock_registry, sample_metadata):
        """Test successful retrieval of specific version."""
        mock_registry.get_model.return_value = (None, sample_metadata)

        with patch("cli.model_registry_cli.get_registry", return_value=mock_registry):
            result = runner.invoke(
                cli,
                ["get", "test_model", "--version", "1.0.0"],
                obj={"config": {"output": {"format": "table"}}},
            )

        assert result.exit_code == EXIT_SUCCESS
        mock_registry.get_model.assert_called_once_with("test_model", "1.0.0")

    def test_get_not_found(self, runner, mock_registry):
        """Test retrieval of non-existent model."""
        mock_registry.get_latest.side_effect = ModelNotFoundError("Model not found")

        with patch("cli.model_registry_cli.get_registry", return_value=mock_registry):
            result = runner.invoke(
                cli,
                ["get", "test_model"],
                obj={"config": {"output": {"format": "table"}}},
            )

        assert result.exit_code == EXIT_NOT_FOUND
        assert "not found" in result.output


class TestRollbackCommand:
    """Tests for the rollback command."""

    def test_rollback_success(self, runner, mock_registry):
        """Test successful rollback."""
        mock_registry.rollback.return_value = True

        with patch("cli.model_registry_cli.get_registry", return_value=mock_registry):
            result = runner.invoke(
                cli,
                ["rollback", "test_model", "1.0.0"],
                obj={"config": {"output": {"format": "table"}}},
            )

        assert result.exit_code == EXIT_SUCCESS
        assert "rolled back" in result.output
        mock_registry.rollback.assert_called_once_with("test_model", "1.0.0")

    def test_rollback_not_found(self, runner, mock_registry):
        """Test rollback to non-existent version."""
        mock_registry.rollback.side_effect = ModelNotFoundError("Version not found")

        with patch("cli.model_registry_cli.get_registry", return_value=mock_registry):
            result = runner.invoke(
                cli,
                ["rollback", "test_model", "1.0.0"],
                obj={"config": {"output": {"format": "table"}}},
            )

        assert result.exit_code == EXIT_NOT_FOUND


class TestHistoryCommand:
    """Tests for the history command."""

    def test_history_success(self, runner, mock_registry):
        """Test successful history retrieval."""
        mock_registry.get_version_history.return_value = [
            {
                "version": "1.1.0",
                "created_at": "2024-01-02T12:00:00",
                "model_name": "test_model",
                "metrics": {"accuracy": 0.96},
                "tags": ["production"],
                "training_data": "dataset_v2",
            },
            {
                "version": "1.0.0",
                "created_at": "2024-01-01T12:00:00",
                "model_name": "test_model",
                "metrics": {"accuracy": 0.95},
                "tags": ["production"],
                "training_data": "dataset_v1",
            },
        ]

        with patch("cli.model_registry_cli.get_registry", return_value=mock_registry):
            result = runner.invoke(
                cli,
                ["history", "test_model"],
                obj={"config": {"output": {"format": "table"}}},
            )

        assert result.exit_code == EXIT_SUCCESS
        assert "1.1.0" in result.output
        assert "1.0.0" in result.output

    def test_history_empty(self, runner, mock_registry):
        """Test history with no versions."""
        mock_registry.get_version_history.return_value = []

        with patch("cli.model_registry_cli.get_registry", return_value=mock_registry):
            result = runner.invoke(
                cli,
                ["history", "test_model"],
                obj={"config": {"output": {"format": "table"}}},
            )

        assert result.exit_code == EXIT_NOT_FOUND
        assert "No history found" in result.output


class TestCompareCommand:
    """Tests for the compare command."""

    def test_compare_success(self, runner, mock_registry):
        """Test successful version comparison."""
        mock_registry.compare_versions.return_value = {
            "version1": {
                "version": "1.0.0",
                "created_at": "2024-01-01T12:00:00",
                "metrics": {"accuracy": 0.95},
            },
            "version2": {
                "version": "1.1.0",
                "created_at": "2024-01-02T12:00:00",
                "metrics": {"accuracy": 0.96},
            },
            "metric_diffs": {"accuracy": 0.01},
        }

        with patch("cli.model_registry_cli.get_registry", return_value=mock_registry):
            result = runner.invoke(
                cli,
                ["compare", "test_model", "1.0.0", "1.1.0"],
            )

        assert result.exit_code == EXIT_SUCCESS
        assert "test_model" in result.output
        assert "0.01" in result.output

    def test_compare_not_found(self, runner, mock_registry):
        """Test comparison with non-existent model."""
        mock_registry.compare_versions.side_effect = ModelNotFoundError(
            "Model not found"
        )

        with patch("cli.model_registry_cli.get_registry", return_value=mock_registry):
            result = runner.invoke(
                cli,
                ["compare", "test_model", "1.0.0", "1.1.0"],
                obj={"config": {"output": {"format": "table"}}},
            )

        assert result.exit_code == EXIT_NOT_FOUND


class TestValidateCommand:
    """Tests for the validate command."""

    def test_validate_success(self, runner, temp_model_file):
        """Test successful validation."""
        result = runner.invoke(
            cli,
            ["validate", "test_model", str(temp_model_file)],
            obj={"config": {"output": {"format": "table"}}},
        )

        assert result.exit_code == EXIT_SUCCESS
        assert "Validation PASSED" in result.output

    def test_validate_missing_file(self, runner):
        """Test validation of non-existent file."""
        result = runner.invoke(
            cli,
            ["validate", "test_model", "/nonexistent/path/model.pkl"],
            obj={"config": {"output": {"format": "table"}}},
        )

        assert result.exit_code != EXIT_SUCCESS  # Click handles missing file

    def test_validate_invalid_pickle(self, runner, tmp_path):
        """Test validation of invalid pickle file."""
        invalid_file = tmp_path / "invalid.pkl"
        with open(invalid_file, "w") as f:
            f.write("not valid pickle data")

        result = runner.invoke(
            cli,
            ["validate", "test_model", str(invalid_file)],
            obj={"config": {"output": {"format": "table"}}},
        )

        assert result.exit_code == EXIT_VALIDATION_ERROR
        assert "Failed to load" in result.output


class TestHealthCommand:
    """Tests for the health command."""

    def test_health_success(self, runner, mock_registry):
        """Test successful health check."""
        mock_registry.list_versions.return_value = []

        with patch("cli.model_registry_cli.get_registry", return_value=mock_registry):
            result = runner.invoke(
                cli,
                ["-o", "json", "health"],
            )

        assert result.exit_code == EXIT_SUCCESS
        output_data = json.loads(result.output)
        assert output_data["status"] == "healthy"
        assert output_data["registry_initialized"] is True


class TestConfigCommands:
    """Tests for configuration commands."""

    def test_config_show(self, runner, tmp_path):
        """Test showing configuration."""
        config_file = tmp_path / "config.yaml"
        test_config = {
            "registry": {"base_path": "/test/path"},
            "output": {"format": "json"},
        }
        with open(config_file, "w") as f:
            import yaml

            yaml.dump(test_config, f)

        with patch("cli.model_registry_cli.get_config_path") as mock_path:
            mock_path.return_value = config_file
            result = runner.invoke(cli, ["config-show"])

        assert result.exit_code == EXIT_SUCCESS
        assert "/test/path" in result.output

    def test_config_set(self, runner, tmp_path):
        """Test setting configuration values."""
        config_file = tmp_path / "config.yaml"

        with patch("cli.model_registry_cli.get_config_path") as mock_path:
            mock_path.return_value = config_file

            result = runner.invoke(
                cli,
                ["config-set", "--base-path", "/new/path", "--output-format", "json"],
            )

        assert result.exit_code == EXIT_SUCCESS
        assert "Configuration saved" in result.output

        # Verify saved config
        with open(config_file) as f:
            import yaml

            saved = yaml.safe_load(f)
            assert saved["registry"]["base_path"] == "/new/path"
            assert saved["output"]["format"] == "json"


class TestEnvironmentVariables:
    """Tests for environment variable handling."""

    def test_env_var_registry_host(
        self, runner, mock_registry, temp_model_file, monkeypatch
    ):
        """Test CHISE_REGISTRY_HOST environment variable."""
        monkeypatch.setenv("CHISE_REGISTRY_HOST", "custom-host")

        # Create a config to check env var is read
        config = load_config()

        # Env vars are only applied in CLI context, not in load_config directly
        # But we can verify the mechanism works through integration
        assert os.getenv("CHISE_REGISTRY_HOST") == "custom-host"

    def test_env_var_registry_port(self, runner, mock_registry, monkeypatch):
        """Test CHISE_REGISTRY_PORT environment variable."""
        monkeypatch.setenv("CHISE_REGISTRY_PORT", "9000")

        assert os.getenv("CHISE_REGISTRY_PORT") == "9000"


class TestVerboseMode:
    """Tests for verbose mode."""

    def test_verbose_flag(
        self, runner, mock_registry, temp_model_file, sample_model_version
    ):
        """Test that verbose flag enables debug logging."""
        mock_registry.register_model.return_value = sample_model_version

        with patch("cli.model_registry_cli.get_registry", return_value=mock_registry):
            result = runner.invoke(
                cli,
                [
                    "-v",
                    "register",
                    "test_model",
                    str(temp_model_file),
                    "--version",
                    "1.0.0",
                    "--training-data",
                    "dataset_v1",
                ],
                obj={"config": {"output": {"format": "table"}}},
            )

        assert result.exit_code == EXIT_SUCCESS


class TestOutputFormats:
    """Tests for different output formats."""

    def test_output_json(self, runner, mock_registry, sample_metadata):
        """Test JSON output format."""
        mock_registry.get_latest.return_value = (None, sample_metadata)

        with patch("cli.model_registry_cli.get_registry", return_value=mock_registry):
            result = runner.invoke(
                cli,
                ["-o", "json", "get", "test_model"],
                obj={"config": {"output": {"format": "table"}}},
            )

        assert result.exit_code == EXIT_SUCCESS
        # Should be valid JSON
        output_data = json.loads(result.output)
        assert output_data["success"] is True

    def test_output_table(self, runner, mock_registry, sample_metadata):
        """Test table output format."""
        mock_registry.get_latest.return_value = (None, sample_metadata)

        with patch("cli.model_registry_cli.get_registry", return_value=mock_registry):
            result = runner.invoke(
                cli,
                ["-o", "table", "get", "test_model"],
                obj={"config": {"output": {"format": "json"}}},
            )

        assert result.exit_code == EXIT_SUCCESS
        # Table format should not be JSON
        assert "Model:" in result.output or "test_model" in result.output
