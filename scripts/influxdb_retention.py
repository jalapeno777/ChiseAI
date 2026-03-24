#!/usr/bin/env python3
"""
InfluxDB Retention Policy Management Script

This script manages retention policies for InfluxDB buckets to prevent disk exhaustion.
It provides both inspection and update capabilities for retention settings.

Usage:
    python3 scripts/influxdb_retention.py --list          # List current retention policies
    python3 scripts/influxdb_retention.py --set <bucket_id> <hours>  # Set retention for a bucket

Retention Guidelines:
    - chiseai (main data): 90 days (2160h)
    - governance: 7 days (168h)
    - _monitoring: 7 days (168h)
    - _tasks: 3 days (72h)
"""

import argparse
import subprocess
import json
import sys
from typing import Optional


INFLUX_CONTAINER = "chiseai-influxdb"
DEFAULT_RETENTION_HOURS = {
    "chiseai": 2160,  # 90 days
    "governance": 168,  # 7 days
    "_monitoring": 168,  # 7 days
    "_tasks": 72,  # 3 days
}


def run_influx_command(cmd: list[str]) -> str:
    """Run a command in the InfluxDB container."""
    full_cmd = ["docker", "exec", INFLUX_CONTAINER] + cmd
    result = subprocess.run(full_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error running command: {' '.join(cmd)}", file=sys.stderr)
        print(f"stderr: {result.stderr}", file=sys.stderr)
        return ""
    return result.stdout


def list_buckets() -> list[dict]:
    """List all buckets with their retention policies."""
    output = run_influx_command(["influx", "bucket", "list", "--json"])
    if not output:
        return []
    try:
        data = json.loads(output)
        return data if isinstance(data, list) else [data]
    except json.JSONDecodeError:
        # Try plain text output
        return []


def list_retention_policies() -> str:
    """List retention policies via V1 shell."""
    output = run_influx_command(["influx", "v1", "shell"])
    # Parse the output - it contains a table of retention policies
    return output


def get_bucket_retention(bucket_id: str) -> Optional[str]:
    """Get the retention duration for a specific bucket."""
    buckets = list_buckets()
    for bucket in buckets:
        if bucket.get("id") == bucket_id:
            return bucket.get("retentionRules", [{}])[0].get("everySeconds", "infinite")
    return None


def update_bucket_retention(bucket_id: str, retention_hours: int) -> bool:
    """Update the retention policy for a bucket."""
    retention_seconds = retention_hours * 3600
    result = run_influx_command(
        [
            "influx",
            "bucket",
            "update",
            "--id",
            bucket_id,
            "--retention",
            f"{retention_seconds}s",
        ]
    )
    return "id" in result.lower() or bucket_id in result


def main():
    parser = argparse.ArgumentParser(description="Manage InfluxDB retention policies")
    parser.add_argument(
        "--list", "-l", action="store_true", help="List current retention policies"
    )
    parser.add_argument(
        "--set",
        nargs=2,
        metavar=("BUCKET_ID", "HOURS"),
        help="Set retention policy for a bucket (id, hours)",
    )
    parser.add_argument(
        "--apply-defaults",
        action="store_true",
        help="Apply default retention policies to all known buckets",
    )

    args = parser.parse_args()

    if args.list:
        print("Fetching retention policies...")
        output = run_influx_command(["influx", "bucket", "list"])
        print(output if output else "Failed to fetch buckets")
        return

    if args.set:
        bucket_id, hours = args.set
        retention_hours = int(hours)
        print(f"Updating bucket {bucket_id} retention to {retention_hours} hours...")
        if update_bucket_retention(bucket_id, retention_hours):
            print("Success!")
        else:
            print("Failed to update bucket retention")
            sys.exit(1)
        return

    if args.apply_defaults:
        print("Fetching buckets to apply default retention policies...")
        buckets = list_buckets()

        # Map bucket names to IDs
        name_to_id = {b.get("name"): b.get("id") for b in buckets}

        for bucket_name, retention_hours in DEFAULT_RETENTION_HOURS.items():
            if bucket_name in name_to_id:
                bucket_id = name_to_id[bucket_name]
                print(f"Setting {bucket_name} ({bucket_id}) to {retention_hours}h...")
                if update_bucket_retention(bucket_id, retention_hours):
                    print(f"  Success!")
                else:
                    print(f"  Failed!")
            else:
                print(f"Bucket {bucket_name} not found, skipping")
        return

    # Default: show help
    parser.print_help()


if __name__ == "__main__":
    main()
