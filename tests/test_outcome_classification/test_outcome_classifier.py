"""Tests for outcome classification in OutcomeCaptureIntegration.

Tests the _classify_outcome_type method and outcome field population
in _create_outcome_from_position.
"""

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

from ml.models.signal_outcome import OutcomeType


class TestOutcomeClassifier:
    """Tests for _classify_outcome_type method."""

    def setup_method(self):
        """Set up test fixtures."""
        # Import here to ensure we use the worktree version
        from execution.outcome_capture.integration import OutcomeCaptureIntegration

        self.integration = OutcomeCaptureIntegration()

    def test_classify_tp_hit_long_position(self):
        """Test TP_HIT classification for LONG position."""
        signal = {"take_profit_price": 50000, "stop_loss_price": 45000}
        result = self.integration._classify_outcome_type(signal, 50100, "LONG")
        assert result == OutcomeType.TP_HIT

    def test_classify_tp_hit_long_exact(self):
        """Test TP_HIT classification when exit equals take profit exactly."""
        signal = {"take_profit_price": 50000, "stop_loss_price": 45000}
        result = self.integration._classify_outcome_type(signal, 50000, "LONG")
        assert result == OutcomeType.TP_HIT

    def test_classify_sl_hit_long_position(self):
        """Test SL_HIT classification for LONG position."""
        signal = {"take_profit_price": 50000, "stop_loss_price": 45000}
        result = self.integration._classify_outcome_type(signal, 44900, "LONG")
        assert result == OutcomeType.SL_HIT

    def test_classify_sl_hit_long_exact(self):
        """Test SL_HIT classification when exit equals stop loss exactly."""
        signal = {"take_profit_price": 50000, "stop_loss_price": 45000}
        result = self.integration._classify_outcome_type(signal, 45000, "LONG")
        assert result == OutcomeType.SL_HIT

    def test_classify_manual_close_long_position(self):
        """Test MANUAL_CLOSE classification for LONG position between TP and SL."""
        signal = {"take_profit_price": 50000, "stop_loss_price": 45000}
        result = self.integration._classify_outcome_type(signal, 47500, "LONG")
        assert result == OutcomeType.MANUAL_CLOSE

    def test_classify_tp_hit_short_position(self):
        """Test TP_HIT classification for SHORT position."""
        signal = {"take_profit_price": 50000, "stop_loss_price": 55000}
        result = self.integration._classify_outcome_type(signal, 49900, "SHORT")
        assert result == OutcomeType.TP_HIT

    def test_classify_tp_hit_short_exact(self):
        """Test TP_HIT classification when exit equals take profit exactly for SHORT."""
        signal = {"take_profit_price": 50000, "stop_loss_price": 55000}
        result = self.integration._classify_outcome_type(signal, 50000, "SHORT")
        assert result == OutcomeType.TP_HIT

    def test_classify_sl_hit_short_position(self):
        """Test SL_HIT classification for SHORT position."""
        signal = {"take_profit_price": 50000, "stop_loss_price": 55000}
        result = self.integration._classify_outcome_type(signal, 55100, "SHORT")
        assert result == OutcomeType.SL_HIT

    def test_classify_sl_hit_short_exact(self):
        """Test SL_HIT classification when exit equals stop loss exactly for SHORT."""
        signal = {"take_profit_price": 50000, "stop_loss_price": 55000}
        result = self.integration._classify_outcome_type(signal, 55000, "SHORT")
        assert result == OutcomeType.SL_HIT

    def test_classify_manual_close_short_position(self):
        """Test MANUAL_CLOSE classification for SHORT position between TP and SL."""
        signal = {"take_profit_price": 50000, "stop_loss_price": 55000}
        result = self.integration._classify_outcome_type(signal, 52500, "SHORT")
        assert result == OutcomeType.MANUAL_CLOSE

    def test_classify_unknown_when_signal_empty(self):
        """Test UNKNOWN classification when signal is None."""
        result = self.integration._classify_outcome_type(None, 50000, "LONG")
        assert result == OutcomeType.UNKNOWN

    def test_classify_unknown_when_signal_empty_dict(self):
        """Test MANUAL_CLOSE classification when signal is empty dict with no TP/SL."""
        result = self.integration._classify_outcome_type({}, 50000, "LONG")
        assert result == OutcomeType.MANUAL_CLOSE

    def test_classify_manual_close_when_no_tp_sl(self):
        """Test MANUAL_CLOSE when signal has no TP or SL prices."""
        signal = {}
        result = self.integration._classify_outcome_type(signal, 50000, "LONG")
        assert result == OutcomeType.MANUAL_CLOSE

    def test_classify_manual_close_when_only_tp(self):
        """Test MANUAL_CLOSE when only TP is set, exit doesn't hit it."""
        signal = {"take_profit_price": 50000}
        result = self.integration._classify_outcome_type(signal, 49000, "LONG")
        assert result == OutcomeType.MANUAL_CLOSE

    def test_classify_manual_close_when_only_sl(self):
        """Test MANUAL_CLOSE when only SL is set, exit doesn't hit it."""
        signal = {"stop_loss_price": 45000}
        result = self.integration._classify_outcome_type(signal, 46000, "LONG")
        assert result == OutcomeType.MANUAL_CLOSE

    def test_classify_with_take_profit_key(self):
        """Test classification works with 'take_profit' key (not take_profit_price)."""
        signal = {"take_profit": 50000, "stop_loss": 45000}
        result = self.integration._classify_outcome_type(signal, 50100, "LONG")
        assert result == OutcomeType.TP_HIT


