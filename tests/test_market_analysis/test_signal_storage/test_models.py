"""Tests for signal storage data models."""

from market_analysis.signal_storage.models import (
    OutcomeRecord,
    OutcomeType,
    SignalDirection,
    SignalRecord,
    SignalWithOutcome,
)


class TestSignalDirection:
    """Tests for SignalDirection enum."""

    def test_direction_values(self):
        """Test direction enum values."""
        assert SignalDirection.LONG.value == "LONG"
        assert SignalDirection.SHORT.value == "SHORT"
        assert SignalDirection.NEUTRAL.value == "NEUTRAL"

    def test_direction_str(self):
        """Test direction string representation."""
        assert str(SignalDirection.LONG) == "LONG"
        assert str(SignalDirection.SHORT) == "SHORT"
        assert str(SignalDirection.NEUTRAL) == "NEUTRAL"


class TestOutcomeType:
    """Tests for OutcomeType enum."""

    def test_outcome_type_values(self):
        """Test outcome type enum values."""
        assert OutcomeType.TP_HIT.value == "tp_hit"
        assert OutcomeType.SL_HIT.value == "sl_hit"
        assert OutcomeType.MANUAL_CLOSE.value == "manual_close"
        assert OutcomeType.TIMEOUT.value == "timeout"
        assert OutcomeType.UNKNOWN.value == "unknown"


class TestSignalRecord:
    """Tests for SignalRecord dataclass."""

    def test_basic_creation(self):
        """Test basic signal record creation."""
        signal = SignalRecord(
            signal_id="test-uuid-123",
            token="BTC",
            timestamp=1234567890000,
            direction=SignalDirection.LONG,
            confidence=0.75,
            entry_price=50000.0,
            score=75.0,
            indicators_used=["rsi", "macd"],
            timeframes_used=["1h", "4h"],
        )

        assert signal.signal_id == "test-uuid-123"
        assert signal.token == "BTC"
        assert signal.timestamp == 1234567890000
        assert signal.direction == SignalDirection.LONG
        assert signal.confidence == 0.75
        assert signal.entry_price == 50000.0
        assert signal.score == 75.0
        assert signal.indicators_used == ["rsi", "macd"]
        assert signal.timeframes_used == ["1h", "4h"]

    def test_confidence_normalization(self):
        """Test confidence is normalized to 0-1 range."""
        signal_high = SignalRecord(
            signal_id="test-1",
            token="BTC",
            timestamp=1234567890000,
            direction=SignalDirection.LONG,
            confidence=1.5,  # Above 1
            entry_price=50000.0,
            score=75.0,
        )
        assert signal_high.confidence == 1.0

        signal_low = SignalRecord(
            signal_id="test-2",
            token="BTC",
            timestamp=1234567890000,
            direction=SignalDirection.LONG,
            confidence=-0.5,  # Below 0
            entry_price=50000.0,
            score=75.0,
        )
        assert signal_low.confidence == 0.0

    def test_score_normalization(self):
        """Test score is normalized to 0-100 range."""
        signal_high = SignalRecord(
            signal_id="test-1",
            token="BTC",
            timestamp=1234567890000,
            direction=SignalDirection.LONG,
            confidence=0.5,
            entry_price=50000.0,
            score=150.0,  # Above 100
        )
        assert signal_high.score == 100.0

        signal_low = SignalRecord(
            signal_id="test-2",
            token="BTC",
            timestamp=1234567890000,
            direction=SignalDirection.LONG,
            confidence=0.5,
            entry_price=50000.0,
            score=-10.0,  # Below 0
        )
        assert signal_low.score == 0.0

    def test_confidence_bucket(self):
        """Test confidence bucket calculation."""
        signal_75 = SignalRecord(
            signal_id="test-1",
            token="BTC",
            timestamp=1234567890000,
            direction=SignalDirection.LONG,
            confidence=0.75,
            entry_price=50000.0,
            score=75.0,
        )
        assert signal_75.confidence_bucket == "70-80"

        signal_45 = SignalRecord(
            signal_id="test-2",
            token="BTC",
            timestamp=1234567890000,
            direction=SignalDirection.LONG,
            confidence=0.45,
            entry_price=50000.0,
            score=75.0,
        )
        assert signal_45.confidence_bucket == "40-50"

    def test_signal_type(self):
        """Test signal type generation."""
        signal = SignalRecord(
            signal_id="test-1",
            token="BTC",
            timestamp=1234567890000,
            direction=SignalDirection.LONG,
            confidence=0.75,
            entry_price=50000.0,
            score=75.0,
            indicators_used=["rsi", "macd", "bb"],
        )
        assert signal.signal_type == "LONG_bb_macd_rsi"

    def test_to_dict(self):
        """Test conversion to dictionary."""
        signal = SignalRecord(
            signal_id="test-uuid",
            token="BTC",
            timestamp=1234567890000,
            direction=SignalDirection.LONG,
            confidence=0.75,
            entry_price=50000.0,
            score=75.0,
            indicators_used=["rsi"],
            timeframes_used=["1h"],
        )

        data = signal.to_dict()
        assert data["signal_id"] == "test-uuid"
        assert data["token"] == "BTC"
        assert data["direction"] == "LONG"
        assert data["confidence"] == 0.75
        assert data["confidence_bucket"] == "70-80"

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "signal_id": "test-uuid",
            "token": "BTC",
            "timestamp": 1234567890000,
            "direction": "LONG",
            "confidence": 0.75,
            "entry_price": 50000.0,
            "score": 75.0,
            "indicators_used": ["rsi"],
            "timeframes_used": ["1h"],
        }

        signal = SignalRecord.from_dict(data)
        assert signal.signal_id == "test-uuid"
        assert signal.direction == SignalDirection.LONG
        assert signal.confidence == 0.75


