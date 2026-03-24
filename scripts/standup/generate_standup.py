#!/usr/bin/env python3
"""
Daily Standup Report Generator

Generates a comprehensive daily standup report from:
- docs/bmm-workflow-status.yaml (workflow status)
- Redis iterlog keys (active stories)
- Git log (recent merges)
- Incident records (blockers)

Usage:
    python3 scripts/standup/generate_standup.py
    python3 scripts/standup/generate_standup.py --post-discord --channel-id "1234567890"
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import yaml

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    import redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    print("Warning: redis package not installed. Redis queries will be skipped.")


class StandupGenerator:
    """Generate daily standup reports from multiple data sources."""

    def __init__(
        self,
        date: str | None = None,
        redis_host: str = "localhost",
        redis_port: int = 6380,
        redis_db: int = 0,
        verbose: bool = False,
    ):
        self.date = date or datetime.now().strftime("%Y-%m-%d")
        self.verbose = verbose
        self.redis_client = None

        # Initialize Redis connection
        if REDIS_AVAILABLE:
            try:
                self.redis_client = redis.Redis(
                    host=redis_host, port=redis_port, db=redis_db, decode_responses=True
                )
                self.redis_client.ping()
                if self.verbose:
                    print(f"✓ Connected to Redis at {redis_host}:{redis_port}")
            except Exception as e:
                if self.verbose:
                    print(f"⚠ Redis connection failed: {e}")
                self.redis_client = None

        # Load workflow status
        self.workflow_status = self._load_workflow_status()

    def _load_workflow_status(self) -> dict[str, Any]:
        """Load workflow status from YAML file."""
        workflow_path = Path("docs/bmm-workflow-status.yaml")

        if not workflow_path.exists():
            raise FileNotFoundError(
                f"Workflow status file not found: {workflow_path}\n"
                "Please run this script from the ChiseAI repository root."
            )

        with open(workflow_path) as f:
            return yaml.safe_load(f)

    def _get_active_stories_from_redis(self) -> list[dict[str, Any]]:
        """Query Redis for active story iterlogs."""
        if not self.redis_client:
            return []

        active_stories = []

        try:
            # Scan for all story iterlog keys
            cursor = 0
            while True:
                cursor, keys = self.redis_client.scan(
                    cursor=cursor, match="bmad:chiseai:iterlog:story:*", count=100
                )

                # Filter out incident subkeys
                story_keys = [k for k in keys if ":incidents" not in k]

                for key in story_keys:
                    story_data = self.redis_client.hgetall(key)
                    if story_data.get("status") in ["in_progress", "planned"]:
                        active_stories.append(story_data)

                if cursor == 0:
                    break

        except Exception as e:
            if self.verbose:
                print(f"⚠ Error querying Redis: {e}")

        return active_stories

    def _get_completed_yesterday(self) -> list[dict[str, Any]]:
        """Get stories completed in the last 24-48 hours."""
        completed = []
        datetime.now() - timedelta(days=1)
        day_before = datetime.now() - timedelta(days=2)

        # From workflow status
        for story in self.workflow_status.get("completed", []):
            # Check merge_date or completion_date
            date_fields = ["merged_date", "completion_date", "created_date"]
            for field in date_fields:
                date_str = story.get(field)
                if date_str:
                    try:
                        story_date = datetime.strptime(date_str, "%Y-%m-%d")
                        if story_date >= day_before:
                            completed.append(story)
                            break
                    except ValueError:
                        pass

        return completed

    def _get_planned_today(self) -> dict[str, list[dict[str, Any]]]:
        """Get planned work for today, grouped by priority."""
        planned = {"P0": [], "P1": [], "P2": [], "P3": []}

        # From workflow status backlog
        for story in self.workflow_status.get("backlog", []):
            status = story.get("status", "")
            if status in ["in_progress", "planned"]:
                priority = story.get("priority", "P3")
                if priority in planned:
                    planned[priority].append(story)

        # From Redis active stories
        redis_stories = self._get_active_stories_from_redis()
        for story in redis_stories:
            # Avoid duplicates
            story_id = story.get("story_id")
            if not any(s.get("id") == story_id for p in planned.values() for s in p):
                priority = story.get("priority", "P3")
                if priority in planned:
                    planned[priority].append(
                        {
                            "id": story_id,
                            "title": story.get("story_title", "Untitled"),
                            "owner": story.get("owner", "TBD"),
                            "status": story.get("status"),
                            "phase": story.get("phase"),
                            "priority": priority,
                        }
                    )

        return planned

    def _get_blockers(self) -> dict[str, list[dict[str, Any]]]:
        """Identify current blockers."""
        blockers = {"technical": [], "dependencies": [], "resources": []}

        # From workflow status - stories with status "blocked"
        for story in self.workflow_status.get("backlog", []):
            if story.get("status") == "blocked":
                blockers["technical"].append(
                    {
                        "id": story.get("id"),
                        "title": story.get("title"),
                        "description": story.get("description", "No description"),
                        "owner": story.get("owner", "TBD"),
                    }
                )

            # Check for dependencies
            if story.get("depends_on"):
                blockers["dependencies"].append(
                    {
                        "id": story.get("id"),
                        "title": story.get("title"),
                        "depends_on": story.get("depends_on"),
                        "owner": story.get("owner", "TBD"),
                    }
                )

        # From Redis incidents
        if self.redis_client:
            try:
                cursor = 0
                while True:
                    cursor, keys = self.redis_client.scan(
                        cursor=cursor,
                        match="bmad:chiseai:iterlog:story:*:incidents",
                        count=100,
                    )

                    for key in keys:
                        incidents = self.redis_client.lrange(key, 0, -1)
                        if incidents:
                            story_id = key.split(":")[4]
                            blockers["technical"].append(
                                {
                                    "id": story_id,
                                    "title": "Active incidents",
                                    "incident_count": len(incidents),
                                    "type": "incidents",
                                }
                            )

                    if cursor == 0:
                        break
            except Exception as e:
                if self.verbose:
                    print(f"⚠ Error querying incidents: {e}")

        return blockers

    def _get_risks(self) -> list[dict[str, Any]]:
        """Identify schedule and quality risks."""
        risks = []
        today = datetime.now()

        # Check for overdue stories
        for story in self.workflow_status.get("backlog", []):
            target_date = story.get("target_date") or story.get("deadline")
            if target_date:
                try:
                    deadline = datetime.strptime(target_date, "%Y-%m-%d")
                    if deadline < today and story.get("status") != "completed":
                        risks.append(
                            {
                                "type": "schedule",
                                "id": story.get("id"),
                                "title": story.get("title"),
                                "due": target_date,
                                "status": story.get("status"),
                                "impact": "Overdue",
                                "days_overdue": (today - deadline).days,
                            }
                        )
                except ValueError:
                    pass

        # Check for epic completion rates
        for epic in self.workflow_status.get("epics", []):
            completion = epic.get("completion_percentage", 100)
            target_date = epic.get("target_date") or epic.get("launch_date")

            if target_date and completion < 100:
                try:
                    deadline = datetime.strptime(target_date, "%Y-%m-%d")
                    days_remaining = (deadline - today).days

                    if completion < 50 and days_remaining < 14:
                        risks.append(
                            {
                                "type": "quality",
                                "id": epic.get("id"),
                                "title": epic.get("name"),
                                "completion": completion,
                                "days_remaining": days_remaining,
                                "impact": f"Low completion ({completion}%) with deadline approaching",
                            }
                        )
                except ValueError:
                    pass

        return risks

    def _get_metrics(self) -> dict[str, int]:
        """Calculate summary metrics."""
        completed = self._get_completed_yesterday()
        planned = self._get_planned_today()
        blockers = self._get_blockers()

        sum(len(stories) for stories in planned.values())
        total_blockers = sum(len(items) for items in blockers.values())

        return {
            "active_stories": len(self.workflow_status.get("backlog", [])),
            "in_progress": len(
                [
                    s
                    for s in self.workflow_status.get("backlog", [])
                    if s.get("status") == "in_progress"
                ]
            ),
            "blocked": total_blockers,
            "completed_24h": len(completed),
            "incidents_24h": len(blockers.get("technical", [])),
        }

    def _get_thinking_partner_status(self) -> dict[str, Any]:
        """Build Thinking Partner visibility snapshot from Redis + iterlogs."""
        status = {
            "mode": "OFF",
            "tp_sessions_24h": 0,
            "tp_sessions_expected_24h": 0,
            "tp_sessions_found_24h": 0,
            "tp_session_gap_count": 0,
            "insight_packets_24h": 0,
            "aria_decisions_24h": 0,
            "open_risk_items": 0,
            "decision_debt_open": 0,
            "last_proof_chain": "IP:none -> AD:none",
            "proof_coverage_percent": 0.0,
        }

        # Redis sessions (best effort)
        if self.redis_client:
            try:
                cursor = 0
                sessions = 0
                while True:
                    cursor, keys = self.redis_client.scan(
                        cursor=cursor,
                        match="bmad:chiseai:tp:session:*",
                        count=100,
                    )
                    sessions += len(keys)
                    if cursor == 0:
                        break
                status["tp_sessions_24h"] = sessions
            except Exception:
                pass

        # Iterlog-derived governance signal (best effort)
        try:
            iterlog_paths = sorted(Path("docs/tempmemories").glob("iterlog-*.md"))
            total = len(iterlog_paths)
            with_proof = 0
            latest_ip = "none"
            latest_ad = "none"
            expected_sessions: set[str] = set()
            found_sessions = 0

            for path in iterlog_paths:
                body = path.read_text(encoding="utf-8", errors="replace")
                if "Thinking Partner Proof:" in body:
                    with_proof += 1

                ip_matches = re.findall(
                    r"insight_packet_id:\s*([A-Za-z0-9._:-]+)", body
                )
                ad_matches = re.findall(r"aria_decision_id:\s*([A-Za-z0-9._:-]+)", body)
                if ip_matches:
                    latest_ip = ip_matches[-1]
                    status["insight_packets_24h"] += len(ip_matches)
                if ad_matches:
                    latest_ad = ad_matches[-1]
                    status["aria_decisions_24h"] += len(ad_matches)

                # Lightweight debt/risk signal from documented fields.
                status["open_risk_items"] += len(
                    re.findall(
                        r"urgency:\s*(medium|high|critical)", body, flags=re.IGNORECASE
                    )
                )
                status["decision_debt_open"] += len(re.findall(r"\bdebt_id:\b", body))
                for session_id in re.findall(
                    r"(?im)^\s*(?:[-*]\s*)?(?:\*\*|`)?tp_session_id(?:\*\*|`)?\s*:\s*([A-Za-z0-9._:-]+)\s*$",
                    body,
                ):
                    expected_sessions.add(session_id.strip())

            status["tp_sessions_expected_24h"] = len(expected_sessions)
            if self.redis_client and expected_sessions:
                for session_id in expected_sessions:
                    key = f"bmad:chiseai:tp:session:{session_id}"
                    try:
                        if self.redis_client.exists(key) == 1:
                            found_sessions += 1
                    except Exception:
                        continue
                status["tp_sessions_found_24h"] = found_sessions
            else:
                status["tp_sessions_found_24h"] = min(
                    status["tp_sessions_24h"], status["tp_sessions_expected_24h"]
                )
            status["tp_session_gap_count"] = max(
                status["tp_sessions_expected_24h"] - status["tp_sessions_found_24h"], 0
            )

            status["last_proof_chain"] = f"IP:{latest_ip} -> AD:{latest_ad}"
            if total > 0:
                status["proof_coverage_percent"] = round(
                    (with_proof / total) * 100.0, 1
                )
        except Exception:
            pass

        coverage = status["proof_coverage_percent"]
        if coverage >= 95.0 and status["tp_sessions_24h"] > 0:
            status["mode"] = "ACTIVE"
        elif coverage >= 70.0:
            status["mode"] = "DEGRADED"
        else:
            status["mode"] = "OFF"

        return status

    def generate_markdown_report(self) -> str:
        """Generate full markdown standup report."""
        completed = self._get_completed_yesterday()
        planned = self._get_planned_today()
        blockers = self._get_blockers()
        risks = self._get_risks()
        metrics = self._get_metrics()
        tp = self._get_thinking_partner_status()

        current_phase = self.workflow_status.get("current_phase", {})

        report = f"""# Daily Standup - {self.date}

