#!/usr/bin/env python3
"""Paper Trading KPI Calculator for PAPER-GO-REMEDIATION-001.

Calculates canonical live KPIs from paper trading data in Redis:
- Win Rate: winning_trades / total_trades
- Max Drawdown: maximum peak-to-trough decline
- Turnover: trades per day (aggregated by UTC day)
- Latency p50/p95/p99 from order timestamps
- Risk-gate adherence: % of trades passing all risk checks

Usage:
    python scripts/analysis/calculate_paper_kpis.py
    python scripts/analysis/calculate_paper_kpis.py --days 7 --output-dir docs/validation/evidence

Environment Variables:
    REDIS_HOST - Redis host (default: host.docker.internal)
    REDIS_PORT - Redis port (default: 6380)
    REDIS_DB - Redis database (default: 0)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Add src to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

# Import after path setup
try:
    import redis
except ImportError:
    logger.error("redis package not installed. Run: pip install redis")
    sys.exit(1)


@dataclass
class KPIDataPoint:
    """Single KPI data point with timestamp."""

    timestamp: str
    value: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LatencyStats:
    """Latency statistics."""

    p50_ms: float
    p95_ms: float
    p99_ms: float
    count: int


@dataclass
class PaperTradingKPIs:
    """Canonical KPIs for paper trading performance."""

    # Metadata
    calculation_id: str
    story_id: str
    calculation_timestamp: str
    data_start_time: str
    data_end_time: str
    lookback_days: int

    # Trade counts
    total_trades: int
    winning_trades: int
    losing_trades: int
    open_trades: int

    # Core KPIs
    win_rate: float  # percentage
    total_pnl: float  # Net PnL (total_net_pnl alias)
    total_net_pnl: float  # Sum of net_pnl (realized_pnl - fees)
    total_gross_pnl: float  # Sum of realized_pnl (without fee deduction)
    total_fees: float  # Sum of fees
    fee_impact_percent: float  # Percentage of gross PnL lost to fees
    avg_pnl_per_trade: float
    max_drawdown: float  # percentage
    max_drawdown_amount: float

    # Turnover
    turnover: dict[str, Any]  # trades per day aggregated by UTC day

    # Latency stats
    latency_ms: LatencyStats | None

    # Risk gate adherence
    risk_gate_adherence: float  # percentage passing all checks

    # Data quality
    data_freshness_hours: float
    is_data_fresh: bool
    net_pnl_validation_passed: (
        bool  # True if net_pnl = realized_pnl - fees for all entries
    )
    data_quality_flags: list[str]  # List of data quality issues
    target_assessment: dict[str, Any] = field(default_factory=dict)


def calculate_percentile(values: list[float], percentile: float) -> float:
    """Calculate percentile using linear interpolation.

    Args:
        values: Sorted list of values
        percentile: Percentile to calculate (0-100)

    Returns:
        Percentile value
    """
    if not values:
        return 0.0

    sorted_values = sorted(values)
    n = len(sorted_values)

    if n == 1:
        return sorted_values[0]

    k = (n - 1) * percentile / 100.0
    f = int(k)
    c = min(f + 1, n - 1)

    return sorted_values[f] + (k - f) * (sorted_values[c] - sorted_values[f])


def calculate_max_drawdown(pnl_series: list[float]) -> tuple[float, float]:
    """Calculate maximum drawdown from PnL series.

    Args:
        pnl_series: List of PnL values in chronological order

    Returns:
        Tuple of (max_drawdown_percentage, max_drawdown_amount)
    """
    if not pnl_series:
        return 0.0, 0.0

    cumulative = 0.0
    peak = 0.0
    max_dd_pct = 0.0
    max_dd_amount = 0.0

    for pnl in pnl_series:
        cumulative += pnl
        if cumulative > peak:
            peak = cumulative
        else:
            drawdown = peak - cumulative
            drawdown_pct = (drawdown / peak * 100) if peak > 0 else 0.0
            if drawdown_pct > max_dd_pct:
                max_dd_pct = drawdown_pct
                max_dd_amount = drawdown

    return max_dd_pct, max_dd_amount


def calculate_turnover(entries: list[dict], lookback_days: int) -> dict[str, Any]:
    """Calculate turnover as trades per day aggregated by UTC day.

    Args:
        entries: List of trade journal entries
        lookback_days: Number of days in lookback period

    Returns:
        Dictionary with turnover metrics
    """
    from collections import defaultdict

    trades_by_day: dict[str, int] = defaultdict(int)

    for entry in entries:
        entry_time_str = entry.get("entry_time", "")
        if not entry_time_str:
            continue

        try:
            entry_time = datetime.fromisoformat(entry_time_str.replace("Z", "+00:00"))
            day_key = entry_time.strftime("%Y-%m-%d")
            trades_by_day[day_key] += 1
        except (ValueError, TypeError):
            continue

    if not trades_by_day:
        return {
            "avg_trades_per_day": 0.0,
            "p95_trades_per_day": 0.0,
            "max_trades_per_day": 0,
            "total_days": 0,
            "daily_counts": {},
        }

    daily_counts = list(trades_by_day.values())

    return {
        "avg_trades_per_day": round(sum(daily_counts) / len(daily_counts), 2),
        "p95_trades_per_day": round(calculate_percentile(daily_counts, 95), 2),
        "max_trades_per_day": max(daily_counts),
        "total_days": len(daily_counts),
        "daily_counts": dict(trades_by_day),
    }


def calculate_latency_stats(entries: list[dict]) -> LatencyStats | None:
    """Calculate latency statistics from trade entries.

    Args:
        entries: List of trade journal entries

    Returns:
        LatencyStats or None if no latency data available
    """
    latencies = []

    for entry in entries:
        # Calculate latency from entry_time to exit_time if both exist
        entry_time_str = entry.get("entry_time", "")
        exit_time_str = entry.get("exit_time", "")

        if not entry_time_str or not exit_time_str:
            continue

        try:
            entry_time = datetime.fromisoformat(entry_time_str.replace("Z", "+00:00"))
            exit_time = datetime.fromisoformat(exit_time_str.replace("Z", "+00:00"))
            latency_ms = (exit_time - entry_time).total_seconds() * 1000

            # Only include positive latencies (sanity check)
            if latency_ms >= 0:
                latencies.append(latency_ms)
        except (ValueError, TypeError):
            continue

    if not latencies:
        return None

    return LatencyStats(
        p50_ms=round(calculate_percentile(latencies, 50), 2),
        p95_ms=round(calculate_percentile(latencies, 95), 2),
        p99_ms=round(calculate_percentile(latencies, 99), 2),
        count=len(latencies),
    )


def assess_targets(kpis: PaperTradingKPIs) -> dict[str, Any]:
    """Assess KPIs against targets.

    Args:
        kpis: Calculated KPIs

    Returns:
        Dictionary with target assessments
    """
    assessments = {
        "win_rate": {
            "value": round(kpis.win_rate, 2),
            "target": "> 55%",
            "passed": kpis.win_rate > 55.0,
        },
        "max_drawdown": {
            "value": round(kpis.max_drawdown, 2),
            "target": "< 5%",
            "passed": kpis.max_drawdown < 5.0,
        },
        "data_freshness": {
            "value": round(kpis.data_freshness_hours, 2),
            "target": "< 24 hours",
            "passed": kpis.is_data_fresh,
        },
        "risk_gate_adherence": {
            "value": round(kpis.risk_gate_adherence, 2),
            "target": "> 95%",
            "passed": kpis.risk_gate_adherence >= 95.0,
        },
    }

    # Overall assessment
    all_passed = all(a["passed"] for a in assessments.values())
    passed_count = sum(1 for a in assessments.values() if a["passed"])

    assessments["overall"] = {
        "status": "PASS" if all_passed else "FAIL",
        "passed_count": passed_count,
        "total_count": len([k for k in assessments.keys() if k != "overall"]),
    }

    return assessments


class RedisPaperKPIExtractor:
    """Extract paper trading data from Redis and calculate KPIs."""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        db: int = 0,
    ) -> None:
        """Initialize Redis connection.

        Args:
            host: Redis host (default: from env or host.docker.internal)
            port: Redis port (default: from env or 6380)
            db: Redis database (default: 0)
        """
        self.host = host or os.getenv("REDIS_HOST", "host.docker.internal")
        self.port = port or int(os.getenv("REDIS_PORT", "6380"))
        self.db = db
        self.client: redis.Redis | None = None

    def connect(self) -> bool:
        """Connect to Redis.

        Returns:
            True if connection successful
        """
        try:
            self.client = redis.Redis(
                host=self.host,
                port=self.port,
                db=self.db,
                decode_responses=True,
                socket_connect_timeout=5,
            )
            self.client.ping()
            logger.info(f"Connected to Redis at {self.host}:{self.port}/{self.db}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            return False

    def fetch_journal_entries(self, lookback_days: int = 7) -> list[dict]:
        """Fetch all paper journal entries from Redis within lookback period.

        Args:
            lookback_days: Number of days to look back

        Returns:
            List of journal entry dictionaries
        """
        if not self.client:
            raise RuntimeError("Not connected to Redis")

        entries = []
        cutoff_time = datetime.now(UTC) - timedelta(days=lookback_days)

        # Scan for all paper journal entry keys
        cursor = 0
        entry_keys = []

        while True:
            cursor, keys = self.client.scan(
                cursor=cursor,
                match="paper:journal:*:entry:*",
                count=100,
            )
            entry_keys.extend(keys)
            if cursor == 0:
                break

        logger.info(f"Found {len(entry_keys)} journal entry keys")

        for key in entry_keys:
            try:
                data = self.client.hget(key, "data")
                if data:
                    entry = json.loads(data)

                    # Filter by time
                    entry_time_str = entry.get("entry_time", "")
                    if entry_time_str:
                        try:
                            entry_time = datetime.fromisoformat(
                                entry_time_str.replace("Z", "+00:00")
                            )
                            if entry_time >= cutoff_time:
                                entries.append(entry)
                        except (ValueError, TypeError):
                            # Include entries with invalid timestamps anyway
                            entries.append(entry)
                    else:
                        entries.append(entry)
            except (json.JSONDecodeError, Exception) as e:
                logger.warning(f"Failed to parse entry {key}: {e}")
                continue

        logger.info(f"Fetched {len(entries)} entries within lookback period")
        return entries

    def fetch_risk_gate_data(self, lookback_days: int = 7) -> tuple[int, int]:
        """Fetch risk gate statistics.

        Args:
            lookback_days: Number of days to look back

        Returns:
            Tuple of (passed_count, total_count)
        """
        if not self.client:
            raise RuntimeError("Not connected to Redis")

        cutoff_time = datetime.now(UTC) - timedelta(days=lookback_days)

        # Look for risk check results in journal entries
        # For now, we'll infer from trade status
        entries = self.fetch_journal_entries(lookback_days)

        total = len(entries)
        # Count entries that weren't rejected
        passed = sum(
            1
            for e in entries
            if e.get("exit_reason") not in ("rejected", "risk_reduction")
        )

        return passed, total


class PaperKPICalculator:
    """Calculate KPIs from paper trading data."""

    def __init__(self, extractor: RedisPaperKPIExtractor) -> None:
        """Initialize calculator.

        Args:
            extractor: Redis data extractor
        """
        self.extractor = extractor

    def calculate(
        self, lookback_days: int = 7, story_id: str = "PAPER-GO-REMEDIATION-001"
    ) -> PaperTradingKPIs:
        """Calculate all KPIs.

        Args:
            lookback_days: Number of days to look back
            story_id: Story ID for tracking

        Returns:
            PaperTradingKPIs with all calculated metrics
        """
        logger.info(f"Calculating KPIs for last {lookback_days} days...")

        # Fetch data
        entries = self.extractor.fetch_journal_entries(lookback_days)

        if not entries:
            logger.warning("No entries found in lookback period")
            return self._create_empty_kpis(lookback_days, story_id)

        # Parse timestamps for data range
        timestamps = []
        for entry in entries:
            entry_time_str = entry.get("entry_time", "")
            if entry_time_str:
                try:
                    ts = datetime.fromisoformat(entry_time_str.replace("Z", "+00:00"))
                    timestamps.append(ts)
                except (ValueError, TypeError):
                    continue

        data_start = min(timestamps) if timestamps else datetime.now(UTC)
        data_end = max(timestamps) if timestamps else datetime.now(UTC)

        # Calculate trade counts
        closed_entries = [e for e in entries if e.get("is_closed", False)]
        open_entries = [e for e in entries if e.get("is_open", True)]

        # Validate net_pnl calculation and collect data quality flags
        data_quality_flags = []
        validation_failures = 0

        for entry in closed_entries:
            entry_id = entry.get("entry_id", "unknown")
            net_pnl = entry.get("net_pnl", 0)
            realized_pnl = entry.get("realized_pnl", 0)
            fees = entry.get("fees", 0)

            # Check for missing fee data
            if fees is None or fees == 0:
                # This might be valid for some exchanges, but flag it
                if fees is None:
                    data_quality_flags.append(f"Entry {entry_id}: Missing fee data")

            # Validate net_pnl formula: net_pnl = realized_pnl - fees
            if realized_pnl is not None and fees is not None:
                expected_net_pnl = realized_pnl - fees
                if abs(net_pnl - expected_net_pnl) > 1e-9:
                    validation_failures += 1
                    logger.warning(
                        f"net_pnl validation failed for {entry_id}: "
                        f"net_pnl={net_pnl}, realized_pnl={realized_pnl}, fees={fees}, "
                        f"expected={expected_net_pnl}"
                    )

            # Check for entries with fees > realized_pnl (negative net_pnl on winning trades)
            if (
                fees is not None
                and realized_pnl is not None
                and fees > 0
                and realized_pnl > 0
                and fees > realized_pnl
            ):
                data_quality_flags.append(
                    f"Entry {entry_id}: Fees ({fees}) exceed realized_pnl ({realized_pnl})"
                )

        net_pnl_validation_passed = validation_failures == 0
        if not net_pnl_validation_passed:
            data_quality_flags.append(
                f"net_pnl validation: {validation_failures} entries with incorrect formula"
            )

        winning_trades = [e for e in closed_entries if e.get("net_pnl", 0) > 0]
        losing_trades = [e for e in closed_entries if e.get("net_pnl", 0) < 0]

        # Calculate PnL metrics with gross vs net separation
        total_net_pnl = sum(e.get("net_pnl") or 0 for e in closed_entries)
        total_gross_pnl = sum(e.get("realized_pnl") or 0 for e in closed_entries)
        total_fees = sum(e.get("fees") or 0 for e in closed_entries)

        # Calculate fee impact percentage
        fee_impact_percent = 0.0
        if abs(total_gross_pnl) > 1e-9:
            fee_impact_percent = (total_fees / abs(total_gross_pnl)) * 100

        # Calculate win rate
        win_rate = (
            (len(winning_trades) / len(closed_entries) * 100) if closed_entries else 0.0
        )

        # Calculate drawdown
        pnl_series = [e.get("net_pnl", 0) for e in closed_entries]
        max_dd_pct, max_dd_amount = calculate_max_drawdown(pnl_series)

        # Calculate turnover
        turnover = calculate_turnover(entries, lookback_days)

        # Calculate latency stats
        latency_stats = calculate_latency_stats(entries)

        # Calculate risk gate adherence
        passed_risk, total_risk = self.extractor.fetch_risk_gate_data(lookback_days)
        risk_adherence = (passed_risk / total_risk * 100) if total_risk > 0 else 100.0

        # Calculate data freshness
        now = datetime.now(UTC)
        most_recent = max(timestamps) if timestamps else now
        freshness_hours = (now - most_recent).total_seconds() / 3600

        # Build KPI object
        kpis = PaperTradingKPIs(
            calculation_id=f"PAPER-KPI-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}",
            story_id=story_id,
            calculation_timestamp=datetime.now(UTC).isoformat(),
            data_start_time=data_start.isoformat(),
            data_end_time=data_end.isoformat(),
            lookback_days=lookback_days,
            total_trades=len(entries),
            winning_trades=len(winning_trades),
            losing_trades=len(losing_trades),
            open_trades=len(open_entries),
            win_rate=round(win_rate, 2),
            total_pnl=round(total_net_pnl, 4),  # Alias for backward compatibility
            total_net_pnl=round(total_net_pnl, 4),
            total_gross_pnl=round(total_gross_pnl, 4),
            total_fees=round(total_fees, 4),
            fee_impact_percent=round(fee_impact_percent, 2),
            avg_pnl_per_trade=(
                round(total_net_pnl / len(closed_entries), 4) if closed_entries else 0.0
            ),
            max_drawdown=round(max_dd_pct, 2),
            max_drawdown_amount=round(max_dd_amount, 4),
            turnover=turnover,
            latency_ms=latency_stats,
            risk_gate_adherence=round(risk_adherence, 2),
            data_freshness_hours=round(freshness_hours, 2),
            is_data_fresh=freshness_hours < 24,
            net_pnl_validation_passed=net_pnl_validation_passed,
            data_quality_flags=data_quality_flags,
        )

        # Assess against targets
        kpis.target_assessment = assess_targets(kpis)

        return kpis

    def _create_empty_kpis(self, lookback_days: int, story_id: str) -> PaperTradingKPIs:
        """Create empty KPIs when no data available."""
        now = datetime.now(UTC)
        return PaperTradingKPIs(
            calculation_id=f"PAPER-KPI-{now.strftime('%Y%m%d-%H%M%S')}",
            story_id=story_id,
            calculation_timestamp=now.isoformat(),
            data_start_time=now.isoformat(),
            data_end_time=now.isoformat(),
            lookback_days=lookback_days,
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            open_trades=0,
            win_rate=0.0,
            total_pnl=0.0,
            total_net_pnl=0.0,
            total_gross_pnl=0.0,
            total_fees=0.0,
            fee_impact_percent=0.0,
            avg_pnl_per_trade=0.0,
            max_drawdown=0.0,
            max_drawdown_amount=0.0,
            turnover={
                "avg_trades_per_day": 0.0,
                "p95_trades_per_day": 0.0,
                "max_trades_per_day": 0,
                "total_days": 0,
                "daily_counts": {},
            },
            latency_ms=None,
            risk_gate_adherence=0.0,
            data_freshness_hours=float("inf"),
            is_data_fresh=False,
            net_pnl_validation_passed=True,  # No entries to validate
            data_quality_flags=["No data available for validation"],
            target_assessment={
                "overall": {
                    "status": "FAIL",
                    "passed_count": 0,
                    "total_count": 4,
                }
            },
        )


def generate_json_output(kpis: PaperTradingKPIs, output_path: Path) -> None:
    """Generate JSON output file.

    Args:
        kpis: Calculated KPIs
        output_path: Path to output file
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "calculation_id": kpis.calculation_id,
        "story_id": kpis.story_id,
        "calculation_timestamp": kpis.calculation_timestamp,
        "data_range": {
            "start_time": kpis.data_start_time,
            "end_time": kpis.data_end_time,
            "lookback_days": kpis.lookback_days,
        },
        "trade_summary": {
            "total_trades": kpis.total_trades,
            "winning_trades": kpis.winning_trades,
            "losing_trades": kpis.losing_trades,
            "open_trades": kpis.open_trades,
        },
        "kpis": {
            "win_rate_percent": kpis.win_rate,
            "total_pnl": kpis.total_pnl,
            "total_net_pnl": kpis.total_net_pnl,
            "total_gross_pnl": kpis.total_gross_pnl,
            "total_fees": kpis.total_fees,
            "fee_impact_percent": kpis.fee_impact_percent,
            "avg_pnl_per_trade": kpis.avg_pnl_per_trade,
            "max_drawdown_percent": kpis.max_drawdown,
            "max_drawdown_amount": kpis.max_drawdown_amount,
            "turnover": kpis.turnover,
            "latency_ms": asdict(kpis.latency_ms) if kpis.latency_ms else None,
            "risk_gate_adherence_percent": kpis.risk_gate_adherence,
        },
        "data_quality": {
            "freshness_hours": kpis.data_freshness_hours,
            "is_fresh": kpis.is_data_fresh,
            "net_pnl_validation_passed": kpis.net_pnl_validation_passed,
            "data_quality_flags": kpis.data_quality_flags,
        },
        "target_assessment": kpis.target_assessment,
    }

    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)

    logger.info(f"JSON output saved to: {output_path}")


