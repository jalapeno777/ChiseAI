"""Tests for ICT neuro-symbolic explainability module.

Covers:
    - ICTConceptRegistry lookups and immutability
    - ICTExplainer single-signal and confluence explanations
    - Confidence/strength tier classification
    - Discord and dashboard formatter rendering
    - Edge cases (unknown signal types, neutral direction, missing fields)
    - JSON serialisation of explanation results
"""

from __future__ import annotations

import json

import pytest

from ict.explainability.concepts import ICTConcept, ICTConceptRegistry
from ict.explainability.explainer import (
    ICTExplainer,
    _confidence_tier,
    _normalise_direction,
    _strength_label,
)
from ict.explainability.formatter import format_for_dashboard, format_for_discord

# ---------------------------------------------------------------------------
# ICTConceptRegistry
# ---------------------------------------------------------------------------


class TestICTConceptRegistry:
    """Tests for the ICT concept knowledge base."""

    def test_registry_has_all_three_concepts(self) -> None:
        registry = ICTConceptRegistry()
        for concept in (ICTConcept.CVD, ICTConcept.FVG, ICTConcept.ORDER_BLOCK):
            entry = registry.get(concept)
            assert entry is not None, f"Missing concept: {concept.value}"
            assert entry.name  # non-empty display name
            assert entry.description  # non-empty description

    def test_get_by_name_case_insensitive(self) -> None:
        registry = ICTConceptRegistry()
        entry = registry.get_by_name("cvd")
        assert entry is not None
        assert entry.name == "Cumulative Volume Delta"

        entry_upper = registry.get_by_name("ORDER_BLOCK")
        assert entry_upper is not None
        assert entry_upper.name == "Order Block"

    def test_get_by_name_unknown_returns_none(self) -> None:
        registry = ICTConceptRegistry()
        assert registry.get_by_name("NONEXISTENT") is None
        assert registry.get_by_name("") is None

    def test_supported_types_list(self) -> None:
        registry = ICTConceptRegistry()
        types = registry.supported_types
        assert "CVD" in types
        assert "FVG" in types
        assert "ORDER_BLOCK" in types
        assert len(types) == 3

    def test_concepts_have_key_traits(self) -> None:
        registry = ICTConceptRegistry()
        for concept in ICTConcept:
            entry = registry.get(concept)
            assert entry is not None
            assert len(entry.key_traits) >= 3

    def test_concepts_have_directional_interpretations(self) -> None:
        registry = ICTConceptRegistry()
        for concept in ICTConcept:
            entry = registry.get(concept)
            assert entry is not None
            assert entry.bullish_interpretation
            assert entry.bearish_interpretation

    def test_registry_is_immutable(self) -> None:
        registry = ICTConceptRegistry()
        with pytest.raises(TypeError):
            registry._ENTRIES = {}  # type: ignore[misc]

    def test_all_concepts_returns_copy(self) -> None:
        registry = ICTConceptRegistry()
        copy = registry.all_concepts
        assert len(copy) == 3
        copy[ICTConcept.CVD] = None  # type: ignore[assignment]
        # Original should be unaffected
        assert registry.get(ICTConcept.CVD) is not None


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


class TestHelperFunctions:
    """Tests for internal classification helpers."""

    @pytest.mark.parametrize(
        "direction, expected",
        [
            ("BULLISH", "bullish"),
            ("BEARISH", "bearish"),
            ("NEUTRAL", "neutral"),
            ("LONG", "bullish"),
            ("SHORT", "bearish"),
            ("  bullish  ", "bullish"),
        ],
    )
    def test_normalise_direction(self, direction: str, expected: str) -> None:
        assert _normalise_direction(direction) == expected

    def test_normalise_direction_unknown_passthrough(self) -> None:
        assert _normalise_direction("UNKNOWN") == "unknown"

    @pytest.mark.parametrize(
        "confidence, expected",
        [
            (0.9, "high"),
            (0.8, "high"),
            (0.7, "moderate"),
            (0.5, "moderate"),
            (0.3, "low"),
            (0.0, "low"),
        ],
    )
    def test_confidence_tier(self, confidence: float, expected: str) -> None:
        assert _confidence_tier(confidence) == expected

    @pytest.mark.parametrize(
        "strength, expected",
        [
            (1.0, "strong"),
            (0.8, "strong"),
            (0.6, "moderate"),
            (0.5, "moderate"),
            (0.3, "weak"),
            (0.0, "weak"),
        ],
    )
    def test_strength_label(self, strength: float, expected: str) -> None:
        assert _strength_label(strength) == expected


# ---------------------------------------------------------------------------
# ICTExplainer — single signal
# ---------------------------------------------------------------------------


