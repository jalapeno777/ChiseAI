"""Data quality validation for exchange data."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set

from exchange_data.binance.config import BinanceConfig
from exchange_data.binance.orderbook import OrderBookSnapshot, OrderBookTracker


@dataclass
class QualityCheckResult:
    """Result of a data quality check.

    Attributes:
        check_name: Name of the quality check
        passed: Whether the check passed
        symbol: Trading pair symbol (if applicable)
        details: Additional details about the check
        timestamp: When the check was performed
    """

    check_name: str
    passed: bool
    symbol: Optional[str] = None
    details: str = ""
    timestamp: datetime = None  # type: ignore

    def __post_init__(self) -> None:
        """Set default timestamp."""
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


@dataclass
class DataQualityReport:
    """Comprehensive data quality report.

    Attributes:
        timestamp: Report generation time
        overall_passed: Whether all checks passed
        checks: List of individual check results
        summary: Human-readable summary
    """

    timestamp: datetime
    overall_passed: bool
    checks: List[QualityCheckResult]
    summary: str

    def to_dict(self) -> Dict:
        """Convert report to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "overall_passed": self.overall_passed,
            "summary": self.summary,
            "checks": [
                {
                    "check_name": c.check_name,
                    "passed": c.passed,
                    "symbol": c.symbol,
                    "details": c.details,
                    "timestamp": c.timestamp.isoformat(),
                }
                for c in self.checks
            ],
        }


class DataQualityValidator:
    """Validate data quality for exchange market data.

    Performs checks for:
    - Data freshness (no stale data)
    - Data gaps (no missing intervals)
    - Duplicates (no duplicate update IDs)
    - Price accuracy (within tolerance)
    """

    def __init__(self, config: Optional[BinanceConfig] = None) -> None:
        """Initialize validator.

        Args:
            config: Binance configuration
        """
        self.config = config or BinanceConfig()
        self._price_history: Dict[
            str, List[tuple]
        ] = {}  # symbol -> [(timestamp, price)]

    def validate_snapshot(
        self, snapshot: OrderBookSnapshot, reference_price: Optional[float] = None
    ) -> List[QualityCheckResult]:
        """Validate a single order book snapshot.

        Args:
            snapshot: Order book snapshot to validate
            reference_price: Optional reference price for accuracy check

        Returns:
            List of quality check results
        """
        results = []
        symbol = snapshot.symbol

        # Check freshness
        age_sec = (datetime.utcnow() - snapshot.timestamp).total_seconds()
        freshness_pass = age_sec <= self.config.freshness_threshold_sec
        results.append(
            QualityCheckResult(
                check_name="freshness",
                passed=freshness_pass,
                symbol=symbol,
                details=f"Data age: {age_sec:.2f}s (threshold: {self.config.freshness_threshold_sec}s)",
            )
        )

        # Check for valid prices
        mid_price = snapshot.mid_price
        price_valid = mid_price is not None and mid_price > 0
        results.append(
            QualityCheckResult(
                check_name="valid_price",
                passed=price_valid,
                symbol=symbol,
                details=f"Mid price: {mid_price}",
            )
        )

        # Check price accuracy against reference
        if reference_price is not None and price_valid and mid_price is not None:
            price_diff_pct = abs(mid_price - reference_price) / reference_price * 100
            accuracy_pass = price_diff_pct <= self.config.price_accuracy_pct
            results.append(
                QualityCheckResult(
                    check_name="price_accuracy",
                    passed=accuracy_pass,
                    symbol=symbol,
                    details=f"Price diff: {price_diff_pct:.4f}% (threshold: {self.config.price_accuracy_pct}%)",
                )
            )

        # Check for non-empty book
        book_valid = len(snapshot.bids) > 0 and len(snapshot.asks) > 0
        results.append(
            QualityCheckResult(
                check_name="non_empty_book",
                passed=book_valid,
                symbol=symbol,
                details=f"Bids: {len(snapshot.bids)}, Asks: {len(snapshot.asks)}",
            )
        )

        # Store price for future gap detection
        if price_valid and mid_price is not None:
            if symbol not in self._price_history:
                self._price_history[symbol] = []
            self._price_history[symbol].append((snapshot.timestamp, mid_price))
            # Keep last 1000 prices
            self._price_history[symbol] = self._price_history[symbol][-1000:]

        return results

    def validate_tracker(self, tracker: OrderBookTracker) -> List[QualityCheckResult]:
        """Validate order book tracker for all symbols.

        Args:
            tracker: Order book tracker with history

        Returns:
            List of quality check results
        """
        results = []

        for symbol in tracker.get_all_symbols():
            # Check for gaps
            gaps = tracker.detect_gaps(symbol, self.config.freshness_threshold_sec)
            gaps_pass = len(gaps) == 0
            gap_details = f"Found {len(gaps)} gaps" if gaps else "No gaps detected"
            if gaps:
                gap_details += f"; largest: {max(g['duration_sec'] for g in gaps):.1f}s"

            results.append(
                QualityCheckResult(
                    check_name="no_gaps",
                    passed=gaps_pass,
                    symbol=symbol,
                    details=gap_details,
                )
            )

            # Check for duplicates
            has_dups = tracker.has_duplicates(symbol)
            results.append(
                QualityCheckResult(
                    check_name="no_duplicates",
                    passed=not has_dups,
                    symbol=symbol,
                    details="Duplicate update IDs found"
                    if has_dups
                    else "No duplicates",
                )
            )

        return results

    def generate_report(
        self, tracker: OrderBookTracker, snapshots: List[OrderBookSnapshot]
    ) -> DataQualityReport:
        """Generate comprehensive quality report.

        Args:
            tracker: Order book tracker
            snapshots: Recent snapshots to validate

        Returns:
            Data quality report
        """
        all_checks: List[QualityCheckResult] = []

        # Validate recent snapshots
        for snapshot in snapshots:
            all_checks.extend(self.validate_snapshot(snapshot))

        # Validate tracker history
        all_checks.extend(self.validate_tracker(tracker))

        # Calculate overall status
        passed_count = sum(1 for c in all_checks if c.passed)
        total_count = len(all_checks)
        overall_passed = passed_count == total_count

        # Generate summary
        failed_checks = [c for c in all_checks if not c.passed]
        if failed_checks:
            summary = f"FAILED: {len(failed_checks)}/{total_count} checks failed. "
            failed_by_symbol: Dict[Optional[str], int] = {}
            for c in failed_checks:
                failed_by_symbol[c.symbol] = failed_by_symbol.get(c.symbol, 0) + 1
            summary += "Issues by symbol: " + ", ".join(
                f"{s or 'global'}:{n}" for s, n in failed_by_symbol.items()
            )
        else:
            summary = f"PASSED: All {total_count} checks passed."

        return DataQualityReport(
            timestamp=datetime.utcnow(),
            overall_passed=overall_passed,
            checks=all_checks,
            summary=summary,
        )

    def get_failing_symbols(self, report: DataQualityReport) -> Set[str]:
        """Get set of symbols with failing checks.

        Args:
            report: Data quality report

        Returns:
            Set of symbol names with failures
        """
        failing = set()
        for check in report.checks:
            if not check.passed and check.symbol:
                failing.add(check.symbol)
        return failing
