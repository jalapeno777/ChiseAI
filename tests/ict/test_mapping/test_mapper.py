"""
Tests for zone-to-signal mapping module.

Tests cover:
    - Order Block zone to entry signal mapping
    - FVG zone to continuation signal mapping
    - CVD divergence to momentum signal mapping
    - Multiple active zones per token/timeframe
    - Zone invalidation handling
    - Signal resolution performance (<10ms)
"""

import time
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from src.ict.mapping.mapper import (
    ZONE_STATUS_CONFIDENCE_MULTIPLIERS,
    ZoneSignalMapper,
)
from src.ict.mapping.signal_models import (
    ContinuationSignal,
    EntrySignal,
    MomentumSignal,
    SignalDirection,
    SignalResolution,
    ZoneSignalType,
    ZoneToSignalResult,
)
from src.market_analysis.zones.zone_models import (
    PriceRange,
    Zone,
    ZoneStatus,
    ZoneType,
)


# Fixtures
@pytest.fixture
def mock_storage():
    """Create a mock ZoneRedisStorage."""
    storage = MagicMock()
    storage.get_by_token_timeframe.return_value = []
    return storage


@pytest.fixture
def zone_signal_mapper(mock_storage):
    """Create a ZoneSignalMapper with mock storage."""
    mapper = ZoneSignalMapper(zone_storage=mock_storage)
    return mapper


@pytest.fixture
def sample_bullish_ob_zone():
    """Create a sample bullish Order Block zone."""
    return Zone(
        zone_type=ZoneType.OB,
        timeframe="1H",
        token="BTC/USDT",
        price_range=PriceRange(high=50000.0, low=49500.0),
        status=ZoneStatus.ACTIVE,
        uuid=UUID("11111111-1111-1111-1111-111111111111"),
        notes="bullish order block",
    )


@pytest.fixture
def sample_bearish_ob_zone():
    """Create a sample bearish Order Block zone."""
    return Zone(
        zone_type=ZoneType.OB,
        timeframe="1H",
        token="BTC/USDT",
        price_range=PriceRange(high=51000.0, low=50500.0),
        status=ZoneStatus.ACTIVE,
        uuid=UUID("22222222-2222-2222-2222-222222222222"),
        notes="bearish order block",
    )


@pytest.fixture
def sample_bullish_fvg_zone():
    """Create a sample bullish FVG zone."""
    return Zone(
        zone_type=ZoneType.FVG,
        timeframe="1H",
        token="BTC/USDT",
        price_range=PriceRange(high=50200.0, low=50000.0),
        status=ZoneStatus.ACTIVE,
        uuid=UUID("33333333-3333-3333-3333-333333333333"),
        notes="bullish fvg",
    )


@pytest.fixture
def sample_bearish_fvg_zone():
    """Create a sample bearish FVG zone."""
    return Zone(
        zone_type=ZoneType.FVG,
        timeframe="1H",
        token="BTC/USDT",
        price_range=PriceRange(high=50800.0, low=50600.0),
        status=ZoneStatus.ACTIVE,
        uuid=UUID("44444444-4444-4444-4444-444444444444"),
        notes="bearish fvg",
    )


@pytest.fixture
def sample_tested_ob_zone():
    """Create a sample TESTED Order Block zone."""
    return Zone(
        zone_type=ZoneType.OB,
        timeframe="1H",
        token="BTC/USDT",
        price_range=PriceRange(high=50000.0, low=49500.0),
        status=ZoneStatus.TESTED,
        uuid=UUID("55555555-5555-5555-5555-555555555555"),
        notes="tested bullish ob",
    )


@pytest.fixture
def sample_mitigated_fvg_zone():
    """Create a sample MITIGATED FVG zone."""
    return Zone(
        zone_type=ZoneType.FVG,
        timeframe="1H",
        token="BTC/USDT",
        price_range=PriceRange(high=50200.0, low=50000.0),
        status=ZoneStatus.MITIGATED,
        uuid=UUID("66666666-6666-6666-6666-666666666666"),
    )


