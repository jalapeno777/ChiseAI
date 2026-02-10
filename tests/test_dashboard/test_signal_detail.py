"""Tests for signal detail breakdown module."""

from __future__ import annotations

from datetime import UTC, datetime

from dashboard.key_levels import KeyLevel, KeyLevelsResult, LevelType
from dashboard.signal_detail import (
    ConfidenceMultiplierInfo,
    ConfluenceBreakdown,
    IndicatorContribution,
    PositionSizeInfo,
    RiskRewardInfo,
    SignalDetail,
    SignalDetailBuilder,
    StopLossInfo,
    TimeframeAgreement,
)
from signal_generation.models import Signal, SignalDirection, SignalStatus


class TestIndicatorContribution:
    """Tests for IndicatorContribution dataclass."""

    def test_indicator_contribution_creation(self) -> None:
        """Test creating IndicatorContribution."""
        contrib = IndicatorContribution(
            indicator_type="rsi",
            timeframe="1h",
            direction="long",
            strength=0.8,
            confidence=0.75,
            weight=1.0,
            weighted_score=0.6,
            raw_value=65.5,
        )

        assert contrib.indicator_type == "rsi"
        assert contrib.timeframe == "1h"
        assert contrib.direction == "long"
        assert contrib.strength == 0.8
        assert contrib.raw_value == 65.5

    def test_indicator_contribution_normalization(self) -> None:
        """Test value normalization."""
        contrib = IndicatorContribution(
            indicator_type="macd",
            timeframe="4h",
            direction="short",
            strength=1.5,  # Should clamp to 1.0
            confidence=-0.2,  # Should clamp to 0.0
            weight=-1.0,  # Should clamp to 0.0
            weighted_score=-0.5,  # Should clamp to 0.0
        )

        assert contrib.strength == 1.0
        assert contrib.confidence == 0.0
        assert contrib.weight == 0.0
        assert contrib.weighted_score == 0.0

    def test_to_dict(self) -> None:
        """Test serialization."""
        contrib = IndicatorContribution(
            indicator_type="bb",
            timeframe="1d",
            direction="long",
            strength=0.7,
            confidence=0.8,
            weight=1.2,
            weighted_score=0.56,
            raw_value=42.0,
        )

        d = contrib.to_dict()

        assert d["indicator_type"] == "bb"
        assert d["timeframe"] == "1d"
        assert d["strength"] == 0.7
        assert d["raw_value"] == 42.0


class TestTimeframeAgreement:
    """Tests for TimeframeAgreement dataclass."""

    def test_timeframe_agreement_creation(self) -> None:
        """Test creating TimeframeAgreement."""
        agreement = TimeframeAgreement(
            timeframe="1h",
            dominant_direction="long",
            long_weight=2.5,
            short_weight=0.5,
            neutral_weight=0.0,
            signal_count=3,
            agrees_with_overall=True,
        )

        assert agreement.timeframe == "1h"
        assert agreement.dominant_direction == "long"
        assert agreement.agrees_with_overall is True

    def test_total_weight(self) -> None:
        """Test total weight calculation."""
        agreement = TimeframeAgreement(
            timeframe="4h",
            dominant_direction="short",
            long_weight=1.0,
            short_weight=3.0,
            neutral_weight=0.5,
            signal_count=4,
            agrees_with_overall=False,
        )

        assert agreement.total_weight == 4.5

    def test_agreement_ratio(self) -> None:
        """Test agreement ratio calculation."""
        agreement = TimeframeAgreement(
            timeframe="1d",
            dominant_direction="long",
            long_weight=3.0,
            short_weight=1.0,
            neutral_weight=1.0,
            signal_count=5,
            agrees_with_overall=True,
        )

        # Long ratio = 3/5 = 0.6
        assert agreement.agreement_ratio == 0.6

    def test_agreement_ratio_zero_total(self) -> None:
        """Test agreement ratio with zero total weight."""
        agreement = TimeframeAgreement(
            timeframe="1m",
            dominant_direction="neutral",
            long_weight=0.0,
            short_weight=0.0,
            neutral_weight=0.0,
            signal_count=0,
            agrees_with_overall=True,
        )

        assert agreement.agreement_ratio == 0.0

    def test_to_dict(self) -> None:
        """Test serialization."""
        agreement = TimeframeAgreement(
            timeframe="1h",
            dominant_direction="long",
            long_weight=2.0,
            short_weight=0.5,
            neutral_weight=0.5,
            signal_count=3,
            agrees_with_overall=True,
        )

        d = agreement.to_dict()

        assert d["timeframe"] == "1h"
        assert d["dominant_direction"] == "long"
        assert d["agrees_with_overall"] is True
        assert "total_weight" in d


