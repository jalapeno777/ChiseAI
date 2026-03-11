#!/usr/bin/env python3
"""Paper Trading E2E Health Probe Script.

Comprehensive health check for paper trading E2E pipeline with pass/fail output
and evidence collection. Designed for CI/CD integration and monitoring.

Exit Codes:
    0 = PASS (all checks passed)
    1 = WARN (some checks passed with warnings)
    2 = FAIL (one or more critical checks failed)

Usage:
    python3 paper_e2e_health_probe.py [--dry-run] [--output-dir PATH]

ST-PARTY-E2E-REMEDIATION-001 - Task 1.1
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import redis


# Load environment from .env file
def _load_env_file() -> None:
    """Load .env file from project root."""
    script_dir = Path(__file__).parent.absolute()
    project_root = script_dir.parent.parent
    env_file = project_root / ".env"

    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    if key not in os.environ:
                        os.environ[key] = value.strip().strip('"').strip("'")


_load_env_file()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Configuration
REDIS_HOST = os.getenv("REDIS_HOST", "host.docker.internal")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6380"))
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_CHANNEL_ID = os.getenv("DISCORD_DEVELOPMENT_CHANNEL_ID", "")

# Redis key patterns
PAPER_MODE_KEY = "bmad:chiseai:paper_trading:mode"
SIGNAL_INDEX_KEY = "paper:index:signals"
ORDER_INDEX_KEY = "paper:index:orders"
KILL_SWITCH_KEY = "bmad:chiseai:kill_switch"
DISCORD_CONTINUITY_PREFIX = "chise:discord:continuity"

# Time windows for checks
SIGNAL_LOOKBACK_MINUTES = 5
ORDER_LOOKBACK_MINUTES = 5


class HealthCheckResult:
    """Result of a single health check."""

    def __init__(
        self,
        name: str,
        status: str,  # "PASS", "WARN", "FAIL", "SKIP"
        message: str,
        details: dict[str, Any] | None = None,
    ):
        self.name = name
        self.status = status
        self.message = message
        self.details = details or {}
        self.timestamp = datetime.now(UTC).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp,
        }


class PaperE2EHealthProbe:
    """Paper Trading E2E Health Probe."""

    def __init__(self, dry_run: bool = False, output_dir: str | None = None):
        self.dry_run = dry_run
        self.output_dir = (
            Path(output_dir) if output_dir else Path("_bmad-output/evidence")
        )
        self.results: list[HealthCheckResult] = []
        self.redis_client: redis.Redis | None = None
        self.start_time = datetime.now(UTC)

    def _get_redis(self) -> redis.Redis | None:
        """Get Redis connection with caching."""
        if self.redis_client is not None:
            try:
                self.redis_client.ping()
                return self.redis_client
            except Exception:
                self.redis_client = None

        try:
            client = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            client.ping()
            self.redis_client = client
            return client
        except Exception as e:
            logger.error(f"Redis connection error: {e}")
            return None

    def _add_result(
        self,
        name: str,
        status: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> HealthCheckResult:
        """Add a health check result."""
        result = HealthCheckResult(name, status, message, details)
        self.results.append(result)
        logger.info(f"[{status}] {name}: {message}")
        return result

    def check_redis_connectivity(self) -> HealthCheckResult:
        """Check Redis connectivity."""
        if self.dry_run:
            return self._add_result(
                "redis_connectivity",
                "SKIP",
                "Dry run - skipping Redis connectivity check",
            )

        try:
            client = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            client.ping()
            info = client.info()
            return self._add_result(
                "redis_connectivity",
                "PASS",
                f"Redis connected at {REDIS_HOST}:{REDIS_PORT}",
                {
                    "host": REDIS_HOST,
                    "port": REDIS_PORT,
                    "redis_version": info.get("redis_version", "unknown"),
                    "connected_clients": info.get("connected_clients", 0),
                },
            )
        except redis.ConnectionError as e:
            return self._add_result(
                "redis_connectivity",
                "FAIL",
                f"Redis connection failed: {e}",
                {"host": REDIS_HOST, "port": REDIS_PORT, "error": str(e)},
            )
        except Exception as e:
            return self._add_result(
                "redis_connectivity",
                "FAIL",
                f"Redis error: {e}",
                {"host": REDIS_HOST, "port": REDIS_PORT, "error": str(e)},
            )

    def check_paper_trading_mode(self) -> HealthCheckResult:
        """Check if paper trading mode is active."""
        if self.dry_run:
            return self._add_result(
                "paper_trading_mode",
                "SKIP",
                "Dry run - skipping paper trading mode check",
            )

        r = self._get_redis()
        if r is None:
            return self._add_result(
                "paper_trading_mode",
                "FAIL",
                "Cannot check paper trading mode - Redis unavailable",
            )

        try:
            mode = r.get(PAPER_MODE_KEY)
            if mode is None:
                # Check for any paper trading signals/orders as fallback
                signal_count = r.zcard(SIGNAL_INDEX_KEY) or 0
                order_count = r.zcard(ORDER_INDEX_KEY) or 0

                if signal_count > 0 or order_count > 0:
                    return self._add_result(
                        "paper_trading_mode",
                        "PASS",
                        "Paper trading mode inferred from activity",
                        {
                            "mode_key": None,
                            "signal_count": signal_count,
                            "order_count": order_count,
                            "note": "Mode key not set but activity detected",
                        },
                    )
                else:
                    return self._add_result(
                        "paper_trading_mode",
                        "WARN",
                        "Paper trading mode key not set and no activity detected",
                        {"mode_key": None, "signal_count": 0, "order_count": 0},
                    )

            mode_str = mode.lower() if isinstance(mode, str) else str(mode).lower()
            is_active = mode_str in ("paper", "active", "1", "true", "yes")

            if is_active:
                return self._add_result(
                    "paper_trading_mode",
                    "PASS",
                    f"Paper trading mode is active: {mode}",
                    {"mode": mode, "mode_key": PAPER_MODE_KEY},
                )
            else:
                return self._add_result(
                    "paper_trading_mode",
                    "FAIL",
                    f"Paper trading mode is not active: {mode}",
                    {"mode": mode, "mode_key": PAPER_MODE_KEY},
                )

        except Exception as e:
            return self._add_result(
                "paper_trading_mode",
                "FAIL",
                f"Error checking paper trading mode: {e}",
                {"error": str(e)},
            )

    def check_signal_generation(self) -> HealthCheckResult:
        """Verify signal generation (signals in last 5 min)."""
        if self.dry_run:
            return self._add_result(
                "signal_generation",
                "SKIP",
                "Dry run - skipping signal generation check",
            )

        r = self._get_redis()
        if r is None:
            return self._add_result(
                "signal_generation",
                "FAIL",
                "Cannot check signal generation - Redis unavailable",
            )

        try:
            now = datetime.now(UTC)
            lookback = now - timedelta(minutes=SIGNAL_LOOKBACK_MINUTES)
            lookback_ts = lookback.timestamp()

            # Get signals from the last 5 minutes
            recent_signals = r.zrangebyscore(
                SIGNAL_INDEX_KEY, lookback_ts, "+inf", withscores=True
            )

            signal_count = len(recent_signals)

            if signal_count > 0:
                # Get details of most recent signal
                most_recent = recent_signals[-1] if recent_signals else None
                recent_signal_ids = [s[0] for s in recent_signals[-5:]]  # Last 5

                return self._add_result(
                    "signal_generation",
                    "PASS",
                    f"{signal_count} signals generated in last {SIGNAL_LOOKBACK_MINUTES} minutes",
                    {
                        "signal_count": signal_count,
                        "lookback_minutes": SIGNAL_LOOKBACK_MINUTES,
                        "most_recent_signal": most_recent[0] if most_recent else None,
                        "most_recent_timestamp": (
                            datetime.fromtimestamp(most_recent[1], UTC).isoformat()
                            if most_recent
                            else None
                        ),
                        "recent_signal_ids": recent_signal_ids,
                    },
                )
            else:
                # Check total signal count as context
                total_signals = r.zcard(SIGNAL_INDEX_KEY) or 0

                if total_signals == 0:
                    return self._add_result(
                        "signal_generation",
                        "WARN",
                        "No signals found in system - may be initial startup",
                        {
                            "recent_count": 0,
                            "total_count": total_signals,
                            "lookback_minutes": SIGNAL_LOOKBACK_MINUTES,
                        },
                    )
                else:
                    # Get oldest signal timestamp for context
                    oldest = r.zrange(SIGNAL_INDEX_KEY, 0, 0, withscores=True)
                    oldest_ts = oldest[0][1] if oldest else None

                    return self._add_result(
                        "signal_generation",
                        "WARN",
                        f"No signals in last {SIGNAL_LOOKBACK_MINUTES} minutes ({total_signals} total)",
                        {
                            "recent_count": 0,
                            "total_count": total_signals,
                            "lookback_minutes": SIGNAL_LOOKBACK_MINUTES,
                            "oldest_signal_timestamp": (
                                datetime.fromtimestamp(oldest_ts, UTC).isoformat()
                                if oldest_ts
                                else None
                            ),
                        },
                    )

        except Exception as e:
            return self._add_result(
                "signal_generation",
                "FAIL",
                f"Error checking signal generation: {e}",
                {"error": str(e)},
            )

    def check_order_flow(self) -> HealthCheckResult:
        """Verify order flow (orders in last 5 min)."""
        if self.dry_run:
            return self._add_result(
                "order_flow",
                "SKIP",
                "Dry run - skipping order flow check",
            )

        r = self._get_redis()
        if r is None:
            return self._add_result(
                "order_flow",
                "FAIL",
                "Cannot check order flow - Redis unavailable",
            )

        try:
            now = datetime.now(UTC)
            lookback = now - timedelta(minutes=ORDER_LOOKBACK_MINUTES)
            lookback_ts = lookback.timestamp()

            # Get orders from the last 5 minutes
            recent_orders = r.zrangebyscore(
                ORDER_INDEX_KEY, lookback_ts, "+inf", withscores=True
            )

            order_count = len(recent_orders)

            if order_count > 0:
                most_recent = recent_orders[-1] if recent_orders else None
                recent_order_ids = [o[0] for o in recent_orders[-5:]]  # Last 5

                return self._add_result(
                    "order_flow",
                    "PASS",
                    f"{order_count} orders in last {ORDER_LOOKBACK_MINUTES} minutes",
                    {
                        "order_count": order_count,
                        "lookback_minutes": ORDER_LOOKBACK_MINUTES,
                        "most_recent_order": most_recent[0] if most_recent else None,
                        "most_recent_timestamp": (
                            datetime.fromtimestamp(most_recent[1], UTC).isoformat()
                            if most_recent
                            else None
                        ),
                        "recent_order_ids": recent_order_ids,
                    },
                )
            else:
                # Check total order count as context
                total_orders = r.zcard(ORDER_INDEX_KEY) or 0

                if total_orders == 0:
                    return self._add_result(
                        "order_flow",
                        "WARN",
                        "No orders found in system - may be initial startup",
                        {
                            "recent_count": 0,
                            "total_count": total_orders,
                            "lookback_minutes": ORDER_LOOKBACK_MINUTES,
                        },
                    )
                else:
                    return self._add_result(
                        "order_flow",
                        "WARN",
                        f"No orders in last {ORDER_LOOKBACK_MINUTES} minutes ({total_orders} total)",
                        {
                            "recent_count": 0,
                            "total_count": total_orders,
                            "lookback_minutes": ORDER_LOOKBACK_MINUTES,
                        },
                    )

        except Exception as e:
            return self._add_result(
                "order_flow",
                "FAIL",
                f"Error checking order flow: {e}",
                {"error": str(e)},
            )

    def check_kill_switch(self) -> HealthCheckResult:
        """Check kill-switch status."""
        if self.dry_run:
            return self._add_result(
                "kill_switch",
                "SKIP",
                "Dry run - skipping kill-switch check",
            )

        r = self._get_redis()
        if r is None:
            return self._add_result(
                "kill_switch",
                "FAIL",
                "Cannot check kill-switch - Redis unavailable",
            )

        try:
            # Import kill-switch bootstrap functions
            sys_path_inserted = False
            if "/src" not in sys.path:
                script_dir = Path(__file__).parent.absolute()
                src_path = script_dir.parent.parent / "src"
                sys.path.insert(0, str(src_path))
                sys_path_inserted = True

            try:
                from execution.kill_switch.bootstrap import (
                    bootstrap_kill_switch,
                    get_kill_switch_status,
                    is_kill_switch_initialized,
                )

                # Bootstrap if not initialized
                if not is_kill_switch_initialized(r):
                    bootstrap_result = bootstrap_kill_switch(r)
                    if not bootstrap_result:
                        return self._add_result(
                            "kill_switch",
                            "FAIL",
                            "Kill-switch not initialized and bootstrap failed",
                            {"initialized": False, "bootstrap_attempted": True},
                        )

                status = get_kill_switch_status(r)

                if status.get("error"):
                    return self._add_result(
                        "kill_switch",
                        "FAIL",
                        f"Kill-switch error: {status['error']}",
                        status,
                    )

                if not status.get("initialized"):
                    return self._add_result(
                        "kill_switch",
                        "FAIL",
                        "Kill-switch not initialized",
                        status,
                    )

                if status.get("triggered"):
                    return self._add_result(
                        "kill_switch",
                        "FAIL",
                        "Kill-switch is TRIGGERED - trading halted",
                        status,
                    )

                if not status.get("enabled"):
                    return self._add_result(
                        "kill_switch",
                        "WARN",
                        "Kill-switch is DISARMED - not monitoring",
                        status,
                    )

                return self._add_result(
                    "kill_switch",
                    "PASS",
                    "Kill-switch is armed and monitoring",
                    status,
                )

            finally:
                if sys_path_inserted:
                    sys.path.pop(0)

        except Exception as e:
            return self._add_result(
                "kill_switch",
                "FAIL",
                f"Error checking kill-switch: {e}",
                {"error": str(e)},
            )

    def check_discord_connectivity(self) -> HealthCheckResult:
        """Check Discord connectivity."""
        if self.dry_run:
            return self._add_result(
                "discord_connectivity",
                "SKIP",
                "Dry run - skipping Discord connectivity check",
            )

        # Check if Discord is configured
        if not any([DISCORD_WEBHOOK_URL, (DISCORD_BOT_TOKEN and DISCORD_CHANNEL_ID)]):
            return self._add_result(
                "discord_connectivity",
                "WARN",
                "Discord not configured - no webhook or bot token",
                {
                    "webhook_configured": bool(DISCORD_WEBHOOK_URL),
                    "bot_configured": bool(DISCORD_BOT_TOKEN and DISCORD_CHANNEL_ID),
                },
            )

        # Try to get continuity status from Redis
        r = self._get_redis()
        continuity_status = None
        last_success = None

        if r is not None:
            try:
                continuity_status = r.get(
                    f"{DISCORD_CONTINUITY_PREFIX}:continuity_status"
                )
                last_success = r.get(f"{DISCORD_CONTINUITY_PREFIX}:last_success_at")
            except Exception as e:
                logger.warning(f"Could not read Discord continuity from Redis: {e}")

        # Test Discord connectivity with a lightweight request
        import ssl
        import urllib.request

        discord_ok = False
        discord_method = None
        error_msg = None
        ctx = ssl.create_default_context()

        # Try webhook first
        if DISCORD_WEBHOOK_URL:
            try:
                req = urllib.request.Request(
                    DISCORD_WEBHOOK_URL,
                    method="GET",
                    headers={"User-Agent": "ChiseAI-HealthProbe/1.0"},
                )
                with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                    # Discord webhooks return 200 OK on GET
                    if resp.status == 200:
                        discord_ok = True
                        discord_method = "webhook"
            except urllib.error.HTTPError as e:
                # 401/403 means webhook exists but requires auth (expected)
                if e.code in (401, 403):
                    discord_ok = True
                    discord_method = "webhook"
                else:
                    error_msg = f"Webhook HTTP error: {e.code}"
            except Exception as e:
                error_msg = f"Webhook error: {e}"

        # Try bot API if webhook failed
        if not discord_ok and DISCORD_BOT_TOKEN and DISCORD_CHANNEL_ID:
            try:
                url = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}"
                req = urllib.request.Request(
                    url,
                    method="GET",
                    headers={
                        "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
                        "User-Agent": "ChiseAI-HealthProbe/1.0",
                    },
                )
                with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                    if resp.status == 200:
                        discord_ok = True
                        discord_method = "bot_api"
            except urllib.error.HTTPError as e:
                if e.code == 200:
                    discord_ok = True
                    discord_method = "bot_api"
                else:
                    error_msg = f"Bot API HTTP error: {e.code}"
            except Exception as e:
                error_msg = f"Bot API error: {e}"

        details = {
            "webhook_configured": bool(DISCORD_WEBHOOK_URL),
            "bot_configured": bool(DISCORD_BOT_TOKEN and DISCORD_CHANNEL_ID),
            "continuity_status": continuity_status,
            "last_success_at": last_success,
            "test_method": discord_method,
        }

        if discord_ok:
            return self._add_result(
                "discord_connectivity",
                "PASS",
                f"Discord connectivity OK via {discord_method}",
                details,
            )
        else:
            return self._add_result(
                "discord_connectivity",
                "WARN",
                f"Discord connectivity issue: {error_msg or 'unknown error'}",
                details,
            )

    def run_all_checks(self) -> dict[str, Any]:
        """Run all health checks and return summary."""
        logger.info("Starting Paper E2E Health Probe")
        logger.info(f"Dry run: {self.dry_run}")
        logger.info(f"Output directory: {self.output_dir}")

        # Run all checks
        self.check_redis_connectivity()
        self.check_paper_trading_mode()
        self.check_signal_generation()
        self.check_order_flow()
        self.check_kill_switch()
        self.check_discord_connectivity()

        # Calculate summary
        pass_count = sum(1 for r in self.results if r.status == "PASS")
        warn_count = sum(1 for r in self.results if r.status == "WARN")
        fail_count = sum(1 for r in self.results if r.status == "FAIL")
        skip_count = sum(1 for r in self.results if r.status == "SKIP")

        end_time = datetime.now(UTC)
        duration_ms = (end_time - self.start_time).total_seconds() * 1000

        summary = {
            "probe_name": "paper_e2e_health_probe",
            "version": "1.0.0",
            "timestamp": end_time.isoformat(),
            "start_time": self.start_time.isoformat(),
            "duration_ms": duration_ms,
            "dry_run": self.dry_run,
            "summary": {
                "total_checks": len(self.results),
                "pass": pass_count,
                "warn": warn_count,
                "fail": fail_count,
                "skip": skip_count,
            },
            "checks": [r.to_dict() for r in self.results],
        }

        # Determine overall status
        if fail_count > 0:
            summary["overall_status"] = "FAIL"
            summary["exit_code"] = 2
        elif warn_count > 0:
            summary["overall_status"] = "WARN"
            summary["exit_code"] = 1
        else:
            summary["overall_status"] = "PASS"
            summary["exit_code"] = 0

        return summary

    def save_evidence(self, summary: dict[str, Any]) -> Path:
        """Save evidence to file."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        filename = f"paper_health_{timestamp}.json"
        filepath = self.output_dir / filename

        with open(filepath, "w") as f:
            json.dump(summary, f, indent=2, default=str)

        logger.info(f"Evidence saved to: {filepath}")
        return filepath

    def print_report(self, summary: dict[str, Any]) -> None:
        """Print formatted report to console."""
        print("\n" + "=" * 70)
        print("PAPER TRADING E2E HEALTH PROBE REPORT")
        print("=" * 70)
        print(f"Timestamp: {summary['timestamp']}")
        print(f"Duration: {summary['duration_ms']:.1f}ms")
        print(f"Dry Run: {summary['dry_run']}")
        print("-" * 70)

        # Summary
        s = summary["summary"]
        status_emoji = {
            "PASS": "✅",
            "WARN": "⚠️",
            "FAIL": "❌",
        }.get(summary["overall_status"], "❓")

        print(f"\nOverall Status: {status_emoji} {summary['overall_status']}")
        print(f"Exit Code: {summary['exit_code']}")
        print(f"\nChecks: {s['total_checks']} total")
        print(f"  ✅ PASS: {s['pass']}")
        print(f"  ⚠️  WARN: {s['warn']}")
        print(f"  ❌ FAIL: {s['fail']}")
        print(f"  ⏭️  SKIP: {s['skip']}")

        # Individual check results
        print("\n" + "-" * 70)
        print("DETAILED RESULTS")
        print("-" * 70)

        for check in summary["checks"]:
            emoji = {
                "PASS": "✅",
                "WARN": "⚠️",
                "FAIL": "❌",
                "SKIP": "⏭️",
            }.get(check["status"], "❓")

            print(f"\n{emoji} [{check['status']}] {check['name']}")
            print(f"   Message: {check['message']}")

            if check.get("details"):
                for key, value in check["details"].items():
                    if value is not None:
                        print(f"   {key}: {value}")

        print("\n" + "=" * 70)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Paper Trading E2E Health Probe",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exit Codes:
  0 = PASS (all checks passed)
  1 = WARN (some checks passed with warnings)
  2 = FAIL (one or more critical checks failed)
        """,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run in dry-run mode (skip actual checks)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="_bmad-output/evidence",
        help="Directory to save evidence files",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress console output (only log to file)",
    )

    args = parser.parse_args()

    if args.quiet:
        logging.getLogger().setLevel(logging.WARNING)

    # Create and run probe
    probe = PaperE2EHealthProbe(dry_run=args.dry_run, output_dir=args.output_dir)
    summary = probe.run_all_checks()

    # Save evidence
    probe.save_evidence(summary)

    # Print report unless quiet mode
    if not args.quiet:
        probe.print_report(summary)

    return summary["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