@pytest.fixture
def sample_invalidated_zone():
    """Create a sample INVALIDATED zone."""
    return Zone(
        zone_type=ZoneType.OB,
        timeframe="1H",
        token="BTC/USDT",
        price_range=PriceRange(high=50000.0, low=49500.0),
        status=ZoneStatus.INVALIDATED,
        uuid=UUID("77777777-7777-7777-7777-777777777777"),
    )


class TestZoneSignalMapper:
    """Tests for ZoneSignalMapper class."""

    def test_mapper_requires_storage(self):
        """Test that mapper requires either zone_manager or zone_storage."""
        with pytest.raises(ValueError, match="Either zone_manager or zone_storage"):
            ZoneSignalMapper()

    def test_mapper_with_storage(self, mock_storage):
        """Test mapper initialization with storage."""
        mapper = ZoneSignalMapper(zone_storage=mock_storage)
        assert mapper._get_storage() is mock_storage

    def test_get_signals_no_zones(self, zone_signal_mapper, mock_storage):
        """Test signal resolution when no zones exist."""
        mock_storage.get_by_token_timeframe.return_value = []
        result = zone_signal_mapper.get_signals(
            token="BTC/USDT",
            timeframe="1H",
            current_price=50000.0,
        )

        assert result.resolution == SignalResolution.NO_ACTIVE_ZONES
        assert result.total_signals == 0
        assert result.zones_processed == 0

    def test_get_signals_all_invalidated(
        self, zone_signal_mapper, mock_storage, sample_invalidated_zone
    ):
        """Test signal resolution when all zones are invalidated."""
        mock_storage.get_by_token_timeframe.return_value = [sample_invalidated_zone]
        result = zone_signal_mapper.get_signals(
            token="BTC/USDT",
            timeframe="1H",
            current_price=50000.0,
        )

        assert result.resolution == SignalResolution.ZONES_INVALIDATED
        assert result.total_signals == 0
        assert result.zones_invalidated == 1

    def test_bullish_ob_zone_generates_long_entry_signal(
        self, zone_signal_mapper, mock_storage, sample_bullish_ob_zone
    ):
        """Test that bullish OB zone generates LONG entry signal."""
        mock_storage.get_by_token_timeframe.return_value = [sample_bullish_ob_zone]

        result = zone_signal_mapper.get_signals(
            token="BTC/USDT",
            timeframe="1H",
            current_price=49750.0,
        )

        assert result.resolution == SignalResolution.SUCCESS
        assert len(result.entry_signals) == 1

        signal = result.entry_signals[0]
        assert signal.signal_type == ZoneSignalType.ENTRY
        assert signal.direction == SignalDirection.LONG
        assert signal.zone_uuid == sample_bullish_ob_zone.uuid
        assert signal.price_high == 50000.0
        assert signal.price_low == 49500.0
        assert signal.zone_status == ZoneStatus.ACTIVE.value

    def test_bearish_ob_zone_generates_short_entry_signal(
        self, zone_signal_mapper, mock_storage, sample_bearish_ob_zone
    ):
        """Test that bearish OB zone generates SHORT entry signal."""
        mock_storage.get_by_token_timeframe.return_value = [sample_bearish_ob_zone]

        result = zone_signal_mapper.get_signals(
            token="BTC/USDT",
            timeframe="1H",
            current_price=50750.0,
        )

        assert result.resolution == SignalResolution.SUCCESS
        assert len(result.entry_signals) == 1

        signal = result.entry_signals[0]
        assert signal.direction == SignalDirection.SHORT
        # zone_polarity is "neutral" when detected from notes (ob_results not provided)
        assert signal.zone_polarity == "neutral"

    def test_bullish_fvg_zone_generates_long_continuation_signal(
        self, zone_signal_mapper, mock_storage, sample_bullish_fvg_zone
    ):
        """Test that bullish FVG zone generates LONG continuation signal."""
        mock_storage.get_by_token_timeframe.return_value = [sample_bullish_fvg_zone]

        result = zone_signal_mapper.get_signals(
            token="BTC/USDT",
            timeframe="1H",
            current_price=49900.0,  # Below the FVG zone
        )

        assert result.resolution == SignalResolution.SUCCESS
        assert len(result.continuation_signals) == 1

        signal = result.continuation_signals[0]
        assert signal.signal_type == ZoneSignalType.CONTINUATION
        assert signal.direction == SignalDirection.LONG
        assert signal.zone_uuid == sample_bullish_fvg_zone.uuid

    def test_bearish_fvg_zone_generates_short_continuation_signal(
        self, zone_signal_mapper, mock_storage, sample_bearish_fvg_zone
    ):
        """Test that bearish FVG zone generates SHORT continuation signal."""
        mock_storage.get_by_token_timeframe.return_value = [sample_bearish_fvg_zone]

        result = zone_signal_mapper.get_signals(
            token="BTC/USDT",
            timeframe="1H",
            current_price=50900.0,  # Above the FVG zone
        )

        assert result.resolution == SignalResolution.SUCCESS
        assert len(result.continuation_signals) == 1

        signal = result.continuation_signals[0]
        assert signal.direction == SignalDirection.SHORT

    def test_tested_zone_has_reduced_confidence(
        self, zone_signal_mapper, mock_storage, sample_tested_ob_zone
    ):
        """Test that TESTED zones have reduced confidence."""
        mock_storage.get_by_token_timeframe.return_value = [sample_tested_ob_zone]

        result = zone_signal_mapper.get_signals(
            token="BTC/USDT",
            timeframe="1H",
            current_price=49750.0,
            include_tested=True,
        )

        assert len(result.entry_signals) == 1
        active_multiplier = ZONE_STATUS_CONFIDENCE_MULTIPLIERS[ZoneStatus.ACTIVE]
        tested_multiplier = ZONE_STATUS_CONFIDENCE_MULTIPLIERS[ZoneStatus.TESTED]
        assert tested_multiplier < active_multiplier

    def test_mitigated_zone_no_signal(
        self, zone_signal_mapper, mock_storage, sample_mitigated_fvg_zone
    ):
        """Test that MITIGATED zones don't generate signals."""
        mock_storage.get_by_token_timeframe.return_value = [sample_mitigated_fvg_zone]

        result = zone_signal_mapper.get_signals(
            token="BTC/USDT",
            timeframe="1H",
            current_price=49900.0,
        )

        # MITIGATED zones result in ZONES_INVALIDATED resolution (no active zones)
        assert result.resolution == SignalResolution.ZONES_INVALIDATED
        assert len(result.continuation_signals) == 0
        assert result.zones_mitigated == 1

    def test_invalidated_zone_no_signal(
        self, zone_signal_mapper, mock_storage, sample_invalidated_zone
    ):
        """Test that INVALIDATED zones don't generate signals."""
        mock_storage.get_by_token_timeframe.return_value = [sample_invalidated_zone]

        result = zone_signal_mapper.get_signals(
            token="BTC/USDT",
            timeframe="1H",
            current_price=49750.0,
        )

        assert len(result.entry_signals) == 0
        assert result.zones_invalidated == 1

    def test_multiple_zones_same_token_timeframe(
        self,
        zone_signal_mapper,
        mock_storage,
        sample_bullish_ob_zone,
        sample_bullish_fvg_zone,
        sample_bearish_fvg_zone,
    ):
        """Test handling of multiple zones for same token/timeframe."""
        mock_storage.get_by_token_timeframe.return_value = [
            sample_bullish_ob_zone,
            sample_bullish_fvg_zone,
            sample_bearish_fvg_zone,
        ]

        result = zone_signal_mapper.get_signals(
            token="BTC/USDT",
            timeframe="1H",
            current_price=50100.0,
        )

        assert result.resolution == SignalResolution.SUCCESS
        assert len(result.entry_signals) == 1  # Only the bullish OB
        assert len(result.continuation_signals) == 2  # Both FVGs
        assert result.zones_processed == 3

    def test_zone_to_signal_resolution_within_10ms(
        self, zone_signal_mapper, mock_storage, sample_bullish_ob_zone
    ):
        """Test that zone-to-signal resolution completes within 10ms."""
        mock_storage.get_by_token_timeframe.return_value = [sample_bullish_ob_zone]

        start_time = time.perf_counter()
        result = zone_signal_mapper.get_signals(
            token="BTC/USDT",
            timeframe="1H",
            current_price=49750.0,
        )
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        assert result.resolution_time_ms < 10.0, f"Resolution took {elapsed_ms:.2f}ms"
        assert elapsed_ms < 10.0, f"Actual wall time: {elapsed_ms:.2f}ms"

    def test_ob_signals_can_be_disabled(
        self, zone_signal_mapper, mock_storage, sample_bullish_ob_zone
    ):
        """Test that OB signals can be disabled."""
        zone_signal_mapper.enable_ob_signals = False
        mock_storage.get_by_token_timeframe.return_value = [sample_bullish_ob_zone]

        result = zone_signal_mapper.get_signals(
            token="BTC/USDT",
            timeframe="1H",
            current_price=49750.0,
        )

        assert len(result.entry_signals) == 0
        assert len(result.continuation_signals) == 0

    def test_fvg_signals_can_be_disabled(
        self, zone_signal_mapper, mock_storage, sample_bullish_fvg_zone
    ):
        """Test that FVG signals can be disabled."""
        zone_signal_mapper.enable_fvg_signals = False
        mock_storage.get_by_token_timeframe.return_value = [sample_bullish_fvg_zone]

        result = zone_signal_mapper.get_signals(
            token="BTC/USDT",
            timeframe="1H",
            current_price=49900.0,
        )

        assert len(result.continuation_signals) == 0
        assert len(result.entry_signals) == 0


