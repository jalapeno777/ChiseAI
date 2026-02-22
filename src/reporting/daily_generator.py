"""Daily report generator for ChiseAI.

Generates daily PnL summaries with trade metrics, win/loss ratios,
and risk metrics. Formats output as Markdown for Discord/email.

For PAPER-003-003: Automated Reporting and Anomaly Detection
"""

from __future__ import annotations

import logging
import statistics
from datetime import UTC, datetime, timedelta
from typing import Any

from .models import (
    DailyReport,
    PaperHealthMetrics,
    PaperHealthReport,
    RiskMetrics,
    TradeMetrics,
)

logger = logging.getLogger(__name__)


class DailyReportGenerator:
    """Generate daily trading summary reports.

    Queries InfluxDB for paper trading metrics and generates
    comprehensive daily reports with PnL, trade statistics, and risk metrics.

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
        """Initialize daily report generator.

        Args:
            influxdb_client: InfluxDB client instance
            bucket: InfluxDB bucket name
            org: InfluxDB organization
        """
        self._client = influxdb_client
        self._bucket = bucket
        self._org = org
        self._query_api = None

        logger.info(f"DailyReportGenerator initialized: bucket={bucket}")

    def _get_query_api(self) -> Any:
        """Get or create InfluxDB query API."""
        if self._query_api is None and self._client is not None:
            self._query_api = self._client.query_api()
        return self._query_api

    async def generate_report(
        self,
        date: datetime | None = None,
        use_mock_data: bool = False,
    ) -> DailyReport:
        """Generate daily report for a specific date.

        Args:
            date: Date to generate report for (default: yesterday)
            use_mock_data: Use mock data for testing

        Returns:
            DailyReport with all metrics

        Raises:
            RuntimeError: If cannot query InfluxDB and not using mock data
        """
        if date is None:
            # Default to yesterday (UTC)
            date = datetime.now(UTC) - timedelta(days=1)

        # Normalize to start of day
        date = date.replace(hour=0, minute=0, second=0, microsecond=0)

        logger.info(f"Generating daily report for {date.strftime('%Y-%m-%d')}")

        if use_mock_data:
            return self._generate_mock_report(date)

        try:
            # Query data from InfluxDB
            trades_data = await self._query_trades(date)
            portfolio_data = await self._query_portfolio(date)
            positions_data = await self._query_positions(date)

            # Calculate metrics
            trade_metrics = self._calculate_trade_metrics(trades_data)
            risk_metrics = self._calculate_risk_metrics(trades_data, portfolio_data)

            # Build report
            report = DailyReport(
                date=date,
                total_trades=trade_metrics.total_trades,
                winning_trades=trade_metrics.winning_trades,
                losing_trades=trade_metrics.losing_trades,
                win_rate=trade_metrics.win_rate,
                total_pnl=portfolio_data.get("total_pnl", 0.0),
                realized_pnl=portfolio_data.get("realized_pnl", 0.0),
                unrealized_pnl=portfolio_data.get("unrealized_pnl", 0.0),
                max_drawdown=risk_metrics.max_drawdown,
                max_drawdown_pct=risk_metrics.max_drawdown_pct,
                avg_pnl=trade_metrics.avg_pnl_per_trade,
                trade_metrics=trade_metrics,
                risk_metrics=risk_metrics,
                open_positions=positions_data.get("open_count", 0),
                portfolio_value=portfolio_data.get("portfolio_value", 0.0),
            )

            logger.info(
                f"Daily report generated: trades={report.total_trades}, "
                f"pnl=${report.total_pnl:.2f}, win_rate={report.win_rate:.1f}%"
            )

            return report

        except Exception as e:
            logger.error(f"Failed to generate daily report: {e}")
            raise RuntimeError(f"Cannot generate daily report: {e}") from e

    async def _query_trades(self, date: datetime) -> list[dict[str, Any]]:
        """Query trades from InfluxDB for a specific date.

        Args:
            date: Date to query

        Returns:
            List of trade records
        """
        query_api = self._get_query_api()
        if query_api is None:
            return []

        start_time = date.isoformat()
        end_time = (date + timedelta(days=1)).isoformat()

        query = f"""
        from(bucket: "{self._bucket}")
            |> range(start: {start_time}, stop: {end_time})
            |> filter(fn: (r) => r._measurement == "paper_trades")
            |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
        """

        try:
            tables = query_api.query(query, org=self._org)
            trades = []
            for table in tables:
                for record in table.records:
                    trades.append(
                        {
                            "timestamp": record.get_time(),
                            "symbol": record.values.get("symbol", ""),
                            "side": record.values.get("side", ""),
                            "pnl": record.values.get("pnl", 0.0),
                            "quantity": record.values.get("quantity", 0.0),
                            "price": record.values.get("price", 0.0),
                        }
                    )
            return trades
        except Exception as e:
            logger.warning(f"Failed to query trades: {e}")
            return []

    async def _query_portfolio(self, date: datetime) -> dict[str, Any]:
        """Query portfolio metrics from InfluxDB.

        Args:
            date: Date to query

        Returns:
            Portfolio metrics dictionary
        """
        query_api = self._get_query_api()
        if query_api is None:
            return {}

        start_time = date.isoformat()
        end_time = (date + timedelta(days=1)).isoformat()

        query = f"""
        from(bucket: "{self._bucket}")
            |> range(start: {start_time}, stop: {end_time})
            |> filter(fn: (r) => r._measurement == "paper_portfolio")
            |> filter(fn: (r) => r._field == "total_pnl" or r._field == "realized_pnl" 
                or r._field == "unrealized_pnl" or r._field == "portfolio_value")
            |> last()
        """

        try:
            tables = query_api.query(query, org=self._org)
            portfolio = {}
            for table in tables:
                for record in table.records:
                    field = record.get_field()
                    value = record.get_value()
                    portfolio[field] = value
            return portfolio
        except Exception as e:
            logger.warning(f"Failed to query portfolio: {e}")
            return {}

    async def _query_positions(self, date: datetime) -> dict[str, Any]:
        """Query position data from InfluxDB.

        Args:
            date: Date to query

        Returns:
            Position metrics dictionary
        """
        query_api = self._get_query_api()
        if query_api is None:
            return {"open_count": 0}

        start_time = date.isoformat()
        end_time = (date + timedelta(days=1)).isoformat()

        query = f"""
        from(bucket: "{self._bucket}")
            |> range(start: {start_time}, stop: {end_time})
            |> filter(fn: (r) => r._measurement == "paper_positions")
            |> filter(fn: (r) => r._field == "is_open")
            |> last()
        """

        try:
            tables = query_api.query(query, org=self._org)
            open_count = 0
            for table in tables:
                for record in table.records:
                    if record.get_value() == 1.0:
                        open_count += 1
            return {"open_count": open_count}
        except Exception as e:
            logger.warning(f"Failed to query positions: {e}")
            return {"open_count": 0}

    def _calculate_trade_metrics(self, trades: list[dict[str, Any]]) -> TradeMetrics:
        """Calculate trade metrics from trade data.

        Args:
            trades: List of trade records

        Returns:
            TradeMetrics with calculated values
        """
        if not trades:
            return TradeMetrics()

        total_trades = len(trades)
        pnls = [t.get("pnl", 0.0) for t in trades]
        winning_pnls = [p for p in pnls if p > 0]
        losing_pnls = [p for p in pnls if p < 0]

        winning_trades = len(winning_pnls)
        losing_trades = len(losing_pnls)
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0

        avg_pnl = statistics.mean(pnls) if pnls else 0.0
        avg_win = statistics.mean(winning_pnls) if winning_pnls else 0.0
        avg_loss = statistics.mean(losing_pnls) if losing_pnls else 0.0

        largest_win = max(winning_pnls) if winning_pnls else 0.0
        largest_loss = min(losing_pnls) if losing_pnls else 0.0

        total_volume = sum(t.get("quantity", 0.0) * t.get("price", 0.0) for t in trades)

        return TradeMetrics(
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            avg_pnl_per_trade=avg_pnl,
            avg_win=avg_win,
            avg_loss=avg_loss,
            largest_win=largest_win,
            largest_loss=largest_loss,
            total_volume=total_volume,
        )

    def _calculate_risk_metrics(
        self,
        trades: list[dict[str, Any]],
        portfolio: dict[str, Any],
    ) -> RiskMetrics:
        """Calculate risk metrics from trade and portfolio data.

        Args:
            trades: List of trade records
            portfolio: Portfolio metrics

        Returns:
            RiskMetrics with calculated values
        """
        pnls = [t.get("pnl", 0.0) for t in trades]

        if not pnls:
            return RiskMetrics()

        # Calculate returns for Sharpe ratio
        returns = [p for p in pnls if p != 0]

        # Sharpe ratio (simplified - assumes risk-free rate of 0)
        if len(returns) > 1:
            avg_return = statistics.mean(returns)
            std_return = statistics.stdev(returns)
            sharpe_ratio = (avg_return / std_return) if std_return > 0 else 0.0
        else:
            sharpe_ratio = 0.0

        # Volatility (standard deviation of returns)
        volatility = statistics.stdev(returns) if len(returns) > 1 else 0.0

        # Value at Risk (95% - simplified as 1.645 * std)
        var_95 = 1.645 * volatility if volatility > 0 else 0.0

        # Max drawdown from portfolio data
        max_drawdown = portfolio.get("max_drawdown", 0.0)
        max_drawdown_pct = portfolio.get("drawdown_pct", 0.0)

        # Exposure percentage
        exposure_pct = portfolio.get("exposure_pct", 0.0)

        return RiskMetrics(
            sharpe_ratio=sharpe_ratio,
            volatility=volatility,
            max_drawdown=max_drawdown,
            max_drawdown_pct=max_drawdown_pct,
            var_95=var_95,
            exposure_pct=exposure_pct,
        )

    async def generate_paper_health_report(
        self,
        paper_tracker: Any | None = None,
        date: datetime | None = None,
        thresholds: dict[str, Any] | None = None,
    ) -> PaperHealthReport:
        """Generate paper trading health report.

        Args:
            paper_tracker: PaperTracker instance for health metrics
            date: Date for the report (default: today)
            thresholds: Health check thresholds (default: from config)

        Returns:
            PaperHealthReport with health metrics and pass/fail status

        For PAPER-004: Daily paper trading health/performance reports
        """
        if date is None:
            date = datetime.now(UTC)

        # Normalize to start of day
        date = date.replace(hour=0, minute=0, second=0, microsecond=0)

        logger.info(f"Generating paper health report for {date.strftime('%Y-%m-%d')}")

        # Default thresholds
        default_thresholds = {
            "redis_error_rate_max_pct": 5.0,
            "validation_failure_max_pct": 10.0,
            "data_freshness_max_seconds": 60.0,
        }
        thresholds = thresholds or default_thresholds

        # Gather health metrics from paper tracker
        health_metrics = await self._gather_health_metrics(paper_tracker, thresholds)

        # Gather portfolio summary
        portfolio = await self._query_portfolio(date)
        positions = await self._query_positions(date)

        # Collect warnings
        warnings = []
        if not health_metrics.redis_sync_pass:
            warnings.append(f"Redis sync failed: {health_metrics.redis_sync_status}")
        if not health_metrics.validation_pass:
            warnings.append(
                f"High validation failure rate: {health_metrics.validation_failure_rate_pct:.1f}%"
            )
        if not health_metrics.circuit_breaker_pass:
            warnings.append(
                f"Circuit breaker is {health_metrics.circuit_breaker_state}"
            )
        if not health_metrics.kill_switch_pass:
            warnings.append("Kill switch is ARMED - trading halted")
        if not health_metrics.data_freshness_pass:
            warnings.append(
                f"Stale data: {health_metrics.data_freshness_seconds:.0f}s since last update"
            )

        # Build report
        report = PaperHealthReport(
            date=date,
            health_metrics=health_metrics,
            portfolio_value=portfolio.get("portfolio_value", 0.0),
            total_pnl=portfolio.get("total_pnl", 0.0),
            open_positions=positions.get("open_count", 0),
            active_strategies=positions.get("active_strategies", 0),
            warnings=warnings,
        )

        logger.info(
            f"Paper health report generated: status={health_metrics.overall_health}, "
            f"checks_pass={health_metrics.all_pass}"
        )

        return report

    async def _gather_health_metrics(
        self,
        paper_tracker: Any | None,
        thresholds: dict[str, Any],
    ) -> PaperHealthMetrics:
        """Gather health metrics from paper tracker.

        Args:
            paper_tracker: PaperTracker instance
            thresholds: Health check thresholds

        Returns:
            PaperHealthMetrics with values and pass/fail status
        """
        metrics = PaperHealthMetrics()

        if paper_tracker is None:
            # No tracker available - return unknown status
            logger.warning("No PaperTracker provided - returning unknown health status")
            return metrics

        try:
            # Get Redis health from tracker
            redis_health = paper_tracker.get_redis_health()
            metrics.redis_error_rate_pct = redis_health.get("error_rate_pct", 0.0)
            metrics.circuit_breaker_state = (
                "open" if redis_health.get("circuit_breaker_open", False) else "closed"
            )

            # Get sync status
            sync_status = paper_tracker.get_sync_status()
            if sync_status.get("redis_connected", False):
                divergence_pct = sync_status.get("divergence_pct", 0.0)
                if divergence_pct == 0:
                    metrics.redis_sync_status = "synced"
                    metrics.redis_sync_pass = True
                elif divergence_pct < 5.0:  # Under 5% divergence
                    metrics.redis_sync_status = "slight_divergence"
                    metrics.redis_sync_pass = True
                else:
                    metrics.redis_sync_status = "diverged"
                    metrics.redis_sync_pass = False
            else:
                metrics.redis_sync_status = "disconnected"
                metrics.redis_sync_pass = False

            # Get validation failure summary
            validation_summary = paper_tracker.get_validation_failure_summary()
            metrics.validation_failure_rate_pct = validation_summary.get(
                "failure_rate_pct", 0.0
            )
            metrics.validation_pass = (
                metrics.validation_failure_rate_pct
                < thresholds.get("validation_failure_max_pct", 10.0)
            )

            # Check circuit breaker state
            cb_state = paper_tracker.get_circuit_breaker_state()
            cb_state_str = cb_state.get("state", "closed").lower()
            metrics.circuit_breaker_state = cb_state_str
            metrics.circuit_breaker_pass = cb_state_str == "closed"

            # Check kill switch (assumed to be exposed by tracker)
            metrics.kill_switch_armed = getattr(
                paper_tracker, "kill_switch_armed", False
            )
            metrics.kill_switch_pass = not metrics.kill_switch_armed

            # Data freshness - check last successful operation
            last_success = redis_health.get("last_successful_operation")
            if last_success:
                metrics.last_data_update = datetime.fromisoformat(last_success)
                metrics.data_freshness_seconds = (
                    datetime.now(UTC) - metrics.last_data_update
                ).total_seconds()
                metrics.data_freshness_pass = (
                    metrics.data_freshness_seconds
                    < thresholds.get("data_freshness_max_seconds", 60.0)
                )
            else:
                metrics.last_data_update = None
                metrics.data_freshness_seconds = float("inf")
                metrics.data_freshness_pass = False

        except Exception as e:
            logger.error(f"Error gathering health metrics: {e}")
            # Return metrics with unknown status

        return metrics

    def _generate_mock_report(self, date: datetime) -> DailyReport:
        """Generate a mock report for testing.

        Args:
            date: Date for the report

        Returns:
            DailyReport with mock data
        """
        return DailyReport(
            date=date,
            total_trades=42,
            winning_trades=28,
            losing_trades=14,
            win_rate=66.7,
            total_pnl=1250.50,
            realized_pnl=980.25,
            unrealized_pnl=270.25,
            max_drawdown=150.0,
            max_drawdown_pct=2.5,
            avg_pnl=29.77,
            trade_metrics=TradeMetrics(
                total_trades=42,
                winning_trades=28,
                losing_trades=14,
                win_rate=66.7,
                avg_pnl_per_trade=29.77,
                avg_win=55.30,
                avg_loss=-21.20,
                largest_win=125.50,
                largest_loss=-45.25,
                total_volume=125000.0,
            ),
            risk_metrics=RiskMetrics(
                sharpe_ratio=1.85,
                volatility=0.025,
                max_drawdown=150.0,
                max_drawdown_pct=2.5,
                var_95=41.13,
                exposure_pct=65.0,
            ),
            open_positions=5,
            portfolio_value=50000.0,
        )
