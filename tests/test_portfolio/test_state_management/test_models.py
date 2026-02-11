"""Tests for portfolio state management models."""

from portfolio.state_management.models import (
    Balance,
    PortfolioSnapshot,
    PortfolioState,
    Position,
    PositionDirection,
    PositionStatus,
)


class TestPositionDirection:
    """Tests for PositionDirection enum."""

    def test_direction_values(self) -> None:
        """Test direction enum values."""
        assert PositionDirection.LONG.value == "LONG"
        assert PositionDirection.SHORT.value == "SHORT"

    def test_direction_str(self) -> None:
        """Test direction string representation."""
        assert str(PositionDirection.LONG) == "LONG"
        assert str(PositionDirection.SHORT) == "SHORT"


class TestPositionStatus:
    """Tests for PositionStatus enum."""

    def test_status_values(self) -> None:
        """Test status enum values."""
        assert PositionStatus.OPEN.value == "open"
        assert PositionStatus.CLOSED.value == "closed"
        assert PositionStatus.PENDING.value == "pending"


class TestPosition:
    """Tests for Position dataclass."""

    def test_basic_creation(self) -> None:
        """Test basic position creation."""
        position = Position(
            position_id="test-pos-123",
            token="BTC",
            direction=PositionDirection.LONG,
            entry_price=50000.0,
            quantity=1.0,
            current_price=51000.0,
        )

        assert position.position_id == "test-pos-123"
        assert position.token == "BTC"
        assert position.direction == PositionDirection.LONG
        assert position.entry_price == 50000.0
        assert position.quantity == 1.0
        assert position.current_price == 51000.0
        assert position.is_open is True
        assert position.is_long is True
        assert position.is_short is False

    def test_long_pnl_calculation(self) -> None:
        """Test PnL calculation for long position."""
        position = Position(
            position_id="test-1",
            token="BTC",
            direction=PositionDirection.LONG,
            entry_price=50000.0,
            quantity=1.0,
            current_price=51000.0,
        )

        # PnL = (51000 - 50000) * 1 * 1 = 1000
        assert position.unrealized_pnl == 1000.0
        assert position.unrealized_pnl_pct == 2.0  # 2% with 1x leverage

    def test_short_pnl_calculation(self) -> None:
        """Test PnL calculation for short position."""
        position = Position(
            position_id="test-1",
            token="BTC",
            direction=PositionDirection.SHORT,
            entry_price=50000.0,
            quantity=1.0,
            current_price=49000.0,
        )

        # PnL = (50000 - 49000) * 1 * 1 = 1000
        assert position.unrealized_pnl == 1000.0
        assert position.unrealized_pnl_pct == 2.0

    def test_leverage_pnl_calculation(self) -> None:
        """Test PnL calculation with leverage."""
        position = Position(
            position_id="test-1",
            token="BTC",
            direction=PositionDirection.LONG,
            entry_price=50000.0,
            quantity=1.0,
            current_price=51000.0,
            leverage=3.0,
        )

        # PnL = (51000 - 50000) * 1 * 3 = 3000
        assert position.unrealized_pnl == 3000.0
        assert position.unrealized_pnl_pct == 6.0  # 2% * 3x = 6%

    def test_update_price(self) -> None:
        """Test price update."""
        position = Position(
            position_id="test-1",
            token="BTC",
            direction=PositionDirection.LONG,
            entry_price=50000.0,
            quantity=1.0,
            current_price=50000.0,
        )

        position.update_price(52000.0, timestamp=1234567890000)

        assert position.current_price == 52000.0
        assert position.unrealized_pnl == 2000.0
        assert position.last_update == 1234567890000

    def test_close_position(self) -> None:
        """Test position closing."""
        position = Position(
            position_id="test-1",
            token="BTC",
            direction=PositionDirection.LONG,
            entry_price=50000.0,
            quantity=1.0,
            current_price=51000.0,
        )

        realized_pnl = position.close_position(51000.0, timestamp=1234567890000)

        assert realized_pnl == 1000.0
        assert position.realized_pnl == 1000.0
        assert position.unrealized_pnl == 0.0
        assert position.status == PositionStatus.CLOSED
        assert position.is_closed is True

    def test_notional_value(self) -> None:
        """Test notional value calculation."""
        position = Position(
            position_id="test-1",
            token="BTC",
            direction=PositionDirection.LONG,
            entry_price=50000.0,
            quantity=2.0,
            current_price=51000.0,
        )

        assert position.notional_value == 102000.0  # 51000 * 2

    def test_margin_used_calculation(self) -> None:
        """Test margin used calculation."""
        position = Position(
            position_id="test-1",
            token="BTC",
            direction=PositionDirection.LONG,
            entry_price=50000.0,
            quantity=1.0,
            leverage=2.0,
        )

        # Margin = (50000 * 1) / 2 = 25000
        assert position.margin_used == 25000.0

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        position = Position(
            position_id="test-1",
            token="BTC",
            direction=PositionDirection.LONG,
            entry_price=50000.0,
            quantity=1.0,
            current_price=51000.0,
        )

        data = position.to_dict()

        assert data["position_id"] == "test-1"
        assert data["token"] == "BTC"
        assert data["direction"] == "LONG"
        assert data["entry_price"] == 50000.0
        assert data["unrealized_pnl"] == 1000.0
        assert "unrealized_pnl_pct" in data

    def test_from_dict(self) -> None:
        """Test creation from dictionary."""
        data = {
            "position_id": "test-1",
            "token": "BTC",
            "direction": "LONG",
            "entry_price": 50000.0,
            "quantity": 1.0,
            "current_price": 51000.0,
            "status": "open",
            "leverage": 2.0,
        }

        position = Position.from_dict(data)

        assert position.position_id == "test-1"
        assert position.direction == PositionDirection.LONG
        assert position.status == PositionStatus.OPEN
        assert position.leverage == 2.0


