"""Model Registry CLI for ChiseAI.

Provides command-line interface for model versioning, storage, and retrieval.

Commands:
    chise-model register <name> <path> - Register model
    chise-model list <name> - List versions
    chise-model get <name> [version] - Get model info
    chise-model rollback <name> <version> - Rollback
    chise-model history <name> - Show history
    chise-model compare <name> <v1> <v2> - Compare versions
    chise-model validate <name> <path> - Validate model before registration
    chise-model health - Check registry health

Configuration:
    CLI reads configuration from ~/.chise/config.yaml
    Environment variables override config file values.
    Environment variables: CHISE_REGISTRY_HOST, CHISE_REGISTRY_PORT

Exit Codes:
    0 - Success
    1 - General error
    2 - Model not found
    3 - Version conflict
    4 - Validation error
    5 - Connection error

Example:
    chise-model register my_model ./model.pkl --version 1.0.0
    chise-model list my_model
    chise-model get my_model --version latest
"""

from __future__ import annotations

import json
import logging
import os
import pickle
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import click
import yaml

from ml.models.model_registry import ModelRegistry, ModelRegistryFactory
from ml.models.model_storage import (
    ModelMetadata,
    ModelNotFoundError,
    ModelValidationError,
    ModelVersionExistsError,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("chise-model")

# Default configuration
DEFAULT_CONFIG = {
    "registry": {
        "host": "localhost",
        "port": 8000,
        "base_path": "models",
    },
    "output": {
        "format": "table",  # table, json
    },
}

# Exit codes
EXIT_SUCCESS = 0
EXIT_ERROR = 1
EXIT_NOT_FOUND = 2
EXIT_VERSION_CONFLICT = 3
EXIT_VALIDATION_ERROR = 4
EXIT_CONNECTION_ERROR = 5


def get_config_path() -> Path:
    """Get the path to the configuration file."""
    home = Path.home()
    config_dir = home / ".chise"
    config_dir.mkdir(exist_ok=True)
    return config_dir / "config.yaml"


def load_config() -> dict[str, Any]:
    """Load configuration from file."""
    config_path = get_config_path()
    if config_path.exists():
        try:
            with open(config_path) as f:
                return yaml.safe_load(f) or DEFAULT_CONFIG
        except Exception as e:
            logger.warning(f"Failed to load config: {e}. Using defaults.")
    return DEFAULT_CONFIG.copy()


def save_config(config: dict[str, Any]) -> None:
    """Save configuration to file."""
    config_path = get_config_path()
    try:
        with open(config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False)
    except Exception as e:
        logger.error(f"Failed to save config: {e}")


def get_registry(ctx: click.Context) -> ModelRegistry:
    """Get or create model registry instance.

    Args:
        ctx: Click context

    Returns:
        ModelRegistry instance
    """
    if "registry" not in ctx.obj:
        config = ctx.obj.get("config", DEFAULT_CONFIG)
        base_path = config.get("registry", {}).get("base_path", "models")

        # Use local filesystem registry by default
        registry = ModelRegistryFactory.create_filesystem_registry(
            base_path=base_path,
            enable_cache=True,
        )
        ctx.obj["registry"] = registry

    return ctx.obj["registry"]


def format_output(
    data: Any, format_type: str, table_headers: list[str] | None = None
) -> str:
    """Format output for display.

    Args:
        data: Data to format
        format_type: Output format (table, json)
        table_headers: Headers for table format

    Returns:
        Formatted string
    """
    if format_type == "json":
        return json.dumps(data, indent=2, default=str)

    # Table format
    if isinstance(data, list):
        if not data:
            return "No data found."

        if isinstance(data[0], dict):
            # List of dictionaries
            headers = table_headers or list(data[0].keys())
            lines = []
            lines.append(" | ".join(headers))
            lines.append("-" * (sum(len(h) for h in headers) + 3 * (len(headers) - 1)))
            for item in data:
                row = [str(item.get(h, "")) for h in headers]
                lines.append(" | ".join(row))
            return "\n".join(lines)
        else:
            # List of simple values
            return "\n".join(str(item) for item in data)

    elif isinstance(data, dict):
        # Dictionary
        max_key_len = max(len(str(k)) for k in data.keys()) if data else 0
        lines = []
        for key, value in data.items():
            lines.append(f"{str(key):{max_key_len}} : {value}")
        return "\n".join(lines)

    else:
        return str(data)


# CLI Group
@click.group()
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True),
    help="Path to configuration file",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose output",
)
@click.option(
    "--output",
    "-o",
    type=click.Choice(["table", "json"], case_sensitive=False),
    default=None,
    help="Output format",
)
@click.option(
    "--base-path",
    "-b",
    type=click.Path(),
    help="Base path for model storage",
)
@click.pass_context
def cli(
    ctx: click.Context,
    config: str | None,
    verbose: bool,
    output: str | None,
    base_path: str | None,
) -> None:
    """ChiseAI Model Registry CLI.

    Manage ML models with versioning, storage, and retrieval.

    Configuration is read from ~/.chise/config.yaml by default.
    Use --config to specify an alternative configuration file.
    """
    # Ensure context is a dict
    ctx.ensure_object(dict)

    # Load configuration
    if config:
        with open(config) as f:
            ctx.obj["config"] = yaml.safe_load(f)
    else:
        ctx.obj["config"] = load_config()

    # Apply environment variable overrides
    if os.getenv("CHISE_REGISTRY_HOST"):
        ctx.obj["config"]["registry"]["host"] = os.getenv("CHISE_REGISTRY_HOST")
    if os.getenv("CHISE_REGISTRY_PORT"):
        ctx.obj["config"]["registry"]["port"] = int(os.getenv("CHISE_REGISTRY_PORT"))

    # Apply CLI option overrides
    if output:
        ctx.obj["config"]["output"]["format"] = output
    if base_path:
        ctx.obj["config"]["registry"]["base_path"] = base_path

    # Set logging level
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        ctx.obj["verbose"] = True


