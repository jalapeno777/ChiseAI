"""Unit tests for Strategy Registry - Champion/Challenger Tracking (ST-SIG-002).

Test coverage:
- AC1: Champion/challenger relationships
- AC2: Artifact storage (config, diffs, backtest results, paper results)
- AC3: Promotion criteria enforcement
- AC4: Version immutability (frozen=True)
"""

from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from backtesting.candidate.registry import (
    InMemoryStrategyRegistry,
    PromotionCriteria,
    StrategyArtifact,
    StrategyRegistry,
    StrategyStatus,
    StrategyVersion,
)


class TestStrategyVersion:
    """Tests for StrategyVersion frozen dataclass (AC4)."""

    def test_version_is_frozen(self):
        """AC4: StrategyVersion must be immutable once created."""
        version = StrategyVersion(
            version_id="test_v1",
            strategy_id="strategy_1",
            version="1.0.0",
            symbol="BTCUSDT",
            timeframe="1h",
            status=StrategyStatus.CANDIDATE,
            created_at=datetime.now(UTC),
            config_hash="abc123",
        )

        # Attempting to modify should raise FrozenInstanceError
        with pytest.raises((AttributeError, TypeError)):
            version.version_id = "new_id"

    def test_version_immutability_via_replace(self):
        """AC4: Creating new version with changes requires creating new object."""
        version = StrategyVersion(
            version_id="test_v1",
            strategy_id="strategy_1",
            version="1.0.0",
            symbol="BTCUSDT",
            timeframe="1h",
            status=StrategyStatus.CANDIDATE,
            created_at=datetime.now(UTC),
            config_hash="abc123",
        )

        # To "change" status, must create new object
        new_version = StrategyVersion(
            version_id=version.version_id,
            strategy_id=version.strategy_id,
            version=version.version,
            symbol=version.symbol,
            timeframe=version.timeframe,
            status=StrategyStatus.CHAMPION,  # Changed
            created_at=version.created_at,
            config_hash=version.config_hash,
            parent_version=version.parent_version,
        )

        # Original unchanged
        assert version.status == StrategyStatus.CANDIDATE
        # New has changed status
        assert new_version.status == StrategyStatus.CHAMPION

    def test_version_validation_required_fields(self):
        """AC4: Version must have all required fields."""
        with pytest.raises(ValueError, match="version_id is required"):
            StrategyVersion(
                version_id="",
                strategy_id="strategy_1",
                version="1.0.0",
                symbol="BTCUSDT",
                timeframe="1h",
                status=StrategyStatus.CANDIDATE,
                created_at=datetime.now(UTC),
                config_hash="abc123",
            )

    def test_version_with_parent(self):
        """AC4: Version can track parent version for lineage."""
        parent = StrategyVersion(
            version_id="parent_v1",
            strategy_id="strategy_1",
            version="1.0.0",
            symbol="BTCUSDT",
            timeframe="1h",
            status=StrategyStatus.CHAMPION,
            created_at=datetime.now(UTC),
            config_hash="abc123",
        )

        child = StrategyVersion(
            version_id="child_v2",
            strategy_id="strategy_1",
            version="1.1.0",
            symbol="BTCUSDT",
            timeframe="1h",
            status=StrategyStatus.CANDIDATE,
            created_at=datetime.now(UTC),
            config_hash="def456",
            parent_version=parent.version_id,
        )

        assert child.parent_version == parent.version_id


