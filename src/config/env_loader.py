"""Centralized environment variable loader.

Provides consistent environment variable loading with validation
and default value support across the codebase.

For CH-KIMI-DISCORD-001: Fix KIMI env loading
For ST-ENV-001: Environment bootstrap system
For LLM-PROVIDER-FIX-001: Provider configuration defaults

================================================================================
CANONICAL LLM PROVIDER CONFIGURATION (LLM-PROVIDER-FIX-001 Phase C)
================================================================================

Provider Defaults:
  KIMI (Direct):
    - Endpoint: https://api.moonshot.cn/v1
    - Model: kimi-k2.5
    - API Key: KIMI_API_KEY
    - Env Prefix: KIMI_

  KIMI (Adapter):
    - Endpoint: http://chiseai-kimi-adapter:8002/v1
    - Model: kimi-for-coding
    - API Key: KIMI_API_KEY (shared with direct)

  Z.ai Coding:
    - Endpoint: https://api.z.ai/api/coding/paas/v4
    - Model: glm-5
    - API Key: ZAI_API_KEY
    - Env Prefix: ZAI_

  Zhipu (Open BigModel):
    - Endpoint: https://open.bigmodel.cn/api/paas/v4
    - Model: glm-4.7
    - API Key: ZHIPU_API_KEY (with ZAI_API_KEY fallback)
    - Env Prefix: ZHIPU_

Configuration Priority:
  1. Explicit environment variable (e.g., KIMI_BASE_URL)
  2. Default value from canonical configuration above
  3. Fallback to generic provider chain

Smoke Test Commands:
  See: docs/runbooks/llm-provider-smoke-tests.md
  Preflight: ./scripts/preflight/llm_provider_check.sh

================================================================================
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class EnvLoader:
    """Centralized environment variable loader.

    Provides consistent loading of environment variables with
    type conversion, validation, and default values.

    Attributes:
        prefix: Optional prefix for environment variables
        strict: If True, raises error on missing required vars
    """

    def __init__(self, prefix: str | None = None, strict: bool = False) -> None:
        """Initialize env loader.

        Args:
            prefix: Optional prefix for env vars (e.g., "KIMI_")
            strict: If True, missing required vars raise error
        """
        self.prefix = prefix
        self.strict = strict

    def _get_key(self, key: str) -> str:
        """Get full key with prefix.

        Args:
            key: Base environment variable name

        Returns:
            Full key with prefix if set
        """
        if self.prefix:
            return f"{self.prefix}{key}"
        return key

    def get(
        self,
        key: str,
        default: Any = None,
        required: bool = False,
        var_type: type = str,
    ) -> Any:
        """Get environment variable.

        Args:
            key: Environment variable name
            default: Default value if not set
            required: If True, raises error when not set
            var_type: Type to convert value to (str, int, float, bool)

        Returns:
            Environment variable value or default

        Raises:
            ValueError: If required variable is not set and strict mode
        """
        full_key = self._get_key(key)
        value = os.getenv(full_key)

        if value is None or value == "":
            if required and self.strict:
                raise ValueError(f"Required environment variable {full_key} not set")
            return default

        # Type conversion
        if var_type is bool:
            return value.lower() in ("true", "1", "yes", "on")
        elif var_type is int:
            try:
                return int(value)
            except ValueError:
                logger.warning(f"Could not convert {full_key} to int, using default")
                return default
        elif var_type is float:
            try:
                return float(value)
            except ValueError:
                logger.warning(f"Could not convert {full_key} to float, using default")
                return default

        return value

    def get_str(
        self, key: str, default: str | None = None, required: bool = False
    ) -> str | None:
        """Get string environment variable.

        Args:
            key: Environment variable name
            default: Default value if not set
            required: If True, raises error when not set

        Returns:
            String value or default
        """
        result = self.get(key, default, required, str)
        if result is None:
            return None
        return str(result)

    def get_int(
        self, key: str, default: int | None = None, required: bool = False
    ) -> int | None:
        """Get integer environment variable.

        Args:
            key: Environment variable name
            default: Default value if not set
            required: If True, raises error when not set

        Returns:
            Integer value or default
        """
        result = self.get(key, default, required, int)
        if result is None:
            return None
        return int(result)

    def get_float(
        self, key: str, default: float | None = None, required: bool = False
    ) -> float | None:
        """Get float environment variable.

        Args:
            key: Environment variable name
            default: Default value if not set
            required: If True, raises error when not set

        Returns:
            Float value or default
        """
        result = self.get(key, default, required, float)
        if result is None:
            return None
        return float(result)

    def get_bool(self, key: str, default: bool = False, required: bool = False) -> bool:
        """Get boolean environment variable.

        Args:
            key: Environment variable name
            default: Default value if not set
            required: If True, raises error when not set

        Returns:
            Boolean value or default
        """
        result = self.get(key, default, required, bool)
        if result is None:
            return default
        return bool(result)


# Global loader instances for common prefixes
kimi_loader = EnvLoader(prefix="KIMI_", strict=False)
discord_loader = EnvLoader(prefix="DISCORD_", strict=False)


def load_kimi_config() -> dict[str, Any]:
    """Load KIMI configuration from environment.

    Returns:
        Dictionary with KIMI config values
    """
    return {
        "api_key": kimi_loader.get_str("API_KEY"),
        "base_url": kimi_loader.get_str("BASE_URL", "https://api.moonshot.cn/v1"),
        "model": kimi_loader.get_str("MODEL", "kimi-k2.5"),
        "timeout": kimi_loader.get_float("TIMEOUT", 30.0),
        "max_retries": kimi_loader.get_int("MAX_RETRIES", 3),
        "retry_delay": kimi_loader.get_float("RETRY_DELAY", 1.0),
    }


def load_discord_config() -> dict[str, Any]:
    """Load Discord configuration from environment.

    Returns:
        Dictionary with Discord config values
    """
    return {
        "bot_token": discord_loader.get_str("BOT_TOKEN"),
        "webhook_url": discord_loader.get_str("WEBHOOK_URL"),
        "default_channel": discord_loader.get_str("DEFAULT_CHANNEL", "trading-signals"),
        "guild_id": discord_loader.get_str("GUILD_ID"),  # Guild restriction
    }


def load_discord_config_with_ids() -> dict[str, Any]:
    """Load Discord configuration with authoritative channel IDs.

    Gate B fix: Loads authoritative channel IDs for routing.

    Authoritative Discord Configuration:
    - Guild ID: 1413522994810327134
    - #summaries channel: 1445752426563899492
    - #trading channel: 1444447985378398459

    Environment variables:
        DISCORD_BOT_TOKEN: Bot token
        DISCORD_WEBHOOK_URL: Webhook URL
        DISCORD_DEFAULT_CHANNEL: Default channel name
        DISCORD_GUILD_ID: Guild/server ID for lock enforcement
        DISCORD_SUMMARIES_CHANNEL_ID: Channel ID for summaries (#summaries)
        DISCORD_TRADING_CHANNEL_ID: Channel ID for trading (#trading)

    Returns:
        Dictionary with Discord config values including channel IDs
    """
    return {
        "bot_token": discord_loader.get_str("BOT_TOKEN"),
        "webhook_url": discord_loader.get_str("WEBHOOK_URL"),
        "default_channel": discord_loader.get_str("DEFAULT_CHANNEL", "trading-signals"),
        "guild_id": discord_loader.get_str("GUILD_ID"),  # Guild restriction
        # Authoritative channel IDs (Gate B fix)
        "summaries_channel_id": discord_loader.get_str(
            "SUMMARIES_CHANNEL_ID", "1445752426563899492"
        ),
        "trading_channel_id": discord_loader.get_str(
            "TRADING_CHANNEL_ID", "1444447985378398459"
        ),
    }


# =============================================================================
# Environment Bootstrap System (ST-ENV-001)
# =============================================================================


def _load_dotenv_file(env_path: Path, override: bool = False) -> bool:
    """Load environment variables from a .env file.

    Supports both python-dotenv (if available) and manual fallback parsing.

    Args:
        env_path: Path to the .env file
        override: Whether to override existing environment variables

    Returns:
        True if file was loaded successfully, False otherwise
    """
    if not env_path.exists():
        return False

    try:
        # Try python-dotenv first
        from dotenv import load_dotenv

        load_dotenv(dotenv_path=env_path, override=override)
        return True
    except ImportError:
        # Fall back to manual parsing
        return _manual_load_dotenv(env_path, override)


def _manual_load_dotenv(env_path: Path, override: bool = False) -> bool:
    """Manually parse .env file if python-dotenv is not available.

    Args:
        env_path: Path to the .env file
        override: Whether to override existing environment variables

    Returns:
        True if file was loaded successfully
    """
    try:
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip().strip("\"'")
                    if override or key not in os.environ:
                        os.environ[key] = value
        return True
    except Exception as e:
        logger.warning(f"Failed to manually load {env_path}: {e}")
        return False


def bootstrap_environment(
    env_file_path: str | None = None, override: bool = False
) -> dict[str, Any]:
    """Bootstrap environment with proper variable precedence.

    Loads environment variables with the following precedence:
    1. Existing process environment variables (highest priority - never override)
    2. Explicit env file path if provided
    3. Default .env file in repo root
    4. Default .env file in current working directory

    Args:
        env_file_path: Optional explicit path to .env file
        override: Whether to override existing env vars (use with caution)

    Returns:
        Dictionary with bootstrap summary:
        - loaded_files: List of files that were loaded
        - env_file_path: The explicit path provided (if any)
        - override: Whether override mode was used

    Note:
        Never logs or exposes actual environment variable values.
    """
    loaded_files: list[str] = []
    repo_root = Path(__file__).parent.parent.parent

    # 1. Explicit env file path (highest priority after process env)
    if env_file_path:
        explicit_path = Path(env_file_path)
        if _load_dotenv_file(explicit_path, override=override):
            loaded_files.append(str(explicit_path.resolve()))
            logger.info(f"Loaded environment from explicit file: {explicit_path}")

    # 2. Default .env in repo root
    repo_env = repo_root / ".env"
    if (
        repo_env.exists()
        and str(repo_env.resolve()) not in loaded_files
        and _load_dotenv_file(repo_env, override=override)
    ):
        loaded_files.append(str(repo_env.resolve()))
        logger.info(f"Loaded environment from repo root: {repo_env}")

    # 3. Default .env in current working directory
    cwd_env = Path.cwd() / ".env"
    if (
        cwd_env.exists()
        and str(cwd_env.resolve()) not in loaded_files
        and str(cwd_env.resolve()) != str(repo_env.resolve())
        and _load_dotenv_file(cwd_env, override=override)
    ):
        loaded_files.append(str(cwd_env.resolve()))
        logger.info(f"Loaded environment from current directory: {cwd_env}")

    summary = {
        "loaded_files": loaded_files,
        "env_file_path": env_file_path,
        "override": override,
    }

    logger.info(f"Environment bootstrap complete. Loaded {len(loaded_files)} file(s)")
    return summary


# =============================================================================
# Provider Discovery Functions (ST-ENV-001)
# =============================================================================


def discover_kimi_config() -> dict[str, Any]:
    """Discover KIMI provider configuration from environment.

    Checks for KIMI_API_KEY and KIMI_ENABLED environment variables.

    Returns:
        Dictionary with provider configuration:
        - enabled: Whether provider is enabled
        - api_key_present: Whether API key is present (not the value)
        - base_url: Base URL for API calls
        - model: Model identifier

    Note:
        Never includes actual API key values in output.
    """
    api_key = os.environ.get("KIMI_API_KEY", "").strip()
    enabled_str = os.environ.get("KIMI_ENABLED", "true").lower()
    enabled = enabled_str in ("true", "1", "yes", "on")

    return {
        "enabled": enabled and bool(api_key),
        "api_key_present": bool(api_key),
        "base_url": os.environ.get("KIMI_BASE_URL", "https://api.moonshot.cn/v1"),
        "model": os.environ.get("KIMI_MODEL", "kimi-k2.5"),
    }


def discover_zai_config() -> dict[str, Any]:
    """Discover Z.ai (Zhipu) provider configuration from environment.

    Checks for ZAI_API_KEY environment variable.

    Returns:
        Dictionary with provider configuration:
        - enabled: Whether provider is enabled (key present)
        - api_key_present: Whether API key is present (not the value)
        - base_url: Base URL for API calls

    Note:
        Never includes actual API key values in output.
    """
    api_key = os.environ.get("ZAI_API_KEY", "").strip()

    return {
        "enabled": bool(api_key),
        "api_key_present": bool(api_key),
        "base_url": os.environ.get(
            "ZAI_BASE_URL", "https://api.z.ai/api/coding/paas/v4"
        ),
    }


def discover_zhipu_config() -> dict[str, Any]:
    """Discover Zhipu AI provider configuration from environment.

    Checks for ZHIPU_API_KEY, with fallback to ZAI_API_KEY.

    Returns:
        Dictionary with provider configuration:
        - enabled: Whether provider is enabled (key present)
        - api_key_present: Whether API key is present (not the value)
        - base_url: Base URL for API calls
        - model: Model identifier

    Note:
        Never includes actual API key values in output.
    """
    api_key = os.environ.get("ZHIPU_API_KEY", "").strip()
    fallback_key = os.environ.get("ZAI_API_KEY", "").strip()

    # Use ZHIPU_API_KEY if available, otherwise fall back to ZAI_API_KEY
    key_present = bool(api_key) or bool(fallback_key)

    return {
        "enabled": key_present,
        "api_key_present": key_present,
        "base_url": os.environ.get(
            "ZHIPU_BASE_URL", "https://api.z.ai/api/coding/paas/v4"
        ),
        "model": os.environ.get("ZHIPU_MODEL", "glm-5"),
    }


def discover_minimax_config() -> dict[str, Any]:
    """Discover MiniMax provider configuration from environment.

    Checks for MINIMAX_API_KEY and MINIMAX_ENABLED environment variables.

    Returns:
        Dictionary with provider configuration:
        - enabled: Whether provider is enabled
        - api_key_present: Whether API key is present (not the value)
        - base_url: Base URL for API calls
        - model: Model identifier

    Note:
        Never includes actual API key values in output.
    """
    api_key = os.environ.get("MINIMAX_API_KEY", "").strip()
    enabled_str = os.environ.get("MINIMAX_ENABLED", "false").lower()
    enabled = enabled_str in ("true", "1", "yes", "on")

    return {
        "enabled": enabled and bool(api_key),
        "api_key_present": bool(api_key),
        "base_url": os.environ.get("MINIMAX_BASE_URL", "https://api.minimax.chat/v1"),
        "model": os.environ.get("MINIMAX_MODEL", "abab6.5s"),
    }


def get_available_providers() -> list[str]:
    """Get list of available LLM provider names.

    Returns:
        List of provider names that have API keys configured.
        Possible values: "kimi", "zai", "zhipu", "minimax"

    Note:
        Only returns provider names, never includes API keys or secrets.
    """
    providers = []

    if discover_kimi_config()["enabled"]:
        providers.append("kimi")
    if discover_zai_config()["enabled"]:
        providers.append("zai")
    if discover_zhipu_config()["enabled"]:
        providers.append("zhipu")
    if discover_minimax_config()["enabled"]:
        providers.append("minimax")

    return providers


def diagnose_provider_availability() -> list[dict[str, Any]]:
    """Diagnose availability of all LLM providers.

    Returns structured diagnostic information about each provider
    without revealing any API keys or secrets.

    Returns:
        List of dictionaries, each containing:
        - provider: Provider name (e.g., "kimi", "zai")
        - available: Boolean indicating if provider is available
        - reason: String explaining why provider is not available (if applicable)
        - config: Sanitized configuration (no secrets)

    Example:
        >>> diagnostics = diagnose_provider_availability()
        >>> for d in diagnostics:
        ...     status = "✓" if d["available"] else "✗"
        ...     print(f"{status} {d['provider']}: {d.get('reason', 'OK')}")
    """
    results = []

    # KIMI
    kimi = discover_kimi_config()
    kimi_diag: dict[str, Any] = {
        "provider": "kimi",
        "available": kimi["enabled"],
        "config": {
            "base_url": kimi["base_url"],
            "model": kimi["model"],
        },
    }
    if not kimi["api_key_present"]:
        kimi_diag["reason"] = "KIMI_API_KEY not set"
    elif not kimi["enabled"]:
        kimi_diag["reason"] = "KIMI_ENABLED is false"
    results.append(kimi_diag)

    # Z.ai
    zai = discover_zai_config()
    zai_diag: dict[str, Any] = {
        "provider": "zai",
        "available": zai["enabled"],
        "config": {
            "base_url": zai["base_url"],
        },
    }
    if not zai["api_key_present"]:
        zai_diag["reason"] = "ZAI_API_KEY not set"
    results.append(zai_diag)

    # Zhipu
    zhipu = discover_zhipu_config()
    zhipu_diag: dict[str, Any] = {
        "provider": "zhipu",
        "available": zhipu["enabled"],
        "config": {
            "base_url": zhipu["base_url"],
            "model": zhipu["model"],
        },
    }
    if not zhipu["api_key_present"]:
        zhipu_diag["reason"] = "ZHIPU_API_KEY (or ZAI_API_KEY fallback) not set"
    results.append(zhipu_diag)

    # MiniMax
    minimax = discover_minimax_config()
    minimax_diag: dict[str, Any] = {
        "provider": "minimax",
        "available": minimax["enabled"],
        "config": {
            "base_url": minimax["base_url"],
            "model": minimax["model"],
        },
    }
    if not minimax["api_key_present"]:
        minimax_diag["reason"] = "MINIMAX_API_KEY not set"
    elif not minimax["enabled"]:
        minimax_diag["reason"] = "MINIMAX_ENABLED is false"
    results.append(minimax_diag)

    return results


# =============================================================================
# Database Configuration Loader (GATE-RECOVERY-001)
# =============================================================================


def is_running_in_container() -> bool:
    """Detect if running inside a Docker container.

    Returns:
        True if running inside a container, False otherwise.
    """
    # Check for .dockerenv file
    if os.path.exists("/.dockerenv"):
        return True

    # Check cgroup for docker/containerd references
    try:
        with open("/proc/1/cgroup") as f:
            cgroup_content = f.read()
            if any(
                marker in cgroup_content
                for marker in ["docker", "containerd", "kubepods"]
            ):
                return True
    except (FileNotFoundError, PermissionError):
        pass

    return False


def load_database_config(
    prefix: str = "POSTGRES_",
    container_host_default: str = "chiseai-postgres",
    host_host_default: str = "host.docker.internal",
    port_default: int = 5434,
    db_default: str = "chiseai",
    user_default: str = "chiseai",
) -> dict[str, Any]:
    """Load unified database configuration from environment.

    Reads database connection parameters from environment variables with
    intelligent defaults based on execution context (container vs host).

    Args:
        prefix: Prefix for environment variables (default: "POSTGRES_")
        container_host_default: Default host when running in container
        host_host_default: Default host when running on host
        port_default: Default port number
        db_default: Default database name
        user_default: Default username

    Returns:
        Dictionary with database configuration:
        - host: Database host
        - port: Database port
        - database: Database name
        - user: Username
        - password: Password (required, no default)

    Raises:
        ValueError: If password is not set in environment

    Example:
        >>> config = load_database_config()
        >>> print(f"Connecting to {config['host']}:{config['port']}")
    """
    # Detect execution context
    in_container = is_running_in_container()

    # Determine default host based on context
    default_host = container_host_default if in_container else host_host_default

    # Load from environment with defaults
    host = os.environ.get(f"{prefix}HOST", default_host)
    port_str = os.environ.get(f"{prefix}PORT", str(port_default))
    database = os.environ.get(f"{prefix}DB", db_default)
    user = os.environ.get(f"{prefix}USER", user_default)
    password = os.environ.get(f"{prefix}PASSWORD")

    # Validate password is set
    if not password:
        raise ValueError(
            f"{prefix}PASSWORD environment variable is required but not set"
        )

    # Parse port as integer
    try:
        port = int(port_str)
    except ValueError:
        logger.warning(
            f"Invalid {prefix}PORT value '{port_str}', using default {port_default}"
        )
        port = port_default

    config = {
        "host": host,
        "port": port,
        "database": database,
        "user": user,
        "password": password,
        "in_container": in_container,
    }

    logger.debug(
        f"Loaded database config: host={host}, port={port}, "
        f"database={database}, user={user}, in_container={in_container}"
    )

    return config


def get_postgres_connection_string(
    config: dict[str, Any] | None = None,
) -> str:
    """Build PostgreSQL connection string from config.

    Args:
        config: Database config dict from load_database_config(),
                or None to load fresh config

    Returns:
        PostgreSQL connection string

    Example:
        >>> conn_str = get_postgres_connection_string()
        >>> # postgresql://user:pass@host:port/database
    """
    if config is None:
        config = load_database_config()

    return (
        f"postgresql://{config['user']}:{config['password']}"
        f"@{config['host']}:{config['port']}/{config['database']}"
    )