class TestOutcomeFieldPopulation:
    """Tests for outcome field population in _create_outcome_from_position."""

    def setup_method(self):
        """Set up test fixtures."""
        from execution.outcome_capture.integration import OutcomeCaptureIntegration

        self.integration = OutcomeCaptureIntegration()

    def _create_mock_position(
        self,
        position_id: str = "test-pos-123",
        symbol: str = "BTC/USDT",
        side: str = "long",
        entry_price: float = 50000.0,
        quantity: float = 0.1,
        metadata: dict | None = None,
    ):
        """Create a mock position object."""
        position = MagicMock()
        position.position_id = position_id
        position.symbol = symbol
        position.side = side
        position.entry_price = entry_price
        position.quantity = quantity
        position.metadata = metadata or {}
        return position

    def test_outcome_type_populated_for_tp_hit(self):
        """Test outcome_type is set to TP_HIT when exit hits take profit."""
        position = self._create_mock_position(
            side="long",
            metadata={"take_profit": 51000, "stop_loss": 49000},
        )
        outcome = self.integration._create_outcome_from_position(
            position, realized_pnl=100.0, exit_price=51100.0
        )
        assert outcome.outcome_type == OutcomeType.TP_HIT

    def test_outcome_type_populated_for_sl_hit(self):
        """Test outcome_type is set to SL_HIT when exit hits stop loss."""
        position = self._create_mock_position(
            side="long",
            metadata={"take_profit": 51000, "stop_loss": 49000},
        )
        outcome = self.integration._create_outcome_from_position(
            position, realized_pnl=-100.0, exit_price=48900.0
        )
        assert outcome.outcome_type == OutcomeType.SL_HIT

    def test_outcome_type_populated_for_manual_close(self):
        """Test outcome_type is set to MANUAL_CLOSE when neither TP nor SL hit."""
        position = self._create_mock_position(
            side="long",
            metadata={"take_profit": 51000, "stop_loss": 49000},
        )
        outcome = self.integration._create_outcome_from_position(
            position, realized_pnl=50.0, exit_price=50000.0
        )
        assert outcome.outcome_type == OutcomeType.MANUAL_CLOSE

    def test_outcome_type_populated_for_short_tp_hit(self):
        """Test outcome_type is set to TP_HIT for SHORT position."""
        position = self._create_mock_position(
            side="short",
            metadata={"take_profit": 49000, "stop_loss": 51000},
        )
        outcome = self.integration._create_outcome_from_position(
            position, realized_pnl=100.0, exit_price=48900.0
        )
        assert outcome.outcome_type == OutcomeType.TP_HIT

    def test_outcome_type_populated_for_short_sl_hit(self):
        """Test outcome_type is set to SL_HIT for SHORT position."""
        position = self._create_mock_position(
            side="short",
            metadata={"take_profit": 49000, "stop_loss": 51000},
        )
        outcome = self.integration._create_outcome_from_position(
            position, realized_pnl=-100.0, exit_price=51100.0
        )
        assert outcome.outcome_type == OutcomeType.SL_HIT

    def test_exit_time_is_populated(self):
        """Test exit_time is set when creating outcome."""
        position = self._create_mock_position()
        outcome = self.integration._create_outcome_from_position(
            position, realized_pnl=100.0, exit_price=51000.0
        )
        assert outcome.exit_time is not None
        assert isinstance(outcome.exit_time, datetime)
        assert outcome.exit_time.tzinfo is not None  # Should be UTC

    def test_fee_is_calculated(self):
        """Test fee is calculated when creating outcome."""
        position = self._create_mock_position(
            entry_price=50000.0,
            quantity=0.1,
            metadata={"fee_rate": 0.001},
        )
        outcome = self.integration._create_outcome_from_position(
            position, realized_pnl=100.0, exit_price=51000.0
        )
        assert outcome.fee is not None
        expected_fee = Decimal("51000.0") * Decimal("0.1") * Decimal("0.001")
        assert outcome.fee == expected_fee

    def test_fee_uses_default_rate_when_not_in_metadata(self):
        """Test fee uses default rate when fee_rate not in metadata."""
        position = self._create_mock_position(
            entry_price=50000.0,
            quantity=0.1,
            metadata={},  # No fee_rate
        )
        outcome = self.integration._create_outcome_from_position(
            position, realized_pnl=100.0, exit_price=51000.0
        )
        assert outcome.fee is not None
        # Default fee rate is 0.001 (0.1%)
        expected_fee = Decimal("51000.0") * Decimal("0.1") * Decimal("0.001")
        assert outcome.fee == expected_fee

    def test_fee_is_none_when_no_exit_price(self):
        """Test fee is None when exit_price is not provided."""
        position = self._create_mock_position(
            entry_price=50000.0,
            quantity=0.1,
            metadata={},
        )
        outcome = self.integration._create_outcome_from_position(
            position, realized_pnl=100.0, exit_price=None
        )
        assert outcome.fee is None

    def test_outcome_fields_basic(self):
        """Test basic outcome fields are correctly populated."""
        position = self._create_mock_position(
            position_id="pos-123",
            symbol="ETH/USDT",
            side="long",
            entry_price=3000.0,
            quantity=1.5,
            metadata={"take_profit": 3300, "stop_loss": 2700},
        )
        outcome = self.integration._create_outcome_from_position(
            position, realized_pnl=150.0, exit_price=3100.0
        )
        assert outcome.order_id == "pos-123"
        assert outcome.symbol == "ETH/USDT"
        assert outcome.side == "Buy"
        assert outcome.direction == "LONG"
        assert outcome.fill_price == Decimal("3000.0")
        assert outcome.fill_quantity == Decimal("1.5")
        assert outcome.entry_price == Decimal("3000.0")
        assert outcome.exit_price == Decimal("3100.0")
        assert outcome.position_size == Decimal("1.5")
        assert outcome.pnl == Decimal("150.0")
        assert outcome.status.value == "closed"

    def test_short_position_side_and_direction(self):
        """Test SHORT position is correctly mapped to Sell side."""
        position = self._create_mock_position(
            side="short",
            metadata={},
        )
        outcome = self.integration._create_outcome_from_position(
            position, realized_pnl=-50.0, exit_price=51000.0
        )
        assert outcome.side == "Sell"
        assert outcome.direction == "SHORT"


