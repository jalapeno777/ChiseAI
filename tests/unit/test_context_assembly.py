"""Tests for the Final Context Assembly Boundary.

Covers priority ordering, protected identity enforcement, budget eviction,
stale/low-confidence handling, tracing, and feature flag behavior.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from src.config.aria_config import (
    AriaConfig,
    reset_aria_config,
    set_aria_config,
)
from src.governance.context_assembly import (
    CONTEXT_ASSEMBLY_FEATURE_FLAG,
    ContextAssemblyBoundary,
    ContextItem,
    ContextPriority,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "config" / "aria"


@pytest.fixture(autouse=True)
def _reset_global():
    """Reset the global singleton between tests."""
    reset_aria_config()
    yield
    reset_aria_config()


@pytest.fixture()
def real_aria_dir():
    """Return path to the real config/aria/ directory."""
    return FIXTURES_DIR


@pytest.fixture()
def aria_config(real_aria_dir):
    """Build an AriaConfig from the real YAML files."""
    config = AriaConfig.from_directory(real_aria_dir)
    set_aria_config(config)
    return config


@pytest.fixture()
def boundary(aria_config):
    """Create a ContextAssemblyBoundary from real config."""
    return ContextAssemblyBoundary(aria_config=aria_config)


def _make_item(
    content: str = "test content",
    priority: ContextPriority = ContextPriority.OLD_CONVERSATIONS,
    is_mandatory: bool = False,
    is_protected_identity: bool = False,
    confidence: float = 1.0,
    stale: bool = False,
    token_size: int = 100,
    source: str = "test",
) -> ContextItem:
    """Factory for creating ContextItem instances."""
    return ContextItem(
        content=content,
        priority=priority,
        is_mandatory=is_mandatory,
        is_protected_identity=is_protected_identity,
        confidence=confidence,
        stale=stale,
        token_size=token_size,
        source=source,
    )


# ---------------------------------------------------------------------------
# Tests: ContextItem basics
# ---------------------------------------------------------------------------


class TestContextItem:
    """Tests for ContextItem dataclass behavior."""

    def test_priority_index_assigned(self):
        """priority_index should map from enum value."""
        item = _make_item(priority=ContextPriority.CORE_PERSONALITY)
        assert item.priority_index == 0

    def test_priority_index_order(self):
        """Higher priority should have lower index."""
        core = _make_item(priority=ContextPriority.CORE_PERSONALITY)
        old_conv = _make_item(priority=ContextPriority.OLD_CONVERSATIONS)
        assert core.priority_index < old_conv.priority_index

    def test_can_evict_mandatory_false(self):
        """Mandatory items cannot be evicted."""
        item = _make_item(is_mandatory=True)
        assert item.can_evict() is False

    def test_can_evict_protected_false(self):
        """Protected identity items cannot be evicted."""
        item = _make_item(is_protected_identity=True)
        assert item.can_evict() is False

    def test_can_evict_optional_true(self):
        """Optional, non-protected items can be evicted."""
        item = _make_item(is_mandatory=False, is_protected_identity=False)
        assert item.can_evict() is True

    def test_mandatory_and_protected_both_false(self):
        """An item that is both mandatory and protected still can't evict."""
        item = _make_item(is_mandatory=True, is_protected_identity=True)
        assert item.can_evict() is False


# ---------------------------------------------------------------------------
# Tests: ContextAssemblyBoundary initialization
# ---------------------------------------------------------------------------


class TestBoundaryInit:
    """Tests for boundary initialization."""

    def test_enabled_by_default(self, boundary):
        """Boundary should be enabled by default."""
        assert boundary.enabled is True

    def test_disabled_via_env(self, aria_config, monkeypatch):
        """Setting env var to 'false' should disable the boundary."""
        monkeypatch.setenv("CHISEAI_CONTEXT_ASSEMBLY_ENABLED", "false")
        b = ContextAssemblyBoundary(aria_config=aria_config)
        assert b.enabled is False

    def test_protected_items_populated(self, boundary):
        """Protected identity items should include approval_gated_fields."""
        protected = boundary.get_protected_identity_items()
        assert isinstance(protected, set)
        assert len(protected) > 0

    def test_protected_items_contains_hardlined_soul_items(self, boundary):
        """Protected items should include hardlined_soul_items from identity contract."""
        protected = boundary.get_protected_identity_items()
        assert "hardlined_soul_items" in protected

    def test_protected_items_contains_prd_objectives(self, boundary):
        """Protected items should include prd_objectives."""
        protected = boundary.get_protected_identity_items()
        assert "prd_objectives" in protected

    def test_feature_flag_key(self, boundary):
        """Feature flag key should match expected constant."""
        assert boundary._feature_flag_key == CONTEXT_ASSEMBLY_FEATURE_FLAG


