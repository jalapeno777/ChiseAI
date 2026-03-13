#!/usr/bin/env python3
"""Dashboard CLI for querying dashboard data.

Provides command-line interface for querying dashboard data
without starting the full server.

Usage:
    python3 scripts/dashboard/dashboard_cli.py health
    python3 scripts/dashboard/dashboard_cli.py state
    python3 scripts/dashboard/dashboard_cli.py panels circuit-breakers
    python3 scripts/dashboard/dashboard_cli.py charts incident-trend

For ST-CONTROL-003: Control Plane Dashboard
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def get_health(api_url: str) -> dict:
    """Get health status."""
    import aiohttp

    async with aiohttp.ClientSession() as session:
        async with session.get(f"{api_url}/health") as response:
            if response.status == 200:
                return await response.json()
            else:
                return {"error": f"HTTP {response.status}"}


async def get_state(api_url: str) -> dict:
    """Get full dashboard state."""
    import aiohttp

    async with aiohttp.ClientSession() as session:
        async with session.get(f"{api_url}/state") as response:
            if response.status == 200:
                return await response.json()
            else:
                return {"error": f"HTTP {response.status}"}


async def get_panel(api_url: str, panel_name: str, **kwargs) -> dict:
    """Get panel data."""
    import aiohttp

    url = f"{api_url}/panels/{panel_name}"
    params = {k: v for k, v in kwargs.items() if v is not None}

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as response:
            if response.status == 200:
                return await response.json()
            else:
                return {"error": f"HTTP {response.status}"}


async def get_chart(api_url: str, chart_name: str, **kwargs) -> dict:
    """Get chart data."""
    import aiohttp

    url = f"{api_url}/charts/{chart_name}"
    params = {k: v for k, v in kwargs.items() if v is not None}

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as response:
            if response.status == 200:
                return await response.json()
            else:
                return {"error": f"HTTP {response.status}"}


async def search_incidents(api_url: str, query: str, **kwargs) -> dict:
    """Search incidents."""
    import aiohttp

    url = f"{api_url}/incidents/search"
    params = {"q": query}
    params.update({k: v for k, v in kwargs.items() if v is not None})

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as response:
            if response.status == 200:
                return await response.json()
            else:
                return {"error": f"HTTP {response.status}"}


def format_output(data: dict, format_type: str) -> str:
    """Format output for display."""
    if format_type == "json":
        return json.dumps(data, indent=2)
    elif format_type == "compact":
        return json.dumps(data)
    else:
        # Pretty print
        return json.dumps(data, indent=2)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="ChiseAI Dashboard CLI",
    )
    parser.add_argument(
        "--api-url",
        default="http://localhost:8080/api/v1/dashboard",
        help="Dashboard API URL",
    )
    parser.add_argument(
        "--format",
        choices=["json", "compact"],
        default="json",
        help="Output format",
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Health command
    subparsers.add_parser("health", help="Get API health status")

    # State command
    subparsers.add_parser("state", help="Get full dashboard state")

    # Panels command
    panels_parser = subparsers.add_parser("panels", help="Get panel data")
    panels_parser.add_argument(
        "panel",
        choices=[
            "circuit-breakers",
            "incidents",
            "self-healing",
            "rollbacks",
            "system-health",
        ],
        help="Panel name",
    )
    panels_parser.add_argument("--group", help="Filter by group (for circuit-breakers)")
    panels_parser.add_argument("--status", help="Filter by status (for incidents)")
    panels_parser.add_argument("--severity", help="Filter by severity (for incidents)")
    panels_parser.add_argument("--limit", type=int, default=50, help="Limit results")

    # Charts command
    charts_parser = subparsers.add_parser("charts", help="Get chart data")
    charts_parser.add_argument(
        "chart",
        choices=[
            "incident-trend",
            "health-gauge",
            "cb-status",
            "severity-distribution",
        ],
        help="Chart name",
    )
    charts_parser.add_argument(
        "--hours", type=int, default=24, help="Hours to look back"
    )
    charts_parser.add_argument(
        "--resolution",
        choices=["hour", "day"],
        default="hour",
        help="Time resolution",
    )

    # Search command
    search_parser = subparsers.add_parser("search", help="Search incidents")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument("--status", help="Filter by status")
    search_parser.add_argument("--severity", help="Filter by severity")
    search_parser.add_argument("--limit", type=int, default=50, help="Limit results")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    async def run_command():
        if args.command == "health":
            result = await get_health(args.api_url)
        elif args.command == "state":
            result = await get_state(args.api_url)
        elif args.command == "panels":
            panel_map = {
                "circuit-breakers": "circuit-breakers",
                "incidents": "incidents",
                "self-healing": "self-healing",
                "rollbacks": "rollbacks",
                "system-health": "system-health",
            }
            result = await get_panel(
                args.api_url,
                panel_map[args.panel],
                group=getattr(args, "group", None),
                status=getattr(args, "status", None),
                severity=getattr(args, "severity", None),
                limit=getattr(args, "limit", 50),
            )
        elif args.command == "charts":
            chart_map = {
                "incident-trend": "incident-trend",
                "health-gauge": "health-gauge",
                "cb-status": "cb-status",
                "severity-distribution": "severity-distribution",
            }
            result = await get_chart(
                args.api_url,
                chart_map[args.chart],
                hours=getattr(args, "hours", 24),
                resolution=getattr(args, "resolution", "hour"),
            )
        elif args.command == "search":
            result = await search_incidents(
                args.api_url,
                args.query,
                status=getattr(args, "status", None),
                severity=getattr(args, "severity", None),
                limit=getattr(args, "limit", 50),
            )
        else:
            result = {"error": "Unknown command"}

        print(format_output(result, args.format))

    try:
        asyncio.run(run_command())
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