class TestICTExplainerSingle:
    """Tests for single-signal explanation generation."""

    @pytest.fixture()
    def explainer(self) -> ICTExplainer:
        return ICTExplainer()

    def test_explain_cvd_bullish(self, explainer: ICTExplainer) -> None:
        result = explainer.explain(
            signal_type="CVD",
            direction="BULLISH",
            confidence=0.85,
            strength=0.9,
            timeframe="15m",
        )
        assert result.signal_type == "CVD"
        assert result.direction == "bullish"
        assert result.confidence == 0.85
        assert result.confidence_tier == "high"
        assert result.timeframe == "15m"
        assert result.concept_name == "Cumulative Volume Delta"
        assert (
            "CVD" in result.explanation
            or "Cumulative Volume Delta" in result.explanation
        )
        assert len(result.rationale) >= 3
        assert len(result.key_factors) >= 3

    def test_explain_fvg_bearish(self, explainer: ICTExplainer) -> None:
        result = explainer.explain(
            signal_type="FVG",
            direction="BEARISH",
            confidence=0.6,
            strength=0.7,
            timeframe="1h",
        )
        assert result.signal_type == "FVG"
        assert result.direction == "bearish"
        assert result.confidence_tier == "moderate"
        assert result.concept_name == "Fair Value Gap"
        assert "bearish" in result.concept_summary.lower()

    def test_explain_order_block_bullish(self, explainer: ICTExplainer) -> None:
        result = explainer.explain(
            signal_type="ORDER_BLOCK",
            direction="BULLISH",
            confidence=0.92,
            strength=0.95,
            timeframe="5m",
        )
        assert result.signal_type == "ORDER_BLOCK"
        assert result.direction == "bullish"
        assert result.confidence_tier == "high"
        assert "Order Block" in result.concept_name
        assert "support" in result.concept_summary.lower()

    def test_explain_neutral_direction(self, explainer: ICTExplainer) -> None:
        result = explainer.explain(
            signal_type="CVD",
            direction="NEUTRAL",
            confidence=0.4,
            strength=0.3,
        )
        assert result.direction == "neutral"
        assert result.confidence_tier == "low"
        # Neutral should use general description, not directional interp.
        assert result.concept_summary  # still populated

    def test_explain_long_direction_maps_to_bullish(
        self, explainer: ICTExplainer
    ) -> None:
        result = explainer.explain(
            signal_type="FVG",
            direction="LONG",
            confidence=0.75,
        )
        assert result.direction == "bullish"

    def test_explain_short_direction_maps_to_bearish(
        self, explainer: ICTExplainer
    ) -> None:
        result = explainer.explain(
            signal_type="ORDER_BLOCK",
            direction="SHORT",
            confidence=0.7,
        )
        assert result.direction == "bearish"

    def test_explain_unknown_signal_type(self, explainer: ICTExplainer) -> None:
        result = explainer.explain(
            signal_type="MYSTERY_SIGNAL",
            direction="BULLISH",
            confidence=0.5,
        )
        assert result.signal_type == "MYSTERY_SIGNAL"
        assert result.direction == "bullish"
        assert result.concept_name == "MYSTERY_SIGNAL"
        assert result.concept_traits == ()

    def test_explain_with_metadata(self, explainer: ICTExplainer) -> None:
        meta = {"price": 45000.0, "volume": 1234.5}
        result = explainer.explain(
            signal_type="CVD",
            direction="BULLISH",
            confidence=0.8,
            metadata=meta,
        )
        assert result.metadata == meta

    def test_explain_without_timeframe(self, explainer: ICTExplainer) -> None:
        result = explainer.explain(
            signal_type="FVG",
            direction="BEARISH",
            confidence=0.7,
        )
        assert result.timeframe == ""
        # Timeframe should not appear in key_factors when empty.
        assert "timeframe" not in " ".join(result.key_factors).lower()

    def test_rationale_includes_concept_description(
        self, explainer: ICTExplainer
    ) -> None:
        result = explainer.explain(
            signal_type="ORDER_BLOCK",
            direction="BULLISH",
            confidence=0.8,
            timeframe="15m",
        )
        # First rationale line should mention the concept description.
        assert any("consolidation" in r.lower() for r in result.rationale)


# ---------------------------------------------------------------------------
# ICTExplainer — confluence
# ---------------------------------------------------------------------------