@cli.command()
@click.argument("name")
@click.argument("path", type=click.Path(exists=True))
@click.option(
    "--version",
    required=True,
    help="Model version (e.g., 1.0.0)",
)
@click.option(
    "--training-data",
    required=True,
    help="Reference to training dataset",
)
@click.option(
    "--hyperparameters",
    "-p",
    type=str,
    default="{}",
    help="Hyperparameters as JSON string",
)
@click.option(
    "--metrics",
    "-m",
    type=str,
    default="{}",
    help="Metrics as JSON string",
)
@click.option(
    "--tags",
    "-t",
    type=str,
    default="[]",
    help="Tags as JSON array string",
)
@click.pass_context
def register(
    ctx: click.Context,
    name: str,
    path: str,
    version: str,
    training_data: str,
    hyperparameters: str,
    metrics: str,
    tags: str,
) -> None:
    """Register a new model version.

    NAME: Model name
    PATH: Path to model file (pickle/joblib format)

    Example:
        chise-model register my_model ./model.pkl --version 1.0.0 --training-data dataset_v1
    """
    try:
        registry = get_registry(ctx)

        # Parse JSON parameters
        try:
            hyperparams_dict = json.loads(hyperparameters)
            metrics_dict = json.loads(metrics)
            tags_list = json.loads(tags)
        except json.JSONDecodeError as e:
            click.echo(f"Error: Invalid JSON parameter: {e}", err=True)
            sys.exit(EXIT_VALIDATION_ERROR)

        # Load model file
        model_path = Path(path)
        try:
            with open(model_path, "rb") as f:
                model = pickle.load(f)
        except Exception as e:
            click.echo(f"Error: Failed to load model file: {e}", err=True)
            sys.exit(EXIT_VALIDATION_ERROR)

        # Create metadata
        metadata = ModelMetadata(
            model_name=name,
            version=version,
            created_at=datetime.now(UTC),
            training_data=training_data,
            hyperparameters=hyperparams_dict,
            metrics=metrics_dict,
            tags=tags_list,
        )

        # Register model
        model_version = registry.register_model(model, metadata)

        output_format = (
            ctx.obj.get("config", {}).get("output", {}).get("format", "table")
        )
        result = {
            "success": True,
            "message": f"Model {name}@{version} registered successfully",
            "model": {
                "version": model_version.version,
                "created_at": model_version.created_at.isoformat(),
                "model_name": model_version.model_name,
                "checksum": model_version.checksum,
            },
        }

        click.echo(format_output(result, output_format))

    except ModelVersionExistsError as e:
        click.echo(f"Error: Version already exists - {e}", err=True)
        sys.exit(EXIT_VERSION_CONFLICT)
    except ModelValidationError as e:
        click.echo(f"Error: Validation failed - {e}", err=True)
        sys.exit(EXIT_VALIDATION_ERROR)
    except Exception as e:
        click.echo(f"Error: Failed to register model: {e}", err=True)
        sys.exit(EXIT_ERROR)