class TestStrategyArtifact:
    """Tests for StrategyArtifact dataclass (AC2)."""

    def test_artifact_creation(self):
        """AC2: Artifact can be created with all required fields."""
        artifact = StrategyArtifact(
            artifact_id="art_1",
            version_id="version_1",
            artifact_type="config",
            data={"param1": 100, "param2": "value"},
            metadata={"source": "test"},
        )

        assert artifact.artifact_id == "art_1"
        assert artifact.version_id == "version_1"
        assert artifact.artifact_type == "config"
        assert artifact.data["param1"] == 100
        assert artifact.metadata["source"] == "test"

    def test_artifact_validation_invalid_type(self):
        """AC2: Artifact type must be valid."""
        with pytest.raises(ValueError, match="artifact_type must be one of"):
            StrategyArtifact(
                artifact_id="art_1",
                version_id="version_1",
                artifact_type="invalid_type",
                data={},
            )

    def test_artifact_valid_types(self):
        """AC2: All valid artifact types are accepted."""
        valid_types = [
            "config",
            "diff",
            "backtest",
            "paper",
            "live",
            "promotion_request",
        ]

        for i, art_type in enumerate(valid_types):
            artifact = StrategyArtifact(
                artifact_id=f"art_{i}",
                version_id="version_1",
                artifact_type=art_type,
                data={"test": True},
            )
            assert artifact.artifact_type == art_type


class TestPromotionCriteria:
    """Tests for PromotionCriteria (AC3)."""

    def test_default_criteria(self):
        """AC3: Default criteria have documented values."""
        criteria = PromotionCriteria()

        # Backtest criteria
        assert criteria.min_backtest_score == 60.0
        assert criteria.min_sharpe_ratio == 1.0
        assert criteria.max_drawdown_pct == 15.0
        assert criteria.min_win_rate_pct == 50.0

        # Paper trading criteria
        assert criteria.min_paper_trades == 20
        assert criteria.min_paper_days == 3
        assert criteria.min_paper_sharpe == 0.8
        assert criteria.max_paper_drawdown_pct == 10.0

        # Comparison criteria
        assert criteria.require_outperformance is True
        assert criteria.outperformance_margin_pct == 5.0

    def test_custom_criteria(self):
        """AC3: Criteria can be customized."""
        criteria = PromotionCriteria(
            min_backtest_score=70.0,
            min_sharpe_ratio=1.5,
            max_drawdown_pct=10.0,
            require_outperformance=False,
        )

        assert criteria.min_backtest_score == 70.0
        assert criteria.min_sharpe_ratio == 1.5
        assert criteria.max_drawdown_pct == 10.0
        assert criteria.require_outperformance is False

    def test_criteria_serialization(self):
        """AC3: Criteria can be serialized and deserialized."""
        criteria = PromotionCriteria(min_backtest_score=75.0)

        data = criteria.to_dict()
        restored = PromotionCriteria.from_dict(data)

        assert restored.min_backtest_score == 75.0
        assert restored.min_sharpe_ratio == criteria.min_sharpe_ratio


class TestStrategyRegistryBasics:
    """Tests for basic StrategyRegistry operations."""

    def test_registry_creation(self):
        """Registry can be created."""
        registry = InMemoryStrategyRegistry()
        assert registry is not None
        assert len(registry.list_all_versions()) == 0

    def test_register_strategy(self):
        """AC1 + AC4: Strategy can be registered with immutable version."""
        registry = InMemoryStrategyRegistry()

        config = {"grid_size": 10, "take_profit": 0.05}
        version = registry.register_strategy(
            strategy_id="grid_btc",
            version="1.0.0",
            symbol="BTCUSDT",
            timeframe="1h",
            config=config,
        )

        assert version.strategy_id == "grid_btc"
        assert version.version == "1.0.0"
        assert version.symbol == "BTCUSDT"
        assert version.timeframe == "1h"
        assert version.status == StrategyStatus.CANDIDATE
        assert version.config_hash is not None

    def test_register_strategy_with_parent(self):
        """AC1 + AC2: Strategy registration stores config and diff artifacts."""
        registry = InMemoryStrategyRegistry()

        # Register parent
        parent_config = {"grid_size": 10, "take_profit": 0.05}
        parent = registry.register_strategy(
            strategy_id="grid_btc",
            version="1.0.0",
            symbol="BTCUSDT",
            timeframe="1h",
            config=parent_config,
        )

        # Register child with changes
        child_config = {"grid_size": 15, "take_profit": 0.05}  # Changed grid_size
        child = registry.register_strategy(
            strategy_id="grid_btc",
            version="1.1.0",
            symbol="BTCUSDT",
            timeframe="1h",
            config=child_config,
            parent_version=parent.version_id,
        )

        assert child.parent_version == parent.version_id

        # Check diff artifact was created
        diff_artifacts = registry.get_artifacts(child.version_id, artifact_type="diff")
        assert len(diff_artifacts) == 1
        diff = diff_artifacts[0].data
        assert "modified" in diff
        assert "grid_size" in diff["modified"]


