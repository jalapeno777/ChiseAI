"""Tests for ShadowModeManager in model_validator.py.

Tests shadow mode lifecycle, prediction recording, comparison reports,
and session management.
"""


from ml.validation.model_validator import (
    ShadowComparisonResult,
    ShadowModeConfig,
    ShadowModeManager,
)


class TestShadowModeManagerInit:
    """Tests for ShadowModeManager initialization."""

    def test_default_initialization(self, mock_influx_logger):
        """Test default initialization."""
        mgr = ShadowModeManager(influx_logger=mock_influx_logger)
        assert mgr._config.enabled is True
        assert mgr._config.duration_hours == 24.0
        assert len(mgr._active_sessions) == 0
        assert len(mgr._comparison_history) == 0

    def test_custom_config(self, shadow_config, mock_influx_logger):
        """Test initialization with custom config."""
        mgr = ShadowModeManager(config=shadow_config, influx_logger=mock_influx_logger)
        assert mgr._config.min_samples_required == 100

    def test_disabled_config(self, mock_influx_logger):
        """Test initialization with disabled shadow mode."""
        config = ShadowModeConfig(enabled=False)
        mgr = ShadowModeManager(config=config, influx_logger=mock_influx_logger)
        assert mgr._config.enabled is False


class TestShadowModeStartStop:
    """Tests for starting and stopping shadow mode sessions."""

    def test_start_shadow_mode(self, shadow_config, mock_influx_logger):
        """Test starting a shadow mode session."""
        mgr = ShadowModeManager(config=shadow_config, influx_logger=mock_influx_logger)
        session_id = mgr.start_shadow_mode("v1_champion", "v2_candidate")
        assert session_id != ""
        assert session_id.startswith("shadow_")
        assert session_id in mgr._active_sessions

    def test_start_disabled_returns_empty(self, mock_influx_logger):
        """Test starting shadow mode when disabled returns empty string."""
        config = ShadowModeConfig(enabled=False)
        mgr = ShadowModeManager(config=config, influx_logger=mock_influx_logger)
        session_id = mgr.start_shadow_mode("v1", "v2")
        assert session_id == ""

    def test_end_shadow_mode(self, shadow_config, mock_influx_logger):
        """Test ending a shadow mode session."""
        mgr = ShadowModeManager(config=shadow_config, influx_logger=mock_influx_logger)
        session_id = mgr.start_shadow_mode("v1", "v2")
        assert mgr.end_shadow_mode(session_id) is True
        assert session_id not in mgr._active_sessions

    def test_end_nonexistent_session(self, shadow_config, mock_influx_logger):
        """Test ending a nonexistent session returns False."""
        mgr = ShadowModeManager(config=shadow_config, influx_logger=mock_influx_logger)
        assert mgr.end_shadow_mode("nonexistent") is False

    def test_is_shadow_mode_active(self, shadow_config, mock_influx_logger):
        """Test checking if shadow mode is active."""
        mgr = ShadowModeManager(config=shadow_config, influx_logger=mock_influx_logger)
        session_id = mgr.start_shadow_mode("v1", "v2")
        assert mgr.is_shadow_mode_active(session_id) is True
        mgr.end_shadow_mode(session_id)
        assert mgr.is_shadow_mode_active(session_id) is False

    def test_is_shadow_mode_active_nonexistent(self, shadow_config, mock_influx_logger):
        """Test is_active returns False for nonexistent session."""
        mgr = ShadowModeManager(config=shadow_config, influx_logger=mock_influx_logger)
        assert mgr.is_shadow_mode_active("nonexistent") is False


