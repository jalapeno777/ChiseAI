"""Risk exposure calculation for portfolio management.

Provides risk metrics calculation including total exposure, margin utilization,
portfolio heat maps, and configurable alert thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from portfolio.state_management.models import PortfolioState, Position


class RiskLevel(Enum):
    """Risk level classification."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    def __str__(self) -> str:
        """Return string representation."""
        return self.value


@dataclass
class TokenExposure:
    """Exposure breakdown for a single token.

    Attributes:
        token: Token symbol (e.g., "BTC", "ETH")
        long_notional: Total long position notional value
        short_notional: Total short position notional value
        net_exposure: Net exposure (long - short)
        gross_exposure: Gross exposure (long + short)
        position_count: Number of positions for this token
        margin_used: Margin allocated to this token's positions
    """

    token: str
    long_notional: float = 0.0
    short_notional: float = 0.0
    position_count: int = 0
    margin_used: float = 0.0

    @property
    def net_exposure(self) -> float:
        """Calculate net exposure (long - short)."""
        return self.long_notional - self.short_notional

    @property
    def gross_exposure(self) -> float:
        """Calculate gross exposure (long + short)."""
        return self.long_notional + self.short_notional

    @property
    def directional_bias(self) -> str:
        """Return directional bias based on net exposure."""
        if self.net_exposure > 0:
            return "long"
        elif self.net_exposure < 0:
            return "short"
        return "neutral"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "token": self.token,
            "long_notional": round(self.long_notional, 8),
            "short_notional": round(self.short_notional, 8),
            "net_exposure": round(self.net_exposure, 8),
            "gross_exposure": round(self.gross_exposure, 8),
            "position_count": self.position_count,
            "margin_used": round(self.margin_used, 8),
            "directional_bias": self.directional_bias,
        }


@dataclass
class MarginUtilization:
    """Margin utilization metrics.

    Attributes:
        margin_used: Total margin used across all positions
        total_equity: Total portfolio equity
        available_equity: Available equity for new positions
        utilization_pct: Margin utilization percentage
        risk_level: Risk level based on utilization
    """

    margin_used: float
    total_equity: float
    available_equity: float

    @property
    def utilization_pct(self) -> float:
        """Calculate margin utilization percentage."""
        if self.total_equity <= 0:
            return 0.0
        return (self.margin_used / self.total_equity) * 100

    @property
    def risk_level(self) -> RiskLevel:
        """Determine risk level based on utilization."""
        util = self.utilization_pct
        if util >= 90:
            return RiskLevel.CRITICAL
        elif util >= 75:
            return RiskLevel.HIGH
        elif util >= 50:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "margin_used": round(self.margin_used, 8),
            "total_equity": round(self.total_equity, 8),
            "available_equity": round(self.available_equity, 8),
            "utilization_pct": round(self.utilization_pct, 2),
            "risk_level": self.risk_level.value,
        }