# ---------------------------------------------------------------------------
# Tests: Budget allocation calculation
# ---------------------------------------------------------------------------


class TestBudgetAllocation:
    """Tests for calculate_budget_allocation."""

    def test_allocation_sums_to_max(self, boundary):
        """Budget allocation should sum to max_tokens."""
        allocation = boundary.calculate_budget_allocation(12000)
        total = sum(allocation.values())
        assert total == 12000

    def test_allocation_categories_match_policy(self, boundary):
        """All categories from policy should be in allocation."""
        allocation = boundary.calculate_budget_allocation(10000)
        for entry in boundary._policy.allocation_order:
            name = entry["name"]
            assert name in allocation, f"Missing category: {name}"

    def test_allocation_percentages_correct(self, boundary):
        """Each category should get the correct percentage."""
        max_tokens = 10000
        allocation = boundary.calculate_budget_allocation(max_tokens)
        for entry in boundary._policy.allocation_order:
            name = entry["name"]
            expected = int(max_tokens * entry["reserve_pct"] / 100)
            assert allocation[name] == expected


# ---------------------------------------------------------------------------
# Tests: Assembly - priority ordering
# ---------------------------------------------------------------------------


class TestAssemblyPriority:
    """Tests that higher priority items are included before lower priority."""

    def test_high_priority_included_first(self, boundary):
        """Core personality should be included before old conversations."""
        items = [
            _make_item(
                content="old conv",
                priority=ContextPriority.OLD_CONVERSATIONS,
                token_size=100,
            ),
            _make_item(
                content="core personality",
                priority=ContextPriority.CORE_PERSONALITY,
                token_size=100,
            ),
        ]
        result = boundary.assemble(items, max_tokens=100)
        # Only the first item (core personality) should fit
        assert len(result.assembled_items) == 1
        assert result.assembled_items[0].content == "core personality"

    def test_all_items_fit_in_budget(self, boundary):
        """When budget allows, all items should be included."""
        items = [
            _make_item(priority=ContextPriority.CORE_PERSONALITY, token_size=100),
            _make_item(priority=ContextPriority.OLD_CONVERSATIONS, token_size=100),
        ]
        result = boundary.assemble(items, max_tokens=1000)
        assert len(result.assembled_items) == 2

    def test_assembled_order_respects_priority(self, boundary):
        """Assembled items should be in priority order regardless of input order."""
        items = [
            _make_item(
                content="z_last",
                priority=ContextPriority.OLD_CONVERSATIONS,
                token_size=100,
            ),
            _make_item(
                content="a_first",
                priority=ContextPriority.CORE_PERSONALITY,
                token_size=100,
            ),
            _make_item(
                content="m_middle",
                priority=ContextPriority.CURRENT_TASK_DETAILS,
                token_size=100,
            ),
        ]
        result = boundary.assemble(items, max_tokens=1000)
        contents = [i.content for i in result.assembled_items]
        assert contents == ["a_first", "m_middle", "z_last"]


# ---------------------------------------------------------------------------
# Tests: Assembly - protected identity
# ---------------------------------------------------------------------------


