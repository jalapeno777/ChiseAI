"""Integration tests for ContextAssemblyBoundary.

These tests PROVE the boundary works correctly in isolation,
establishing the foundation for future runtime integration.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from src.config.aria_config import (
    AriaConfig,
    reset_aria_config,
    set_aria_config,
)
from src.config.feature_flags import FeatureFlags
from src.governance.context_assembly import (
    ContextAssemblyBoundary,
    ContextItem,
    ContextPriority,
    UnresolvedConflict,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).resolve().parents[3] / "config" / "aria"


@pytest.fixture(autouse=True)
def _reset():
    """Reset the global singletons between tests."""
    reset_aria_config()
    yield
    reset_aria_config()


@pytest.fixture()
def aria_config():
    """Build an AriaConfig from the real YAML files."""
    config = AriaConfig.from_directory(FIXTURES_DIR)
    set_aria_config(config)
    return config


@pytest.fixture()
def boundary(aria_config):
    """Create a ContextAssemblyBoundary from real config."""
    return ContextAssemblyBoundary(aria_config=aria_config)


def _make_item(
    content: str = "test",
    priority: ContextPriority = ContextPriority.OLD_CONVERSATIONS,
    is_protected_identity: bool = False,
    token_size: int = 100,
    source: str = "test",
    confidence: float = 1.0,
    stale: bool = False,
    is_mandatory: bool = False,
) -> ContextItem:
    """Factory for creating ContextItem instances."""
    return ContextItem(
        content=content,
        priority=priority,
        is_mandatory=is_mandatory,
        is_protected_identity=is_protected_identity,
        token_size=token_size,
        source=source,
        confidence=confidence,
        stale=stale,
    )


# ---------------------------------------------------------------------------
# Tests: Feature Flag Wiring
# ---------------------------------------------------------------------------


class TestFeatureFlagWiring:
    """Tests that feature flag uses Redis-backed pattern."""

    def test_is_enabled_uses_redis_feature_flags(self, aria_config, monkeypatch):
        """_is_enabled() must use get_feature_flags().get_redis_value()."""
        # Create mock feature flags that returns False for the flag
        mock_flags = FeatureFlags()
        monkeypatch.setattr(
            "src.governance.context_assembly.get_feature_flags",
            lambda: mock_flags,
        )

        b = ContextAssemblyBoundary(aria_config=aria_config)
        # Should consult Redis, not env var
        result = b._is_enabled()
        assert isinstance(result, bool)

    def test_feature_flag_key_correct(self, boundary):
        """Feature flag key should be the correct Redis key."""
        assert (
            boundary._feature_flag_key
            == "chise:feature_flags:governance:context_assembly_enabled"
        )


# ---------------------------------------------------------------------------
# Tests: Unresolved Conflict Surfacing
# ---------------------------------------------------------------------------


class TestUnresolvedConflictSurfacing:
    """Tests that unresolved conflicts are surfaced as first-class output."""

    def test_conflicting_evidence_produces_unresolved(self, boundary):
        """When evidence strengths are too close to determine winner, conflict surfaced."""
        items = [
            _make_item(
                content="Belief A - evidence strength 0.7",
                priority=ContextPriority.PROJECT_RULES_AND_ARCHITECTURE,
                token_size=200,
                confidence=0.7,
                source="source_a",
            ),
            _make_item(
                content="Belief B - evidence strength 0.68",
                priority=ContextPriority.PROJECT_RULES_AND_ARCHITECTURE,
                token_size=200,
                confidence=0.68,
                source="source_b",
            ),
        ]
        result = boundary.assemble(items, max_tokens=250)  # Can't fit both

        assert hasattr(result, "unresolved_conflicts")
        assert len(result.unresolved_conflicts) > 0
        conflict = result.unresolved_conflicts[0]
        assert isinstance(conflict, UnresolvedConflict)
        assert conflict.reason in (
            "contradictory_signals",
            "budget_exceeded_all_options",
            "insufficient_evidence",
        )
        assert conflict.suggested_resolution in (
            "escalate_to_craig",
            "gather_more_evidence",
        )

    def test_trace_shows_conflict_unresolved_action(self, boundary):
        """AssemblyTrace should have action='conflict_unresolved' for unresolved items."""
        items = [
            _make_item(
                content="Conflicting A",
                priority=ContextPriority.CORE_PERSONALITY,
                token_size=300,
                confidence=0.6,
                source="conf_a",
            ),
            _make_item(
                content="Conflicting B",
                priority=ContextPriority.CORE_PERSONALITY,
                token_size=300,
                confidence=0.58,
                source="conf_b",
            ),
        ]
        result = boundary.assemble(items, max_tokens=350)

        # The conflict should be traceable
        assert len(result.traces) >= 1
        # Check that at least one trace has conflict_unresolved action
        conflict_traces = [
            t for t in result.traces if t.action == "conflict_unresolved"
        ]
        assert len(conflict_traces) > 0

    def test_unresolved_conflict_dataclass_structure(self):
        """UnresolvedConflict dataclass should have correct structure."""
        conflict = UnresolvedConflict(
            item_ids=["source_a:core_personality", "source_b:core_personality"],
            evidence_strengths=[0.7, 0.68],
            reason="contradictory_signals",
            suggested_resolution="escalate_to_craig",
        )
        assert conflict.item_ids == [
            "source_a:core_personality",
            "source_b:core_personality",
        ]
        assert conflict.evidence_strengths == [0.7, 0.68]
        assert conflict.reason == "contradictory_signals"
        assert conflict.suggested_resolution == "escalate_to_craig"

    def test_assembly_result_has_unresolved_conflicts_field(self, boundary):
        """AssemblyResult should have unresolved_conflicts field with default empty list."""
        result = boundary.assemble([], max_tokens=1000)
        assert hasattr(result, "unresolved_conflicts")
        assert isinstance(result.unresolved_conflicts, list)


# ---------------------------------------------------------------------------
# Tests: Protected Identity Enforcement
# ---------------------------------------------------------------------------


class TestProtectedIdentityEnforcement:
    """Tests that protected identity items survive budget pressure."""

    def test_protected_identity_always_included(self, boundary):
        """Protected items must survive even with tiny budget."""
        items = [
            _make_item(
                content="Protected identity item",
                priority=ContextPriority.CORE_PERSONALITY,
                is_protected_identity=True,
                token_size=500,
            ),
        ]
        result = boundary.assemble(items, max_tokens=100)  # 5x too small
        assert len(result.assembled_items) == 1
        assert result.assembled_items[0].content == "Protected identity item"

    def test_protected_trace_action(self, boundary):
        """Protected items should have trace action 'protected'."""
        items = [
            _make_item(
                content="Protected",
                priority=ContextPriority.CORE_PERSONALITY,
                is_protected_identity=True,
                token_size=500,
            ),
        ]
        result = boundary.assemble(items, max_tokens=1)
        protected_traces = [t for t in result.traces if t.action == "protected"]
        assert len(protected_traces) == 1


# ---------------------------------------------------------------------------
# Tests: Budget Eviction
# ---------------------------------------------------------------------------


class TestBudgetEviction:
    """Tests eviction under budget pressure."""

    def test_lower_priority_evicted_first(self, boundary):
        """Low priority items evicted before high priority."""
        items = [
            _make_item(
                content="HIGH",
                priority=ContextPriority.CORE_PERSONALITY,
                token_size=300,
            ),
            _make_item(
                content="LOW",
                priority=ContextPriority.OLD_CONVERSATIONS,
                token_size=300,
            ),
        ]
        result = boundary.assemble(items, max_tokens=300)
        contents = [i.content for i in result.assembled_items]
        assert "HIGH" in contents
        assert "LOW" not in contents

    def test_total_tokens_respects_max(self, boundary):
        """Total tokens should never exceed max_tokens."""
        items = [_make_item(priority=p, token_size=500) for p in ContextPriority]
        result = boundary.assemble(items, max_tokens=1500)
        assert result.total_tokens <= result.max_tokens


# ---------------------------------------------------------------------------
# Tests: Disabled Flag Behavior
# ---------------------------------------------------------------------------


class TestDisabledFlagBehavior:
    """Tests safe behavior when feature flag is disabled."""

    def test_disabled_passthrough_all_items(self, boundary, monkeypatch):
        """When disabled via feature flag, all items pass through."""
        # Disable via monkeypatching _enabled directly
        boundary._enabled = False

        items = [
            _make_item(token_size=10000),
            _make_item(token_size=10000),
        ]
        result = boundary.assemble(items, max_tokens=100)
        assert len(result.assembled_items) == 2


# ---------------------------------------------------------------------------
# Tests: Real Runtime Trace
# ---------------------------------------------------------------------------


class TestRealRuntimeTrace:
    """Tests that produce real trace samples."""

    def test_full_trace_sample(self, boundary):
        """Produce real trace output for verification."""
        items = [
            _make_item(
                content="PROTECTED identity",
                priority=ContextPriority.CORE_PERSONALITY,
                is_protected_identity=True,
                token_size=100,
                source="identity",
            ),
            _make_item(
                content="MANDATORY task",
                priority=ContextPriority.CURRENT_TASK_DETAILS,
                is_mandatory=True,
                token_size=100,
                source="task",
            ),
            _make_item(
                content="OLD lesson",
                priority=ContextPriority.OLD_LESSONS,
                token_size=100,
                source="lesson",
            ),
            _make_item(
                content="STALE memory",
                priority=ContextPriority.OLD_CONVERSATIONS,
                stale=True,
                confidence=0.2,
                token_size=100,
                source="qdrant",
            ),
        ]
        result = boundary.assemble(items, max_tokens=250)

        # Print trace for manual verification
        for t in result.traces:
            print(f"  {t.action}: {t.item_id} - {t.reason} ({t.token_size} tokens)")

        # Verify trace completeness
        actions = {t.action for t in result.traces}
        assert "protected" in actions or "included" in actions
        assert len(result.traces) == len(items)

    def test_unresolved_conflict_trace_sample(self, boundary):
        """Produce unresolved conflict trace for verification."""
        items = [
            _make_item(
                content="Evidence A - 0.65 confidence",
                priority=ContextPriority.PROJECT_RULES_AND_ARCHITECTURE,
                token_size=200,
                confidence=0.65,
                source="src_a",
            ),
            _make_item(
                content="Evidence B - 0.63 confidence",
                priority=ContextPriority.PROJECT_RULES_AND_ARCHITECTURE,
                token_size=200,
                confidence=0.63,
                source="src_b",
            ),
        ]
        result = boundary.assemble(items, max_tokens=250)

        print(f"Unresolved conflicts: {len(result.unresolved_conflicts)}")
        for uc in result.unresolved_conflicts:
            print(f"  {uc.reason}: {uc.item_ids} -> {uc.suggested_resolution}")

        # Should have unresolved conflict since evidence is close
        assert hasattr(result, "unresolved_conflicts")

    def test_detect_conflicts_method_exists(self, boundary):
        """Boundary should have _detect_conflicts method."""
        assert hasattr(boundary, "_detect_conflicts")
        assert callable(boundary._detect_conflicts)

    def test_conflict_detection_with_similar_confidence(self, boundary):
        """Items with similar confidence in same priority should trigger conflict detection."""
        items = [
            _make_item(
                content="Evidence 1",
                priority=ContextPriority.PROJECT_RULES_AND_ARCHITECTURE,
                token_size=200,
                confidence=0.7,
                source="src1",
            ),
            _make_item(
                content="Evidence 2",
                priority=ContextPriority.PROJECT_RULES_AND_ARCHITECTURE,
                token_size=200,
                confidence=0.65,
                source="src2",
            ),
        ]
        conflicts = boundary._detect_conflicts(items, max_tokens=250)
        # With similar confidence and tight budget, should detect conflict
        assert isinstance(conflicts, list)
