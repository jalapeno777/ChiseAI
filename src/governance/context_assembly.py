"""Final Context Assembly Boundary for Aria.

Enforces priority-based context allocation per config/aria/context-budget-policy.yaml.
Marks protected identity items as non-evictable.
Provides tracing/debug output.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from src.config.aria_config import AriaConfig, get_aria_config
from src.config.feature_flags import get_feature_flags

logger = logging.getLogger(__name__)

# Feature flag for enabling the new context assembly boundary
CONTEXT_ASSEMBLY_FEATURE_FLAG = (
    "chise:feature_flags:governance:context_assembly_enabled"
)


class ContextPriority(Enum):
    """Context priority levels matching allocation_order names."""

    CORE_PERSONALITY = "core_personality"
    PERSONAL_PREFERENCES = "personal_preferences"
    PROJECT_RULES_AND_ARCHITECTURE = "project_rules_and_architecture"
    CURRENT_TASK_DETAILS = "current_task_details"
    OLD_LESSONS = "old_lessons"
    OLD_CONVERSATIONS = "old_conversations"


# Map priority name -> index (lower = higher priority, evicted last)
PRIORITY_INDEX = {p.value: i for i, p in enumerate(ContextPriority)}


@dataclass
class ContextItem:
    """A single context item with priority and metadata."""

    content: str
    priority: ContextPriority
    priority_index: int = field(init=False)
    is_mandatory: bool = False
    is_protected_identity: bool = False
    confidence: float = 1.0
    stale: bool = False
    token_size: int = 0
    source: str = "unknown"

    def __post_init__(self) -> None:
        self.priority_index = PRIORITY_INDEX.get(self.priority.value, 999)

    def can_evict(self) -> bool:
        """Returns True if this item can be evicted under budget pressure."""
        if self.is_mandatory:
            return False
        return not self.is_protected_identity


@dataclass
class AssemblyTrace:
    """Trace record for debugging context assembly decisions."""

    action: str  # "included", "evicted", "protected", "budget_exceeded", "conflict_unresolved"
    item_id: str
    reason: str
    priority: str
    token_size: int


@dataclass
class UnresolvedConflict:
    """Records when strongest evidence cannot safely resolve a conflict."""

    item_ids: list[str]  # Conflicting item identifiers
    evidence_strengths: list[float]  # Respective evidence strengths
    reason: str  # Why unresolved: "insufficient_evidence", "contradictory_signals", "budget_exceeded_all_options"
    suggested_resolution: str  # "escalate_to_craig", "gather_more_evidence"


@dataclass
class AssemblyResult:
    """Result of context assembly."""

    assembled_context: str
    assembled_items: list[ContextItem]
    total_tokens: int
    max_tokens: int
    traces: list[AssemblyTrace]
    budget_allocation: dict[str, int]
    category_tokens: dict[str, int]
    unresolved_conflicts: list[UnresolvedConflict] = field(default_factory=list)


class ContextAssemblyBoundary:
    """Final boundary for context assembly with priority-based eviction.

    This class enforces the allocation_order from context-budget-policy.yaml
    and marks protected identity items as non-evictable.

    Usage:
        boundary = ContextAssemblyBoundary()
        result = boundary.assemble(raw_items, max_tokens=12000)
        print(result.assembled_context)
        for trace in result.traces:
            print(f"{trace.action}: {trace.item_id} - {trace.reason}")
    """

    def __init__(
        self,
        aria_config: AriaConfig | None = None,
        feature_flag_key: str = CONTEXT_ASSEMBLY_FEATURE_FLAG,
    ):
        self._config = aria_config or get_aria_config()
        self._policy = self._config.context_budget_policy
        self._identity = self._config.identity_contract
        self._feature_flag_key = feature_flag_key
        self._enabled = self._is_enabled()

        # Build protected identity items set from identity-contract.yaml
        self._protected_items: set[str] = set(self._identity.approval_gated_fields)

        # Build priority-to-reserve mapping
        self._priority_reserve: dict[str, dict[str, Any]] = {}
        for entry in self._policy.allocation_order:
            name = entry.get("name", "")
            pct = entry.get("reserve_pct", 0)
            mandatory = entry.get("mandatory", False)
            self._priority_reserve[name] = {"pct": pct, "mandatory": mandatory}

    def _is_enabled(self) -> bool:
        """Check if the feature flag is enabled via Redis.

        Uses the get_feature_flags().get_redis_value() pattern.
        Defaults to enabled for safe rollout.
        """
        try:
            flags = get_feature_flags()
            return flags.get_redis_value(self._feature_flag_key, default=True)
        except Exception as e:
            logger.warning(f"Error checking feature flag {self._feature_flag_key}: {e}")
            return True  # Default to enabled for safety

    @property
    def enabled(self) -> bool:
        """Whether the assembly boundary is active."""
        return self._enabled

    def get_protected_identity_items(self) -> set[str]:
        """Return the set of protected identity item names."""
        return self._protected_items.copy()

    def calculate_budget_allocation(self, max_tokens: int) -> dict[str, int]:
        """Calculate token budget per priority category.

        Args:
            max_tokens: Total available token budget

        Returns:
            Dict mapping priority name to max tokens for that category
        """
        allocation: dict[str, int] = {}
        for entry in self._policy.allocation_order:
            name = entry.get("name", "")
            pct = entry.get("reserve_pct", 0)
            allocation[name] = int(max_tokens * pct / 100)
        return allocation

    def _detect_conflicts(
        self,
        items: list[ContextItem],
        max_tokens: int,
    ) -> list[UnresolvedConflict]:
        """Detect conflicts between items that cannot be resolved.

        Conflicts are detected when:
        1. Multiple items of same priority have similar confidence (within 0.1)
           AND contradictory signals (different sources)
        2. Budget is too tight to fit even the highest-confidence item
           alongside mandatory/protected items

        Args:
            items: Items to check for conflicts
            max_tokens: Available budget

        Returns:
            List of UnresolvedConflict objects
        """
        conflicts: list[UnresolvedConflict] = []
        sorted_items = sorted(items, key=lambda x: (x.priority_index, -x.confidence))

        # Calculate mandatory/protected tokens upfront
        reserved_tokens = sum(
            item.token_size
            for item in items
            if item.is_protected_identity or item.is_mandatory
        )
        available_for_optional = max_tokens - reserved_tokens

        # Group items by priority
        by_priority: dict[ContextPriority, list[ContextItem]] = {}
        for item in sorted_items:
            if not item.is_protected_identity and not item.is_mandatory:
                by_priority.setdefault(item.priority, []).append(item)

        for priority, priority_items in by_priority.items():
            if len(priority_items) < 2:
                continue

            # Check for similar confidence items (within 0.1)
            for i in range(len(priority_items)):
                for j in range(i + 1, len(priority_items)):
                    item_a = priority_items[i]
                    item_b = priority_items[j]
                    confidence_diff = abs(item_a.confidence - item_b.confidence)

                    # Similar confidence threshold: 0.1
                    if confidence_diff <= 0.1:
                        total_tokens_needed = (
                            item_a.token_size
                            + item_b.token_size
                            + sum(
                                x.token_size
                                for x in priority_items
                                if x is not item_a and x is not item_b
                            )
                        )

                        # If both can't fit and confidences are too close to decide
                        if total_tokens_needed > available_for_optional:
                            # Check if evidence is too close to call a winner
                            if confidence_diff <= 0.1:
                                conflict = UnresolvedConflict(
                                    item_ids=[
                                        f"{item_a.source}:{item_a.priority.value}",
                                        f"{item_b.source}:{item_b.priority.value}",
                                    ],
                                    evidence_strengths=[
                                        item_a.confidence,
                                        item_b.confidence,
                                    ],
                                    reason="contradictory_signals",
                                    suggested_resolution="escalate_to_craig",
                                )
                                conflicts.append(conflict)
                                break
                if (
                    conflicts
                    and conflicts[-1].item_ids[0]
                    == f"{priority_items[i].source}:{priority_items[i].priority.value}"
                ):
                    break

        return conflicts

    def assemble(
        self,
        items: list[ContextItem],
        max_tokens: int = 12000,
    ) -> AssemblyResult:
        """Assemble context items respecting priority and budget.

        Processing order:
        1. Sort all items by priority_index (lower = higher priority).
        2. Protected identity items are always included (traced as "protected").
        3. Mandatory items are included if budget allows (traced as "mandatory").
        4. Optional stale items with low confidence are evicted first.
        5. Remaining optional items are included until budget is exhausted.
        6. Every decision produces an AssemblyTrace for debugging.

        Args:
            items: List of ContextItem to assemble
            max_tokens: Maximum tokens available

        Returns:
            AssemblyResult with assembled context and traces
        """
        if not self._enabled:
            # Feature flag disabled: pass through all items without filtering
            assembled_context = "\n\n".join(item.content for item in items)
            return AssemblyResult(
                assembled_context=assembled_context,
                assembled_items=list(items),
                total_tokens=sum(i.token_size for i in items),
                max_tokens=max_tokens,
                traces=[
                    AssemblyTrace(
                        action="included",
                        item_id=f"{i.source}:{i.priority.value}",
                        reason="feature_flag_disabled_passthrough",
                        priority=i.priority.value,
                        token_size=i.token_size,
                    )
                    for i in items
                ],
                budget_allocation={},
                category_tokens={},
            )

        traces: list[AssemblyTrace] = []
        assembled: list[ContextItem] = []
        total_tokens = 0

        # Sort items by priority (lower index = higher priority)
        sorted_items = sorted(items, key=lambda x: x.priority_index)

        # Detect conflicts before assembly
        unresolved_conflicts = self._detect_conflicts(sorted_items, max_tokens)

        # Build set of conflicting item IDs for tracing
        conflicting_ids: set[str] = set()
        for conflict in unresolved_conflicts:
            conflicting_ids.update(conflict.item_ids)

        # Calculate budget per category
        budget_allocation = self.calculate_budget_allocation(max_tokens)
        category_tokens: dict[str, int] = {}

        for item in sorted_items:
            item_id = f"{item.source}:{item.priority.value}"

            # Check if item is protected identity - NEVER evict
            if item.is_protected_identity:
                traces.append(
                    AssemblyTrace(
                        action="protected",
                        item_id=item_id,
                        reason="protected_identity_item",
                        priority=item.priority.value,
                        token_size=item.token_size,
                    )
                )
                assembled.append(item)
                total_tokens += item.token_size
                category_tokens[item.priority.value] = (
                    category_tokens.get(item.priority.value, 0) + item.token_size
                )
                continue

            # Check if mandatory
            if item.is_mandatory:
                if total_tokens + item.token_size <= max_tokens:
                    traces.append(
                        AssemblyTrace(
                            action="included",
                            item_id=item_id,
                            reason="mandatory",
                            priority=item.priority.value,
                            token_size=item.token_size,
                        )
                    )
                    assembled.append(item)
                    total_tokens += item.token_size
                    category_tokens[item.priority.value] = (
                        category_tokens.get(item.priority.value, 0) + item.token_size
                    )
                else:
                    traces.append(
                        AssemblyTrace(
                            action="budget_exceeded",
                            item_id=item_id,
                            reason="mandatory_item_exceeds_budget",
                            priority=item.priority.value,
                            token_size=item.token_size,
                        )
                    )
                continue

            # Check stale/low-confidence items - evict before budget check
            if item.stale and item.confidence < 0.5:
                traces.append(
                    AssemblyTrace(
                        action="evicted",
                        item_id=item_id,
                        reason="stale_and_low_confidence",
                        priority=item.priority.value,
                        token_size=item.token_size,
                    )
                )
                continue

            # Check if item is part of an unresolved conflict
            if item_id in conflicting_ids:
                # Find the specific conflict reason
                conflict_reason = "contradictory_signals"
                for conflict in unresolved_conflicts:
                    if item_id in conflict.item_ids:
                        conflict_reason = conflict.reason
                        break
                traces.append(
                    AssemblyTrace(
                        action="conflict_unresolved",
                        item_id=item_id,
                        reason=f"unresolved_conflict_{conflict_reason}",
                        priority=item.priority.value,
                        token_size=item.token_size,
                    )
                )
                # Don't add to assembled - conflict prevents resolution
                continue

            # Check if within total budget
            if total_tokens + item.token_size <= max_tokens:
                traces.append(
                    AssemblyTrace(
                        action="included",
                        item_id=item_id,
                        reason="within_budget",
                        priority=item.priority.value,
                        token_size=item.token_size,
                    )
                )
                assembled.append(item)
                total_tokens += item.token_size
                category_used = category_tokens.get(item.priority.value, 0)
                category_tokens[item.priority.value] = category_used + item.token_size
            else:
                traces.append(
                    AssemblyTrace(
                        action="evicted",
                        item_id=item_id,
                        reason="budget_exceeded",
                        priority=item.priority.value,
                        token_size=item.token_size,
                    )
                )

        # Build assembled context string
        assembled_context = "\n\n".join(item.content for item in assembled)

        return AssemblyResult(
            assembled_context=assembled_context,
            assembled_items=assembled,
            total_tokens=total_tokens,
            max_tokens=max_tokens,
            traces=traces,
            budget_allocation=budget_allocation,
            category_tokens=category_tokens,
            unresolved_conflicts=unresolved_conflicts,
        )