def generate_markdown_report(kpis: PaperTradingKPIs, output_path: Path) -> None:
    """Generate Markdown summary report.

    Args:
        kpis: Calculated KPIs
        output_path: Path to output file
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    report = f"""# Paper Trading KPI Report

**Story ID:** {kpis.story_id}  
**Calculation ID:** {kpis.calculation_id}  
**Generated:** {kpis.calculation_timestamp}

## Data Range

| Metric | Value |
|--------|-------|
| Lookback Period | {kpis.lookback_days} days |
| Data Start | {kpis.data_start_time} |
| Data End | {kpis.data_end_time} |

## Trade Summary

| Metric | Value |
|--------|-------|
| Total Trades | {kpis.total_trades} |
| Winning Trades | {kpis.winning_trades} |
| Losing Trades | {kpis.losing_trades} |
| Open Trades | {kpis.open_trades} |

## Key Performance Indicators

| KPI | Value | Target | Status |
|-----|-------|--------|--------|
| Win Rate | {kpis.win_rate:.2f}% | > 55% | {"PASS" if kpis.win_rate > 55 else "FAIL"} |
| Max Drawdown | {kpis.max_drawdown:.2f}% | < 5% | {"PASS" if kpis.max_drawdown < 5 else "FAIL"} |
| Risk Gate Adherence | {kpis.risk_gate_adherence:.2f}% | >= 95% | {"PASS" if kpis.risk_gate_adherence >= 95 else "FAIL"} |
| **Gross PnL** | {kpis.total_gross_pnl:.4f} | - | - |
| **Total Fees** | {kpis.total_fees:.4f} | - | - |
| **Net PnL** | {kpis.total_net_pnl:.4f} | - | - |
| **Fee Impact** | {kpis.fee_impact_percent:.2f}% | - | - |
| Avg PnL/Trade | {kpis.avg_pnl_per_trade:.4f} | - | - |