class TestEntrySignal:
    """Tests for EntrySignal model."""

    def test_entry_signal_creation(self, sample_bullish_ob_zone):
        """Test EntrySignal creation with all fields."""
        signal = EntrySignal(
            direction=SignalDirection.LONG,
            zone_uuid=sample_bullish_ob_zone.uuid,
            zone_type=sample_bullish_ob_zone.zone_type.value,
            token="BTC/USDT",
            timeframe="1H",
            price_high=50000.0,
            price_low=49500.0,
            confidence=0.75,
            zone_status="ACTIVE",
            zone_polarity="bullish",
            optimal_entry_price=49750.0,
            stop_loss=49450.0,
            risk_reward_ratio=2.0,
        )

        assert signal.signal_type == ZoneSignalType.ENTRY
        assert signal.direction == SignalDirection.LONG
        assert signal.zone_polarity == "bullish"
        assert signal.optimal_entry_price == 49750.0

    def test_entry_signal_to_dict(self, sample_bullish_ob_zone):
        """Test EntrySignal serialization to dict."""
        signal = EntrySignal(
            direction=SignalDirection.LONG,
            zone_uuid=sample_bullish_ob_zone.uuid,
            zone_type="OB",
            token="BTC/USDT",
            timeframe="1H",
            price_high=50000.0,
            price_low=49500.0,
            confidence=0.75,
            zone_status="ACTIVE",
        )

        data = signal.to_dict()
        assert data["signal_type"] == "entry"
        assert data["direction"] == "long"
        assert data["price_high"] == 50000.0


