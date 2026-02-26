"""Load .env file for cron context.

This module provides centralized .env loading for monitoring scripts
running in cron or other minimal environments.
"""

import os
from pathlib import Path


def load_env_file():
    """Load .env file from project root.

    Finds the project root by traversing up from this script's location,
    then loads the .env file into environment variables.

    Only sets variables that aren't already defined in the environment
    to allow for override via explicit env vars.

    Returns:
        bool: True if .env file was found and loaded, False otherwise.
    """
    # Find project root (where .env should be)
    script_dir = Path(__file__).parent.absolute()
    project_root = (
        script_dir.parent.parent
    )  # scripts/monitoring/ -> scripts/ -> project/

    env_file = project_root / ".env"

    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    # Only set if not already in environment
                    if key not in os.environ:
                        os.environ[key] = value.strip().strip('"').strip("'")
        return True
    return False


# Auto-load on import
load_env_file()
