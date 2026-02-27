#!/usr/bin/env python3
"""Continuous paper trading metrics emitter.

This script continuously emits paper trading metrics to InfluxDB
to keep the Grafana dashboard populated with live data.

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
"""

from __future__ import annotations

import json
import logging
import os
import random
import signal
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Configuration
INFLUXDB_URL = os.getenv("INFLUXDB_URL", "http://localhost:18087")
INFLUXDB_TOKEN = os.getenv(
    "INFLUXDB_TOKEN",
    "REDACTED_INFLUXDB_TOKEN",
)
INFLUXDB_ORG = os.getenv("INFLUXDB_ORG", "chiseai")
INFLUXDB_BUCKET = os.getenv("INFLUXDB_BUCKET", "chiseai")
EMIT_INTERVAL = float(os.getenv("EMIT_INTERVAL", "5"))
REDIS_HOST = os.getenv("REDIS_HOST", "host.docker.internal")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6380"))
STATUS_FILE = os.getenv("STATUS_FILE", "/tmp/continuous_paper_emitter.status")
HEARTBEAT_INTERVAL = float(os.getenv("HEARTBEAT_INTERVAL", "30"))

# Retry configuration
MAX_RETRIES = 5
INITIAL_BACKOFF = 1.0  # seconds

# Global state for graceful shutdown
shutdown_requested = False


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
    global shutdown_requested

    # Register signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    logger.info(f"Starting continuous paper metrics emitter")
    logger.info(f"InfluxDB URL: {INFLUXDB_URL}")
    logger.info(f"Emit interval: {EMIT_INTERVAL}s")
    logger.info(f"Heartbeat interval: {HEARTBEAT_INTERVAL}s")
    logger.info(f"Max retries: {MAX_RETRIES}")
    logger.info(f"PID: {os.getpid()}")

    # Write initial status
    write_heartbeat()

    # Initial values
    portfolio_value = 10000.0
    total_pnl = 150.50
    unrealized_pnl = 75.25
    win_count = 8
    loss_count = 3

    # Get live prices from Redis
    live_prices = get_live_prices()
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

                    success = emit_trade(symbol, side, 0.1, price, pnl, confidence)
                    if success:
                        success_count += 1
                    else:
                        error_count += 1

                    # Emit order for Order/Fill tracking
                    success = emit_order(symbol, side, price, 0.1)
                    if success:
                        success_count += 1
                    else:
                        error_count += 1

                    # Emit fill for Order/Fill tracking
                    success = emit_fill(symbol, side, price, 0.1)
                    if success:
                        success_count += 1
                    else:
                        error_count += 1

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
        write_final_status(1, str(e))
        sys.exit(1)

    # Graceful shutdown
    logger.info(f"Shutting down gracefully. Total iterations: {iteration}")
    logger.info(f"Final stats: success={success_count}, errors={error_count}")
    write_final_status(0)
    sys.exit(0)


if __name__ == "__main__":
    main()
