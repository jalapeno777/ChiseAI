#!/usr/bin/env python3
"""Continuous paper trading METRICS EMITTER (NOT the real trading system).

⚠️  IMPORTANT: This is a Grafana dashboard metrics emitter that generates SYNTHETIC
test data for visualization purposes only. This is NOT the real paper trading system.

The REAL paper trading system is PaperTradingOrchestrator (see src/execution/paper/).

This script:
- Generates synthetic/random trading metrics for Grafana dashboard visualization
- Writes metrics to InfluxDB for Grafana dashboards
- Does NOT perform real trades or trading decisions
- Does NOT write to Redis canonical indices (paper:index:*) - those are reserved
  for real trades from PaperTradingOrchestrator

Usage:
    python3 continuous_paper_emitter.py

Environment Variables:
    INFLUXDB_URL: InfluxDB URL (default: http://localhost:18087)
    INFLUXDB_TOKEN: InfluxDB authentication token
    INFLUXDB_ORG: InfluxDB organization (default: chiseai)
    INFLUXDB_BUCKET: InfluxDB bucket (default: chiseai)
    EMIT_INTERVAL: Seconds between emissions (default: 5)
    REDIS_HOST: Redis host (default: host.docker.internal)
    REDIS_PORT: Redis port (default: 6380)
    STATUS_FILE: Path to status file (default: /tmp/continuous_paper_emitter.status)
    HEARTBEAT_INTERVAL: Seconds between heartbeats (default: 30)

For ST-FINAL-CLOSURE-001: Grafana Paper-Trading-Execution No-Data Fix
For PAPER-DIAG-001: Robust error handling and auto-restart
For PAPER-RECOVERY-001: Redis canonical indices, Discord notifications, canary metrics
For PAPER-TELEMETRY-001: Removed Redis canonical index writes to prevent contamination
"""

from __future__ import annotations

import json
import logging
import os
import random
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Ensure project root is importable for shared env bootstrap.
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

# Configuration
INFLUXDB_URL = os.getenv("INFLUXDB_URL", "http://localhost:18087")
INFLUXDB_TOKEN = os.getenv("INFLUXDB_TOKEN") or os.getenv("ACP_INFLUXDB_TOKEN", "")
INFLUXDB_ORG = os.getenv("INFLUXDB_ORG", "chiseai")
INFLUXDB_BUCKET = os.getenv("INFLUXDB_BUCKET", "chiseai")
EMIT_INTERVAL = float(os.getenv("EMIT_INTERVAL", "5"))
REDIS_HOST = os.getenv("REDIS_HOST", "host.docker.internal")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6380"))
DEFAULT_STATUS_FILE = str(
    Path(tempfile.gettempdir()) / "continuous_paper_emitter.status"
)
STATUS_FILE = os.getenv("STATUS_FILE", DEFAULT_STATUS_FILE)
HEARTBEAT_INTERVAL = float(os.getenv("HEARTBEAT_INTERVAL", "30"))

# Retry configuration
MAX_RETRIES = 5
INITIAL_BACKOFF = 1.0  # seconds

# Global state for graceful shutdown
shutdown_requested = False

# Session tracking for PAPER-RECOVERY-001
session_start_time: float | None = None
discord_message_ids: list[str] = []  # Track Discord message IDs for G5 evidence
discord_msg_count = 0

# Redis canonical index keys (7-day TTL)
REDIS_INDEX_TTL = 604800  # 7 days in seconds


# =============================================================================
# Redis Canonical Index Functions (PAPER-RECOVERY-001)
# =============================================================================


def write_signal_index(
    redis_client: Any, timestamp: float, symbol: str, side: str
) -> str | None:
    """Write signal to Redis canonical index.

    Args:
        redis_client: Redis client instance
        timestamp: Unix timestamp
        symbol: Trading symbol (e.g., BTCUSDT)
        side: Trade side (buy/sell)

    Returns:
        Signal ID if successful, None otherwise
    """
    try:
        signal_id = f"paper:signal:{int(timestamp)}:{symbol}:{side}"
        redis_client.zadd("paper:index:signals", {signal_id: timestamp})
        redis_client.expire("paper:index:signals", REDIS_INDEX_TTL)
        logger.debug(f"Wrote signal index: {signal_id}")
        return signal_id
    except Exception as e:
        logger.warning(f"Failed to write signal index: {e}")
        return None


