#!/usr/bin/env python3
"""Dashboard Emitter - consumes signals from Redis and emits to InfluxDB for dashboard visualization.

This service:
- Reads signals from Redis stream (chiseai:signals:dashboard)
- Emits signal metrics to InfluxDB for Grafana dashboard visualization
- Provides health check endpoint for container orchestration

Environment Variables:
    INFLUXDB_URL: InfluxDB URL (default: http://chiseai-influxdb:18087)
    INFLUXDB_TOKEN: InfluxDB authentication token (REQUIRED)
    INFLUXDB_ORG: InfluxDB organization (default: chiseai)
    INFLUXDB_BUCKET: InfluxDB bucket (default: chiseai)
    REDIS_HOST: Redis host (default: host.docker.internal)
    REDIS_PORT: Redis port (default: 6380)
    REDIS_DB: Redis DB (default: 0)
    POLL_INTERVAL: Seconds between stream polls (default: 1.0)
    HEALTHCHECK_INTERVAL: Seconds between health checks (default: 30)

For PAPER-006: Containerize Dashboard Emitter
"""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from src.config.env_loader import bootstrap_environment

    bootstrap_environment()
except Exception:
    pass

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Configuration - fail fast if INFLUXDB_TOKEN is missing
INFLUXDB_URL = os.getenv("INFLUXDB_URL", "http://chiseai-influxdb:18087")
INFLUXDB_TOKEN = os.getenv("INFLUXDB_TOKEN", "")
INFLUXDB_ORG = os.getenv("INFLUXDB_ORG", "chiseai")
INFLUXDB_BUCKET = os.getenv("INFLUXDB_BUCKET", "chiseai")
REDIS_HOST = os.getenv("REDIS_HOST", "chiseai-redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6380"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "1.0"))
HEALTHCHECK_INTERVAL = float(os.getenv("HEALTHCHECK_INTERVAL", "30"))

# Redis stream key (matches DashboardEmitter.STREAM_KEY)
STREAM_KEY = "chiseai:signals:dashboard"

# Retry configuration
MAX_RETRIES = 5
INITIAL_BACKOFF = 1.0

# Global shutdown flag
shutdown_requested = False


def validate_config() -> None:
    """Validate required configuration. Fails fast if INFLUXDB_TOKEN is missing."""
    if not INFLUXDB_TOKEN:
        logger.error("INFLUXDB_TOKEN environment variable is not set. Exiting.")
        sys.exit(1)
    logger.info(f"Configuration validated. InfluxDB: {INFLUXDB_URL}")


def signal_handler(signum: int, frame: Any) -> None:
    """Handle shutdown signals gracefully."""
    global shutdown_requested
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    shutdown_requested = True


# Register signal handlers
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)


# =============================================================================
# Redis Stream Consumer
# =============================================================================


def get_redis_client() -> Any:
    """Create and return a Redis client."""
    import redis

    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        decode_responses=True,
    )


def read_from_stream(
    client: Any, last_id: str = "0"
) -> tuple[list[tuple[str, dict[str, str]]], str]:
    """Read new entries from Redis stream.

    Args:
        client: Redis client
        last_id: Last processed stream entry ID (starting from "0")

    Returns:
        Tuple of (entries, new_last_id) where entries are (id, data) tuples
    """
    try:
        # Use XREAD to read new entries from stream
        stream_data = client.xread(
            {STREAM_KEY: last_id}, count=100, block=int(POLL_INTERVAL * 1000)
        )

        if not stream_data:
            return [], last_id

        entries = []
        for stream_name, messages in stream_data:
            for msg_id, data in messages:
                entries.append((msg_id, data))
                last_id = msg_id

        return entries, last_id
    except Exception as e:
        logger.warning(f"Error reading from stream: {e}")
        return [], last_id


# =============================================================================
# InfluxDB Emitter
# =============================================================================