class TestChampionChallengerManagement:
    """Tests for champion/challenger relationships (AC1)."""

    def test_set_champion(self):
        """AC1: Champion can be set for a symbol/timeframe."""
        registry = InMemoryStrategyRegistry()

        version = registry.register_strategy(
            strategy_id="grid_btc",
            version="1.0.0",
            symbol="BTCUSDT",
            timeframe="1h",
            config={"test": True},
        )

        champion = registry.set_champion(version.version_id)

        assert champion.status == StrategyStatus.CHAMPION
        assert registry.get_champion("BTCUSDT", "1h") == champion

    def test_champion_replaces_previous(self):
        """AC1: Setting new champion deprecates old champion."""
        registry = InMemoryStrategyRegistry()

        v1 = registry.register_strategy(
            strategy_id="grid_btc",
            version="1.0.0",
            symbol="BTCUSDT",
            timeframe="1h",
            config={"v": 1},
        )
        registry.set_champion(v1.version_id)

        v2 = registry.register_strategy(
            strategy_id="grid_btc",
            version="1.1.0",
            symbol="BTCUSDT",
            timeframe="1h",
            config={"v": 2},
        )
        registry.set_champion(v2.version_id)

        # Old champion is deprecated
        old_champion = registry.get_version(v1.version_id)
        assert old_champion.status == StrategyStatus.DEPRECATED

        # New is champion
        assert registry.get_champion("BTCUSDT", "1h").version_id == v2.version_id

    def test_add_challenger(self):
        """AC1: Challenger can be added to compete with champion."""
        registry = InMemoryStrategyRegistry()

        # Create champion
        champion = registry.register_strategy(
            strategy_id="grid_btc",
            version="1.0.0",
            symbol="BTCUSDT",
            timeframe="1h",
            config={"v": 1},
        )
        registry.set_champion(champion.version_id)

        # Create challenger
        challenger = registry.register_strategy(
            strategy_id="grid_btc",
            version="1.1.0",
            symbol="BTCUSDT",
            timeframe="1h",
            config={"v": 2},
        )
        registry.add_challenger(challenger.version_id)

        # Check challenger status
        updated = registry.get_version(challenger.version_id)
        assert updated.status == StrategyStatus.CHALLENGER

        # Check challengers list
        challengers = registry.get_challengers("BTCUSDT", "1h")
        assert len(challengers) == 1
        assert challengers[0].version_id == challenger.version_id

    def test_add_challenger_requires_candidate_status(self):
        """AC1: Only CANDIDATE can become challenger."""
        registry = InMemoryStrategyRegistry()

        version = registry.register_strategy(
            strategy_id="grid_btc",
            version="1.0.0",
            symbol="BTCUSDT",
            timeframe="1h",
            config={"v": 1},
        )
        registry.set_champion(version.version_id)

        # Cannot add champion as challenger
        with pytest.raises(ValueError, match="must be in CANDIDATE status"):
            registry.add_challenger(version.version_id)

    def test_get_challengers_empty(self):
        """AC1: Empty challengers list when none exist."""
        registry = InMemoryStrategyRegistry()

        challengers = registry.get_challengers("BTCUSDT", "1h")
        assert challengers == []

    def test_multiple_challengers(self):
        """AC1: Multiple challengers can exist for same symbol/timeframe."""
        registry = InMemoryStrategyRegistry()

        # Create champion
        champion = registry.register_strategy(
            strategy_id="grid_btc",
            version="1.0.0",
            symbol="BTCUSDT",
            timeframe="1h",
            config={"v": 1},
        )
        registry.set_champion(champion.version_id)

        # Create multiple challengers
        for i in range(3):
            challenger = registry.register_strategy(
                strategy_id="grid_btc",
                version=f"1.{i + 1}.0",
                symbol="BTCUSDT",
                timeframe="1h",
                config={"v": i + 2},
            )
            registry.add_challenger(challenger.version_id)

        challengers = registry.get_challengers("BTCUSDT", "1h")
        assert len(challengers) == 3

    def test_promoted_challenger_removed_from_challengers(self):
        """AC1: Challenger promoted to champion is removed from challengers list."""
        registry = InMemoryStrategyRegistry()

        # Create champion
        champion = registry.register_strategy(
            strategy_id="grid_btc",
            version="1.0.0",
            symbol="BTCUSDT",
            timeframe="1h",
            config={"v": 1},
        )
        registry.set_champion(champion.version_id)

        # Create challenger
        challenger = registry.register_strategy(
            strategy_id="grid_btc",
            version="1.1.0",
            symbol="BTCUSDT",
            timeframe="1h",
            config={"v": 2},
        )
        registry.add_challenger(challenger.version_id)

        # Promote challenger (bypass criteria for this test)
        registry.set_champion(challenger.version_id)

        # Should be removed from challengers
        challengers = registry.get_challengers("BTCUSDT", "1h")
        assert len(challengers) == 0