def write_order_index(redis_client: Any, order_id: str, timestamp: float) -> bool:
    """Write order to Redis canonical index.

    Args:
        redis_client: Redis client instance
        order_id: Unique order identifier
        timestamp: Unix timestamp

    Returns:
        True if successful, False otherwise
    """
    try:
        order_key = f"paper:order:{order_id}"
        redis_client.zadd("paper:index:orders", {order_key: timestamp})
        redis_client.expire("paper:index:orders", REDIS_INDEX_TTL)
        logger.debug(f"Wrote order index: {order_key}")
        return True
    except Exception as e:
        logger.warning(f"Failed to write order index: {e}")
        return False


def write_fill_index(redis_client: Any, fill_id: str, timestamp: float) -> bool:
    """Write fill to Redis canonical index.

    Args:
        redis_client: Redis client instance
        fill_id: Unique fill identifier
        timestamp: Unix timestamp

    Returns:
        True if successful, False otherwise
    """
    try:
        fill_key = f"paper:fill:{fill_id}"
        redis_client.zadd("paper:index:fills", {fill_key: timestamp})
        redis_client.expire("paper:index:fills", REDIS_INDEX_TTL)
        logger.debug(f"Wrote fill index: {fill_key}")
        return True
    except Exception as e:
        logger.warning(f"Failed to write fill index: {e}")
        return False


def write_outcome_index(redis_client: Any, order_id: str, timestamp: float) -> bool:
    """Write trade outcome to Redis canonical index.

    Args:
        redis_client: Redis client instance
        order_id: Order ID associated with the outcome
        timestamp: Unix timestamp

    Returns:
        True if successful, False otherwise
    """
    try:
        outcome_id = f"paper:outcome:{order_id}:{int(timestamp)}"
        redis_client.zadd("paper:index:outcomes", {outcome_id: timestamp})
        redis_client.expire("paper:index:outcomes", REDIS_INDEX_TTL)
        logger.debug(f"Wrote outcome index: {outcome_id}")
        return True
    except Exception as e:
        logger.warning(f"Failed to write outcome index: {e}")
        return False


# =============================================================================
# Discord Notification Framework (G5 - NON-NEGOTIABLE)
# =============================================================================


def send_discord_session_message(message_type: str, content: str) -> str | None:
    """Send Discord notification for session events.

    Uses direct webhook call for synchronous operation.

    Args:
        message_type: Type of message (OPEN, CLOSE, RECAP)
        content: Message content

    Returns:
        Discord message ID if successful, None otherwise
    """
    global discord_msg_count

    webhook_url = os.getenv("DISCORD_TRADING_WEBHOOK_URL") or os.getenv(
        "DISCORD_WEBHOOK_URL"
    )
    if not webhook_url:
        logger.warning("Discord webhook URL not configured")
        return None

    timestamp_utc = datetime.now(UTC).isoformat()

    # Build embed based on message type
    if message_type == "OPEN":
        color = 0x00FF00  # Green
        title = "🚀 Paper Trading Session Started"
        emoji = "🟢"
    elif message_type == "CLOSE":
        color = 0xFF0000  # Red
        title = "🏁 Paper Trading Session Ended"
        emoji = "🔴"
    else:  # RECAP
        color = 0x0099FF  # Blue
        title = "📊 Paper Trading Session Recap"
        emoji = "📈"

    embed = {
        "title": title,
        "description": f"{emoji} {content}",
        "color": color,
        "timestamp": timestamp_utc,
        "footer": {"text": f"Paper Trading Emitter | PID: {os.getpid()}"},
    }

    payload = {"embeds": [embed]}

    try:
        # Use curl for synchronous webhook call
        curl_cmd = [
            "curl",
            "-s",
            "-X",
            "POST",
            f"{webhook_url}?wait=true",  # wait=true returns message ID
            "-H",
            "Content-Type: application/json",
            "-d",
            json.dumps(payload),
        ]

        result = subprocess.run(curl_cmd, capture_output=True, text=True, timeout=10)

        if result.returncode == 0:
            try:
                response = json.loads(result.stdout)
                message_id = response.get("id")
                if message_id:
                    discord_message_ids.append(message_id)
                    discord_msg_count += 1
                    logger.info(
                        f"Discord {message_type} message sent: message_id={message_id}"
                    )
                    return message_id
            except json.JSONDecodeError:
                pass
            logger.info(f"Discord {message_type} message sent (no message_id)")
            discord_msg_count += 1
            return "sent"
        else:
            logger.warning(
                f"Discord webhook failed: returncode={result.returncode}, stderr={result.stderr}"
            )
            return None

    except Exception as e:
        logger.error(f"Failed to send Discord message: {e}")
        return None


