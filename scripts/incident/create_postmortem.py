#!/usr/bin/env python3
"""
Create post-mortem documents from incidents.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from config.bootstrap import bootstrap

# Try to import Redis
try:
    import redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


def get_incident_from_redis(story_id):
    """Get incident data from Redis."""
    if not REDIS_AVAILABLE:
        return None

    try:
        r = redis.Redis(host="host.docker.internal", port=6380, db=0)
        key = f"bmad:chiseai:iterlog:story:{story_id}:incidents"

        # Get last incident
        incidents = r.lrange(key, -1, -1)
        if incidents:
            return json.loads(incidents[0])
        return None
    except Exception as e:
        print(f"Warning: Could not read from Redis: {e}")
        return None


def generate_postmortem(incident_data, story_id):
    """Generate post-mortem markdown content."""

    content = f"""# Post-Mortem: {story_id}

## Metadata
- **Story**: {story_id}
- **Severity**: {incident_data.get("severity", "Unknown")}
- **Date**: {datetime.now().strftime("%Y-%m-%d")}
- **Created**: {datetime.now().isoformat()}

## Summary
{incident_data.get("symptom", "No summary provided")}

## Timeline
| Time | Event |
|------|-------|
| T+0 | Incident detected |
| T+? | (Fill in actual timeline) |
| T+? | Issue resolved |

## Root Cause Analysis
### 5 Whys
1. Why? → (Answer)
2. Why? → (Answer)
3. Why? → (Answer)
4. Why? → (Answer)
5. Why? → Root cause

### Root Cause
{incident_data.get("root_cause", "Not documented")}

## Impact
- (Fill in actual impact)

## Resolution
- (Fill in how issue was resolved)

## Prevention Measures
- [ ] {incident_data.get("prevention_rule", "No prevention rule documented")}
- [ ] (Add more action items)

## Lessons Learned
- (Fill in learnings)

## Action Items
| Task | Owner | Due Date | Status |
|------|-------|----------|--------|
| (Add tasks) | | | |

---
*Generated from incident log*
"""

    return content


def interactive_mode():
    """Interactive post-mortem creation."""
    print("Interactive Post-Mortem Creation")
    print("=" * 50)

    story_id = input("Story ID: ")

    # Try to get from Redis
    incident = get_incident_from_redis(story_id)

    if incident:
        print(f"Found incident data for {story_id}")
        use_data = input("Use incident data? (y/n): ").lower() == "y"
    else:
        print("No incident data found, creating empty template")
        incident = {
            "severity": input("Severity (P0/P1/P2/P3): "),
            "symptom": input("What went wrong? "),
            "root_cause": input("Why did it happen? "),
            "prevention_rule": input("How to prevent? "),
        }
        use_data = True

    return story_id, incident if use_data else None


def main():
    # Bootstrap environment first
    bootstrap(load_env=True)
    parser = argparse.ArgumentParser(description="Create post-mortem from incident")
    parser.add_argument("--story-id", help="Story ID")
    parser.add_argument("--output", help="Output file path")
    parser.add_argument("--interactive", action="store_true", help="Interactive mode")

    args = parser.parse_args()

    if args.interactive:
        story_id, incident = interactive_mode()
    elif args.story_id:
        story_id = args.story_id
        incident = get_incident_from_redis(story_id)
        if not incident:
            print(f"No incident found for {story_id}")
            print("Use --interactive to create manually")
            sys.exit(1)
    else:
        print("Error: Provide --story-id or use --interactive")
        sys.exit(1)

    # Generate post-mortem
    content = generate_postmortem(incident, story_id)

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        # Create postmortems directory
        postmortems_dir = Path("docs/postmortems")
        postmortems_dir.mkdir(parents=True, exist_ok=True)
        output_path = (
            postmortems_dir / f"{datetime.now().strftime('%Y-%m-%d')}-{story_id}.md"
        )

    # Write file
    output_path.write_text(content)

    print(f"✅ Post-mortem created: {output_path}")
    print(f"   Story: {story_id}")
    print(f"   Severity: {incident.get('severity', 'Unknown')}")


if __name__ == "__main__":
    main()
