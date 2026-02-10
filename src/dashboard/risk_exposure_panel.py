"""Risk exposure dashboard panel for Streamlit.

Provides real-time risk metrics visualization including:
- Total portfolio exposure
- Margin utilization gauge
- Portfolio heat map by token and direction
- Risk alerts and thresholds
- On-demand risk report generation
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import streamlit as st

if TYPE_CHECKING:
    from portfolio.state_management.models import PortfolioState
    from portfolio.state_management.risk_calculator import (
        RiskCalculator,
        RiskMetrics,
    )


def render_risk_exposure_panel(
    portfolio_state: PortfolioState | None,
    refresh_interval: float = 5.0,
) -> dict[str, Any] | None:
    """Render the risk exposure dashboard panel.

    Displays real-time risk metrics including exposure, margin utilization,
    heat maps, and alerts. Updates automatically based on refresh interval.

    Args:
        portfolio_state: Current portfolio state (None if unavailable)
        refresh_interval: Seconds between automatic refreshes (default 5.0)

    Returns:
        Risk report dictionary if generated, None otherwise
    """
    from portfolio.state_management.risk_calculator import RiskCalculator

    st.header("Risk Exposure Dashboard")

    # Check if portfolio state is available
    if portfolio_state is None:
        st.warning("Portfolio state unavailable. Risk metrics cannot be displayed.")
        return None

    # Calculate risk metrics
    calculator = RiskCalculator()
    risk_metrics = calculator.calculate_risk_metrics(portfolio_state)

    # Auto-refresh mechanism
    if refresh_interval > 0:
        time.sleep(0.1)  # Small delay to prevent excessive CPU usage
        st.empty()  # Placeholder for refresh

    # Render summary metrics
    _render_summary_metrics(risk_metrics)

    # Render margin utilization gauge
    _render_margin_gauge(risk_metrics)

    # Render exposure heat map
    _render_heat_map(risk_metrics)

    # Render alerts panel
    _render_alerts(risk_metrics)

    # Render exposure breakdown table
    _render_exposure_table(risk_metrics)

    # Risk report generation button
    report = _render_report_section(calculator, risk_metrics)

    # Display last update time
    st.caption(
        f"Last updated: {risk_metrics.timestamp.strftime('%Y-%m-%d %H:%M:%S')} UTC"
    )

    return report


def _render_summary_metrics(risk_metrics: RiskMetrics) -> None:
    """Render summary risk metrics in columns.

    Args:
        risk_metrics: Calculated risk metrics
    """
    st.subheader("Portfolio Risk Summary")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            label="Total Exposure",
            value=f"${risk_metrics.total_exposure:,.2f}",
            help="Sum of all position notional values",
        )

    with col2:
        st.metric(
            label="Net Exposure",
            value=f"${risk_metrics.net_exposure:,.2f}",
            help="Long exposure minus short exposure",
        )

    with col3:
        st.metric(
            label="Concentration Risk",
            value=f"{risk_metrics.concentration_risk:.1f}%",
            help="Maximum single-token exposure as % of equity",
        )

    with col4:
        alert_count = len(risk_metrics.alerts)
        st.metric(
            label="Active Alerts",
            value=str(alert_count),
            help="Number of risk threshold breaches",
        )


def _render_margin_gauge(risk_metrics: RiskMetrics) -> None:
    """Render margin utilization gauge.

    Args:
        risk_metrics: Calculated risk metrics
    """
    st.subheader("Margin Utilization")

    margin = risk_metrics.margin_utilization
    util_pct = margin.utilization_pct

    # Determine color based on risk level
    if util_pct >= 90:
        color = "#ff4b4b"  # Red - Critical
        status = "CRITICAL"
    elif util_pct >= 75:
        color = "#ff9f43"  # Orange - High
        status = "HIGH"
    elif util_pct >= 50:
        color = "#feca57"  # Yellow - Medium
        status = "MEDIUM"
    else:
        color = "#1dd1a1"  # Green - Low
        status = "LOW"

    # Create columns for gauge and details
    col1, col2 = st.columns([2, 1])

    with col1:
        # Progress bar as gauge
        st.progress(min(util_pct / 100, 1.0), text=f"{util_pct:.1f}% utilized")

        # Color indicator
        st.markdown(
            f"""
            <div style="
                background-color: {color};
                padding: 10px;
                border-radius: 5px;
                text-align: center;
                color: white;
                font-weight: bold;
            ">
                Risk Level: {status}
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col2:
        st.metric("Margin Used", f"${margin.margin_used:,.2f}")
        st.metric("Available Equity", f"${margin.available_equity:,.2f}")
        st.metric("Total Equity", f"${margin.total_equity:,.2f}")


def _render_heat_map(risk_metrics: RiskMetrics) -> None:
    """Render portfolio heat map by token and direction.

    Args:
        risk_metrics: Calculated risk metrics
    """
    st.subheader("Exposure Heat Map")

    if not risk_metrics.token_exposures:
        st.info("No active positions to display in heat map.")
        return

    # Create heat map data
    from portfolio.state_management.risk_calculator import RiskCalculator

    calculator = RiskCalculator()
    heat_map = calculator.get_heat_map_data(risk_metrics)

    # Display as bar chart
    import pandas as pd

    df = pd.DataFrame(
        {
            "Token": heat_map["tokens"],
            "Long": heat_map["long_exposure"],
            "Short": heat_map["short_exposure"],
            "Net": heat_map["net_exposure"],
        }
    )

    # Stacked bar chart for long/short exposure
    st.bar_chart(
        df.set_index("Token")[["Long", "Short"]],
        use_container_width=True,
    )

    # Net exposure as separate chart
    st.caption("Net Exposure by Token")
    net_df = pd.DataFrame(
        {
            "Token": heat_map["tokens"],
            "Net Exposure": heat_map["net_exposure"],
        }
    ).set_index("Token")

    st.bar_chart(net_df, use_container_width=True, color="#00adb5")