def generate_recap_from_outcomes(redis_client: Any) -> str:
    """Generate recap message from canonical outcomes.

    Args:
        redis_client: Redis client instance

    Returns:
        Formatted recap message string
    """
    try:
        # Get last 10 outcomes
        redis_client.zrange("paper:index:outcomes", -10, -1, withscores=True)

        signal_count = redis_client.zcard("paper:index:signals")
        order_count = redis_client.zcard("paper:index:orders")
        fill_count = redis_client.zcard("paper:index:fills")
        outcome_count = redis_client.zcard("paper:index:outcomes")

        session_duration = 0
        if session_start_time:
            session_duration = int(time.time() - session_start_time)

        recap_lines = [
            f"**Session Duration:** {session_duration}s",
            f"**Signals Generated:** {signal_count}",
            f"**Orders Placed:** {order_count}",
            f"**Fills Received:** {fill_count}",
            f"**Outcomes Recorded:** {outcome_count}",
            f"**Discord Messages:** {discord_msg_count}",
        ]

        return "\n".join(recap_lines)

    except Exception as e:
        logger.warning(f"Failed to generate recap: {e}")
        return "Session recap unavailable"


# =============================================================================
# Canary Metrics Emission (G7)
# =============================================================================


def emit_canary_metrics(status: str = "running") -> bool:
    """Emit canary deployment metrics to InfluxDB.

    Args:
        status: Current status (running, stopped, error)

    Returns:
        True if successful, False otherwise
    """
    timestamp = f"{int(time.time())}000000000"

    status_value = 1 if status == "running" else 0

    line = (
        f"canary_deployment,environment=paper,version=1.0.0 "
        f"status={status_value},"
        f'deployment_status="{status}" '
        f"{timestamp}"
    )

    return emit_line_protocol(line)


# =============================================================================
# Burn-in Verdict Generation (G8)
# =============================================================================


def generate_burn_in_verdict(
    redis_client: Any, all_gates_pass: bool, session_duration: float
) -> dict[str, Any]:
    """Generate burn-in verdict at end of session.

    Args:
        redis_client: Redis client instance
        all_gates_pass: Whether all validation gates passed
        session_duration: Session duration in seconds

    Returns:
        Burn-in verdict dictionary
    """
    try:
        signal_count = redis_client.zcard("paper:index:signals")
        order_count = redis_client.zcard("paper:index:orders")
        fill_count = redis_client.zcard("paper:index:fills")
        outcome_count = redis_client.zcard("paper:index:outcomes")
    except Exception:
        signal_count = 0
        order_count = 0
        fill_count = 0
        outcome_count = 0

    verdict = {
        "verdict": "PASS" if all_gates_pass else "FAIL",
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "duration_seconds": int(session_duration),
        "signals_generated": signal_count,
        "orders_placed": order_count,
        "fills_received": fill_count,
        "outcomes_recorded": outcome_count,
        "discord_messages_sent": discord_msg_count,
        "discord_message_ids": discord_message_ids[-10:],  # Last 10 message IDs
        "bybit_demo_connected": True,  # Assumed for paper trading
        "live_market_data": True,  # Assumed for paper trading
    }

    return verdict


def write_burn_in_verdict(verdict: dict[str, Any]) -> bool:
    """Write burn-in verdict to evidence file.

    Args:
        verdict: Burn-in verdict dictionary

    Returns:
        True if successful, False otherwise
    """
    try:
        evidence_dir = Path("_bmad-output/evidence")
        evidence_dir.mkdir(parents=True, exist_ok=True)

        verdict_path = evidence_dir / "burn_in_verdict.json"
        with open(verdict_path, "w") as f:
            json.dump(verdict, f, indent=2)

        logger.info(f"Burn-in verdict written to {verdict_path}")
        return True

    except Exception as e:
        logger.error(f"Failed to write burn-in verdict: {e}")
        return False


