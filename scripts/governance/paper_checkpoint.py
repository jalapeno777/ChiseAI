#!/usr/bin/env python3
"""
Paper Trading Checkpoint Automation CLI

An executable CLI script for managing paper trading checkpoints with G1-G8 gate checks,
evidence collection, and reporting.

Usage:
    python paper_checkpoint.py run           # Execute full checkpoint audit
    python paper_checkpoint.py status       # Show current checkpoint status
    python paper_checkpoint.py history      # Show checkpoint history
    python paper_checkpoint.py gate G1      # Check specific gate (G1-G8)
    python paper_checkpoint.py evidence     # Collect and store evidence

Exit codes:
    0: All gates passed
    1: One or more gates failed
    2: Error during execution
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Constants
REDIS_HOST = os.getenv("REDIS_HOST", "host.docker.internal")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6380"))
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID", "")

# Redis key patterns
KEY_CHECKPOINT_LATEST = "bmad:chiseai:checkpoint:latest"
KEY_CHECKPOINT_HISTORY = "bmad:chiseai:checkpoint:history"
KEY_CHECKPOINT_EVIDENCE_PREFIX = "bmad:chiseai:checkpoint:evidence:"

# Evidence archive directory
EVIDENCE_DIR = Path("logs/checkpoints")


# ============================================================================
# Protocol definitions for src.governance.checkpoint integration
# ============================================================================


class CheckpointManagerProtocol(Protocol):
    """Protocol for CheckpointManager from src.governance.checkpoint."""

    def run_checkpoint(self) -> dict[str, Any]: ...
    def get_status(self) -> dict[str, Any]: ...
    def get_history(self, limit: int = 10) -> list[dict[str, Any]]: ...


class GateCheckerProtocol(Protocol):
    """Protocol for GateChecker from src.governance.checkpoint."""

    def check_gate(self, gate_id: str) -> dict[str, Any]: ...
    def check_all_gates(self) -> list[dict[str, Any]]: ...


class EvidenceCollectorProtocol(Protocol):
    """Protocol for EvidenceCollector from src.governance.checkpoint."""

    def collect(self, gate_results: list[dict[str, Any]]) -> dict[str, Any]: ...
    def archive(self, evidence: dict[str, Any], path: Path) -> Path: ...


class StateManagerProtocol(Protocol):
    """Protocol for StateManager from src.governance.checkpoint."""

    def save_checkpoint(self, data: dict[str, Any]) -> bool: ...
    def load_checkpoint(self) -> dict[str, Any] | None: ...
    def add_to_history(self, data: dict[str, Any]) -> bool: ...


# ============================================================================
# Stub implementations (used when src.governance.checkpoint is not available)
# ============================================================================


class CheckpointManager:
    """Stub implementation of CheckpointManager."""

    def __init__(self, redis_client: Any | None = None) -> None:
        self.redis = redis_client
        self.gate_checker = GateChecker(redis_client)
        self.evidence_collector = EvidenceCollector()
        self.state_manager = StateManager(redis_client)

    def run_checkpoint(self) -> dict[str, Any]:
        """Execute full checkpoint audit."""
        logger.info("Running full checkpoint audit...")

        # Run all gate checks
        gate_results = self.gate_checker.check_all_gates()

        # Collect evidence
        evidence = self.evidence_collector.collect(gate_results)

        # Build checkpoint result
        checkpoint = {
            "timestamp": datetime.now(UTC).isoformat(),
            "gates": gate_results,
            "evidence": evidence,
            "summary": self._summarize(gate_results),
        }

        # Save to Redis
        self.state_manager.save_checkpoint(checkpoint)
        self.state_manager.add_to_history(checkpoint)

        # Archive evidence to file
        self.evidence_collector.archive(evidence, EVIDENCE_DIR)

        return checkpoint

    def get_status(self) -> dict[str, Any]:
        """Get current checkpoint status."""
        return self.state_manager.load_checkpoint() or {
            "status": "unknown",
            "message": "No checkpoint found",
        }

    def get_history(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get checkpoint history."""
        return self.state_manager.get_history(limit)

    def _summarize(self, gate_results: list[dict[str, Any]]) -> dict[str, int]:
        """Summarize gate results."""
        passed = sum(1 for g in gate_results if "PASS" in g.get("status", ""))
        failed = sum(1 for g in gate_results if "FAIL" in g.get("status", ""))
        check = sum(1 for g in gate_results if "CHECK" in g.get("status", ""))

        return {
            "total": len(gate_results),
            "passed": passed,
            "failed": failed,
            "check": check,
        }