@cli.command()
@click.argument("name")
@click.option(
    "--limit",
    "-l",
    type=int,
    default=100,
    help="Maximum number of versions to display",
)
@click.pass_context
def list_versions(ctx: click.Context, name: str, limit: int) -> None:
    """List all versions of a model.

    NAME: Model name

    Example:
        chise-model list my_model
    """
    try:
        registry = get_registry(ctx)
        versions = registry.list_versions(name)

        if not versions:
            click.echo(f"No versions found for model: {name}")
            sys.exit(EXIT_NOT_FOUND)

        # Limit versions
        versions = versions[:limit]

        output_format = (
            ctx.obj.get("config", {}).get("output", {}).get("format", "table")
        )

        if output_format == "json":
            result = {
                "success": True,
                "model_name": name,
                "versions": [
                    {
                        "version": v.version,
                        "created_at": v.created_at.isoformat(),
                        "checksum": v.checksum,
                    }
                    for v in versions
                ],
                "count": len(versions),
            }
            click.echo(format_output(result, output_format))
        else:
            # Table format
            click.echo(f"\nModel: {name}")
            click.echo("-" * 60)
            click.echo(f"{'Version':<15} {'Created At':<25} {'Checksum'}")
            click.echo("-" * 60)
            for v in versions:
                created = v.created_at.strftime("%Y-%m-%d %H:%M:%S")
                checksum = v.checksum[:16] + "..." if v.checksum else "N/A"
                click.echo(f"{v.version:<15} {created:<25} {checksum}")
            click.echo("-" * 60)
            click.echo(f"Total: {len(versions)} version(s)\n")

    except Exception as e:
        click.echo(f"Error: Failed to list versions: {e}", err=True)
        sys.exit(EXIT_ERROR)


# Alias for list command
cli.add_command(list_versions, name="list")