class TestConfluenceBreakdown:
    """Tests for ConfluenceBreakdown dataclass."""

    def test_confluence_breakdown_creation(self) -> None:
        """Test creating ConfluenceBreakdown."""
        breakdown = ConfluenceBreakdown(
            base_score=75.0,
            agreement_ratio=0.8,
            avg_strength=0.7,
            avg_confidence=0.75,
            diversity_bonus=0.08,
            type_bonus=0.05,
        )

        assert breakdown.base_score == 75.0
        assert breakdown.agreement_ratio == 0.8

    def test_confluence_breakdown_normalization(self) -> None:
        """Test value normalization."""
        breakdown = ConfluenceBreakdown(
            base_score=150.0,  # Should clamp to 100
            agreement_ratio=-0.5,  # Should clamp to 0
            avg_strength=2.0,  # Should clamp to 1.0
            avg_confidence=-0.1,  # Should clamp to 0
            diversity_bonus=0.2,  # Should clamp to 0.1
            type_bonus=-0.05,  # Should clamp to 0
        )

        assert breakdown.base_score == 100.0
        assert breakdown.agreement_ratio == 0.0
        assert breakdown.avg_strength == 1.0
        assert breakdown.avg_confidence == 0.0
        assert breakdown.diversity_bonus == 0.1
        assert breakdown.type_bonus == 0.0

    def test_total_contributing_indicators(self) -> None:
        """Test indicator count."""
        contributions = [
            IndicatorContribution(
                indicator_type="rsi",
                timeframe="1h",
                direction="long",
                strength=0.8,
                confidence=0.75,
                weight=1.0,
                weighted_score=0.6,
            ),
            IndicatorContribution(
                indicator_type="macd",
                timeframe="1h",
                direction="long",
                strength=0.7,
                confidence=0.8,
                weight=1.0,
                weighted_score=0.56,
            ),
        ]

        breakdown = ConfluenceBreakdown(
            base_score=70.0,
            agreement_ratio=0.75,
            avg_strength=0.75,
            avg_confidence=0.775,
            diversity_bonus=0.04,
            type_bonus=0.05,
            indicator_contributions=contributions,
        )

        assert breakdown.total_contributing_indicators == 2

    def test_unique_timeframes(self) -> None:
        """Test unique timeframes extraction."""
        agreements = [
            TimeframeAgreement(
                timeframe="1h",
                dominant_direction="long",
                long_weight=2.0,
                short_weight=0.0,
                neutral_weight=0.0,
                signal_count=2,
                agrees_with_overall=True,
            ),
            TimeframeAgreement(
                timeframe="4h",
                dominant_direction="long",
                long_weight=1.5,
                short_weight=0.5,
                neutral_weight=0.0,
                signal_count=2,
                agrees_with_overall=True,
            ),
        ]

        breakdown = ConfluenceBreakdown(
            base_score=70.0,
            agreement_ratio=0.75,
            avg_strength=0.75,
            avg_confidence=0.775,
            diversity_bonus=0.04,
            type_bonus=0.05,
            timeframe_agreements=agreements,
        )

        assert set(breakdown.unique_timeframes) == {"1h", "4h"}

    def test_unique_indicator_types(self) -> None:
        """Test unique indicator types extraction."""
        contributions = [
            IndicatorContribution(
                indicator_type="rsi",
                timeframe="1h",
                direction="long",
                strength=0.8,
                confidence=0.75,
                weight=1.0,
                weighted_score=0.6,
            ),
            IndicatorContribution(
                indicator_type="macd",
                timeframe="1h",
                direction="long",
                strength=0.7,
                confidence=0.8,
                weight=1.0,
                weighted_score=0.56,
            ),
            IndicatorContribution(
                indicator_type="rsi",  # Duplicate type
                timeframe="4h",
                direction="long",
                strength=0.75,
                confidence=0.7,
                weight=1.2,
                weighted_score=0.63,
            ),
        ]

        breakdown = ConfluenceBreakdown(
            base_score=70.0,
            agreement_ratio=0.75,
            avg_strength=0.75,
            avg_confidence=0.775,
            diversity_bonus=0.04,
            type_bonus=0.05,
            indicator_contributions=contributions,
        )

        assert set(breakdown.unique_indicator_types) == {"rsi", "macd"}

    def test_to_dict(self) -> None:
        """Test serialization."""
        breakdown = ConfluenceBreakdown(
            base_score=80.0,
            agreement_ratio=0.85,
            avg_strength=0.8,
            avg_confidence=0.82,
            diversity_bonus=0.06,
            type_bonus=0.05,
        )

        d = breakdown.to_dict()

        assert d["base_score"] == 80.0
        assert d["agreement_ratio"] == 0.85
        assert d["total_contributing_indicators"] == 0


