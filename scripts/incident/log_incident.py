#!/usr/bin/env python3
"""
Log structured incidents for ChiseAI.
Stores to Redis and markdown fallback.
"""

import argparse
import json
from datetime import datetime
from pathlib import Path
import sys

# Try to import Redis
try:
    import redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


def log_to_redis(incident_data):
    """Log incident to Redis."""
    if not REDIS_AVAILABLE:
        return False

    try:
        r = redis.Redis(host="host.docker.internal", port=6380, db=0)
        story_id = incident_data["story_id"]

        key = f"bmad:chiseai:iterlog:story:{story_id}:incidents"
        r.rpush(key, json.dumps(incident_data))

        return True
    except Exception as e:
        print(f"Warning: Could not log to Redis: {e}")
        return False


def log_to_markdown(incident_data):
    """Log incident to markdown fallback."""
    try:
        story_id = incident_data["story_id"]
        fallback_path = Path(f"docs/tempmemories/iterlog-{story_id}.md")

        # Create file if doesn't exist
        if not fallback_path.exists():
            fallback_path.write_text(f"# Iteration Log: {story_id}\n\n")

        # Append incident
        with open(fallback_path, "a") as f:
            f.write(f"\n## Incident: {datetime.now().isoformat()}\n\n")
            f.write(f"**Severity:** {incident_data.get('severity', 'unknown')}\n\n")
            f.write(f"**Symptom:**\n{incident_data.get('symptom', 'N/A')}\n\n")
            f.write(f"**Root Cause:**\n{incident_data.get('root_cause', 'N/A')}\n\n")
            f.write(
                f"**Prevention:**\n{incident_data.get('prevention_rule', 'N/A')}\n\n"
            )

        return True
    except Exception as e:
        print(f"Error: Could not log to markdown: {e}")
        return False


def interactive_mode():
    """Interactive incident logging."""
    print("Interactive Incident Logging")
    print("=" * 50)

    incident = {}
    incident["story_id"] = input("Story ID: ")
    incident["severity"] = input("Severity (P0/P1/P2/P3): ")
    incident["symptom"] = input("What went wrong? ")
    incident["root_cause"] = input("Why did it happen? ")
    incident["prevention_rule"] = input("How to prevent? ")
    incident["timestamp"] = datetime.now().isoformat()

    return incident


def main():
    parser = argparse.ArgumentParser(description="Log structured incidents")
    parser.add_argument("--interactive", action="store_true", help="Interactive mode")
    parser.add_argument("--story-id", help="Story ID")
    parser.add_argument("--severity", choices=["P0", "P1", "P2", "P3"], help="Severity")
    parser.add_argument("--symptom", help="What went wrong")
    parser.add_argument("--root-cause", help="Why it happened")
    parser.add_argument("--prevention", help="How to prevent")

    args = parser.parse_args()

    if args.interactive:
        incident = interactive_mode()
    else:
        # Validate required args
        required = ["story_id", "severity", "symptom", "root_cause", "prevention"]
        missing = [r for r in required if not getattr(args, r.replace("-", "_"))]

        if missing:
            print(f"Error: Missing required arguments: {missing}")
            print("Use --interactive or provide all required fields")
            sys.exit(1)

        incident = {
            "story_id": args.story_id,
            "severity": args.severity,
            "symptom": args.symptom,
            "root_cause": args.root_cause,
            "prevention_rule": args.prevention,
            "timestamp": datetime.now().isoformat(),
        }

    # Log to both Redis and markdown
    redis_ok = log_to_redis(incident)
    markdown_ok = log_to_markdown(incident)

    if redis_ok or markdown_ok:
        print(f"✅ Incident logged for {incident['story_id']}")
        if not redis_ok:
            print("   (Logged to markdown fallback - Redis unavailable)")
    else:
        print("❌ Failed to log incident")
        sys.exit(1)


if __name__ == "__main__":
    main()