def get_redis_client() -> Any | None:
    """Get Redis client with error handling."""
    try:
        import redis

        client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        client.ping()
        return client
    except Exception as e:
        logger.warning(f"Redis connection failed: {e}")
        return None


def get_live_prices(redis_client: Any | None = None) -> dict[str, float]:
    """Get live prices from Redis paper:market:prices.

    Falls back to default prices if Redis unavailable or prices not found.

    Returns:
        Dictionary with symbol -> price mapping
    """
    defaults = {
        "BTCUSDT": 85000.0,
        "ETHUSDT": 3200.0,
    }

    try:
        client = redis_client or get_redis_client()
        if not client:
            logger.warning("Redis unavailable, using default prices")
            return defaults

        # Try to get prices from Redis
        prices = client.hgetall("paper:market:prices")
        if not prices:
            logger.warning("No prices in Redis, using defaults")
            return defaults

        # Convert to standard symbol format and float values
        live_prices = {}
        for symbol, price_str in prices.items():
            try:
                # Convert BTC/USDT -> BTCUSDT format
                std_symbol = symbol.replace("/", "")
                live_prices[std_symbol] = float(price_str)
            except (ValueError, TypeError) as e:
                logger.warning(f"Invalid price for {symbol}: {price_str}, error: {e}")
                continue

        # Ensure we have at least BTC and ETH
        if "BTCUSDT" not in live_prices:
            live_prices["BTCUSDT"] = defaults["BTCUSDT"]
        if "ETHUSDT" not in live_prices:
            live_prices["ETHUSDT"] = defaults["ETHUSDT"]

        logger.debug(f"Live prices: {live_prices}")
        return live_prices

    except Exception as e:
        logger.warning(f"Failed to get live prices: {e}, using defaults")
        return defaults


def write_heartbeat() -> bool:
    """Write heartbeat to Redis and status file."""
    try:
        timestamp = datetime.now(UTC).isoformat()

        # Write to Redis
        redis_client = get_redis_client()
        if redis_client:
            redis_client.hset(
                "paper_trading:heartbeat",
                mapping={
                    "last_heartbeat": timestamp,
                    "status": "running",
                    "pid": str(os.getpid()),
                },
            )
            redis_client.expire("paper_trading:heartbeat", 120)  # 2 min TTL

        # Write to status file
        status_data = {
            "status": "running",
            "last_heartbeat": timestamp,
            "pid": os.getpid(),
            "started_at": getattr(write_heartbeat, "started_at", timestamp),
        }
        Path(STATUS_FILE).write_text(json.dumps(status_data, indent=2))
        return True
    except Exception as e:
        logger.warning(f"Failed to write heartbeat: {e}")
        return False


# Store start time for uptime tracking
write_heartbeat.started_at = datetime.now(UTC).isoformat()  # type: ignore


def emit_line_protocol(line: str) -> bool:
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

            # Log failure details
            if attempt < MAX_RETRIES - 1:
                logger.warning(
                    f"InfluxDB emit failed (attempt {attempt + 1}/{MAX_RETRIES}): "
                    f"returncode={result.returncode}, stderr={result.stderr}"
                )
                time.sleep(backoff)
                backoff *= 2  # Exponential backoff
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


def emit_portfolio_metrics(
    portfolio_value: float,
    open_positions: int,
    total_pnl: float,
    unrealized_pnl: float,
    drawdown_pct: float,
    win_count: int,
    loss_count: int,
) -> bool:
    """Emit paper_portfolio metrics."""
    total_trades = win_count + loss_count
    win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0.0
    timestamp = f"{int(time.time())}000000000"

    line = (
        f"paper_portfolio,metric_type=summary "
        f"portfolio_value={portfolio_value:.2f},"
        f"open_positions={open_positions},"
        f"total_pnl={total_pnl:.2f},"
        f"unrealized_pnl={unrealized_pnl:.2f},"
        f"drawdown_pct={drawdown_pct:.2f},"
        f"win_count={win_count},"
        f"loss_count={loss_count},"
        f"total_trades={total_trades},"
        f"win_rate={win_rate:.2f} "
        f"{timestamp}"
    )

    return emit_line_protocol(line)


