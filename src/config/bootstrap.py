#!/usr/bin/env python3
"""Environment bootstrap for standalone scripts.

Usage:
    from config.bootstrap import bootstrap
    bootstrap()  # Call at script entrypoint

    # Or as CLI:
    python -m config.bootstrap --check
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Track loaded files and provider status
_BOOTSTRAP_STATE: dict[str, Any] = {
    "loaded_files": [],
    "providers": {},
}


def _find_env_files() -> list[Path]:
    """Find potential .env files in standard locations.

    Returns:
        List of paths to potential env files (deduplicated)
    """
    env_files = []
    seen = set()
    search_paths = [
        Path.cwd() / ".env",
        Path.cwd().parent / ".env",
        Path(__file__).parent.parent.parent / ".env",
        Path.home() / ".chiseai" / ".env",
    ]

    for path in search_paths:
        resolved = path.resolve()
        if resolved.exists() and resolved.is_file() and resolved not in seen:
            env_files.append(resolved)
            seen.add(resolved)

    return env_files


def _load_env_file(filepath: Path) -> bool:
    """Load environment variables from a .env file.

    Args:
        filepath: Path to the .env file

    Returns:
        True if file was loaded successfully
    """
    try:
        with open(filepath, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                # Skip comments and empty lines
                if not line or line.startswith("#"):
                    continue
                # Parse KEY=VALUE
                if "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip("\"'")
                    # Only set if not already in environment
                    if key and key not in os.environ:
                        os.environ[key] = value
        return True
    except Exception as e:
        logger.warning(f"Failed to load {filepath}: {e}")
        return False


def _check_provider(name: str, env_vars: list[str]) -> dict[str, Any]:
    """Check if a provider is available based on environment variables.

    Args:
        name: Provider name (e.g., "KIMI", "ZAI")
        env_vars: List of environment variable names to check

    Returns:
        Dictionary with provider status information
    """
    available = False
    source = None
    missing = []

    for var in env_vars:
        value = os.getenv(var)
        if value:
            available = True
            if source is None:
                source = var
            break
        else:
            missing.append(var)

    return {
        "name": name,
        "available": available,
        "source": source,
        "missing": missing,
    }


def _check_all_providers() -> dict[str, dict[str, Any]]:
    """Check availability of all configured providers.

    Returns:
        Dictionary mapping provider names to their status
    """
    providers = {
        "KIMI": ["KIMI_API_KEY", "KIMI_API_KEY_PRIMARY"],
        "ZAI": ["ZAI_API_KEY", "ZAI_API_KEY_PRIMARY"],
        "ZHIPU": ["ZHIPU_API_KEY", "ZAI_API_KEY"],  # ZAI key can proxy for ZHIPU
        "MINIMAX": ["MINIMAX_API_KEY"],
    }

    results = {}
    for name, env_vars in providers.items():
        # Check if provider is explicitly disabled
        enabled_var = f"{name}_ENABLED"
        # MINIMAX defaults to disabled, others default to enabled
        default_value = "false" if name == "MINIMAX" else "true"
        is_enabled = os.getenv(enabled_var, default_value).lower() in (
            "true",
            "1",
            "yes",
            "on",
        )

        status = _check_provider(name, env_vars)
        status["explicitly_disabled"] = not is_enabled

        # If explicitly disabled, mark as disabled even if keys exist
        if not is_enabled:
            status["available"] = False

        results[name] = status

    return results


def bootstrap(
    load_env: bool = True,
    env_file: Path | None = None,
    verbose: bool = False,
) -> dict[str, Any]:
    """Bootstrap the environment for standalone scripts.

    This function should be called at the entrypoint of standalone scripts
    to ensure environment variables are loaded and providers are available.

    Args:
        load_env: Whether to load .env files
        env_file: Specific env file to load (optional)
        verbose: Whether to log detailed information

    Returns:
        Dictionary with bootstrap state including:
        - loaded_files: List of env files that were loaded
        - providers: Dictionary of provider availability status
    """
    global _BOOTSTRAP_STATE

    if verbose:
        logger.setLevel(logging.DEBUG)

    loaded_files = []

    # Load environment files
    if load_env:
        if env_file:
            # Load specific file
            if env_file.exists():
                if _load_env_file(env_file):
                    loaded_files.append(env_file.resolve())
                    if verbose:
                        logger.info(f"Loaded env file: {env_file}")
            else:
                logger.warning(f"Specified env file not found: {env_file}")
        else:
            # Auto-discover and load env files
            for env_path in _find_env_files():
                if _load_env_file(env_path):
                    loaded_files.append(env_path)
                    if verbose:
                        logger.info(f"Loaded env file: {env_path}")

    # Check provider availability
    providers = _check_all_providers()

    _BOOTSTRAP_STATE = {
        "loaded_files": loaded_files,
        "providers": providers,
    }

    return _BOOTSTRAP_STATE


def get_bootstrap_state() -> dict[str, Any]:
    """Get the current bootstrap state.

    Returns:
        Dictionary with bootstrap state
    """
    return _BOOTSTRAP_STATE


def format_provider_status(status: dict[str, Any]) -> str:
    """Format provider status for display (without secrets).

    Args:
        status: Provider status dictionary from _check_provider

    Returns:
        Human-readable status string
    """
    name = status["name"]
    available = status["available"]
    source = status.get("source")
    missing = status.get("missing", [])
    explicitly_disabled = status.get("explicitly_disabled", False)

    if explicitly_disabled:
        return f"disabled ({name}_ENABLED != true)"

    if available:
        if source:
            return f"available (via {source})"
        return "available"

    # Not available
    if missing:
        return f"not available ({', '.join(missing)} not set)"
    return "not available"


def check_environment(required_vars: list[str] | None = None) -> dict[str, Any]:
    """Check that required environment variables are set.

    Args:
        required_vars: List of required environment variable names.
                      If None, uses default critical vars.

    Returns:
        Dictionary with check results:
        - ok: bool - True if all required vars are set
        - missing: list - List of missing variable names
        - present: list - List of present variable names
        - warnings: list - List of warning messages

    Raises:
        EnvironmentError: If required variables are missing and raise_on_missing=True
    """
    if required_vars is None:
        # Default critical variables for ChiseAI
        required_vars = [
            "REDIS_HOST",
            "DB_URL",
        ]

    result = {
        "ok": True,
        "missing": [],
        "present": [],
        "warnings": [],
    }

    for var in required_vars:
        value = os.getenv(var)
        if value:
            result["present"].append(var)
            # Check for placeholder values
            if value in ("placeholder", "changeme", "your_value_here", "xxx"):
                result["warnings"].append(f"{var} appears to have a placeholder value")
        else:
            result["missing"].append(var)

    if result["missing"]:
        result["ok"] = False

    return result


def verify_chiseai_network() -> dict[str, Any]:
    """Verify Docker chiseai network exists and required containers are connected.

    Returns:
        Dictionary with verification results:
        - ok: bool - True if network exists and containers are connected
        - network_exists: bool - Whether chiseai network exists
        - containers: dict - Status of required containers
        - errors: list - List of error messages
    """
    import subprocess

    result = {
        "ok": True,
        "network_exists": False,
        "containers": {},
        "errors": [],
    }

    # Check if chiseai network exists
    try:
        proc = subprocess.run(  # nosec B607
            ["docker", "network", "inspect", "chiseai"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        result["network_exists"] = proc.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        result["errors"].append(f"Could not check Docker network: {e}")
        result["ok"] = False
        return result

    if not result["network_exists"]:
        result["errors"].append("chiseai network does not exist")
        result["ok"] = False
        return result

    # Check for required containers on the network
    required_containers = [
        "chiseai-redis",
        "chiseai-postgres",
    ]

    try:
        # Get list of containers on chiseai network
        proc = subprocess.run(  # nosec B607
            [
                "docker",
                "network",
                "inspect",
                "chiseai",
                "--format",
                "{{range .Containers}}{{.Name}} {{end}}",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        connected = set(proc.stdout.strip().split()) if proc.returncode == 0 else set()

        for container in required_containers:
            result["containers"][container] = container in connected
            if not result["containers"][container]:
                result["errors"].append(
                    f"{container} is not connected to chiseai network"
                )
                result["ok"] = False

    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        result["errors"].append(f"Could not check container connectivity: {e}")
        result["ok"] = False

    return result


def check_docker_connectivity() -> dict[str, Any]:
    """Check Docker daemon connectivity and basic functionality.

    Returns:
        Dictionary with check results:
        - ok: bool - True if Docker is accessible
        - daemon_accessible: bool - Whether Docker daemon is accessible
        - version: str - Docker version (if available)
        - errors: list - List of error messages
    """
    import subprocess

    result = {
        "ok": False,
        "daemon_accessible": False,
        "version": None,
        "errors": [],
    }

    try:
        # Check Docker version
        proc = subprocess.run(  # nosec B607
            ["docker", "version", "--format", "{{.Server.Version}}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode == 0:
            result["daemon_accessible"] = True
            result["version"] = proc.stdout.strip()
            result["ok"] = True
        else:
            result["errors"].append("Docker daemon not accessible")
    except FileNotFoundError:
        result["errors"].append("Docker command not found - is Docker installed?")
    except subprocess.TimeoutExpired:
        result["errors"].append("Docker command timed out")
    except Exception as e:
        result["errors"].append(f"Unexpected error checking Docker: {e}")

    return result


def print_diagnostics() -> int:
    """Print diagnostic output and return exit code.

    Returns:
        Exit code: 0 if at least one provider available, 1 otherwise, 2 on error
    """
    try:
        state = get_bootstrap_state()

        # If bootstrap hasn't been called yet, call it now
        if not state["loaded_files"] and not state["providers"]:
            state = bootstrap(load_env=True, verbose=False)

        print("Environment Bootstrap Diagnostic")
        print("=" * 40)

        # Print loaded files
        print("\nEnv files loaded:")
        if state["loaded_files"]:
            for f in state["loaded_files"]:
                print(f"  - {f}")
        else:
            print("  (none)")

        # Print provider availability
        print("\nProvider Availability:")
        available_count = 0
        total_count = len(state["providers"])

        for name, status in sorted(state["providers"].items()):
            status_str = format_provider_status(status)
            print(f"  {name}: {status_str}")
            if status["available"]:
                available_count += 1

        # Print summary
        print(f"\nSummary: {available_count}/{total_count} providers available")

        # Return appropriate exit code
        if available_count > 0:
            return 0
        return 1

    except Exception as e:
        logger.error(f"Diagnostic failed: {e}")
        return 2


def main() -> int:
    """Main entry point for CLI usage.

    Returns:
        Exit code
    """
    parser = argparse.ArgumentParser(
        description="Environment bootstrap diagnostic tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python -m config.bootstrap --check
    python -m config.bootstrap --check --verbose
        """,
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Run diagnostic check and exit",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        help="Specific env file to load",
    )

    args = parser.parse_args()

    if args.check:
        # Bootstrap first, then print diagnostics
        bootstrap(load_env=True, env_file=args.env_file, verbose=args.verbose)
        return print_diagnostics()

    # Default: just run diagnostics
    return print_diagnostics()


if __name__ == "__main__":
    sys.exit(main())
