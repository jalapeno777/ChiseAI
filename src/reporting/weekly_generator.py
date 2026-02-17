"""Weekly performance report generator for ChiseAI.

Generates 7-day rolling performance analysis with strategy comparisons,
risk metrics, and week-over-week comparisons.

For PAPER-003-003: Automated Reporting and Anomaly Detection
"""

from __future__ import annotations

import logging
import statistics
from datetime import UTC, datetime, timedelta
from typing import Any

from .models import RiskMetrics, StrategyPerformance, WeeklyReport

logger = logging.getLogger(__name__)


class WeeklyPerformanceReport:
    """Generate weekly performance analysis reports.

    Provides 7-day rolling performance analysis with:
    - Strategy performance comparison
    - Risk metrics (Sharpe ratio, volatility)
    - Week-over-week comparison
    - Daily breakdown

    Attributes:
        influxdb_client: InfluxDB client for querying data
        bucket: InfluxDB bucket name
        org: InfluxDB organization
    """

    def __init__(
        self,
        influxdb_client: Any | None = None,
        bucket: str = "chiseai",
        org: str = "chiseai",
    ) -> None:
        """Initialize weekly report generator.

        Args:
            influxdb_client: InfluxDB client instance
            bucket: InfluxDB bucket name
            org: InfluxDB organization
        """
        self._client = influxdb_client
        self._bucket = bucket
        self._org = org
        self._query_api = None

        logger.info(f"WeeklyPerformanceReport initialized: bucket={bucket}")

    def _get_query_api(self) -> Any:
        """Get or create InfluxDB query API."""
        if self._query_api is None and self._client is not None:
            self._query_api = self._client.query_api()
        return self._query_api

    async def generate_report(
        self,
        end_date: datetime | None = None,
        use_mock_data: bool = False,
    ) -> WeeklyReport:
        """Generate weekly report ending on a specific date.

        Args:
            end_date: End date for the week (default: yesterday)
            use_mock_data: Use mock data for testing

        Returns:
            WeeklyReport with all metrics

        Raises:
            RuntimeError: If cannot query InfluxDB and not using mock data
        """
        if end_date is None:
            # Default to yesterday (UTC)
            end_date = datetime.now(UTC) - timedelta(days=1)

        # Calculate start date (7 days before end date)
        start_date = end_date - timedelta(days=6)

        # Normalize to start/end of day
        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)

        logger.info(
            f"Generating weekly report: {start_date.strftime('%Y-%m-%d')} to "
            f"{end_date.strftime('%Y-%m-%d')}"
        )

        if use_mock_data:
            return self._generate_mock_report(start_date, end_date)

        try:
            # Query data from InfluxDB
            daily_data = await self._query_daily_metrics(start_date, end_date)
            strategy_data = await self._query_strategy_performance(start_date, end_date)
            previous_week_data = await self._query_previous_week(start_date)

            # Calculate metrics
            total_trades = sum(d.get("trades", 0) for d in daily_data)
            total_pnl = sum(d.get("pnl", 0.0) for d in daily_data)

            # Calculate win rate
            total_wins = sum(d.get("wins", 0) for d in daily_data)
            total_losses = sum(d.get("losses", 0) for d in daily_data)
            win_rate = (
                (total_wins / (total_wins + total_losses) * 100)
                if (total_wins + total_losses) > 0
                else 0.0
            )

            # Calculate average daily PnL
            avg_daily_pnl = total_pnl / 7.0 if daily_data else 0.0

            # Find best and worst days
            best_day = max(daily_data, key=lambda x: x.get("pnl", 0.0), default={})
            worst_day = min(daily_data, key=lambda x: x.get("pnl", 0.0), default={})

            # Calculate risk metrics
            risk_metrics = self._calculate_risk_metrics(daily_data)

            # Build strategy performance list
            strategy_performance = self._build_strategy_performance(strategy_data)

            # Calculate week-over-week change
            week_over_week = self._calculate_week_over_week(
                daily_data, previous_week_data
            )

            # Build daily breakdown
            daily_breakdown = [
                {
                    "date": d.get("date", "").strftime("%Y-%m-%d"),
                    "pnl": round(d.get("pnl", 0.0), 2),
                    "trades": d.get("trades", 0),
                    "win_rate": round(
                        (
                            d.get("wins", 0) / d.get("trades", 1) * 100
                            if d.get("trades", 0) > 0
                            else 0.0
                        ),
                        1,
                    ),
                }
                for d in daily_data
            ]

            report = WeeklyReport(
                start_date=start_date,
                end_date=end_date,
                total_trades=total_trades,
                total_pnl=total_pnl,
                win_rate=win_rate,
                avg_daily_pnl=avg_daily_pnl,
                best_day=(
                    best_day.get("date", start_date),
                    best_day.get("pnl", 0.0),
                ),
                worst_day=(
                    worst_day.get("date", start_date),
                    worst_day.get("pnl", 0.0),
                ),
                risk_metrics=risk_metrics,
                strategy_performance=strategy_performance,
                week_over_week_change=week_over_week,
                daily_breakdown=daily_breakdown,
            )

            logger.info(
                f"Weekly report generated: trades={report.total_trades}, "
                f"pnl=${report.total_pnl:.2f}, win_rate={report.win_rate:.1f}%"
            )

            return report

        except Exception as e:
            logger.error(f"Failed to generate weekly report: {e}")
            raise RuntimeError(f"Cannot generate weekly report: {e}") from e

    async def _query_daily_metrics(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> list[dict[str, Any]]:
        """Query daily metrics from InfluxDB.

        Args:
            start_date: Start of the week
            end_date: End of the week

        Returns:
            List of daily metric records
        """
        query_api = self._get_query_api()
        if query_api is None:
            return []

        start_time = start_date.isoformat()
        end_time = end_date.isoformat()

        query = f'''
        from(bucket: "{self._bucket}")
            |> range(start: {start_time}, stop: {end_time})
            |> filter(fn: (r) => r._measurement == "paper_portfolio")
            |> filter(fn: (r) => r._field == "total_pnl" or r._field == "win_count" 
                or r._field == "loss_count" or r._field == "total_trades")
            |> aggregateWindow(every: 1d, fn: last, createEmpty: false)
        '''

        try:
            tables = query_api.query(query, org=self._org)
            daily_metrics = {}

            for table in tables:
                for record in table.records:
                    date = record.get_time().date()
                    if date not in daily_metrics:
                        daily_metrics[date] = {
                            "date": datetime.combine(date, datetime.min.time()),
                            "pnl": 0.0,
                            "wins": 0,
                            "losses": 0,
                            "trades": 0,
                        }

                    field = record.get_field()
                    value = record.get_value()

                    if field == "total_pnl":
                        daily_metrics[date]["pnl"] = value
                    elif field == "win_count":
                        daily_metrics[date]["wins"] = int(value)
                    elif field == "loss_count":
                        daily_metrics[date]["losses"] = int(value)
                    elif field == "total_trades":
                        daily_metrics[date]["trades"] = int(value)

            return list(daily_metrics.values())

        except Exception as e:
            logger.warning(f"Failed to query daily metrics: {e}")
            return []

    async def _query_strategy_performance(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> dict[str, dict[str, Any]]:
        """Query strategy performance from InfluxDB.

        Args:
            start_date: Start of the week
            end_date: End of the week

        Returns:
            Dictionary of strategy performance data
        """
        query_api = self._get_query_api()
        if query_api is None:
            return {}

        start_time = start_date.isoformat()
        end_time = end_date.isoformat()

        query = f'''
        from(bucket: "{self._bucket}")
            |> range(start: {start_time}, stop: {end_time})
            |> filter(fn: (r) => r._measurement == "paper_trades")
            |> filter(fn: (r) => r._field == "pnl")
            |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
        '''

        try:
            tables = query_api.query(query, org=self._org)
            strategies = {}

            for table in tables:
                for record in table.records:
                    strategy_id = record.values.get("strategy_id", "unknown")
                    pnl = record.values.get("pnl", 0.0)

                    if strategy_id not in strategies:
                        strategies[strategy_id] = {
                            "trades": 0,
                            "wins": 0,
                            "losses": 0,
                            "pnls": [],
                        }

                    strategies[strategy_id]["trades"] += 1
                    strategies[strategy_id]["pnls"].append(pnl)

                    if pnl > 0:
                        strategies[strategy_id]["wins"] += 1
                    elif pnl < 0:
                        strategies[strategy_id]["losses"] += 1

            return strategies

        except Exception as e:
            logger.warning(f"Failed to query strategy performance: {e}")
            return {}

    async def _query_previous_week(
        self,
        current_start: datetime,
    ) -> list[dict[str, Any]]:
        """Query previous week's data for comparison.

        Args:
            current_start: Start date of current week

        Returns:
            List of daily metric records for previous week
        """
        prev_end = current_start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=6)
        return await self._query_daily_metrics(prev_start, prev_end)

    def _calculate_risk_metrics(
        self,
        daily_data: list[dict[str, Any]],
    ) -> RiskMetrics:
        """Calculate risk metrics from daily data.

        Args:
            daily_data: List of daily metric records

        Returns:
            RiskMetrics with calculated values
        """
        if not daily_data:
            return RiskMetrics()

        pnls = [d.get("pnl", 0.0) for d in daily_data]

        # Sharpe ratio (simplified)
        if len(pnls) > 1:
            avg_pnl = statistics.mean(pnls)
            std_pnl = statistics.stdev(pnls)
            sharpe_ratio = (avg_pnl / std_pnl) if std_pnl > 0 else 0.0
        else:
            sharpe_ratio = 0.0

        # Volatility
        volatility = statistics.stdev(pnls) if len(pnls) > 1 else 0.0

        # Max drawdown (simplified - based on cumulative PnL)
        cumulative = 0.0
        peak = 0.0
        max_drawdown = 0.0

        for pnl in sorted(pnls):  # Simplified - assumes chronological order
            cumulative += pnl
            if cumulative > peak:
                peak = cumulative
            drawdown = peak - cumulative
            if drawdown > max_drawdown:
                max_drawdown = drawdown

        max_drawdown_pct = (max_drawdown / peak * 100) if peak > 0 else 0.0

        # Value at Risk (95%)
        var_95 = 1.645 * volatility if volatility > 0 else 0.0

        return RiskMetrics(
            sharpe_ratio=sharpe_ratio,
            volatility=volatility,
            max_drawdown=max_drawdown,
            max_drawdown_pct=max_drawdown_pct,
            var_95=var_95,
            exposure_pct=0.0,  # Would need additional data
        )

    def _build_strategy_performance(
        self,
        strategy_data: dict[str, dict[str, Any]],
    ) -> list[StrategyPerformance]:
        """Build strategy performance list from raw data.

        Args:
            strategy_data: Dictionary of strategy performance data

        Returns:
            List of StrategyPerformance objects
        """
        performance_list = []

        for strategy_id, data in strategy_data.items():
            total_trades = data.get("trades", 0)
            wins = data.get("wins", 0)
            pnls = data.get("pnls", [])

            win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0
            total_pnl = sum(pnls)
            avg_pnl = statistics.mean(pnls) if pnls else 0.0

            # Simplified Sharpe ratio per strategy
            if len(pnls) > 1:
                std_pnl = statistics.stdev(pnls)
                sharpe = (avg_pnl / std_pnl) if std_pnl > 0 else 0.0
            else:
                sharpe = 0.0

            performance_list.append(
                StrategyPerformance(
                    strategy_id=strategy_id,
                    strategy_name=strategy_id.replace("_", " ").title(),
                    total_trades=total_trades,
                    win_rate=win_rate,
                    total_pnl=total_pnl,
                    avg_pnl=avg_pnl,
                    sharpe_ratio=sharpe,
                )
            )

        # Sort by total PnL descending
        performance_list.sort(key=lambda x: x.total_pnl, reverse=True)

        return performance_list

    def _calculate_week_over_week(
        self,
        current_data: list[dict[str, Any]],
        previous_data: list[dict[str, Any]],
    ) -> dict[str, float]:
        """Calculate week-over-week percentage changes.

        Args:
            current_data: Current week's daily data
            previous_data: Previous week's daily data

        Returns:
            Dictionary of percentage changes
        """
        current_pnl = sum(d.get("pnl", 0.0) for d in current_data)
        current_trades = sum(d.get("trades", 0) for d in current_data)
        current_wins = sum(d.get("wins", 0) for d in current_data)
        current_win_rate = (
            (current_wins / current_trades * 100) if current_trades > 0 else 0.0
        )
        current_avg = current_pnl / 7.0 if current_data else 0.0

        prev_pnl = sum(d.get("pnl", 0.0) for d in previous_data)
        prev_trades = sum(d.get("trades", 0) for d in previous_data)
        prev_wins = sum(d.get("wins", 0) for d in previous_data)
        prev_win_rate = (prev_wins / prev_trades * 100) if prev_trades > 0 else 0.0
        prev_avg = prev_pnl / 7.0 if previous_data else 0.0

        return {
            "total_pnl": (
                ((current_pnl - prev_pnl) / abs(prev_pnl) * 100)
                if prev_pnl != 0
                else 0.0
            ),
            "total_trades": (
                ((current_trades - prev_trades) / prev_trades * 100)
                if prev_trades > 0
                else 0.0
            ),
            "win_rate": current_win_rate - prev_win_rate,
            "avg_daily_pnl": (
                ((current_avg - prev_avg) / abs(prev_avg) * 100)
                if prev_avg != 0
                else 0.0
            ),
        }

    def _generate_mock_report(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> WeeklyReport:
        """Generate a mock report for testing.

        Args:
            start_date: Start date of the week
            end_date: End date of the week

        Returns:
            WeeklyReport with mock data
        """
        # Generate daily breakdown
        daily_breakdown = []
        current_date = start_date
        total_pnl = 0.0

        for i in range(7):
            day_pnl = 100.0 + (i * 50.0) - (i % 3 * 75.0)  # Varying PnL
            daily_breakdown.append(
                {
                    "date": current_date.strftime("%Y-%m-%d"),
                    "pnl": round(day_pnl, 2),
                    "trades": 5 + i,
                    "win_rate": 60.0 + (i * 2.0),
                }
            )
            total_pnl += day_pnl
            current_date += timedelta(days=1)

        return WeeklyReport(
            start_date=start_date,
            end_date=end_date,
            total_trades=287,
            total_pnl=total_pnl,
            win_rate=68.5,
            avg_daily_pnl=total_pnl / 7.0,
            best_day=(start_date + timedelta(days=5), 325.50),
            worst_day=(start_date + timedelta(days=2), -85.25),
            risk_metrics=RiskMetrics(
                sharpe_ratio=2.15,
                volatility=0.032,
                max_drawdown=250.0,
                max_drawdown_pct=3.2,
                var_95=52.6,
                exposure_pct=72.0,
            ),
            strategy_performance=[
                StrategyPerformance(
                    strategy_id="momentum_v1",
                    strategy_name="Momentum V1",
                    total_trades=120,
                    win_rate=72.5,
                    total_pnl=850.50,
                    avg_pnl=7.09,
                    sharpe_ratio=2.45,
                ),
                StrategyPerformance(
                    strategy_id="mean_reversion_v2",
                    strategy_name="Mean Reversion V2",
                    total_trades=95,
                    win_rate=65.3,
                    total_pnl=520.25,
                    avg_pnl=5.48,
                    sharpe_ratio=1.85,
                ),
                StrategyPerformance(
                    strategy_id="breakout_v1",
                    strategy_name="Breakout V1",
                    total_trades=72,
                    win_rate=62.5,
                    total_pnl=320.75,
                    avg_pnl=4.45,
                    sharpe_ratio=1.55,
                ),
            ],
            week_over_week_change={
                "total_pnl": 15.5,
                "total_trades": 8.2,
                "win_rate": 2.3,
                "avg_daily_pnl": 12.1,
            },
            daily_breakdown=daily_breakdown,
        )
