"""Tests for risk exposure calculator."""

from __future__ import annotations

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
    RiskThresholds,
    TokenExposure,
)


class TestRiskLevel:
    """Tests for RiskLevel enum."""

    def test_risk_level_values(self) -> None:
        """Test risk level enum values."""
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.MEDIUM.value == "medium"
        assert RiskLevel.HIGH.value == "high"
        assert RiskLevel.CRITICAL.value == "critical"

    def test_risk_level_str(self) -> None:
        """Test risk level string representation."""
        assert str(RiskLevel.LOW) == "low"
        assert str(RiskLevel.CRITICAL) == "critical"


class TestTokenExposure:
    """Tests for TokenExposure dataclass."""

    def test_basic_creation(self) -> None:
        """Test basic token exposure creation."""
        exposure = TokenExposure(
            token="BTC",
            long_notional=100000.0,
            short_notional=0.0,
            position_count=2,
            margin_used=50000.0,
        )

        assert exposure.token == "BTC"
        assert exposure.long_notional == 100000.0
        assert exposure.short_notional == 0.0
        assert exposure.net_exposure == 100000.0
        assert exposure.gross_exposure == 100000.0
        assert exposure.directional_bias == "long"

    def test_short_bias(self) -> None:
        """Test short directional bias."""
        exposure = TokenExposure(
            token="ETH",
            long_notional=0.0,
            short_notional=50000.0,
            position_count=1,
        )

        assert exposure.net_exposure == -50000.0
        assert exposure.gross_exposure == 50000.0
        assert exposure.directional_bias == "short"

    def test_neutral_bias(self) -> None:
        """Test neutral directional bias."""
        exposure = TokenExposure(
            token="SOL",
            long_notional=50000.0,
            short_notional=50000.0,
            position_count=2,
        )

        assert exposure.net_exposure == 0.0
        assert exposure.gross_exposure == 100000.0
        assert exposure.directional_bias == "neutral"

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        exposure = TokenExposure(
            token="BTC",
            long_notional=100000.0,
            short_notional=20000.0,
            position_count=3,
            margin_used=60000.0,
        )

        data = exposure.to_dict()

        assert data["token"] == "BTC"
        assert data["long_notional"] == 100000.0
        assert data["short_notional"] == 20000.0
        assert data["net_exposure"] == 80000.0
        assert data["gross_exposure"] == 120000.0
        assert data["directional_bias"] == "long"


class TestMarginUtilization:
    """Tests for MarginUtilization dataclass."""

    def test_utilization_calculation(self) -> None:
        """Test margin utilization percentage calculation."""
        margin = MarginUtilization(
            margin_used=50000.0,
            total_equity=100000.0,
            available_equity=50000.0,
        )

        assert margin.utilization_pct == 50.0
        assert margin.risk_level == RiskLevel.MEDIUM

    def test_low_risk_level(self) -> None:
        """Test low risk level at 25% utilization."""
        margin = MarginUtilization(
            margin_used=25000.0,
            total_equity=100000.0,
            available_equity=75000.0,
        )

        assert margin.utilization_pct == 25.0
        assert margin.risk_level == RiskLevel.LOW

    def test_high_risk_level(self) -> None:
        """Test high risk level at 80% utilization."""
        margin = MarginUtilization(
            margin_used=80000.0,
            total_equity=100000.0,
            available_equity=20000.0,
        )

        assert margin.utilization_pct == 80.0
        assert margin.risk_level == RiskLevel.HIGH

    def test_critical_risk_level(self) -> None:
        """Test critical risk level at 95% utilization."""
        margin = MarginUtilization(
            margin_used=95000.0,
            total_equity=100000.0,
            available_equity=5000.0,
        )

        assert margin.utilization_pct == 95.0
        assert margin.risk_level == RiskLevel.CRITICAL

    def test_zero_equity(self) -> None:
        """Test handling of zero total equity."""
        margin = MarginUtilization(
            margin_used=0.0,
            total_equity=0.0,
            available_equity=0.0,
        )

        assert margin.utilization_pct == 0.0
        assert margin.risk_level == RiskLevel.LOW

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        margin = MarginUtilization(
            margin_used=50000.0,
            total_equity=100000.0,
            available_equity=50000.0,
        )

        data = margin.to_dict()

        assert data["margin_used"] == 50000.0
        assert data["total_equity"] == 100000.0
        assert data["available_equity"] == 50000.0
        assert data["utilization_pct"] == 50.0
        assert data["risk_level"] == "medium"


