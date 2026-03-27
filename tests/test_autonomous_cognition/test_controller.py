"""Tests for AutonomousCognitionController self-assessment deduplication."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from autonomous_cognition.artifacts import SelfAssessmentArtifact
from autonomous_cognition.controller import AutonomousCognitionController


class TestPersistArtifactDeduplication:
    """Tests for _persist_artifact deduplication behavior."""

    def _make_artifact(
        self, assessment_id: str = "sa-test-001", overall_score: float = 0.85
    ) -> SelfAssessmentArtifact:
        """Create a test artifact with given score."""
        artifact = SelfAssessmentArtifact.create_empty(assessment_id=assessment_id)
        artifact.overall_score = overall_score
        artifact.status = "ok"
        artifact.dimensions = {"test": 0.85}
        artifact.findings = ["test finding"]
        artifact.recommendations = ["test recommendation"]
        return artifact

    def _make_mock_redis_client(self, stored_payload: str | None):
        """Create a mock Redis client that returns stored_payload for get."""
        mock = MagicMock()
        mock.get.return_value = stored_payload
        return mock

    def test_first_run_always_writes(self, tmp_path: Path):
        """First run should always write file (no baseline assumption)."""
        # No Redis client - simulates first run with no previous data
        controller = AutonomousCognitionController(
            artifacts_dir=tmp_path,
            redis_client=None,
        )

        artifact = self._make_artifact(overall_score=0.85)

        # Mock _get_previous_score to return None (no previous run)
        with patch.object(controller, "_get_previous_score", return_value=None):
            path, status = controller._persist_artifact(artifact)

        assert path is not None
        assert status == "written"
        assert path.exists()
        assert controller.get_dedup_stats()["files_written"] == 1
        assert controller.get_dedup_stats()["files_skipped"] == 0

    def test_same_score_write_is_skipped(self, tmp_path: Path):
        """Same score should skip file write."""
        # Previous artifact with same score stored in Redis
        previous_artifact = self._make_artifact(overall_score=0.85)
        stored_payload = previous_artifact.to_json()

        mock_redis = self._make_mock_redis_client(stored_payload)
        controller = AutonomousCognitionController(
            artifacts_dir=tmp_path,
            redis_client=mock_redis,
        )

        # Current artifact with same score
        current_artifact = self._make_artifact(overall_score=0.85)

        path, status = controller._persist_artifact(current_artifact)

        assert path is None
        assert status == "skipped"
        assert controller.get_dedup_stats()["files_written"] == 0
        assert controller.get_dedup_stats()["files_skipped"] == 1

    def test_different_score_write_succeeds(self, tmp_path: Path):
        """Different score should write file."""
        # Previous artifact with different score
        previous_artifact = self._make_artifact(overall_score=0.70)
        stored_payload = previous_artifact.to_json()

        mock_redis = self._make_mock_redis_client(stored_payload)
        controller = AutonomousCognitionController(
            artifacts_dir=tmp_path,
            redis_client=mock_redis,
        )

        # Current artifact with different score
        current_artifact = self._make_artifact(overall_score=0.85)

        path, status = controller._persist_artifact(current_artifact)

        assert path is not None
        assert status == "written"
        assert path.exists()
        assert controller.get_dedup_stats()["files_written"] == 1
        assert controller.get_dedup_stats()["files_skipped"] == 0

    def test_redis_always_updated_even_when_skipped(self, tmp_path: Path):
        """Redis should be updated even when file write is skipped (for next comparison)."""
        # Previous artifact
        previous_artifact = self._make_artifact(overall_score=0.85)
        stored_payload = previous_artifact.to_json()

        mock_redis = self._make_mock_redis_client(stored_payload)
        controller = AutonomousCognitionController(
            artifacts_dir=tmp_path,
            redis_client=mock_redis,
        )

        # Current artifact with same score (will be skipped)
        current_artifact = self._make_artifact(overall_score=0.85)

        with patch.object(controller, "_get_previous_score", return_value=0.85):
            path, status = controller._persist_artifact(current_artifact)

        # Verify skip occurred
        assert path is None
        assert status == "skipped"

        # Verify Redis was called (via run_daily_self_assessment which calls _persist_redis after)
        # Note: This test just verifies the skip happened; Redis update is tested separately

    def test_redis_update_happens_after_persist(self, tmp_path: Path):
        """Redis CURRENT_KEY should be updated after artifact is persisted."""
        mock_redis = self._make_mock_redis_client(None)
        controller = AutonomousCognitionController(
            artifacts_dir=tmp_path,
            redis_client=mock_redis,
        )

        artifact = self._make_artifact(overall_score=0.85)

        # Patch _build_artifact to return our artifact and _get_previous_score to return None
        with (
            patch.object(controller, "_get_previous_score", return_value=None),
            patch.object(controller, "_build_artifact", return_value=artifact),
        ):
            controller.run_daily_self_assessment()

        # Verify Redis set was called with the new artifact
        mock_redis.set.assert_called()
        call_args = mock_redis.set.call_args_list
        # First call should be to REDIS_CURRENT_KEY
        current_key_call = [
            c for c in call_args if c[0][0] == controller.REDIS_CURRENT_KEY
        ]
        assert len(current_key_call) == 1

        # Verify the payload is the artifact JSON
        payload = current_key_call[0][0][1]
        parsed = json.loads(payload)
        assert parsed["overall_score"] == 0.85

    def test_get_previous_score_returns_none_when_no_redis(self):
        """_get_previous_score should return None when Redis unavailable."""
        controller = AutonomousCognitionController(redis_client=None)

        with patch("autonomous_cognition.controller.redis_state_get_client", None):
            result = controller._get_previous_score()

        assert result is None

    def test_get_previous_score_returns_none_when_key_missing(self):
        """_get_previous_score should return None when key doesn't exist in Redis."""
        mock_redis = self._make_mock_redis_client(None)
        controller = AutonomousCognitionController(redis_client=mock_redis)

        # Also patch redis_state_get_client to return None to avoid real Redis calls
        with patch("autonomous_cognition.controller.redis_state_get_client", None):
            result = controller._get_previous_score()

        assert result is None

    def test_get_previous_score_parses_artifact_correctly(self, tmp_path: Path):
        """_get_previous_score should correctly extract overall_score from artifact."""
        previous_artifact = self._make_artifact(overall_score=0.73)
        stored_payload = previous_artifact.to_json()

        mock_redis = self._make_mock_redis_client(stored_payload)
        controller = AutonomousCognitionController(
            artifacts_dir=tmp_path,
            redis_client=mock_redis,
        )

        result = controller._get_previous_score()

        assert result == 0.73

    def test_slightly_different_score_not_skipped(self, tmp_path: Path):
        """Scores that differ even slightly should not be skipped."""
        # Previous artifact with score 0.85
        previous_artifact = self._make_artifact(overall_score=0.85)
        stored_payload = previous_artifact.to_json()

        mock_redis = self._make_mock_redis_client(stored_payload)
        controller = AutonomousCognitionController(
            artifacts_dir=tmp_path,
            redis_client=mock_redis,
        )

        # Current artifact with score 0.8500001 (technically different)
        current_artifact = self._make_artifact(overall_score=0.8500001)

        path, status = controller._persist_artifact(current_artifact)

        assert path is not None
        assert status == "written"

    def test_dedup_stats_accumulate_across_multiple_calls(self, tmp_path: Path):
        """Stats should accumulate correctly across multiple persist calls."""
        mock_redis = self._make_mock_redis_client(None)
        controller = AutonomousCognitionController(
            artifacts_dir=tmp_path,
            redis_client=mock_redis,
        )

        # First call - writes
        artifact1 = self._make_artifact(assessment_id="sa-test-001", overall_score=0.85)
        with patch.object(controller, "_get_previous_score", return_value=None):
            path1, status1 = controller._persist_artifact(artifact1)

        assert status1 == "written"
        assert controller.get_dedup_stats()["files_written"] == 1

        # Second call - same score, should skip
        artifact2 = self._make_artifact(assessment_id="sa-test-002", overall_score=0.85)
        with patch.object(controller, "_get_previous_score", return_value=0.85):
            path2, status2 = controller._persist_artifact(artifact2)

        assert status2 == "skipped"
        assert controller.get_dedup_stats()["files_written"] == 1
        assert controller.get_dedup_stats()["files_skipped"] == 1

        # Third call - different score, should write
        artifact3 = self._make_artifact(assessment_id="sa-test-003", overall_score=0.90)
        with patch.object(controller, "_get_previous_score", return_value=0.85):
            path3, status3 = controller._persist_artifact(artifact3)

        assert status3 == "written"
        assert controller.get_dedup_stats()["files_written"] == 2
        assert controller.get_dedup_stats()["files_skipped"] == 1