class GateChecker:
    """Stub implementation of GateChecker with G1-G8 checks."""

    def __init__(self, redis_client: Any | None = None) -> None:
        self.redis = redis_client or self._get_redis()

    def _get_redis(self) -> Any | None:
        """Get Redis connection."""
        try:
            import redis as redis_lib

            return redis_lib.Redis(
                host=REDIS_HOST, port=REDIS_PORT, decode_responses=True
            )
        except Exception as e:
            logger.warning(f"Redis unavailable: {e}")
            return None

    def check_gate(self, gate_id: str) -> dict[str, Any]:
        """Check a specific gate (G1-G8)."""
        check_map = {
            "G1": self._check_g1_scheduler,
            "G2": self._check_g2_signal_cadence,
            "G3": self._check_g3_data_flow,
            "G4": self._check_g4_kill_switch,
            "G5": self._check_g5_cron_cadence,
            "G6": self._check_g6_bybit_connectivity,
            "G7": self._check_g7_observability,
            "G8": self._check_g8_pipeline,
        }

        checker = check_map.get(gate_id.upper())
        if checker:
            return checker()
        return {"gate": gate_id, "status": "❌ FAIL", "detail": "Unknown gate"}

    def check_all_gates(self) -> list[dict[str, Any]]:
        """Check all G1-G8 gates."""
        return [
            self._check_g1_scheduler(),
            self._check_g2_signal_cadence(),
            self._check_g3_data_flow(),
            self._check_g4_kill_switch(),
            self._check_g5_cron_cadence(),
            self._check_g6_bybit_connectivity(),
            self._check_g7_observability(),
            self._check_g8_pipeline(),
        ]

    def _check_g1_scheduler(self) -> dict[str, Any]:
        """G1: Scheduler Continuity - Check Redis heartbeat."""
        if not self.redis:
            return {"gate": "G1", "status": "❌ FAIL", "detail": "Redis unavailable"}

        try:
            heartbeat = self.redis.hgetall("bmad:chiseai:scheduler:heartbeat")
            if not heartbeat:
                return {
                    "gate": "G1",
                    "status": "❌ FAIL",
                    "detail": "No scheduler heartbeat",
                }

            timestamp_str = heartbeat.get("timestamp", "")
            status = heartbeat.get("status", "unknown")

            if not timestamp_str:
                return {
                    "gate": "G1",
                    "status": "❌ FAIL",
                    "detail": "Invalid heartbeat",
                }

            last_heartbeat = datetime.fromisoformat(timestamp_str)
            age_seconds = (datetime.now(UTC) - last_heartbeat).total_seconds()

            if status != "running":
                return {
                    "gate": "G1",
                    "status": "❌ FAIL",
                    "detail": f"Scheduler status: {status}",
                }

            if age_seconds > 120:
                return {
                    "gate": "G1",
                    "status": "⚠️ CHECK",
                    "detail": f"Heartbeat stale: {age_seconds:.0f}s",
                }

            return {
                "gate": "G1",
                "status": "✅ PASS",
                "detail": f"Heartbeat {age_seconds:.0f}s ago",
            }
        except Exception as e:
            return {"gate": "G1", "status": "❌ FAIL", "detail": str(e)}

    def _check_g2_signal_cadence(self) -> dict[str, Any]:
        """G2: Signal Cadence."""
        if not self.redis:
            return {"gate": "G2", "status": "❌ FAIL", "detail": "Redis unavailable"}

        try:
            count = len(self.redis.keys("bmad:chiseai:signals:*"))
            if count > 0:
                return {
                    "gate": "G2",
                    "status": "✅ PASS",
                    "detail": f"{count} signals in Redis",
                }
            return {"gate": "G2", "status": "⚠️ CHECK", "detail": "No signals found"}
        except Exception as e:
            return {"gate": "G2", "status": "❌ FAIL", "detail": str(e)}

    def _check_g3_data_flow(self) -> dict[str, Any]:
        """G3: Data Flow Movement."""
        if not self.redis:
            return {"gate": "G3", "status": "❌ FAIL", "detail": "Redis unavailable"}

        try:
            count = self.redis.scard("bmad:chiseai:outcomes:index")
            if count and count > 0:
                return {
                    "gate": "G3",
                    "status": "✅ PASS",
                    "detail": f"{count} outcomes recorded",
                }
            return {"gate": "G3", "status": "⚠️ CHECK", "detail": "No outcomes found"}
        except Exception as e:
            return {"gate": "G3", "status": "❌ FAIL", "detail": str(e)}

    def _check_g4_kill_switch(self) -> dict[str, Any]:
        """G4: Kill Switch Active."""
        if not self.redis:
            return {"gate": "G4", "status": "❌ FAIL", "detail": "Redis unavailable"}

        try:
            enabled = self.redis.hget("bmad:chiseai:kill_switch", "enabled")
            triggered = self.redis.hget("bmad:chiseai:kill_switch", "triggered")

            if enabled == "1" and triggered == "0":
                return {"gate": "G4", "status": "✅ PASS", "detail": "Armed and ready"}
            elif triggered == "1":
                return {
                    "gate": "G4",
                    "status": "🚨 ALERT",
                    "detail": "TRIGGERED - Trading halted",
                }
            return {"gate": "G4", "status": "⚠️ CHECK", "detail": "Not configured"}
        except Exception as e:
            return {"gate": "G4", "status": "❌ FAIL", "detail": str(e)}

    def _check_g5_cron_cadence(self) -> dict[str, Any]:
        """G5: Cron Job Cadence Evidence."""
        if not self.redis:
            return {"gate": "G5", "status": "❌ FAIL", "detail": "Redis unavailable"}

        try:
            # Check cron evidence keys
            cron_keys = self.redis.keys("bmad:chiseai:cron:*:last_run")
            if not cron_keys:
                return {
                    "gate": "G5",
                    "status": "⚠️ CHECK",
                    "detail": "No cron evidence",
                }

            # Check if any cron jobs are stale (> 2x expected interval)
            stale_jobs = []
            now = time.time()

            for key in cron_keys:
                last_run = self.redis.get(key)
                if last_run:
                    age = now - float(last_run)
                    job_name = key.split(":")[-2]
                    # Default 1 hour threshold
                    if age > 7200:  # 2 hours
                        stale_jobs.append(f"{job_name}:{age // 60:.0f}m")

            if stale_jobs:
                return {
                    "gate": "G5",
                    "status": "⚠️ CHECK",
                    "detail": f"Stale jobs: {', '.join(stale_jobs[:3])}",
                }

            return {
                "gate": "G5",
                "status": "✅ PASS",
                "detail": f"{len(cron_keys)} cron jobs active",
            }
        except Exception as e:
            return {"gate": "G5", "status": "❌ FAIL", "detail": str(e)}

    def _check_g6_bybit_connectivity(self) -> dict[str, Any]:
        """G6: Bybit Connectivity."""
        try:
            import socket
            import ssl

            host = "api.bybit.com"
            port = 443
            timeout = 5

            context = ssl.create_default_context()
            with socket.create_connection((host, port), timeout=timeout) as sock:
                with context.wrap_socket(sock, server_hostname=host) as ssock:
                    request = f"GET /v5/market/time HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n"
                    ssock.send(request.encode())
                    response = ssock.recv(1024).decode()
                    if "200 OK" in response or "HTTP/1.1" in response:
                        return {
                            "gate": "G6",
                            "status": "✅ PASS",
                            "detail": "API reachable",
                        }
                    return {
                        "gate": "G6",
                        "status": "⚠️ CHECK",
                        "detail": "Unexpected response",
                    }
        except Exception as e:
            return {"gate": "G6", "status": "❌ FAIL", "detail": str(e)[:50]}

    def _check_g7_observability(self) -> dict[str, Any]:
        """G7: Observability Health."""
        if not self.redis:
            return {"gate": "G7", "status": "❌ FAIL", "detail": "Redis unavailable"}

        try:
            ping = self.redis.ping()
            keys = self.redis.dbsize()
            info = self.redis.info("server")
            uptime = info.get("uptime_in_seconds", 0)

            if ping and uptime > 3600:
                return {
                    "gate": "G7",
                    "status": "✅ PASS",
                    "detail": f"Redis OK, {keys} keys, {uptime // 3600}h uptime",
                }
            elif ping:
                return {
                    "gate": "G7",
                    "status": "⚠️ CHECK",
                    "detail": "Redis OK but uptime <1h",
                }
            return {"gate": "G7", "status": "❌ FAIL", "detail": "Redis ping failed"}
        except Exception as e:
            return {"gate": "G7", "status": "❌ FAIL", "detail": str(e)}

    def _check_g8_pipeline(self) -> dict[str, Any]:
        """G8: End-to-End Pipeline - Burn-in Verdict."""
        if not self.redis:
            return {"gate": "G8", "status": "❌ FAIL", "detail": "Redis unavailable"}

        try:
            verdict = self.redis.get("bmad:chiseai:burnin:verdict")
            signals = len(self.redis.keys("bmad:chiseai:signals:*"))
            outcomes = self.redis.scard("bmad:chiseai:outcomes:index")

            if verdict is None:
                return {
                    "gate": "G8",
                    "status": "❓ UNKNOWN",
                    "detail": "No burn-in verdict found",
                }
            elif verdict == "GO":
                return {
                    "gate": "G8",
                    "status": "✅ PASS",
                    "detail": f"Verdict: GO | {signals} signals → {outcomes} outcomes",
                }
            elif verdict == "NO-GO":
                return {
                    "gate": "G8",
                    "status": "❌ FAIL",
                    "detail": "Verdict: NO-GO | Pipeline halted",
                }
            return {
                "gate": "G8",
                "status": "⚠️ CHECK",
                "detail": f"Unexpected verdict: '{verdict}'",
            }
        except Exception as e:
            return {"gate": "G8", "status": "❌ FAIL", "detail": str(e)}


