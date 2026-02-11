"""Tests for data quality validator."""

from datetime import datetime, timedelta

from exchange_data.binance.config import BinanceConfig
from exchange_data.binance.orderbook import (
    OrderBookLevel,
    OrderBookSnapshot,
    OrderBookTracker,
)
from exchange_data.binance.validator import (
    DataQualityReport,
    DataQualityValidator,
    QualityCheckResult,
)


class TestQualityCheckResult:
    """Test QualityCheckResult dataclass."""

    def test_creation(self) -> None:
        """Test creating a check result."""
        result = QualityCheckResult(
            check_name="freshness",
            passed=True,
            symbol="BTCUSDT",
            details="Data is fresh",
        )

        assert result.check_name == "freshness"
        assert result.passed is True
        assert result.symbol == "BTCUSDT"
        assert result.timestamp is not None


class TestDataQualityReport:
    """Test DataQualityReport dataclass."""

    def test_creation(self) -> None:
        """Test creating a report."""
        check = QualityCheckResult(
            check_name="freshness",
            passed=True,
            symbol="BTCUSDT",
        )
        report = DataQualityReport(
            timestamp=datetime.utcnow(),
            overall_passed=True,
            checks=[check],
            summary="All checks passed",
        )

        assert report.overall_passed is True
        assert len(report.checks) == 1

    def test_to_dict(self) -> None:
        """Test dictionary conversion."""
        check = QualityCheckResult(
            check_name="freshness",
            passed=True,
            symbol="BTCUSDT",
            details="Data is fresh",
        )
        report = DataQualityReport(
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
            overall_passed=True,
            checks=[check],
            summary="All checks passed",
        )

        data = report.to_dict()
        assert data["overall_passed"] is True
        assert data["summary"] == "All checks passed"
        assert len(data["checks"]) == 1