class TestShadowModeRecordPrediction:
    """Tests for recording predictions in shadow mode."""

    def test_record_prediction(self, shadow_config, mock_influx_logger):
        """Test recording a prediction from both models."""
        mgr = ShadowModeManager(config=shadow_config, influx_logger=mock_influx_logger)
        session_id = mgr.start_shadow_mode("v1", "v2")

        mgr.record_prediction(
            session_id=session_id,
            signal_data={"symbol": "BTC/USDT", "price": 50000.0},
            champion_prediction={"direction": 1, "confidence": 0.8},
            candidate_prediction={"direction": 1, "confidence": 0.85},
        )

        session = mgr._active_sessions[session_id]
        assert session["sample_count"] == 1
        assert len(session["champion_predictions"]) == 1
        assert len(session["candidate_predictions"]) == 1

    def test_record_prediction_nonexistent_session(
        self, shadow_config, mock_influx_logger
    ):
        """Test recording prediction for nonexistent session does nothing."""
        mgr = ShadowModeManager(config=shadow_config, influx_logger=mock_influx_logger)
        # Should not raise
        mgr.record_prediction(
            session_id="nonexistent",
            signal_data={},
            champion_prediction={},
            candidate_prediction={},
        )

    def test_record_multiple_predictions(self, shadow_config, mock_influx_logger):
        """Test recording multiple predictions."""
        mgr = ShadowModeManager(config=shadow_config, influx_logger=mock_influx_logger)
        session_id = mgr.start_shadow_mode("v1", "v2")

        for i in range(10):
            mgr.record_prediction(
                session_id=session_id,
                signal_data={"index": i},
                champion_prediction={"direction": 1},
                candidate_prediction={"direction": 1},
            )

        session = mgr._active_sessions[session_id]
        assert session["sample_count"] == 10


class TestShadowModeComparison:
    """Tests for shadow mode comparison report generation."""

    def test_get_comparison_no_outcomes(self, shadow_config, mock_influx_logger):
        """Test comparison without actual outcomes (simulated metrics)."""
        mgr = ShadowModeManager(config=shadow_config, influx_logger=mock_influx_logger)
        session_id = mgr.start_shadow_mode("v1", "v2")

        # Record some predictions
        for i in range(50):
            mgr.record_prediction(
                session_id=session_id,
                signal_data={"index": i},
                champion_prediction={"direction": 1},
                candidate_prediction={"direction": 1},
            )

        result = mgr.get_comparison(session_id)
        assert result is not None
        assert result.sample_count == 50
        assert "accuracy" in result.champion_metrics
        assert "accuracy" in result.candidate_metrics
        assert result.recommendation == "pending"  # < min_samples

    def test_get_comparison_nonexistent_session(
        self, shadow_config, mock_influx_logger
    ):
        """Test comparison for nonexistent session returns None."""
        mgr = ShadowModeManager(config=shadow_config, influx_logger=mock_influx_logger)
        assert mgr.get_comparison("nonexistent") is None

    def test_get_comparison_promote_recommendation(
        self, shadow_config, mock_influx_logger
    ):
        """Test comparison recommendation is 'promote' when all deltas positive."""
        mgr = ShadowModeManager(config=shadow_config, influx_logger=mock_influx_logger)
        session_id = mgr.start_shadow_mode("v1", "v2")

        # Record enough predictions to meet min_samples_required
        for i in range(150):
            mgr.record_prediction(
                session_id=session_id,
                signal_data={"index": i},
                champion_prediction={"direction": 1},
                candidate_prediction={"direction": 1},
            )

        # Without outcomes, both get simulated metrics (same values)
        # So deltas will be 0 for all metrics -> recommendation = "extend"
        result = mgr.get_comparison(session_id)
        assert result is not None
        assert result.sample_count == 150

    def test_comparison_with_actual_outcomes(self, shadow_config, mock_influx_logger):
        """Test comparison with actual outcomes provided."""
        mgr = ShadowModeManager(config=shadow_config, influx_logger=mock_influx_logger)
        session_id = mgr.start_shadow_mode("v1", "v2")

        # Record predictions with directional info
        for i in range(150):
            direction = 1 if i % 3 != 0 else -1
            mgr.record_prediction(
                session_id=session_id,
                signal_data={"index": i},
                champion_prediction={"direction": direction},
                candidate_prediction={"direction": 1 if i % 2 == 0 else -1},
            )

        # Provide actual outcomes
        outcomes = [{"direction": 1 if i % 3 != 0 else -1} for i in range(150)]
        result = mgr.get_comparison(session_id, actual_outcomes=outcomes)
        assert result is not None
        assert result.sample_count == 150
        assert result.recommendation in ("promote", "reject", "extend")

    def test_comparison_stored_in_history(self, shadow_config, mock_influx_logger):
        """Test that comparison results are stored in history."""
        mgr = ShadowModeManager(config=shadow_config, influx_logger=mock_influx_logger)
        session_id = mgr.start_shadow_mode("v1", "v2")

        for i in range(50):
            mgr.record_prediction(
                session_id=session_id,
                signal_data={"index": i},
                champion_prediction={"direction": 1},
                candidate_prediction={"direction": 1},
            )

        mgr.get_comparison(session_id)
        assert len(mgr._comparison_history) == 1

    def test_get_comparison_history(self, shadow_config, mock_influx_logger):
        """Test retrieving comparison history."""
        mgr = ShadowModeManager(config=shadow_config, influx_logger=mock_influx_logger)

        for run in range(3):
            session_id = mgr.start_shadow_mode("v1", "v2")
            for i in range(50):
                mgr.record_prediction(
                    session_id=session_id,
                    signal_data={"index": i},
                    champion_prediction={"direction": 1},
                    candidate_prediction={"direction": 1},
                )
            mgr.get_comparison(session_id)

        history = mgr.get_comparison_history()
        assert len(history) == 3

    def test_comparison_history_limit(self, shadow_config, mock_influx_logger):
        """Test comparison history limit parameter."""
        mgr = ShadowModeManager(config=shadow_config, influx_logger=mock_influx_logger)

        for run in range(10):
            session_id = mgr.start_shadow_mode("v1", "v2")
            for i in range(50):
                mgr.record_prediction(
                    session_id=session_id,
                    signal_data={"index": i},
                    champion_prediction={"direction": 1},
                    candidate_prediction={"direction": 1},
                )
            mgr.get_comparison(session_id)

        history = mgr.get_comparison_history(limit=3)
        assert len(history) == 3