@dataclass
class ExposureAlert:
    """Exposure alert triggered when thresholds are breached.

    Attributes:
        alert_type: Type of alert (exposure, margin, concentration)
        severity: Alert severity level
        message: Human-readable alert message
        threshold: Threshold that was breached
        current_value: Current value that triggered the alert
        timestamp: When the alert was triggered
    """

    alert_type: str
    severity: RiskLevel
    message: str
    threshold: float
    current_value: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "alert_type": self.alert_type,
            "severity": self.severity.value,
            "message": self.message,
            "threshold": self.threshold,
            "current_value": round(self.current_value, 4),
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class RiskMetrics:
    """Complete risk metrics for a portfolio.

    Attributes:
        timestamp: When metrics were calculated
        portfolio_id: Portfolio identifier
        total_exposure: Total portfolio exposure (sum of notionals)
        net_exposure: Net exposure across all positions
        gross_exposure: Gross exposure (long + short)
        margin_utilization: Margin utilization metrics
        token_exposures: Exposure breakdown by token
        long_exposure: Total long exposure
        short_exposure: Total short exposure
        concentration_risk: Concentration risk score (0-100)
        alerts: List of active risk alerts
    """

    timestamp: datetime
    portfolio_id: str
    total_exposure: float
    net_exposure: float
    gross_exposure: float
    margin_utilization: MarginUtilization
    token_exposures: list[TokenExposure]
    long_exposure: float
    short_exposure: float
    concentration_risk: float
    alerts: list[ExposureAlert] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for dashboard payload."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "portfolio_id": self.portfolio_id,
            "total_exposure": round(self.total_exposure, 8),
            "net_exposure": round(self.net_exposure, 8),
            "gross_exposure": round(self.gross_exposure, 8),
            "long_exposure": round(self.long_exposure, 8),
            "short_exposure": round(self.short_exposure, 8),
            "margin_utilization": self.margin_utilization.to_dict(),
            "token_exposures": [te.to_dict() for te in self.token_exposures],
            "concentration_risk": round(self.concentration_risk, 2),
            "alerts": [alert.to_dict() for alert in self.alerts],
            "alert_count": len(self.alerts),
        }


@dataclass
class RiskThresholds:
    """Configurable risk thresholds for alerts.

    Attributes:
        max_exposure_pct: Maximum exposure as percentage of equity (default 80%)
        max_margin_utilization_pct: Maximum margin utilization (default 80%)
        max_concentration_pct: Maximum concentration in single token (default 50%)
        max_position_count: Maximum number of open positions (default 20)
    """

    max_exposure_pct: float = 80.0
    max_margin_utilization_pct: float = 80.0
    max_concentration_pct: float = 50.0
    max_position_count: int = 20

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "max_exposure_pct": self.max_exposure_pct,
            "max_margin_utilization_pct": self.max_margin_utilization_pct,
            "max_concentration_pct": self.max_concentration_pct,
            "max_position_count": self.max_position_count,
        }