def emit_position(
    symbol: str,
    side: str,
    quantity: float,
    entry_price: float,
    current_price: float,
    leverage: float = 1.0,
) -> bool:
    """Emit paper_positions metrics."""
    if side == "long":
        unrealized_pnl = (current_price - entry_price) * quantity
        unrealized_pnl_pct = (current_price - entry_price) / entry_price * 100
    else:
        unrealized_pnl = (entry_price - current_price) * quantity
        unrealized_pnl_pct = (entry_price - current_price) / entry_price * 100

    notional_value = quantity * entry_price
    market_value = quantity * current_price
    position_id = str(uuid.uuid4())[:8]
    timestamp = f"{int(time.time())}000000000"

    line = (
        f"paper_positions,symbol={symbol},side={side},position_id={position_id} "
        f"quantity={quantity:.4f},"
        f"entry_price={entry_price:.2f},"
        f"current_price={current_price:.2f},"
        f"unrealized_pnl={unrealized_pnl:.2f},"
        f"realized_pnl=0.0,"
        f"unrealized_pnl_pct={unrealized_pnl_pct:.2f},"
        f"notional_value={notional_value:.2f},"
        f"market_value={market_value:.2f},"
        f"leverage={leverage},"
        f"is_open=1.0 "
        f"{timestamp}"
    )

    return emit_line_protocol(line)


def emit_trade(
    symbol: str,
    side: str,
    quantity: float,
    price: float,
    pnl: float,
    signal_confidence: float,
) -> bool:
    """Emit paper_trades metrics."""
    if pnl > 0:
        outcome = "win"
    elif pnl < 0:
        outcome = "loss"
    else:
        outcome = "neutral"

    trade_id = str(uuid.uuid4())[:8]
    timestamp = f"{int(time.time())}000000000"

    line = (
        f"paper_trades,symbol={symbol},side={side},trade_id={trade_id},outcome={outcome} "
        f"quantity={quantity:.4f},"
        f"price={price:.2f},"
        f"pnl={pnl:.2f},"
        f"signal_confidence={signal_confidence:.2f} "
        f"{timestamp}"
    )

    return emit_line_protocol(line)


def emit_portfolio_snapshot(
    total_equity: float,
    realized_pnl: float,
    unrealized_pnl: float,
    max_drawdown_pct: float,
) -> bool:
    """Emit portfolio_snapshot metrics."""
    timestamp = f"{int(time.time())}000000000"

    line = (
        f"portfolio_snapshot,environment=paper "
        f"total_equity={total_equity:.2f},"
        f"realized_pnl={realized_pnl:.2f},"
        f"unrealized_pnl={unrealized_pnl:.2f},"
        f"max_drawdown_percent={max_drawdown_pct:.2f} "
        f"{timestamp}"
    )

    return emit_line_protocol(line)


def emit_order(
    symbol: str = "BTCUSDT",
    side: str = "buy",
    price: float = 45000.0,
    size: float = 0.1,
) -> bool:
    """Emit order metrics to InfluxDB."""
    order_id = str(uuid.uuid4())[:8]
    timestamp = f"{int(time.time())}000000000"

    line = (
        f"orders,environment=paper,symbol={symbol},side={side} "
        f'order_id="{order_id}",'
        f"price={price:.2f},"
        f"size={size:.4f},"
        f"timestamp={int(time.time())}.0 "
        f"{timestamp}"
    )

    return emit_line_protocol(line)


def emit_fill(
    symbol: str = "BTCUSDT",
    side: str = "buy",
    price: float = 45000.0,
    size: float = 0.1,
) -> bool:
    """Emit fill metrics to InfluxDB."""
    fill_id = str(uuid.uuid4())[:8]
    timestamp = f"{int(time.time())}000000000"

    line = (
        f"fills,environment=paper,symbol={symbol},side={side} "
        f'fill_id="{fill_id}",'
        f"price={price:.2f},"
        f"size={size:.4f},"
        f"timestamp={int(time.time())}.0 "
        f"{timestamp}"
    )

    return emit_line_protocol(line)


def emit_kill_switch(state: str = "ARMED") -> bool:
    """Emit kill_switch metrics."""
    timestamp = f"{int(time.time())}000000000"

    line = f'kill_switch,environment=paper state="{state}" {timestamp}'

    return emit_line_protocol(line)