class TestArtifactStorage:
    """Tests for artifact storage (AC2)."""

    def test_store_config_artifact(self):
        """AC2: Config artifact is stored on strategy registration."""
        registry = InMemoryStrategyRegistry()

        config = {"grid_size": 10, "levels": 5}
        version = registry.register_strategy(
            strategy_id="grid_btc",
            version="1.0.0",
            symbol="BTCUSDT",
            timeframe="1h",
            config=config,
        )

        artifacts = registry.get_artifacts(version.version_id, artifact_type="config")
        assert len(artifacts) == 1
        assert artifacts[0].data == config

    def test_store_backtest_artifact(self):
        """AC2: Backtest results can be stored as artifacts."""
        registry = InMemoryStrategyRegistry()

        version = registry.register_strategy(
            strategy_id="grid_btc",
            version="1.0.0",
            symbol="BTCUSDT",
            timeframe="1h",
            config={"test": True},
        )

        backtest_metrics = {
            "sharpe_ratio": 1.5,
            "max_drawdown_pct": 10.0,
            "composite_score": 75.0,
        }

        artifact = registry.store_artifact(
            version_id=version.version_id,
            artifact_type="backtest",
            data=backtest_metrics,
            metadata={"window": "2024-01-01 to 2024-02-01"},
        )

        assert artifact.artifact_type == "backtest"
        assert artifact.data["sharpe_ratio"] == 1.5

        # Retrieve
        artifacts = registry.get_artifacts(version.version_id, artifact_type="backtest")
        assert len(artifacts) == 1

    def test_store_paper_artifact(self):
        """AC2: Paper trading results can be stored as artifacts."""
        registry = InMemoryStrategyRegistry()

        version = registry.register_strategy(
            strategy_id="grid_btc",
            version="1.0.0",
            symbol="BTCUSDT",
            timeframe="1h",
            config={"test": True},
        )

        paper_metrics = {
            "trade_count": 50,
            "days_trading": 7,
            "sharpe_ratio": 1.2,
            "max_drawdown_pct": 5.0,
        }

        artifact = registry.store_artifact(
            version_id=version.version_id,
            artifact_type="paper",
            data=paper_metrics,
        )

        assert artifact.artifact_type == "paper"

        artifacts = registry.get_artifacts(version.version_id, artifact_type="paper")
        assert len(artifacts) == 1
        assert artifacts[0].data["trade_count"] == 50

    def test_get_all_artifacts(self):
        """AC2: All artifacts for a version can be retrieved."""
        registry = InMemoryStrategyRegistry()

        version = registry.register_strategy(
            strategy_id="grid_btc",
            version="1.0.0",
            symbol="BTCUSDT",
            timeframe="1h",
            config={"test": True},
        )

        # Add multiple artifacts
        registry.store_artifact(version.version_id, "backtest", {"score": 80})
        registry.store_artifact(version.version_id, "paper", {"trades": 30})

        all_artifacts = registry.get_artifacts(version.version_id)
        assert len(all_artifacts) == 3  # config + backtest + paper

    def test_get_artifact_by_id(self):
        """AC2: Specific artifact can be retrieved by ID."""
        registry = InMemoryStrategyRegistry()

        version = registry.register_strategy(
            strategy_id="grid_btc",
            version="1.0.0",
            symbol="BTCUSDT",
            timeframe="1h",
            config={"test": True},
        )

        artifact = registry.store_artifact(
            version_id=version.version_id,
            artifact_type="backtest",
            data={"score": 90},
        )

        retrieved = registry.get_artifact(artifact.artifact_id)
        assert retrieved is not None
        assert retrieved.artifact_id == artifact.artifact_id

    def test_store_artifact_requires_valid_version(self):
        """AC2: Cannot store artifact for non-existent version."""
        registry = InMemoryStrategyRegistry()

        with pytest.raises(ValueError, match="Version nonexistent not found"):
            registry.store_artifact("nonexistent", "backtest", {})