**Generated**: {datetime.now().isoformat()}
**Phase**: {current_phase.get("phase", "Unknown")} ({current_phase.get("status", "Unknown")})

---

## Yesterday

### Completed ({len(completed)})
"""

        if completed:
            for story in completed[:10]:  # Limit to 10
                story_id = story.get("id", "Unknown")
                title = story.get("title", "Untitled")
                owner = story.get("owner", "TBD")
                merge_commit = story.get("merge_commit", story.get("commit_sha", "N/A"))

                report += f"""
- **{story_id}** {title} ({owner})
  - Merge: `{merge_commit[:7] if merge_commit != "N/A" else "N/A"}`
"""
        else:
            report += "\n*No completions in last 24-48 hours*\n"

        report += "\n---\n\n## Today\n\n### Planned Work\n"

        for priority in ["P0", "P1", "P2", "P3"]:
            stories = planned.get(priority, [])
            if stories:
                emoji = {"P0": "🔴", "P1": "🟠", "P2": "🟡", "P3": "🟢"}.get(
                    priority, "⚪"
                )
                report += f"\n#### {emoji} {priority} - {self._get_priority_label(priority)}\n"

                for story in stories[:5]:  # Limit to 5 per priority
                    story_id = story.get("id", "Unknown")
                    title = story.get("title", "Untitled")
                    owner = story.get("owner", "TBD")
                    status = story.get("status", "unknown")

                    report += f"""