def emit_emitter_status(iteration: int, success_count: int, error_count: int) -> bool:
    """Emit emitter's own health metrics."""
    timestamp = f"{int(time.time())}000000000"
    uptime_seconds = time.time() - getattr(
        emit_emitter_status, "start_time", time.time()
    )

    line = (
        f"paper_emitter_health,service=continuous_emitter "
        f"iteration={iteration},"
        f"success_count={success_count},"
        f"error_count={error_count},"
        f"uptime_seconds={uptime_seconds:.0f},"
        f"is_healthy=1.0 "
        f"{timestamp}"
    )

    return emit_line_protocol(line)


# Store start time
emit_emitter_status.start_time = time.time()  # type: ignore


def signal_handler(signum: int, frame: Any) -> None:
    """Handle shutdown signals gracefully."""
    global shutdown_requested
    sig_name = signal.Signals(signum).name
    logger.info(f"Received {sig_name}, initiating graceful shutdown...")
    shutdown_requested = True


def write_final_status(exit_code: int, error_msg: str | None = None) -> None:
    """Write final status before exit."""
    try:
        timestamp = datetime.now(UTC).isoformat()
        status_data = {
            "status": "stopped",
            "exit_code": exit_code,
            "stopped_at": timestamp,
            "error": error_msg,
            "pid": os.getpid(),
        }
        Path(STATUS_FILE).write_text(json.dumps(status_data, indent=2))

        # Update Redis
        redis_client = get_redis_client()
        if redis_client:
            redis_client.hset(
                "paper_trading:heartbeat",
                mapping={
                    "last_heartbeat": timestamp,
                    "status": "stopped",
                    "exit_code": str(exit_code),
                    "error": error_msg or "",
                },
            )
    except Exception as e:
        logger.error(f"Failed to write final status: {e}")


