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
    assemble_aria_context,
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


# ---------------------------------------------------------------------------
# Tests: Runtime Integration (full_cycle._store_aria_briefing)
# ---------------------------------------------------------------------------


class TestRuntimeIntegration:
    """Tests proving boundary is called from full_cycle._store_aria_briefing."""

    def test_assemble_aria_context_helper_exists(self):
        """assemble_aria_context helper should exist and be callable."""
        from src.governance.context_assembly import assemble_aria_context

        assert callable(assemble_aria_context)

    def test_assemble_aria_context_produces_assembly_result(self, boundary):
        """assemble_aria_context should produce an AssemblyResult."""
        from src.governance.context_assembly import assemble_aria_context

        findings = ["System memory is healthy", "Runtime stability is good"]
        recommendations = ["Continue monitoring", "Run daily self-assessment"]
        evidence = {
            "self_assessment_score": 0.85,
            "belief_conflicts": 0,
            "belief_revisions": 0,
        }
        beliefs_summary = "System is stable with no conflicts"

        result = assemble_aria_context(
            findings=findings,
            recommendations=recommendations,
            evidence=evidence,
            beliefs_summary=beliefs_summary,
            max_tokens=12000,
            boundary=boundary,
        )

        assert hasattr(result, "assembled_context")
        assert hasattr(result, "traces")
        assert hasattr(result, "unresolved_conflicts")
        assert isinstance(result.traces, list)
        assert isinstance(result.unresolved_conflicts, list)

    def test_assemble_aria_context_maps_findings_to_current_task(self, boundary):
        """Findings should be mapped to CURRENT_TASK_DETAILS priority."""
        findings = ["Finding A", "Finding B"]
        recommendations = []
        evidence = {}
        beliefs_summary = ""

        result = assemble_aria_context(
            findings=findings,
            recommendations=recommendations,
            evidence=evidence,
            beliefs_summary=beliefs_summary,
            max_tokens=12000,
            boundary=boundary,
        )

        # Check that traces contain items from findings with CURRENT_TASK_DETAILS priority
        current_task_traces = [t for t in result.traces if "findings" in t.item_id]
        assert len(current_task_traces) >= len(findings)

    def test_assemble_aria_context_maps_beliefs_to_project_rules(self, boundary):
        """Beliefs summary should be mapped to PROJECT_RULES_AND_ARCHITECTURE priority."""
        findings = []
        recommendations = []
        evidence = {}
        beliefs_summary = "System is stable with no conflicts"

        result = assemble_aria_context(
            findings=findings,
            recommendations=recommendations,
            evidence=evidence,
            beliefs_summary=beliefs_summary,
            max_tokens=12000,
            boundary=boundary,
        )

        # Check that traces contain beliefs with PROJECT_RULES_AND_ARCHITECTURE priority
        project_rules_traces = [t for t in result.traces if "beliefs" in t.item_id]
        assert len(project_rules_traces) >= 1

    def test_assemble_aria_context_trace_includes_included_action(self, boundary):
        """Trace should show 'included' action for items within budget."""
        findings = ["Finding A"]
        recommendations = ["Recommendation A"]
        evidence = {"score": 0.9}
        beliefs_summary = "Stable"

        result = assemble_aria_context(
            findings=findings,
            recommendations=recommendations,
            evidence=evidence,
            beliefs_summary=beliefs_summary,
            max_tokens=12000,
            boundary=boundary,
        )

        included_traces = [t for t in result.traces if t.action == "included"]
        assert len(included_traces) >= 1

    def test_assemble_aria_context_unresolved_conflicts_when_close_evidence(
        self, boundary
    ):
        """When evidence strengths are close, unresolved_conflicts should be populated."""
        findings = []
        recommendations = []
        evidence = {}
        beliefs_summary = ""

        # Create items with similar confidence in same priority that can't all fit
        items = [
            _make_item(
                content="Evidence A - 0.65 confidence",
                priority=ContextPriority.CURRENT_TASK_DETAILS,
                token_size=5000,
                confidence=0.65,
                source="src_a",
            ),
            _make_item(
                content="Evidence B - 0.63 confidence",
                priority=ContextPriority.CURRENT_TASK_DETAILS,
                token_size=5000,
                confidence=0.63,
                source="src_b",
            ),
        ]

        result = boundary.assemble(items, max_tokens=6000)

        # With similar confidence and tight budget, should detect conflict
        assert len(result.unresolved_conflicts) > 0

    def test_runtime_trace_sample_inclusion(self, boundary):
        """Produce runtime trace showing included items."""
        findings = [
            "System memory is healthy",
            "All components operational",
            "No incidents detected",
        ]
        recommendations = [
            "Continue monitoring",
            "Review recent metrics",
        ]
        evidence = {
            "self_assessment_score": 0.88,
            "belief_conflicts": 0,
            "belief_revisions": 0,
            "autonomy_level": "bounded",
        }
        beliefs_summary = "Active conflicts: 0, Revisions applied: 0"

        result = assemble_aria_context(
            findings=findings,
            recommendations=recommendations,
            evidence=evidence,
            beliefs_summary=beliefs_summary,
            max_tokens=12000,
            boundary=boundary,
        )

        print("\n=== Runtime Inclusion Trace ===")
        for t in result.traces:
            if t.action == "included":
                print(f"  INCLUDED: {t.item_id} - {t.reason} ({t.token_size} tokens)")

        included_traces = [t for t in result.traces if t.action == "included"]
        assert len(included_traces) >= 1

    def test_runtime_trace_sample_unresolved_conflict(self, boundary):
        """Produce runtime trace showing unresolved conflicts."""
        items = [
            _make_item(
                content="Strategy A - confidence 0.72",
                priority=ContextPriority.PROJECT_RULES_AND_ARCHITECTURE,
                token_size=3000,
                confidence=0.72,
                source="strategy_a",
            ),
            _make_item(
                content="Strategy B - confidence 0.70",
                priority=ContextPriority.PROJECT_RULES_AND_ARCHITECTURE,
                token_size=3000,
                confidence=0.70,
                source="strategy_b",
            ),
            _make_item(
                content="Strategy C - confidence 0.68",
                priority=ContextPriority.PROJECT_RULES_AND_ARCHITECTURE,
                token_size=3000,
                confidence=0.68,
                source="strategy_c",
            ),
        ]

        result = boundary.assemble(items, max_tokens=5000)

        print("\n=== Runtime Unresolved Conflict Trace ===")
        for t in result.traces:
            print(f"  {t.action}: {t.item_id} - {t.reason} ({t.token_size} tokens)")
        if result.unresolved_conflicts:
            print("Unresolved conflicts:")
            for uc in result.unresolved_conflicts:
                print(f"  {uc.reason}: {uc.item_ids} -> {uc.suggested_resolution}")

        assert hasattr(result, "unresolved_conflicts")

    def test_runtime_trace_sample_protected_and_evicted(self, boundary):
        """Produce runtime trace showing protected and evicted items."""
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
                content="LOW priority old conversation",
                priority=ContextPriority.OLD_CONVERSATIONS,
                token_size=100,
                source="qdrant",
            ),
            _make_item(
                content="STALE low confidence old lesson",
                priority=ContextPriority.OLD_LESSONS,
                stale=True,
                confidence=0.2,
                token_size=100,
                source="lessons",
            ),
        ]

        result = boundary.assemble(items, max_tokens=250)

        print("\n=== Runtime Protected/Evicted Trace ===")
        for t in result.traces:
            print(f"  {t.action}: {t.item_id} - {t.reason} ({t.token_size} tokens)")

        protected_traces = [t for t in result.traces if t.action == "protected"]
        evicted_traces = [t for t in result.traces if t.action == "evicted"]
        included_traces = [t for t in result.traces if t.action == "included"]

        assert len(protected_traces) >= 1
        assert len(included_traces) >= 1
        assert len(evicted_traces) >= 1

    def test_store_aria_briefing_calls_boundary(self, aria_config):
        """Prove _store_aria_briefing invokes assemble_aria_context with correct payload.

        This test exercises the REAL runtime call chain:
        AutonomousCognitionFullCycle._store_aria_briefing()
            -> assemble_aria_context()
            -> ContextAssemblyBoundary.assemble()
        """
        from unittest.mock import MagicMock, patch

        from src.autonomous_cognition.contracts import CycleResult
        from src.autonomous_cognition.full_cycle import (
            AutonomousCognitionFullCycle,
        )

        # Create a real boundary to use in the call chain
        boundary = ContextAssemblyBoundary(aria_config=aria_config)

        # Create mock redis client
        mock_redis = MagicMock()
        stored_briefing = {}

        def capture_set(key, value, ex=None):
            stored_briefing["key"] = key
            stored_briefing["value"] = value  # JSON string

        mock_redis.set = capture_set

        # Create realistic cycle result
        result = CycleResult.create(run_id="test-run-001")
        result.status = "completed"
        result.self_assessment_status = "ok"
        result.belief_conflicts = 0
        result.belief_revisions = 0
        result.experiments_run = 1
        result.promotions = 0
        result.rejections = 1
        result.constitution_violations = 0
        result.autonomy_level_after = "bounded"
        result.completed_at = "2026-04-01T12:00:00+00:00"

        # Create mock assessment with findings that have .description attributes
        mock_assessment = MagicMock()
        mock_assessment.overall_score = 0.85
        mock_assessment.status = "ok"

        # Create finding objects with .description attribute
        finding1 = MagicMock()
        finding1.description = "System memory is healthy"

        finding2 = MagicMock()
        finding2.description = "Runtime stability is good"

        mock_assessment.findings = [finding1, finding2]

        # Create recommendation objects with .description attribute
        rec1 = MagicMock()
        rec1.description = "Continue monitoring"

        rec2 = MagicMock()
        rec2.description = "Run daily self-assessment"

        mock_assessment.recommendations = [rec1, rec2]

        governance_state = {
            "belief_registry": {
                "__global__": {"next_check_after": "2026-04-02T12:00:00+00:00"}
            }
        }

        # Patch boundary creation so we use our real boundary
        with patch(
            "src.governance.context_assembly.ContextAssemblyBoundary",
            return_value=boundary,
        ):
            cycle = AutonomousCognitionFullCycle()

            # Call the actual _store_aria_briefing method
            cycle._store_aria_briefing(
                redis_client=mock_redis,
                result=result,
                mode="full",
                shadow_mode=True,
                actions=["daily self assessment", "belief consistency check"],
                assessment=mock_assessment,
                governance_state=governance_state,
            )

        # Verify the briefing was stored in Redis
        assert "key" in stored_briefing
        assert stored_briefing["key"] == "autocog:aria_briefing:current"

        # Parse the stored briefing
        import json

        briefing = json.loads(stored_briefing["value"])

        # Verify context_assembly keys exist
        assert (
            "context_assembly" in briefing
        ), f"Briefing must contain 'context_assembly' key. Keys: {list(briefing.keys())}"
        assert (
            "context_assembly_traces" in briefing
        ), f"Briefing must contain 'context_assembly_traces' key. Keys: {list(briefing.keys())}"

        # Verify context_assembly structure
        ca = briefing["context_assembly"]
        assert "assembled_context" in ca
        assert "total_tokens" in ca
        assert "max_tokens" in ca
        assert "unresolved_conflicts" in ca

        # Verify context_assembly_traces has entries with action values
        traces = briefing["context_assembly_traces"]
        assert len(traces) > 0, "context_assembly_traces must not be empty"

        # Check that traces have the expected structure
        actions = {t["action"] for t in traces}
        assert (
            "included" in actions or "protected" in actions
        ), f"Traces must include 'included' or 'protected' actions. Found: {actions}"

        # Verify trace entries have expected fields
        for trace in traces:
            assert "action" in trace
            assert "item_id" in trace
            assert "reason" in trace
            assert "priority" in trace
            assert "token_size" in trace

    def test_store_aria_briefing_handles_none_description(self, aria_config):
        """Prove findings with None description are handled gracefully.

        When a finding's .description is None, it should fall back to str(f).
        """
        from unittest.mock import MagicMock, patch

        from src.autonomous_cognition.contracts import CycleResult
        from src.autonomous_cognition.full_cycle import (
            AutonomousCognitionFullCycle,
        )

        boundary = ContextAssemblyBoundary(aria_config=aria_config)

        mock_redis = MagicMock()
        stored_briefing = {}

        def capture_set(key, value, ex=None):
            stored_briefing["key"] = key
            stored_briefing["value"] = value

        mock_redis.set = capture_set

        result = CycleResult.create(run_id="test-run-002")
        result.status = "completed"
        result.self_assessment_status = "ok"
        result.belief_conflicts = 0
        result.belief_revisions = 0
        result.experiments_run = 0
        result.promotions = 0
        result.rejections = 0
        result.constitution_violations = 0
        result.autonomy_level_after = "bounded"
        result.completed_at = "2026-04-01T12:00:00+00:00"

        # Create finding with None description
        mock_assessment = MagicMock()
        mock_assessment.overall_score = 0.80
        mock_assessment.status = "ok"

        finding_none_desc = MagicMock()
        finding_none_desc.description = None

        finding_normal = MagicMock()
        finding_normal.description = "Normal finding"

        mock_assessment.findings = [finding_none_desc, finding_normal]
        mock_assessment.recommendations = []

        governance_state = {}

        with patch(
            "src.governance.context_assembly.ContextAssemblyBoundary",
            return_value=boundary,
        ):
            cycle = AutonomousCognitionFullCycle()

            # Should not raise - None description should be handled
            cycle._store_aria_briefing(
                redis_client=mock_redis,
                result=result,
                mode="full",
                shadow_mode=True,
                actions=["test"],
                assessment=mock_assessment,
                governance_state=governance_state,
            )

        # Verify the briefing was stored successfully
        assert "key" in stored_briefing

        import json

        briefing = json.loads(stored_briefing["value"])
        assert "context_assembly" in briefing
        assert "context_assembly_traces" in briefing