- **{story_id}** {title} ({owner})
  - Status: {status}
"""

        report += "\n---\n\n## Blockers\n"

        total_blockers = sum(len(items) for items in blockers.values())
        if total_blockers > 0:
            for blocker_type, items in blockers.items():
                if items:
                    emoji = {
                        "technical": "🔧",
                        "dependencies": "🔗",
                        "resources": "📦",
                    }.get(blocker_type, "⚠️")
                    report += f"\n### {emoji} {blocker_type.title()} ({len(items)})\n"

                    for item in items[:5]:  # Limit to 5 per category
                        story_id = item.get("id", "Unknown")
                        title = item.get("title", "Untitled")

                        report += f"\n- **{story_id}** {title}\n"

                        if blocker_type == "dependencies":
                            deps = item.get("depends_on", [])
                            report += f"  - Waiting on: {', '.join(deps)}\n"
                        elif blocker_type == "resources":
                            report += f"  - Missing: {item.get('missing', 'Unknown resource')}\n"
        else:
            report += "\n*No active blockers* ✅\n"

        report += "\n---\n\n## Risks\n"

        if risks:
            for risk in risks[:10]:  # Limit to 10
                risk_type = risk.get("type", "unknown")
                emoji = {"schedule": "⏰", "quality": "⚠️"}.get(risk_type, "❗")
                story_id = risk.get("id", "Unknown")
                title = risk.get("title", "Untitled")
                impact = risk.get("impact", "Unknown impact")

                report += f"""