class TestBalance:
    """Tests for Balance dataclass."""

    def test_basic_creation(self) -> None:
        """Test basic balance creation."""
        balance = Balance(
            token="USDT",
            free=10000.0,
            locked=2000.0,
        )

        assert balance.token == "USDT"
        assert balance.free == 10000.0
        assert balance.locked == 2000.0
        assert balance.total == 12000.0

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        balance = Balance(token="BTC", free=1.5, locked=0.5)

        data = balance.to_dict()

        assert data["token"] == "BTC"
        assert data["free"] == 1.5
        assert data["locked"] == 0.5
        assert data["total"] == 2.0

    def test_from_dict(self) -> None:
        """Test creation from dictionary."""
        data = {"token": "ETH", "free": 10.0, "locked": 2.0}

        balance = Balance.from_dict(data)

        assert balance.token == "ETH"
        assert balance.free == 10.0
        assert balance.locked == 2.0


class TestPortfolioState:
    """Tests for PortfolioState dataclass."""

    def test_basic_creation(self) -> None:
        """Test basic portfolio state creation."""
        state = PortfolioState(portfolio_id="test-portfolio")

        assert state.portfolio_id == "test-portfolio"
        assert state.positions == {}
        assert state.balances == {}
        assert state.total_equity == 0.0

    def test_add_position(self) -> None:
        """Test adding a position."""
        state = PortfolioState(portfolio_id="test-portfolio")

        position = Position(
            position_id="pos-1",
            token="BTC",
            direction=PositionDirection.LONG,
            entry_price=50000.0,
            quantity=1.0,
            current_price=51000.0,
            leverage=1.0,
        )

        state.add_position(position)

        assert "pos-1" in state.positions
        assert len(state.get_open_positions()) == 1
        assert state.unrealized_pnl == 1000.0

    def test_update_position(self) -> None:
        """Test updating a position."""
        state = PortfolioState(portfolio_id="test-portfolio")

        position = Position(
            position_id="pos-1",
            token="BTC",
            direction=PositionDirection.LONG,
            entry_price=50000.0,
            quantity=1.0,
            current_price=50000.0,
        )
        state.add_position(position)

        updated = state.update_position("pos-1", current_price=52000.0)

        assert updated is not None
        assert updated.current_price == 52000.0
        assert updated.unrealized_pnl == 2000.0
        assert state.unrealized_pnl == 2000.0

    def test_update_position_not_found(self) -> None:
        """Test updating a non-existent position."""
        state = PortfolioState(portfolio_id="test-portfolio")

        result = state.update_position("non-existent", current_price=50000.0)

        assert result is None

    def test_remove_position(self) -> None:
        """Test removing a position."""
        state = PortfolioState(portfolio_id="test-portfolio")

        position = Position(
            position_id="pos-1",
            token="BTC",
            direction=PositionDirection.LONG,
            entry_price=50000.0,
            quantity=1.0,
            current_price=51000.0,
            realized_pnl=1000.0,
            status=PositionStatus.CLOSED,
        )
        state.add_position(position)

        removed = state.remove_position("pos-1")

        assert removed is not None
        assert "pos-1" not in state.positions
        assert state.realized_pnl == 1000.0

    def test_update_balance(self) -> None:
        """Test updating balance."""
        state = PortfolioState(portfolio_id="test-portfolio")

        balance = state.update_balance("USDT", free=10000.0, locked=2000.0)

        assert "USDT" in state.balances
        assert balance.free == 10000.0
        assert balance.locked == 2000.0
        assert state.total_equity == 12000.0

    def test_get_positions_by_token(self) -> None:
        """Test getting positions by token."""
        state = PortfolioState(portfolio_id="test-portfolio")

        state.add_position(
            Position(
                position_id="pos-1",
                token="BTC",
                direction=PositionDirection.LONG,
                entry_price=50000.0,
                quantity=1.0,
            )
        )
        state.add_position(
            Position(
                position_id="pos-2",
                token="ETH",
                direction=PositionDirection.LONG,
                entry_price=3000.0,
                quantity=10.0,
            )
        )

        btc_positions = state.get_positions_by_token("BTC")

        assert len(btc_positions) == 1
        assert btc_positions[0].position_id == "pos-1"

    def test_get_position_summary(self) -> None:
        """Test getting position summary."""
        state = PortfolioState(portfolio_id="test-portfolio")

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
                direction=PositionDirection.SHORT,
                entry_price=3000.0,
                quantity=10.0,
                current_price=2900.0,
            )
        )

        summary = state.get_position_summary()

        assert summary["total_positions"] == 2
        assert summary["open_positions"] == 2
        assert summary["long_positions"] == 1
        assert summary["short_positions"] == 1

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        state = PortfolioState(portfolio_id="test-portfolio")
        state.update_balance("USDT", free=10000.0)

        data = state.to_dict()

        assert data["portfolio_id"] == "test-portfolio"
        assert "balances" in data
        assert "USDT" in data["balances"]

    def test_from_dict(self) -> None:
        """Test creation from dictionary."""
        data = {
            "portfolio_id": "test-portfolio",
            "positions": {},
            "balances": {"USDT": {"token": "USDT", "free": 10000.0, "locked": 0.0}},
            "total_equity": 10000.0,
            "timestamp": 1234567890000,
        }

        state = PortfolioState.from_dict(data)

        assert state.portfolio_id == "test-portfolio"
        assert "USDT" in state.balances
        assert state.total_equity == 10000.0