class EvidenceCollector:
    """Stub implementation of EvidenceCollector."""

    def collect(self, gate_results: list[dict[str, Any]]) -> dict[str, Any]:
        """Collect evidence from gate results."""
        return {
            "collected_at": datetime.now(UTC).isoformat(),
            "gate_count": len(gate_results),
            "gates": gate_results,
            "metadata": {
                "hostname": os.getenv("HOSTNAME", "unknown"),
                "environment": os.getenv("ENVIRONMENT", "development"),
            },
        }

    def archive(self, evidence: dict[str, Any], path: Path) -> Path:
        """Archive evidence to file."""
        path.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        filename = f"checkpoint-evidence-{timestamp}.json"
        filepath = path / filename

        with open(filepath, "w") as f:
            json.dump(evidence, f, indent=2, default=str)

        logger.info(f"Evidence archived to {filepath}")
        return filepath


class StateManager:
    """Stub implementation of StateManager."""

    def __init__(self, redis_client: Any | None = None) -> None:
        self.redis = redis_client

    def save_checkpoint(self, data: dict[str, Any]) -> bool:
        """Save checkpoint to Redis."""
        if not self.redis:
            logger.warning("Redis unavailable, checkpoint not saved")
            return False

        try:
            self.redis.set(KEY_CHECKPOINT_LATEST, json.dumps(data, default=str))
            return True
        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")
            return False

    def load_checkpoint(self) -> dict[str, Any] | None:
        """Load latest checkpoint from Redis."""
        if not self.redis:
            return None

        try:
            data = self.redis.get(KEY_CHECKPOINT_LATEST)
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.error(f"Failed to load checkpoint: {e}")
            return None

    def add_to_history(self, data: dict[str, Any]) -> bool:
        """Add checkpoint to history."""
        if not self.redis:
            logger.warning("Redis unavailable, history not updated")
            return False

        try:
            self.redis.lpush(KEY_CHECKPOINT_HISTORY, json.dumps(data, default=str))
            # Keep only last 100 entries
            self.redis.ltrim(KEY_CHECKPOINT_HISTORY, 0, 99)
            return True
        except Exception as e:
            logger.error(f"Failed to add to history: {e}")
            return False

    def get_history(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get checkpoint history."""
        if not self.redis:
            return []

        try:
            items = self.redis.lrange(KEY_CHECKPOINT_HISTORY, 0, limit - 1)
            return [json.loads(item) for item in items]
        except Exception as e:
            logger.error(f"Failed to get history: {e}")
            return []


# ============================================================================
# Try to import from src.governance.checkpoint (will use stubs if unavailable)
# ============================================================================

try:
    from src.governance.checkpoint import (
        CheckpointManager,
        EvidenceCollector,
        GateChecker,
        StateManager,
    )

    logger.debug("Using CheckpointManager from src.governance.checkpoint")
except ImportError:
    logger.debug("Using stub implementations (src.governance.checkpoint not available)")


# ============================================================================
# Discord integration
# ============================================================================


async def post_to_discord(message: str) -> bool:
    """Post message to Discord via webhook or bot API."""
    import aiohttp

    # Try webhook first
    if DISCORD_WEBHOOK_URL:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    DISCORD_WEBHOOK_URL, json={"content": message}
                ) as resp:
                    if resp.status in (200, 204):
                        logger.info("Discord webhook post successful")
                        return True
                    logger.warning(f"Discord webhook failed: {resp.status}")
        except Exception as e:
            logger.warning(f"Discord webhook error: {e}")

    # Fall back to bot API
    if DISCORD_CHANNEL_ID and DISCORD_BOT_TOKEN:
        try:
            url = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages"
            headers = {
                "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
                "Content-Type": "application/json",
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, headers=headers, json={"content": message}
                ) as resp:
                    if resp.status == 200:
                        logger.info("Discord bot post successful")
                        return True
                    logger.error(f"Discord bot post failed: {resp.status}")
        except Exception as e:
            logger.error(f"Discord bot error: {e}")

    logger.warning("Discord not configured")
    return False


def format_checkpoint_report(checkpoint: dict[str, Any]) -> str:
    """Format checkpoint data as a Discord message."""
    timestamp = checkpoint.get("timestamp", datetime.now(UTC).isoformat())
    gates = checkpoint.get("gates", [])
    summary = checkpoint.get("summary", {})

    lines = [
        f"**📊 Paper Trading Checkpoint** | {timestamp}",
        "",
        f"**Summary:** {summary.get('passed', 0)} ✅ | {summary.get('check', 0)} ⚠️ | {summary.get('failed', 0)} ❌",
        "",
    ]

    for gate in gates:
        lines.append(f"**{gate['gate']}:** {gate['status']} - {gate['detail']}")

    return "\n".join(lines)


# ============================================================================
# CLI commands
# ============================================================================


def cmd_run(args: argparse.Namespace) -> int:
    """Execute full checkpoint audit."""
    try:
        manager = CheckpointManager()
        checkpoint = manager.run_checkpoint()

        # Format and optionally post to Discord
        report = format_checkpoint_report(checkpoint)
        print(report)

        if args.discord:
            asyncio.run(post_to_discord(report))

        # Determine exit code based on gate results
        summary = checkpoint.get("summary", {})
        if summary.get("failed", 0) > 0:
            return 1  # One or more gates failed
        return 0  # All gates passed

    except Exception as e:
        logger.error(f"Checkpoint run failed: {e}")
        return 2  # Error during execution


def cmd_status(args: argparse.Namespace) -> int:
    """Show current checkpoint status."""
    try:
        manager = CheckpointManager()
        status = manager.get_status()

        if status.get("status") == "unknown":
            print("No checkpoint found in Redis")
            return 0

        print(json.dumps(status, indent=2, default=str))
        return 0

    except Exception as e:
        logger.error(f"Failed to get status: {e}")
        return 2


def cmd_history(args: argparse.Namespace) -> int:
    """Show checkpoint history."""
    try:
        manager = CheckpointManager()
        history = manager.get_history(limit=args.limit)

        if not history:
            print("No checkpoint history found")
            return 0

        for i, entry in enumerate(history, 1):
            timestamp = entry.get("timestamp", "unknown")
            summary = entry.get("summary", {})
            print(
                f"{i}. {timestamp} - "
                f"✅ {summary.get('passed', 0)} "
                f"⚠️ {summary.get('check', 0)} "
                f"❌ {summary.get('failed', 0)}"
            )

        return 0

    except Exception as e:
        logger.error(f"Failed to get history: {e}")
        return 2


def cmd_gate(args: argparse.Namespace) -> int:
    """Check specific gate (G1-G8)."""
    gate_id = args.gate_id.upper()

    if gate_id not in {"G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8"}:
        print(f"Error: Invalid gate '{gate_id}'. Must be G1-G8.", file=sys.stderr)
        return 2

    try:
        checker = GateChecker()
        result = checker.check_gate(gate_id)

        print(f"**{result['gate']}:** {result['status']} - {result['detail']}")

        if "FAIL" in result["status"]:
            return 1
        return 0

    except Exception as e:
        logger.error(f"Gate check failed: {e}")
        return 2


def cmd_evidence(args: argparse.Namespace) -> int:
    """Collect and store evidence."""
    try:
        checker = GateChecker()
        collector = EvidenceCollector()

        # Run all gate checks
        gate_results = checker.check_all_gates()

        # Collect evidence
        evidence = collector.collect(gate_results)

        # Archive to file
        path = collector.archive(evidence, EVIDENCE_DIR)

        print(f"Evidence collected and archived to: {path}")
        print(f"Gates checked: {len(gate_results)}")

        # Print summary
        passed = sum(1 for g in gate_results if "PASS" in g.get("status", ""))
        failed = sum(1 for g in gate_results if "FAIL" in g.get("status", ""))
        print(f"Results: {passed} passed, {failed} failed")

        if failed > 0:
            return 1
        return 0

    except Exception as e:
        logger.error(f"Evidence collection failed: {e}")
        return 2


# ============================================================================
# Main entry point
# ============================================================================


def main() -> int:
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        prog="paper_checkpoint",
        description="Paper Trading Checkpoint Automation CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s run                    # Execute full checkpoint audit
  %(prog)s run --discord          # Run and post to Discord
  %(prog)s status                 # Show current checkpoint status
  %(prog)s history --limit 20     # Show last 20 checkpoints
  %(prog)s gate G1                # Check specific gate
  %(prog)s evidence               # Collect and archive evidence

Exit codes:
  0 - All gates passed / Success
  1 - One or more gates failed
  2 - Error during execution
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # run command
    run_parser = subparsers.add_parser(
        "run",
        help="Execute full checkpoint audit (G1-G8)",
    )
    run_parser.add_argument(
        "--discord",
        action="store_true",
        help="Post results to Discord",
    )
    run_parser.set_defaults(func=cmd_run)

    # status command
    status_parser = subparsers.add_parser(
        "status",
        help="Show current checkpoint status",
    )
    status_parser.set_defaults(func=cmd_status)

    # history command
    history_parser = subparsers.add_parser(
        "history",
        help="Show checkpoint history",
    )
    history_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Number of checkpoints to show (default: 10)",
    )
    history_parser.set_defaults(func=cmd_history)

    # gate command
    gate_parser = subparsers.add_parser(
        "gate",
        help="Check specific gate (G1-G8)",
    )
    gate_parser.add_argument(
        "gate_id",
        help="Gate to check (G1, G2, G3, G4, G5, G6, G7, or G8)",
    )
    gate_parser.set_defaults(func=cmd_gate)

    # evidence command
    evidence_parser = subparsers.add_parser(
        "evidence",
        help="Collect and store evidence",
    )
    evidence_parser.set_defaults(func=cmd_evidence)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 0

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
