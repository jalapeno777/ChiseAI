"""Comprehensive tests for FundingRateAnalyzer.

Tests cover:
- FundingRatePoint dataclass
- FundingTrend dataclass
- ExtremeFundingDetection dataclass
- FundingRateResult dataclass and confluence integration
- FundingRateAnalyzer: initialization, validation, metadata
- Bybit API integration (sync and async)
- Trend calculation (8h/24h/7d windows)
- Extreme funding detection with percentile thresholds
- Signal adjustment calculation
- Signal conversion
- Static utility methods
- Edge cases and error handling
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from market_analysis.fundamentals.funding_rate import (
    BYBIT_V5_PUBLIC,
    ExtremeFundingDetection,
    FundingDirection,
    FundingRateAnalyzer,
    FundingRatePoint,
    FundingRateResult,
    FundingTrend,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_rates() -> list[FundingRatePoint]:
    """Create sample funding rate data points (24 points, 8h intervals)."""
    now = datetime.now(UTC)
    rates = []
    for i in range(24):
        ts = int((now - timedelta(hours=8 * i)).timestamp() * 1000)
        # Varying funding rates with some extremes
        if i < 3:
            rate = 0.0003 + i * 0.0001  # Recent high rates
        elif i < 6:
            rate = 0.0001 + i * 0.00002  # Moderate
        elif i > 20:
            rate = -0.0002 - (i - 20) * 0.0001  # Old low rates
        else:
            rate = 0.00005 + i * 0.00001  # Low-moderate
        rates.append(
            FundingRatePoint(symbol="BTCUSDT", funding_rate=rate, timestamp=ts)
        )
    return rates


@pytest.fixture
def normal_rates() -> list[FundingRatePoint]:
    """Create normally-distributed funding rate data.

    All rates are positive and clustered around 0.0001 (0.01%),
    with the newest rate near the center of the distribution
    so it doesn't trigger extreme detection.
    """
    now = datetime.now(UTC)
    rates = []
    for i in range(50):
        ts = int((now - timedelta(hours=8 * i)).timestamp() * 1000)
        # Normal range centered on 0.0001, never zero or negative
        # Newest (i=0) = 0.0001 (center); i>0 cycles through -2..5
        offset = 0 if i == 0 else ((i - 1) % 10) - 2
        rate = 0.0001 + offset * 0.000005
        rates.append(
            FundingRatePoint(symbol="BTCUSDT", funding_rate=rate, timestamp=ts)
        )
    return rates


@pytest.fixture
def extreme_high_rates() -> list[FundingRatePoint]:
    """Create data with extremely high funding rates."""
    now = datetime.now(UTC)
    rates = []
    for i in range(30):
        ts = int((now - timedelta(hours=8 * i)).timestamp() * 1000)
        if i < 2:
            rate = 0.001  # Very extreme recent
        else:
            rate = 0.0001 + (i % 10) * 0.00001  # Normal
        rates.append(
            FundingRatePoint(symbol="BTCUSDT", funding_rate=rate, timestamp=ts)
        )
    return rates


@pytest.fixture
def extreme_low_rates() -> list[FundingRatePoint]:
    """Create data with extremely low (negative) funding rates."""
    now = datetime.now(UTC)
    rates = []
    for i in range(30):
        ts = int((now - timedelta(hours=8 * i)).timestamp() * 1000)
        if i < 2:
            rate = -0.001  # Very extreme negative recent
        else:
            rate = 0.0001 + (i % 10) * 0.00001  # Normal
        rates.append(
            FundingRatePoint(symbol="BTCUSDT", funding_rate=rate, timestamp=ts)
        )
    return rates


@pytest.fixture
def mock_bybit_response() -> dict:
    """Create a mock Bybit API response."""
    now = datetime.now(UTC)
    items = []
    for i in range(10):
        ts = int((now - timedelta(hours=8 * i)).timestamp() * 1000)
        items.append(
            {
                "symbol": "BTCUSDT",
                "fundingRate": f"{0.0001 + i * 0.00001:.6f}",
                "fundingRateTimestamp": str(ts),
            }
        )
    return {
        "retCode": 0,
        "retMsg": "OK",
        "result": {"category": "linear", "list": items},
    }


@pytest.fixture
def mock_bybit_error_response() -> dict:
    """Create a mock Bybit API error response."""
    return {
        "retCode": 10001,
        "retMsg": "Invalid symbol",
        "result": {},
    }


@pytest.fixture
def analyzer() -> FundingRateAnalyzer:
    """Create a FundingRateAnalyzer instance."""
    return FundingRateAnalyzer(symbol="BTCUSDT")


@pytest.fixture
def analyzer_with_client() -> FundingRateAnalyzer:
    """Create an analyzer with a mock HTTP client."""
    mock_client = MagicMock(spec=httpx.Client)
    return FundingRateAnalyzer(
        symbol="BTCUSDT",
        http_client=mock_client,
    )


# ---------------------------------------------------------------------------
# FundingRatePoint Tests
# ---------------------------------------------------------------------------


class TestFundingRatePoint:
    """Tests for FundingRatePoint dataclass."""

    def test_creation(self):
        """Test creating a funding rate point."""
        point = FundingRatePoint(
            symbol="BTCUSDT",
            funding_rate=0.0001,
            timestamp=1700000000000,
        )
        assert point.symbol == "BTCUSDT"
        assert point.funding_rate == 0.0001
        assert point.timestamp == 1700000000000

    def test_datetime_utc_property(self):
        """Test datetime conversion."""
        ts = int(datetime(2026, 1, 15, 12, 0, tzinfo=UTC).timestamp() * 1000)
        point = FundingRatePoint(symbol="BTCUSDT", funding_rate=0.0001, timestamp=ts)
        assert point.datetime_utc.year == 2026
        assert point.datetime_utc.month == 1

    def test_funding_rate_pct(self):
        """Test percentage conversion."""
        point = FundingRatePoint(symbol="BTCUSDT", funding_rate=0.0001, timestamp=0)
        assert point.funding_rate_pct == pytest.approx(0.01)

    def test_annualized_rate_pct(self):
        """Test annualized rate calculation."""
        point = FundingRatePoint(symbol="BTCUSDT", funding_rate=0.0001, timestamp=0)
        # 0.0001 * 100 * 3 * 365 = 10.95%
        assert point.annualized_rate_pct == pytest.approx(10.95)

    def test_negative_funding_rate(self):
        """Test negative funding rate."""
        point = FundingRatePoint(symbol="BTCUSDT", funding_rate=-0.0002, timestamp=0)
        assert point.funding_rate_pct == pytest.approx(-0.02)


# ---------------------------------------------------------------------------
# FundingTrend Tests
# ---------------------------------------------------------------------------


class TestFundingTrend:
    """Tests for FundingTrend dataclass."""

    def test_creation(self):
        """Test creating a funding trend."""
        trend = FundingTrend(
            window_label="8h",
            window_hours=8,
            mean=0.0001,
            median=0.0001,
            std=0.00002,
            min=0.00005,
            max=0.0002,
            trend_slope=0.000001,
            current=0.00015,
            sample_count=3,
        )
        assert trend.window_label == "8h"
        assert trend.window_hours == 8
        assert trend.mean == 0.0001
        assert trend.sample_count == 3


# ---------------------------------------------------------------------------
# ExtremeFundingDetection Tests
# ---------------------------------------------------------------------------


class TestExtremeFundingDetection:
    """Tests for ExtremeFundingDetection dataclass."""

    def test_not_extreme(self):
        """Test non-extreme detection."""
        detection = ExtremeFundingDetection(
            is_extreme=False,
            extreme_type="none",
            percentile_rank=50.0,
            high_threshold=0.0003,
            low_threshold=-0.0001,
            severity=0.0,
            message="Normal range",
        )
        assert not detection.is_extreme
        assert detection.extreme_type == "none"
        assert detection.severity == 0.0

    def test_extreme_high(self):
        """Test high extreme detection."""
        detection = ExtremeFundingDetection(
            is_extreme=True,
            extreme_type="high",
            percentile_rank=98.0,
            high_threshold=0.0003,
            low_threshold=-0.0001,
            severity=0.85,
            message="Extremely HIGH funding rate",
        )
        assert detection.is_extreme
        assert detection.extreme_type == "high"
        assert detection.severity == 0.85

    def test_extreme_low(self):
        """Test low extreme detection."""
        detection = ExtremeFundingDetection(
            is_extreme=True,
            extreme_type="low",
            percentile_rank=2.0,
            high_threshold=0.0003,
            low_threshold=-0.0002,
            severity=0.9,
            message="Extremely LOW funding rate",
        )
        assert detection.is_extreme
        assert detection.extreme_type == "low"


# ---------------------------------------------------------------------------
# FundingRateResult Tests
# ---------------------------------------------------------------------------


class TestFundingRateResult:
    """Tests for FundingRateResult dataclass."""

    def test_creation(self, normal_rates):
        """Test creating a funding rate result."""
        analyzer = FundingRateAnalyzer(symbol="BTCUSDT")
        result = analyzer.analyze(normal_rates)
        assert result.symbol == "BTCUSDT"
        assert result.current_rate != 0.0
        assert len(result.trends) == 3
        assert "8h" in result.trends
        assert "24h" in result.trends
        assert "7d" in result.trends

    def test_funding_direction_positive(self):
        """Test positive funding direction."""
        result = FundingRateResult(
            symbol="BTCUSDT",
            current_rate=0.0005,
            trends={},
            extreme_detection=ExtremeFundingDetection(
                is_extreme=False,
                extreme_type="none",
                percentile_rank=50.0,
                high_threshold=0.0,
                low_threshold=0.0,
                severity=0.0,
                message="",
            ),
            signal_adjustment=0.0,
        )
        assert result.funding_direction == FundingDirection.POSITIVE

    def test_funding_direction_negative(self):
        """Test negative funding direction."""
        result = FundingRateResult(
            symbol="BTCUSDT",
            current_rate=-0.0005,
            trends={},
            extreme_detection=ExtremeFundingDetection(
                is_extreme=False,
                extreme_type="none",
                percentile_rank=50.0,
                high_threshold=0.0,
                low_threshold=0.0,
                severity=0.0,
                message="",
            ),
            signal_adjustment=0.0,
        )
        assert result.funding_direction == FundingDirection.NEGATIVE

    def test_funding_direction_neutral(self):
        """Test neutral funding direction."""
        result = FundingRateResult(
            symbol="BTCUSDT",
            current_rate=0.00001,
            trends={},
            extreme_detection=ExtremeFundingDetection(
                is_extreme=False,
                extreme_type="none",
                percentile_rank=50.0,
                high_threshold=0.0,
                low_threshold=0.0,
                severity=0.0,
                message="",
            ),
            signal_adjustment=0.0,
        )
        assert result.funding_direction == FundingDirection.NEUTRAL

    def test_to_confluence_factor(self, normal_rates):
        """Test conversion to confluence factor."""
        analyzer = FundingRateAnalyzer(symbol="BTCUSDT")
        result = analyzer.analyze(normal_rates)
        factor = result.to_confluence_factor()
        assert factor["indicator"] == "funding_rate"
        assert factor["timeframe"] == "8h"
        assert "direction" in factor
        assert "strength" in factor
        assert "confidence" in factor
        assert "raw_value" in factor
        assert factor["raw_value"] == result.current_rate


# ---------------------------------------------------------------------------
# FundingRateAnalyzer Initialization Tests
# ---------------------------------------------------------------------------


class TestFundingRateAnalyzerInit:
    """Tests for FundingRateAnalyzer initialization."""

    def test_default_initialization(self):
        """Test default parameter values."""
        analyzer = FundingRateAnalyzer(symbol="ETHUSDT")
        assert analyzer.symbol == "ETHUSDT"
        assert analyzer.windows == {"8h": 8, "24h": 24, "7d": 168}
        assert analyzer.high_percentile == 95.0
        assert analyzer.low_percentile == 5.0
        assert analyzer.api_base_url == BYBIT_V5_PUBLIC

    def test_custom_windows(self):
        """Test custom window configuration."""
        custom_windows = {"1h": 1, "12h": 12, "30d": 720}
        analyzer = FundingRateAnalyzer(symbol="BTCUSDT", windows=custom_windows)
        assert analyzer.windows == custom_windows

    def test_custom_percentiles(self):
        """Test custom percentile thresholds."""
        analyzer = FundingRateAnalyzer(
            symbol="BTCUSDT",
            high_percentile=90.0,
            low_percentile=10.0,
        )
        assert analyzer.high_percentile == 90.0
        assert analyzer.low_percentile == 10.0

    def test_custom_http_client(self):
        """Test custom HTTP client injection."""
        mock_client = MagicMock(spec=httpx.Client)
        analyzer = FundingRateAnalyzer(symbol="BTCUSDT", http_client=mock_client)
        assert analyzer._http_client is mock_client

    def test_custom_api_url(self):
        """Test custom API base URL."""
        analyzer = FundingRateAnalyzer(
            symbol="BTCUSDT",
            api_base_url="https://api-testnet.bybit.com",
        )
        assert analyzer.api_base_url == "https://api-testnet.bybit.com"

    def test_name_includes_symbol(self):
        """Test that default name includes symbol."""
        analyzer = FundingRateAnalyzer(symbol="ETHUSDT")
        assert "ETHUSDT" in analyzer.name
        assert "FundingRateAnalyzer" in analyzer.name


# ---------------------------------------------------------------------------
# BaseIndicator Interface Tests
# ---------------------------------------------------------------------------


class TestBaseIndicatorInterface:
    """Tests for BaseIndicator interface compliance."""

    def test_description(self, analyzer):
        """Test description property."""
        desc = analyzer.description
        assert "BTCUSDT" in desc
        assert "funding" in desc.lower()

    def test_parameters(self, analyzer):
        """Test parameters property."""
        params = analyzer.parameters
        assert params["symbol"] == "BTCUSDT"
        assert "windows" in params
        assert "high_percentile" in params
        assert "low_percentile" in params

    def test_compute_returns_result(self, analyzer, sample_rates):
        """Test compute returns FundingRateResult."""
        with patch.object(analyzer, "fetch_funding_rates", return_value=sample_rates):
            result = analyzer.compute([])
            assert isinstance(result, FundingRateResult)
            assert result.symbol == "BTCUSDT"

    def test_validate_with_symbol(self, analyzer):
        """Test validation with valid symbol."""
        assert analyzer.validate([]) is True

    def test_validate_empty_symbol(self):
        """Test validation with empty symbol."""
        analyzer = FundingRateAnalyzer(symbol="")
        assert analyzer.validate([]) is False

    def test_get_metadata(self, analyzer):
        """Test metadata retrieval."""
        metadata = analyzer.get_metadata()
        assert metadata["name"] == analyzer.name
        assert "description" in metadata
        assert metadata["type"] == "fundamental"
        assert metadata["parameters"]["symbol"] == "BTCUSDT"


# ---------------------------------------------------------------------------
# Bybit API Integration Tests
# ---------------------------------------------------------------------------


class TestBybitAPIIntegration:
    """Tests for Bybit API integration."""

    def test_fetch_funding_rates_success(
        self, analyzer_with_client, mock_bybit_response
    ):
        """Test successful funding rate fetch."""
        mock_response = MagicMock()
        mock_response.json.return_value = mock_bybit_response
        mock_response.raise_for_status = MagicMock()
        analyzer_with_client._http_client.get.return_value = mock_response

        rates = analyzer_with_client.fetch_funding_rates()

        assert len(rates) == 10
        assert all(isinstance(r, FundingRatePoint) for r in rates)
        assert rates[0].symbol == "BTCUSDT"
        # Newest first
        assert rates[0].timestamp > rates[-1].timestamp
        analyzer_with_client._http_client.get.assert_called_once()

    def test_fetch_funding_rates_api_error(
        self, analyzer_with_client, mock_bybit_error_response
    ):
        """Test API error handling."""
        mock_response = MagicMock()
        mock_response.json.return_value = mock_bybit_error_response
        mock_response.raise_for_status = MagicMock()
        analyzer_with_client._http_client.get.return_value = mock_response

        with pytest.raises(ValueError, match="Bybit API error"):
            analyzer_with_client.fetch_funding_rates()

    def test_fetch_funding_rates_empty_list(self):
        """Test handling of empty result list."""
        analyzer = FundingRateAnalyzer(symbol="BTCUSDT")
        empty_response = {
            "retCode": 0,
            "retMsg": "OK",
            "result": {"category": "linear", "list": []},
        }
        mock_response = MagicMock()
        mock_response.json.return_value = empty_response
        mock_response.raise_for_status = MagicMock()

        with patch.object(analyzer, "_http_client") as mock_client:
            mock_client.get.return_value = mock_response
            mock_client.__class__ = httpx.Client  # isinstance check
            rates = analyzer.fetch_funding_rates()
            assert rates == []

    def test_fetch_funding_rates_http_error(self, analyzer_with_client):
        """Test HTTP error handling."""
        analyzer_with_client._http_client.get.side_effect = httpx.HTTPStatusError(
            "500 Server Error",
            request=MagicMock(),
            response=MagicMock(status_code=500),
        )
        with pytest.raises(httpx.HTTPStatusError):
            analyzer_with_client.fetch_funding_rates()

    def test_fetch_funding_rates_request_error(self, analyzer_with_client):
        """Test network request error handling."""
        analyzer_with_client._http_client.get.side_effect = httpx.RequestError(
            "Connection error"
        )
        with pytest.raises(httpx.RequestError):
            analyzer_with_client.fetch_funding_rates()

    def test_fetch_funding_rates_creates_own_client(self, mock_bybit_response):
        """Test that analyzer creates its own client when none provided."""
        analyzer = FundingRateAnalyzer(symbol="BTCUSDT")
        mock_response = MagicMock()
        mock_response.json.return_value = mock_bybit_response
        mock_response.raise_for_status = MagicMock()

        with patch(
            "market_analysis.fundamentals.funding_rate.httpx.Client"
        ) as mock_client_cls:
            mock_instance = MagicMock()
            mock_instance.get.return_value = mock_response
            mock_client_cls.return_value = mock_instance

            analyzer.fetch_funding_rates()

            mock_client_cls.assert_called_once_with(timeout=10.0)
            mock_instance.close.assert_called_once()

    def test_fetch_funding_rates_limit_param(
        self, analyzer_with_client, mock_bybit_response
    ):
        """Test limit parameter is passed correctly."""
        mock_response = MagicMock()
        mock_response.json.return_value = mock_bybit_response
        mock_response.raise_for_status = MagicMock()
        analyzer_with_client._http_client.get.return_value = mock_response

        analyzer_with_client.fetch_funding_rates(limit=50)

        call_args = analyzer_with_client._http_client.get.call_args
        assert call_args[1]["params"]["limit"] == 50

    def test_fetch_funding_rates_limit_capped(
        self, analyzer_with_client, mock_bybit_response
    ):
        """Test limit is capped at 200."""
        mock_response = MagicMock()
        mock_response.json.return_value = mock_bybit_response
        mock_response.raise_for_status = MagicMock()
        analyzer_with_client._http_client.get.return_value = mock_response

        analyzer_with_client.fetch_funding_rates(limit=500)

        call_args = analyzer_with_client._http_client.get.call_args
        assert call_args[1]["params"]["limit"] == 200

    @pytest.mark.asyncio
    async def test_fetch_funding_rates_async_success(self, mock_bybit_response):
        """Test async funding rate fetch."""
        mock_client = MagicMock(spec=httpx.AsyncClient)
        mock_response = MagicMock()
        mock_response.json.return_value = mock_bybit_response
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        analyzer = FundingRateAnalyzer(symbol="BTCUSDT", http_client=mock_client)
        rates = await analyzer.fetch_funding_rates_async()

        assert len(rates) == 10
        mock_client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_funding_rates_async_creates_client(self, mock_bybit_response):
        """Test async creates own client when none provided."""
        analyzer = FundingRateAnalyzer(symbol="BTCUSDT")

        mock_response = MagicMock()
        mock_response.json.return_value = mock_bybit_response
        mock_response.raise_for_status = MagicMock()

        with patch(
            "market_analysis.fundamentals.funding_rate.httpx.AsyncClient"
        ) as mock_client_cls:
            # When no client provided, code uses: client = httpx.AsyncClient(timeout=10.0)
            # So mock_client_cls() return value IS the client used directly
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.aclose = AsyncMock()
            mock_client_cls.return_value = mock_client

            await analyzer.fetch_funding_rates_async()

            mock_client_cls.assert_called_once_with(timeout=10.0)
            mock_client.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_funding_rates_async_with_sync_client_error(self):
        """Test error when sync client passed to async method."""
        sync_client = MagicMock()
        sync_client.__class__ = httpx.Client
        analyzer = FundingRateAnalyzer(symbol="BTCUSDT", http_client=sync_client)

        # Should not raise - it should create its own async client
        with patch(
            "market_analysis.fundamentals.funding_rate.httpx.AsyncClient"
        ) as mock_client_cls:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "retCode": 0,
                "retMsg": "OK",
                "result": {"list": []},
            }
            mock_response.raise_for_status = MagicMock()
            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_response
            mock_cm = AsyncMock()
            mock_cm.__aenter__.return_value = mock_instance
            mock_cm.__aexit__.return_value = False
            mock_client_cls.return_value = mock_cm

            result = await analyzer.fetch_funding_rates_async()
            assert isinstance(result, list)

    def test_async_client_to_sync_raises(self):
        """Test that async client raises in sync fetch."""
        async_client = MagicMock(spec=httpx.AsyncClient)
        analyzer = FundingRateAnalyzer(symbol="BTCUSDT", http_client=async_client)

        with pytest.raises(TypeError, match="fetch_funding_rates_async"):
            analyzer.fetch_funding_rates()


# ---------------------------------------------------------------------------
# Trend Calculation Tests
# ---------------------------------------------------------------------------


class TestTrendCalculation:
    """Tests for funding rate trend calculation."""

    def test_8h_trend(self, analyzer, sample_rates):
        """Test 8-hour trend calculation."""
        result = analyzer.analyze(sample_rates)
        trend = result.trends["8h"]
        assert trend.window_label == "8h"
        assert trend.window_hours == 8
        assert trend.sample_count >= 1
        assert trend.mean is not None
        assert trend.std >= 0.0
        assert trend.min <= trend.max

    def test_24h_trend(self, analyzer, sample_rates):
        """Test 24-hour trend calculation."""
        result = analyzer.analyze(sample_rates)
        trend = result.trends["24h"]
        assert trend.window_label == "24h"
        assert trend.window_hours == 24
        assert trend.sample_count >= 1

    def test_7d_trend(self, analyzer, sample_rates):
        """Test 7-day trend calculation."""
        result = analyzer.analyze(sample_rates)
        trend = result.trends["7d"]
        assert trend.window_label == "7d"
        assert trend.window_hours == 168
        # 24 rates at 8h intervals = 184h span > 168h, so some fall outside
        assert trend.sample_count >= 20
        assert trend.sample_count <= 24

    def test_trend_slope_increasing(self, analyzer):
        """Test trend slope for increasing funding rates."""
        now = datetime.now(UTC)
        rates = []
        # 4 points at 8h intervals = 24h span (fits within 24h window)
        for i in range(4):
            ts = int((now - timedelta(hours=8 * (3 - i))).timestamp() * 1000)
            # Increasing rates: older = lower, newer = higher
            rates.append(
                FundingRatePoint(
                    symbol="BTCUSDT",
                    funding_rate=0.0001 * (i + 1),
                    timestamp=ts,
                )
            )

        result = analyzer.analyze(rates)
        # Slope should be positive (rates increasing over time)
        assert result.trends["24h"].trend_slope > 0

    def test_trend_slope_decreasing(self, analyzer):
        """Test trend slope for decreasing funding rates."""
        now = datetime.now(UTC)
        rates = []
        # 4 points at 8h intervals = 24h span (fits within 24h window)
        for i in range(4):
            ts = int((now - timedelta(hours=8 * (3 - i))).timestamp() * 1000)
            # Decreasing rates: older = higher, newer = lower
            rates.append(
                FundingRatePoint(
                    symbol="BTCUSDT",
                    funding_rate=0.001 * (4 - i),
                    timestamp=ts,
                )
            )

        result = analyzer.analyze(rates)
        # Slope should be negative
        assert result.trends["24h"].trend_slope < 0

    def test_trend_flat(self, analyzer):
        """Test trend slope for flat funding rates."""
        now = datetime.now(UTC)
        rates = []
        for i in range(10):
            ts = int((now - timedelta(hours=8 * i)).timestamp() * 1000)
            rates.append(
                FundingRatePoint(
                    symbol="BTCUSDT",
                    funding_rate=0.0001,
                    timestamp=ts,
                )
            )

        result = analyzer.analyze(rates)
        # Slope should be ~0 for flat rates
        assert abs(result.trends["24h"].trend_slope) < 1e-10

    def test_trend_with_single_point(self, analyzer):
        """Test trend with only one data point."""
        now = datetime.now(UTC)
        rates = [
            FundingRatePoint(
                symbol="BTCUSDT",
                funding_rate=0.0001,
                timestamp=int(now.timestamp() * 1000),
            )
        ]

        result = analyzer.analyze(rates)
        trend = result.trends["8h"]
        assert trend.sample_count == 1
        assert trend.mean == 0.0001
        assert trend.trend_slope == 0.0
        assert trend.std == 0.0

    def test_trend_with_custom_windows(self):
        """Test trend with custom window configuration."""
        custom_windows = {"1h": 1, "6h": 6}
        analyzer = FundingRateAnalyzer(symbol="BTCUSDT", windows=custom_windows)

        now = datetime.now(UTC)
        rates = [
            FundingRatePoint(
                symbol="BTCUSDT",
                funding_rate=0.0001,
                timestamp=int((now - timedelta(hours=8 * i)).timestamp() * 1000),
            )
            for i in range(5)
        ]

        result = analyzer.analyze(rates)
        assert "1h" in result.trends
        assert "6h" in result.trends
        assert "8h" not in result.trends


# ---------------------------------------------------------------------------
# Extreme Funding Detection Tests
# ---------------------------------------------------------------------------


class TestExtremeFundingDetectionLogic:
    """Tests for extreme funding detection logic."""

    def test_no_extreme_normal_rates(self, analyzer, normal_rates):
        """Test no extreme detected with normal rates."""
        result = analyzer.analyze(normal_rates)
        # Normal rates should not trigger extreme
        assert not result.extreme_detection.is_extreme
        assert result.extreme_detection.extreme_type == "none"

    def test_extreme_high_detected(self, analyzer, extreme_high_rates):
        """Test extreme high funding detected."""
        result = analyzer.analyze(extreme_high_rates)
        assert result.extreme_detection.is_extreme
        assert result.extreme_detection.extreme_type == "high"
        assert result.extreme_detection.severity > 0.0
        assert "HIGH" in result.extreme_detection.message

    def test_extreme_low_detected(self, analyzer, extreme_low_rates):
        """Test extreme low funding detected."""
        result = analyzer.analyze(extreme_low_rates)
        assert result.extreme_detection.is_extreme
        assert result.extreme_detection.extreme_type == "low"
        assert result.extreme_detection.severity > 0.0
        assert "LOW" in result.extreme_detection.message

    def test_percentile_rank(self, analyzer, normal_rates):
        """Test percentile rank calculation."""
        result = analyzer.analyze(normal_rates)
        rank = result.extreme_detection.percentile_rank
        assert 0 <= rank <= 100

    def test_thresholds_are_set(self, analyzer, normal_rates):
        """Test that thresholds are properly calculated."""
        result = analyzer.analyze(normal_rates)
        detection = result.extreme_detection
        assert detection.high_threshold > 0
        assert detection.low_threshold <= detection.high_threshold

    def test_insufficient_data(self, analyzer):
        """Test extreme detection with insufficient data."""
        now = datetime.now(UTC)
        rates = [
            FundingRatePoint(
                symbol="BTCUSDT",
                funding_rate=0.0001,
                timestamp=int(now.timestamp() * 1000),
            )
        ]
        result = analyzer.analyze(rates)
        assert not result.extreme_detection.is_extreme
        assert "Insufficient" in result.extreme_detection.message

    def test_custom_percentile_thresholds(self):
        """Test custom percentile thresholds change detection."""
        analyzer = FundingRateAnalyzer(
            symbol="BTCUSDT",
            high_percentile=50.0,  # Very aggressive threshold
            low_percentile=50.0,
        )

        now = datetime.now(UTC)
        rates = []
        for i in range(20):
            ts = int((now - timedelta(hours=8 * i)).timestamp() * 1000)
            rate = 0.0001 + (i - 10) * 0.00001
            rates.append(
                FundingRatePoint(symbol="BTCUSDT", funding_rate=rate, timestamp=ts)
            )

        result = analyzer.analyze(rates)
        # With 50th percentile thresholds, should detect extremes more often
        assert result.extreme_detection.high_threshold is not None
        assert result.extreme_detection.low_threshold is not None


# ---------------------------------------------------------------------------
# Signal Adjustment Tests
# ---------------------------------------------------------------------------


class TestSignalAdjustment:
    """Tests for signal confidence adjustment."""

    def test_no_adjustment_normal(self, analyzer, normal_rates):
        """Test no adjustment for normal funding."""
        result = analyzer.analyze(normal_rates)
        assert result.signal_adjustment == 0.0

    def test_extreme_high_adjustment(self, analyzer, extreme_high_rates):
        """Test adjustment for extreme high funding."""
        result = analyzer.analyze(extreme_high_rates)
        assert result.signal_adjustment > 0.0

    def test_extreme_low_adjustment(self, analyzer, extreme_low_rates):
        """Test adjustment for extreme low funding."""
        result = analyzer.analyze(extreme_low_rates)
        assert result.signal_adjustment > 0.0

    def test_adjustment_capped(self, analyzer):
        """Test that adjustment doesn't exceed max."""
        # Create very extreme rates
        now = datetime.now(UTC)
        rates = []
        for i in range(30):
            ts = int((now - timedelta(hours=8 * i)).timestamp() * 1000)
            rate = 0.01 if i < 2 else 0.0001  # 1% vs 0.01%
            rates.append(
                FundingRatePoint(symbol="BTCUSDT", funding_rate=rate, timestamp=ts)
            )

        result = analyzer.analyze(rates)
        assert result.signal_adjustment <= analyzer.EXTREME_ADJUSTMENT

    def test_moderate_severity_adjustment(self):
        """Test moderate severity gives moderate adjustment."""
        analyzer = FundingRateAnalyzer(symbol="BTCUSDT")
        detection = ExtremeFundingDetection(
            is_extreme=True,
            extreme_type="high",
            percentile_rank=96.0,
            high_threshold=0.0003,
            low_threshold=-0.0001,
            severity=0.6,
            message="Moderate extreme",
        )
        adjustment = analyzer._calculate_signal_adjustment(detection)
        assert adjustment == analyzer.MODERATE_ADJUSTMENT

    def test_low_severity_adjustment(self):
        """Test low severity gives small adjustment."""
        analyzer = FundingRateAnalyzer(symbol="BTCUSDT")
        detection = ExtremeFundingDetection(
            is_extreme=True,
            extreme_type="high",
            percentile_rank=93.0,
            high_threshold=0.0003,
            low_threshold=-0.0001,
            severity=0.3,
            message="Mild extreme",
        )
        adjustment = analyzer._calculate_signal_adjustment(detection)
        expected = analyzer.MODERATE_ADJUSTMENT * 0.5
        assert adjustment == expected

    def test_high_severity_adjustment(self):
        """Test high severity gives maximum adjustment."""
        analyzer = FundingRateAnalyzer(symbol="BTCUSDT")
        detection = ExtremeFundingDetection(
            is_extreme=True,
            extreme_type="high",
            percentile_rank=99.0,
            high_threshold=0.0003,
            low_threshold=-0.0001,
            severity=0.9,
            message="Very extreme",
        )
        adjustment = analyzer._calculate_signal_adjustment(detection)
        assert adjustment == analyzer.EXTREME_ADJUSTMENT

    def test_non_extreme_no_adjustment(self):
        """Test non-extreme gives zero adjustment."""
        analyzer = FundingRateAnalyzer(symbol="BTCUSDT")
        detection = ExtremeFundingDetection(
            is_extreme=False,
            extreme_type="none",
            percentile_rank=50.0,
            high_threshold=0.0003,
            low_threshold=-0.0001,
            severity=0.0,
            message="Normal",
        )
        adjustment = analyzer._calculate_signal_adjustment(detection)
        assert adjustment == 0.0