class TestRiskThresholds:
    """Tests for RiskThresholds dataclass."""

    def test_default_thresholds(self) -> None:
        """Test default threshold values."""
        thresholds = RiskThresholds()

        assert thresholds.max_exposure_pct == 80.0
        assert thresholds.max_margin_utilization_pct == 80.0
        assert thresholds.max_concentration_pct == 50.0
        assert thresholds.max_position_count == 20

    def test_custom_thresholds(self) -> None:
        """Test custom threshold values."""
        thresholds = RiskThresholds(
            max_exposure_pct=70.0,
            max_margin_utilization_pct=75.0,
            max_concentration_pct=40.0,
            max_position_count=15,
        )

        assert thresholds.max_exposure_pct == 70.0
        assert thresholds.max_margin_utilization_pct == 75.0
        assert thresholds.max_concentration_pct == 40.0
        assert thresholds.max_position_count == 15


class TestRiskCalculator:
    """Tests for RiskCalculator class."""

    def test_empty_portfolio(self) -> None:
        """Test risk calculation with empty portfolio."""
        state = PortfolioState(portfolio_id="test-portfolio")
        state.update_balance("USDT", free=100000.0)

        calculator = RiskCalculator()
        metrics = calculator.calculate_risk_metrics(state)

        assert metrics.total_exposure == 0.0
        assert metrics.net_exposure == 0.0
        assert metrics.gross_exposure == 0.0
        assert metrics.long_exposure == 0.0
        assert metrics.short_exposure == 0.0
        assert metrics.concentration_risk == 0.0
        assert len(metrics.alerts) == 0

    def test_single_long_position(self) -> None:
        """Test risk calculation with single long position."""
        state = PortfolioState(portfolio_id="test-portfolio")
        state.update_balance("USDT", free=100000.0)

        position = Position(
            position_id="pos-1",
            token="BTC",
            direction=PositionDirection.LONG,
            entry_price=50000.0,
            quantity=1.0,
            current_price=51000.0,
        )
        state.add_position(position)

        calculator = RiskCalculator()
        metrics = calculator.calculate_risk_metrics(state)

        assert metrics.total_exposure == 51000.0  # current_price * quantity
        assert metrics.net_exposure == 51000.0
        assert metrics.gross_exposure == 51000.0
        assert metrics.long_exposure == 51000.0
        assert metrics.short_exposure == 0.0

    def test_long_and_short_positions(self) -> None:
        """Test risk calculation with both long and short positions."""
        state = PortfolioState(portfolio_id="test-portfolio")
        state.update_balance("USDT", free=100000.0)

        # Long BTC position
        long_pos = Position(
            position_id="pos-1",
            token="BTC",
            direction=PositionDirection.LONG,
            entry_price=50000.0,
            quantity=1.0,
            current_price=51000.0,
        )
        state.add_position(long_pos)

        # Short ETH position
        short_pos = Position(
            position_id="pos-2",
            token="ETH",
            direction=PositionDirection.SHORT,
            entry_price=3000.0,
            quantity=10.0,
            current_price=2900.0,
        )
        state.add_position(short_pos)

        calculator = RiskCalculator()
        metrics = calculator.calculate_risk_metrics(state)

        assert metrics.long_exposure == 51000.0
        assert metrics.short_exposure == 29000.0
        assert metrics.gross_exposure == 80000.0
        assert metrics.net_exposure == 22000.0  # 51000 - 29000

    def test_exposure_alert_triggered(self) -> None:
        """Test exposure alert when threshold is breached."""
        state = PortfolioState(portfolio_id="test-portfolio")
        state.update_balance("USDT", free=100000.0)

        # Large position that exceeds 80% exposure threshold
        position = Position(
            position_id="pos-1",
            token="BTC",
            direction=PositionDirection.LONG,
            entry_price=50000.0,
            quantity=2.0,  # $100k notional at entry, $102k at current price
            current_price=51000.0,
            leverage=1.0,
        )
        state.add_position(position)

        calculator = RiskCalculator()
        metrics = calculator.calculate_risk_metrics(state)

        # Should trigger exposure alert (>80%)
        exposure_alerts = [a for a in metrics.alerts if a.alert_type == "exposure"]
        assert len(exposure_alerts) > 0
        assert exposure_alerts[0].severity == RiskLevel.HIGH

    def test_margin_alert_triggered(self) -> None:
        """Test margin utilization alert when threshold is breached."""
        state = PortfolioState(portfolio_id="test-portfolio")
        state.update_balance("USDT", free=200000.0)

        # Position with high margin usage - $100k notional at 2x leverage = $50k margin
        position = Position(
            position_id="pos-1",
            token="BTC",
            direction=PositionDirection.LONG,
            entry_price=50000.0,
            quantity=2.0,
            current_price=50000.0,  # No PnL to simplify calculation
            leverage=2.0,
        )
        state.add_position(position)

        calculator = RiskCalculator()
        metrics = calculator.calculate_risk_metrics(state)

        # Margin utilization = 50000 / 200000 = 25%
        # Should NOT trigger margin alert at 25%
        assert metrics.margin_utilization.utilization_pct == 25.0

        # Now test with high margin utilization that triggers alert
        state2 = PortfolioState(portfolio_id="test-portfolio-2")
        state2.update_balance("USDT", free=100000.0)

        # Position using 85% of equity as margin
        position2 = Position(
            position_id="pos-2",
            token="BTC",
            direction=PositionDirection.LONG,
            entry_price=50000.0,
            quantity=1.7,  # $85k notional
            current_price=50000.0,
            leverage=1.0,  # $85k margin used
        )
        state2.add_position(position2)

        metrics2 = calculator.calculate_risk_metrics(state2)

        # Should trigger margin alert (>80%)
        margin_alerts = [a for a in metrics2.alerts if a.alert_type == "margin"]
        assert len(margin_alerts) > 0
        assert margin_alerts[0].severity == RiskLevel.HIGH

    def test_concentration_risk_calculation(self) -> None:
        """Test concentration risk calculation."""
        state = PortfolioState(portfolio_id="test-portfolio")
        state.update_balance("USDT", free=100000.0)

        # Single large position - high concentration
        position = Position(
            position_id="pos-1",
            token="BTC",
            direction=PositionDirection.LONG,
            entry_price=50000.0,
            quantity=1.5,
            current_price=51000.0,  # $76.5k exposure
        )
        state.add_position(position)

        calculator = RiskCalculator()
        metrics = calculator.calculate_risk_metrics(state)

        # Concentration should be ~76.5% (exposure / equity)
        assert metrics.concentration_risk > 50.0

    def test_concentration_alert_triggered(self) -> None:
        """Test concentration alert when threshold is breached."""
        state = PortfolioState(portfolio_id="test-portfolio")
        state.update_balance("USDT", free=100000.0)

        # Large single-token position exceeding 50% threshold
        position = Position(
            position_id="pos-1",
            token="BTC",
            direction=PositionDirection.LONG,
            entry_price=50000.0,
            quantity=1.5,
            current_price=60000.0,  # $90k exposure - 90% of equity
        )
        state.add_position(position)

        calculator = RiskCalculator()
        metrics = calculator.calculate_risk_metrics(state)

        # Should trigger concentration alert
        concentration_alerts = [
            a for a in metrics.alerts if a.alert_type == "concentration"
        ]
        assert len(concentration_alerts) > 0

    def test_position_count_alert(self) -> None:
        """Test position count alert when threshold is breached."""
        state = PortfolioState(portfolio_id="test-portfolio")
        state.update_balance("USDT", free=1000000.0)

        # Add 25 positions (exceeds default threshold of 20)
        for i in range(25):
            position = Position(
                position_id=f"pos-{i}",
                token=f"TOKEN{i}",
                direction=PositionDirection.LONG,
                entry_price=100.0,
                quantity=1.0,
                current_price=100.0,
            )
            state.add_position(position)

        calculator = RiskCalculator()
        metrics = calculator.calculate_risk_metrics(state)

        # Should trigger position count alert
        count_alerts = [a for a in metrics.alerts if a.alert_type == "position_count"]
        assert len(count_alerts) > 0
        assert count_alerts[0].current_value == 25.0

    def test_token_exposures_calculation(self) -> None:
        """Test token-level exposure breakdown."""
        state = PortfolioState(portfolio_id="test-portfolio")
        state.update_balance("USDT", free=100000.0)

        # Multiple BTC positions
        state.add_position(
            Position(
                position_id="pos-1",
                token="BTC",
                direction=PositionDirection.LONG,
                entry_price=50000.0,
                quantity=0.5,
                current_price=51000.0,
            )
        )
        state.add_position(
            Position(
                position_id="pos-2",
                token="BTC",
                direction=PositionDirection.SHORT,
                entry_price=50000.0,
                quantity=0.3,
                current_price=51000.0,
            )
        )

        # ETH position
        state.add_position(
            Position(
                position_id="pos-3",
                token="ETH",
                direction=PositionDirection.LONG,
                entry_price=3000.0,
                quantity=5.0,
                current_price=3100.0,
            )
        )

        calculator = RiskCalculator()
        metrics = calculator.calculate_risk_metrics(state)

        # Should have 2 tokens
        assert len(metrics.token_exposures) == 2

        # Find BTC exposure
        btc_exposure = next(
            (te for te in metrics.token_exposures if te.token == "BTC"), None
        )
        assert btc_exposure is not None
        assert btc_exposure.position_count == 2
        assert btc_exposure.long_notional == 25500.0  # 0.5 * 51000
        assert btc_exposure.short_notional == 15300.0  # 0.3 * 51000

    def test_closed_positions_excluded(self) -> None:
        """Test that closed positions are excluded from risk calculations."""
        state = PortfolioState(portfolio_id="test-portfolio")
        state.update_balance("USDT", free=100000.0)

        # Open position
        state.add_position(
            Position(
                position_id="pos-1",
                token="BTC",
                direction=PositionDirection.LONG,
                entry_price=50000.0,
                quantity=1.0,
                current_price=51000.0,
                status=PositionStatus.OPEN,
            )
        )

        # Closed position
        state.add_position(
            Position(
                position_id="pos-2",
                token="ETH",
                direction=PositionDirection.LONG,
                entry_price=3000.0,
                quantity=10.0,
                current_price=3100.0,
                status=PositionStatus.CLOSED,
            )
        )

        calculator = RiskCalculator()
        metrics = calculator.calculate_risk_metrics(state)

        # Only BTC should be in exposures
        assert len(metrics.token_exposures) == 1
        assert metrics.token_exposures[0].token == "BTC"
        assert metrics.total_exposure == 51000.0

    def test_heat_map_data(self) -> None:
        """Test heat map data generation."""
        state = PortfolioState(portfolio_id="test-portfolio")
        state.update_balance("USDT", free=100000.0)

        state.add_position(
            Position(
                position_id="pos-1",
                token="BTC",
                direction=PositionDirection.LONG,
                entry_price=50000.0,
                quantity=1.0,
                current_price=51000.0,
            )
        )
        state.add_position(
            Position(
                position_id="pos-2",
                token="ETH",
                direction=PositionDirection.LONG,
                entry_price=3000.0,
                quantity=5.0,
                current_price=3100.0,
            )
        )

        calculator = RiskCalculator()
        metrics = calculator.calculate_risk_metrics(state)
        heat_map = calculator.get_heat_map_data(metrics)

        assert "tokens" in heat_map
        assert "long_exposure" in heat_map
        assert "short_exposure" in heat_map
        assert "net_exposure" in heat_map
        assert len(heat_map["tokens"]) == 2

    def test_risk_report_generation(self) -> None:
        """Test on-demand risk report generation."""
        state = PortfolioState(portfolio_id="test-portfolio")
        state.update_balance("USDT", free=100000.0)

        state.add_position(
            Position(
                position_id="pos-1",
                token="BTC",
                direction=PositionDirection.LONG,
                entry_price=50000.0,
                quantity=1.0,
                current_price=51000.0,
            )
        )

        calculator = RiskCalculator()
        metrics = calculator.calculate_risk_metrics(state)
        report = calculator.generate_risk_report(metrics)

        assert report["report_type"] == "risk_exposure"
        assert "summary" in report
        assert "margin" in report
        assert "exposure_by_token" in report
        assert "heat_map" in report
        assert "thresholds" in report
        assert report["summary"]["total_exposure"] == 51000.0

    def test_update_thresholds(self) -> None:
        """Test updating risk thresholds."""
        calculator = RiskCalculator()

        # Default threshold should not trigger with 70% exposure
        assert calculator.thresholds.max_exposure_pct == 80.0

        # Update to more strict threshold
        new_thresholds = RiskThresholds(max_exposure_pct=60.0)
        calculator.update_thresholds(new_thresholds)

        assert calculator.thresholds.max_exposure_pct == 60.0

    def test_risk_metrics_to_dict(self) -> None:
        """Test RiskMetrics conversion to dictionary."""
        state = PortfolioState(portfolio_id="test-portfolio")
        state.update_balance("USDT", free=100000.0)

        state.add_position(
            Position(
                position_id="pos-1",
                token="BTC",
                direction=PositionDirection.LONG,
                entry_price=50000.0,
                quantity=1.0,
                current_price=51000.0,
            )
        )

        calculator = RiskCalculator()
        metrics = calculator.calculate_risk_metrics(state)
        data = metrics.to_dict()

        assert data["portfolio_id"] == "test-portfolio"
        assert data["total_exposure"] == 51000.0
        assert data["net_exposure"] == 51000.0
        assert "margin_utilization" in data
        assert "token_exposures" in data
        assert "concentration_risk" in data
        assert "alerts" in data

    def test_exposure_alert_to_dict(self) -> None:
        """Test ExposureAlert conversion to dictionary."""
        alert = ExposureAlert(
            alert_type="exposure",
            severity=RiskLevel.HIGH,
            message="Exposure exceeds threshold",
            threshold=80.0,
            current_value=85.0,
        )

        data = alert.to_dict()

        assert data["alert_type"] == "exposure"
        assert data["severity"] == "high"
        assert data["message"] == "Exposure exceeds threshold"
        assert data["threshold"] == 80.0
        assert data["current_value"] == 85.0
        assert "timestamp" in data
