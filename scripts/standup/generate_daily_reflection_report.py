#!/usr/bin/env python3
"""
Daily Reflection Quality Report Generator

Generates daily reflection-quality metrics for 7-day stabilization cadence:
- KPI snapshot (reflection completion rate, metacog calibration)
- Trend deltas (7-day moving averages, improvement trajectories)
- Incidents (active blockers, repeated issues)
- Blockers (scope conflicts, validation failures)

Usage:
    python3 scripts/standup/generate_daily_reflection_report.py
    python3 scripts/standup/generate_daily_reflection_report.py --post-discord
    python3 scripts/standup/generate_daily_reflection_report.py --day 3/7

Story: ST-DAILY-REFLECTION-001
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    import redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    print("Warning: redis package not installed. Redis queries will be skipped.")

try:
    import requests

    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    print("Warning: requests package not installed. Discord posting will be skipped.")


class DailyReflectionReportGenerator:
    """Generate daily reflection-quality metrics reports."""

    def __init__(
        self,
        day: Optional[int] = None,
        total_days: int = 7,
        redis_host: str = "localhost",
        redis_port: int = 6380,
        redis_db: int = 0,
        verbose: bool = False,
    ):
        self.date = datetime.now().strftime("%Y-%m-%d")
        self.timestamp = datetime.now().isoformat()
        self.total_days = total_days
        self.verbose = verbose
        self.redis_client = None

        # Initialize Redis connection FIRST
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

        # NOW calculate day (after redis_client is initialized)
        self.day = day or self._calculate_current_day()

        # Load configuration
        self.discord_webhook_url = os.getenv("DISCORD_WEBHOOK_URL") or os.getenv(
            "CHISE_DISCORD_WEBHOOK_URL"
        )
        self.discord_bot_token = os.getenv("DISCORD_BOT_TOKEN")
        self.discord_channel_id = os.getenv(
            "DISCORD_DEVELOPMENT_CHANNEL_ID", "1444447985378398459"
        )

    def _calculate_current_day(self) -> int:
        """Calculate current day of 7-day cadence."""
        # Check Redis for cadence start date
        if self.redis_client:
            start_date_str = self.redis_client.get(
                "bmad:chiseai:reflection_cadence:start_date"
            )
            if start_date_str:
                start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
                delta = (datetime.now() - start_date).days + 1
                return min(max(delta, 1), self.total_days)

        # Default to day 1 if no start date found
        return 1

    def _get_kpi_snapshot(self) -> Dict[str, Any]:
        """Get current KPI snapshot from Redis."""
        kpis = {
            "reflection_completion_rate": 0.0,
            "metacog_calibration_score": 0.0,
            "active_stories": 0,
            "completed_iterations": 0,
            "avg_iteration_duration_hours": 0.0,
        }

        if not self.redis_client:
            return kpis

        try:
            # Get reflection metrics
            reflection_metrics = self.redis_client.hgetall(
                "bmad:chiseai:metrics:reflection"
            )
            if reflection_metrics:
                kpis["reflection_completion_rate"] = float(
                    reflection_metrics.get("completion_rate", 0.0)
                )
                kpis["metacog_calibration_score"] = float(
                    reflection_metrics.get("calibration_score", 0.0)
                )

            # Count active stories
            cursor = 0
            story_count = 0
            while True:
                cursor, keys = self.redis_client.scan(
                    cursor=cursor, match="bmad:chiseai:iterlog:story:*", count=100
                )
                story_keys = [k for k in keys if ":incidents" not in k]
                story_count += len(story_keys)
                if cursor == 0:
                    break

            kpis["active_stories"] = story_count

            # Get iteration metrics
            iter_metrics = self.redis_client.hgetall("bmad:chiseai:metrics:iterations")
            if iter_metrics:
                kpis["completed_iterations"] = int(iter_metrics.get("completed", 0))
                kpis["avg_iteration_duration_hours"] = float(
                    iter_metrics.get("avg_duration_hours", 0.0)
                )

        except Exception as e:
            if self.verbose:
                print(f"⚠ Error fetching KPI snapshot: {e}")

        return kpis

    def _get_trend_deltas(self) -> Dict[str, Any]:
        """Calculate 7-day trend deltas."""
        trends = {
            "reflection_rate_delta": 0.0,
            "calibration_improvement": 0.0,
            "velocity_trend": "stable",
            "blocker_trend": "stable",
        }

        if not self.redis_client:
            return trends

        try:
            # Get historical metrics (last 7 days)
            historical_data = []
            for i in range(7):
                date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
                metrics = self.redis_client.hgetall(
                    f"bmad:chiseai:metrics:reflection:{date}"
                )
                if metrics:
                    historical_data.append(
                        {
                            "date": date,
                            "completion_rate": float(
                                metrics.get("completion_rate", 0.0)
                            ),
                            "calibration_score": float(
                                metrics.get("calibration_score", 0.0)
                            ),
                        }
                    )

            if len(historical_data) >= 2:
                # Calculate deltas
                latest = historical_data[0]
                previous = historical_data[-1]

                trends["reflection_rate_delta"] = (
                    latest["completion_rate"] - previous["completion_rate"]
                )
                trends["calibration_improvement"] = (
                    latest["calibration_score"] - previous["calibration_score"]
                )

                # Determine trends
                if trends["reflection_rate_delta"] > 0.05:
                    trends["velocity_trend"] = "improving"
                elif trends["reflection_rate_delta"] < -0.05:
                    trends["velocity_trend"] = "declining"

        except Exception as e:
            if self.verbose:
                print(f"⚠ Error calculating trend deltas: {e}")

        return trends

    def _get_incidents(self) -> List[Dict[str, Any]]:
        """Get active incidents from Redis."""
        incidents = []

        if not self.redis_client:
            return incidents

        try:
            # Scan for incident keys
            cursor = 0
            while True:
                cursor, keys = self.redis_client.scan(
                    cursor=cursor, match="bmad:chiseai:incidents:*", count=100
                )

                for key in keys:
                    incident_data = self.redis_client.hgetall(key)
                    if incident_data:
                        # Only include active incidents from last 24 hours
                        created_at = incident_data.get("created_at", "")
                        if created_at:
                            incident_time = datetime.fromisoformat(created_at)
                            if (datetime.now() - incident_time) < timedelta(hours=24):
                                incidents.append(
                                    {
                                        "id": key.split(":")[-1],
                                        "type": incident_data.get("type", "unknown"),
                                        "severity": incident_data.get(
                                            "severity", "medium"
                                        ),
                                        "story_id": incident_data.get(
                                            "story_id", "N/A"
                                        ),
                                        "description": incident_data.get(
                                            "description", ""
                                        )[:100],
                                        "created_at": created_at,
                                    }
                                )

                if cursor == 0:
                    break

        except Exception as e:
            if self.verbose:
                print(f"⚠ Error fetching incidents: {e}")

        return incidents

    def _get_blockers(self) -> List[Dict[str, Any]]:
        """Get active blockers from workflow status and Redis."""
        blockers = []

        # Load workflow status
        workflow_path = Path("docs/bmm-workflow-status.yaml")
        if workflow_path.exists():
            try:
                with open(workflow_path, "r") as f:
                    workflow_status = yaml.safe_load(f)

                # Check in_progress stories for blockers
                in_progress = workflow_status.get("in_progress", [])
                if isinstance(in_progress, list):
                    for story in in_progress:
                        if isinstance(story, dict):
                            if story.get("status") == "blocked":
                                blockers.append(
                                    {
                                        "story_id": story.get("id", "unknown"),
                                        "type": "workflow_blocked",
                                        "description": story.get(
                                            "blocker_reason",
                                            story.get(
                                                "description", "No reason provided"
                                            ),
                                        )[:100],
                                        "since": story.get("blocked_since", "N/A"),
                                    }
                                )

                # Check planned stories for blockers
                planned = workflow_status.get("planned", [])
                if isinstance(planned, list):
                    for story in planned:
                        if isinstance(story, dict):
                            if story.get("status") == "blocked":
                                blockers.append(
                                    {
                                        "story_id": story.get("id", "unknown"),
                                        "type": "workflow_blocked",
                                        "description": story.get(
                                            "blocker_reason",
                                            story.get(
                                                "description", "No reason provided"
                                            ),
                                        )[:100],
                                        "since": story.get("blocked_since", "N/A"),
                                    }
                                )
            except Exception as e:
                if self.verbose:
                    print(f"⚠ Error loading workflow status: {e}")

        # Get scope conflicts from Redis
        if self.redis_client:
            try:
                ownership_conflicts = self.redis_client.hgetall(
                    "bmad:chiseai:ownership_conflicts"
                )
                if ownership_conflicts:
                    for path, conflict_data in ownership_conflicts.items():
                        blockers.append(
                            {
                                "story_id": "SCOPE-CONFLICT",
                                "type": "scope_conflict",
                                "description": f"Ownership conflict on {path}",
                                "details": conflict_data,
                            }
                        )
            except Exception as e:
                if self.verbose:
                    print(f"⚠ Error fetching ownership conflicts: {e}")

        return blockers

    def _get_git_activity(self) -> Dict[str, Any]:
        """Get recent git activity."""
        activity = {
            "commits_today": 0,
            "merges_today": 0,
            "active_branches": 0,
        }

        try:
            # Count commits today
            since = datetime.now().strftime("%Y-%m-%d 00:00:00")
            result = subprocess.run(
                ["git", "log", "--oneline", f"--since={since}", "--author=.*"],
                capture_output=True,
                text=True,
                cwd="/home/tacopants/projects/ChiseAI",
            )
            activity["commits_today"] = len(
                [l for l in result.stdout.strip().split("\n") if l]
            )

            # Count merges today
            result = subprocess.run(
                ["git", "log", "--oneline", f"--since={since}", "--merges"],
                capture_output=True,
                text=True,
                cwd="/home/tacopants/projects/ChiseAI",
            )
            activity["merges_today"] = len(
                [l for l in result.stdout.strip().split("\n") if l]
            )

            # Count active branches
            result = subprocess.run(
                ["git", "branch", "-r", "--list", "origin/feature/*"],
                capture_output=True,
                text=True,
                cwd="/home/tacopants/projects/ChiseAI",
            )
            activity["active_branches"] = len(
                [l for l in result.stdout.strip().split("\n") if l]
            )

        except Exception as e:
            if self.verbose:
                print(f"⚠ Error fetching git activity: {e}")

        return activity

    def generate_report(self) -> Dict[str, Any]:
        """Generate the daily reflection report."""
        if self.verbose:
            print(
                f"📊 Generating Daily Reflection Report - Day {self.day}/{self.total_days}"
            )
            print(f"Date: {self.date}")
            print(f"Timestamp: {self.timestamp}")

        report = {
            "metadata": {
                "report_type": "daily_reflection_quality",
                "date": self.date,
                "timestamp": self.timestamp,
                "day": f"{self.day}/{self.total_days}",
                "cadence": "7-day-stabilization",
            },
            "kpi_snapshot": self._get_kpi_snapshot(),
            "trend_deltas": self._get_trend_deltas(),
            "incidents": self._get_incidents(),
            "blockers": self._get_blockers(),
            "git_activity": self._get_git_activity(),
            "summary": {
                "health_status": self._calculate_health_status(),
                "recommendations": self._generate_recommendations(),
            },
        }

        if self.verbose:
            print("✓ Report generated successfully")

        return report

    def _calculate_health_status(self) -> str:
        """Calculate overall health status."""
        kpis = self._get_kpi_snapshot()
        incidents = self._get_incidents()
        blockers = self._get_blockers()

        # Critical conditions
        if kpis["reflection_completion_rate"] < 0.5:
            return "critical"

        if len(incidents) > 3 or len(blockers) > 2:
            return "at_risk"

        # Good conditions
        if kpis["reflection_completion_rate"] > 0.8 and len(blockers) == 0:
            return "healthy"

        return "stable"

    def _generate_recommendations(self) -> List[str]:
        """Generate actionable recommendations."""
        recommendations = []
        kpis = self._get_kpi_snapshot()
        trends = self._get_trend_deltas()
        incidents = self._get_incidents()
        blockers = self._get_blockers()

        # Reflection rate recommendations
        if kpis["reflection_completion_rate"] < 0.7:
            recommendations.append(
                "📈 Focus on completing reflection cycles before starting new iterations"
            )

        # Calibration recommendations
        if kpis["metacog_calibration_score"] < 0.6:
            recommendations.append(
                "🎯 Review metacognitive predictions and improve confidence calibration"
            )

        # Incident recommendations
        if len(incidents) > 0:
            recommendations.append(
                f"🚨 Address {len(incidents)} active incident(s) within 24 hours"
            )

        # Blocker recommendations
        if len(blockers) > 0:
            recommendations.append(
                f"🔒 Resolve {len(blockers)} blocker(s) to unblock progress"
            )

        # Trend recommendations
        if trends["velocity_trend"] == "declining":
            recommendations.append(
                "⚠️ Velocity declining - review iteration scope and resource allocation"
            )

        return recommendations

    def format_report_markdown(self, report: Dict[str, Any]) -> str:
        """Format report as markdown for Discord."""
        lines = []

        # Header
        lines.append(f"# 📊 Daily Reflection Report - Day {report['metadata']['day']}")
        lines.append(f"**Date:** {report['metadata']['date']}")
        lines.append(f"**Cadence:** {report['metadata']['cadence']}")
        lines.append("")

        # Health Status
        health = report["summary"]["health_status"]
        health_emoji = {
            "healthy": "✅",
            "stable": "➡️",
            "at_risk": "⚠️",
            "critical": "🚨",
        }.get(health, "❓")
        lines.append(f"## {health_emoji} Health Status: **{health.upper()}**")
        lines.append("")

        # KPI Snapshot
        lines.append("## 📈 KPI Snapshot")
        kpis = report["kpi_snapshot"]
        lines.append(
            f"- **Reflection Completion Rate:** {kpis['reflection_completion_rate']:.1%}"
        )
        lines.append(
            f"- **Metacog Calibration Score:** {kpis['metacog_calibration_score']:.1%}"
        )
        lines.append(f"- **Active Stories:** {kpis['active_stories']}")
        lines.append(f"- **Completed Iterations:** {kpis['completed_iterations']}")
        lines.append(
            f"- **Avg Iteration Duration:** {kpis['avg_iteration_duration_hours']:.1f}h"
        )
        lines.append("")

        # Trend Deltas
        lines.append("## 📉 Trend Deltas (7-day)")
        trends = report["trend_deltas"]
        rate_delta = trends["reflection_rate_delta"]
        calib_delta = trends["calibration_improvement"]

        rate_emoji = "📈" if rate_delta > 0 else "📉" if rate_delta < 0 else "➡️"
        calib_emoji = "📈" if calib_delta > 0 else "📉" if calib_delta < 0 else "➡️"

        lines.append(f"- {rate_emoji} **Reflection Rate Delta:** {rate_delta:+.1%}")
        lines.append(f"- {calib_emoji} **Calibration Improvement:** {calib_delta:+.1%}")
        lines.append(
            f"- **Velocity Trend:** {trends['velocity_trend'].replace('_', ' ').title()}"
        )
        lines.append(
            f"- **Blocker Trend:** {trends['blocker_trend'].replace('_', ' ').title()}"
        )
        lines.append("")

        # Incidents
        incidents = report["incidents"]
        lines.append(f"## 🚨 Incidents ({len(incidents)})")
        if incidents:
            for incident in incidents[:5]:  # Limit to 5 for readability
                lines.append(
                    f"- **{incident['severity'].upper()}**: {incident['type']} (Story: {incident['story_id']})"
                )
                lines.append(f"  - {incident['description']}")
        else:
            lines.append("✅ No active incidents in last 24 hours")
        lines.append("")

        # Blockers
        blockers = report["blockers"]
        lines.append(f"## 🔒 Blockers ({len(blockers)})")
        if blockers:
            for blocker in blockers[:5]:  # Limit to 5
                lines.append(f"- **{blocker['type']}**: Story {blocker['story_id']}")
                lines.append(f"  - {blocker['description']}")
        else:
            lines.append("✅ No active blockers")
        lines.append("")

        # Git Activity
        lines.append("## 🔀 Git Activity (Today)")
        git = report["git_activity"]
        lines.append(f"- **Commits:** {git['commits_today']}")
        lines.append(f"- **Merges:** {git['merges_today']}")
        lines.append(f"- **Active Branches:** {git['active_branches']}")
        lines.append("")

        # Recommendations
        recommendations = report["summary"]["recommendations"]
        lines.append("## 💡 Recommendations")
        if recommendations:
            for rec in recommendations:
                lines.append(f"- {rec}")
        else:
            lines.append("✅ System healthy - maintain current practices")
        lines.append("")

        # Footer
        lines.append("---")
        lines.append(f"🤖 Generated by ChiseAI Daily Reflection Reporter")
        lines.append(f"📅 {report['metadata']['timestamp']}")

        return "\n".join(lines)

    def post_to_discord(self, report: Dict[str, Any]) -> bool:
        """Post report to Discord channel."""
        if not REQUESTS_AVAILABLE:
            print("❌ Cannot post to Discord: requests package not available")
            return False

        if not self.discord_webhook_url and not self.discord_bot_token:
            print("❌ Cannot post to Discord: no webhook URL or bot token configured")
            return False

        markdown_content = self.format_report_markdown(report)

        try:
            # Use webhook if available
            if self.discord_webhook_url:
                payload = {
                    "content": markdown_content[:2000],  # Discord limit
                    "username": "ChiseAI Daily Reflection",
                }

                response = requests.post(
                    self.discord_webhook_url, json=payload, timeout=10
                )

                if response.status_code == 204 or response.status_code == 200:
                    if self.verbose:
                        print("✓ Successfully posted to Discord via webhook")
                    return True
                else:
                    print(
                        f"❌ Discord webhook failed: {response.status_code} - {response.text}"
                    )
                    return False

            # Use bot API if webhook not available
            elif self.discord_bot_token and self.discord_channel_id:
                url = f"https://discord.com/api/v10/channels/{self.discord_channel_id}/messages"
                headers = {
                    "Authorization": f"Bot {self.discord_bot_token}",
                    "Content-Type": "application/json",
                }
                payload = {"content": markdown_content[:2000]}

                response = requests.post(url, headers=headers, json=payload, timeout=10)

                if response.status_code == 200:
                    if self.verbose:
                        print("✓ Successfully posted to Discord via bot API")
                    return True
                else:
                    print(
                        f"❌ Discord bot API failed: {response.status_code} - {response.text}"
                    )
                    return False

        except Exception as e:
            print(f"❌ Error posting to Discord: {e}")
            return False

        return False

    def save_report_to_redis(self, report: Dict[str, Any]) -> bool:
        """Save report to Redis for historical tracking."""
        if not self.redis_client:
            return False

        try:
            # Save to daily key with 30-day expiration
            key = f"bmad:chiseai:daily_reflection_report:{self.date}"
            self.redis_client.hset(
                key,
                mapping={
                    "report": json.dumps(report),
                    "timestamp": self.timestamp,
                    "day": self.day,
                },
            )
            self.redis_client.expire(key, 86400 * 30)  # 30 days

            if self.verbose:
                print(f"✓ Report saved to Redis: {key}")
            return True

        except Exception as e:
            if self.verbose:
                print(f"⚠ Error saving report to Redis: {e}")
            return False


def main():
    parser = argparse.ArgumentParser(
        description="Generate daily reflection quality report"
    )
    parser.add_argument(
        "--day", type=int, help="Day number in 7-day cadence (default: auto-calculate)"
    )
    parser.add_argument(
        "--total-days", type=int, default=7, help="Total days in cadence (default: 7)"
    )
    parser.add_argument(
        "--post-discord", action="store_true", help="Post report to Discord channel"
    )
    parser.add_argument(
        "--redis-host", default="localhost", help="Redis host (default: localhost)"
    )
    parser.add_argument(
        "--redis-port", type=int, default=6380, help="Redis port (default: 6380)"
    )
    parser.add_argument("--output", help="Output file path for JSON report")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")

    args = parser.parse_args()

    # Determine Redis host (check if in Docker)
    redis_host = args.redis_host
    if os.path.exists("/.dockerenv"):
        # Check if we're on the chiseai network
        # If not, use host.docker.internal to reach host services
        try:
            import subprocess

            result = subprocess.run(
                ["ip", "addr", "show"], capture_output=True, text=True, timeout=2
            )
            # If we're on chiseai network (172.27.x.x), use chiseai-redis
            if "172.27." in result.stdout:
                redis_host = "chiseai-redis"
            else:
                # Otherwise, use host.docker.internal to reach host
                redis_host = "host.docker.internal"
        except Exception:
            # Fallback to host.docker.internal
            redis_host = "host.docker.internal"

    # Generate report
    generator = DailyReflectionReportGenerator(
        day=args.day,
        total_days=args.total_days,
        redis_host=redis_host,
        redis_port=args.redis_port,
        verbose=args.verbose,
    )

    report = generator.generate_report()

    # Save to Redis
    generator.save_report_to_redis(report)

    # Save to file if requested
    if args.output:
        with open(args.output, "w") as f:
            json.dump(report, f, indent=2)
        if args.verbose:
            print(f"✓ Report saved to {args.output}")

    # Post to Discord if requested
    if args.post_discord:
        success = generator.post_to_discord(report)
        if not success:
            sys.exit(1)

    # Print markdown to stdout
    print("\n" + generator.format_report_markdown(report))

    return 0


if __name__ == "__main__":
    sys.exit(main())