# ---------------------------------------------------------------------------
# Signal Conversion Tests
# ---------------------------------------------------------------------------


class TestSignalConversion:
    """Tests for signal conversion from funding rate results."""

    def test_to_signal_positive_funding(self, analyzer, extreme_high_rates):
        """Test signal direction for positive (high) funding."""
        result = analyzer.analyze(extreme_high_rates)
        signal = analyzer.to_signal(result)
        # High funding = crowded long = SELL signal
        assert signal.direction.value == "sell"
        assert signal.confidence > 0.0

    def test_to_signal_negative_funding(self, analyzer, extreme_low_rates):
        """Test signal direction for negative (low) funding."""
        result = analyzer.analyze(extreme_low_rates)
        signal = analyzer.to_signal(result)
        # Low funding = crowded short = BUY signal
        assert signal.direction.value == "buy"
        assert signal.confidence > 0.0

    def test_to_signal_no_data(self, analyzer):
        """Test signal with no data."""
        result = analyzer._empty_result()
        signal = analyzer.to_signal(result)
        assert signal.direction.value == "hold"
        assert signal.confidence == 0.0

    def test_to_signal_metadata(self, analyzer, extreme_high_rates):
        """Test signal includes funding metadata."""
        result = analyzer.analyze(extreme_high_rates)
        signal = analyzer.to_signal(result)
        assert signal.metadata["symbol"] == "BTCUSDT"
        assert "funding_rate" in signal.metadata
        assert "is_extreme" in signal.metadata
        assert "severity" in signal.metadata
        assert "signal_adjustment" in signal.metadata


