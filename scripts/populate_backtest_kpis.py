#!/usr/bin/env python3
"""Populate backtest_kpis measurement with sample/demo data.

This script populates the InfluxDB backtest_kpis measurement with sample data
for testing the Grafana dashboard.

Usage:
    # Populate sample data for a strategy
    python scripts/populate_backtest_kpis.py --strategy-id test-strategy --days 7

    # Populate with specific symbol and timeframe
    python scripts/populate_backtest_kpis.py --strategy-id grid_btc --symbol BTCUSDT --timeframe 1h --days 30

    # Populate multiple strategies
    python scripts/populate_backtest_kpis.py --days 14 --multiple

Environment Variables:
    INFLUXDB_URL: InfluxDB URL (default: http://host.docker.internal:18087)
    INFLUXDB_TOKEN: InfluxDB token (default: chiseai-token)
    INFLUXDB_ORG: InfluxDB organization (default: chiseai)
    INFLUXDB_BUCKET: InfluxDB bucket (default: chiseai)
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from backtesting.kpi_writer import BacktestKPIWriter, BacktestKPIs


def generate_sample_kpis(
    strategy_id: str,
    timestamp: datetime,
    symbol: str = "BTCUSDT",
    timeframe: str = "1h",
) -> BacktestKPIs:
    """Generate sample KPIs for testing.

    Args:
        strategy_id: Strategy identifier
        timestamp: Timestamp for the KPI record
        symbol: Trading pair symbol
        timeframe: Candle timeframe

    Returns:
        BacktestKPIs with realistic sample values
    """
    # Generate somewhat realistic values with some randomness
    base_sharpe = 1.2
    base_drawdown = 0.15
    base_winrate = 0.52

    # Add some variation based on time to make trends visible
    hour_factor = timestamp.hour / 24.0
    day_factor = timestamp.weekday() / 7.0

    sharpe = base_sharpe + random.gauss(0, 0.3) + (hour_factor - 0.5) * 0.4
    max_dd = base_drawdown + random.gauss(0, 0.03) + (day_factor - 0.5) * 0.05
    win_rate = base_winrate + random.gauss(0, 0.05) + (hour_factor - 0.5) * 0.1

    # Ensure values are in reasonable ranges
    sharpe = max(-1.0, min(3.0, sharpe))
    max_dd = max(0.01, min(0.5, max_dd))
    win_rate = max(0.3, min(0.8, win_rate))

    # Trade count varies by timeframe
    timeframe_multipliers = {
        "1m": 1440,
        "5m": 288,
        "15m": 96,
        "1h": 24,
        "4h": 6,
        "1d": 1,
    }
    multiplier = timeframe_multipliers.get(timeframe, 24)
    trade_count = int(random.gauss(50, 15) * multiplier / 24)
    trade_count = max(1, trade_count)

    # PnL correlates with win rate and trade count
    avg_trade_pnl = (win_rate - 0.5) * 100  # $ per trade
    total_pnl = avg_trade_pnl * trade_count

    return BacktestKPIs(
        strategy_id=strategy_id,
        timestamp=timestamp,
        sharpe_ratio=round(sharpe, 2),
        max_drawdown=round(max_dd, 4),
        win_rate=round(win_rate, 4),
        trade_count=trade_count,
        total_pnl=round(total_pnl, 2),
        symbol=symbol,
        timeframe=timeframe,
    )


def populate_strategy_data(
    writer: BacktestKPIWriter,
    strategy_id: str,
    days: int,
    symbol: str,
    timeframe: str,
    points_per_day: int = 4,
) -> int:
    """Populate data for a single strategy.

    Args:
        writer: BacktestKPIWriter instance
        strategy_id: Strategy identifier
        days: Number of days of data to generate
        symbol: Trading pair symbol
        timeframe: Candle timeframe
        points_per_day: Number of data points per day

    Returns:
        Number of records written
    """
    now = datetime.now(timezone.utc)
    count = 0

    for day in range(days):
        for point in range(points_per_day):
            # Generate timestamps spread across the day
            hour = int(24 * point / points_per_day)
            timestamp = now - timedelta(days=day, hours=now.hour - hour)

            kpis = generate_sample_kpis(
                strategy_id=strategy_id,
                timestamp=timestamp,
                symbol=symbol,
                timeframe=timeframe,
            )

            if writer.write_kpis(kpis):
                count += 1

    return count


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 for success, 1 for error)
    """
    parser = argparse.ArgumentParser(
        description="Populate backtest_kpis measurement with sample data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Populate sample data for 7 days
  python populate_backtest_kpis.py --strategy-id test-strategy --days 7

  # Populate with specific symbol and timeframe
  python populate_backtest_kpis.py --strategy-id grid_btc --symbol BTCUSDT --timeframe 1h --days 30

  # Populate multiple default strategies
  python populate_backtest_kpis.py --days 14 --multiple
        """,
    )

    parser.add_argument(
        "--strategy-id",
        type=str,
        default="test-strategy",
        help="Strategy identifier (default: test-strategy)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Number of days of data to generate (default: 7)",
    )
    parser.add_argument(
        "--symbol",
        type=str,
        default="BTCUSDT",
        help="Trading pair symbol (default: BTCUSDT)",
    )
    parser.add_argument(
        "--timeframe",
        type=str,
        default="1h",
        choices=["1m", "5m", "15m", "1h", "4h", "1d"],
        help="Candle timeframe (default: 1h)",
    )
    parser.add_argument(
        "--points-per-day",
        type=int,
        default=4,
        help="Number of data points per day (default: 4)",
    )
    parser.add_argument(
        "--multiple",
        action="store_true",
        help="Populate multiple default strategies",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify data was written by querying back",
    )

    args = parser.parse_args()

    print(f"Connecting to InfluxDB...")
    writer = BacktestKPIWriter()

    # Health check
    if not writer.health_check():
        print("ERROR: InfluxDB health check failed")
        return 1

    print(f"InfluxDB connection OK")

    strategies = []
    if args.multiple:
        strategies = [
            ("grid_btc_usdt", "BTCUSDT", "1h"),
            ("grid_eth_usdt", "ETHUSDT", "1h"),
            ("momentum_btc", "BTCUSDT", "4h"),
            ("mean_reversion_eth", "ETHUSDT", "1h"),
            ("breakout_btc", "BTCUSDT", "15m"),
        ]
    else:
        strategies = [(args.strategy_id, args.symbol, args.timeframe)]

    total_written = 0

    for strategy_id, symbol, timeframe in strategies:
        print(f"\nPopulating data for {strategy_id} ({symbol}, {timeframe})...")
        count = populate_strategy_data(
            writer=writer,
            strategy_id=strategy_id,
            days=args.days,
            symbol=symbol,
            timeframe=timeframe,
            points_per_day=args.points_per_day,
        )
        print(f"  Written {count} records")
        total_written += count

    print(f"\n{'=' * 50}")
    print(f"Total records written: {total_written}")

    # Verify if requested
    if args.verify:
        print(f"\nVerifying data...")
        for strategy_id, _, _ in strategies:
            results = writer.query_kpis(strategy_id=strategy_id, limit=5)
            print(f"  {strategy_id}: {len(results)} records found")
            if results:
                latest = results[0]
                print(
                    f"    Latest: Sharpe={latest.get('sharpe_ratio', 'N/A')}, "
                    f"MaxDD={latest.get('max_drawdown', 'N/A')}, "
                    f"WinRate={latest.get('win_rate', 'N/A')}, "
                    f"Trades={latest.get('trade_count', 'N/A')}"
                )

    writer.close()
    print("\nDone!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