class RiskCalculator:
    """Calculator for portfolio risk metrics.

    Calculates comprehensive risk metrics including:
    - Total portfolio exposure (sum of position notionals)
    - Margin utilization percentage
    - Token-level exposure breakdown
    - Concentration risk
    - Configurable threshold alerts
    """

    def __init__(self, thresholds: RiskThresholds | None = None):
        """Initialize risk calculator.

        Args:
            thresholds: Risk thresholds for alerts (uses defaults if None)
        """
        self.thresholds = thresholds or RiskThresholds()

    def calculate_risk_metrics(
        self,
        portfolio_state: PortfolioState,
    ) -> RiskMetrics:
        """Calculate comprehensive risk metrics for a portfolio.

        Args:
            portfolio_state: Current portfolio state

        Returns:
            RiskMetrics with all calculated risk indicators
        """
        from portfolio.state_management.models import PositionStatus

        timestamp = datetime.now(UTC)
        portfolio_id = portfolio_state.portfolio_id

        # Get open and pending positions only
        active_positions = [
            pos
            for pos in portfolio_state.positions.values()
            if pos.status in (PositionStatus.OPEN, PositionStatus.PENDING)
        ]

        # Calculate token-level exposures
        token_exposures = self._calculate_token_exposures(active_positions)

        # Calculate aggregate exposures
        long_exposure = sum(te.long_notional for te in token_exposures)
        short_exposure = sum(te.short_notional for te in token_exposures)
        gross_exposure = long_exposure + short_exposure
        net_exposure = long_exposure - short_exposure

        # Total exposure is the gross exposure
        total_exposure = gross_exposure

        # Calculate margin utilization
        margin_util = MarginUtilization(
            margin_used=portfolio_state.margin_used,
            total_equity=portfolio_state.total_equity,
            available_equity=portfolio_state.available_equity,
        )

        # Calculate concentration risk
        concentration_risk = self._calculate_concentration_risk(
            token_exposures, portfolio_state.total_equity
        )

        # Check thresholds and generate alerts
        alerts = self._check_thresholds(
            total_exposure=total_exposure,
            net_exposure=net_exposure,
            margin_utilization=margin_util,
            token_exposures=token_exposures,
            position_count=len(active_positions),
            total_equity=portfolio_state.total_equity,
        )

        return RiskMetrics(
            timestamp=timestamp,
            portfolio_id=portfolio_id,
            total_exposure=total_exposure,
            net_exposure=net_exposure,
            gross_exposure=gross_exposure,
            margin_utilization=margin_util,
            token_exposures=token_exposures,
            long_exposure=long_exposure,
            short_exposure=short_exposure,
            concentration_risk=concentration_risk,
            alerts=alerts,
        )

    def _calculate_token_exposures(
        self,
        positions: list[Position],
    ) -> list[TokenExposure]:
        """Calculate exposure breakdown by token.

        Args:
            positions: List of active positions

        Returns:
            List of TokenExposure for each token with positions
        """
        exposures: dict[str, TokenExposure] = {}

        for pos in positions:
            token = pos.token
            if token not in exposures:
                exposures[token] = TokenExposure(token=token)

            exposure = exposures[token]
            notional = pos.notional_value

            if pos.is_long:
                exposure.long_notional += notional
            else:
                exposure.short_notional += notional

            exposure.position_count += 1
            exposure.margin_used += pos.margin_used

        return list(exposures.values())

    def _calculate_concentration_risk(
        self,
        token_exposures: list[TokenExposure],
        total_equity: float,
    ) -> float:
        """Calculate concentration risk score.

        Measures how concentrated the portfolio is in a single token.
        Score ranges from 0 (well diversified) to 100 (fully concentrated).

        Args:
            token_exposures: List of token exposures
            total_equity: Total portfolio equity

        Returns:
            Concentration risk score (0-100)
        """
        if not token_exposures or total_equity <= 0:
            return 0.0

        # Find the largest exposure as percentage of equity
        max_exposure_pct = max(
            (te.gross_exposure / total_equity) * 100 for te in token_exposures
        )

        # Normalize to 0-100 scale (100% concentration = 100 score)
        return min(max_exposure_pct, 100.0)

    def _check_thresholds(
        self,
        total_exposure: float,
        net_exposure: float,
        margin_utilization: MarginUtilization,
        token_exposures: list[TokenExposure],
        position_count: int,
        total_equity: float,
    ) -> list[ExposureAlert]:
        """Check risk thresholds and generate alerts.

        Args:
            total_exposure: Total portfolio exposure
            net_exposure: Net exposure
            margin_utilization: Margin utilization metrics
            token_exposures: Token-level exposures
            position_count: Number of active positions
            total_equity: Total portfolio equity

        Returns:
            List of triggered alerts
        """
        alerts: list[ExposureAlert] = []

        if total_equity <= 0:
            return alerts

        # Check total exposure threshold
        exposure_pct = (abs(net_exposure) / total_equity) * 100
        if exposure_pct > self.thresholds.max_exposure_pct:
            alerts.append(
                ExposureAlert(
                    alert_type="exposure",
                    severity=RiskLevel.HIGH,
                    message=(
                        f"Net exposure ({exposure_pct:.1f}%) exceeds "
                        f"threshold ({self.thresholds.max_exposure_pct}%)"
                    ),
                    threshold=self.thresholds.max_exposure_pct,
                    current_value=exposure_pct,
                )
            )

        # Check margin utilization threshold
        if (
            margin_utilization.utilization_pct
            > self.thresholds.max_margin_utilization_pct
        ):
            alerts.append(
                ExposureAlert(
                    alert_type="margin",
                    severity=margin_utilization.risk_level,
                    message=(
                        f"Margin utilization ({margin_utilization.utilization_pct:.1f}%) "
                        f"exceeds threshold ({self.thresholds.max_margin_utilization_pct}%)"
                    ),
                    threshold=self.thresholds.max_margin_utilization_pct,
                    current_value=margin_utilization.utilization_pct,
                )
            )

        # Check concentration threshold for each token
        for te in token_exposures:
            if total_equity > 0:
                concentration_pct = (te.gross_exposure / total_equity) * 100
                if concentration_pct > self.thresholds.max_concentration_pct:
                    alerts.append(
                        ExposureAlert(
                            alert_type="concentration",
                            severity=RiskLevel.HIGH,
                            message=(
                                f"{te.token} concentration ({concentration_pct:.1f}%) "
                                f"exceeds threshold ({self.thresholds.max_concentration_pct}%)"
                            ),
                            threshold=self.thresholds.max_concentration_pct,
                            current_value=concentration_pct,
                        )
                    )

        # Check position count threshold
        if position_count > self.thresholds.max_position_count:
            alerts.append(
                ExposureAlert(
                    alert_type="position_count",
                    severity=RiskLevel.MEDIUM,
                    message=(
                        f"Position count ({position_count}) exceeds "
                        f"threshold ({self.thresholds.max_position_count})"
                    ),
                    threshold=float(self.thresholds.max_position_count),
                    current_value=float(position_count),
                )
            )

        return alerts

    def update_thresholds(self, thresholds: RiskThresholds) -> None:
        """Update risk thresholds.

        Args:
            thresholds: New risk thresholds
        """
        self.thresholds = thresholds

    def get_heat_map_data(
        self,
        risk_metrics: RiskMetrics,
    ) -> dict[str, Any]:
        """Generate heat map data for dashboard visualization.

        Args:
            risk_metrics: Calculated risk metrics

        Returns:
            Dictionary with heat map data structure
        """
        # Sort tokens by gross exposure for visualization
        sorted_exposures = sorted(
            risk_metrics.token_exposures,
            key=lambda x: x.gross_exposure,
            reverse=True,
        )

        heat_map = {
            "tokens": [te.token for te in sorted_exposures],
            "long_exposure": [te.long_notional for te in sorted_exposures],
            "short_exposure": [te.short_notional for te in sorted_exposures],
            "net_exposure": [te.net_exposure for te in sorted_exposures],
            "exposure_pct": [
                (te.gross_exposure / risk_metrics.total_exposure * 100)
                if risk_metrics.total_exposure > 0
                else 0
                for te in sorted_exposures
            ],
            "directional_bias": [te.directional_bias for te in sorted_exposures],
        }

        return heat_map

    def generate_risk_report(
        self,
        risk_metrics: RiskMetrics,
    ) -> dict[str, Any]:
        """Generate on-demand risk report.

        Args:
            risk_metrics: Calculated risk metrics

        Returns:
            Comprehensive risk report dictionary
        """
        heat_map = self.get_heat_map_data(risk_metrics)

        return {
            "report_type": "risk_exposure",
            "generated_at": risk_metrics.timestamp.isoformat(),
            "portfolio_id": risk_metrics.portfolio_id,
            "summary": {
                "total_exposure": round(risk_metrics.total_exposure, 8),
                "net_exposure": round(risk_metrics.net_exposure, 8),
                "gross_exposure": round(risk_metrics.gross_exposure, 8),
                "long_exposure": round(risk_metrics.long_exposure, 8),
                "short_exposure": round(risk_metrics.short_exposure, 8),
                "concentration_risk": round(risk_metrics.concentration_risk, 2),
            },
            "margin": risk_metrics.margin_utilization.to_dict(),
            "exposure_by_token": [te.to_dict() for te in risk_metrics.token_exposures],
            "heat_map": heat_map,
            "alerts": [alert.to_dict() for alert in risk_metrics.alerts],
            "thresholds": self.thresholds.to_dict(),
        }