# ---------------------------------------------------------------------------
# Analyze Method Tests
# ---------------------------------------------------------------------------


class TestAnalyzeMethod:
    """Tests for the main analyze() method."""

    def test_analyze_with_provided_rates(self, analyzer, sample_rates):
        """Test analyze with pre-fetched rates (no API call)."""
        result = analyzer.analyze(sample_rates)
        assert result.symbol == "BTCUSDT"
        assert result.current_rate != 0.0
        assert len(result.trends) == 3
        assert result.metadata["data_points"] == len(sample_rates)

    def test_analyze_empty_rates(self, analyzer):
        """Test analyze with empty rate list."""
        result = analyzer.analyze([])
        assert result.current_rate == 0.0
        assert result.metadata.get("error") == "no_data"

    def test_analyze_none_rates_fetches(self, analyzer, sample_rates):
        """Test analyze with None triggers API fetch."""
        with patch.object(
            analyzer, "fetch_funding_rates", return_value=sample_rates
        ) as mock_fetch:
            result = analyzer.analyze(None)
            mock_fetch.assert_called_once()
            assert result.current_rate != 0.0

    def test_analyze_updates_cache(self, analyzer, sample_rates):
        """Test that analyze updates the rate cache."""
        assert len(analyzer._rate_cache) == 0
        analyzer.analyze(sample_rates)
        assert len(analyzer._rate_cache) == len(sample_rates)

    def test_analyze_metadata_timestamps(self, analyzer, sample_rates):
        """Test metadata includes timestamp range."""
        result = analyzer.analyze(sample_rates)
        assert result.metadata["oldest_timestamp"] is not None
        assert result.metadata["newest_timestamp"] is not None
        assert result.metadata["newest_timestamp"] > result.metadata["oldest_timestamp"]