class TestConfidenceMultiplierInfo:
    """Tests for ConfidenceMultiplierInfo dataclass."""

    def test_confidence_multiplier_creation(self) -> None:
        """Test creating ConfidenceMultiplierInfo."""
        info = ConfidenceMultiplierInfo(
            multiplier=1.2,
            rationale="2 timeframes agreeing",
            base_confidence=0.75,
            final_confidence=0.90,
            agreeing_timeframes=2,
            conflicting_timeframes=0,
        )

        assert info.multiplier == 1.2
        assert info.agreeing_timeframes == 2

    def test_confidence_multiplier_normalization(self) -> None:
        """Test value normalization."""
        info = ConfidenceMultiplierInfo(
            multiplier=2.0,  # Should clamp to 1.5
            rationale="Test",
            base_confidence=-0.1,  # Should clamp to 0
            final_confidence=1.5,  # Should clamp to 1.0
            agreeing_timeframes=-1,  # Should clamp to 0
            conflicting_timeframes=-2,  # Should clamp to 0
        )

        assert info.multiplier == 1.5
        assert info.base_confidence == 0.0
        assert info.final_confidence == 1.0
        assert info.agreeing_timeframes == 0
        assert info.conflicting_timeframes == 0

    def test_was_applied(self) -> None:
        """Test multiplier applied check."""
        applied = ConfidenceMultiplierInfo(
            multiplier=1.2,
            rationale="Applied",
            base_confidence=0.7,
            final_confidence=0.84,
            agreeing_timeframes=2,
            conflicting_timeframes=0,
        )
        not_applied = ConfidenceMultiplierInfo(
            multiplier=1.0,
            rationale="Not applied",
            base_confidence=0.5,
            final_confidence=0.5,
            agreeing_timeframes=1,
            conflicting_timeframes=0,
        )

        assert applied.was_applied is True
        assert not_applied.was_applied is False

    def test_confidence_boost_percent(self) -> None:
        """Test confidence boost calculation."""
        info = ConfidenceMultiplierInfo(
            multiplier=1.3,
            rationale="Applied",
            base_confidence=0.7,
            final_confidence=0.91,
            agreeing_timeframes=3,
            conflicting_timeframes=0,
        )

        assert abs(info.confidence_boost_percent - 30.0) < 0.001

    def test_to_dict(self) -> None:
        """Test serialization."""
        info = ConfidenceMultiplierInfo(
            multiplier=1.2,
            rationale="2 timeframes agreeing",
            base_confidence=0.75,
            final_confidence=0.90,
            agreeing_timeframes=2,
            conflicting_timeframes=0,
        )

        d = info.to_dict()

        assert d["multiplier"] == 1.2
        assert d["was_applied"] is True
        assert d["confidence_boost_percent"] == 20.0


class TestStopLossInfo:
    """Tests for StopLossInfo dataclass."""

    def test_stop_loss_creation(self) -> None:
        """Test creating StopLossInfo."""
        info = StopLossInfo(
            stop_loss_price=45000.0,
            stop_loss_percent=2.5,
            based_on="key_level",
        )

        assert info.stop_loss_price == 45000.0
        assert info.stop_loss_percent == 2.5
        assert info.based_on == "key_level"

    def test_stop_loss_with_key_level(self) -> None:
        """Test StopLossInfo with key level."""
        key_level = KeyLevel(
            price=46000.0,
            level_type=LevelType.SUPPORT,
            strength=80.0,
            timeframes=["1h", "4h"],
            touches=3,
        )

        info = StopLossInfo(
            stop_loss_price=45770.0,
            stop_loss_percent=2.5,
            based_on="key_level",
            key_level_used=key_level,
        )

        assert info.key_level_used is not None
        assert info.key_level_used.price == 46000.0

    def test_stop_loss_with_atr(self) -> None:
        """Test StopLossInfo with ATR."""
        info = StopLossInfo(
            stop_loss_price=44000.0,
            stop_loss_percent=4.0,
            based_on="volatility",
            atr_value=1000.0,
            atr_multiplier=2.0,
        )

        assert info.atr_value == 1000.0
        assert info.atr_multiplier == 2.0

    def test_to_dict(self) -> None:
        """Test serialization."""
        info = StopLossInfo(
            stop_loss_price=45000.0,
            stop_loss_percent=2.5,
            based_on="fixed_percentage",
        )

        d = info.to_dict()

        assert d["stop_loss_price"] == 45000.0
        assert d["stop_loss_percent"] == 2.5
        assert d["based_on"] == "fixed_percentage"


class TestPositionSizeInfo:
    """Tests for PositionSizeInfo dataclass."""

    def test_position_size_creation(self) -> None:
        """Test creating PositionSizeInfo."""
        info = PositionSizeInfo(
            position_size=0.5,
            position_value_usd=25000.0,
            risk_amount_usd=100.0,
            risk_percent=1.0,
            portfolio_value_usd=10000.0,
        )

        assert info.position_size == 0.5
        assert info.risk_amount_usd == 100.0
        assert info.risk_percent == 1.0

    def test_position_size_normalization(self) -> None:
        """Test value normalization."""
        info = PositionSizeInfo(
            position_size=-0.5,  # Should clamp to 0
            position_value_usd=-1000.0,  # Should clamp to 0
            risk_amount_usd=-50.0,  # Should clamp to 0
            risk_percent=150.0,  # Should clamp to 100
            portfolio_value_usd=-5000.0,  # Should clamp to 0
            leverage_used=0.5,  # Should clamp to 1.0
        )

        assert info.position_size == 0.0
        assert info.position_value_usd == 0.0
        assert info.risk_amount_usd == 0.0
        assert info.risk_percent == 100.0
        assert info.portfolio_value_usd == 0.0
        assert info.leverage_used == 1.0

    def test_margin_required(self) -> None:
        """Test margin required calculation."""
        info = PositionSizeInfo(
            position_size=1.0,
            position_value_usd=50000.0,
            risk_amount_usd=100.0,
            risk_percent=1.0,
            portfolio_value_usd=10000.0,
            leverage_used=2.0,
        )

        # Margin = Position Value / Leverage = 50000 / 2 = 25000
        assert info.margin_required_usd == 25000.0

    def test_to_dict(self) -> None:
        """Test serialization."""
        info = PositionSizeInfo(
            position_size=0.5,
            position_value_usd=25000.0,
            risk_amount_usd=100.0,
            risk_percent=1.0,
            portfolio_value_usd=10000.0,
            leverage_used=1.0,
        )

        d = info.to_dict()

        assert d["position_size"] == 0.5
        assert d["risk_percent"] == 1.0
        assert d["margin_required_usd"] == 25000.0


