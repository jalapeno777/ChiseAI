"""Strategy Registry - Champion/Challenger Tracking.

This module implements the StrategyRegistry with champion/challenger relationships,
artifact storage, and promotion criteria as specified in ST-SIG-002.

AC1: Concrete StrategyRegistry class with champion/challenger relationships
AC2: Artifact storage (config, diffs, backtest results, paper results)
AC3: Promotion criteria with documented thresholds
AC4: Frozen StrategyVersion dataclass for immutability
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Protocol


class StrategyStatus(Enum):
    """Status of a strategy in the registry.

    AC1: Strategy lifecycle states for champion/challenger tracking.
    """

    CANDIDATE = "candidate"  # New strategy awaiting evaluation
    CHALLENGER = "challenger"  # Passed backtest, competing with champion
    CHAMPION = "champion"  # Current best strategy for a symbol/timeframe
    DEPRECATED = "deprecated"  # Retired strategy (no longer used)


@dataclass(frozen=True)
class StrategyVersion:
    """Immutable strategy version metadata.

    AC4: Frozen dataclass for immutability - once registered, versions
    cannot be modified, ensuring auditability and reproducibility.

    Attributes:
        version_id: Unique identifier for this version
        strategy_id: Parent strategy identifier
        version: Semantic version string (e.g., "1.2.3")
        symbol: Trading symbol (e.g., "BTCUSDT")
        timeframe: Timeframe (e.g., "1h", "4h", "1d")
        status: Current status in lifecycle
        created_at: Registration timestamp
        config_hash: Hash of strategy configuration for integrity
        parent_version: Previous version this was derived from (if any)
    """

    version_id: str
    strategy_id: str
    version: str
    symbol: str
    timeframe: str
    status: StrategyStatus
    created_at: datetime
    config_hash: str
    parent_version: str | None = None

    def __post_init__(self) -> None:
        """Validate version data."""
        if not self.version_id:
            raise ValueError("version_id is required")
        if not self.strategy_id:
            raise ValueError("strategy_id is required")
        if not self.version:
            raise ValueError("version is required")
        if not self.symbol:
            raise ValueError("symbol is required")
        if not self.timeframe:
            raise ValueError("timeframe is required")
        if not self.config_hash:
            raise ValueError("config_hash is required")


@dataclass
class StrategyArtifact:
    """Artifact storage for strategy versions.

    AC2: Stores config, diffs, backtest results, and paper trading results
    associated with a specific strategy version.

    Attributes:
        artifact_id: Unique identifier for this artifact
        version_id: Associated strategy version
        artifact_type: Type of artifact (config, diff, backtest, paper, live)
        data: Artifact data (dict or bytes depending on type)
        created_at: Timestamp when artifact was stored
        metadata: Additional metadata about the artifact
    """

    artifact_id: str
    version_id: str
    artifact_type: str
    data: dict[str, Any]
    created_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate artifact data."""
        if not self.artifact_id:
            raise ValueError("artifact_id is required")
        if not self.version_id:
            raise ValueError("version_id is required")
        if not self.artifact_type:
            raise ValueError("artifact_type is required")
        valid_types = {
            "config",
            "diff",
            "backtest",
            "paper",
            "live",
            "promotion_request",
        }
        if self.artifact_type not in valid_types:
            raise ValueError(f"artifact_type must be one of {valid_types}")