# ---------------------------------------------------------------------------
# Static Utility Tests
# ---------------------------------------------------------------------------


class TestStaticUtilities:
    """Tests for static utility methods."""

    def test_calculate_percentile(self):
        """Test percentile calculation (nearest-rank method)."""
        values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        # Nearest-rank: idx = int(n * percentile / 100)
        # 50th: idx=5 -> 6.0, 90th: idx=9 -> 10.0, 10th: idx=1 -> 2.0
        assert FundingRateAnalyzer.calculate_percentile(values, 50) == 6.0
        assert FundingRateAnalyzer.calculate_percentile(values, 90) == 10.0
        assert FundingRateAnalyzer.calculate_percentile(values, 10) == 2.0

    def test_calculate_percentile_single_value(self):
        """Test percentile with single value."""
        assert FundingRateAnalyzer.calculate_percentile([5.0], 50) == 5.0

    def test_calculate_percentile_empty_raises(self):
        """Test percentile raises on empty list."""
        with pytest.raises(ValueError, match="empty list"):
            FundingRateAnalyzer.calculate_percentile([], 50)

    def test_calculate_percentile_unsorted(self):
        """Test percentile works with unsorted input."""
        values = [5.0, 1.0, 3.0, 2.0, 4.0]
        result = FundingRateAnalyzer.calculate_percentile(values, 50)
        assert result == 3.0


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_all_same_funding_rates(self, analyzer):
        """Test analysis with all identical funding rates."""
        now = datetime.now(UTC)
        rates = [
            FundingRatePoint(
                symbol="BTCUSDT",
                funding_rate=0.0001,
                timestamp=int((now - timedelta(hours=8 * i)).timestamp() * 1000),
            )
            for i in range(20)
        ]
        result = analyzer.analyze(rates)
        assert result.current_rate == 0.0001
        for trend in result.trends.values():
            assert trend.std == 0.0
            assert trend.mean == 0.0001

    def test_very_large_funding_rate(self, analyzer):
        """Test handling of very large funding rates."""
        now = datetime.now(UTC)
        rates = [
            FundingRatePoint(
                symbol="BTCUSDT",
                funding_rate=0.01,  # 1% per 8h = very extreme
                timestamp=int(now.timestamp() * 1000),
            )
        ]
        result = analyzer.analyze(rates)
        # Should not crash
        assert result.current_rate == 0.01

    def test_very_small_funding_rate(self, analyzer):
        """Test handling of very small (near-zero) funding rates."""
        now = datetime.now(UTC)
        rates = [
            FundingRatePoint(
                symbol="BTCUSDT",
                funding_rate=0.0000001,
                timestamp=int(now.timestamp() * 1000),
            )
        ]
        result = analyzer.analyze(rates)
        assert result.funding_direction == FundingDirection.NEUTRAL

    def test_zero_funding_rate(self, analyzer):
        """Test zero funding rate."""
        now = datetime.now(UTC)
        rates = [
            FundingRatePoint(
                symbol="BTCUSDT",
                funding_rate=0.0,
                timestamp=int(now.timestamp() * 1000),
            )
        ]
        result = analyzer.analyze(rates)
        assert result.funding_direction == FundingDirection.NEUTRAL

    def test_window_larger_than_data(self, analyzer):
        """Test when window is larger than available data span."""
        now = datetime.now(UTC)
        rates = [
            FundingRatePoint(
                symbol="BTCUSDT",
                funding_rate=0.0001,
                timestamp=int((now - timedelta(hours=8 * i)).timestamp() * 1000),
            )
            for i in range(3)  # Only 24h of data
        ]

        result = analyzer.analyze(rates)
        # 7d trend should use all available data
        trend_7d = result.trends["7d"]
        assert trend_7d.sample_count == 3

    def test_odd_number_of_rates_median(self, analyzer):
        """Test median calculation with odd number of rates in window."""
        now = datetime.now(UTC)
        rates = [
            FundingRatePoint(
                symbol="BTCUSDT",
                funding_rate=float(i) * 0.0001,
                timestamp=int((now - timedelta(hours=4 * i)).timestamp() * 1000),
            )
            for i in range(5)  # 5 points at 4h intervals = 16h (fits in 24h)
        ]

        result = analyzer.analyze(rates)
        # With 5 values sorted: 0.0, 0.0001, 0.0002, 0.0003, 0.0004
        # Median should be 0.0002
        assert result.trends["24h"].median == pytest.approx(0.0002)

    def test_even_number_of_rates_median(self, analyzer):
        """Test median calculation with even number of rates."""
        now = datetime.now(UTC)
        rates = [
            FundingRatePoint(
                symbol="BTCUSDT",
                funding_rate=float(i) * 0.0001,
                timestamp=int((now - timedelta(hours=8 * i)).timestamp() * 1000),
            )
            for i in range(4)
        ]

        result = analyzer.analyze(rates)
        # With 4 values sorted: 0.0, 0.0001, 0.0002, 0.0003
        # Median should be (0.0001 + 0.0002) / 2 = 0.00015
        assert result.trends["24h"].median == pytest.approx(0.00015)


