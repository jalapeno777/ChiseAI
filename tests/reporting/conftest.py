"""Pytest configuration and fixtures for reporting tests"""

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_redis():
    """Provides a mock Redis client for testing"""
    redis = MagicMock()
    redis.get.return_value = None
    redis.set.return_value = True
    redis.delete.return_value = 1
    redis.keys.return_value = []
    redis.dbsize.return_value = 0
    return redis


@pytest.fixture
def sample_trade():
    """Provides a sample trade dictionary"""
    return {
        "trade_id": "T001",
        "symbol": "AAPL",
        "direction": "long",
        "quantity": Decimal("10"),
        "entry_price": Decimal("150.00"),
        "exit_price": Decimal("155.00"),
        "entry_time": datetime(2026, 3, 28, 10, 0),
        "exit_time": datetime(2026, 3, 28, 14, 0),
        "pnl": Decimal("50.00"),
        "fees": Decimal("1.00"),
        "timestamp": datetime(2026, 3, 28, 14, 0),
    }


@pytest.fixture
def sample_trades(sample_trade):
    """Provides a list of sample trades"""
    trades = [sample_trade]
    trades.append(
        {
            **sample_trade,
            "trade_id": "T002",
            "symbol": "GOOGL",
            "pnl": Decimal("-30.00"),
            "timestamp": datetime(2026, 3, 28, 15, 0),
        }
    )
    trades.append(
        {
            **sample_trade,
            "trade_id": "T003",
            "symbol": "MSFT",
            "pnl": Decimal("75.00"),
            "timestamp": datetime(2026, 3, 28, 16, 0),
        }
    )
    return trades


@pytest.fixture
def sample_equity_curve():
    """Provides a sample equity curve for drawdown testing"""
    return [
        {
            "equity": Decimal("10000.00"),
            "peak_equity": Decimal("10000.00"),
            "timestamp": datetime(2026, 3, 28, 9, 0),
        },
        {
            "equity": Decimal("10200.00"),
            "peak_equity": Decimal("10200.00"),
            "timestamp": datetime(2026, 3, 28, 10, 0),
        },
        {
            "equity": Decimal("9800.00"),
            "peak_equity": Decimal("10200.00"),
            "timestamp": datetime(2026, 3, 28, 11, 0),
        },
        {
            "equity": Decimal("9600.00"),
            "peak_equity": Decimal("10200.00"),
            "timestamp": datetime(2026, 3, 28, 12, 0),
        },
        {
            "equity": Decimal("9900.00"),
            "peak_equity": Decimal("10200.00"),
            "timestamp": datetime(2026, 3, 28, 13, 0),
        },
        {
            "equity": Decimal("10500.00"),
            "peak_equity": Decimal("10500.00"),
            "timestamp": datetime(2026, 3, 28, 14, 0),
        },
    ]