class TestRiskRewardInfo:
    """Tests for RiskRewardInfo dataclass."""

    def test_risk_reward_creation(self) -> None:
        """Test creating RiskRewardInfo."""
        info = RiskRewardInfo(
            risk_reward_ratio=2.0,
            risk_amount=1000.0,
            reward_amount=2000.0,
            take_profit_price=52000.0,
            take_profit_percent=4.0,
            risk_percent=2.0,
        )

        assert info.risk_reward_ratio == 2.0
        assert info.risk_amount == 1000.0
        assert info.reward_amount == 2000.0

    def test_risk_reward_normalization(self) -> None:
        """Test value normalization."""
        info = RiskRewardInfo(
            risk_reward_ratio=-1.0,  # Should clamp to 0
            risk_amount=-100.0,  # Should clamp to 0
            reward_amount=-200.0,  # Should clamp to 0
            take_profit_price=52000.0,
            take_profit_percent=-4.0,  # Should clamp to 0
            risk_percent=-2.0,  # Should clamp to 0
        )

        assert info.risk_reward_ratio == 0.0
        assert info.risk_amount == 0.0
        assert info.reward_amount == 0.0
        assert info.take_profit_percent == 0.0
        assert info.risk_percent == 0.0

    def test_is_favorable(self) -> None:
        """Test favorable ratio check."""
        favorable = RiskRewardInfo(
            risk_reward_ratio=2.0,
            risk_amount=1000.0,
            reward_amount=2000.0,
            take_profit_price=52000.0,
            take_profit_percent=4.0,
            risk_percent=2.0,
        )
        not_favorable = RiskRewardInfo(
            risk_reward_ratio=1.0,
            risk_amount=1000.0,
            reward_amount=1000.0,
            take_profit_price=51000.0,
            take_profit_percent=2.0,
            risk_percent=2.0,
        )

        assert favorable.is_favorable is True
        assert not_favorable.is_favorable is False

    def test_ratio_text(self) -> None:
        """Test ratio text formatting."""
        info = RiskRewardInfo(
            risk_reward_ratio=2.5,
            risk_amount=1000.0,
            reward_amount=2500.0,
            take_profit_price=52500.0,
            take_profit_percent=5.0,
            risk_percent=2.0,
        )

        assert info.ratio_text == "1:2.5"

    def test_to_dict(self) -> None:
        """Test serialization."""
        info = RiskRewardInfo(
            risk_reward_ratio=2.0,
            risk_amount=1000.0,
            reward_amount=2000.0,
            take_profit_price=52000.0,
            take_profit_percent=4.0,
            risk_percent=2.0,
        )

        d = info.to_dict()

        assert d["risk_reward_ratio"] == 2.0
        assert d["ratio_text"] == "1:2.0"
        assert d["is_favorable"] is True


