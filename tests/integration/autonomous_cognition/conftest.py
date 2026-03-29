"""Pytest fixtures for autonomous cognition integration tests.

Provides mocked Redis, Qdrant, Discord, and full cycle integration fixtures.
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))


# =============================================================================
# Mock Redis Fixture
# =============================================================================


@pytest.fixture
def mock_redis():
    """Create a mock Redis client with common operations.

    Returns a Mock with async ping and basic key-value operations.
    """
    redis = Mock()
    redis.ping = AsyncMock(return_value=True)
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.setex = AsyncMock(return_value=True)
    redis.incr = AsyncMock(return_value=1)
    redis.exists = AsyncMock(return_value=0)
    redis.delete = AsyncMock(return_value=1)
    redis.expire = AsyncMock(return_value=True)
    redis.hget = AsyncMock(return_value=None)
    redis.hset = AsyncMock(return_value=True)
    redis.hgetall = AsyncMock(return_value={})
    redis.keys = AsyncMock(return_value=[])
    redis.smembers = AsyncMock(return_value=set())
    redis.sismember = AsyncMock(return_value=False)
    redis.zadd = AsyncMock(return_value=1)
    redis.zrange = AsyncMock(return_value=[])
    redis.zrem = AsyncMock(return_value=0)
    redis.lpush = AsyncMock(return_value=1)
    redis.rpush = AsyncMock(return_value=1)
    redis.lrange = AsyncMock(return_value=[])
    redis.lpop = AsyncMock(return_value=None)
    redis.rpop = AsyncMock(return_value=None)
    redis.llen = AsyncMock(return_value=0)
    redis.scan = AsyncMock(return_value=(0, []))
    redis.info = AsyncMock(return_value={})
    return redis


# =============================================================================
# Mock Qdrant Fixture
# =============================================================================


class MockQdrantCollection:
    """Mock Qdrant collection for testing."""

    def __init__(self, name: str = "test_collection"):
        self.name = name
        self.points: dict[str, dict[str, Any]] = {}

    def upsert(self, points: list[dict[str, Any]]) -> None:
        """Mock upsert operation."""
        for point in points:
            self.points[point["id"]] = point

    def retrieve(self, ids: list[str]) -> list[dict[str, Any]]:
        """Mock retrieve operation."""
        return [self.points[mid] for mid in ids if mid in self.points]

    def search(
        self, query_vector: list[float], limit: int = 10
    ) -> list[dict[str, Any]]:
        """Mock search operation - returns empty for testing."""
        return []


class MockQdrantClient:
    """Mock Qdrant client with in-memory mode for testing.

    Supports collection creation, upsert, retrieve, and search operations.
    """

    def __init__(self, location: str = ":memory:", **kwargs):
        self.location = location
        self.collections: dict[str, MockQdrantCollection] = {}
        self.__VECTOR_SIZE = 384  # Default vector size

    def get_collections(self) -> dict[str, Any]:
        """Mock get_collections returning list of collection names."""
        return {
            "collections": [{"name": col.name} for col in self.collections.values()]
        }

    def get_collection(self, collection_name: str) -> dict[str, Any]:
        """Mock get_collection with status."""
        if collection_name in self.collections:
            return {"status": "green", "vectors_count": 0}
        return {"status": "available", "vectors_count": 0}

    def create_collection(
        self, collection_name: str, vectors_config: dict[str, Any]
    ) -> bool:
        """Mock create_collection."""
        if collection_name not in self.collections:
            self.collections[collection_name] = MockQdrantCollection(collection_name)
        return True

    def delete_collection(self, collection_name: str) -> bool:
        """Mock delete_collection."""
        if collection_name in self.collections:
            del self.collections[collection_name]
        return True

    def upsert(self, collection_name: str, points: list[dict[str, Any]]) -> None:
        """Mock upsert to a collection."""
        if collection_name not in self.collections:
            self.collections[collection_name] = MockQdrantCollection(collection_name)
        self.collections[collection_name].upsert(points)

    def retrieve(self, collection_name: str, ids: list[str]) -> list[dict[str, Any]]:
        """Mock retrieve from a collection."""
        if collection_name in self.collections:
            return self.collections[collection_name].retrieve(ids)
        return []

    def search(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int = 10,
        **kwargs,
    ) -> list[dict[str, Any]]:
        """Mock search in a collection."""
        if collection_name in self.collections:
            return self.collections[collection_name].search(query_vector, limit)
        return []


@pytest.fixture
def mock_qdrant():
    """Create a mock Qdrant client in in-memory mode.

    Returns a MockQdrantClient instance with in-memory storage.
    """
    return MockQdrantClient(location=":memory:")


# =============================================================================
# Mock Discord Notifier Fixture
# =============================================================================


@pytest.fixture
def mock_discord_notifier():
    """Create a mock Discord notifier with AsyncMock for async methods.

    Returns a DiscordNotifier-like mock with async notification methods.
    """
    notifier = Mock()
    notifier.notify_autocog_event = AsyncMock(return_value=True)
    notifier.notify_self_assessment = AsyncMock(return_value=True)
    notifier.notify_decision = AsyncMock(return_value=True)
    notifier.notify_reflection = AsyncMock(return_value=True)
    notifier.send_digest = AsyncMock(return_value=True)
    notifier.add_to_digest = Mock(return_value=True)
    notifier.should_flush_digest = Mock(return_value=False)
    notifier.should_notify_for_cycle_event = Mock(return_value=True)
    notifier.should_notify_for_assessment = Mock(return_value=True)
    notifier.close = AsyncMock(return_value=None)
    notifier._is_enabled = Mock(return_value=True)
    notifier._is_duplicate = Mock(return_value=False)
    notifier._mark_sent = Mock(return_value=None)
    notifier._low_severity_buffer: list[dict[str, Any]] = []
    return notifier


# =============================================================================
# Mock BeliefStore Fixture
# =============================================================================


@pytest.fixture
def mock_belief_store():
    """Create a mock BeliefStore for testing.

    Returns a Mock with belief store operations.
    """
    store = Mock()
    store.list_active = Mock(return_value=[])
    store.get = Mock(return_value=None)
    store.put = Mock(return_value=True)
    store.delete = Mock(return_value=True)
    store.update = Mock(return_value=True)
    return store


# =============================================================================
# Mock ChampionChallengerEngine Fixture
# =============================================================================


@pytest.fixture
def mock_champion_challenger_engine():
    """Create a mock ChampionChallengerEngine for testing.

    Returns a Mock with champion/challenger evaluation methods.
    """
    engine = Mock()

    # Mock evaluate_candidate to return a promotion outcome
    mock_outcome = Mock()
    mock_outcome.promoted = True
    mock_outcome.reason = "passed_gates"
    mock_outcome.version_id = "v1.0.0"
    engine.evaluate_candidate = Mock(return_value=mock_outcome)

    # Mock registry methods
    engine._registry = Mock()
    engine._registry.get_version = Mock(return_value=None)
    engine._registry.get_rollback_target = Mock(return_value=None)
    engine._registry.promote_to_champion = Mock(return_value=True)

    return engine


# =============================================================================
# Mock HypothesisGenerator Fixture
# =============================================================================


@pytest.fixture
def mock_hypothesis_generator():
    """Create a mock HypothesisGenerator for testing.

    Returns a Mock with hypothesis generation methods.
    """
    generator = Mock()

    # Create a mock hypothesis
    mock_hypothesis = Mock()
    mock_hypothesis.hypothesis_id = "hyp-test-001"
    mock_hypothesis.target_component = "test_strategy"
    mock_hypothesis.to_dict = Mock(
        return_value={
            "hypothesis_id": "hyp-test-001",
            "target_component": "test_strategy",
        }
    )

    generator.generate = Mock(return_value=[mock_hypothesis])
    return generator


# =============================================================================
# Mock Experiment Lab (PortfolioPolicyLab) Fixture
# =============================================================================


@pytest.fixture
def mock_portfolio_policy_lab():
    """Create a mock PortfolioPolicyLab for testing.

    Returns a Mock with experiment run methods.
    """
    lab = Mock()

    # Create a mock experiment result
    mock_result = Mock()
    mock_result.to_metrics = Mock(
        return_value={
            "sharpe": 1.2,
            "sortino": 0.9,
            "drawdown": 0.15,
            "ece": 0.08,
            "passed": True,
        }
    )
    mock_result.hypothesis_id = "hyp-test-001"

    lab.run = Mock(return_value=mock_result)
    return lab


# =============================================================================
# AutonomousCognitionFullCycle Fixture with All Mocks Wired Up
# =============================================================================


@pytest.fixture
def autocog_full_cycle(mock_redis, mock_qdrant, mock_discord_notifier):
    """Create an AutonomousCognitionFullCycle instance with all mocks wired up.

    This fixture provides a fully mocked cycle for integration testing.
    """
    from unittest.mock import AsyncMock as AMock
    from unittest.mock import patch

    from autonomous_cognition.autonomy_tuner import AutonomyTuner
    from autonomous_cognition.beliefs.consistency_checker import (
        BeliefConsistencyChecker,
    )
    from autonomous_cognition.beliefs.revision_engine import BeliefRevisionEngine
    from autonomous_cognition.beliefs.store import BeliefStore
    from autonomous_cognition.constitution_audit import ConstitutionAuditEngine
    from autonomous_cognition.controller import AutonomousCognitionController
    from autonomous_cognition.experiments.champion_challenger import (
        ChampionChallengerEngine,
    )
    from autonomous_cognition.experiments.hypothesis_generator import (
        HypothesisGenerator,
    )
    from autonomous_cognition.experiments.portfolio_policy_lab import PortfolioPolicyLab
    from autonomous_cognition.full_cycle import AutonomousCognitionFullCycle
    from autonomous_cognition.runtime_integration import NeuroSymbolicRuntimeIntegrator
    from governance.notifications.discord_notifier import DiscordNotifier

    # Create mocks for each component
    mock_controller = Mock(spec=AutonomousCognitionController)
    mock_controller._redis_client = mock_redis
    mock_controller._qdrant_client = mock_qdrant

    # Mock run_daily_self_assessment to return a valid assessment
    mock_assessment = Mock()
    mock_assessment.status = "ok"
    mock_assessment.overall_score = 0.85
    mock_assessment.findings = ["System is healthy", "Memory usage normal"]
    mock_assessment.created_at = datetime.now(UTC).isoformat()
    mock_assessment.assessment_id = "test-assessment-001"
    mock_assessment.to_dict = Mock(
        return_value={
            "status": "ok",
            "overall_score": 0.85,
            "findings": ["System is healthy", "Memory usage normal"],
        }
    )

    # Create temp path for assessment
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        assessment_path = Path(tmpdir) / "assessment.json"
        assessment_path.write_text(json.dumps(mock_assessment.to_dict()))
        mock_controller.run_daily_self_assessment = Mock(
            return_value=(mock_assessment, assessment_path)
        )
        mock_controller._get_previous_score = Mock(return_value=None)

    # Mock BeliefStore
    mock_belief_store = Mock(spec=BeliefStore)
    mock_belief_store.list_active = Mock(return_value=[])
    mock_belief_store.put = Mock(return_value=True)
    mock_belief_store.get = Mock(return_value=None)

    # Mock BeliefConsistencyChecker
    mock_checker = Mock(spec=BeliefConsistencyChecker)
    mock_checker.detect_conflicts = Mock(return_value=[])

    # Mock BeliefRevisionEngine
    mock_revision_engine = Mock(spec=BeliefRevisionEngine)
    mock_revision_engine.apply_revisions = Mock(return_value=[])
    mock_revision_engine.last_support_scores = []
    mock_revision_engine.last_blocked_revisions = []

    # Mock HypothesisGenerator
    mock_hypothesis = Mock()
    mock_hypothesis.hypothesis_id = "hyp-test-001"
    mock_hypothesis.target_component = "test_strategy"

    mock_hypothesis_gen = Mock(spec=HypothesisGenerator)
    mock_hypothesis_gen.generate = Mock(return_value=[mock_hypothesis])

    # Mock PortfolioPolicyLab
    mock_exp_result = Mock()
    mock_exp_result.to_metrics = Mock(
        return_value={
            "sharpe": 1.2,
            "sortino": 0.9,
            "drawdown": 0.15,
            "ece": 0.08,
        }
    )

    mock_lab = Mock(spec=PortfolioPolicyLab)
    mock_lab.run = Mock(return_value=mock_exp_result)

    # Mock ChampionChallengerEngine
    mock_champion_outcome = Mock()
    mock_champion_outcome.promoted = False
    mock_champion_outcome.reason = "low_sharpe"
    mock_champion_outcome.version_id = "v1.0.0"

    mock_champion_engine = Mock(spec=ChampionChallengerEngine)
    mock_champion_engine.evaluate_candidate = Mock(return_value=mock_champion_outcome)

    # Mock NeuroSymbolicRuntimeIntegrator
    mock_runtime_result = Mock()
    mock_runtime_result.divergence_score = 0.05
    mock_runtime_result.passed_non_regression = True

    mock_runtime = Mock(spec=NeuroSymbolicRuntimeIntegrator)
    mock_runtime.run = Mock(return_value=mock_runtime_result)

    # Mock AutonomyTuner
    mock_tuning_result = Mock()
    mock_tuning_result.new_level = "bounded"
    mock_tuning_result.previous_level = "bounded"
    mock_tuning_result.reason = "normal_operation"

    mock_tuner = Mock(spec=AutonomyTuner)
    mock_tuner.tune = Mock(return_value=mock_tuning_result)

    # Mock ConstitutionAuditEngine
    mock_audit_result = Mock()
    mock_audit_result.violations = []
    mock_audit_result.critical_count = 0

    mock_audit = Mock(spec=ConstitutionAuditEngine)
    mock_audit.run = Mock(return_value=mock_audit_result)

    # Mock DiscordNotifier - patch the class
    with patch.object(DiscordNotifier, "__init__", lambda self, **kw: None):
        with patch.object(
            DiscordNotifier, "notify_autocog_event", AMock(return_value=True)
        ):
            with patch.object(
                DiscordNotifier, "notify_self_assessment", AMock(return_value=True)
            ):
                with patch.object(DiscordNotifier, "close", AMock(return_value=None)):
                    with patch.object(
                        DiscordNotifier,
                        "should_notify_for_cycle_event",
                        return_value=True,
                    ):
                        # Create the cycle with mocked components
                        cycle = AutonomousCognitionFullCycle.__new__(
                            AutonomousCognitionFullCycle
                        )
                        cycle._controller = mock_controller
                        cycle._belief_store = mock_belief_store
                        cycle._checker = mock_checker
                        cycle._revision_engine = mock_revision_engine
                        cycle._hypothesis_generator = mock_hypothesis_gen
                        cycle._lab = mock_lab
                        cycle._champion_engine = mock_champion_engine
                        cycle._runtime = mock_runtime
                        cycle._tuner = mock_tuner
                        cycle._audit = mock_audit
                        cycle._config = {
                            "experiments": {
                                "enabled": True,
                                "max_experiments_per_cycle": 3,
                                "safe_mode": True,
                            },
                            "qdrant": {
                                "write_enabled": False,
                                "collection_name": "ChiseAI",
                                "vector_size": 384,
                            },
                            "metrics": {
                                "skip_rate_alert_threshold": 0.20,
                                "skip_rate_window_days": 7,
                                "alert_on_high_skip_rate": True,
                            },
                            "safety": {
                                "max_risk_level": "medium",
                                "require_approval_for": ["high", "critical"],
                            },
                        }
                        cycle._REPO_ROOT = Path("/home/tacopants/projects/ChiseAI")
                        cycle.DEFAULT_CYCLE_DIR = str(
                            cycle._REPO_ROOT / "_bmad-output/autocog/cycles"
                        )
                        cycle.DEFAULT_GOVERNANCE_STATE_PATH = str(
                            cycle._REPO_ROOT
                            / "_bmad-output/autocog/governance_state.json"
                        )
                        cycle.DEFAULT_WEEKLY_META_AUDIT_DIR = str(
                            cycle._REPO_ROOT / "_bmad-output/autocog/meta_audit"
                        )
                        cycle.CONFIG_PATH = cycle._REPO_ROOT / "config/autocog.yaml"

                        yield cycle


# =============================================================================
# Event Loop Fixture
# =============================================================================


@pytest.fixture
def event_loop():
    """Create an instance of the default event loop for each test case."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