class TestPortfolioSnapshot:
    """Tests for PortfolioSnapshot dataclass."""

    def test_basic_creation(self) -> None:
        """Test basic snapshot creation."""
        snapshot = PortfolioSnapshot(
            snapshot_id="snap-1",
            portfolio_id="test-portfolio",
            timestamp=1234567890000,
            total_equity=100000.0,
            available_equity=80000.0,
            margin_used=20000.0,
            unrealized_pnl=5000.0,
            realized_pnl=2000.0,
            position_count=5,
        )

        assert snapshot.snapshot_id == "snap-1"
        assert snapshot.total_equity == 100000.0
        assert snapshot.position_count == 5

    def test_from_portfolio_state(self) -> None:
        """Test creating snapshot from portfolio state."""
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

        snapshot = PortfolioSnapshot.from_portfolio_state("snap-1", state)

        assert snapshot.snapshot_id == "snap-1"
        assert snapshot.portfolio_id == "test-portfolio"
        assert snapshot.total_equity == 101000.0  # 100000 + 1000 unrealized
        assert snapshot.position_count == 1

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        snapshot = PortfolioSnapshot(
            snapshot_id="snap-1",
            portfolio_id="test-portfolio",
            timestamp=1234567890000,
            total_equity=100000.0,
            available_equity=80000.0,
            margin_used=20000.0,
            unrealized_pnl=5000.0,
            realized_pnl=2000.0,
            position_count=5,
            balance_summary={"USDT": 100000.0},
        )

        data = snapshot.to_dict()

        assert data["snapshot_id"] == "snap-1"
        assert data["total_equity"] == 100000.0
        assert data["balance_summary"]["USDT"] == 100000.0

    def test_from_dict(self) -> None:
        """Test creation from dictionary."""
        data = {
            "snapshot_id": "snap-1",
            "portfolio_id": "test-portfolio",
            "timestamp": 1234567890000,
            "total_equity": 100000.0,
            "available_equity": 80000.0,
            "margin_used": 20000.0,
            "unrealized_pnl": 5000.0,
            "realized_pnl": 2000.0,
            "position_count": 5,
            "balance_summary": {"USDT": 100000.0},
        }

        snapshot = PortfolioSnapshot.from_dict(data)

        assert snapshot.snapshot_id == "snap-1"
        assert snapshot.total_equity == 100000.0
        assert snapshot.balance_summary["USDT"] == 100000.0