class TestPromotionCriteriaEnforcement:
    """Tests for promotion criteria enforcement (AC3)."""

    def test_promote_challenger_success(self):
        """AC3: Challenger meeting all criteria is promoted to champion."""
        registry = InMemoryStrategyRegistry()

        # Create champion
        champion = registry.register_strategy(
            strategy_id="grid_btc",
            version="1.0.0",
            symbol="BTCUSDT",
            timeframe="1h",
            config={"v": 1},
        )
        registry.set_champion(champion.version_id)

        # Create challenger
        challenger = registry.register_strategy(
            strategy_id="grid_btc",
            version="1.1.0",
            symbol="BTCUSDT",
            timeframe="1h",
            config={"v": 2},
        )
        registry.add_challenger(challenger.version_id)

        # Promote with excellent metrics
        result = registry.promote_challenger(
            version_id=challenger.version_id,
            backtest_metrics={
                "composite_score": 80.0,
                "sharpe_ratio": 1.5,
                "max_drawdown_pct": 10.0,
                "win_rate_pct": 55.0,
            },
            paper_metrics={
                "trade_count": 30,
                "days_trading": 5,
                "sharpe_ratio": 1.2,
                "max_drawdown_pct": 5.0,
            },
        )

        assert result.success is True
        assert len(result.passed_criteria) > 0
        assert len(result.failed_criteria) == 0

        # Verify promoted
        updated = registry.get_version(challenger.version_id)
        assert updated.status == StrategyStatus.CHAMPION

    def test_promote_challenger_fails_backtest_score(self):
        """AC3: Challenger fails if backtest score too low."""
        registry = InMemoryStrategyRegistry()

        challenger = registry.register_strategy(
            strategy_id="grid_btc",
            version="1.0.0",
            symbol="BTCUSDT",
            timeframe="1h",
            config={"v": 1},
        )
        registry.add_challenger(challenger.version_id)

        result = registry.promote_challenger(
            version_id=challenger.version_id,
            backtest_metrics={
                "composite_score": 50.0,  # Below 60 threshold
                "sharpe_ratio": 1.5,
                "max_drawdown_pct": 10.0,
                "win_rate_pct": 55.0,
            },
            paper_metrics={
                "trade_count": 30,
                "days_trading": 5,
                "sharpe_ratio": 1.2,
                "max_drawdown_pct": 5.0,
            },
        )

        assert result.success is False
        assert any("backtest_score" in str(f) for f in result.failed_criteria)

    def test_promote_challenger_fails_paper_trades(self):
        """AC3: Challenger fails if insufficient paper trades."""
        registry = InMemoryStrategyRegistry()

        challenger = registry.register_strategy(
            strategy_id="grid_btc",
            version="1.0.0",
            symbol="BTCUSDT",
            timeframe="1h",
            config={"v": 1},
        )
        registry.add_challenger(challenger.version_id)

        result = registry.promote_challenger(
            version_id=challenger.version_id,
            backtest_metrics={
                "composite_score": 80.0,
                "sharpe_ratio": 1.5,
                "max_drawdown_pct": 10.0,
                "win_rate_pct": 55.0,
            },
            paper_metrics={
                "trade_count": 10,  # Below 20 threshold
                "days_trading": 5,
                "sharpe_ratio": 1.2,
                "max_drawdown_pct": 5.0,
            },
        )

        assert result.success is False
        assert any("paper_trades" in str(f) for f in result.failed_criteria)

    def test_promote_challenger_fails_outperformance(self):
        """AC3: Challenger must outperform champion to be promoted."""
        registry = InMemoryStrategyRegistry()

        # Create champion with good score
        champion = registry.register_strategy(
            strategy_id="grid_btc",
            version="1.0.0",
            symbol="BTCUSDT",
            timeframe="1h",
            config={"v": 1},
        )
        registry.set_champion(champion.version_id)

        # Store champion backtest with high score
        registry.store_artifact(
            version_id=champion.version_id,
            artifact_type="backtest",
            data={"composite_score": 90.0},
        )

        # Create challenger with lower score
        challenger = registry.register_strategy(
            strategy_id="grid_btc",
            version="1.1.0",
            symbol="BTCUSDT",
            timeframe="1h",
            config={"v": 2},
        )
        registry.add_challenger(challenger.version_id)

        result = registry.promote_challenger(
            version_id=challenger.version_id,
            backtest_metrics={
                "composite_score": 80.0,  # Less than 90 + 5%
                "sharpe_ratio": 1.5,
                "max_drawdown_pct": 10.0,
                "win_rate_pct": 55.0,
            },
            paper_metrics={
                "trade_count": 30,
                "days_trading": 5,
                "sharpe_ratio": 1.2,
                "max_drawdown_pct": 5.0,
            },
        )

        assert result.success is False
        assert any("outperformance" in str(f) for f in result.failed_criteria)

    def test_promote_challenger_no_champion_auto_passes(self):
        """AC3: Outperformance check passes if no existing champion."""
        registry = InMemoryStrategyRegistry()

        challenger = registry.register_strategy(
            strategy_id="grid_btc",
            version="1.0.0",
            symbol="BTCUSDT",
            timeframe="1h",
            config={"v": 1},
        )
        registry.add_challenger(challenger.version_id)

        result = registry.promote_challenger(
            version_id=challenger.version_id,
            backtest_metrics={
                "composite_score": 80.0,
                "sharpe_ratio": 1.5,
                "max_drawdown_pct": 10.0,
                "win_rate_pct": 55.0,
            },
            paper_metrics={
                "trade_count": 30,
                "days_trading": 5,
                "sharpe_ratio": 1.2,
                "max_drawdown_pct": 5.0,
            },
        )

        assert result.success is True
        assert any("No existing champion" in str(p) for p in result.passed_criteria)

    def test_promote_non_challenger_fails(self):
        """AC3: Only challengers can be promoted."""
        registry = InMemoryStrategyRegistry()

        version = registry.register_strategy(
            strategy_id="grid_btc",
            version="1.0.0",
            symbol="BTCUSDT",
            timeframe="1h",
            config={"v": 1},
        )
        # Not added as challenger

        result = registry.promote_challenger(
            version_id=version.version_id,
            backtest_metrics={"composite_score": 80.0},
            paper_metrics={"trade_count": 30},
        )

        assert result.success is False
        assert any("CHALLENGER" in str(f) for f in result.failed_criteria)

    def test_promote_missing_metrics_fails(self):
        """AC3: Promotion requires both backtest and paper metrics."""
        registry = InMemoryStrategyRegistry()

        challenger = registry.register_strategy(
            strategy_id="grid_btc",
            version="1.0.0",
            symbol="BTCUSDT",
            timeframe="1h",
            config={"v": 1},
        )
        registry.add_challenger(challenger.version_id)

        # Missing paper metrics
        result = registry.promote_challenger(
            version_id=challenger.version_id,
            backtest_metrics={"composite_score": 80.0},
            paper_metrics=None,
        )

        assert result.success is False
        assert any("paper_metrics" in str(f) for f in result.failed_criteria)

    def test_custom_promotion_criteria(self):
        """AC3: Custom criteria can be set per symbol/timeframe."""
        registry = InMemoryStrategyRegistry()

        custom_criteria = PromotionCriteria(
            min_backtest_score=70.0,
            require_outperformance=False,
        )
        registry.set_promotion_criteria("BTCUSDT", "1h", custom_criteria)

        retrieved = registry.get_promotion_criteria("BTCUSDT", "1h")
        assert retrieved.min_backtest_score == 70.0
        assert retrieved.require_outperformance is False