class TestSignalDetail:
    """Tests for SignalDetail dataclass."""

    def test_signal_detail_creation(self) -> None:
        """Test creating SignalDetail."""
        confluence = ConfluenceBreakdown(
            base_score=75.0,
            agreement_ratio=0.8,
            avg_strength=0.7,
            avg_confidence=0.75,
            diversity_bonus=0.06,
            type_bonus=0.05,
        )
        multiplier = ConfidenceMultiplierInfo(
            multiplier=1.2,
            rationale="2 timeframes agreeing",
            base_confidence=0.75,
            final_confidence=0.90,
            agreeing_timeframes=2,
            conflicting_timeframes=0,
        )
        stop_loss = StopLossInfo(
            stop_loss_price=45000.0,
            stop_loss_percent=2.5,
            based_on="key_level",
        )
        position_size = PositionSizeInfo(
            position_size=0.5,
            position_value_usd=25000.0,
            risk_amount_usd=100.0,
            risk_percent=1.0,
            portfolio_value_usd=10000.0,
        )
        risk_reward = RiskRewardInfo(
            risk_reward_ratio=2.0,
            risk_amount=1000.0,
            reward_amount=2000.0,
            take_profit_price=52000.0,
            take_profit_percent=4.0,
            risk_percent=2.0,
        )

        detail = SignalDetail(
            signal_id="test-123",
            token="BTC/USDT",
            direction="long",
            entry_price=50000.0,
            confidence=90.0,
            base_score=75.0,
            timeframe="1h",
            timestamp=datetime.now(UTC).isoformat(),
            confluence_breakdown=confluence,
            confidence_multiplier=multiplier,
            stop_loss=stop_loss,
            position_size=position_size,
            risk_reward=risk_reward,
        )

        assert detail.signal_id == "test-123"
        assert detail.token == "BTC/USDT"
        assert detail.direction == "long"
        assert detail.entry_price == 50000.0

    def test_signal_detail_normalization(self) -> None:
        """Test value normalization."""
        confluence = ConfluenceBreakdown(
            base_score=75.0,
            agreement_ratio=0.8,
            avg_strength=0.7,
            avg_confidence=0.75,
            diversity_bonus=0.06,
            type_bonus=0.05,
        )
        multiplier = ConfidenceMultiplierInfo(
            multiplier=1.2,
            rationale="Test",
            base_confidence=0.75,
            final_confidence=0.90,
            agreeing_timeframes=2,
            conflicting_timeframes=0,
        )
        stop_loss = StopLossInfo(
            stop_loss_price=45000.0,
            stop_loss_percent=2.5,
            based_on="key_level",
        )
        position_size = PositionSizeInfo(
            position_size=0.5,
            position_value_usd=25000.0,
            risk_amount_usd=100.0,
            risk_percent=1.0,
            portfolio_value_usd=10000.0,
        )
        risk_reward = RiskRewardInfo(
            risk_reward_ratio=2.0,
            risk_amount=1000.0,
            reward_amount=2000.0,
            take_profit_price=52000.0,
            take_profit_percent=4.0,
            risk_percent=2.0,
        )

        detail = SignalDetail(
            signal_id="test-123",
            token="BTC/USDT",
            direction="long",
            entry_price=-50000.0,  # Should clamp to 0
            confidence=150.0,  # Should clamp to 100
            base_score=-10.0,  # Should clamp to 0
            timeframe="1h",
            timestamp=datetime.now(UTC).isoformat(),
            confluence_breakdown=confluence,
            confidence_multiplier=multiplier,
            stop_loss=stop_loss,
            position_size=position_size,
            risk_reward=risk_reward,
        )

        assert detail.entry_price == 0.0
        assert detail.confidence == 100.0
        assert detail.base_score == 0.0

    def test_is_long(self) -> None:
        """Test long direction check."""
        detail = self._create_test_detail(direction="long")
        assert detail.is_long is True
        assert detail.is_short is False

    def test_is_short(self) -> None:
        """Test short direction check."""
        detail = self._create_test_detail(direction="short")
        assert detail.is_short is True
        assert detail.is_long is False

    def test_emoji(self) -> None:
        """Test emoji property."""
        long_detail = self._create_test_detail(direction="long")
        short_detail = self._create_test_detail(direction="short")
        neutral_detail = self._create_test_detail(direction="neutral")

        assert long_detail.emoji == "🟢"
        assert short_detail.emoji == "🔴"
        assert neutral_detail.emoji == "⚪"

    def test_to_dict(self) -> None:
        """Test serialization."""
        detail = self._create_test_detail()

        d = detail.to_dict()

        assert d["signal_id"] == "test-123"
        assert d["token"] == "BTC/USDT"
        assert d["direction"] == "long"
        assert "confluence_breakdown" in d
        assert "stop_loss" in d
        assert "position_size" in d
        assert "risk_reward" in d

    def test_to_discord_message(self) -> None:
        """Test Discord message formatting."""
        detail = self._create_test_detail()

        message = detail.to_discord_message()

        assert "🟢" in message
        assert "BTC/USDT" in message
        assert "Confluence Breakdown" in message
        assert "Confidence Multiplier" in message
        assert "Risk Management" in message

    def _create_test_detail(self, direction: str = "long") -> SignalDetail:
        """Helper to create test SignalDetail."""
        confluence = ConfluenceBreakdown(
            base_score=75.0,
            agreement_ratio=0.8,
            avg_strength=0.7,
            avg_confidence=0.75,
            diversity_bonus=0.06,
            type_bonus=0.05,
        )
        multiplier = ConfidenceMultiplierInfo(
            multiplier=1.2,
            rationale="2 timeframes agreeing",
            base_confidence=0.75,
            final_confidence=0.90,
            agreeing_timeframes=2,
            conflicting_timeframes=0,
        )
        stop_loss = StopLossInfo(
            stop_loss_price=45000.0,
            stop_loss_percent=2.5,
            based_on="key_level",
        )
        position_size = PositionSizeInfo(
            position_size=0.5,
            position_value_usd=25000.0,
            risk_amount_usd=100.0,
            risk_percent=1.0,
            portfolio_value_usd=10000.0,
        )
        risk_reward = RiskRewardInfo(
            risk_reward_ratio=2.0,
            risk_amount=1000.0,
            reward_amount=2000.0,
            take_profit_price=52000.0,
            take_profit_percent=4.0,
            risk_percent=2.0,
        )

        return SignalDetail(
            signal_id="test-123",
            token="BTC/USDT",
            direction=direction,
            entry_price=50000.0,
            confidence=90.0,
            base_score=75.0,
            timeframe="1h",
            timestamp=datetime.now(UTC).isoformat(),
            confluence_breakdown=confluence,
            confidence_multiplier=multiplier,
            stop_loss=stop_loss,
            position_size=position_size,
            risk_reward=risk_reward,
        )