## Turnover (Trades per Day)

| Metric | Value |
|--------|-------|
| Average | {kpis.turnover["avg_trades_per_day"]:.2f} trades/day |
| P95 | {kpis.turnover["p95_trades_per_day"]:.2f} trades/day |
| Maximum | {kpis.turnover["max_trades_per_day"]} trades/day |
| Trading Days | {kpis.turnover["total_days"]} |

### Daily Breakdown

| Date | Trade Count |
|------|-------------|
"""

    # Add daily counts
    for date, count in sorted(kpis.turnover.get("daily_counts", {}).items()):
        report += f"| {date} | {count} |\n"

    # Latency section
    if kpis.latency_ms:
        report += f"""
## Latency Statistics

| Percentile | Latency (ms) |
|------------|--------------|
| P50 | {kpis.latency_ms.p50_ms:.2f} |
| P95 | {kpis.latency_ms.p95_ms:.2f} |
| P99 | {kpis.latency_ms.p99_ms:.2f} |
| Count | {kpis.latency_ms.count} |
"""
    else:
        report += """
## Latency Statistics

*No latency data available*
"""

    # Data quality section
    freshness_status = "PASS" if kpis.is_data_fresh else "FAIL"
    validation_status = "PASS" if kpis.net_pnl_validation_passed else "FAIL"

    # Build data quality flags section
    flags_section = ""
    if kpis.data_quality_flags:
        flags_section = "\n### Data Quality Flags\n\n"
        for flag in kpis.data_quality_flags:
            flags_section += f"- ⚠️ {flag}\n"
    else:
        flags_section = (
            "\n### Data Quality Flags\n\n- ✅ No data quality issues detected\n"
        )

    report += f"""
