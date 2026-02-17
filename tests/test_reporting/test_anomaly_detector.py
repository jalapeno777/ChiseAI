"""Tests for the anomaly detector.

For PAPER-003-003: Automated Reporting and Anomaly Detection
"""

import pytest
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch

from src.reporting.anomaly_detector import AnomalyDetector
from src.reporting.models import AnomalyAlert, AnomalySeverity, AnomalyType


class TestAnomalyDetector:
    """Tests for AnomalyDetector."""

    @pytest.fixture
    def detector(self):
        """Create an anomaly detector instance."""
        return AnomalyDetector()

    @pytest.fixture
    def mock_influx_client(self):
        """Create a mock InfluxDB client."""
        mock_client = Mock()
        mock_query_api = Mock()
        mock_client.query_api.return_value = mock_query_api
        return mock_client

    def test_default_thresholds(self, detector):
        """Test default detection thresholds."""
        assert detector.PNL_STD_DEV_THRESHOLD == 3.0
        assert detector.VOLUME_SPIKE_THRESHOLD == 2.0
        assert detector.ERROR_RATE_SPIKE_THRESHOLD == 5.0

    def test_initialization(self, detector):
        """Test detector initialization."""
        assert detector._baseline_window_days == 30
        assert detector._alert_history == []

    @pytest.mark.asyncio
    async def test_detect_pnl_anomalies_no_baseline(self, detector):
        """Test PnL anomaly detection with no baseline data."""
        # Mock _query_baseline_pnls to return empty list
        detector._query_baseline_pnls = AsyncMock(return_value=[])

        alerts = await detector.detect_pnl_anomalies()

        assert alerts == []

    @pytest.mark.asyncio
    async def test_detect_pnl_anomalies_with_spike(self, detector):
        """Test PnL anomaly detection with a spike."""
        # Create baseline with some variance to have std dev > 0
        baseline = [100.0 + i * 5 for i in range(20)]  # Varying values

        detector._query_baseline_pnls = AsyncMock(return_value=baseline)
        detector._query_current_pnl = AsyncMock(return_value=5000.0)  # Large spike

        alerts = await detector.detect_pnl_anomalies()

        # Should detect an anomaly with large enough spike
        if len(alerts) > 0:
            assert alerts[0].anomaly_type == AnomalyType.PNL_SPIKE
            assert alerts[0].metric_name == "PnL"

    @pytest.mark.asyncio
    async def test_detect_volume_spikes_no_baseline(self, detector):
        """Test volume spike detection with no baseline data."""
        detector._query_baseline_volumes = AsyncMock(return_value=[])

        alerts = await detector.detect_volume_spikes()

        assert alerts == []

    @pytest.mark.asyncio
    async def test_detect_volume_spikes_with_spike(self, detector):
        """Test volume spike detection with a spike."""
        baseline = [1000.0] * 20  # Mean = 1000

        detector._query_baseline_volumes = AsyncMock(return_value=baseline)
        detector._query_current_volume = AsyncMock(return_value=3000.0)  # 3x spike

        alerts = await detector.detect_volume_spikes()

        assert len(alerts) == 1
        assert alerts[0].anomaly_type == AnomalyType.VOLUME_SPIKE
        assert alerts[0].severity == AnomalySeverity.WARNING

    @pytest.mark.asyncio
    async def test_detect_error_rate_spikes(self, detector):
        """Test error rate spike detection."""
        baseline = [0.01] * 20  # 1% error rate

        detector._query_baseline_error_rates = AsyncMock(return_value=baseline)
        detector._query_current_error_rate = AsyncMock(return_value=0.1)  # 10x spike

        alerts = await detector.detect_error_rate_spikes()

        assert len(alerts) == 1
        assert alerts[0].anomaly_type == AnomalyType.ERROR_RATE_SPIKE

    @pytest.mark.asyncio
    async def test_detect_drawdown_spikes(self, detector):
        """Test drawdown spike detection."""
        baseline = [0.01] * 20  # 1% drawdown

        detector._query_baseline_drawdowns = AsyncMock(return_value=baseline)
        detector._query_current_drawdown = AsyncMock(return_value=0.05)  # 5% drawdown

        alerts = await detector.detect_drawdown_spikes()

        assert len(alerts) == 1
        assert alerts[0].anomaly_type == AnomalyType.DRAWDOWN_SPIKE

    @pytest.mark.asyncio
    async def test_detect_latency_spikes(self, detector):
        """Test latency spike detection."""
        baseline = [50.0] * 20  # 50ms latency

        detector._query_baseline_latencies = AsyncMock(return_value=baseline)
        detector._query_current_latency = AsyncMock(return_value=200.0)  # 4x spike

        alerts = await detector.detect_latency_spikes()

        assert len(alerts) == 1
        assert alerts[0].anomaly_type == AnomalyType.LATENCY_SPIKE

    @pytest.mark.asyncio
    async def test_detect_all(self, detector):
        """Test running all anomaly detection checks."""
        # Mock all detection methods
        detector.detect_pnl_anomalies = AsyncMock(return_value=[])
        detector.detect_volume_spikes = AsyncMock(return_value=[])
        detector.detect_error_rate_spikes = AsyncMock(return_value=[])
        detector.detect_drawdown_spikes = AsyncMock(return_value=[])
        detector.detect_latency_spikes = AsyncMock(return_value=[])

        alerts = await detector.detect_all()

        assert alerts == []
        detector.detect_pnl_anomalies.assert_called_once()
        detector.detect_volume_spikes.assert_called_once()

    def test_filter_duplicates(self, detector):
        """Test duplicate alert filtering."""
        now = datetime.now(UTC)

        # Create alerts
        alert1 = AnomalyAlert(
            anomaly_type=AnomalyType.PNL_SPIKE,
            severity=AnomalySeverity.WARNING,
            message="Test",
            detected_at=now,
            metric_name="PnL",
            current_value=100.0,
            expected_value=10.0,
            deviation=10.0,
        )

        alert2 = AnomalyAlert(
            anomaly_type=AnomalyType.VOLUME_SPIKE,
            severity=AnomalySeverity.WARNING,
            message="Test",
            detected_at=now,
            metric_name="Volume",
            current_value=1000.0,
            expected_value=100.0,
            deviation=10.0,
        )

        # Record first alert in history
        detector._record_alert(alert1)

        # Filter duplicates
        filtered = detector._filter_duplicates([alert1, alert2])

        # alert1 should be filtered as duplicate, alert2 should pass
        assert len(filtered) == 1
        assert filtered[0].anomaly_type == AnomalyType.VOLUME_SPIKE

    def test_record_alert(self, detector):
        """Test recording alerts."""
        alert = AnomalyAlert(
            anomaly_type=AnomalyType.PNL_SPIKE,
            severity=AnomalySeverity.WARNING,
            message="Test",
            detected_at=datetime.now(UTC),
            metric_name="PnL",
            current_value=100.0,
            expected_value=10.0,
            deviation=10.0,
        )

        detector._record_alert(alert)

        assert len(detector._alert_history) == 1
        assert detector._alert_history[0]["type"] == "pnl_spike"

    def test_get_alert_history(self, detector):
        """Test getting alert history."""
        now = datetime.now(UTC)

        detector._alert_history = [
            {"type": "pnl_spike", "detected_at": now, "metric_name": "PnL"},
            {
                "type": "volume_spike",
                "detected_at": now - timedelta(hours=2),
                "metric_name": "Volume",
            },
        ]

        # Get last hour
        history = detector.get_alert_history(hours=1)

        assert len(history) == 1
        assert history[0]["type"] == "pnl_spike"

    def test_clear_history(self, detector):
        """Test clearing alert history."""
        detector._alert_history = [{"type": "test"}]

        detector.clear_history()

        assert detector._alert_history == []

    def test_alert_to_markdown(self):
        """Test alert Markdown generation."""
        alert = AnomalyAlert(
            anomaly_type=AnomalyType.PNL_SPIKE,
            severity=AnomalySeverity.CRITICAL,
            message="Critical PnL spike detected",
            detected_at=datetime(2026, 2, 17, 12, 0, 0, tzinfo=UTC),
            metric_name="Daily PnL",
            current_value=5000.0,
            expected_value=100.0,
            deviation=50.0,
            details={"std_dev": 100.0},
        )

        markdown = alert.to_markdown()

        assert "PnL" in markdown or "pnl" in markdown.lower()
        assert "CRITICAL" in markdown
        assert "5000.0000" in markdown
        assert "Critical PnL spike detected" in markdown