### {emoji} {risk_type.title()} Risk
- **{story_id}** {title}
  - Impact: {impact}
"""
                if risk_type == "schedule":
                    report += f"  - Days overdue: {risk.get('days_overdue', 'N/A')}\n"
                elif risk_type == "quality":
                    report += f"  - Completion: {risk.get('completion', 'N/A')}%\n"
                    report += (
                        f"  - Days remaining: {risk.get('days_remaining', 'N/A')}\n"
                    )
        else:
            report += "\n*No significant risks identified* ✅\n"

        report += f"""
---

## Metrics

- **Active Stories**: {metrics["active_stories"]}
- **In Progress**: {metrics["in_progress"]}
- **Blocked**: {metrics["blocked"]}
- **Completed (24h)**: {metrics["completed_24h"]}
- **Incidents (24h)**: {metrics["incidents_24h"]}

---

## Thinking Partner Status

- **Mode**: {tp["mode"]}
- **TP Sessions (24h)**: {tp["tp_sessions_24h"]}
- **TP Sessions Expected (Iterlogs)**: {tp["tp_sessions_expected_24h"]}
- **TP Sessions Found (Redis)**: {tp["tp_sessions_found_24h"]}
- **TP Session Gap**: {tp["tp_session_gap_count"]}
- **Insight Packets (24h)**: {tp["insight_packets_24h"]}
- **Aria Decisions (24h)**: {tp["aria_decisions_24h"]}
- **Open Risk Items**: {tp["open_risk_items"]}
- **Decision Debt Open**: {tp["decision_debt_open"]}
- **Proof Coverage**: {tp["proof_coverage_percent"]}%
- **Last Proof Chain**: {tp["last_proof_chain"]}