# ---------------------------------------------------------------------------
# ConfluenceScorer Integration Tests
# ---------------------------------------------------------------------------


class TestConfluenceIntegration:
    """Tests for ConfluenceScorer integration."""

    def test_confluence_factor_structure(self, analyzer, normal_rates):
        """Test confluence factor has expected structure."""
        result = analyzer.analyze(normal_rates)
        factor = result.to_confluence_factor()

        # Verify all expected keys
        expected_keys = {
            "type",
            "indicator",
            "timeframe",
            "direction",
            "strength",
            "confidence",
            "weight",
            "weighted_score",
            "raw_value",
            "funding_rate_pct",
            "is_extreme",
            "extreme_type",
        }
        assert set(factor.keys()) == expected_keys

    def test_confluence_factor_extreme(self, analyzer, extreme_high_rates):
        """Test confluence factor reflects extreme funding."""
        result = analyzer.analyze(extreme_high_rates)
        factor = result.to_confluence_factor()

        assert factor["is_extreme"] is True
        assert factor["extreme_type"] == "high"
        assert factor["strength"] > 0

    def test_confluence_factor_normal(self, analyzer, normal_rates):
        """Test confluence factor for normal funding."""
        result = analyzer.analyze(normal_rates)
        factor = result.to_confluence_factor()

        assert factor["is_extreme"] is False
        assert factor["extreme_type"] == "none"

    def test_confluence_factor_values_in_range(self, analyzer, sample_rates):
        """Test confluence factor values are in valid ranges."""
        result = analyzer.analyze(sample_rates)
        factor = result.to_confluence_factor()

        assert 0.0 <= factor["strength"] <= 1.0
        assert 0.0 <= factor["confidence"] <= 1.0
        assert 0.0 <= factor["weighted_score"] <= 1.0

    def test_confluence_factor_direction_mapping(self, analyzer):
        """Test funding direction maps correctly to confluence factor."""
        # Positive funding
        now = datetime.now(UTC)
        pos_rates = [
            FundingRatePoint(
                symbol="BTCUSDT",
                funding_rate=0.001,
                timestamp=int(now.timestamp() * 1000),
            )
        ]
        result = analyzer.analyze(pos_rates)
        factor = result.to_confluence_factor()
        assert factor["direction"] == "positive"

        # Negative funding
        neg_rates = [
            FundingRatePoint(
                symbol="BTCUSDT",
                funding_rate=-0.001,
                timestamp=int(now.timestamp() * 1000),
            )
        ]
        result = analyzer.analyze(neg_rates)
        factor = result.to_confluence_factor()
        assert factor["direction"] == "negative"


# ---------------------------------------------------------------------------
# Module Import Tests
# ---------------------------------------------------------------------------


class TestModuleImports:
    """Tests for module import structure."""

    def test_import_from_package(self):
        """Test importing from fundamentals package."""
        from market_analysis.fundamentals import (
            ExtremeFundingDetection,
            FundingDirection,
            FundingRateAnalyzer,
            FundingRatePoint,
            FundingRateResult,
            FundingTrend,
        )

        assert FundingRateAnalyzer is not None
        assert FundingRatePoint is not None
        assert FundingTrend is not None
        assert ExtremeFundingDetection is not None
        assert FundingRateResult is not None
        assert FundingDirection is not None

    def test_import_direction_enum(self):
        """Test FundingDirection enum values."""
        assert FundingDirection.POSITIVE.value == "positive"
        assert FundingDirection.NEGATIVE.value == "negative"
        assert FundingDirection.NEUTRAL.value == "neutral"