class TestOutcomeRecord:
    """Tests for OutcomeRecord dataclass."""

    def test_basic_creation(self):
        """Test basic outcome record creation."""
        outcome = OutcomeRecord(
            signal_id="test-uuid-123",
            exit_timestamp=1234567950000,
            is_win=True,
            pnl=100.0,
            exit_price=50100.0,
            duration_hours=1.5,
            outcome_type=OutcomeType.TP_HIT,
            note="Take profit hit",
        )

        assert outcome.signal_id == "test-uuid-123"
        assert outcome.exit_timestamp == 1234567950000
        assert outcome.is_win is True
        assert outcome.pnl == 100.0
        assert outcome.exit_price == 50100.0
        assert outcome.duration_hours == 1.5
        assert outcome.outcome_type == OutcomeType.TP_HIT
        assert outcome.note == "Take profit hit"

    def test_is_win_normalization_from_pnl(self):
        """Test is_win is normalized from PnL."""
        outcome_positive = OutcomeRecord(
            signal_id="test-1",
            exit_timestamp=1234567950000,
            is_win=False,  # Wrong value
            pnl=100.0,  # Positive PnL
            exit_price=50100.0,
            duration_hours=1.0,
        )
        assert outcome_positive.is_win is True

        outcome_negative = OutcomeRecord(
            signal_id="test-2",
            exit_timestamp=1234567950000,
            is_win=True,  # Wrong value
            pnl=-50.0,  # Negative PnL
            exit_price=49950.0,
            duration_hours=1.0,
        )
        assert outcome_negative.is_win is False

    def test_outcome_type_from_string(self):
        """Test outcome type from string."""
        outcome = OutcomeRecord(
            signal_id="test-1",
            exit_timestamp=1234567950000,
            is_win=True,
            pnl=100.0,
            exit_price=50100.0,
            duration_hours=1.0,
            outcome_type="tp_hit",  # String instead of enum
        )
        assert outcome.outcome_type == OutcomeType.TP_HIT

    def test_invalid_outcome_type_defaults_to_unknown(self):
        """Test invalid outcome type defaults to UNKNOWN."""
        outcome = OutcomeRecord(
            signal_id="test-1",
            exit_timestamp=1234567950000,
            is_win=True,
            pnl=100.0,
            exit_price=50100.0,
            duration_hours=1.0,
            outcome_type="invalid_type",
        )
        assert outcome.outcome_type == OutcomeType.UNKNOWN

    def test_to_dict(self):
        """Test conversion to dictionary."""
        outcome = OutcomeRecord(
            signal_id="test-uuid",
            exit_timestamp=1234567950000,
            is_win=True,
            pnl=100.0,
            exit_price=50100.0,
            duration_hours=1.5,
            outcome_type=OutcomeType.TP_HIT,
        )

        data = outcome.to_dict()
        assert data["signal_id"] == "test-uuid"
        assert data["is_win"] is True
        assert data["pnl"] == 100.0
        assert data["outcome_type"] == "tp_hit"

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "signal_id": "test-uuid",
            "exit_timestamp": 1234567950000,
            "is_win": True,
            "pnl": 100.0,
            "exit_price": 50100.0,
            "duration_hours": 1.5,
            "outcome_type": "tp_hit",
            "note": "Test note",
        }

        outcome = OutcomeRecord.from_dict(data)
        assert outcome.signal_id == "test-uuid"
        assert outcome.is_win is True
        assert outcome.outcome_type == OutcomeType.TP_HIT


class TestSignalWithOutcome:
    """Tests for SignalWithOutcome dataclass."""

    def test_creation_with_outcome(self):
        """Test creation with both signal and outcome."""
        signal = SignalRecord(
            signal_id="test-uuid",
            token="BTC",
            timestamp=1234567890000,
            direction=SignalDirection.LONG,
            confidence=0.75,
            entry_price=50000.0,
            score=75.0,
        )

        outcome = OutcomeRecord(
            signal_id="test-uuid",
            exit_timestamp=1234567950000,
            is_win=True,
            pnl=100.0,
            exit_price=50100.0,
            duration_hours=1.0,
        )

        swo = SignalWithOutcome(signal=signal, outcome=outcome)

        assert swo.is_resolved is True
        assert swo.is_win is True
        assert swo.pnl == 100.0

    def test_creation_without_outcome(self):
        """Test creation with signal only."""
        signal = SignalRecord(
            signal_id="test-uuid",
            token="BTC",
            timestamp=1234567890000,
            direction=SignalDirection.LONG,
            confidence=0.75,
            entry_price=50000.0,
            score=75.0,
        )

        swo = SignalWithOutcome(signal=signal, outcome=None)

        assert swo.is_resolved is False
        assert swo.is_win is None
        assert swo.pnl is None

    def test_to_dict(self):
        """Test conversion to dictionary."""
        signal = SignalRecord(
            signal_id="test-uuid",
            token="BTC",
            timestamp=1234567890000,
            direction=SignalDirection.LONG,
            confidence=0.75,
            entry_price=50000.0,
            score=75.0,
        )

        outcome = OutcomeRecord(
            signal_id="test-uuid",
            exit_timestamp=1234567950000,
            is_win=True,
            pnl=100.0,
            exit_price=50100.0,
            duration_hours=1.0,
        )

        swo = SignalWithOutcome(signal=signal, outcome=outcome)
        data = swo.to_dict()

        assert data["is_resolved"] is True
        assert data["is_win"] is True
        assert data["pnl"] == 100.0
        assert data["signal"]["signal_id"] == "test-uuid"