class TestShadowComparisonResult:
    """Tests for ShadowComparisonResult dataclass."""

    def test_to_dict(self):
        """Test ShadowComparisonResult serialization."""
        result = ShadowComparisonResult(
            champion_metrics={"accuracy": 0.70},
            candidate_metrics={"accuracy": 0.75},
            delta={
                "accuracy": 0.05,
                "precision": 0.0,
                "recall": 0.0,
                "f1": 0.0,
                "win_rate": 0.0,
            },
            sample_count=100,
            duration_hours=1.0,
            recommendation="promote",
        )
        d = result.to_dict()
        assert d["recommendation"] == "promote"
        assert d["sample_count"] == 100
        assert d["champion_metrics"]["accuracy"] == 0.70


class TestShadowModeCalculateMetrics:
    """Tests for ShadowModeManager._calculate_metrics internal method."""

    def test_empty_predictions(self, shadow_config, mock_influx_logger):
        """Test calculating metrics with empty predictions."""
        mgr = ShadowModeManager(config=shadow_config, influx_logger=mock_influx_logger)
        metrics = mgr._calculate_metrics([], None)
        assert metrics["accuracy"] == 0.0
        assert metrics["precision"] == 0.0

    def test_predictions_without_outcomes(self, shadow_config, mock_influx_logger):
        """Test calculating metrics without outcomes returns simulated."""
        mgr = ShadowModeManager(config=shadow_config, influx_logger=mock_influx_logger)
        predictions = [{"signal": {}, "prediction": {"direction": 1}}]
        metrics = mgr._calculate_metrics(predictions, None)
        # Should return simulated metrics
        assert metrics["accuracy"] == 0.70
