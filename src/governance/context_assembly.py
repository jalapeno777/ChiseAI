"""Final Context Assembly Boundary for Aria.

Enforces priority-based context allocation per config/aria/context-budget-policy.yaml.
Marks protected identity items as non-evictable.
Provides tracing/debug output.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from src.config.aria_config import AriaConfig, get_aria_config

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

    action: str  # "included", "evicted", "protected", "budget_exceeded"
    item_id: str
    reason: str
    priority: str
    token_size: int


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
        """Check if the feature flag is enabled.

        Checks the environment variable CHISEAI_CONTEXT_ASSEMBLY_ENABLED.
        Defaults to enabled for safe rollout.
        """
        return (
            os.environ.get("CHISEAI_CONTEXT_ASSEMBLY_ENABLED", "true").lower()
            != "false"
        )

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
        )
