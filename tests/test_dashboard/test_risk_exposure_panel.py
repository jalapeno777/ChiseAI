"""Tests for risk exposure dashboard panel."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from portfolio.state_management.models import (
    PortfolioState,
    Position,
    PositionDirection,
    PositionStatus,
)
from portfolio.state_management.risk_calculator import (
    ExposureAlert,
    MarginUtilization,
    RiskCalculator,
    RiskLevel,
    RiskMetrics,
    TokenExposure,
)
from dashboard.risk_exposure_panel import (
    render_risk_exposure_panel,
    render_risk_metrics_mini,
    _render_summary_metrics,
    _render_margin_gauge,
    _render_heat_map,
    _render_alerts,
    _render_exposure_table,
    _render_report_section,
)


class TestRenderRiskExposurePanel:
    """Tests for render_risk_exposure_panel function."""

    @patch("streamlit.header")
    @patch("streamlit.warning")
    def test_null_portfolio_state(self, mock_warning, mock_header) -> None:
        """Test handling of null portfolio state."""
        result = render_risk_exposure_panel(None)

        assert result is None
        mock_warning.assert_called_once()
        assert "unavailable" in mock_warning.call_args[0][0].lower()

    @patch("streamlit.header")
    @patch("streamlit.warning")
    @patch("streamlit.subheader")
    @patch("streamlit.metric")
    @patch("streamlit.columns")
    @patch("streamlit.progress")
    @patch("streamlit.markdown")
    @patch("streamlit.caption")
    @patch("streamlit.button")
    @patch("streamlit.empty")
    @patch("streamlit.bar_chart")
    @patch("streamlit.dataframe")
    @patch("streamlit.divider")
    @patch("streamlit.info")
    def test_render_with_valid_state(
        self,
        mock_info,
        mock_dataframe,
        mock_divider,
        mock_bar_chart,
        mock_empty,
        mock_button,
        mock_caption,
        mock_markdown,
        mock_progress,
        mock_columns,
        mock_metric,
        mock_subheader,
        mock_warning,
        mock_header,
    ) -> None:
        """Test rendering with valid portfolio state."""
        # Setup mock columns - return dynamic number of columns based on input
        mock_col = MagicMock()

        def columns_side_effect(*args, **kwargs):
            # Handle st.columns(n) or st.columns([...])
            if args:
                if isinstance(args[0], int):
                    return [mock_col] * args[0]
                elif isinstance(args[0], list):
                    return [mock_col] * len(args[0])
            # Default to 4 columns
            return [mock_col, mock_col, mock_col, mock_col]

        mock_columns.side_effect = columns_side_effect

        # Create test portfolio state (empty to trigger early returns in sub-functions)
        state = PortfolioState(portfolio_id="test-portfolio")
        state.update_balance("USDT", free=100000.0)
        # No positions - this triggers early returns in heat_map and exposure_table

        result = render_risk_exposure_panel(state, refresh_interval=0)

        # The mock button returns True by default (MagicMock), so report is generated
        # In real usage, button returns False until clicked
        mock_header.assert_called()
        mock_subheader.assert_called()
        # Verify the function ran successfully (result may be report or None)


class TestRenderSummaryMetrics:
    """Tests for _render_summary_metrics function."""

    @patch("streamlit.subheader")
    @patch("streamlit.metric")
    @patch("streamlit.columns")
    def test_summary_metrics_display(
        self, mock_columns, mock_metric, mock_subheader
    ) -> None:
        """Test summary metrics are displayed correctly."""
        mock_col = MagicMock()
        mock_columns.return_value = [mock_col, mock_col, mock_col, mock_col]

        margin = MarginUtilization(
            margin_used=50000.0,
            total_equity=100000.0,
            available_equity=50000.0,
        )

        metrics = RiskMetrics(
            timestamp=MagicMock(),
            portfolio_id="test",
            total_exposure=100000.0,
            net_exposure=80000.0,
            gross_exposure=100000.0,
            margin_utilization=margin,
            token_exposures=[],
            long_exposure=90000.0,
            short_exposure=10000.0,
            concentration_risk=75.0,
            alerts=[],
        )

        _render_summary_metrics(metrics)

        mock_subheader.assert_called_once_with("Portfolio Risk Summary")
        # Should call metric 4 times (Total Exposure, Net Exposure, Concentration, Alerts)
        assert mock_metric.call_count == 4


class TestRenderMarginGauge:
    """Tests for _render_margin_gauge function."""

    @patch("streamlit.subheader")
    @patch("streamlit.progress")
    @patch("streamlit.markdown")
    @patch("streamlit.metric")
    @patch("streamlit.columns")
    def test_margin_gauge_low_risk(
        self, mock_columns, mock_metric, mock_markdown, mock_progress, mock_subheader
    ) -> None:
        """Test margin gauge with low risk level."""
        mock_col = MagicMock()
        mock_columns.return_value = [mock_col, mock_col]

        margin = MarginUtilization(
            margin_used=25000.0,
            total_equity=100000.0,
            available_equity=75000.0,
        )

        metrics = RiskMetrics(
            timestamp=MagicMock(),
            portfolio_id="test",
            total_exposure=50000.0,
            net_exposure=40000.0,
            gross_exposure=50000.0,
            margin_utilization=margin,
            token_exposures=[],
            long_exposure=50000.0,
            short_exposure=0.0,
            concentration_risk=50.0,
            alerts=[],
        )

        _render_margin_gauge(metrics)

        mock_subheader.assert_called_once_with("Margin Utilization")
        mock_progress.assert_called_once()
        # Progress should show 25%
        assert mock_progress.call_args[1]["text"] == "25.0% utilized"

    @patch("streamlit.subheader")
    @patch("streamlit.progress")
    @patch("streamlit.markdown")
    @patch("streamlit.metric")
    @patch("streamlit.columns")
    def test_margin_gauge_critical_risk(
        self, mock_columns, mock_metric, mock_markdown, mock_progress, mock_subheader
    ) -> None:
        """Test margin gauge with critical risk level."""
        mock_col = MagicMock()
        mock_columns.return_value = [mock_col, mock_col]

        margin = MarginUtilization(
            margin_used=95000.0,
            total_equity=100000.0,
            available_equity=5000.0,
        )

        metrics = RiskMetrics(
            timestamp=MagicMock(),
            portfolio_id="test",
            total_exposure=100000.0,
            net_exposure=100000.0,
            gross_exposure=100000.0,
            margin_utilization=margin,
            token_exposures=[],
            long_exposure=100000.0,
            short_exposure=0.0,
            concentration_risk=100.0,
            alerts=[],
        )

        _render_margin_gauge(metrics)

        mock_progress.assert_called_once()
        # Progress should show 95%
        assert mock_progress.call_args[1]["text"] == "95.0% utilized"


class TestRenderHeatMap:
    """Tests for _render_heat_map function."""

    @patch("streamlit.subheader")
    @patch("streamlit.info")
    def test_empty_heat_map(self, mock_info, mock_subheader) -> None:
        """Test heat map with no positions."""
        margin = MarginUtilization(
            margin_used=0.0,
            total_equity=100000.0,
            available_equity=100000.0,
        )

        metrics = RiskMetrics(
            timestamp=MagicMock(),
            portfolio_id="test",
            total_exposure=0.0,
            net_exposure=0.0,
            gross_exposure=0.0,
            margin_utilization=margin,
            token_exposures=[],
            long_exposure=0.0,
            short_exposure=0.0,
            concentration_risk=0.0,
            alerts=[],
        )

        _render_heat_map(metrics)

        mock_subheader.assert_called_once_with("Exposure Heat Map")
        mock_info.assert_called_once()

    @patch("streamlit.subheader")
    @patch("streamlit.bar_chart")
    @patch("streamlit.caption")
    def test_heat_map_with_positions(
        self, mock_caption, mock_bar_chart, mock_subheader
    ) -> None:
        """Test heat map with positions."""
        token_exposure = TokenExposure(
            token="BTC",
            long_notional=100000.0,
            short_notional=0.0,
            position_count=1,
        )

        margin = MarginUtilization(
            margin_used=50000.0,
            total_equity=100000.0,
            available_equity=50000.0,
        )

        metrics = RiskMetrics(
            timestamp=MagicMock(),
            portfolio_id="test",
            total_exposure=100000.0,
            net_exposure=100000.0,
            gross_exposure=100000.0,
            margin_utilization=margin,
            token_exposures=[token_exposure],
            long_exposure=100000.0,
            short_exposure=0.0,
            concentration_risk=100.0,
            alerts=[],
        )

        _render_heat_map(metrics)

        mock_subheader.assert_called_once_with("Exposure Heat Map")
        # Should call bar_chart twice (long/short and net)
        assert mock_bar_chart.call_count == 2


class TestRenderAlerts:
    """Tests for _render_alerts function."""

    @patch("streamlit.subheader")
    @patch("streamlit.success")
    def test_no_alerts(self, mock_success, mock_subheader) -> None:
        """Test alerts panel with no alerts."""
        margin = MarginUtilization(
            margin_used=25000.0,
            total_equity=100000.0,
            available_equity=75000.0,
        )

        metrics = RiskMetrics(
            timestamp=MagicMock(),
            portfolio_id="test",
            total_exposure=50000.0,
            net_exposure=40000.0,
            gross_exposure=50000.0,
            margin_utilization=margin,
            token_exposures=[],
            long_exposure=50000.0,
            short_exposure=0.0,
            concentration_risk=50.0,
            alerts=[],
        )

        _render_alerts(metrics)

        mock_subheader.assert_called_once_with("Risk Alerts")
        mock_success.assert_called_once()
        assert "No risk alerts" in mock_success.call_args[0][0]

    @patch("streamlit.subheader")
    @patch("streamlit.markdown")
    def test_critical_alert(self, mock_markdown, mock_subheader) -> None:
        """Test alerts panel with critical alert."""
        alert = ExposureAlert(
            alert_type="margin",
            severity=RiskLevel.CRITICAL,
            message="Margin utilization critical",
            threshold=80.0,
            current_value=95.0,
        )

        margin = MarginUtilization(
            margin_used=95000.0,
            total_equity=100000.0,
            available_equity=5000.0,
        )

        metrics = RiskMetrics(
            timestamp=MagicMock(),
            portfolio_id="test",
            total_exposure=100000.0,
            net_exposure=100000.0,
            gross_exposure=100000.0,
            margin_utilization=margin,
            token_exposures=[],
            long_exposure=100000.0,
            short_exposure=0.0,
            concentration_risk=100.0,
            alerts=[alert],
        )

        _render_alerts(metrics)

        mock_subheader.assert_called_once_with("Risk Alerts")
        mock_markdown.assert_called_once()
        # Should contain critical emoji
        assert "🚨" in mock_markdown.call_args[0][0]


class TestRenderExposureTable:
    """Tests for _render_exposure_table function."""

    @patch("streamlit.subheader")
    @patch("streamlit.info")
    def test_empty_exposure_table(self, mock_info, mock_subheader) -> None:
        """Test exposure table with no positions."""
        margin = MarginUtilization(
            margin_used=0.0,
            total_equity=100000.0,
            available_equity=100000.0,
        )

        metrics = RiskMetrics(
            timestamp=MagicMock(),
            portfolio_id="test",
            total_exposure=0.0,
            net_exposure=0.0,
            gross_exposure=0.0,
            margin_utilization=margin,
            token_exposures=[],
            long_exposure=0.0,
            short_exposure=0.0,
            concentration_risk=0.0,
            alerts=[],
        )

        _render_exposure_table(metrics)

        mock_subheader.assert_called_once_with("Exposure Breakdown by Token")
        mock_info.assert_called_once()

    @patch("streamlit.subheader")
    @patch("streamlit.dataframe")
    @patch("streamlit.divider")
    @patch("streamlit.metric")
    @patch("streamlit.columns")
    def test_exposure_table_with_positions(
        self, mock_columns, mock_metric, mock_divider, mock_dataframe, mock_subheader
    ) -> None:
        """Test exposure table with positions."""
        mock_col = MagicMock()
        mock_columns.return_value = [mock_col, mock_col, mock_col]

        token_exposure = TokenExposure(
            token="BTC",
            long_notional=100000.0,
            short_notional=0.0,
            position_count=2,
        )

        margin = MarginUtilization(
            margin_used=50000.0,
            total_equity=100000.0,
            available_equity=50000.0,
        )

        metrics = RiskMetrics(
            timestamp=MagicMock(),
            portfolio_id="test",
            total_exposure=100000.0,
            net_exposure=100000.0,
            gross_exposure=100000.0,
            margin_utilization=margin,
            token_exposures=[token_exposure],
            long_exposure=100000.0,
            short_exposure=0.0,
            concentration_risk=100.0,
            alerts=[],
        )

        _render_exposure_table(metrics)

        mock_subheader.assert_called_once_with("Exposure Breakdown by Token")
        mock_dataframe.assert_called_once()
        mock_divider.assert_called_once()
        # Should display 3 metrics (Total Long, Total Short, Gross Exposure)
        assert mock_metric.call_count == 3


class TestRenderReportSection:
    """Tests for _render_report_section function."""

    @patch("streamlit.subheader")
    @patch("streamlit.button")
    @patch("streamlit.columns")
    def test_report_button_not_clicked(
        self, mock_columns, mock_button, mock_subheader
    ) -> None:
        """Test report section when button is not clicked."""
        mock_col = MagicMock()
        mock_columns.return_value = [mock_col, mock_col]
        mock_button.return_value = False

        calculator = RiskCalculator()
        margin = MarginUtilization(
            margin_used=50000.0,
            total_equity=100000.0,
            available_equity=50000.0,
        )

        metrics = RiskMetrics(
            timestamp=MagicMock(),
            portfolio_id="test",
            total_exposure=100000.0,
            net_exposure=100000.0,
            gross_exposure=100000.0,
            margin_utilization=margin,
            token_exposures=[],
            long_exposure=100000.0,
            short_exposure=0.0,
            concentration_risk=100.0,
            alerts=[],
        )

        result = _render_report_section(calculator, metrics)

        assert result is None
        mock_subheader.assert_called_once_with("Risk Report")
        mock_button.assert_called_once()

    @patch("streamlit.subheader")
    @patch("streamlit.button")
    @patch("streamlit.success")
    @patch("streamlit.expander")
    @patch("streamlit.json")
    @patch("streamlit.columns")
    def test_report_button_clicked(
        self,
        mock_columns,
        mock_json,
        mock_expander,
        mock_success,
        mock_button,
        mock_subheader,
    ) -> None:
        """Test report section when button is clicked."""
        mock_col = MagicMock()
        mock_columns.return_value = [mock_col, mock_col]
        mock_button.return_value = True

        calculator = RiskCalculator()
        margin = MarginUtilization(
            margin_used=50000.0,
            total_equity=100000.0,
            available_equity=50000.0,
        )

        metrics = RiskMetrics(
            timestamp=MagicMock(),
            portfolio_id="test",
            total_exposure=100000.0,
            net_exposure=100000.0,
            gross_exposure=100000.0,
            margin_utilization=margin,
            token_exposures=[],
            long_exposure=100000.0,
            short_exposure=0.0,
            concentration_risk=100.0,
            alerts=[],
        )

        result = _render_report_section(calculator, metrics)

        assert result is not None
        assert result["report_type"] == "risk_exposure"
        mock_success.assert_called_once()
        # Should create 3 expanders (summary, margin, alerts)
        assert mock_expander.call_count == 3


class TestRenderRiskMetricsMini:
    """Tests for render_risk_metrics_mini function."""

    @patch("streamlit.warning")
    def test_null_state_mini(self, mock_warning) -> None:
        """Test mini display with null state."""
        render_risk_metrics_mini(None)

        mock_warning.assert_called_once_with("No portfolio data")

    @patch("streamlit.columns")
    @patch("streamlit.metric")
    @patch("streamlit.success")
    def test_mini_display_no_alerts(
        self, mock_success, mock_metric, mock_columns
    ) -> None:
        """Test mini display with no alerts."""
        mock_col = MagicMock()
        mock_columns.return_value = [mock_col, mock_col]

        state = PortfolioState(portfolio_id="test-portfolio")
        state.update_balance("USDT", free=100000.0)

        render_risk_metrics_mini(state)

        # Should call metric twice (Margin and Exposure)
        assert mock_metric.call_count == 2
        mock_success.assert_called_once_with("✅ Risk OK")

    @patch("streamlit.columns")
    @patch("streamlit.metric")
    @patch("streamlit.warning")
    def test_mini_display_with_alerts(
        self, mock_warning, mock_metric, mock_columns
    ) -> None:
        """Test mini display with alerts."""
        mock_col = MagicMock()
        mock_columns.return_value = [mock_col, mock_col]

        state = PortfolioState(portfolio_id="test-portfolio")
        state.update_balance("USDT", free=100000.0)
        # Add large position to trigger alert
        state.add_position(
            Position(
                position_id="pos-1",
                token="BTC",
                direction=PositionDirection.LONG,
                entry_price=50000.0,
                quantity=2.0,
                current_price=51000.0,
            )
        )

        render_risk_metrics_mini(state)

        # Should call metric twice
        assert mock_metric.call_count == 2
        # Should show warning for alerts
        mock_warning.assert_called_once()
        assert "alert" in mock_warning.call_args[0][0].lower()
