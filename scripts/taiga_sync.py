#!/usr/bin/env python3
"""Legacy-compatible Taiga sync shim.

Taiga integration is now legacy-exempt in current planning context. This script
preserves command compatibility and provides safe validation/no-op behavior.
"""

from __future__ import annotations

import argparse
import os
import sys


def has_taiga_config() -> bool:
    has_token = bool(os.getenv("TAIGA_TOKEN"))
    has_userpass = bool(os.getenv("TAIGA_USERNAME") and os.getenv("TAIGA_PASSWORD"))
    return bool(os.getenv("TAIGA_PROJECT_SLUG")) and (has_token or has_userpass)


def main() -> int:
    parser = argparse.ArgumentParser(description="Taiga sync compatibility shim")
    parser.add_argument("--validate", action="store_true", help="Validate Taiga config")
    parser.add_argument(
        "--apply", action="store_true", help="Apply sync (legacy no-op)"
    )
    parser.add_argument("--force", action="store_true", help="Legacy flag (no-op)")
    args = parser.parse_args()

    # Validate path: fail fast only when explicitly asked and sync is marked required.
    if args.validate:
        required = os.getenv("TAIGA_SYNC_REQUIRED", "false").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if required and not has_taiga_config():
            print(
                "ERROR: TAIGA sync required but missing config. Set TAIGA_PROJECT_SLUG and TAIGA_TOKEN (or TAIGA_USERNAME/TAIGA_PASSWORD).",
                file=sys.stderr,
            )
            return 1
        print("Taiga sync validate: OK (legacy-exempt mode)")
        return 0

    if args.apply:
        if not has_taiga_config():
            print(
                "Taiga sync apply: skipped (missing Taiga credentials, legacy-exempt mode)"
            )
            return 0
        print("Taiga sync apply: no-op compatibility mode (legacy-exempt)")
        return 0

    print("Taiga sync dry-run: no-op compatibility mode (legacy-exempt)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
