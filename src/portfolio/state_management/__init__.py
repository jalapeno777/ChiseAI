"""Portfolio state management module.

Provides real-time portfolio tracking, position management,
and state persistence with fault tolerance.
"""

from portfolio.state_management.api import PortfolioAPI, create_portfolio_routes
from portfolio.state_management.models import (
    Balance,
    PortfolioSnapshot,
    PortfolioState,
    Position,
    PositionDirection,
    PositionStatus,
)
from portfolio.state_management.storage import (
    FallbackPortfolioStorage,
    InfluxDBPortfolioStorage,
    PostgresPortfolioStorage,
    StorageConfig,
)
from portfolio.state_management.risk_calculator import (
    ExposureAlert,
    RiskCalculator,
    RiskLevel,
    RiskMetrics,
    RiskThresholds,
    TokenExposure,
)
from portfolio.state_management.tracker import (
    BalanceUpdate,
    PortfolioStorageInterface,
    PortfolioTracker,
    PortfolioUpdate,
    PositionUpdate,
    PriceUpdate,
)

__all__ = [
    # Models
    "Position",
    "PositionDirection",
    "PositionStatus",
    "Balance",
    "PortfolioState",
    "PortfolioSnapshot",
    # Tracker
    "PortfolioTracker",
    "PortfolioUpdate",
    "PositionUpdate",
    "BalanceUpdate",
    "PriceUpdate",
    "PortfolioStorageInterface",
    # Storage
    "StorageConfig",
    "InfluxDBPortfolioStorage",
    "PostgresPortfolioStorage",
    "FallbackPortfolioStorage",
    # API
    "PortfolioAPI",
    "create_portfolio_routes",
    # Risk Calculator
    "RiskCalculator",
    "RiskMetrics",
    "RiskThresholds",
    "RiskLevel",
    "TokenExposure",
    "ExposureAlert",
]