## Data Quality

| Metric | Value | Status |
|--------|-------|--------|
| Freshness | {kpis.data_freshness_hours:.2f} hours | {freshness_status} |
| Net PnL Validation | {"Passed" if kpis.net_pnl_validation_passed else "Failed"} | {validation_status} |
| Target | < 24 hours | - |
{flags_section}
## Target Assessment Summary

**Overall Status:** {kpis.target_assessment.get("overall", {}).get("status", "UNKNOWN")}

**Passed:** {kpis.target_assessment.get("overall", {}).get("passed_count", 0)} / {kpis.target_assessment.get("overall", {}).get("total_count", 0)}

## Notes

- Win rate calculated from closed trades only
- Drawdown calculated from sequential PnL series
- Turnover aggregated by UTC calendar day
- Latency measured from entry to exit time
- Risk gate adherence inferred from trade outcomes

---

*Report generated by scripts/analysis/calculate_paper_kpis.py*
"""

    with open(output_path, "w") as f:
        f.write(report)

    logger.info(f"Markdown report saved to: {output_path}")


def print_summary(kpis: PaperTradingKPIs) -> None:
    """Print summary to console."""
    print("\n" + "=" * 60)
    print("PAPER TRADING KPI SUMMARY")
    print("=" * 60)
    print(f"\nCalculation ID: {kpis.calculation_id}")
    print(f"Data Range: {kpis.data_start_time} to {kpis.data_end_time}")
    print(f"\nTrade Summary:")
    print(f"  Total Trades: {kpis.total_trades}")
    print(f"  Winning: {kpis.winning_trades}")
    print(f"  Losing: {kpis.losing_trades}")
    print(f"  Open: {kpis.open_trades}")
    print(f"\nKey Metrics:")
    print(f"  Win Rate: {kpis.win_rate:.2f}%")
    print(f"  Gross PnL: {kpis.total_gross_pnl:.4f}")
    print(f"  Total Fees: {kpis.total_fees:.4f}")
    print(f"  Net PnL: {kpis.total_net_pnl:.4f}")
    print(f"  Fee Impact: {kpis.fee_impact_percent:.2f}%")
    print(f"  Max Drawdown: {kpis.max_drawdown:.2f}%")
    print(f"  Turnover (avg): {kpis.turnover['avg_trades_per_day']:.2f} trades/day")
    print(f"  Risk Adherence: {kpis.risk_gate_adherence:.2f}%")

    if kpis.latency_ms:
        print(f"\nLatency (ms):")
        print(f"  P50: {kpis.latency_ms.p50_ms:.2f}")
        print(f"  P95: {kpis.latency_ms.p95_ms:.2f}")
        print(f"  P99: {kpis.latency_ms.p99_ms:.2f}")

    print(f"\nData Quality:")
    print(f"  Freshness: {kpis.data_freshness_hours:.2f} hours")
    print(f"  Is Fresh: {kpis.is_data_fresh}")
    print(
        f"  Net PnL Validation: {'PASS' if kpis.net_pnl_validation_passed else 'FAIL'}"
    )
    if kpis.data_quality_flags:
        print(f"  Quality Flags: {len(kpis.data_quality_flags)} issue(s)")

    overall = kpis.target_assessment.get("overall", {})
    print(f"\nTarget Assessment: {overall.get('status', 'UNKNOWN')}")
    print(f"  Passed: {overall.get('passed_count', 0)}/{overall.get('total_count', 0)}")
    print("=" * 60)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Calculate paper trading KPIs from Redis data"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Number of days to look back (default: 7)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="docs/validation/evidence",
        help="Output directory for reports (default: docs/validation/evidence)",
    )
    parser.add_argument(
        "--story-id",
        type=str,
        default="PAPER-GO-REMEDIATION-001",
        help="Story ID for tracking (default: PAPER-GO-REMEDIATION-001)",
    )
    parser.add_argument(
        "--redis-host",
        type=str,
        default=None,
        help="Redis host (default: from env or host.docker.internal)",
    )
    parser.add_argument(
        "--redis-port",
        type=int,
        default=None,
        help="Redis port (default: from env or 6380)",
    )

    args = parser.parse_args()

    # Connect to Redis
    extractor = RedisPaperKPIExtractor(
        host=args.redis_host,
        port=args.redis_port,
    )

    if not extractor.connect():
        logger.error("Failed to connect to Redis. Exiting.")
        return 1

    # Calculate KPIs
    calculator = PaperKPICalculator(extractor)
    kpis = calculator.calculate(
        lookback_days=args.days,
        story_id=args.story_id,
    )

    # Print summary
    print_summary(kpis)

    # Generate outputs
    output_dir = Path(args.output_dir)
    date_str = datetime.now(UTC).strftime("%Y%m%d")

    json_path = output_dir / f"{args.story_id}-KPI-SNAPSHOT-{date_str}.json"
    md_path = output_dir / f"{args.story_id}-KPI-REPORT-{date_str}.md"

    generate_json_output(kpis, json_path)
    generate_markdown_report(kpis, md_path)

    # Exit conditions check
    if kpis.total_trades == 0:
        logger.error("EXIT CONDITION: No trades found in lookback period")
        return 2

    if not kpis.is_data_fresh:
        logger.warning("EXIT CONDITION: Data is >24 hours stale")
        return 3

    logger.info("KPI calculation completed successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())