class TestSignalDetailBuilder:
    """Tests for SignalDetailBuilder class."""

    def test_builder_creation(self) -> None:
        """Test creating SignalDetailBuilder."""
        builder = SignalDetailBuilder()

        assert builder.risk_percent == 1.0
        assert builder.atr_multiplier == 2.0
        assert builder.leverage == 1.0

    def test_builder_custom_params(self) -> None:
        """Test builder with custom parameters."""
        builder = SignalDetailBuilder(
            risk_percent=2.0,
            atr_multiplier=3.0,
            leverage=2.0,
        )

        assert builder.risk_percent == 2.0
        assert builder.atr_multiplier == 3.0
        assert builder.leverage == 2.0

    def test_build_basic(self) -> None:
        """Test basic signal detail build."""
        builder = SignalDetailBuilder()
        signal = self._create_test_signal()

        detail = builder.build(
            signal=signal,
            entry_price=50000.0,
            portfolio_value_usd=10000.0,
        )

        assert detail.signal_id == signal.signal_id
        assert detail.token == "BTC/USDT"
        assert detail.direction == "long"
        assert detail.entry_price == 50000.0
        assert detail.confluence_breakdown is not None
        assert detail.confidence_multiplier is not None
        assert detail.stop_loss is not None
        assert detail.position_size is not None
        assert detail.risk_reward is not None

    def test_build_with_key_levels(self) -> None:
        """Test build with key levels for stop-loss."""
        builder = SignalDetailBuilder()
        signal = self._create_test_signal()

        support_level = KeyLevel(
            price=48000.0,
            level_type=LevelType.SUPPORT,
            strength=80.0,
            timeframes=["1h"],
            touches=3,
        )
        key_levels = KeyLevelsResult(
            token="BTC/USDT",
            support_levels=[support_level],
            current_price=50000.0,
            nearest_support=support_level,
        )

        detail = builder.build(
            signal=signal,
            entry_price=50000.0,
            key_levels=key_levels,
            portfolio_value_usd=10000.0,
        )

        assert detail.stop_loss.based_on == "key_level"
        assert detail.stop_loss.key_level_used is not None

    def test_build_with_atr(self) -> None:
        """Test build with ATR for volatility-based stop-loss."""
        builder = SignalDetailBuilder()
        signal = self._create_test_signal()

        detail = builder.build(
            signal=signal,
            entry_price=50000.0,
            atr_value=1000.0,
            portfolio_value_usd=10000.0,
        )

        assert detail.stop_loss.based_on == "volatility"
        assert detail.stop_loss.atr_value == 1000.0

    def test_build_short_signal(self) -> None:
        """Test build with short signal."""
        builder = SignalDetailBuilder()
        signal = self._create_test_signal(direction=SignalDirection.SHORT)

        resistance_level = KeyLevel(
            price=52000.0,
            level_type=LevelType.RESISTANCE,
            strength=80.0,
            timeframes=["1h"],
            touches=3,
        )
        key_levels = KeyLevelsResult(
            token="BTC/USDT",
            resistance_levels=[resistance_level],
            current_price=50000.0,
            nearest_resistance=resistance_level,
        )

        detail = builder.build(
            signal=signal,
            entry_price=50000.0,
            key_levels=key_levels,
            portfolio_value_usd=10000.0,
        )

        assert detail.direction == "short"
        assert detail.is_short is True
        assert detail.stop_loss.stop_loss_price > detail.entry_price

    def test_build_confluence_breakdown(self) -> None:
        """Test confluence breakdown extraction."""
        builder = SignalDetailBuilder()
        signal = self._create_test_signal_with_breakdown()

        detail = builder.build(
            signal=signal,
            entry_price=50000.0,
            portfolio_value_usd=10000.0,
        )

        breakdown = detail.confluence_breakdown
        assert breakdown.base_score == signal.base_score
        assert len(breakdown.indicator_contributions) > 0
        assert len(breakdown.timeframe_agreements) > 0

    def test_build_confidence_multiplier(self) -> None:
        """Test confidence multiplier extraction."""
        builder = SignalDetailBuilder()
        signal = self._create_test_signal_with_multiplier()

        detail = builder.build(
            signal=signal,
            entry_price=50000.0,
            portfolio_value_usd=10000.0,
        )

        multiplier = detail.confidence_multiplier
        assert multiplier.multiplier == 1.2
        assert "agreeing" in multiplier.rationale.lower()

    def test_position_size_calculation(self) -> None:
        """Test position size calculation."""
        builder = SignalDetailBuilder(risk_percent=1.0)
        signal = self._create_test_signal()

        detail = builder.build(
            signal=signal,
            entry_price=50000.0,
            portfolio_value_usd=10000.0,
        )

        # With 1% risk on $10k = $100 risk
        # If stop-loss is 2.5% away, position size = $100 / ($50000 * 0.025) = 0.08
        assert detail.position_size.risk_amount_usd == 100.0
        assert detail.position_size.risk_percent == 1.0
        assert detail.position_size.portfolio_value_usd == 10000.0

    def test_risk_reward_calculation(self) -> None:
        """Test risk/reward calculation."""
        builder = SignalDetailBuilder()
        signal = self._create_test_signal()

        resistance = KeyLevel(
            price=52000.0,
            level_type=LevelType.RESISTANCE,
            strength=80.0,
            timeframes=["1h"],
            touches=3,
        )
        key_levels = KeyLevelsResult(
            token="BTC/USDT",
            resistance_levels=[resistance],
            current_price=50000.0,
            nearest_resistance=resistance,
        )

        detail = builder.build(
            signal=signal,
            entry_price=50000.0,
            key_levels=key_levels,
            portfolio_value_usd=10000.0,
        )

        # Risk/Reward should be calculated based on nearest resistance
        assert detail.risk_reward.risk_reward_ratio > 0
        assert detail.risk_reward.take_profit_price == 52000.0

    def test_with_risk_params(self) -> None:
        """Test creating builder with modified risk params."""
        builder = SignalDetailBuilder()
        new_builder = builder.with_risk_params(
            risk_percent=2.0,
            atr_multiplier=3.0,
            leverage=2.0,
        )

        assert new_builder.risk_percent == 2.0
        assert new_builder.atr_multiplier == 3.0
        assert new_builder.leverage == 2.0
        # Original builder unchanged
        assert builder.risk_percent == 1.0

    def _create_test_signal(
        self,
        direction: SignalDirection = SignalDirection.LONG,
    ) -> Signal:
        """Helper to create test Signal."""
        return Signal(
            token="BTC/USDT",
            direction=direction,
            confidence=0.90,
            base_score=75.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
            signal_id="test-signal-123",
        )

    def _create_test_signal_with_breakdown(self) -> Signal:
        """Helper to create test Signal with breakdown."""
        return Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.90,
            base_score=75.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
            signal_id="test-signal-456",
            contributing_factors=[
                {
                    "indicator": "rsi",
                    "timeframe": "1h",
                    "direction": "long",
                    "strength": 0.8,
                    "confidence": 0.75,
                    "weight": 1.0,
                    "weighted_score": 0.6,
                    "raw_value": 65.5,
                },
                {
                    "indicator": "macd",
                    "timeframe": "1h",
                    "direction": "long",
                    "strength": 0.7,
                    "confidence": 0.8,
                    "weight": 1.0,
                    "weighted_score": 0.56,
                },
            ],
            signal_breakdown={
                "by_indicator": {
                    "rsi": {"count": 1, "total_weight": 1.0, "directions": ["long"]},
                    "macd": {"count": 1, "total_weight": 1.0, "directions": ["long"]},
                },
                "by_timeframe": {
                    "1h": {
                        "count": 2,
                        "total_weight": 2.0,
                        "directions": ["long", "long"],
                    },
                },
                "total_signals": 2,
            },
            metadata={
                "score_components": {
                    "agreement_ratio": 0.85,
                    "avg_strength": 0.75,
                    "avg_confidence": 0.775,
                    "diversity_bonus": 0.04,
                    "type_bonus": 0.05,
                },
            },
        )

    def _create_test_signal_with_multiplier(self) -> Signal:
        """Helper to create test Signal with multiplier info."""
        return Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.90,
            base_score=75.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
            signal_id="test-signal-789",
            signal_breakdown={
                "by_timeframe": {
                    "1h": {
                        "count": 2,
                        "total_weight": 2.0,
                        "directions": ["long", "long"],
                    },
                    "4h": {"count": 1, "total_weight": 1.0, "directions": ["long"]},
                },
                "total_signals": 3,
            },
            metadata={
                "multiplier_applied": 1.2,
                "multiplier_rationale": "Multiplier 1.2x for 2 agreeing timeframes",
                "base_confidence_before_multiplier": 0.75,
            },
        )