class TestCriticalBugFixes:
    """Tests for CRITICAL bug fixes (ST-NS-014A)."""

    def test_pending_position_in_unrealized_pnl(self) -> None:
        """CRITICAL-4: Test PENDING positions are included in unrealized PnL."""
        state = PortfolioState(portfolio_id="test-portfolio")
        state.update_balance("USDT", free=100000.0)

        # Add OPEN position
        open_pos = Position(
            position_id="pos-open",
            token="BTC",
            direction=PositionDirection.LONG,
            entry_price=50000.0,
            quantity=1.0,
            current_price=51000.0,
            status=PositionStatus.OPEN,
        )
        state.add_position(open_pos)

        # Add PENDING position
        pending_pos = Position(
            position_id="pos-pending",
            token="ETH",
            direction=PositionDirection.LONG,
            entry_price=3000.0,
            quantity=10.0,
            current_price=3100.0,
            status=PositionStatus.PENDING,
        )
        state.add_position(pending_pos)

        # Add CLOSED position (should NOT be included)
        closed_pos = Position(
            position_id="pos-closed",
            token="SOL",
            direction=PositionDirection.LONG,
            entry_price=100.0,
            quantity=100.0,
            current_price=110.0,
            status=PositionStatus.CLOSED,
        )
        state.add_position(closed_pos)

        # CRITICAL-4 FIX: PENDING positions should be included in unrealized PnL
        # OPEN: (51000 - 50000) * 1 = 1000
        # PENDING: (3100 - 3000) * 10 = 1000
        # CLOSED: should be excluded
        expected_unrealized = 1000.0 + 1000.0  # OPEN + PENDING
        assert state.unrealized_pnl == expected_unrealized

        # Margin should also include PENDING positions
        # OPEN: (50000 * 1) / 1 = 50000
        # PENDING: (3000 * 10) / 1 = 30000
        expected_margin = 50000.0 + 30000.0
        assert state.margin_used == expected_margin

    def test_pending_position_margin_calculation(self) -> None:
        """CRITICAL-4: Test PENDING positions contribute to margin_used."""
        state = PortfolioState(portfolio_id="test-portfolio")
        state.update_balance("USDT", free=100000.0)

        # Add PENDING position with leverage
        pending_pos = Position(
            position_id="pos-pending",
            token="BTC",
            direction=PositionDirection.LONG,
            entry_price=50000.0,
            quantity=2.0,
            current_price=51000.0,
            status=PositionStatus.PENDING,
            leverage=2.0,
        )
        state.add_position(pending_pos)

        # Margin = (50000 * 2) / 2 = 50000
        assert state.margin_used == 50000.0

        # Available equity = total_balance - margin_used
        # = 100000 - 50000 = 50000
        assert state.available_equity == 50000.0