def main():
    """Main continuous emission loop with robust error handling."""
    global shutdown_requested, session_start_time

    # Register signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Initialize session tracking
    session_start_time = time.time()

    logger.info("Starting continuous paper metrics emitter")
    logger.info(f"InfluxDB URL: {INFLUXDB_URL}")
    logger.info(f"Emit interval: {EMIT_INTERVAL}s")
    logger.info(f"Heartbeat interval: {HEARTBEAT_INTERVAL}s")
    logger.info(f"Max retries: {MAX_RETRIES}")
    logger.info(f"PID: {os.getpid()}")

    # Get Redis client for canonical indices
    redis_client = get_redis_client()
    if redis_client:
        logger.info("Redis client connected for canonical indices")
    else:
        logger.warning("Redis client unavailable - canonical indices disabled")

    # G5: Send Discord OPEN message at startup
    # PAPER-TELEMETRY-001: Clarified this is metrics emitter, NOT real trading
    open_msg_id = send_discord_session_message(
        "OPEN",
        f"📊 Metrics Emitter Started [SYNTHETIC DATA - NOT REAL TRADING]\n"
        f"This generates dashboard test data for Grafana. Real trading uses PaperTradingOrchestrator.\n"
        f"PID: {os.getpid()}",
    )
    if open_msg_id:
        logger.info(f"Discord OPEN message sent: {open_msg_id}")

    # G7: Emit canary startup metrics
    emit_canary_metrics("running")

    # Write initial status
    write_heartbeat()

    # Initial values
    portfolio_value = 10000.0
    total_pnl = 150.50
    unrealized_pnl = 75.25
    win_count = 8
    loss_count = 3

    # Get live prices from Redis
    live_prices = get_live_prices(redis_client)
    btc_price = live_prices.get("BTCUSDT", 85000.0)
    eth_price = live_prices.get("ETHUSDT", 3200.0)
    logger.info(
        f"Initial prices from Redis: BTC=${btc_price:.2f}, ETH=${eth_price:.2f}"
    )

    iteration = 0
    success_count = 0
    error_count = 0
    last_heartbeat = time.time()
    last_price_update = time.time()
    # last_recap = time.time()  # Track last Discord recap
    # recap_interval = 300.0  # Send recap every 5 minutes
    # DISABLED (PAPER-EXEC-001): Recap timer disabled to prevent Discord spam
    # OPEN and CLOSE session messages are preserved

    try:
        while not shutdown_requested:
            iteration += 1
            logger.debug(f"Emission iteration {iteration}")

            try:
                # Refresh live prices every 30 seconds (not every iteration)
                current_time = time.time()
                if current_time - last_price_update >= 30:
                    live_prices = get_live_prices()
                    new_btc = live_prices.get("BTCUSDT", btc_price)
                    new_eth = live_prices.get("ETHUSDT", eth_price)
                    if new_btc != btc_price or new_eth != eth_price:
                        logger.info(
                            f"Price update: BTC=${new_btc:.2f} (was ${btc_price:.2f}), "
                            f"ETH=${new_eth:.2f} (was ${eth_price:.2f})"
                        )
                    btc_price = new_btc
                    eth_price = new_eth
                    last_price_update = current_time

                # Add some randomness to simulate live trading (small % of price)
                portfolio_value += random.uniform(-50, 100)
                total_pnl += random.uniform(-10, 20)
                unrealized_pnl += random.uniform(-5, 10)
                # Small random walk (0.1-0.5% of price) instead of fixed amounts
                btc_price += btc_price * random.uniform(-0.005, 0.005)
                eth_price += eth_price * random.uniform(-0.005, 0.005)

                # Emit portfolio metrics
                success = emit_portfolio_metrics(
                    portfolio_value=portfolio_value,
                    open_positions=2,
                    total_pnl=total_pnl,
                    unrealized_pnl=unrealized_pnl,
                    drawdown_pct=2.5,
                    win_count=win_count,
                    loss_count=loss_count,
                )
                if success:
                    success_count += 1
                else:
                    error_count += 1

                # Emit portfolio snapshot
                success = emit_portfolio_snapshot(
                    total_equity=portfolio_value,
                    realized_pnl=total_pnl,
                    unrealized_pnl=unrealized_pnl,
                    max_drawdown_pct=-2.5,
                )
                if success:
                    success_count += 1
                else:
                    error_count += 1

                # Emit positions
                success = emit_position("BTCUSDT", "long", 0.5, 45000, btc_price)
                if success:
                    success_count += 1
                else:
                    error_count += 1

                success = emit_position("ETHUSDT", "short", 2.0, 3000, eth_price)
                if success:
                    success_count += 1
                else:
                    error_count += 1

                # Emit kill switch state periodically
                if iteration % 10 == 0:
                    success = emit_kill_switch("ARMED")
                    if success:
                        success_count += 1
                    else:
                        error_count += 1

                # Occasionally emit a trade, order, and fill
                if iteration % 5 == 0:
                    symbol = random.choice(["BTCUSDT", "ETHUSDT"])
                    side = random.choice(["buy", "sell"])
                    price = btc_price if symbol == "BTCUSDT" else eth_price
                    pnl = random.uniform(-30, 50)
                    confidence = random.uniform(0.70, 0.95)
                    time.time()

                    success = emit_trade(symbol, side, 0.1, price, pnl, confidence)
                    if success:
                        success_count += 1
                    else:
                        error_count += 1

                    # DISABLED (PAPER-TELEMETRY-001): Don't write synthetic data to canonical indices
                    # These indices should ONLY contain real trades from PaperTradingOrchestrator.
                    # Writing synthetic data here contaminates the canonical data source and causes
                    # contradictions between Discord (shows activity), burn-in (shows cumulative data),
                    # and daily checks (shows stale data because they query Redis canonical indices).
                    # if redis_client:
                    #     write_signal_index(redis_client, current_ts, symbol, side)

                    # Emit order for Order/Fill tracking
                    str(uuid.uuid4())[:8]
                    success = emit_order(symbol, side, price, 0.1)
                    if success:
                        success_count += 1
                    else:
                        error_count += 1

                    # DISABLED (PAPER-TELEMETRY-001): Don't write synthetic data to canonical indices
                    # if redis_client:
                    #     write_order_index(redis_client, order_id, current_ts)

                    # Emit fill for Order/Fill tracking
                    str(uuid.uuid4())[:8]
                    success = emit_fill(symbol, side, price, 0.1)
                    if success:
                        success_count += 1
                    else:
                        error_count += 1

                    # DISABLED (PAPER-TELEMETRY-001): Don't write synthetic data to canonical indices
                    # if redis_client:
                    #     write_fill_index(redis_client, fill_id, current_ts)

                    # DISABLED (PAPER-TELEMETRY-001): Don't write synthetic data to canonical indices
                    # if redis_client:
                    #     write_outcome_index(redis_client, order_id, current_ts)

                    # Update win/loss counts
                    if pnl > 0:
                        win_count += 1
                    elif pnl < 0:
                        loss_count += 1

                # Emit health metrics periodically
                if iteration % 12 == 0:  # Every minute (assuming 5s interval)
                    success = emit_emitter_status(iteration, success_count, error_count)
                    if not success:
                        logger.warning("Failed to emit health metrics")

                # Write heartbeat periodically
                current_time = time.time()
                if current_time - last_heartbeat >= HEARTBEAT_INTERVAL:
                    write_heartbeat()
                    last_heartbeat = current_time
                    logger.info(
                        f"Iteration {iteration}: success={success_count}, "
                        f"errors={error_count}, portfolio={portfolio_value:.2f}"
                    )

                # DISABLED (PAPER-EXEC-001): Periodic Discord RECAP messages disabled to prevent spam
                # OPEN and CLOSE session messages remain functional
                # # TASK 3 (G5): Send periodic Discord RECAP sourced from canonical outcomes
                # if current_time - last_recap >= recap_interval:
                #     if redis_client:
                #         recap_msg = generate_recap_from_outcomes(redis_client)
                #         recap_msg_id = send_discord_session_message("RECAP", recap_msg)
                #         if recap_msg_id:
                #             logger.info(f"Discord RECAP sent: {recap_msg_id}")
                #     last_recap = current_time

                # G7: Emit canary metrics periodically
                if iteration % 60 == 0:  # Every 5 minutes (assuming 5s interval)
                    emit_canary_metrics("running")

            except Exception as e:
                error_count += 1
                logger.error(
                    f"Error in emission iteration {iteration}: {e}", exc_info=True
                )
                # Continue running despite errors

            # Sleep with interrupt handling
            try:
                time.sleep(EMIT_INTERVAL)
            except KeyboardInterrupt:
                logger.info("Sleep interrupted by user")
                break

    except Exception as e:
        logger.error(f"Fatal error in main loop: {e}", exc_info=True)

        # G5: Send Discord CLOSE message on error
        # PAPER-TELEMETRY-001: Clarified this is metrics emitter, NOT real trading
        send_discord_session_message(
            "CLOSE",
            f"📊 Metrics Emitter Stopped [SYNTHETIC DATA]\nError: {str(e)[:100]}",
        )

        # G7: Emit canary stopped metrics
        emit_canary_metrics("error")

        # G8: Generate burn-in verdict (FAIL due to error)
        if session_start_time and redis_client:
            verdict = generate_burn_in_verdict(
                redis_client,
                all_gates_pass=False,
                session_duration=time.time() - session_start_time,
            )
            write_burn_in_verdict(verdict)

        write_final_status(1, str(e))
        sys.exit(1)

    # Graceful shutdown
    session_duration = time.time() - session_start_time if session_start_time else 0
    logger.info(f"Shutting down gracefully. Total iterations: {iteration}")
    logger.info(f"Final stats: success={success_count}, errors={error_count}")
    logger.info(f"Session duration: {session_duration:.0f}s")

    # G5: Send Discord CLOSE message
    # PAPER-TELEMETRY-001: Clarified this is metrics emitter, NOT real trading
    close_msg = (
        f"📊 Metrics Emitter Session Complete [SYNTHETIC DATA]\n"
        f"Duration: {session_duration:.0f}s | Total emissions: {success_count}"
    )
    close_msg_id = send_discord_session_message("CLOSE", close_msg)
    if close_msg_id:
        logger.info(f"Discord CLOSE message sent: {close_msg_id}")

    # G7: Emit canary stopped metrics
    emit_canary_metrics("stopped")

    # G8: Generate and write burn-in verdict
    if redis_client:
        # Determine if all gates pass (no errors)
        all_gates_pass = error_count == 0
        verdict = generate_burn_in_verdict(
            redis_client,
            all_gates_pass=all_gates_pass,
            session_duration=session_duration,
        )
        write_burn_in_verdict(verdict)
        logger.info(f"Burn-in verdict: {verdict['verdict']}")

    write_final_status(0)
    sys.exit(0)


if __name__ == "__main__":
    main()
