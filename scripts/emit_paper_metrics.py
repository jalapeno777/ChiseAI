#!/usr/bin/env python3
"""Paper trading metrics emitter for Grafana dashboard.

This script emits paper trading metrics to InfluxDB so the Grafana dashboard
can display live trading data. It creates both initial test data and can
run continuously to emit periodic metrics.

Usage:
    # Emit initial test data (one-time)
    python3 emit_paper_metrics.py --init

    # Run continuous emitter (emit every 5 seconds)
    python3 emit_paper_metrics.py --continuous --interval 5

    # Emit single test trade
    python3 emit_paper_metrics.py --test-trade

For ST-FINAL-CLOSURE-001: Grafana Paper-Trading-Execution No-Data Fix
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import uuid
from datetime import UTC, datetime
from typing import Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# InfluxDB configuration from environment or defaults
INFLUXDB_URL = os.getenv("INFLUXDB_URL", "http://localhost:18087")
INFLUXDB_TOKEN = os.getenv(
    "INFLUXDB_TOKEN",
    "REDACTED_INFLUXDB_TOKEN",
)
INFLUXDB_ORG = os.getenv("INFLUXDB_ORG", "chiseai")
INFLUXDB_BUCKET = os.getenv("INFLUXDB_BUCKET", "chiseai")


class PaperMetricsEmitter:
    """Emit paper trading metrics to InfluxDB."""

    def __init__(
        self,
        url: str = INFLUXDB_URL,
        token: str = INFLUXDB_TOKEN,
        org: str = INFLUXDB_ORG,
        bucket: str = INFLUXDB_BUCKET,
    ):
        self.url = url
        self.token = token
        self.org = org
        self.bucket = bucket
        self._client: Any | None = None
        self._write_api: Any | None = None

    async def _get_client(self) -> Any:
        """Get or create InfluxDB client."""
        if self._client is None:
            from influxdb_client import InfluxDBClient

            self._client = InfluxDBClient(
                url=self.url,
                token=self.token,
                org=self.org,
            )
        return self._client

    async def _get_write_api(self) -> Any:
        """Get or create write API."""
        if self._write_api is None:
            client = await self._get_client()
            self._write_api = client.write_api()
        return self._write_api

    async def emit_portfolio_metrics(
        self,
        portfolio_value: float = 10000.0,
        open_positions: int = 2,
        total_pnl: float = 150.50,
        unrealized_pnl: float = 75.25,
        drawdown_pct: float = 2.5,
        win_count: int = 8,
        loss_count: int = 3,
        total_trades: int = 11,
    ) -> bool:
        """Emit paper_portfolio metrics."""
        try:
            from influxdb_client import Point

            win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0.0

            point = (
                Point("paper_portfolio")
                .tag("metric_type", "summary")
                .field("portfolio_value", portfolio_value)
                .field("open_positions", float(open_positions))
                .field("total_pnl", total_pnl)
                .field("unrealized_pnl", unrealized_pnl)
                .field("drawdown_pct", drawdown_pct)
                .field("win_count", float(win_count))
                .field("loss_count", float(loss_count))
                .field("total_trades", float(total_trades))
                .field("win_rate", win_rate)
                .time(datetime.now(UTC))
            )

            write_api = await self._get_write_api()
            write_api.write(bucket=self.bucket, org=self.org, record=point)

            logger.info(
                f"Emitted paper_portfolio: value=${portfolio_value:.2f}, "
                f"pnl=${total_pnl:.2f}, win_rate={win_rate:.1f}%"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to emit portfolio metrics: {e}")
            return False

    async def emit_position(
        self,
        symbol: str = "BTCUSDT",
        side: str = "long",
        quantity: float = 0.5,
        entry_price: float = 45000.0,
        current_price: float = 46000.0,
        leverage: float = 1.0,
        is_open: bool = True,
    ) -> bool:
        """Emit paper_positions metrics."""
        try:
            from influxdb_client import Point

            # Calculate PnL
            if side == "long":
                unrealized_pnl = (current_price - entry_price) * quantity
                unrealized_pnl_pct = (current_price - entry_price) / entry_price * 100
            else:
                unrealized_pnl = (entry_price - current_price) * quantity
                unrealized_pnl_pct = (entry_price - current_price) / entry_price * 100

            notional_value = quantity * entry_price
            market_value = quantity * current_price

            point = (
                Point("paper_positions")
                .tag("symbol", symbol)
                .tag("side", side)
                .tag("position_id", str(uuid.uuid4())[:8])
                .field("quantity", quantity)
                .field("entry_price", entry_price)
                .field("current_price", current_price)
                .field("unrealized_pnl", unrealized_pnl)
                .field("realized_pnl", 0.0)
                .field("unrealized_pnl_pct", unrealized_pnl_pct)
                .field("notional_value", notional_value)
                .field("market_value", market_value)
                .field("leverage", leverage)
                .field("is_open", 1.0 if is_open else 0.0)
                .time(datetime.now(UTC))
            )

            write_api = await self._get_write_api()
            write_api.write(bucket=self.bucket, org=self.org, record=point)

            logger.info(
                f"Emitted paper_position: {symbol} {side} "
                f"pnl=${unrealized_pnl:.2f} ({unrealized_pnl_pct:.2f}%)"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to emit position: {e}")
            return False

    async def emit_trade(
        self,
        symbol: str = "BTCUSDT",
        side: str = "buy",
        quantity: float = 0.1,
        price: float = 45000.0,
        pnl: float = 0.0,
        signal_confidence: float = 0.85,
    ) -> bool:
        """Emit paper_trades metrics."""
        try:
            from influxdb_client import Point

            # Determine outcome
            if pnl > 0:
                outcome = "win"
            elif pnl < 0:
                outcome = "loss"
            else:
                outcome = "neutral"

            point = (
                Point("paper_trades")
                .tag("symbol", symbol)
                .tag("side", side)
                .tag("trade_id", str(uuid.uuid4())[:8])
                .tag("outcome", outcome)
                .field("quantity", quantity)
                .field("price", price)
                .field("pnl", pnl)
                .field("signal_confidence", signal_confidence)
                .time(datetime.now(UTC))
            )

            write_api = await self._get_write_api()
            write_api.write(bucket=self.bucket, org=self.org, record=point)

            logger.info(
                f"Emitted paper_trade: {symbol} {side} @{price:.2f} pnl=${pnl:.2f}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to emit trade: {e}")
            return False

    async def emit_signal_confidence(
        self,
        bucket_range: str = "0.8-1.0",
        count: int = 5,
    ) -> bool:
        """Emit paper_signals metrics."""
        try:
            from influxdb_client import Point

            point = (
                Point("paper_signals")
                .tag("bucket", bucket_range)
                .field("count", float(count))
                .time(datetime.now(UTC))
            )

            write_api = await self._get_write_api()
            write_api.write(bucket=self.bucket, org=self.org, record=point)

            logger.info(f"Emitted paper_signal: bucket={bucket_range} count={count}")
            return True

        except Exception as e:
            logger.error(f"Failed to emit signal confidence: {e}")
            return False

    async def emit_portfolio_snapshot(
        self,
        environment: str = "paper",
        total_equity: float = 10000.0,
        realized_pnl: float = 150.50,
        unrealized_pnl: float = 75.25,
        max_drawdown_pct: float = -2.5,
    ) -> bool:
        """Emit portfolio_snapshot metrics (for paper-execution dashboard)."""
        try:
            from influxdb_client import Point

            point = (
                Point("portfolio_snapshot")
                .tag("environment", environment)
                .field("total_equity", total_equity)
                .field("realized_pnl", realized_pnl)
                .field("unrealized_pnl", unrealized_pnl)
                .field("max_drawdown_percent", max_drawdown_pct)
                .time(datetime.now(UTC))
            )

            write_api = await self._get_write_api()
            write_api.write(bucket=self.bucket, org=self.org, record=point)

            logger.info(f"Emitted portfolio_snapshot: equity=${total_equity:.2f}")
            return True

        except Exception as e:
            logger.error(f"Failed to emit portfolio snapshot: {e}")
            return False

    async def emit_order(
        self,
        environment: str = "paper",
        symbol: str = "BTCUSDT",
        side: str = "buy",
        price: float = 45000.0,
        size: float = 0.1,
    ) -> bool:
        """Emit orders metrics (for paper-execution dashboard)."""
        try:
            from influxdb_client import Point

            point = (
                Point("orders")
                .tag("environment", environment)
                .tag("symbol", symbol)
                .tag("side", side)
                .field("order_id", str(uuid.uuid4())[:8])
                .field("price", price)
                .field("size", size)
                .field("timestamp", datetime.now(UTC).timestamp())
                .time(datetime.now(UTC))
            )

            write_api = await self._get_write_api()
            write_api.write(bucket=self.bucket, org=self.org, record=point)

            logger.info(f"Emitted order: {symbol} {side} @{price:.2f}")
            return True

        except Exception as e:
            logger.error(f"Failed to emit order: {e}")
            return False

    async def emit_fill(
        self,
        environment: str = "paper",
        symbol: str = "BTCUSDT",
        side: str = "buy",
        price: float = 45000.0,
        size: float = 0.1,
    ) -> bool:
        """Emit fills metrics (for paper-execution dashboard)."""
        try:
            from influxdb_client import Point

            point = (
                Point("fills")
                .tag("environment", environment)
                .tag("symbol", symbol)
                .tag("side", side)
                .field("fill_id", str(uuid.uuid4())[:8])
                .field("price", price)
                .field("size", size)
                .field("timestamp", datetime.now(UTC).timestamp())
                .time(datetime.now(UTC))
            )

            write_api = await self._get_write_api()
            write_api.write(bucket=self.bucket, org=self.org, record=point)

            logger.info(f"Emitted fill: {symbol} {side} @{price:.2f}")
            return True

        except Exception as e:
            logger.error(f"Failed to emit fill: {e}")
            return False

    async def emit_kill_switch_state(
        self,
        environment: str = "paper",
        state: str = "ARMED",
    ) -> bool:
        """Emit kill_switch metrics (for paper-execution dashboard)."""
        try:
            from influxdb_client import Point

            point = (
                Point("kill_switch")
                .tag("environment", environment)
                .field("state", state)
                .time(datetime.now(UTC))
            )

            write_api = await self._get_write_api()
            write_api.write(bucket=self.bucket, org=self.org, record=point)

            logger.info(f"Emitted kill_switch: state={state}")
            return True

        except Exception as e:
            logger.error(f"Failed to emit kill switch state: {e}")
            return False

    async def emit_all_test_data(self) -> bool:
        """Emit comprehensive test data for all metrics."""
        logger.info("Emitting all test data...")

        results = []

        # Paper trading dashboard metrics
        results.append(await self.emit_portfolio_metrics())
        results.append(await self.emit_position("BTCUSDT", "long", 0.5, 45000, 46000))
        results.append(await self.emit_position("ETHUSDT", "short", 2.0, 3000, 2900))
        results.append(await self.emit_trade("BTCUSDT", "buy", 0.1, 45000, 0.0, 0.85))
        results.append(
            await self.emit_trade("BTCUSDT", "sell", 0.1, 46000, 100.0, 0.90)
        )
        results.append(await self.emit_trade("ETHUSDT", "sell", 0.5, 3000, 0.0, 0.80))
        results.append(await self.emit_trade("ETHUSDT", "buy", 0.5, 2900, 50.0, 0.75))
        results.append(await self.emit_signal_confidence("0.8-1.0", 5))
        results.append(await self.emit_signal_confidence("0.6-0.8", 3))
        results.append(await self.emit_signal_confidence("0.4-0.6", 2))

        # Paper execution dashboard metrics
        results.append(await self.emit_portfolio_snapshot())
        results.append(await self.emit_order())
        results.append(await self.emit_fill())
        results.append(await self.emit_kill_switch_state())

        success_count = sum(results)
        logger.info(
            f"Test data emission complete: {success_count}/{len(results)} succeeded"
        )
        return all(results)

    async def run_continuous(self, interval: float = 5.0) -> None:
        """Run continuous emission loop."""
        logger.info(f"Starting continuous emission every {interval}s...")

        iteration = 0
        while True:
            try:
                iteration += 1
                logger.info(f"Emission iteration {iteration}")

                # Update values slightly for realism
                import random

                portfolio_value = 10000.0 + random.uniform(-100, 200)
                total_pnl = 150.50 + random.uniform(-10, 20)

                await self.emit_portfolio_metrics(
                    portfolio_value=portfolio_value,
                    total_pnl=total_pnl,
                )
                await self.emit_portfolio_snapshot(
                    total_equity=portfolio_value,
                    realized_pnl=total_pnl,
                )

                # Emit positions periodically
                if iteration % 3 == 0:
                    await self.emit_position(
                        "BTCUSDT",
                        "long",
                        0.5,
                        45000,
                        46000 + random.uniform(-500, 500),
                    )

                # Emit trades occasionally
                if iteration % 5 == 0:
                    await self.emit_trade(
                        "BTCUSDT",
                        "buy" if random.random() > 0.5 else "sell",
                        0.1,
                        45000 + random.uniform(-1000, 1000),
                        random.uniform(-50, 100),
                        random.uniform(0.7, 0.95),
                    )
                    await self.emit_order()
                    await self.emit_fill()

                await asyncio.sleep(interval)

            except asyncio.CancelledError:
                logger.info("Continuous emission cancelled")
                break
            except Exception as e:
                logger.error(f"Error in continuous emission: {e}")
                await asyncio.sleep(interval)

    async def close(self) -> None:
        """Close connections."""
        if self._write_api:
            self._write_api.close()
        if self._client:
            self._client.close()


async def main():
    parser = argparse.ArgumentParser(
        description="Emit paper trading metrics to InfluxDB"
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="Emit initial test data (one-time)",
    )
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="Run continuous emission loop",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=5.0,
        help="Emission interval in seconds (default: 5)",
    )
    parser.add_argument(
        "--test-trade",
        action="store_true",
        help="Emit a single test trade",
    )

    args = parser.parse_args()

    emitter = PaperMetricsEmitter()

    try:
        if args.test_trade:
            await emitter.emit_trade()
            await emitter.emit_order()
            await emitter.emit_fill()
        elif args.continuous:
            await emitter.run_continuous(args.interval)
        elif args.init:
            success = await emitter.emit_all_test_data()
            sys.exit(0 if success else 1)
        else:
            # Default: emit test data
            success = await emitter.emit_all_test_data()
            sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        await emitter.close()


if __name__ == "__main__":
    asyncio.run(main())