---

## Notes

- Report generated from workflow status and Redis iterlogs
- Next standup: {(datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")}

---

*Generated by chise-standup-generate*
*Command: .opencode/command/chise-standup-generate.md*
"""

        return report

    def generate_json_report(self) -> dict[str, Any]:
        """Generate JSON format report for automation."""
        return {
            "date": self.date,
            "generated_at": datetime.now().isoformat(),
            "phase": self.workflow_status.get("current_phase", {}),
            "summary": self._get_metrics(),
            "thinking_partner": self._get_thinking_partner_status(),
            "yesterday": {"completed": self._get_completed_yesterday()},
            "today": {"planned": self._get_planned_today()},
            "blockers": self._get_blockers(),
            "risks": self._get_risks(),
        }

    def _get_priority_label(self, priority: str) -> str:
        """Get human-readable priority label."""
        labels = {
            "P0": "Critical",
            "P1": "High Priority",
            "P2": "Medium Priority",
            "P3": "Low Priority",
        }
        return labels.get(priority, "Unknown")

    def save_report(
        self, report: str, output_path: str | None = None, format: str = "markdown"
    ) -> Path:
        """Save report to file."""
        if output_path:
            report_path = Path(output_path)
        else:
            # Use appropriate extension based on format
            ext = "json" if format == "json" else "md"
            report_path = Path(f"docs/tempmemories/standup-{self.date}.{ext}")

        # Ensure directory exists
        report_path.parent.mkdir(parents=True, exist_ok=True)

        # Write report
        with open(report_path, "w") as f:
            f.write(report)

        if self.verbose:
            print(f"✓ Report saved to: {report_path}")

        return report_path

    def log_to_redis(self, metrics: dict[str, int]):
        """Log standup metadata to Redis."""
        if not self.redis_client:
            return

        try:
            key = f"bmad:chiseai:standup:{self.date}"

            self.redis_client.hset(
                key,
                mapping={
                    "generated_at": datetime.now().isoformat(),
                    "report_path": f"docs/tempmemories/standup-{self.date}.md",
                    "active_stories": str(metrics["active_stories"]),
                    "in_progress": str(metrics["in_progress"]),
                    "blocked": str(metrics["blocked"]),
                    "completed_24h": str(metrics["completed_24h"]),
                },
            )

            # Set 7 day TTL
            self.redis_client.expire(key, 604800)

            if self.verbose:
                print(f"✓ Logged to Redis: {key}")

        except Exception as e:
            if self.verbose:
                print(f"⚠ Failed to log to Redis: {e}")

    def post_to_discord(
        self, channel_id: str, report_path: Path, metrics: dict[str, int]
    ) -> bool:
        """Post summary to Discord."""
        try:
            # Import Discord posting utility
            discord_script = Path("scripts/discord/post_message.py")

            if not discord_script.exists():
                if self.verbose:
                    print("⚠ Discord script not found: scripts/discord/post_message.py")
                return False

            tp = self._get_thinking_partner_status()
            # Format compact message
            message = f"""📊 **Daily Standup - {self.date}**

✅ **Yesterday**: {metrics["completed_24h"]} completed
🔄 **Today**: {metrics["in_progress"]} in progress
🚫 **Blockers**: {metrics["blocked"]} active
⚠️ **Risks**: Check full report
🤝 **Thinking Partner**: {tp["mode"]} (Proof {tp["proof_coverage_percent"]}%, Gap {tp["tp_session_gap_count"]})

Full report: `{report_path}`
"""

            # Post via subprocess
            result = subprocess.run(
                [
                    "python3",
                    str(discord_script),
                    "--channel",
                    channel_id,
                    "--message",
                    message,
                ],
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                if self.verbose:
                    print(f"✓ Posted to Discord channel: {channel_id}")
                return True
            else:
                if self.verbose:
                    print(f"⚠ Discord post failed: {result.stderr}")
                return False

        except Exception as e:
            if self.verbose:
                print(f"⚠ Discord post error: {e}")
            return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Generate daily standup report")

    parser.add_argument(
        "--date", help="Report date (YYYY-MM-DD, default: today)", default=None
    )

    parser.add_argument(
        "--post-discord", help="Post summary to Discord", action="store_true"
    )

    parser.add_argument(
        "--channel-id",
        help="Discord channel ID (or use DISCORD_STANDUP_CHANNEL env var)",
        default=os.getenv("DISCORD_STANDUP_CHANNEL"),
    )

    parser.add_argument(
        "--include-completed",
        type=int,
        default=7,
        help="Days of completed work to include (default: 7)",
    )

    parser.add_argument(
        "--format",
        choices=["markdown", "json", "text"],
        default="markdown",
        help="Output format (default: markdown)",
    )

    parser.add_argument("--output", help="Custom output path", default=None)

    parser.add_argument("--verbose", help="Enable verbose output", action="store_true")

    parser.add_argument(
        "--redis-host", default="localhost", help="Redis host (default: localhost)"
    )

    parser.add_argument(
        "--redis-port", type=int, default=6380, help="Redis port (default: 6380)"
    )

    args = parser.parse_args()

    try:
        # Initialize generator
        generator = StandupGenerator(
            date=args.date,
            redis_host=args.redis_host,
            redis_port=args.redis_port,
            verbose=args.verbose,
        )

        # Generate report
        if args.format == "json":
            report_data = generator.generate_json_report()
            report = json.dumps(report_data, indent=2)
        else:
            report = generator.generate_markdown_report()

        # Save report
        report_path = generator.save_report(report, args.output, args.format)

        # Log to Redis
        metrics = generator._get_metrics()
        generator.log_to_redis(metrics)

        # Print report
        if args.format == "markdown":
            print("\n" + "=" * 80)
            print(report)
            print("=" * 80 + "\n")

        # Post to Discord if requested
        if args.post_discord and args.channel_id:
            success = generator.post_to_discord(args.channel_id, report_path, metrics)
            if not success:
                print("⚠ Discord post failed, but report was saved locally")

        print(f"✓ Standup report generated: {report_path}")
        return 0

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error generating standup report: {e}", file=sys.stderr)
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
