"""
Entry point for running runbooks as a module.

Usage:
    python -m runbooks list
    python -m runbooks execute <runbook-name> [--dry-run]
    python -m runbooks show <runbook-name>
    python -m runbooks history [<runbook-name>] [--limit N]
"""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