class TestProtectedIdentity:
    """Tests that protected identity items are never evicted."""

    def test_protected_item_always_included(self, boundary):
        """Protected identity items should always be included."""
        items = [
            _make_item(
                content="protected soul item",
                priority=ContextPriority.CORE_PERSONALITY,
                is_protected_identity=True,
                token_size=100,
            ),
        ]
        result = boundary.assemble(items, max_tokens=50)  # Less than token_size
        # Protected items should still be included even over budget
        assert len(result.assembled_items) == 1
        assert result.assembled_items[0].content == "protected soul item"

    def test_protected_trace_reason(self, boundary):
        """Protected items should be traced as 'protected'."""
        item = _make_item(
            priority=ContextPriority.CORE_PERSONALITY,
            is_protected_identity=True,
            token_size=100,
        )
        result = boundary.assemble([item], max_tokens=1000)
        protected_traces = [t for t in result.traces if t.action == "protected"]
        assert len(protected_traces) == 1
        assert protected_traces[0].reason == "protected_identity_item"

    def test_protected_included_over_optional(self, boundary):
        """Protected items should be included even if they push optional items out."""
        items = [
            _make_item(
                content="optional old lesson",
                priority=ContextPriority.OLD_LESSONS,
                token_size=500,
            ),
            _make_item(
                content="protected identity",
                priority=ContextPriority.CORE_PERSONALITY,
                is_protected_identity=True,
                token_size=500,
            ),
            _make_item(
                content="optional old conv",
                priority=ContextPriority.OLD_CONVERSATIONS,
                token_size=500,
            ),
        ]
        # Budget: 600 tokens. Protected (500) + old_lesson (500) would be 1000.
        # Protected always goes in, then old_lesson (500) fits, old_conv evicted.
        result = boundary.assemble(items, max_tokens=1000)
        contents = [i.content for i in result.assembled_items]
        assert "protected identity" in contents
        assert "optional old lesson" in contents
        assert "optional old conv" not in contents


# ---------------------------------------------------------------------------
# Tests: Assembly - mandatory items
# ---------------------------------------------------------------------------


class TestMandatoryItems:
    """Tests that mandatory items are always included if budget allows."""

    def test_mandatory_included_when_budget_allows(self, boundary):
        """Mandatory items should be included if budget allows."""
        item = _make_item(
            priority=ContextPriority.PROJECT_RULES_AND_ARCHITECTURE,
            is_mandatory=True,
            token_size=100,
        )
        result = boundary.assemble([item], max_tokens=1000)
        assert len(result.assembled_items) == 1

    def test_mandatory_trace_reason(self, boundary):
        """Mandatory items should be traced as 'included' with reason 'mandatory'."""
        item = _make_item(
            priority=ContextPriority.CURRENT_TASK_DETAILS,
            is_mandatory=True,
            token_size=100,
        )
        result = boundary.assemble([item], max_tokens=1000)
        mandatory_traces = [
            t
            for t in result.traces
            if t.action == "included" and t.reason == "mandatory"
        ]
        assert len(mandatory_traces) == 1

    def test_mandatory_exceeds_budget_traced(self, boundary):
        """Mandatory items that exceed budget should be traced as budget_exceeded."""
        item = _make_item(
            priority=ContextPriority.CURRENT_TASK_DETAILS,
            is_mandatory=True,
            token_size=5000,
        )
        result = boundary.assemble([item], max_tokens=1000)
        exceeded_traces = [t for t in result.traces if t.action == "budget_exceeded"]
        assert len(exceeded_traces) == 1
        assert exceeded_traces[0].reason == "mandatory_item_exceeds_budget"


# ---------------------------------------------------------------------------
# Tests: Assembly - budget eviction
# ---------------------------------------------------------------------------