def _render_alerts(risk_metrics: RiskMetrics) -> None:
    """Render risk alerts panel.

    Args:
        risk_metrics: Calculated risk metrics
    """
    st.subheader("Risk Alerts")

    if not risk_metrics.alerts:
        st.success("✅ No risk alerts - all thresholds within limits")
        return

    for alert in risk_metrics.alerts:
        # Determine alert styling based on severity
        if alert.severity.value == "critical":
            emoji = "🚨"
            color = "#ff4b4b"
        elif alert.severity.value == "high":
            emoji = "⚠️"
            color = "#ff9f43"
        elif alert.severity.value == "medium":
            emoji = "⚠️"
            color = "#feca57"
        else:
            emoji = "ℹ️"
            color = "#74b9ff"

        st.markdown(
            f"""
            <div style="
                background-color: {color}20;
                border-left: 4px solid {color};
                padding: 10px;
                margin: 5px 0;
                border-radius: 3px;
            ">
                {emoji} <strong>{alert.alert_type.upper()}</strong>
                ({alert.severity.value})<br>
                {alert.message}<br>
                <small>Threshold: {alert.threshold:.1f}% |
                Current: {alert.current_value:.1f}%</small>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_exposure_table(risk_metrics: RiskMetrics) -> None:
    """Render detailed exposure breakdown table.

    Args:
        risk_metrics: Calculated risk metrics
    """
    st.subheader("Exposure Breakdown by Token")

    if not risk_metrics.token_exposures:
        st.info("No positions to display.")
        return

    import pandas as pd

    # Create DataFrame from token exposures
    data = []
    for te in risk_metrics.token_exposures:
        total_equity = risk_metrics.margin_utilization.total_equity
        exposure_pct = (
            (te.gross_exposure / total_equity * 100) if total_equity > 0 else 0
        )

        data.append(
            {
                "Token": te.token,
                "Long ($)": f"{te.long_notional:,.2f}",
                "Short ($)": f"{te.short_notional:,.2f}",
                "Net ($)": f"{te.net_exposure:,.2f}",
                "Gross ($)": f"{te.gross_exposure:,.2f}",
                "% of Equity": f"{exposure_pct:.1f}%",
                "Positions": te.position_count,
                "Bias": te.directional_bias.capitalize(),
            }
        )

    df = pd.DataFrame(data)
    st.dataframe(df, use_container_width=True, hide_index=True)

    # Show totals
    st.divider()
    total_col1, total_col2, total_col3 = st.columns(3)

    with total_col1:
        st.metric("Total Long", f"${risk_metrics.long_exposure:,.2f}")

    with total_col2:
        st.metric("Total Short", f"${risk_metrics.short_exposure:,.2f}")

    with total_col3:
        st.metric("Gross Exposure", f"${risk_metrics.gross_exposure:,.2f}")


def _render_report_section(
    calculator: RiskCalculator,
    risk_metrics: RiskMetrics,
) -> dict[str, Any] | None:
    """Render risk report generation section.

    Args:
        calculator: Risk calculator instance
        risk_metrics: Calculated risk metrics

    Returns:
        Risk report dictionary if generated, None otherwise
    """
    st.subheader("Risk Report")

    col1, col2 = st.columns([1, 3])

    with col1:
        generate_report = st.button("📊 Generate Risk Report", type="primary")

    report = None
    if generate_report:
        report = calculator.generate_risk_report(risk_metrics)

        with col2:
            st.success("Risk report generated successfully!")

        # Display report summary
        with st.expander("View Report Summary"):
            st.json(report["summary"])

        with st.expander("View Margin Details"):
            st.json(report["margin"])

        with st.expander("View Alerts"):
            st.json(report["alerts"])

    return report


def render_risk_metrics_mini(
    portfolio_state: PortfolioState | None,
) -> None:
    """Render mini risk metrics for compact display.

    Suitable for sidebar or header display with minimal space.

    Args:
        portfolio_state: Current portfolio state
    """
    from portfolio.state_management.risk_calculator import RiskCalculator

    if portfolio_state is None:
        st.warning("No portfolio data")
        return

    calculator = RiskCalculator()
    risk_metrics = calculator.calculate_risk_metrics(portfolio_state)

    # Compact metrics
    col1, col2 = st.columns(2)

    with col1:
        util_pct = risk_metrics.margin_utilization.utilization_pct
        color = (
            "🔴"
            if util_pct >= 90
            else "🟠" if util_pct >= 75 else "🟡" if util_pct >= 50 else "🟢"
        )
        st.metric(
            "Margin",
            f"{color} {util_pct:.1f}%",
            help="Margin utilization percentage",
        )

    with col2:
        st.metric(
            "Exposure",
            f"${risk_metrics.total_exposure:,.0f}",
            help="Total portfolio exposure",
        )

    # Alert indicator
    alert_count = len(risk_metrics.alerts)
    if alert_count > 0:
        st.warning(f"⚠️ {alert_count} risk alert{'s' if alert_count > 1 else ''}")
    else:
        st.success("✅ Risk OK")
