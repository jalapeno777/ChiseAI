"""Monitoring scripts package.

This package provides monitoring and alerting scripts for the ChiseAI system.
All scripts automatically load environment variables from the project .env file.
"""

# Auto-load .env file for cron context
from . import load_env  # noqa: F401

__version__ = "1.0.0"