class TestBudgetEviction:
    """Tests that lower priority items are evicted first under budget pressure."""

    def test_low_priority_evicted_first(self, boundary):
        """When budget is tight, lower priority items should be evicted first."""
        items = [
            _make_item(
                content="core",
                priority=ContextPriority.CORE_PERSONALITY,
                token_size=300,
            ),
            _make_item(
                content="task",
                priority=ContextPriority.CURRENT_TASK_DETAILS,
                token_size=300,
            ),
            _make_item(
                content="old_conv",
                priority=ContextPriority.OLD_CONVERSATIONS,
                token_size=300,
            ),
        ]
        # Budget allows 2 items (600 tokens)
        result = boundary.assemble(items, max_tokens=600)
        contents = [i.content for i in result.assembled_items]
        assert "core" in contents
        assert "task" in contents
        assert "old_conv" not in contents

    def test_evicted_traces_have_reason(self, boundary):
        """Evicted items should have 'budget_exceeded' reason in trace."""
        items = [
            _make_item(
                priority=ContextPriority.OLD_CONVERSATIONS,
                token_size=100,
            ),
        ]
        result = boundary.assemble(items, max_tokens=0)
        evicted = [t for t in result.traces if t.action == "evicted"]
        assert len(evicted) == 1
        assert evicted[0].reason == "budget_exceeded"

    def test_total_tokens_does_not_exceed_max(self, boundary):
        """Total tokens in assembled result should never exceed max_tokens."""
        items = [
            _make_item(
                priority=p,
                token_size=500,
            )
            for p in ContextPriority
        ]
        result = boundary.assemble(items, max_tokens=1500)
        assert result.total_tokens <= result.max_tokens


# ---------------------------------------------------------------------------
# Tests: Assembly - stale/low-confidence
# ---------------------------------------------------------------------------


class TestStaleLowConfidence:
    """Tests that stale items with low confidence are evicted early."""

    def test_stale_low_confidence_evicted(self, boundary):
        """Stale items with confidence < 0.5 should be evicted."""
        item = _make_item(
            priority=ContextPriority.OLD_LESSONS,
            stale=True,
            confidence=0.3,
            token_size=100,
        )
        result = boundary.assemble([item], max_tokens=1000)
        assert len(result.assembled_items) == 0
        evicted = [t for t in result.traces if t.action == "evicted"]
        assert len(evicted) == 1
        assert evicted[0].reason == "stale_and_low_confidence"

    def test_stale_high_confidence_included(self, boundary):
        """Stale items with high confidence should not be auto-evicted."""
        item = _make_item(
            priority=ContextPriority.OLD_LESSONS,
            stale=True,
            confidence=0.8,
            token_size=100,
        )
        result = boundary.assemble([item], max_tokens=1000)
        assert len(result.assembled_items) == 1

    def test_not_stale_low_confidence_included(self, boundary):
        """Non-stale items with low confidence should not be auto-evicted."""
        item = _make_item(
            priority=ContextPriority.OLD_LESSONS,
            stale=False,
            confidence=0.3,
            token_size=100,
        )
        result = boundary.assemble([item], max_tokens=1000)
        assert len(result.assembled_items) == 1

    def test_stale_confidence_boundary(self, boundary):
        """Confidence exactly 0.5 with stale should not be evicted (not < 0.5)."""
        item = _make_item(
            priority=ContextPriority.OLD_LESSONS,
            stale=True,
            confidence=0.5,
            token_size=100,
        )
        result = boundary.assemble([item], max_tokens=1000)
        assert len(result.assembled_items) == 1


# ---------------------------------------------------------------------------
# Tests: Assembly - tracing
# ---------------------------------------------------------------------------


class TestAssemblyTracing:
    """Tests that every include/exclude decision is traced."""

    def test_every_item_has_trace(self, boundary):
        """Every input item should produce exactly one trace."""
        items = [_make_item(priority=p, token_size=100) for p in ContextPriority]
        result = boundary.assemble(items, max_tokens=10000)
        assert len(result.traces) == len(items)

    def test_trace_actions_are_valid(self, boundary):
        """All trace actions should be in the expected set."""
        valid_actions = {"included", "evicted", "protected", "budget_exceeded"}
        items = [_make_item(token_size=100)]
        result = boundary.assemble(items, max_tokens=1000)
        for trace in result.traces:
            assert trace.action in valid_actions, f"Invalid action: {trace.action}"

    def test_trace_contains_item_id(self, boundary):
        """Each trace should contain an item_id with source:priority format."""
        item = _make_item(source="memory", priority=ContextPriority.OLD_LESSONS)
        result = boundary.assemble([item], max_tokens=1000)
        assert len(result.traces) == 1
        assert result.traces[0].item_id == "memory:old_lessons"

    def test_trace_contains_token_size(self, boundary):
        """Each trace should contain the item's token_size."""
        item = _make_item(token_size=42)
        result = boundary.assemble([item], max_tokens=1000)
        assert result.traces[0].token_size == 42

    def test_assembled_context_is_join_of_contents(self, boundary):
        """assembled_context should be items joined by double newlines."""
        items = [
            _make_item(content="AAA", token_size=100),
            _make_item(content="BBB", token_size=100),
        ]
        result = boundary.assemble(items, max_tokens=1000)
        assert result.assembled_context == "AAA\n\nBBB"

    def test_empty_items_produces_empty_result(self, boundary):
        """Empty input should produce empty result."""
        result = boundary.assemble([], max_tokens=1000)
        assert result.assembled_context == ""
        assert result.total_tokens == 0
        assert result.assembled_items == []
        assert result.traces == []