class TestOutcomeClassifierEdgeCases:
    """Edge case tests for outcome classification."""

    def setup_method(self):
        """Set up test fixtures."""
        from execution.outcome_capture.integration import OutcomeCaptureIntegration

        self.integration = OutcomeCaptureIntegration()

    def test_classify_very_small_tp_distance_long(self):
        """Test classification when TP is very close to entry for LONG."""
        signal = {"take_profit_price": 50001, "stop_loss_price": 49999}
        # Exit between SL and TP
        result = self.integration._classify_outcome_type(signal, 50000.5, "LONG")
        assert result == OutcomeType.MANUAL_CLOSE

    def test_classify_very_small_sl_distance_short(self):
        """Test classification when SL is very close to entry for SHORT."""
        signal = {"take_profit_price": 49999, "stop_loss_price": 50001}
        # Exit between SL and TP
        result = self.integration._classify_outcome_type(signal, 50000.5, "SHORT")
        assert result == OutcomeType.MANUAL_CLOSE

    def test_classify_with_string_prices(self):
        """Test classification works when prices are strings."""
        signal = {"take_profit_price": "50000", "stop_loss_price": "45000"}
        result = self.integration._classify_outcome_type(signal, 50100, "LONG")
        assert result == OutcomeType.TP_HIT

    def test_outcome_type_unknown_for_position_without_metadata(self):
        """Test outcome_type is MANUAL_CLOSE when position has no metadata."""
        position = MagicMock()
        position.position_id = "test"
        position.symbol = "BTC/USDT"
        position.side = "long"
        position.entry_price = 50000.0
        position.quantity = 0.1
        position.metadata = None  # No metadata

        outcome = self.integration._create_outcome_from_position(
            position, realized_pnl=100.0, exit_price=51000.0
        )
        assert outcome.outcome_type == OutcomeType.MANUAL_CLOSE