class TestContinuationSignal:
    """Tests for ContinuationSignal model."""

    def test_continuation_signal_creation(self, sample_bullish_fvg_zone):
        """Test ContinuationSignal creation with all fields."""
        signal = ContinuationSignal(
            direction=SignalDirection.LONG,
            zone_uuid=sample_bullish_fvg_zone.uuid,
            zone_type="FVG",
            token="BTC/USDT",
            timeframe="1H",
            price_high=50200.0,
            price_low=50000.0,
            confidence=0.80,
            zone_status="ACTIVE",
            fvg_direction="bullish",
            mitigation_status="none",
            midpoint=50100.0,
            zone_size=200.0,
        )

        assert signal.signal_type == ZoneSignalType.CONTINUATION
        assert signal.fvg_direction == "bullish"
        assert signal.mitigation_status == "none"

    def test_continuation_signal_to_dict(self, sample_bullish_fvg_zone):
        """Test ContinuationSignal serialization to dict."""
        signal = ContinuationSignal(
            direction=SignalDirection.LONG,
            zone_uuid=sample_bullish_fvg_zone.uuid,
            zone_type="FVG",
            token="BTC/USDT",
            timeframe="1H",
            price_high=50200.0,
            price_low=50000.0,
            confidence=0.80,
            zone_status="ACTIVE",
            midpoint=50100.0,
            zone_size=200.0,
        )

        data = signal.to_dict()
        assert data["signal_type"] == "continuation"
        assert data["midpoint"] == 50100.0
        assert data["zone_size"] == 200.0