@cli.command()
@click.argument("name")
@click.option(
    "--version",
    "-v",
    default="latest",
    help="Model version (default: latest)",
)
@click.pass_context
def get(ctx: click.Context, name: str, version: str) -> None:
    """Get model information.

    NAME: Model name

    Example:
        chise-model get my_model
        chise-model get my_model --version 1.0.0
    """
    try:
        registry = get_registry(ctx)

        if version == "latest":
            _, metadata = registry.get_latest(name)
        else:
            _, metadata = registry.get_model(name, version)

        output_format = (
            ctx.obj.get("config", {}).get("output", {}).get("format", "table")
        )

        if output_format == "json":
            result = {
                "success": True,
                "model_name": name,
                "version": metadata.version,
                "metadata": {
                    "model_name": metadata.model_name,
                    "version": metadata.version,
                    "created_at": metadata.created_at.isoformat(),
                    "training_data": metadata.training_data,
                    "hyperparameters": metadata.hyperparameters,
                    "metrics": metadata.metrics,
                    "tags": metadata.tags,
                    "checksum": metadata.checksum,
                },
            }
            click.echo(format_output(result, output_format))
        else:
            # Table format
            click.echo(f"\nModel: {metadata.model_name}")
            click.echo(f"Version: {metadata.version}")
            click.echo(f"Created: {metadata.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
            click.echo(f"Training Data: {metadata.training_data}")
            if metadata.checksum:
                click.echo(f"Checksum: {metadata.checksum[:32]}...")
            click.echo("\nHyperparameters:")
            for key, value in metadata.hyperparameters.items():
                click.echo(f"  {key}: {value}")
            click.echo("\nMetrics:")
            for key, value in metadata.metrics.items():
                click.echo(f"  {key}: {value}")
            if metadata.tags:
                click.echo(f"\nTags: {', '.join(metadata.tags)}")
            click.echo()

    except ModelNotFoundError:
        click.echo(f"Error: Model '{name}' version '{version}' not found", err=True)
        sys.exit(EXIT_NOT_FOUND)
    except Exception as e:
        click.echo(f"Error: Failed to get model: {e}", err=True)
        sys.exit(EXIT_ERROR)


@cli.command()
@click.argument("name")
@click.argument("version")
@click.pass_context
def rollback(ctx: click.Context, name: str, version: str) -> None:
    """Rollback to a previous model version.

    NAME: Model name
    VERSION: Version to rollback to

    Example:
        chise-model rollback my_model 1.0.0
    """
    try:
        registry = get_registry(ctx)

        success = registry.rollback(name, version)

        output_format = (
            ctx.obj.get("config", {}).get("output", {}).get("format", "table")
        )

        if success:
            result = {
                "success": True,
                "message": f"Successfully rolled back {name} to version {version}",
                "model_name": name,
                "rolled_back_to": version,
            }
            click.echo(format_output(result, output_format))
        else:
            click.echo("Error: Rollback failed", err=True)
            sys.exit(EXIT_ERROR)

    except ModelNotFoundError:
        click.echo(f"Error: Model '{name}' version '{version}' not found", err=True)
        sys.exit(EXIT_NOT_FOUND)
    except Exception as e:
        click.echo(f"Error: Failed to rollback: {e}", err=True)
        sys.exit(EXIT_ERROR)


@cli.command()
@click.argument("name")
@click.pass_context
def history(ctx: click.Context, name: str) -> None:
    """Show version history for a model.

    NAME: Model name

    Example:
        chise-model history my_model
    """
    try:
        registry = get_registry(ctx)
        history_data = registry.get_version_history(name)

        if not history_data:
            click.echo(f"No history found for model: {name}")
            sys.exit(EXIT_NOT_FOUND)

        output_format = (
            ctx.obj.get("config", {}).get("output", {}).get("format", "table")
        )

        if output_format == "json":
            result = {
                "success": True,
                "model_name": name,
                "history": history_data,
            }
            click.echo(format_output(result, output_format))
        else:
            # Table format
            click.echo(f"\nVersion History for: {name}")
            click.echo("-" * 80)
            for entry in history_data:
                click.echo(f"\nVersion: {entry['version']}")
                click.echo(f"Created: {entry['created_at']}")
                click.echo(f"Training Data: {entry['training_data']}")
                if entry.get("metrics"):
                    click.echo("Metrics:")
                    for key, value in entry["metrics"].items():
                        click.echo(f"  {key}: {value}")
                if entry.get("tags"):
                    click.echo(f"Tags: {', '.join(entry['tags'])}")
                click.echo("-" * 80)

    except Exception as e:
        click.echo(f"Error: Failed to get history: {e}", err=True)
        sys.exit(EXIT_ERROR)


@cli.command()
@click.argument("name")
@click.argument("version1")
@click.argument("version2")
@click.pass_context
def compare(ctx: click.Context, name: str, version1: str, version2: str) -> None:
    """Compare two model versions.

    NAME: Model name
    VERSION1: First version to compare
    VERSION2: Second version to compare

    Example:
        chise-model compare my_model 1.0.0 1.1.0
    """
    try:
        registry = get_registry(ctx)
        comparison = registry.compare_versions(name, version1, version2)

        output_format = (
            ctx.obj.get("config", {}).get("output", {}).get("format", "table")
        )

        if output_format == "json":
            result = {
                "success": True,
                "model_name": name,
                "version1": comparison["version1"],
                "version2": comparison["version2"],
                "metric_diffs": comparison["metric_diffs"],
            }
            click.echo(format_output(result, output_format))
        else:
            # Table format
            click.echo(f"\nComparing {name}@{version1} vs {name}@{version2}")
            click.echo("-" * 60)

            v1_info = comparison["version1"]
            v2_info = comparison["version2"]

            click.echo(f"\nVersion {version1}:")
            click.echo(f"  Created: {v1_info['created_at']}")
            if v1_info.get("metrics"):
                click.echo("  Metrics:")
                for key, value in v1_info["metrics"].items():
                    click.echo(f"    {key}: {value}")

            click.echo(f"\nVersion {version2}:")
            click.echo(f"  Created: {v2_info['created_at']}")
            if v2_info.get("metrics"):
                click.echo("  Metrics:")
                for key, value in v2_info["metrics"].items():
                    click.echo(f"    {key}: {value}")

            click.echo("\nMetric Differences (v2 - v1):")
            for key, diff in comparison["metric_diffs"].items():
                sign = "+" if diff > 0 else ""
                click.echo(f"  {key}: {sign}{diff:.6f}")
            click.echo()

    except ModelNotFoundError:
        click.echo("Error: Model or version not found", err=True)
        sys.exit(EXIT_NOT_FOUND)
    except Exception as e:
        click.echo(f"Error: Failed to compare versions: {e}", err=True)
        sys.exit(EXIT_ERROR)


@cli.command()
@click.argument("name")
@click.argument("path", type=click.Path(exists=True))
@click.option(
    "--min-accuracy",
    type=float,
    help="Minimum required accuracy",
)
@click.option(
    "--required-attributes",
    type=str,
    help="Required model attributes (comma-separated)",
)
@click.pass_context
def validate(
    ctx: click.Context,
    name: str,
    path: str,
    min_accuracy: float | None,
    required_attributes: str | None,
) -> None:
    """Validate a model before registration.

    NAME: Model name
    PATH: Path to model file

    Example:
        chise-model validate my_model ./model.pkl --min-accuracy 0.95
    """
    try:
        # Load model file
        model_path = Path(path)
        try:
            with open(model_path, "rb") as f:
                model = pickle.load(f)
        except Exception as e:
            click.echo(f"Error: Failed to load model file: {e}", err=True)
            sys.exit(EXIT_VALIDATION_ERROR)

        # Create temporary metadata for validation
        metadata = ModelMetadata(
            model_name=name,
            version="0.0.0",  # Dummy version for validation
            created_at=datetime.now(UTC),
            training_data="validation",
            hyperparameters={},
            metrics={"accuracy": min_accuracy} if min_accuracy else {},
            tags=["validation"],
        )

        # Run validation
        errors = []

        # Check required attributes
        if required_attributes:
            attrs = [a.strip() for a in required_attributes.split(",")]
            for attr in attrs:
                if not hasattr(model, attr):
                    errors.append(f"Missing required attribute: {attr}")

        # Check model name
        if not name:
            errors.append("Model name cannot be empty")

        # Output results
        if errors:
            click.echo("Validation FAILED:", err=True)
            for error in errors:
                click.echo(f"  - {error}", err=True)
            sys.exit(EXIT_VALIDATION_ERROR)
        else:
            click.echo("Validation PASSED")
            click.echo(f"Model file: {path}")
            click.echo(f"Model type: {type(model).__name__}")
            if hasattr(model, "__module__"):
                click.echo(f"Module: {model.__module__}")

    except Exception as e:
        click.echo(f"Error: Validation failed: {e}", err=True)
        sys.exit(EXIT_ERROR)


@cli.command()
@click.pass_context
def health(ctx: click.Context) -> None:
    """Check registry health status.

    Example:
        chise-model health
    """
    try:
        registry = get_registry(ctx)

        # Check if registry is accessible
        # Just try to list a dummy model to verify connectivity
        try:
            _ = registry.list_versions("__health_check__")
            healthy = True
        except Exception:
            healthy = True  # Empty result is fine, exception means error

        output_format = (
            ctx.obj.get("config", {}).get("output", {}).get("format", "table")
        )

        result = {
            "status": "healthy" if healthy else "unhealthy",
            "registry_initialized": registry is not None,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        click.echo(format_output(result, output_format))

        if not healthy:
            sys.exit(EXIT_CONNECTION_ERROR)

    except Exception as e:
        click.echo(f"Error: Health check failed: {e}", err=True)
        sys.exit(EXIT_ERROR)


@cli.command()
def config_show() -> None:
    """Show current configuration.

    Example:
        chise-model config-show
    """
    config = load_config()
    click.echo(format_output(config, "table"))


@cli.command()
@click.option(
    "--base-path",
    type=click.Path(),
    help="Base path for model storage",
)
@click.option(
    "--output-format",
    type=click.Choice(["table", "json"]),
    help="Default output format",
)
def config_set(base_path: str | None, output_format: str | None) -> None:
    """Set configuration values.

    Example:
        chise-model config-set --base-path /path/to/models
        chise-model config-set --output-format json
    """
    config = load_config()

    if base_path:
        config["registry"]["base_path"] = base_path
        click.echo(f"Set base_path to: {base_path}")

    if output_format:
        config["output"]["format"] = output_format
        click.echo(f"Set output_format to: {output_format}")

    save_config(config)
    click.echo("Configuration saved.")


# Entry point
def main() -> None:
    """CLI entry point."""
    cli()


if __name__ == "__main__":
    main()