# ---------------------------------------------------------------------------
# Tests: Feature flag
# ---------------------------------------------------------------------------


class TestFeatureFlag:
    """Tests that the feature flag disables filtering safely."""

    def test_disabled_passthrough_includes_all(self, aria_config, monkeypatch):
        """When disabled, all items should pass through without filtering."""
        monkeypatch.setenv("CHISEAI_CONTEXT_ASSEMBLY_ENABLED", "false")
        b = ContextAssemblyBoundary(aria_config=aria_config)
        items = [
            _make_item(
                priority=ContextPriority.OLD_CONVERSATIONS,
                token_size=10000,
            ),
            _make_item(
                priority=ContextPriority.OLD_LESSONS,
                token_size=10000,
            ),
        ]
        # With flag disabled, even though budget is small, all items included
        result = b.assemble(items, max_tokens=100)
        assert len(result.assembled_items) == 2

    def test_disabled_passthrough_trace_reason(self, aria_config, monkeypatch):
        """When disabled, traces should indicate passthrough."""
        monkeypatch.setenv("CHISEAI_CONTEXT_ASSEMBLY_ENABLED", "false")
        b = ContextAssemblyBoundary(aria_config=aria_config)
        item = _make_item(token_size=100)
        result = b.assemble([item], max_tokens=1000)
        assert result.traces[0].reason == "feature_flag_disabled_passthrough"

    def test_disabled_empty_budget_allocation(self, aria_config, monkeypatch):
        """When disabled, budget_allocation should be empty dict."""
        monkeypatch.setenv("CHISEAI_CONTEXT_ASSEMBLY_ENABLED", "false")
        b = ContextAssemblyBoundary(aria_config=aria_config)
        result = b.assemble([], max_tokens=1000)
        assert result.budget_allocation == {}


# ---------------------------------------------------------------------------
# Tests: AssemblyResult structure
# ---------------------------------------------------------------------------


class TestAssemblyResult:
    """Tests for AssemblyResult dataclass."""

    def test_result_has_all_fields(self, boundary):
        """AssemblyResult should have all expected fields."""
        result = boundary.assemble([], max_tokens=1000)
        assert hasattr(result, "assembled_context")
        assert hasattr(result, "assembled_items")
        assert hasattr(result, "total_tokens")
        assert hasattr(result, "max_tokens")
        assert hasattr(result, "traces")
        assert hasattr(result, "budget_allocation")
        assert hasattr(result, "category_tokens")

    def test_category_tokens_populated(self, boundary):
        """category_tokens should track tokens per category."""
        items = [
            _make_item(
                priority=ContextPriority.CORE_PERSONALITY,
                token_size=200,
            ),
            _make_item(
                priority=ContextPriority.OLD_CONVERSATIONS,
                token_size=300,
            ),
        ]
        result = boundary.assemble(items, max_tokens=1000)
        assert result.category_tokens["core_personality"] == 200
        assert result.category_tokens["old_conversations"] == 300


# ---------------------------------------------------------------------------
# Tests: Real config integration
# ---------------------------------------------------------------------------


