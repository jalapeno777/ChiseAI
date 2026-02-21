"""Bybit credential resolution utility.

Provides robust credential resolution with support for multiple
environment variable naming conventions and explicit .env loading.

Priority order for credential pairs:
1. BYBIT_DEMO_API_KEY / BYBIT_DEMO_API_SECRET
2. BYBIT_API_KEY / BYBIT_API_SECRET
3. BYBIT_TESTNET_API_KEY / BYBIT_TESTNET_API_SECRET

For SAFETY-BYBIT-AUTH: Credential Resolution Fix
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class BybitCredentials:
    """Resolved Bybit credentials with metadata.

    Attributes:
        api_key: The API key
        api_secret: The API secret
        source: Which env var pair was used (e.g., "BYBIT_DEMO_API_KEY")
        testnet_mode: Whether these are testnet credentials
        demo_mode: Whether these are demo account credentials
        env_file_loaded: Whether .env file was explicitly loaded
    """

    api_key: str
    api_secret: str
    source: str
    testnet_mode: bool
    demo_mode: bool = False
    env_file_loaded: bool = False

    def get_masked_key(self) -> str:
        """Return masked API key (first 4 + last 4 chars only)."""
        if len(self.api_key) <= 8:
            return "****"
        return f"{self.api_key[:4]}...{self.api_key[-4:]}"

    def get_masked_secret(self) -> str:
        """Return masked API secret (first 4 + last 4 chars only)."""
        if len(self.api_secret) <= 8:
            return "****"
        return f"{self.api_secret[:4]}...{self.api_secret[-4:]}"

    def validate_key_prefix(self) -> bool:
        """Check if API key starts with expected demo prefix 'R9K'."""
        return self.api_key.startswith("R9K")

    def validate_secret_prefix(self) -> bool:
        """Check if API secret starts with expected demo prefix '3Nd'."""
        return self.api_secret.startswith("3Nd")

    def get_prefix_validation(self) -> dict[str, Any]:
        """Get prefix validation results for diagnostics.

        Returns:
            Dictionary with validation results and masked prefix info
        """
        key_valid = self.validate_key_prefix()
        secret_valid = self.validate_secret_prefix()

        # Get first 3 chars of actual credentials for prefix display
        key_prefix = self.api_key[:3] if len(self.api_key) >= 3 else self.api_key
        secret_prefix = (
            self.api_secret[:3] if len(self.api_secret) >= 3 else self.api_secret
        )

        return {
            "key_valid": key_valid,
            "secret_valid": secret_valid,
            "expected_key_prefix": "R9K",
            "expected_secret_prefix": "3Nd",
            "actual_key_prefix": key_prefix,
            "actual_secret_prefix": secret_prefix,
            "all_valid": key_valid and secret_valid,
        }


class BybitCredentialResolver:
    """Resolver for Bybit API credentials.

    Implements priority-order resolution across multiple env var naming
    conventions with explicit .env file loading.

    Priority order:
    1. BYBIT_DEMO_API_KEY / BYBIT_DEMO_API_SECRET
    2. BYBIT_API_KEY / BYBIT_API_SECRET
    3. BYBIT_TESTNET_API_KEY / BYBIT_TESTNET_API_SECRET
    """

    # Priority order of credential pairs
    # Format: (key_var, secret_var, is_testnet, is_demo)
    CREDENTIAL_PAIRS = [
        ("BYBIT_DEMO_API_KEY", "BYBIT_DEMO_API_SECRET", False, True),
        ("BYBIT_API_KEY", "BYBIT_API_SECRET", False, False),
        ("BYBIT_TESTNET_API_KEY", "BYBIT_TESTNET_API_SECRET", True, False),
    ]

    # Expected prefixes for demo account credentials
    EXPECTED_KEY_PREFIX = "R9K"
    EXPECTED_SECRET_PREFIX = "3Nd"

    def __init__(self, env_file_path: str | None = None) -> None:
        """Initialize resolver.

        Args:
            env_file_path: Path to .env file (default: .env in current directory)
        """
        self.env_file_path = env_file_path or ".env"
        self._env_file_loaded = False

    def load_dotenv(self, override: bool = False) -> bool:
        """Explicitly load .env file using python-dotenv if available.

        Args:
            override: Whether to override existing env vars

        Returns:
            True if .env was loaded successfully, False otherwise
        """
        try:
            from dotenv import load_dotenv

            env_path = Path(self.env_file_path)
            if env_path.exists():
                load_dotenv(dotenv_path=env_path, override=override)
                self._env_file_loaded = True
                return True
            else:
                # Try repo root
                repo_root = Path(__file__).parent.parent.parent.parent
                env_path = repo_root / ".env"
                if env_path.exists():
                    load_dotenv(dotenv_path=env_path, override=override)
                    self._env_file_loaded = True
                    return True
        except ImportError:
            # python-dotenv not installed, try manual parsing
            return self._manual_load_dotenv()
        except Exception:
            pass

        return False

    def _manual_load_dotenv(self) -> bool:
        """Manually parse .env file if python-dotenv is not available."""
        env_path = Path(self.env_file_path)
        if not env_path.exists():
            # Try repo root
            repo_root = Path(__file__).parent.parent.parent.parent
            env_path = repo_root / ".env"

        if not env_path.exists():
            return False

        try:
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, value = line.split("=", 1)
                        key = key.strip()
                        value = value.strip().strip("\"'")
                        if key not in os.environ:
                            os.environ[key] = value
            self._env_file_loaded = True
            return True
        except Exception:
            return False

    def resolve(self, load_env: bool = True) -> BybitCredentials | None:
        """Resolve credentials using priority order.

        Args:
            load_env: Whether to explicitly load .env file first

        Returns:
            BybitCredentials if found, None otherwise
        """
        if load_env:
            self.load_dotenv()

        # Check each credential pair in priority order
        for key_var, secret_var, is_testnet, is_demo in self.CREDENTIAL_PAIRS:
            api_key = os.environ.get(key_var, "").strip()
            api_secret = os.environ.get(secret_var, "").strip()

            if api_key and api_secret:
                return BybitCredentials(
                    api_key=api_key,
                    api_secret=api_secret,
                    source=key_var,
                    testnet_mode=is_testnet,
                    demo_mode=is_demo,
                    env_file_loaded=self._env_file_loaded,
                )

        return None

    def resolve_all(self, load_env: bool = True) -> dict[str, BybitCredentials]:
        """Resolve all available credential pairs.

        Args:
            load_env: Whether to explicitly load .env file first

        Returns:
            Dict mapping source name to BybitCredentials
        """
        if load_env:
            self.load_dotenv()

        found = {}
        for key_var, secret_var, is_testnet, is_demo in self.CREDENTIAL_PAIRS:
            api_key = os.environ.get(key_var, "").strip()
            api_secret = os.environ.get(secret_var, "").strip()

            if api_key and api_secret:
                found[key_var] = BybitCredentials(
                    api_key=api_key,
                    api_secret=api_secret,
                    source=key_var,
                    testnet_mode=is_testnet,
                    demo_mode=is_demo,
                    env_file_loaded=self._env_file_loaded,
                )

        return found

    def validate_credential_prefixes(
        self, credentials: BybitCredentials
    ) -> dict[str, Any]:
        """Validate credential prefixes for diagnostic purposes.

        This is an informational check that does not block credential
        resolution but reports whether credentials have expected prefixes.

        Args:
            credentials: The BybitCredentials to validate

        Returns:
            Dictionary with validation results
        """
        return credentials.get_prefix_validation()

    def get_credential_status(self, load_env: bool = True) -> dict[str, Any]:
        """Get detailed status of credential resolution.

        Args:
            load_env: Whether to explicitly load .env file first

        Returns:
            Status dictionary with all checks performed
        """
        if load_env:
            self.load_dotenv()

        status = {
            "env_file_loaded": self._env_file_loaded,
            "env_file_path": str(self.env_file_path),
            "checks": [],
            "found_credentials": [],
            "selected": None,
            "prefix_validation": None,
        }

        # Check each credential pair
        for key_var, secret_var, is_testnet, is_demo in self.CREDENTIAL_PAIRS:
            key_present = bool(os.environ.get(key_var, "").strip())
            secret_present = bool(os.environ.get(secret_var, "").strip())

            check = {
                "key_var": key_var,
                "secret_var": secret_var,
                "key_present": key_present,
                "secret_present": secret_present,
                "complete": key_present and secret_present,
                "is_testnet": is_testnet,
                "is_demo": is_demo,
            }
            status["checks"].append(check)

            if check["complete"]:
                status["found_credentials"].append(key_var)

        # Determine which would be selected
        resolved = self.resolve(load_env=False)  # Already loaded
        if resolved:
            status["selected"] = {
                "source": resolved.source,
                "masked_key": resolved.get_masked_key(),
                "testnet_mode": resolved.testnet_mode,
                "demo_mode": resolved.demo_mode,
            }
            # Add prefix validation for the selected credentials
            status["prefix_validation"] = self.validate_credential_prefixes(resolved)

        return status


def resolve_bybit_credentials(
    load_env: bool = True,
    env_file_path: str | None = None,
) -> BybitCredentials | None:
    """Convenience function to resolve Bybit credentials.

    Args:
        load_env: Whether to explicitly load .env file first
        env_file_path: Path to .env file (default: .env in current directory)

    Returns:
        BybitCredentials if found, None otherwise

    Example:
        >>> creds = resolve_bybit_credentials()
        >>> if creds:
        ...     print(f"Using credentials from {creds.source}")
        ...     print(f"Key: {creds.get_masked_key()}")
    """
    resolver = BybitCredentialResolver(env_file_path=env_file_path)
    return resolver.resolve(load_env=load_env)


def get_credential_resolution_status(
    env_file_path: str | None = None,
) -> dict[str, Any]:
    """Get detailed credential resolution status.

    Args:
        env_file_path: Path to .env file (default: .env in current directory)

    Returns:
        Status dictionary with all checks performed

    Example:
        >>> status = get_credential_resolution_status()
        >>> print(f"Found {len(status['found_credentials'])} credential pairs")
        >>> for check in status['checks']:
        ...     print(f"{check['key_var']}: {'✓' if check['complete'] else '✗'}")
    """
    resolver = BybitCredentialResolver(env_file_path=env_file_path)
    return resolver.get_credential_status(load_env=True)