class TestSignalDetailIntegration:
    """Integration tests for signal detail module."""

    def test_full_workflow_long_signal(self) -> None:
        """Test complete workflow for long signal."""
        builder = SignalDetailBuilder(risk_percent=1.0)

        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=80.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
            signal_id="btc-long-001",
            contributing_factors=[
                {
                    "indicator": "rsi",
                    "timeframe": "1h",
                    "direction": "long",
                    "strength": 0.85,
                    "confidence": 0.80,
                    "weight": 1.0,
                    "weighted_score": 0.68,
                },
                {
                    "indicator": "macd",
                    "timeframe": "1h",
                    "direction": "long",
                    "strength": 0.75,
                    "confidence": 0.75,
                    "weight": 1.0,
                    "weighted_score": 0.56,
                },
            ],
            signal_breakdown={
                "by_timeframe": {
                    "1h": {
                        "count": 2,
                        "total_weight": 2.0,
                        "directions": ["long", "long"],
                    },
                },
            },
            metadata={
                "multiplier_applied": 1.1,
                "multiplier_rationale": "1.1x for single timeframe agreement",
                "base_confidence_before_multiplier": 0.77,
                "score_components": {
                    "agreement_ratio": 0.9,
                    "avg_strength": 0.8,
                    "avg_confidence": 0.775,
                },
            },
        )

        support = KeyLevel(
            price=47500.0,
            level_type=LevelType.SUPPORT,
            strength=85.0,
            timeframes=["1h", "4h"],
            touches=5,
        )
        resistance = KeyLevel(
            price=52500.0,
            level_type=LevelType.RESISTANCE,
            strength=80.0,
            timeframes=["1h"],
            touches=3,
        )
        key_levels = KeyLevelsResult(
            token="BTC/USDT",
            support_levels=[support],
            resistance_levels=[resistance],
            current_price=50000.0,
            nearest_support=support,
            nearest_resistance=resistance,
        )

        detail = builder.build(
            signal=signal,
            entry_price=50000.0,
            key_levels=key_levels,
            portfolio_value_usd=50000.0,
        )

        # Verify all components
        assert detail.signal_id == "btc-long-001"
        assert detail.is_long is True
        assert detail.confidence == 85.0
        assert detail.confluence_breakdown.base_score == 80.0
        assert len(detail.confluence_breakdown.indicator_contributions) == 2
        assert detail.confidence_multiplier.multiplier == 1.1
        assert detail.stop_loss.based_on == "key_level"
        assert detail.stop_loss.stop_loss_price < detail.entry_price
        assert detail.position_size.risk_percent == 1.0
        assert detail.risk_reward.take_profit_price == 52500.0
        assert detail.risk_reward.risk_reward_ratio > 0

        # Verify serialization
        payload = detail.to_dict()
        assert "confluence_breakdown" in payload
        assert "stop_loss" in payload
        assert "position_size" in payload
        assert "risk_reward" in payload

    def test_full_workflow_short_signal(self) -> None:
        """Test complete workflow for short signal."""
        builder = SignalDetailBuilder(risk_percent=1.5)

        signal = Signal(
            token="ETH/USDT",
            direction=SignalDirection.SHORT,
            confidence=0.88,
            base_score=82.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="4h",
            signal_id="eth-short-001",
            contributing_factors=[
                {
                    "indicator": "bb",
                    "timeframe": "4h",
                    "direction": "short",
                    "strength": 0.90,
                    "confidence": 0.85,
                    "weight": 1.2,
                    "weighted_score": 0.92,
                },
            ],
            signal_breakdown={
                "by_timeframe": {
                    "4h": {"count": 1, "total_weight": 1.2, "directions": ["short"]},
                },
            },
            metadata={
                "multiplier_applied": 1.0,
                "multiplier_rationale": "Single timeframe, no agreement boost",
                "base_confidence_before_multiplier": 0.88,
            },
        )

        support = KeyLevel(
            price=2800.0,
            level_type=LevelType.SUPPORT,
            strength=75.0,
            timeframes=["4h"],
            touches=3,
        )
        resistance = KeyLevel(
            price=3200.0,
            level_type=LevelType.RESISTANCE,
            strength=90.0,
            timeframes=["4h", "1d"],
            touches=7,
        )
        key_levels = KeyLevelsResult(
            token="ETH/USDT",
            support_levels=[support],
            resistance_levels=[resistance],
            current_price=3000.0,
            nearest_support=support,
            nearest_resistance=resistance,
        )

        detail = builder.build(
            signal=signal,
            entry_price=3000.0,
            key_levels=key_levels,
            portfolio_value_usd=25000.0,
        )

        # Verify short-specific calculations
        assert detail.is_short is True
        assert detail.stop_loss.stop_loss_price > detail.entry_price
        assert detail.risk_reward.take_profit_price < detail.entry_price
        assert detail.position_size.risk_percent == 1.5

    def test_fallback_stop_loss_without_key_levels(self) -> None:
        """Test fallback stop-loss when no key levels available."""
        builder = SignalDetailBuilder()

        signal = Signal(
            token="SOL/USDT",
            direction=SignalDirection.LONG,
            confidence=0.75,
            base_score=70.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
            signal_id="sol-long-001",
        )

        detail = builder.build(
            signal=signal,
            entry_price=100.0,
            portfolio_value_usd=10000.0,
        )

        # Should use fixed percentage fallback
        assert detail.stop_loss.based_on == "fixed_percentage"
        assert detail.stop_loss.stop_loss_percent == 2.0

    def test_discord_message_format(self) -> None:
        """Test Discord message formatting with full detail."""
        builder = SignalDetailBuilder()

        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.90,
            base_score=85.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
            signal_id="btc-001",
            contributing_factors=[
                {
                    "indicator": "rsi",
                    "timeframe": "1h",
                    "direction": "long",
                    "strength": 0.85,
                    "confidence": 0.80,
                    "weight": 1.0,
                    "weighted_score": 0.68,
                },
            ],
            signal_breakdown={
                "by_timeframe": {
                    "1h": {"count": 1, "total_weight": 1.0, "directions": ["long"]},
                },
            },
            metadata={
                "multiplier_applied": 1.0,
                "multiplier_rationale": "Base multiplier",
            },
        )

        detail = builder.build(
            signal=signal,
            entry_price=50000.0,
            portfolio_value_usd=10000.0,
        )

        message = detail.to_discord_message()

        # Verify message contains all key sections
        assert "🟢" in message or "🔴" in message
        assert "BTC/USDT" in message
        assert "Confluence Breakdown" in message
        assert "Confidence Multiplier" in message
        assert "Risk Management" in message
        assert "Stop-Loss" in message
        assert "Position Size" in message
        assert "Risk/Reward" in message