class TestProtocolImplementation:
    """Tests for StrategyRegistry Protocol implementation."""

    def test_get_candidates(self):
        """Protocol: Returns candidate strategies for backtesting."""
        registry = InMemoryStrategyRegistry()

        # Register multiple strategies
        for i in range(3):
            registry.register_strategy(
                strategy_id=f"strategy_{i}",
                version="1.0.0",
                symbol="BTCUSDT",
                timeframe="1h",
                config={"id": i},
            )

        candidates = registry.get_candidates()
        assert len(candidates) == 3

        for candidate in candidates:
            assert "candidate_id" in candidate
            assert "strategy_id" in candidate
            assert "config" in candidate

    def test_update_candidate_status(self):
        """Protocol: Updates candidate status from pipeline."""
        registry = InMemoryStrategyRegistry()

        version = registry.register_strategy(
            strategy_id="grid_btc",
            version="1.0.0",
            symbol="BTCUSDT",
            timeframe="1h",
            config={"test": True},
        )

        # Update status from pipeline
        success = registry.update_candidate_status(
            candidate_id=version.version_id,
            status="completed",
            metrics={"composite_score": 75.0},
        )

        assert success is True

        # Check artifact was stored
        artifacts = registry.get_artifacts(version.version_id, artifact_type="backtest")
        assert len(artifacts) >= 1

    def test_update_candidate_status_not_found(self):
        """Protocol: Returns False for non-existent candidate."""
        registry = InMemoryStrategyRegistry()

        success = registry.update_candidate_status(
            candidate_id="nonexistent",
            status="completed",
        )

        assert success is False

    def test_registry_implements_protocol(self):
        """Protocol: InMemoryStrategyRegistry implements StrategyRegistry Protocol."""
        # This test verifies type compatibility
        registry: StrategyRegistry = InMemoryStrategyRegistry()

        # Should be able to call protocol methods
        candidates = registry.get_candidates()
        assert candidates == []

        result = registry.update_candidate_status("test", "completed")
        assert result is False