class TestICTExplainerConfluence:
    """Tests for multi-signal confluence explanation generation."""

    @pytest.fixture()
    def explainer(self) -> ICTExplainer:
        return ICTExplainer()

    def test_confluence_bullish_two_signals(self, explainer: ICTExplainer) -> None:
        signals = [
            {
                "signal_type": "CVD",
                "direction": "BULLISH",
                "strength": 0.8,
                "confidence": 0.85,
            },
            {
                "signal_type": "FVG",
                "direction": "BULLISH",
                "strength": 0.7,
                "confidence": 0.75,
            },
        ]
        result = explainer.explain_confluence(
            confluence_score=0.78,
            direction="LONG",
            confidence=0.82,
            contributing_signals=signals,
            timeframe="15m",
        )
        assert result.signal_type == "CONFLUENCE"
        assert result.direction == "bullish"
        assert result.confidence_tier == "high"
        assert "2" in result.explanation  # mentions 2 signals
        assert "CVD" in result.concept_name or "Fair Value Gap" in result.concept_name
        assert len(result.rationale) >= 3

    def test_confluence_mixed_directions(self, explainer: ICTExplainer) -> None:
        signals = [
            {
                "signal_type": "CVD",
                "direction": "BULLISH",
                "strength": 0.9,
                "confidence": 0.9,
            },
            {
                "signal_type": "ORDER_BLOCK",
                "direction": "BEARISH",
                "strength": 0.4,
                "confidence": 0.4,
            },
        ]
        result = explainer.explain_confluence(
            confluence_score=0.55,
            direction="LONG",
            confidence=0.6,
            contributing_signals=signals,
        )
        assert result.direction == "bullish"
        assert result.confidence_tier == "moderate"

    def test_confluence_three_signals(self, explainer: ICTExplainer) -> None:
        signals = [
            {
                "signal_type": "CVD",
                "direction": "BULLISH",
                "strength": 0.85,
                "confidence": 0.88,
            },
            {
                "signal_type": "FVG",
                "direction": "BULLISH",
                "strength": 0.75,
                "confidence": 0.78,
            },
            {
                "signal_type": "ORDER_BLOCK",
                "direction": "BULLISH",
                "strength": 0.9,
                "confidence": 0.92,
            },
        ]
        result = explainer.explain_confluence(
            confluence_score=0.85,
            direction="LONG",
            confidence=0.9,
            contributing_signals=signals,
            timeframe="1h",
        )
        assert result.signal_type == "CONFLUENCE"
        assert "3" in result.explanation
        assert result.timeframe == "1h"
        # All three concept names should be referenced.
        assert "Cumulative Volume Delta" in result.concept_name
        assert "Fair Value Gap" in result.concept_name
        assert "Order Block" in result.concept_name

    def test_confluence_empty_signals(self, explainer: ICTExplainer) -> None:
        result = explainer.explain_confluence(
            confluence_score=0.0,
            direction="NEUTRAL",
            confidence=0.1,
            contributing_signals=[],
        )
        assert result.signal_type == "CONFLUENCE"
        assert result.direction == "neutral"
        assert result.confidence_tier == "low"
        assert "0" in result.explanation

    def test_confluence_with_unknown_signal(self, explainer: ICTExplainer) -> None:
        signals = [
            {
                "signal_type": "CVD",
                "direction": "BULLISH",
                "strength": 0.8,
                "confidence": 0.8,
            },
            {
                "signal_type": "UNKNOWN",
                "direction": "BEARISH",
                "strength": 0.5,
                "confidence": 0.5,
            },
        ]
        result = explainer.explain_confluence(
            confluence_score=0.6,
            direction="LONG",
            confidence=0.65,
            contributing_signals=signals,
        )
        # Should not crash; UNKNOWN should be gracefully handled.
        assert result.direction == "bullish"
        assert len(result.rationale) >= 3


# ---------------------------------------------------------------------------
# ICTExplanationResult.to_dict
# ---------------------------------------------------------------------------


class TestExplanationResultSerialization:
    """Tests for result serialisation."""

    def test_to_dict_is_json_serializable(self) -> None:
        explainer = ICTExplainer()
        result = explainer.explain(
            signal_type="CVD",
            direction="BULLISH",
            confidence=0.85,
            strength=0.9,
            timeframe="15m",
            metadata={"price": 45000.0},
        )
        d = result.to_dict()
        serialized = json.dumps(d)
        assert isinstance(serialized, str)
        parsed = json.loads(serialized)
        assert parsed["signal_type"] == "CVD"
        assert parsed["confidence"] == 0.85
        assert parsed["metadata"]["price"] == 45000.0

    def test_to_dict_has_all_expected_keys(self) -> None:
        explainer = ICTExplainer()
        result = explainer.explain("FVG", "BEARISH", 0.7, timeframe="1h")
        d = result.to_dict()
        expected_keys = {
            "signal_type",
            "direction",
            "confidence",
            "confidence_tier",
            "explanation",
            "concept_summary",
            "rationale",
            "key_factors",
            "concept_name",
            "concept_traits",
            "timeframe",
            "metadata",
        }
        assert set(d.keys()) == expected_keys
        assert isinstance(d["rationale"], list)
        assert isinstance(d["key_factors"], list)
        assert isinstance(d["concept_traits"], list)


# ---------------------------------------------------------------------------
# Discord formatter
# ---------------------------------------------------------------------------