class TestMomentumSignal:
    """Tests for MomentumSignal model."""

    def test_momentum_signal_creation(self):
        """Test MomentumSignal creation with all fields."""
        signal = MomentumSignal(
            direction=SignalDirection.LONG,
            zone_uuid=uuid4(),
            zone_type="CVD",
            token="BTC/USDT",
            timeframe="1H",
            price_high=50100.0,
            price_low=49900.0,
            confidence=0.70,
            zone_status="ACTIVE",
            cvd_direction="bullish",
            divergence_strength=0.75,
            threshold=0.5,
            price_at_formation=50000.0,
        )

        assert signal.signal_type == ZoneSignalType.MOMENTUM
        assert signal.cvd_direction == "bullish"
        assert signal.divergence_strength == 0.75

    def test_momentum_signal_to_dict(self):
        """Test MomentumSignal serialization to dict."""
        zone_uuid = uuid4()
        signal = MomentumSignal(
            direction=SignalDirection.LONG,
            zone_uuid=zone_uuid,
            zone_type="CVD",
            token="BTC/USDT",
            timeframe="1H",
            price_high=50100.0,
            price_low=49900.0,
            confidence=0.70,
            zone_status="ACTIVE",
            cvd_direction="bullish",
            divergence_strength=0.75,
        )

        data = signal.to_dict()
        assert data["signal_type"] == "momentum"
        assert data["cvd_direction"] == "bullish"


class TestZoneToSignalResult:
    """Tests for ZoneToSignalResult model."""

    def test_result_total_signals(self):
        """Test total signal count calculation."""
        result = ZoneToSignalResult()
        result.entry_signals.append(EntrySignal(direction=SignalDirection.LONG))
        result.continuation_signals.append(
            ContinuationSignal(direction=SignalDirection.SHORT)
        )
        result.momentum_signals.append(MomentumSignal(direction=SignalDirection.LONG))

        assert result.total_signals == 3

    def test_result_all_signals(self):
        """Test all_signals property combines all signal types."""
        result = ZoneToSignalResult()
        entry = EntrySignal(direction=SignalDirection.LONG)
        continuation = ContinuationSignal(direction=SignalDirection.SHORT)
        momentum = MomentumSignal(direction=SignalDirection.LONG)

        result.entry_signals.append(entry)
        result.continuation_signals.append(continuation)
        result.momentum_signals.append(momentum)

        all_signals = result.all_signals
        assert len(all_signals) == 3
        assert entry in all_signals
        assert continuation in all_signals
        assert momentum in all_signals

    def test_result_to_dict(self):
        """Test ZoneToSignalResult serialization."""
        result = ZoneToSignalResult()
        result.resolution = SignalResolution.SUCCESS
        result.zones_processed = 5
        result.zones_active = 3
        result.zones_tested = 1
        result.zones_mitigated = 1

        data = result.to_dict()
        assert data["resolution"] == "success"
        assert data["zones_processed"] == 5
        assert data["zones_active"] == 3