class TestQueryMethods:
    """Tests for additional query methods."""

    def test_get_version(self):
        """Can retrieve specific version by ID."""
        registry = InMemoryStrategyRegistry()

        version = registry.register_strategy(
            strategy_id="grid_btc",
            version="1.0.0",
            symbol="BTCUSDT",
            timeframe="1h",
            config={"test": True},
        )

        retrieved = registry.get_version(version.version_id)
        assert retrieved == version

    def test_get_version_not_found(self):
        """Returns None for non-existent version."""
        registry = InMemoryStrategyRegistry()

        result = registry.get_version("nonexistent")
        assert result is None

    def test_get_versions_by_strategy(self):
        """Can retrieve all versions for a strategy."""
        registry = InMemoryStrategyRegistry()

        for i in range(3):
            registry.register_strategy(
                strategy_id="grid_btc",
                version=f"1.{i}.0",
                symbol="BTCUSDT",
                timeframe="1h",
                config={"v": i},
            )

        versions = registry.get_versions_by_strategy("grid_btc")
        assert len(versions) == 3

    def test_get_versions_by_symbol_timeframe(self):
        """Can retrieve all versions for symbol/timeframe."""
        registry = InMemoryStrategyRegistry()

        # BTC 1h
        registry.register_strategy(
            strategy_id="grid_btc",
            version="1.0.0",
            symbol="BTCUSDT",
            timeframe="1h",
            config={},
        )
        # BTC 4h
        registry.register_strategy(
            strategy_id="grid_btc",
            version="1.0.0",
            symbol="BTCUSDT",
            timeframe="4h",
            config={},
        )
        # ETH 1h
        registry.register_strategy(
            strategy_id="grid_eth",
            version="1.0.0",
            symbol="ETHUSDT",
            timeframe="1h",
            config={},
        )

        btc_1h = registry.get_versions_by_symbol_timeframe("BTCUSDT", "1h")
        assert len(btc_1h) == 1

    def test_list_all_versions(self):
        """Can list all registered versions."""
        registry = InMemoryStrategyRegistry()

        for i in range(5):
            registry.register_strategy(
                strategy_id=f"strategy_{i}",
                version="1.0.0",
                symbol="BTCUSDT",
                timeframe="1h",
                config={},
            )

        all_versions = registry.list_all_versions()
        assert len(all_versions) == 5