def emit_to_influxdb(line: str) -> bool:
    """Emit a single line protocol line to InfluxDB with retry logic."""
    curl_cmd = [
        "curl",
        "-s",
        "-X",
        "POST",
        f"{INFLUXDB_URL}/api/v2/write?org={INFLUXDB_ORG}&bucket={INFLUXDB_BUCKET}&precision=ns",
        "-H",
        f"Authorization: Token {INFLUXDB_TOKEN}",
        "-H",
        "Content-Type: text/plain; charset=utf-8",
        "--data-raw",
        line,
    ]

    backoff = INITIAL_BACKOFF
    for attempt in range(MAX_RETRIES):
        try:
            result = subprocess.run(
                curl_cmd, capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0 and not result.stderr:
                return True

            if attempt < MAX_RETRIES - 1:
                logger.warning(
                    f"InfluxDB emit failed (attempt {attempt + 1}/{MAX_RETRIES}): "
                    f"returncode={result.returncode}, stderr={result.stderr}"
                )
                time.sleep(backoff)
                backoff *= 2
            else:
                logger.error(
                    f"InfluxDB emit failed after {MAX_RETRIES} attempts: "
                    f"returncode={result.returncode}, stderr={result.stderr}"
                )
        except subprocess.TimeoutExpired:
            logger.warning(
                f"InfluxDB emit timeout (attempt {attempt + 1}/{MAX_RETRIES})"
            )
            if attempt < MAX_RETRIES - 1:
                time.sleep(backoff)
                backoff *= 2
        except Exception as e:
            logger.error(f"Failed to emit: {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(backoff)
                backoff *= 2
            else:
                return False

    return False


def emit_signal_to_influxdb(signal_data: dict[str, Any]) -> bool:
    """Emit a signal to InfluxDB as line protocol.

    Args:
        signal_data: Signal payload dictionary

    Returns:
        True if emission succeeded
    """
    try:
        # Parse timestamp or use current time
        timestamp_str = signal_data.get("timestamp", "")
        if timestamp_str:
            dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            timestamp = int(dt.timestamp() * 1e9)
        else:
            timestamp = int(time.time() * 1e9)

        token = signal_data.get("token", "unknown").replace("/", "_")
        direction = signal_data.get("direction", "neutral")
        signal_id = signal_data.get("id", "unknown")[:8]  # Shorten for tag
        confidence = float(signal_data.get("confidence", 0))
        score = float(signal_data.get("score", 0))
        status = signal_data.get("status", "unknown")
        timeframe = signal_data.get("timeframe", "unknown")
        latency_ms = float(signal_data.get("latency_ms", 0))

        # Optional fields
        stop_loss = signal_data.get("stop_loss")
        take_profit = signal_data.get("take_profit")
        risk_reward = signal_data.get("risk_reward_ratio", 0)

        # Build line protocol
        # Use signal_metrics as measurement
        line_parts = [
            "signal_metrics",
            f"token={token}",
            f"direction={direction}",
            f"signal_id={signal_id}",
            f"status={status}",
            f"timeframe={timeframe}",
        ]

        # Add numeric fields
        fields = [
            f"confidence={confidence}",
            f"score={score}",
            f"latency_ms={latency_ms}",
            f"risk_reward_ratio={risk_reward}",
        ]

        if stop_loss is not None:
            fields.append(f"stop_loss={stop_loss}")
        if take_profit is not None:
            fields.append(f"take_profit={take_profit}")

        line = f"{','.join(line_parts)} {','.join(fields)} {timestamp}"

        return emit_to_influxdb(line)

    except Exception as e:
        logger.error(f"Error formatting signal for InfluxDB: {e}")
        return False


# =============================================================================
# Health Check
# =============================================================================


def check_redis_health(client: Any) -> bool:
    """Check Redis connectivity."""
    try:
        client.ping()
        return True
    except Exception as e:
        logger.warning(f"Redis health check failed: {e}")
        return False


def check_influxdb_health() -> bool:
    """Check InfluxDB connectivity."""
    try:
        curl_cmd = [
            "curl",
            "-s",
            "-o",
            "/dev/null",
            "-w",
            "%{http_code}",
            f"{INFLUXDB_URL}/health",
            "-H",
            f"Authorization: Token {INFLUXDB_TOKEN}",
        ]
        result = subprocess.run(curl_cmd, capture_output=True, text=True, timeout=10)
        return result.returncode == 0 and result.stdout.strip() in ("200", "204")
    except Exception as e:
        logger.warning(f"InfluxDB health check failed: {e}")
        return False


def run_health_check(client: Any) -> bool:
    """Run full health check (Redis + InfluxDB)."""
    redis_ok = check_redis_health(client)
    influx_ok = check_influxdb_health()

    if redis_ok and influx_ok:
        logger.debug("Health check passed: Redis OK, InfluxDB OK")
        return True
    else:
        logger.warning(
            f"Health check failed: Redis={'OK' if redis_ok else 'FAIL'}, "
            f"InfluxDB={'OK' if influx_ok else 'FAIL'}"
        )
        return False


# =============================================================================
# Main Loop
# =============================================================================


def main() -> None:
    """Main entry point for dashboard emitter."""
    global shutdown_requested

    logger.info("Starting Dashboard Emitter...")

    # Fail fast if INFLUXDB_TOKEN is missing
    validate_config()

    # Create Redis client
    redis_client = get_redis_client()

    # Track last processed stream ID
    last_stream_id = "0"
    processed_count = 0
    last_health_check = time.time()

    logger.info(f"Connecting to Redis at {REDIS_HOST}:{REDIS_PORT}")
    logger.info(f"Streaming from: {STREAM_KEY}")
    logger.info(f"Emitting to InfluxDB at {INFLUXDB_URL}")

    while not shutdown_requested:
        try:
            # Read new signals from stream
            entries, last_stream_id = read_from_stream(redis_client, last_stream_id)

            # Process entries
            for entry_id, data in entries:
                try:
                    # Parse JSON data
                    if "data" in data:
                        signal_payload = json.loads(data["data"])
                    else:
                        signal_payload = data

                    # Emit to InfluxDB
                    if emit_signal_to_influxdb(signal_payload):
                        processed_count += 1
                        logger.debug(
                            f"Emitted signal: {signal_payload.get('token', 'unknown')} "
                            f"[{signal_payload.get('direction', '?')}]"
                        )
                    else:
                        logger.warning(f"Failed to emit signal {entry_id}")

                except json.JSONDecodeError as e:
                    logger.warning(f"Invalid JSON in stream entry {entry_id}: {e}")
                except Exception as e:
                    logger.error(f"Error processing entry {entry_id}: {e}")

            # Periodic health check
            now = time.time()
            if now - last_health_check >= HEALTHCHECK_INTERVAL:
                if run_health_check(redis_client):
                    logger.info(
                        f"Health check OK | Processed: {processed_count} signals | "
                        f"Stream position: {last_stream_id}"
                    )
                last_health_check = now

        except Exception as e:
            logger.error(f"Main loop error: {e}")
            time.sleep(5)  # Back off on error

    logger.info(f"Shutting down. Processed {processed_count} signals total.")


if __name__ == "__main__":
    main()
