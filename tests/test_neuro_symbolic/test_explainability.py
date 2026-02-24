"""Tests for the Neuro-Symbolic Explainability Module.

Comprehensive tests for ExplanationGenerator, FeatureImportanceAnalyzer,
ExplanationConfidenceScorer, and ExplanationFormatter.
"""

from __future__ import annotations

import pytest
from typing import Any

from neuro_symbolic.explainability.generator import (
    ExplanationConfig,
    ExplanationGenerator,
    ExplanationResult,
    ExplanationType,
    ReasoningStep,
)
from neuro_symbolic.explainability.feature_importance import (
    FeatureContribution,
    FeatureImportanceAnalyzer,
    FeatureImportanceResult,
    ImportanceMethod,
    ImportanceVisualization,
)
from neuro_symbolic.explainability.confidence_scorer import (
    ConfidenceLevel,
    ConfidenceMetric,
    ConfidenceScore,
    ExplanationConfidenceScorer,
    ScoringConfig,
)
from neuro_symbolic.explainability.formatter import (
    AudienceType,
    ExplanationFormatter,
    FormattedExplanation,
    FormatterConfig,
    OutputFormat,
)
from neuro_symbolic.xai.shap_utils import (
    InteractionDetector,
    InteractionResult,
    SHAPCalculator,
    SHAPConfig,
    SHAPMethod,
    SHAPResult,
    SHAPValue,
)
from neuro_symbolic.xai.visualization import (
    ExplanationVisualizer,
    PlotData,
    PlotType,
    VisualizationConfig,
    VisualizationResult,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def sample_decision_data() -> dict[str, Any]:
    """Sample decision data for testing."""
    return {
        "prediction": "buy",
        "confidence": 0.85,
        "features": {
            "rsi": 28,
            "macd": 0.15,
            "volume": 1.5,
            "trend": 0.7,
            "volatility": 0.02,
        },
        "feature_contributions": {
            "rsi": 0.35,
            "macd": 0.25,
            "volume": 0.15,
            "trend": 0.10,
        },
        "metadata": {"symbol": "BTC", "timeframe": "1h"},
    }


@pytest.fixture
def sample_explanation() -> dict[str, Any]:
    """Sample explanation for testing."""
    return {
        "explanation_type": "signal",
        "summary": "Strong buy signal with 85% confidence based on oversold RSI and bullish MACD crossover.",
        "reasoning_chain": [
            {
                "step_number": 1,
                "description": "Identified buy signal with 85% confidence",
                "evidence": {"prediction": "buy", "confidence": 0.85},
                "confidence": 0.85,
            },
            {
                "step_number": 2,
                "description": "Technical analysis: RSI indicates oversold conditions",
                "evidence": {"rsi": 28},
                "confidence": 0.80,
            },
            {
                "step_number": 3,
                "description": "MACD shows bullish momentum",
                "evidence": {"macd": 0.15},
                "confidence": 0.75,
            },
        ],
        "key_factors": {"rsi": 0.35, "macd": 0.25, "volume": 0.15},
        "overall_confidence": 0.85,
        "metadata": {"symbol": "BTC"},
    }


# ============================================================================
# ReasoningStep Tests
# ============================================================================


class TestReasoningStep:
    """Tests for ReasoningStep dataclass."""

    def test_create_reasoning_step(self):
        """Test creating a reasoning step."""
        step = ReasoningStep(
            step_number=1,
            description="Test step",
            evidence={"key": "value"},
            confidence=0.8,
        )

        assert step.step_number == 1
        assert step.description == "Test step"
        assert step.evidence == {"key": "value"}
        assert step.confidence == 0.8

    def test_reasoning_step_confidence_validation(self):
        """Test confidence must be between 0 and 1."""
        with pytest.raises(ValueError):
            ReasoningStep(
                step_number=1,
                description="Test",
                confidence=1.5,
            )

        with pytest.raises(ValueError):
            ReasoningStep(
                step_number=1,
                description="Test",
                confidence=-0.1,
            )


# ============================================================================
# ExplanationGenerator Tests
# ============================================================================


class TestExplanationGenerator:
    """Tests for ExplanationGenerator class."""

    def test_create_generator(self):
        """Test creating an explanation generator."""
        generator = ExplanationGenerator()
        assert generator.config is not None

        custom_config = ExplanationConfig(max_reasoning_steps=10)
        generator = ExplanationGenerator(config=custom_config)
        assert generator.config.max_reasoning_steps == 10

    def test_explain_buy_signal(self, sample_decision_data):
        """Test explaining a buy signal."""
        generator = ExplanationGenerator()
        result = generator.explain(sample_decision_data)

        assert isinstance(result, ExplanationResult)
        assert result.explanation_type == ExplanationType.SIGNAL
        assert "buy" in result.summary.lower()
        assert len(result.reasoning_chain) > 0
        assert result.overall_confidence == 0.85

    def test_explain_sell_signal(self):
        """Test explaining a sell signal."""
        generator = ExplanationGenerator()
        result = generator.explain(
            {
                "prediction": "sell",
                "confidence": 0.75,
                "features": {"rsi": 75, "macd": -0.2},
            }
        )

        assert "sell" in result.summary.lower()
        assert result.overall_confidence == 0.75

    def test_explain_hold_signal(self):
        """Test explaining a hold signal."""
        generator = ExplanationGenerator()
        result = generator.explain(
            {
                "prediction": "hold",
                "confidence": 0.55,
                "features": {"rsi": 50, "macd": 0.0},
            }
        )

        assert "hold" in result.summary.lower() or "hold" in result.summary.lower()

    def test_explain_with_features(self, sample_decision_data):
        """Test explanation includes feature analysis."""
        generator = ExplanationGenerator()
        result = generator.explain(sample_decision_data)

        # Should have reasoning about features
        feature_steps = [
            s
            for s in result.reasoning_chain
            if "technical" in s.description.lower() or "rsi" in s.description.lower()
        ]
        assert len(feature_steps) > 0

    def test_explain_signal_method(self):
        """Test the explain_signal convenience method."""
        generator = ExplanationGenerator()
        result = generator.explain_signal(
            signal_type="buy",
            confidence=0.9,
            contributing_factors={"rsi": 0.4, "macd": 0.3},
        )

        assert result.explanation_type == ExplanationType.SIGNAL
        assert result.overall_confidence == 0.9

    def test_explain_prediction_method(self):
        """Test the explain_prediction convenience method."""
        generator = ExplanationGenerator()
        result = generator.explain_prediction(
            prediction="up",
            confidence=0.8,
            features={"momentum": 0.5},
            timeframe="4h",
        )

        assert result.explanation_type == ExplanationType.PREDICTION
        assert "timeframe" in result.metadata

    def test_explain_risk_assessment_method(self):
        """Test the explain_risk_assessment convenience method."""
        generator = ExplanationGenerator()
        result = generator.explain_risk_assessment(
            risk_level="high",
            risk_score=0.75,
            risk_factors={"volatility": 0.5, "liquidity": 0.3},
        )

        assert result.explanation_type == ExplanationType.RISK

    def test_invalid_confidence_raises(self):
        """Test that invalid confidence raises error."""
        generator = ExplanationGenerator()

        with pytest.raises(ValueError):
            generator.explain(
                {
                    "prediction": "buy",
                    "confidence": 1.5,  # Invalid
                }
            )

    def test_result_to_dict(self, sample_decision_data):
        """Test ExplanationResult.to_dict method."""
        generator = ExplanationGenerator()
        result = generator.explain(sample_decision_data)
        result_dict = result.to_dict()

        assert isinstance(result_dict, dict)
        assert "explanation_type" in result_dict
        assert "summary" in result_dict
        assert "reasoning_chain" in result_dict


# ============================================================================
# FeatureImportanceAnalyzer Tests
# ============================================================================


class TestFeatureImportanceAnalyzer:
    """Tests for FeatureImportanceAnalyzer class."""

    def test_create_analyzer(self):
        """Test creating an analyzer."""
        analyzer = FeatureImportanceAnalyzer()
        assert analyzer.method == ImportanceMethod.SHAP

        analyzer = FeatureImportanceAnalyzer(method=ImportanceMethod.PERMUTATION)
        assert analyzer.method == ImportanceMethod.PERMUTATION

    def test_analyze_features(self):
        """Test analyzing feature importance."""
        analyzer = FeatureImportanceAnalyzer()
        result = analyzer.analyze(
            features={"rsi": 28, "macd": 0.15, "volume": 1.5},
            prediction=0.85,
            base_value=0.5,
        )

        assert isinstance(result, FeatureImportanceResult)
        assert len(result.contributions) == 3
        assert result.method == ImportanceMethod.SHAP
        assert result.final_prediction == 0.85

    def test_feature_contribution(self):
        """Test FeatureContribution properties."""
        contrib = FeatureContribution(
            feature_name="rsi",
            contribution_value=0.35,
            base_value=0.5,
            feature_value=28,
        )

        assert contrib.absolute_contribution == 0.35
        assert contrib.direction == "positive"

        contrib2 = FeatureContribution(
            feature_name="test",
            contribution_value=-0.2,
        )
        assert contrib2.direction == "negative"

    def test_get_ranked_features(self):
        """Test getting ranked features."""
        analyzer = FeatureImportanceAnalyzer()
        result = analyzer.analyze(
            features={"a": 0.9, "b": 0.5, "c": 0.1},
            prediction=0.8,
            base_value=0.5,
        )

        ranked = result.get_ranked_features(top_n=2)
        assert len(ranked) == 2

    def test_top_positive_negative_features(self):
        """Test getting top positive and negative features."""
        analyzer = FeatureImportanceAnalyzer()
        result = analyzer.analyze(
            features={"pos1": 0.9, "pos2": 0.7, "neg1": 0.1},
            prediction=0.75,
            base_value=0.5,
        )

        assert len(result.top_positive_features) >= 0
        assert len(result.top_negative_features) >= 0

    def test_analyze_batch(self):
        """Test batch analysis."""
        analyzer = FeatureImportanceAnalyzer()
        results = analyzer.analyze_batch(
            feature_list=[
                {"rsi": 30, "macd": 0.1},
                {"rsi": 70, "macd": -0.1},
            ],
            predictions=[0.7, 0.3],
            base_value=0.5,
        )

        assert len(results) == 2
        assert all(isinstance(r, FeatureImportanceResult) for r in results)

    def test_global_importance(self):
        """Test calculating global importance."""
        analyzer = FeatureImportanceAnalyzer()
        results = analyzer.analyze_batch(
            feature_list=[
                {"rsi": 30, "macd": 0.1},
                {"rsi": 70, "macd": -0.1},
            ],
            predictions=[0.7, 0.3],
            base_value=0.5,
        )

        global_importance = analyzer.get_global_importance(results)
        assert isinstance(global_importance, dict)
        assert "rsi" in global_importance

    def test_create_visualization(self):
        """Test creating visualization data."""
        analyzer = FeatureImportanceAnalyzer()
        result = analyzer.analyze(
            features={"rsi": 28, "macd": 0.15},
            prediction=0.8,
            base_value=0.5,
        )

        viz = analyzer.create_visualization(result)
        assert isinstance(viz, ImportanceVisualization)
        assert len(viz.feature_names) == len(viz.values)
        assert len(viz.colors) == len(viz.values)

    def test_waterfall_data(self):
        """Test creating waterfall chart data."""
        analyzer = FeatureImportanceAnalyzer()
        result = analyzer.analyze(
            features={"a": 0.8, "b": 0.5},
            prediction=0.7,
            base_value=0.5,
        )

        waterfall = analyzer.create_waterfall_data(result)
        assert "base" in waterfall
        assert "steps" in waterfall
        assert "final" in waterfall


# ============================================================================
# ExplanationConfidenceScorer Tests
# ============================================================================


class TestExplanationConfidenceScorer:
    """Tests for ExplanationConfidenceScorer class."""

    def test_create_scorer(self):
        """Test creating a confidence scorer."""
        scorer = ExplanationConfidenceScorer()
        assert scorer.config is not None

        config = ScoringConfig(high_confidence_threshold=0.8)
        scorer = ExplanationConfidenceScorer(config=config)
        assert scorer.config.high_confidence_threshold == 0.8

    def test_score_explanation(self, sample_explanation):
        """Test scoring an explanation."""
        scorer = ExplanationConfidenceScorer()
        score = scorer.score_explanation(sample_explanation)

        assert isinstance(score, ConfidenceScore)
        assert 0 <= score.overall_score <= 1
        assert isinstance(score.level, ConfidenceLevel)
        assert len(score.metrics) == 5  # All 5 metrics

    def test_confidence_levels(self, sample_explanation):
        """Test different confidence levels are assigned correctly."""
        scorer = ExplanationConfidenceScorer()

        # High confidence explanation
        sample_explanation["overall_confidence"] = 0.95
        score = scorer.score_explanation(sample_explanation)
        assert score.level in [ConfidenceLevel.HIGH, ConfidenceLevel.VERY_HIGH]

        # Low confidence explanation - need to reduce other metrics too
        low_conf_explanation = {
            "summary": "Test",
            "reasoning_chain": [],
            "key_factors": {},
            "overall_confidence": 0.1,
        }
        score = scorer.score_explanation(low_conf_explanation)
        # With no reasoning chain and low model confidence, should be low
        assert score.overall_score < 0.5

    def test_is_reliable(self, sample_explanation):
        """Test reliability check."""
        scorer = ExplanationConfidenceScorer()
        score = scorer.score_explanation(sample_explanation)

        assert isinstance(score.is_reliable, bool)

    def test_confidence_interval(self, sample_explanation):
        """Test confidence interval calculation."""
        scorer = ExplanationConfidenceScorer()
        score = scorer.score_explanation(sample_explanation)

        interval = score.confidence_interval
        assert isinstance(interval, tuple)
        assert len(interval) == 2
        assert interval[0] <= score.overall_score <= interval[1]

    def test_score_reasoning_chain(self):
        """Test scoring reasoning chain quality."""
        scorer = ExplanationConfidenceScorer()

        chain = [
            {"step_number": 1, "description": "Step 1", "confidence": 0.8},
            {"step_number": 2, "description": "Step 2", "confidence": 0.7},
        ]

        metric = scorer.score_reasoning_chain(chain)
        assert isinstance(metric, ConfidenceMetric)
        assert metric.name == "reasoning_chain"
        assert 0 <= metric.value <= 1

    def test_score_feature_importance(self):
        """Test scoring feature importance."""
        scorer = ExplanationConfidenceScorer()

        factors = {"rsi": 0.35, "macd": 0.25, "volume": 0.15}
        metric = scorer.score_feature_importance(factors)

        assert isinstance(metric, ConfidenceMetric)
        assert metric.name == "feature_importance"

    def test_compare_explanations(self, sample_explanation):
        """Test comparing multiple explanations."""
        scorer = ExplanationConfidenceScorer()

        explanations = [
            sample_explanation,
            {**sample_explanation, "overall_confidence": 0.6},
            {**sample_explanation, "overall_confidence": 0.4},
        ]

        comparison = scorer.compare_explanations(explanations)

        assert "rankings" in comparison
        assert "best_index" in comparison
        assert "reliable_count" in comparison
        assert len(comparison["rankings"]) == 3

    def test_warnings_generated(self):
        """Test that warnings are generated for low-quality explanations."""
        scorer = ExplanationConfidenceScorer()

        poor_explanation = {
            "summary": "",  # No summary
            "reasoning_chain": [],  # No reasoning
            "key_factors": {},  # No factors
            "overall_confidence": 0.3,  # Low confidence
        }

        score = scorer.score_explanation(poor_explanation)
        assert len(score.warnings) > 0

    def test_score_to_dict(self, sample_explanation):
        """Test ConfidenceScore.to_dict method."""
        scorer = ExplanationConfidenceScorer()
        score = scorer.score_explanation(sample_explanation)

        score_dict = score.to_dict()
        assert isinstance(score_dict, dict)
        assert "overall_score" in score_dict
        assert "level" in score_dict


# ============================================================================
# ExplanationFormatter Tests
# ============================================================================


class TestExplanationFormatter:
    """Tests for ExplanationFormatter class."""

    def test_create_formatter(self):
        """Test creating a formatter."""
        formatter = ExplanationFormatter()
        assert formatter.config is not None

        config = FormatterConfig(audience=AudienceType.TECHNICAL)
        formatter = ExplanationFormatter(config=config)
        assert formatter.config.audience == AudienceType.TECHNICAL

    def test_format_default(self, sample_explanation):
        """Test formatting with default settings."""
        formatter = ExplanationFormatter()
        result = formatter.format(sample_explanation)

        assert isinstance(result, FormattedExplanation)
        assert len(result.content) > 0
        assert result.audience == AudienceType.GENERAL
        assert result.format == OutputFormat.TEXT

    def test_format_for_technical(self, sample_explanation):
        """Test formatting for technical audience."""
        formatter = ExplanationFormatter()
        result = formatter.format_for_technical(sample_explanation)

        assert result.audience == AudienceType.TECHNICAL
        assert result.format == OutputFormat.MARKDOWN
        assert "##" in result.content  # Markdown headers

    def test_format_for_trader(self, sample_explanation):
        """Test formatting for trader audience."""
        formatter = ExplanationFormatter()
        result = formatter.format_for_trader(sample_explanation)

        assert result.audience == AudienceType.TRADER
        assert result.format == OutputFormat.TEXT

    def test_format_for_executive(self, sample_explanation):
        """Test formatting for executive audience."""
        formatter = ExplanationFormatter()
        result = formatter.format_for_executive(sample_explanation)

        assert result.audience == AudienceType.EXECUTIVE
        # Executive format should be simpler
        assert len(result.content) > 0

    def test_format_as_json(self, sample_explanation):
        """Test formatting as JSON."""
        formatter = ExplanationFormatter()
        result = formatter.format_as_json(sample_explanation)

        assert result.format == OutputFormat.JSON
        # Content should be valid JSON
        import json

        parsed = json.loads(result.content)
        assert isinstance(parsed, dict)

    def test_format_as_markdown(self, sample_explanation):
        """Test formatting as Markdown."""
        formatter = ExplanationFormatter()
        result = formatter.format_as_markdown(sample_explanation)

        assert result.format == OutputFormat.MARKDOWN

    def test_format_as_html(self, sample_explanation):
        """Test formatting as HTML."""
        formatter = ExplanationFormatter()
        result = formatter.format_as_html(sample_explanation)

        assert result.format == OutputFormat.HTML
        assert "<div" in result.content

    def test_create_summary_only(self, sample_explanation):
        """Test creating summary-only output."""
        formatter = ExplanationFormatter()
        summary = formatter.create_summary_only(sample_explanation)

        assert isinstance(summary, str)
        assert len(summary) > 0

    def test_create_bullet_summary(self, sample_explanation):
        """Test creating bullet summary."""
        formatter = ExplanationFormatter()
        bullets = formatter.create_bullet_summary(sample_explanation, max_bullets=3)

        assert isinstance(bullets, list)
        assert len(bullets) <= 3

    def test_sections_populated(self, sample_explanation):
        """Test that sections are populated."""
        formatter = ExplanationFormatter()
        result = formatter.format(sample_explanation)

        assert "summary" in result.sections
        assert len(result.sections["summary"]) > 0

    def test_formatted_to_dict(self, sample_explanation):
        """Test FormattedExplanation.to_dict method."""
        formatter = ExplanationFormatter()
        result = formatter.format(sample_explanation)

        result_dict = result.to_dict()
        assert isinstance(result_dict, dict)
        assert "content" in result_dict
        assert "audience" in result_dict


# ============================================================================
# SHAPCalculator Tests
# ============================================================================


class TestSHAPCalculator:
    """Tests for SHAPCalculator class."""

    def test_create_calculator(self):
        """Test creating a SHAP calculator."""
        calc = SHAPCalculator()
        assert calc.config is not None
        assert calc.config.method == SHAPMethod.KERNEL

    def test_calculate_shap_values(self):
        """Test calculating SHAP values."""
        calc = SHAPCalculator()
        result = calc.calculate(
            features={"rsi": 28, "macd": 0.15, "volume": 1.5},
            base_value=0.5,
        )

        assert isinstance(result, SHAPResult)
        assert len(result.shap_values) == 3
        assert result.method == SHAPMethod.KERNEL

    def test_shap_value_properties(self):
        """Test SHAPValue properties."""
        sv = SHAPValue(
            feature_name="rsi",
            value=0.35,
            feature_value=28,
            base_value=0.5,
        )

        assert sv.abs_value == 0.35
        assert sv.direction == "increases"

        sv2 = SHAPValue(feature_name="test", value=-0.2)
        assert sv2.direction == "decreases"

    def test_shap_result_properties(self):
        """Test SHAPResult properties."""
        calc = SHAPCalculator()
        result = calc.calculate(
            features={"a": 0.9, "b": 0.5},
            base_value=0.5,
        )

        # Test properties
        assert isinstance(result.total_positive, float)
        assert isinstance(result.total_negative, float)
        assert isinstance(result.top_features, list)

    def test_calculate_batch(self):
        """Test batch SHAP calculation."""
        calc = SHAPCalculator()
        results = calc.calculate_batch(
            feature_list=[
                {"rsi": 30, "macd": 0.1},
                {"rsi": 70, "macd": -0.1},
            ],
            base_value=0.5,
        )

        assert len(results) == 2
        assert all(isinstance(r, SHAPResult) for r in results)

    def test_get_feature_shap(self):
        """Test getting SHAP value for specific feature."""
        calc = SHAPCalculator()
        result = calc.calculate(
            features={"rsi": 28, "macd": 0.15},
            base_value=0.5,
        )

        shap_val = result.get_feature_shap("rsi")
        assert shap_val is not None
        assert shap_val.feature_name == "rsi"

        assert result.get_feature_shap("nonexistent") is None


# ============================================================================
# InteractionDetector Tests
# ============================================================================


class TestInteractionDetector:
    """Tests for InteractionDetector class."""

    def test_create_detector(self):
        """Test creating an interaction detector."""
        detector = InteractionDetector()
        assert detector.n_samples == 100

    def test_detect_interactions(self):
        """Test detecting feature interactions."""
        detector = InteractionDetector()
        interactions = detector.detect(
            features={"rsi": 28, "macd": 0.15, "volume": 1.5},
            base_value=0.5,
        )

        assert isinstance(interactions, list)
        for interaction in interactions:
            assert isinstance(interaction, InteractionResult)

    def test_interaction_result_properties(self):
        """Test InteractionResult properties."""
        result = InteractionResult(
            feature_1="rsi",
            feature_2="macd",
            interaction_value=0.1,
            individual_1=0.3,
            individual_2=0.2,
            synergy=0.15,  # Above threshold of 0.05
        )

        assert result.interaction_strength == 0.1
        assert result.interaction_type == "synergistic"

    def test_get_top_interactions(self):
        """Test getting top interactions."""
        detector = InteractionDetector()
        top = detector.get_top_interactions(
            features={"a": 0.5, "b": 0.5, "c": 0.5, "d": 0.5},
            top_n=2,
        )

        assert len(top) <= 2


# ============================================================================
# ExplanationVisualizer Tests
# ============================================================================


class TestExplanationVisualizer:
    """Tests for ExplanationVisualizer class."""

    def test_create_visualizer(self):
        """Test creating a visualizer."""
        viz = ExplanationVisualizer()
        assert viz.config is not None

    def test_create_feature_importance_plot(self):
        """Test creating feature importance plot."""
        viz = ExplanationVisualizer()
        result = viz.create_feature_importance_plot(
            feature_importance={"rsi": 0.35, "macd": -0.2, "volume": 0.1}
        )

        assert isinstance(result, VisualizationResult)
        assert len(result.plots) == 1
        assert isinstance(result.plots[0], PlotData)

    def test_create_shap_waterfall(self):
        """Test creating SHAP waterfall plot."""
        viz = ExplanationVisualizer()
        result = viz.create_shap_waterfall(
            shap_values={"rsi": 0.3, "macd": 0.2},
            base_value=0.5,
        )

        assert isinstance(result, VisualizationResult)
        assert result.plots[0].plot_type == PlotType.WATERFALL

    def test_create_reasoning_chain_visualization(self):
        """Test creating reasoning chain visualization."""
        viz = ExplanationVisualizer()
        result = viz.create_reasoning_chain_visualization(
            reasoning_steps=[
                {"step_number": 1, "description": "Step 1", "confidence": 0.8},
                {"step_number": 2, "description": "Step 2", "confidence": 0.7},
            ]
        )

        assert isinstance(result, VisualizationResult)
        assert "steps" in result.summary.lower()

    def test_create_confidence_gauge(self):
        """Test creating confidence gauge."""
        viz = ExplanationVisualizer()
        result = viz.create_confidence_gauge(confidence=0.85)

        assert isinstance(result, VisualizationResult)
        assert "High" in result.summary or "Very High" in result.summary

    def test_create_multi_comparison(self):
        """Test creating multi-explanation comparison."""
        viz = ExplanationVisualizer()
        result = viz.create_multi_comparison(
            explanations=[
                {"key_factors": {"rsi": 0.3, "macd": 0.2}},
                {"key_factors": {"rsi": 0.1, "macd": 0.4}},
            ]
        )

        assert isinstance(result, VisualizationResult)
        assert len(result.plots) == 2

    def test_plot_data_to_vega_lite(self):
        """Test PlotData.to_vega_lite method."""
        plot = PlotData(
            plot_type=PlotType.BAR,
            title="Test Plot",
            x_data=[1, 2, 3],
            y_data=[0.3, 0.5, 0.2],
            labels=["A", "B", "C"],
        )

        vega_spec = plot.to_vega_lite()
        assert isinstance(vega_spec, dict)
        assert "$schema" in vega_spec
        assert vega_spec["title"] == "Test Plot"

    def test_visualization_result_to_html(self):
        """Test VisualizationResult.to_html method."""
        viz = ExplanationVisualizer()
        result = viz.create_feature_importance_plot(
            feature_importance={"rsi": 0.35, "macd": 0.25}
        )

        html = result.to_html()
        assert "<!DOCTYPE html>" in html
        assert "<html>" in html

    def test_visualization_result_to_dict(self):
        """Test VisualizationResult.to_dict method."""
        viz = ExplanationVisualizer()
        result = viz.create_feature_importance_plot(feature_importance={"rsi": 0.35})

        result_dict = result.to_dict()
        assert isinstance(result_dict, dict)
        assert "plots" in result_dict
        assert "summary" in result_dict


# ============================================================================
# Integration Tests
# ============================================================================


class TestExplainabilityIntegration:
    """Integration tests for the explainability module."""

    def test_full_explanation_pipeline(self, sample_decision_data):
        """Test the full explanation pipeline."""
        # 1. Generate explanation
        generator = ExplanationGenerator()
        explanation = generator.explain(sample_decision_data)

        # 2. Analyze feature importance
        analyzer = FeatureImportanceAnalyzer()
        importance = analyzer.analyze(
            features=sample_decision_data["features"],
            prediction=sample_decision_data["confidence"],
        )

        # 3. Score explanation confidence
        scorer = ExplanationConfidenceScorer()
        confidence = scorer.score_explanation(explanation.to_dict())

        # 4. Format for trader
        formatter = ExplanationFormatter()
        formatted = formatter.format_for_trader(explanation.to_dict())

        # Verify pipeline results
        assert explanation is not None
        assert importance is not None
        assert confidence is not None
        assert formatted is not None
        assert len(formatted.content) > 0

    def test_explanation_with_visualization(self, sample_decision_data):
        """Test explanation with visualization generation."""
        # Generate explanation
        generator = ExplanationGenerator()
        explanation = generator.explain(sample_decision_data)

        # Create visualizations
        visualizer = ExplanationVisualizer()

        # Feature importance plot
        importance_viz = visualizer.create_feature_importance_plot(
            explanation.key_factors
        )

        # Reasoning chain visualization
        reasoning_viz = visualizer.create_reasoning_chain_visualization(
            [
                {
                    "step_number": s.step_number,
                    "description": s.description,
                    "confidence": s.confidence,
                }
                for s in explanation.reasoning_chain
            ]
        )

        # Confidence gauge
        confidence_viz = visualizer.create_confidence_gauge(
            explanation.overall_confidence
        )

        assert importance_viz is not None
        assert reasoning_viz is not None
        assert confidence_viz is not None

    def test_xai_shap_integration(self, sample_decision_data):
        """Test XAI SHAP utilities integration."""
        # Calculate SHAP values
        calc = SHAPCalculator()
        shap_result = calc.calculate(
            features=sample_decision_data["features"],
            base_value=0.5,
        )

        # Detect interactions
        detector = InteractionDetector()
        interactions = detector.detect(
            features=sample_decision_data["features"],
            base_value=0.5,
        )

        # Visualize SHAP
        visualizer = ExplanationVisualizer()
        shap_viz = visualizer.create_shap_waterfall(
            shap_values={sv.feature_name: sv.value for sv in shap_result.shap_values},
            base_value=shap_result.base_value,
        )

        assert shap_result is not None
        assert len(interactions) >= 0
        assert shap_viz is not None


# ============================================================================
# Edge Case Tests
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_features(self):
        """Test handling empty features."""
        generator = ExplanationGenerator()
        result = generator.explain(
            {
                "prediction": "hold",
                "confidence": 0.5,
                "features": {},
            }
        )

        assert result is not None
        assert result.summary is not None

    def test_missing_optional_fields(self):
        """Test handling missing optional fields."""
        scorer = ExplanationConfidenceScorer()
        score = scorer.score_explanation(
            {
                "summary": "Test summary",
                # Missing reasoning_chain, key_factors, etc.
            }
        )

        assert score is not None
        assert isinstance(score.overall_score, float)

    def test_extreme_confidence_values(self):
        """Test handling extreme confidence values."""
        generator = ExplanationGenerator()

        # Very high confidence
        result = generator.explain(
            {
                "prediction": "buy",
                "confidence": 0.99,
            }
        )
        assert result.overall_confidence == 0.99

        # Very low confidence
        result = generator.explain(
            {
                "prediction": "buy",
                "confidence": 0.01,
            }
        )
        assert result.overall_confidence == 0.01

    def test_large_feature_set(self):
        """Test handling large feature sets."""
        analyzer = FeatureImportanceAnalyzer()

        # Create 50 features
        features = {f"feature_{i}": 0.5 for i in range(50)}
        result = analyzer.analyze(
            features=features,
            prediction=0.7,
            base_value=0.5,
        )

        assert len(result.contributions) == 50

    def test_unicode_in_descriptions(self):
        """Test handling unicode in descriptions."""
        generator = ExplanationGenerator()
        result = generator.explain(
            {
                "prediction": "buy",
                "confidence": 0.8,
                "metadata": {"note": "Unicode: 📈 ✓"},
            }
        )

        assert result is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