class TestPersistence:
    """Tests for artifact persistence to disk."""

    def test_artifact_persistence(self):
        """AC2: Artifacts are persisted to disk when storage_dir set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_dir = Path(tmpdir)
            registry = InMemoryStrategyRegistry(storage_dir=storage_dir)

            version = registry.register_strategy(
                strategy_id="grid_btc",
                version="1.0.0",
                symbol="BTCUSDT",
                timeframe="1h",
                config={"test": True},
            )

            # Check config was persisted
            version_dir = storage_dir / version.version_id
            assert version_dir.exists()

            config_files = list(version_dir.glob("config_*.json"))
            assert len(config_files) == 1

            # Verify content
            with open(config_files[0]) as f:
                data = json.load(f)
                assert data["artifact_type"] == "config"
                assert data["data"]["test"] is True


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_register_duplicate_version_different_id(self):
        """Same version string can be registered with different version_id."""
        registry = InMemoryStrategyRegistry()

        v1 = registry.register_strategy(
            strategy_id="grid_btc",
            version="1.0.0",
            symbol="BTCUSDT",
            timeframe="1h",
            config={"v": 1},
        )

        v2 = registry.register_strategy(
            strategy_id="grid_btc",
            version="1.0.0",  # Same version string
            symbol="BTCUSDT",
            timeframe="1h",
            config={"v": 2},
        )

        # Different version_ids
        assert v1.version_id != v2.version_id
        # Both exist
        assert registry.get_version(v1.version_id) is not None
        assert registry.get_version(v2.version_id) is not None

    def test_champion_different_symbol_timeframe(self):
        """Champions are independent per symbol/timeframe."""
        registry = InMemoryStrategyRegistry()

        # Champion for BTC 1h
        btc_1h = registry.register_strategy(
            strategy_id="grid_btc",
            version="1.0.0",
            symbol="BTCUSDT",
            timeframe="1h",
            config={},
        )
        registry.set_champion(btc_1h.version_id)

        # Champion for BTC 4h
        btc_4h = registry.register_strategy(
            strategy_id="grid_btc",
            version="1.0.0",
            symbol="BTCUSDT",
            timeframe="4h",
            config={},
        )
        registry.set_champion(btc_4h.version_id)

        # Different champions
        assert registry.get_champion("BTCUSDT", "1h").version_id == btc_1h.version_id
        assert registry.get_champion("BTCUSDT", "4h").version_id == btc_4h.version_id

    def test_set_champion_not_found(self):
        """Setting non-existent version as champion raises error."""
        registry = InMemoryStrategyRegistry()

        with pytest.raises(ValueError, match="Version nonexistent not found"):
            registry.set_champion("nonexistent")

    def test_add_challenger_not_found(self):
        """Adding non-existent version as challenger raises error."""
        registry = InMemoryStrategyRegistry()

        with pytest.raises(ValueError, match="Version nonexistent not found"):
            registry.add_challenger("nonexistent")

    def test_promote_nonexistent_version(self):
        """Promoting non-existent version returns failed result."""
        registry = InMemoryStrategyRegistry()

        result = registry.promote_challenger("nonexistent")

        assert result.success is False
        assert any("not found" in str(f) for f in result.failed_criteria)