class TestDataQualityValidator:
    """Test DataQualityValidator functionality."""

    def test_validate_snapshot_freshness_pass(self) -> None:
        """Test freshness check passes."""
        validator = DataQualityValidator()
        snapshot = OrderBookSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),  # Fresh
            last_update_id=1,
            bids=[OrderBookLevel(price=50000.0, quantity=1.0)],
            asks=[OrderBookLevel(price=50001.0, quantity=1.0)],
        )

        results = validator.validate_snapshot(snapshot)
        freshness_result = next(r for r in results if r.check_name == "freshness")

        assert freshness_result.passed is True

    def test_validate_snapshot_freshness_fail(self) -> None:
        """Test freshness check fails for stale data."""
        config = BinanceConfig(freshness_threshold_sec=5)
        validator = DataQualityValidator(config)
        snapshot = OrderBookSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime.utcnow() - timedelta(seconds=10),  # Stale
            last_update_id=1,
            bids=[OrderBookLevel(price=50000.0, quantity=1.0)],
            asks=[OrderBookLevel(price=50001.0, quantity=1.0)],
        )

        results = validator.validate_snapshot(snapshot)
        freshness_result = next(r for r in results if r.check_name == "freshness")

        assert freshness_result.passed is False

    def test_validate_snapshot_valid_price(self) -> None:
        """Test valid price check."""
        validator = DataQualityValidator()
        snapshot = OrderBookSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            last_update_id=1,
            bids=[OrderBookLevel(price=50000.0, quantity=1.0)],
            asks=[OrderBookLevel(price=50001.0, quantity=1.0)],
        )

        results = validator.validate_snapshot(snapshot)
        price_result = next(r for r in results if r.check_name == "valid_price")

        assert price_result.passed is True

    def test_validate_snapshot_invalid_price(self) -> None:
        """Test invalid price check."""
        validator = DataQualityValidator()
        snapshot = OrderBookSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            last_update_id=1,
            bids=[],
            asks=[],
        )

        results = validator.validate_snapshot(snapshot)
        price_result = next(r for r in results if r.check_name == "valid_price")

        assert price_result.passed is False

    def test_validate_snapshot_price_accuracy_pass(self) -> None:
        """Test price accuracy check passes."""
        config = BinanceConfig(price_accuracy_pct=0.01)
        validator = DataQualityValidator(config)
        snapshot = OrderBookSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            last_update_id=1,
            bids=[OrderBookLevel(price=50000.0, quantity=1.0)],
            asks=[OrderBookLevel(price=50000.5, quantity=1.0)],
        )

        results = validator.validate_snapshot(snapshot, reference_price=50000.25)
        accuracy_result = next(r for r in results if r.check_name == "price_accuracy")

        assert accuracy_result.passed is True

    def test_validate_snapshot_price_accuracy_fail(self) -> None:
        """Test price accuracy check fails."""
        config = BinanceConfig(price_accuracy_pct=0.01)
        validator = DataQualityValidator(config)
        snapshot = OrderBookSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            last_update_id=1,
            bids=[OrderBookLevel(price=51000.0, quantity=1.0)],  # 2% off
            asks=[OrderBookLevel(price=51001.0, quantity=1.0)],
        )

        results = validator.validate_snapshot(snapshot, reference_price=50000.0)
        accuracy_result = next(r for r in results if r.check_name == "price_accuracy")

        assert accuracy_result.passed is False

    def test_validate_snapshot_non_empty_book_pass(self) -> None:
        """Test non-empty book check passes."""
        validator = DataQualityValidator()
        snapshot = OrderBookSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            last_update_id=1,
            bids=[OrderBookLevel(price=50000.0, quantity=1.0)],
            asks=[OrderBookLevel(price=50001.0, quantity=1.0)],
        )

        results = validator.validate_snapshot(snapshot)
        book_result = next(r for r in results if r.check_name == "non_empty_book")

        assert book_result.passed is True

    def test_validate_snapshot_non_empty_book_fail(self) -> None:
        """Test non-empty book check fails."""
        validator = DataQualityValidator()
        snapshot = OrderBookSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            last_update_id=1,
            bids=[],
            asks=[],
        )

        results = validator.validate_snapshot(snapshot)
        book_result = next(r for r in results if r.check_name == "non_empty_book")

        assert book_result.passed is False

    def test_validate_tracker_no_gaps(self) -> None:
        """Test gap detection with no gaps."""
        validator = DataQualityValidator()
        tracker = OrderBookTracker()

        # Add snapshots without gaps
        for i in range(3):
            snapshot = OrderBookSnapshot(
                symbol="BTCUSDT",
                timestamp=datetime.utcnow() - timedelta(seconds=i),
                last_update_id=i,
                bids=[OrderBookLevel(price=50000.0, quantity=1.0)],
                asks=[OrderBookLevel(price=50001.0, quantity=1.0)],
            )
            tracker.add_snapshot(snapshot)

        results = validator.validate_tracker(tracker)
        gap_result = next(r for r in results if r.check_name == "no_gaps")

        assert gap_result.passed is True

    def test_validate_tracker_with_gaps(self) -> None:
        """Test gap detection with gaps."""
        config = BinanceConfig(freshness_threshold_sec=5)
        validator = DataQualityValidator(config)
        tracker = OrderBookTracker()

        # Add snapshots with a gap
        snapshot1 = OrderBookSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
            last_update_id=1,
            bids=[OrderBookLevel(price=50000.0, quantity=1.0)],
            asks=[OrderBookLevel(price=50001.0, quantity=1.0)],
        )
        snapshot2 = OrderBookSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime(2024, 1, 1, 12, 0, 10),  # 10 second gap
            last_update_id=2,
            bids=[OrderBookLevel(price=50000.0, quantity=1.0)],
            asks=[OrderBookLevel(price=50001.0, quantity=1.0)],
        )

        tracker.add_snapshot(snapshot1)
        tracker.add_snapshot(snapshot2)

        results = validator.validate_tracker(tracker)
        gap_result = next(r for r in results if r.check_name == "no_gaps")

        assert gap_result.passed is False

    def test_validate_tracker_no_duplicates(self) -> None:
        """Test duplicate detection with no duplicates."""
        validator = DataQualityValidator()
        tracker = OrderBookTracker()

        snapshot1 = OrderBookSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            last_update_id=1,
            bids=[],
            asks=[],
        )
        snapshot2 = OrderBookSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            last_update_id=2,
            bids=[],
            asks=[],
        )

        tracker.add_snapshot(snapshot1)
        tracker.add_snapshot(snapshot2)

        results = validator.validate_tracker(tracker)
        dup_result = next(r for r in results if r.check_name == "no_duplicates")

        assert dup_result.passed is True

    def test_validate_tracker_with_duplicates(self) -> None:
        """Test duplicate detection with duplicates."""
        validator = DataQualityValidator()
        tracker = OrderBookTracker()

        snapshot1 = OrderBookSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            last_update_id=1,
            bids=[],
            asks=[],
        )
        snapshot2 = OrderBookSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            last_update_id=1,  # Duplicate
            bids=[],
            asks=[],
        )

        tracker.add_snapshot(snapshot1)
        tracker.add_snapshot(snapshot2)

        results = validator.validate_tracker(tracker)
        dup_result = next(r for r in results if r.check_name == "no_duplicates")

        assert dup_result.passed is False

    def test_generate_report_pass(self) -> None:
        """Test report generation when all checks pass."""
        validator = DataQualityValidator()
        tracker = OrderBookTracker()

        snapshot = OrderBookSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            last_update_id=1,
            bids=[OrderBookLevel(price=50000.0, quantity=1.0)],
            asks=[OrderBookLevel(price=50001.0, quantity=1.0)],
        )
        tracker.add_snapshot(snapshot)

        report = validator.generate_report(tracker, [snapshot])

        assert report.overall_passed is True
        assert "PASSED" in report.summary

    def test_generate_report_fail(self) -> None:
        """Test report generation when checks fail."""
        validator = DataQualityValidator()
        tracker = OrderBookTracker()

        snapshot = OrderBookSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime.utcnow() - timedelta(seconds=100),  # Stale
            last_update_id=1,
            bids=[OrderBookLevel(price=50000.0, quantity=1.0)],
            asks=[OrderBookLevel(price=50001.0, quantity=1.0)],
        )
        tracker.add_snapshot(snapshot)

        report = validator.generate_report(tracker, [snapshot])

        assert report.overall_passed is False
        assert "FAILED" in report.summary

    def test_get_failing_symbols(self) -> None:
        """Test getting failing symbols."""
        validator = DataQualityValidator()

        check1 = QualityCheckResult(
            check_name="freshness",
            passed=False,
            symbol="BTCUSDT",
        )
        check2 = QualityCheckResult(
            check_name="freshness",
            passed=True,
            symbol="ETHUSDT",
        )
        check3 = QualityCheckResult(
            check_name="valid_price",
            passed=False,
            symbol="BTCUSDT",
        )

        report = DataQualityReport(
            timestamp=datetime.utcnow(),
            overall_passed=False,
            checks=[check1, check2, check3],
            summary="Some checks failed",
        )

        failing = validator.get_failing_symbols(report)

        assert "BTCUSDT" in failing
        assert "ETHUSDT" not in failing