class TestRealConfigIntegration:
    """Integration tests using the real config files."""

    def test_boundary_loads_real_policy(self, aria_config):
        """Boundary should correctly load the real policy's allocation_order."""
        b = ContextAssemblyBoundary(aria_config=aria_config)
        allocation = b.calculate_budget_allocation(12000)
        # From the real config:
        # core_personality: 18%, personal_preferences: 14%, etc.
        assert allocation["core_personality"] == 2160  # 12000 * 0.18
        assert allocation["personal_preferences"] == 1680  # 12000 * 0.14
        assert allocation["project_rules_and_architecture"] == 2640  # 12000 * 0.22
        assert allocation["current_task_details"] == 2880  # 12000 * 0.24
        assert allocation["old_lessons"] == 1440  # 12000 * 0.12
        assert allocation["old_conversations"] == 1200  # 12000 * 0.10

    def test_boundary_loads_real_identity_protection(self, aria_config):
        """Boundary should protect identity items from real config."""
        b = ContextAssemblyBoundary(aria_config=aria_config)
        protected = b.get_protected_identity_items()
        # From identity-contract.yaml belief_policy.disallow_override_of
        assert "hardlined_soul_items" in protected
        assert "prd_objectives" in protected
        assert "approval_gated_rules" in protected

    def test_full_cycle_with_real_config(self, aria_config):
        """Full assembly cycle with real config should work correctly."""
        b = ContextAssemblyBoundary(aria_config=aria_config)
        items = [
            _make_item(
                content="Craig is the project owner",
                priority=ContextPriority.CORE_PERSONALITY,
                is_protected_identity=True,
                token_size=500,
            ),
            _make_item(
                content="Use evidence-first approach",
                priority=ContextPriority.PROJECT_RULES_AND_ARCHITECTURE,
                is_mandatory=True,
                token_size=300,
            ),
            _make_item(
                content="Current task: implement context assembly",
                priority=ContextPriority.CURRENT_TASK_DETAILS,
                is_mandatory=True,
                token_size=400,
            ),
            _make_item(
                content="Old lesson: always check ownership first",
                priority=ContextPriority.OLD_LESSONS,
                token_size=200,
            ),
            _make_item(
                content="Old conversation about something unrelated",
                priority=ContextPriority.OLD_CONVERSATIONS,
                token_size=600,
            ),
        ]
        result = b.assemble(items, max_tokens=1200)
        # Protected (500) + mandatory task (300) + mandatory current (400) = 1200
        # Old lessons (200) would push to 1400 - evicted
        # Old conversations (600) would push to 1800 - evicted
        assert result.total_tokens <= 1200
        contents = [i.content for i in result.assembled_items]
        assert "Craig is the project owner" in contents  # protected
        assert "Use evidence-first approach" in contents  # mandatory, fits
        # One of the two mandatory items will be evicted since 500+300+400=1200
        # but protected items bypass the budget check, so 500+300+400=1200 exactly

    def test_sample_trace_output(self, aria_config):
        """Produce sample trace output for verification."""
        b = ContextAssemblyBoundary(aria_config=aria_config)
        items = [
            _make_item(
                content="identity item",
                priority=ContextPriority.CORE_PERSONALITY,
                is_protected_identity=True,
                token_size=500,
                source="identity",
            ),
            _make_item(
                content="task detail",
                priority=ContextPriority.CURRENT_TASK_DETAILS,
                is_mandatory=True,
                token_size=400,
                source="task",
            ),
            _make_item(
                content="old lesson",
                priority=ContextPriority.OLD_LESSONS,
                token_size=300,
                source="lesson_store",
            ),
            _make_item(
                content="stale memory",
                priority=ContextPriority.OLD_CONVERSATIONS,
                stale=True,
                confidence=0.2,
                token_size=200,
                source="qdrant",
            ),
        ]
        result = b.assemble(items, max_tokens=1000)
        # Print trace for manual verification
        trace_lines = []
        for t in result.traces:
            trace_lines.append(
                f"  {t.action}: {t.item_id} - {t.reason} ({t.token_size} tokens)"
            )
        trace_output = "\n".join(trace_lines)
        # Verify structure
        assert any("protected" in t.reason for t in result.traces)
        assert any("mandatory" in t.reason for t in result.traces)
        assert any("stale_and_low_confidence" in t.reason for t in result.traces)