class TestZoneProximity:
    """Tests for zone proximity calculations."""

    def test_price_in_zone(self, zone_signal_mapper, sample_bullish_ob_zone):
        """Test proximity when price is within zone."""
        proximity = zone_signal_mapper.get_zone_proximity(
            sample_bullish_ob_zone, current_price=49750.0
        )
        assert proximity == 0.0

    def test_price_below_zone(self, zone_signal_mapper, sample_bullish_ob_zone):
        """Test proximity when price is below zone."""
        proximity = zone_signal_mapper.get_zone_proximity(
            sample_bullish_ob_zone, current_price=49000.0
        )
        assert 0.0 < proximity <= 1.0

    def test_price_above_zone(self, zone_signal_mapper, sample_bullish_ob_zone):
        """Test proximity when price is above zone."""
        proximity = zone_signal_mapper.get_zone_proximity(
            sample_bullish_ob_zone, current_price=51000.0
        )
        assert 0.0 < proximity <= 1.0


class TestConfidenceMultipliers:
    """Tests for zone status confidence multipliers."""

    def test_active_multiplier_is_one(self):
        """Test that ACTIVE zones have 1.0 confidence multiplier."""
        assert ZONE_STATUS_CONFIDENCE_MULTIPLIERS[ZoneStatus.ACTIVE] == 1.0

    def test_tested_multiplier_less_than_active(self):
        """Test that TESTED zones have reduced confidence."""
        active = ZONE_STATUS_CONFIDENCE_MULTIPLIERS[ZoneStatus.ACTIVE]
        tested = ZONE_STATUS_CONFIDENCE_MULTIPLIERS[ZoneStatus.TESTED]
        assert tested < active

    def test_mitigated_multiplier_is_zero(self):
        """Test that MITIGATED zones have 0.0 confidence multiplier."""
        assert ZONE_STATUS_CONFIDENCE_MULTIPLIERS[ZoneStatus.MITIGATED] == 0.0

    def test_invalidated_multiplier_is_zero(self):
        """Test that INVALIDATED zones have 0.0 confidence multiplier."""
        assert ZONE_STATUS_CONFIDENCE_MULTIPLIERS[ZoneStatus.INVALIDATED] == 0.0


class TestZoneInvalidation:
    """Tests for zone invalidation handling."""

    def test_invalidate_zone_signals(self, zone_signal_mapper):
        """Test signal invalidation for a zone."""
        result = zone_signal_mapper.invalidate_zone_signals(
            UUID("11111111-1111-1111-1111-111111111111")
        )
        assert result is True

    def test_include_tested_false(
        self, zone_signal_mapper, mock_storage, sample_tested_ob_zone
    ):
        """Test that TESTED zones are excluded when include_tested=False."""
        mock_storage.get_by_token_timeframe.return_value = [sample_tested_ob_zone]

        result = zone_signal_mapper.get_signals(
            token="BTC/USDT",
            timeframe="1H",
            current_price=49750.0,
            include_tested=False,
        )

        assert len(result.entry_signals) == 0


class TestSignalDirectionDetection:
    """Tests for signal direction detection from zone characteristics."""

    def test_direction_from_notes_bullish(self, zone_signal_mapper, mock_storage):
        """Test direction detection from zone notes containing 'bullish'."""
        zone = Zone(
            zone_type=ZoneType.OB,
            timeframe="1H",
            token="BTC/USDT",
            price_range=PriceRange(high=50000.0, low=49500.0),
            status=ZoneStatus.ACTIVE,
            notes="institutional bullish order block",
        )
        mock_storage.get_by_token_timeframe.return_value = [zone]

        result = zone_signal_mapper.get_signals(
            token="BTC/USDT",
            timeframe="1H",
            current_price=49750.0,
        )

        assert result.entry_signals[0].direction == SignalDirection.LONG

    def test_direction_from_notes_bearish(self, zone_signal_mapper, mock_storage):
        """Test direction detection from zone notes containing 'bearish'."""
        zone = Zone(
            zone_type=ZoneType.OB,
            timeframe="1H",
            token="BTC/USDT",
            price_range=PriceRange(high=51000.0, low=50500.0),
            status=ZoneStatus.ACTIVE,
            notes="bearish supply zone",
        )
        mock_storage.get_by_token_timeframe.return_value = [zone]

        result = zone_signal_mapper.get_signals(
            token="BTC/USDT",
            timeframe="1H",
            current_price=50750.0,
        )

        assert result.entry_signals[0].direction == SignalDirection.SHORT