@dataclass
class PromotionCriteria:
    """Promotion criteria with documented thresholds.

    AC3: Documented promotion criteria for challenger -> champion promotion.
    These criteria ensure only well-tested strategies become champions.

    Default Criteria:
        - min_backtest_score: Minimum composite backtest score (default: 60.0)
        - min_sharpe_ratio: Minimum Sharpe ratio (default: 1.0)
        - max_drawdown_pct: Maximum drawdown percentage (default: 15.0)
        - min_win_rate_pct: Minimum win rate percentage (default: 50.0)
        - min_paper_trades: Minimum paper trading trades for validation (default: 20)
        - min_paper_days: Minimum days in paper trading (default: 3)
        - min_paper_sharpe: Minimum paper trading Sharpe ratio (default: 0.8)
        - max_paper_drawdown_pct: Maximum paper trading drawdown (default: 10.0)
        - require_outperformance: Must outperform current champion (default: True)
        - outperformance_margin_pct: Required margin over champion (default: 5.0)
    """

    # Backtest criteria
    min_backtest_score: float = 60.0
    min_sharpe_ratio: float = 1.0
    max_drawdown_pct: float = 15.0
    min_win_rate_pct: float = 50.0

    # Paper trading criteria
    min_paper_trades: int = 20
    min_paper_days: int = 3
    min_paper_sharpe: float = 0.8
    max_paper_drawdown_pct: float = 10.0

    # Comparison criteria
    require_outperformance: bool = True
    outperformance_margin_pct: float = 5.0

    def to_dict(self) -> dict[str, Any]:
        """Convert criteria to dictionary for serialization."""
        return {
            "min_backtest_score": self.min_backtest_score,
            "min_sharpe_ratio": self.min_sharpe_ratio,
            "max_drawdown_pct": self.max_drawdown_pct,
            "min_win_rate_pct": self.min_win_rate_pct,
            "min_paper_trades": self.min_paper_trades,
            "min_paper_days": self.min_paper_days,
            "min_paper_sharpe": self.min_paper_sharpe,
            "max_paper_drawdown_pct": self.max_paper_drawdown_pct,
            "require_outperformance": self.require_outperformance,
            "outperformance_margin_pct": self.outperformance_margin_pct,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PromotionCriteria:
        """Create criteria from dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class PromotionResult:
    """Result of a promotion attempt.

    Attributes:
        success: Whether promotion was successful
        version_id: Version that was evaluated
        champion_id: Current champion version (if any)
        passed_criteria: List of criteria that passed
        failed_criteria: List of criteria that failed with reasons
        timestamp: When the evaluation occurred
    """

    success: bool
    version_id: str
    champion_id: str | None
    passed_criteria: list[str] = field(default_factory=list)
    failed_criteria: list[dict[str, str]] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)


class StrategyRegistry(Protocol):
    """Protocol for strategy registry integration.

    This is the original Protocol from pipeline.py that defines the interface
    for the backtesting pipeline integration.
    """

    def get_candidates(self) -> list[dict[str, Any]]:
        """Get list of candidate strategies for backtesting.

        Returns:
            List of candidate strategy configurations
        """
        ...

    def update_candidate_status(
        self,
        candidate_id: str,
        status: str,
        metrics: dict[str, Any] | None = None,
    ) -> bool:
        """Update candidate status in registry.

        Args:
            candidate_id: Candidate identifier
            status: New status
            metrics: Optional metrics to store

        Returns:
            True if updated successfully
        """
        ...


class InMemoryStrategyRegistry:
    """In-memory implementation of StrategyRegistry with champion/challenger tracking.

    AC1: Concrete StrategyRegistry class implementing champion/challenger relationships.

    This registry maintains:
    - All registered strategy versions (immutable)
    - Champion assignments per symbol/timeframe
    - Challenger tracking for active competition
    - Artifact storage for each version
    - Promotion criteria enforcement
    """

    def __init__(self, storage_dir: Path | None = None) -> None:
        """Initialize the registry.

        Args:
            storage_dir: Optional directory for persistent artifact storage
        """
        # Core storage
        self._versions: dict[str, StrategyVersion] = {}  # version_id -> version
        self._artifacts: dict[
            str, list[StrategyArtifact]
        ] = {}  # version_id -> artifacts

        # Champion/Challenger tracking
        # Key: (symbol, timeframe) -> champion version_id
        self._champions: dict[tuple[str, str], str] = {}
        # Key: (symbol, timeframe) -> list of challenger version_ids
        self._challengers: dict[tuple[str, str], list[str]] = {}

        # Promotion criteria (can be customized per symbol/timeframe)
        self._criteria: dict[tuple[str, str], PromotionCriteria] = {}
        self._default_criteria = PromotionCriteria()

        # Storage directory for persistence
        self._storage_dir = storage_dir
        if storage_dir:
            storage_dir.mkdir(parents=True, exist_ok=True)

    # ==================== AC1: Champion/Challenger Management ====================

    def register_strategy(
        self,
        strategy_id: str,
        version: str,
        symbol: str,
        timeframe: str,
        config: dict[str, Any],
        parent_version: str | None = None,
    ) -> StrategyVersion:
        """Register a new strategy version.

        AC1 + AC4: Creates immutable StrategyVersion and stores initial config artifact.

        Args:
            strategy_id: Parent strategy identifier
            version: Semantic version string
            symbol: Trading symbol
            timeframe: Timeframe
            config: Strategy configuration dictionary
            parent_version: Previous version this was derived from

        Returns:
            The registered StrategyVersion (immutable)

        Raises:
            ValueError: If validation fails
        """
        # Generate version ID
        version_id = f"{strategy_id}_{version}_{uuid.uuid4().hex[:8]}"

        # Create config hash for integrity
        config_hash = self._hash_config(config)

        # Create immutable version
        strategy_version = StrategyVersion(
            version_id=version_id,
            strategy_id=strategy_id,
            version=version,
            symbol=symbol,
            timeframe=timeframe,
            status=StrategyStatus.CANDIDATE,
            created_at=datetime.utcnow(),
            config_hash=config_hash,
            parent_version=parent_version,
        )

        # Store version
        self._versions[version_id] = strategy_version
        self._artifacts[version_id] = []

        # Store config artifact
        self.store_artifact(
            version_id=version_id,
            artifact_type="config",
            data=config,
            metadata={"parent_version": parent_version},
        )

        # If parent version exists, store diff artifact
        if parent_version and parent_version in self._versions:
            parent_config = self._get_config_artifact(parent_version)
            if parent_config:
                diff = self._compute_config_diff(parent_config, config)
                self.store_artifact(
                    version_id=version_id,
                    artifact_type="diff",
                    data=diff,
                    metadata={"parent_version": parent_version},
                )

        return strategy_version

    def get_champion(self, symbol: str, timeframe: str) -> StrategyVersion | None:
        """Get the current champion for a symbol/timeframe.

        AC1: Retrieve the current champion strategy.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe

        Returns:
            Champion StrategyVersion or None if no champion exists
        """
        key = (symbol, timeframe)
        champion_id = self._champions.get(key)
        if champion_id:
            return self._versions.get(champion_id)
        return None

    def set_champion(
        self,
        version_id: str,
        symbol: str | None = None,
        timeframe: str | None = None,
    ) -> StrategyVersion:
        """Set a strategy version as champion.

        AC1: Champion management - sets the given version as champion for
        its symbol/timeframe (or specified symbol/timeframe).

        Args:
            version_id: Version to promote to champion
            symbol: Optional symbol override
            timeframe: Optional timeframe override

        Returns:
            Updated StrategyVersion with CHAMPION status

        Raises:
            ValueError: If version not found
        """
        if version_id not in self._versions:
            raise ValueError(f"Version {version_id} not found")

        version = self._versions[version_id]
        symbol = symbol or version.symbol
        timeframe = timeframe or version.timeframe
        key = (symbol, timeframe)

        # Demote existing champion to deprecated
        old_champion_id = self._champions.get(key)
        if old_champion_id and old_champion_id in self._versions:
            old_version = self._versions[old_champion_id]
            # Create new deprecated version (since versions are immutable)
            deprecated_version = StrategyVersion(
                version_id=old_version.version_id,
                strategy_id=old_version.strategy_id,
                version=old_version.version,
                symbol=old_version.symbol,
                timeframe=old_version.timeframe,
                status=StrategyStatus.DEPRECATED,
                created_at=old_version.created_at,
                config_hash=old_version.config_hash,
                parent_version=old_version.parent_version,
            )
            self._versions[old_champion_id] = deprecated_version

        # Set new champion
        self._champions[key] = version_id

        # Update version status to champion
        champion_version = StrategyVersion(
            version_id=version.version_id,
            strategy_id=version.strategy_id,
            version=version.version,
            symbol=version.symbol,
            timeframe=version.timeframe,
            status=StrategyStatus.CHAMPION,
            created_at=version.created_at,
            config_hash=version.config_hash,
            parent_version=version.parent_version,
        )
        self._versions[version_id] = champion_version

        # Remove from challengers if present
        if key in self._challengers and version_id in self._challengers[key]:
            self._challengers[key].remove(version_id)

        return champion_version

    def add_challenger(self, version_id: str) -> StrategyVersion:
        """Add a strategy version as a challenger.

        AC1: Challenger tracking - adds a candidate as challenger to compete
        with the current champion for a symbol/timeframe.

        Args:
            version_id: Version to add as challenger

        Returns:
            Updated StrategyVersion with CHALLENGER status

        Raises:
            ValueError: If version not found or not a candidate
        """
        if version_id not in self._versions:
            raise ValueError(f"Version {version_id} not found")

        version = self._versions[version_id]

        if version.status != StrategyStatus.CANDIDATE:
            raise ValueError(
                f"Version {version_id} must be in CANDIDATE status, got {version.status.value}"
            )

        key = (version.symbol, version.timeframe)

        # Add to challengers list
        if key not in self._challengers:
            self._challengers[key] = []
        if version_id not in self._challengers[key]:
            self._challengers[key].append(version_id)

        # Update version status
        challenger_version = StrategyVersion(
            version_id=version.version_id,
            strategy_id=version.strategy_id,
            version=version.version,
            symbol=version.symbol,
            timeframe=version.timeframe,
            status=StrategyStatus.CHALLENGER,
            created_at=version.created_at,
            config_hash=version.config_hash,
            parent_version=version.parent_version,
        )
        self._versions[version_id] = challenger_version

        return challenger_version

    def get_challengers(self, symbol: str, timeframe: str) -> list[StrategyVersion]:
        """Get all challengers for a symbol/timeframe.

        AC1: Retrieve all active challengers.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe

        Returns:
            List of challenger StrategyVersions
        """
        key = (symbol, timeframe)
        challenger_ids = self._challengers.get(key, [])
        return [self._versions[vid] for vid in challenger_ids if vid in self._versions]

    # ==================== AC3: Promotion Criteria ====================

    def promote_challenger(
        self,
        version_id: str,
        backtest_metrics: dict[str, Any] | None = None,
        paper_metrics: dict[str, Any] | None = None,
        override_criteria: PromotionCriteria | None = None,
    ) -> PromotionResult:
        """Attempt to promote a challenger to champion.

        AC3: Promotion with documented criteria enforcement.
        Evaluates a challenger against promotion criteria and promotes to
        champion if all criteria are met.

        Args:
            version_id: Challenger version to evaluate
            backtest_metrics: Backtest results metrics
            paper_metrics: Paper trading results metrics
            override_criteria: Optional custom criteria to use

        Returns:
            PromotionResult with success status and detailed criteria evaluation
        """
        if version_id not in self._versions:
            return PromotionResult(
                success=False,
                version_id=version_id,
                champion_id=None,
                failed_criteria=[{"error": f"Version {version_id} not found"}],
            )

        version = self._versions[version_id]

        if version.status != StrategyStatus.CHALLENGER:
            return PromotionResult(
                success=False,
                version_id=version_id,
                champion_id=None,
                failed_criteria=[
                    {
                        "status": f"Version must be CHALLENGER, got {version.status.value}"
                    }
                ],
            )

        # Get criteria
        key = (version.symbol, version.timeframe)
        criteria = override_criteria or self._criteria.get(key, self._default_criteria)

        # Get current champion for comparison
        champion = self.get_champion(version.symbol, version.timeframe)

        passed: list[str] = []
        failed: list[dict[str, str]] = []

        # Evaluate backtest criteria
        if backtest_metrics:
            composite_score = backtest_metrics.get("composite_score", 0.0)
            if composite_score >= criteria.min_backtest_score:
                passed.append(
                    f"backtest_score: {composite_score:.2f} >= {criteria.min_backtest_score}"
                )
            else:
                failed.append(
                    {
                        "backtest_score": f"{composite_score:.2f} < {criteria.min_backtest_score}"
                    }
                )

            sharpe = backtest_metrics.get("sharpe_ratio", 0.0)
            if sharpe >= criteria.min_sharpe_ratio:
                passed.append(
                    f"sharpe_ratio: {sharpe:.2f} >= {criteria.min_sharpe_ratio}"
                )
            else:
                failed.append(
                    {"sharpe_ratio": f"{sharpe:.2f} < {criteria.min_sharpe_ratio}"}
                )

            drawdown = backtest_metrics.get("max_drawdown_pct", 100.0)
            if drawdown <= criteria.max_drawdown_pct:
                passed.append(
                    f"max_drawdown: {drawdown:.2f}% <= {criteria.max_drawdown_pct}%"
                )
            else:
                failed.append(
                    {"max_drawdown": f"{drawdown:.2f}% > {criteria.max_drawdown_pct}%"}
                )

            win_rate = backtest_metrics.get("win_rate_pct", 0.0)
            if win_rate >= criteria.min_win_rate_pct:
                passed.append(
                    f"win_rate: {win_rate:.2f}% >= {criteria.min_win_rate_pct}%"
                )
            else:
                failed.append(
                    {"win_rate": f"{win_rate:.2f}% < {criteria.min_win_rate_pct}%"}
                )
        else:
            failed.append({"backtest_metrics": "No backtest metrics provided"})

        # Evaluate paper trading criteria
        if paper_metrics:
            trade_count = paper_metrics.get("trade_count", 0)
            if trade_count >= criteria.min_paper_trades:
                passed.append(
                    f"paper_trades: {trade_count} >= {criteria.min_paper_trades}"
                )
            else:
                failed.append(
                    {"paper_trades": f"{trade_count} < {criteria.min_paper_trades}"}
                )

            paper_days = paper_metrics.get("days_trading", 0)
            if paper_days >= criteria.min_paper_days:
                passed.append(f"paper_days: {paper_days} >= {criteria.min_paper_days}")
            else:
                failed.append(
                    {"paper_days": f"{paper_days} < {criteria.min_paper_days}"}
                )

            paper_sharpe = paper_metrics.get("sharpe_ratio", 0.0)
            if paper_sharpe >= criteria.min_paper_sharpe:
                passed.append(
                    f"paper_sharpe: {paper_sharpe:.2f} >= {criteria.min_paper_sharpe}"
                )
            else:
                failed.append(
                    {
                        "paper_sharpe": f"{paper_sharpe:.2f} < {criteria.min_paper_sharpe}"
                    }
                )

            paper_dd = paper_metrics.get("max_drawdown_pct", 100.0)
            if paper_dd <= criteria.max_paper_drawdown_pct:
                passed.append(
                    f"paper_drawdown: {paper_dd:.2f}% <= {criteria.max_paper_drawdown_pct}%"
                )
            else:
                failed.append(
                    {
                        "paper_drawdown": f"{paper_dd:.2f}% > {criteria.max_paper_drawdown_pct}%"
                    }
                )
        else:
            failed.append({"paper_metrics": "No paper trading metrics provided"})

        # Evaluate champion comparison
        if criteria.require_outperformance and champion:
            if backtest_metrics and paper_metrics:
                # Compare composite scores
                challenger_score = backtest_metrics.get("composite_score", 0.0)
                champion_backtest = self._get_champion_backtest_artifact(
                    champion.version_id
                )
                champion_score = (
                    champion_backtest.get("composite_score", 0.0)
                    if champion_backtest
                    else 0.0
                )

                margin = criteria.outperformance_margin_pct
                if challenger_score >= champion_score * (1 + margin / 100):
                    passed.append(
                        f"outperformance: {challenger_score:.2f} >= {champion_score:.2f} + {margin}%"
                    )
                else:
                    failed.append(
                        {
                            "outperformance": f"{challenger_score:.2f} < {champion_score:.2f} + {margin}%"
                        }
                    )
            else:
                failed.append({"outperformance": "Missing metrics for comparison"})
        elif criteria.require_outperformance:
            # No champion exists, auto-passes
            passed.append("outperformance: No existing champion")

        # Determine success
        success = len(failed) == 0

        # Promote if successful
        if success:
            self.set_champion(version_id)

        return PromotionResult(
            success=success,
            version_id=version_id,
            champion_id=champion.version_id if champion else None,
            passed_criteria=passed,
            failed_criteria=failed,
        )

    def set_promotion_criteria(
        self, symbol: str, timeframe: str, criteria: PromotionCriteria
    ) -> None:
        """Set custom promotion criteria for a symbol/timeframe.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe
            criteria: Promotion criteria to use
        """
        self._criteria[(symbol, timeframe)] = criteria

    def get_promotion_criteria(self, symbol: str, timeframe: str) -> PromotionCriteria:
        """Get promotion criteria for a symbol/timeframe.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe

        Returns:
            PromotionCriteria (default if not set)
        """
        return self._criteria.get((symbol, timeframe), self._default_criteria)

    # ==================== AC2: Artifact Storage ====================

    def store_artifact(
        self,
        version_id: str,
        artifact_type: str,
        data: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> StrategyArtifact:
        """Store an artifact for a strategy version.

        AC2: Artifact storage for config, diffs, backtest results, paper results.

        Args:
            version_id: Strategy version ID
            artifact_type: Type of artifact (config, diff, backtest, paper, live)
            data: Artifact data
            metadata: Additional metadata

        Returns:
            Created StrategyArtifact

        Raises:
            ValueError: If version not found or invalid artifact type
        """
        if version_id not in self._versions:
            raise ValueError(f"Version {version_id} not found")

        artifact_id = f"{version_id}_{artifact_type}_{uuid.uuid4().hex[:8]}"

        artifact = StrategyArtifact(
            artifact_id=artifact_id,
            version_id=version_id,
            artifact_type=artifact_type,
            data=data,
            metadata=metadata or {},
        )

        if version_id not in self._artifacts:
            self._artifacts[version_id] = []
        self._artifacts[version_id].append(artifact)

        # Persist to disk if storage directory configured
        if self._storage_dir:
            self._persist_artifact(artifact)

        return artifact

    def get_artifacts(
        self,
        version_id: str,
        artifact_type: str | None = None,
    ) -> list[StrategyArtifact]:
        """Get artifacts for a strategy version.

        AC2: Retrieve stored artifacts.

        Args:
            version_id: Strategy version ID
            artifact_type: Optional filter by artifact type

        Returns:
            List of matching artifacts
        """
        artifacts = self._artifacts.get(version_id, [])
        if artifact_type:
            artifacts = [a for a in artifacts if a.artifact_type == artifact_type]
        return artifacts

    def get_artifact(self, artifact_id: str) -> StrategyArtifact | None:
        """Get a specific artifact by ID.

        Args:
            artifact_id: Artifact identifier

        Returns:
            StrategyArtifact or None if not found
        """
        for artifacts in self._artifacts.values():
            for artifact in artifacts:
                if artifact.artifact_id == artifact_id:
                    return artifact
        return None

    # ==================== Protocol Implementation ====================

    def get_candidates(self) -> list[dict[str, Any]]:
        """Get list of candidate strategies for backtesting.

        Protocol method for pipeline integration.

        Returns:
            List of candidate strategy configurations
        """
        candidates = []
        for version in self._versions.values():
            if version.status == StrategyStatus.CANDIDATE:
                config = self._get_config_artifact(version.version_id)
                if config:
                    candidates.append(
                        {
                            "candidate_id": version.version_id,
                            "strategy_id": version.strategy_id,
                            "version": version.version,
                            "symbol": version.symbol,
                            "timeframe": version.timeframe,
                            "config": config,
                            "parent_version": version.parent_version,
                        }
                    )
        return candidates

    def update_candidate_status(
        self,
        candidate_id: str,
        status: str,
        metrics: dict[str, Any] | None = None,
    ) -> bool:
        """Update candidate status in registry.

        Protocol method for pipeline integration.

        Args:
            candidate_id: Candidate identifier (version_id)
            status: New status (pending, running, completed, failed, disqualified)
            metrics: Optional metrics to store

        Returns:
            True if updated successfully
        """
        if candidate_id not in self._versions:
            return False

        version = self._versions[candidate_id]

        # Map pipeline status to registry status
        status_map = {
            "pending": StrategyStatus.CANDIDATE,
            "running": StrategyStatus.CANDIDATE,
            "completed": StrategyStatus.CANDIDATE,  # Still candidate until promoted
            "failed": StrategyStatus.DEPRECATED,
            "disqualified": StrategyStatus.DEPRECATED,
        }

        new_status = status_map.get(status, StrategyStatus.CANDIDATE)

        # Update version (create new immutable version)
        updated_version = StrategyVersion(
            version_id=version.version_id,
            strategy_id=version.strategy_id,
            version=version.version,
            symbol=version.symbol,
            timeframe=version.timeframe,
            status=new_status,
            created_at=version.created_at,
            config_hash=version.config_hash,
            parent_version=version.parent_version,
        )
        self._versions[candidate_id] = updated_version

        # Store metrics as artifact if provided
        if metrics:
            self.store_artifact(
                version_id=candidate_id,
                artifact_type="backtest",
                data=metrics,
                metadata={
                    "status_update": status,
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )

        return True

    # ==================== Additional Query Methods ====================

    def get_version(self, version_id: str) -> StrategyVersion | None:
        """Get a specific strategy version.

        Args:
            version_id: Version identifier

        Returns:
            StrategyVersion or None if not found
        """
        return self._versions.get(version_id)

    def get_versions_by_strategy(self, strategy_id: str) -> list[StrategyVersion]:
        """Get all versions for a strategy.

        Args:
            strategy_id: Strategy identifier

        Returns:
            List of StrategyVersions
        """
        return [v for v in self._versions.values() if v.strategy_id == strategy_id]

    def get_versions_by_symbol_timeframe(
        self, symbol: str, timeframe: str
    ) -> list[StrategyVersion]:
        """Get all versions for a symbol/timeframe.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe

        Returns:
            List of StrategyVersions
        """
        return [
            v
            for v in self._versions.values()
            if v.symbol == symbol and v.timeframe == timeframe
        ]

    def list_all_versions(self) -> list[StrategyVersion]:
        """List all registered versions.

        Returns:
            List of all StrategyVersions
        """
        return list(self._versions.values())

    # ==================== Private Helpers ====================

    def _hash_config(self, config: dict[str, Any]) -> str:
        """Create a hash of configuration for integrity checking."""
        import hashlib

        config_str = json.dumps(config, sort_keys=True, default=str)
        return hashlib.sha256(config_str.encode()).hexdigest()[:16]

    def _get_config_artifact(self, version_id: str) -> dict[str, Any] | None:
        """Get config artifact for a version."""
        artifacts = self.get_artifacts(version_id, artifact_type="config")
        if artifacts:
            return artifacts[0].data
        return None

    def _get_champion_backtest_artifact(self, version_id: str) -> dict[str, Any] | None:
        """Get latest backtest artifact for champion comparison."""
        artifacts = self.get_artifacts(version_id, artifact_type="backtest")
        if artifacts:
            # Return the most recent
            return sorted(artifacts, key=lambda a: a.created_at, reverse=True)[0].data
        return None

    def _compute_config_diff(
        self, old_config: dict[str, Any], new_config: dict[str, Any]
    ) -> dict[str, Any]:
        """Compute differences between two configurations."""
        diff: dict[str, Any] = {
            "added": {},
            "removed": {},
            "modified": {},
        }

        all_keys = set(old_config.keys()) | set(new_config.keys())

        for key in all_keys:
            if key not in old_config:
                diff["added"][key] = new_config[key]
            elif key not in new_config:
                diff["removed"][key] = old_config[key]
            elif old_config[key] != new_config[key]:
                diff["modified"][key] = {
                    "old": old_config[key],
                    "new": new_config[key],
                }

        return diff

    def _persist_artifact(self, artifact: StrategyArtifact) -> None:
        """Persist artifact to disk storage."""
        if not self._storage_dir:
            return

        version_dir = self._storage_dir / artifact.version_id
        version_dir.mkdir(exist_ok=True)

        filename = f"{artifact.artifact_type}_{artifact.artifact_id}.json"
        filepath = version_dir / filename

        data = {
            "artifact_id": artifact.artifact_id,
            "version_id": artifact.version_id,
            "artifact_type": artifact.artifact_type,
            "data": artifact.data,
            "created_at": artifact.created_at.isoformat(),
            "metadata": artifact.metadata,
        }

        with open(filepath, "w") as f:
            json.dump(data, f, indent=2, default=str)


# Export all public classes
__all__ = [
    "StrategyStatus",
    "StrategyVersion",
    "StrategyArtifact",
    "PromotionCriteria",
    "PromotionResult",
    "StrategyRegistry",
    "InMemoryStrategyRegistry",
]