class TestDiscordFormatter:
    """Tests for Discord message rendering."""

    def test_format_contains_emoji_and_bold(self) -> None:
        explainer = ICTExplainer()
        result = explainer.explain("CVD", "BULLISH", 0.85, timeframe="15m")
        discord_msg = format_for_discord(result, token="BTC")
        assert "\U0001f7e2" in discord_msg  # green circle
        assert "**" in discord_msg  # bold markdown
        assert "BTC" in discord_msg
        assert "85%" in discord_msg
        assert "15m" in discord_msg

    def test_format_bearish_uses_red_emoji(self) -> None:
        explainer = ICTExplainer()
        result = explainer.explain("FVG", "BEARISH", 0.6)
        discord_msg = format_for_discord(result)
        assert "\U0001f534" in discord_msg  # red circle

    def test_format_neutral_uses_yellow_emoji(self) -> None:
        explainer = ICTExplainer()
        result = explainer.explain("CVD", "NEUTRAL", 0.3)
        discord_msg = format_for_discord(result)
        assert "\U0001f7e1" in discord_msg  # yellow circle

    def test_format_includes_key_factors_numbered(self) -> None:
        explainer = ICTExplainer()
        result = explainer.explain("ORDER_BLOCK", "BULLISH", 0.9, strength=0.95)
        discord_msg = format_for_discord(result)
        assert "Key Factors" in discord_msg
        # At least one numbered item should appear.
        assert "1." in discord_msg

    def test_format_without_token(self) -> None:
        explainer = ICTExplainer()
        result = explainer.explain("CVD", "BULLISH", 0.8)
        discord_msg = format_for_discord(result)
        assert "CVD" in discord_msg
        assert "\u2014" not in discord_msg  # no token separator

    def test_format_includes_concept_summary(self) -> None:
        explainer = ICTExplainer()
        result = explainer.explain("FVG", "BULLISH", 0.75)
        discord_msg = format_for_discord(result)
        assert "Fair Value Gap" in discord_msg

    def test_format_confluence(self) -> None:
        explainer = ICTExplainer()
        signals = [
            {
                "signal_type": "CVD",
                "direction": "BULLISH",
                "strength": 0.8,
                "confidence": 0.85,
            },
            {
                "signal_type": "FVG",
                "direction": "BULLISH",
                "strength": 0.7,
                "confidence": 0.75,
            },
        ]
        result = explainer.explain_confluence(
            confluence_score=0.78,
            direction="LONG",
            confidence=0.82,
            contributing_signals=signals,
        )
        discord_msg = format_for_discord(result, token="ETH")
        assert "CONFLUENCE" in discord_msg
        assert "ETH" in discord_msg
        assert "82%" in discord_msg


# ---------------------------------------------------------------------------
# Dashboard formatter
# ---------------------------------------------------------------------------


class TestDashboardFormatter:
    """Tests for dashboard dict rendering."""

    def test_format_dashboard_has_display_label(self) -> None:
        explainer = ICTExplainer()
        result = explainer.explain("CVD", "BULLISH", 0.85, timeframe="15m")
        dashboard = format_for_dashboard(result)
        assert "display_label" in dashboard
        assert "Bullish" in dashboard["display_label"]
        assert "CVD" in dashboard["display_label"]

    def test_format_dashboard_has_emojis(self) -> None:
        explainer = ICTExplainer()
        result = explainer.explain("FVG", "BEARISH", 0.6)
        dashboard = format_for_dashboard(result)
        assert "direction_emoji" in dashboard
        assert "confidence_emoji" in dashboard

    def test_format_dashboard_is_json_serializable(self) -> None:
        explainer = ICTExplainer()
        result = explainer.explain("ORDER_BLOCK", "BULLISH", 0.92, timeframe="5m")
        dashboard = format_for_dashboard(result)
        serialized = json.dumps(dashboard)
        assert isinstance(serialized, str)
        parsed = json.loads(serialized)
        assert parsed["signal_type"] == "ORDER_BLOCK"
        assert parsed["confidence"] == 0.92

    def test_format_dashboard_extends_to_dict(self) -> None:
        explainer = ICTExplainer()
        result = explainer.explain("CVD", "BULLISH", 0.8)
        dashboard = format_for_dashboard(result)
        base = result.to_dict()
        # Dashboard should have all base keys plus extra rendering keys.
        for key in base:
            assert key in dashboard
        assert "display_label" in dashboard
        assert "direction_emoji" in dashboard
        assert "confidence_emoji" in dashboard

    def test_format_dashboard_concepts_traits_list(self) -> None:
        explainer = ICTExplainer()
        result = explainer.explain("CVD", "BULLISH", 0.8)
        dashboard = format_for_dashboard(result)
        assert "concept_traits_list" in dashboard
        assert isinstance(dashboard["concept_traits_list"], list)
        assert len(dashboard["concept_traits_list"]) >= 3
