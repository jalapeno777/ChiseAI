#!/usr/bin/env python3
"""Environment diagnostic script.

Standalone diagnostic tool that reports provider availability
and environment configuration. Safe to run from cron or Docker.

Usage:
    python scripts/check_env.py
    python scripts/check_env.py --verbose
    ./scripts/check_env.py

Exit codes:
    0 - At least one provider available
    1 - No providers available
    2 - Error occurred
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config.bootstrap import bootstrap, format_provider_status

# Configure logging
logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> int:
    """Run environment diagnostic.

    Returns:
        Exit code: 0 if at least one provider available, 1 otherwise, 2 on error
    """
    parser = argparse.ArgumentParser(
        description="Environment diagnostic script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python scripts/check_env.py
    python scripts/check_env.py --verbose
    python scripts/check_env.py --env-file /path/to/.env
        """,
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output",
    )
    parser.add_argument(
        "--env-file",
        "-e",
        type=Path,
        help="Specific env file to load",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Verbose mode enabled")

    try:
        # Bootstrap the environment
        state = bootstrap(load_env=True, env_file=args.env_file, verbose=args.verbose)

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
            if args.verbose:
                logger.debug("At least one provider available - exit 0")
            return 0

        if args.verbose:
            logger.debug("No providers available - exit 1")
        return 1

    except Exception as e:
        logger.error(f"Diagnostic failed: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
