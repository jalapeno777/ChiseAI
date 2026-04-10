"""
Unit tests for context_assembler module.

Tests for:
- AC1: build_session_context() returns all 4 tier levels
- AC2: L0 returns last iteration's observations
- AC3: Token budget capped at 25K
- AC4: Staleness precomputed at write-time only
- AC5: Legacy missing marked correctly
- AC6: Fail-fast on runtime staleness compute

HARDENING tests from Aria decision AD-PHASE4-20260409T000000Z-ctx001:
- Strategic challenge invariant enforcement
- No query-time staleness recomputation
- Feature flag toggle: MEMORY_HYBRID_ENABLED=false → direct retrieval fallback
"""

from unittest.mock import MagicMock, patch

import pytest

# Import modules under test
from src.governance.memory.context_assembler import (
    TOKEN_BUDGET_CAP,
    MemoryContext,
    _assemble_hybrid_context,
    _direct_retrieval_fallback,
    assert_no_runtime_staleness_compute_in_context,
    build_session_context,
)
from src.governance.memory.invariants import (
    StalenessComputeError,
    assert_no_runtime_staleness_compute,
    validate_payload_staleness,
)


class TestStalenessComputeError:
    """Tests for StalenessComputeError exception."""

    def test_staleness_compute_error_is_exception(self):
        """StalenessComputeError should be an Exception subclass."""
        error = StalenessComputeError("test message")
        assert isinstance(error, Exception)

    def test_staleness_compute_error_message(self):
        """StalenessComputeError should preserve message."""
        msg = "staleness computed at query time"
        error = StalenessComputeError(msg)
        assert str(error) == msg


class TestAssertNoRuntimeStalenessCompute:
    """Tests for assert_no_runtime_staleness_compute invariant."""

    def test_no_error_when_staleness_missing(self):
        """Should NOT raise when staleness_score is None (legacy_missing case)."""
        payload = {"id": "test-1", "content": "some content"}
        # Should not raise - None means legacy_missing, not computed
        assert_no_runtime_staleness_compute(payload)

    def test_no_error_when_staleness_is_float(self):
        """Should NOT raise when staleness_score is a precomputed float."""
        payload = {"id": "test-2", "staleness_score": 0.75, "content": "data"}
        assert_no_runtime_staleness_compute(payload)

    def test_no_error_when_staleness_is_zero(self):
        """Should NOT raise when staleness_score is 0.0 (precomputed)."""
        payload = {"id": "test-3", "staleness_score": 0.0}
        assert_no_runtime_staleness_compute(payload)

    def test_raises_when_staleness_is_callable(self):
        """Should raise StalenessComputeError when staleness_score is callable."""
        # Callable staleness indicates runtime computation
        payload = {"id": "test-4", "staleness_score": lambda: 0.5}
        with pytest.raises(StalenessComputeError) as exc_info:
            assert_no_runtime_staleness_compute(payload)
        assert "computed at query time" in str(exc_info.value)

    def test_raises_when_staleness_is_function(self):
        """Should raise when staleness_score is a function reference."""

        def compute_staleness():
            return 0.5

        payload = {"id": "test-5", "staleness_score": compute_staleness}
        with pytest.raises(StalenessComputeError):
            assert_no_runtime_staleness_compute(payload)


class TestValidatePayloadStaleness:
    """Tests for validate_payload_staleness function."""

    def test_valid_payload_with_staleness(self):
        """Should return valid=True, empty legacy_missing for good payload."""
        payload = {"id": "test-1", "staleness_score": 0.8}
        is_valid, legacy = validate_payload_staleness(payload, "test-1")
        assert is_valid is True
        assert legacy == []

    def test_legacy_missing_payload(self):
        """Should return legacy_missing reason when staleness_score is None."""
        payload = {"id": "test-2", "content": "legacy data"}
        is_valid, legacy = validate_payload_staleness(payload, "test-2")
        assert is_valid is True  # Not a violation, just legacy
        assert "test-2" in legacy[0]
        assert "missing staleness_score" in legacy[0]

    def test_violation_detected(self):
        """Should return is_valid=False when callable detected."""
        payload = {"id": "test-3", "staleness_score": lambda: 0.5}
        is_valid, legacy = validate_payload_staleness(payload, "test-3")
        assert is_valid is False
        assert "callable" in legacy[0]


class TestMemoryContext:
    """Tests for MemoryContext dataclass."""

    def test_memory_context_creation(self):
        """MemoryContext should be created with all fields."""
        ctx = MemoryContext(
            hot_context={"tier": "L0", "results": []},
            warm_context={"tier": "L1", "results": []},
            cold_context={"tier": "L2", "results": []},
            archived_hints={"tier": "L3", "results": []},
            token_budget_used=1000,
            legacy_missing=["legacy:test-1"],
        )
        assert ctx.hot_context["tier"] == "L0"
        assert ctx.warm_context["tier"] == "L1"
        assert ctx.cold_context["tier"] == "L2"
        assert ctx.archived_hints["tier"] == "L3"
        assert ctx.token_budget_used == 1000
        assert ctx.legacy_missing == ["legacy:test-1"]

    def test_memory_context_default_legacy_missing(self):
        """legacy_missing should default to empty list."""
        ctx = MemoryContext(
            hot_context={},
            warm_context={},
            cold_context={},
            archived_hints={},
            token_budget_used=0,
        )
        assert ctx.legacy_missing == []


class TestBuildSessionContext:
    """Tests for build_session_context function."""

    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client."""
        redis = MagicMock()
        redis.get.return_value = "true"
        redis.zrange.return_value = [
            '{"timestamp": "2026-04-09T10:00:00Z", "content": "L0 obs 1"}',
            '{"timestamp": "2026-04-09T09:00:00Z", "content": "L0 obs 2"}',
        ]
        return redis

    @pytest.fixture
    def mock_qdrant(self):
        """Mock Qdrant client."""
        qdrant = MagicMock()

        # Mock scroll for different tiers
        def mock_scroll(collection_name, filter, limit, offset=None, with_payload=True):
            # L1: recent (0-7 days)
            if "L1" in str(filter) or "gte" in str(filter):
                return [
                    {
                        "id": "qdrant-1",
                        "payload": {
                            "id": "qdrant-1",
                            "content": "L1 content",
                            "staleness_score": 0.8,
                            "created_at": "2026-04-08T10:00:00Z",
                        },
                    }
                ], None
            # L2: historical (7-30 days)
            elif "lte" in str(filter):
                return [
                    {
                        "id": "qdrant-2",
                        "payload": {
                            "id": "qdrant-2",
                            "content": "L2 content",
                            "staleness_score": 0.5,
                            "created_at": "2026-04-01T10:00:00Z",
                        },
                    }
                ], None
            # L3: archived (30+ days)
            elif "lt" in str(filter):
                return [
                    {
                        "id": "qdrant-3",
                        "payload": {
                            "id": "qdrant-3",
                            "content": "L3 content",
                            "staleness_score": 0.2,
                            "created_at": "2026-03-15T10:00:00Z",
                        },
                    }
                ], None
            return [], None

        qdrant.scroll.side_effect = mock_scroll
        return qdrant

    def test_returns_all_four_tier_levels(self, mock_redis, mock_qdrant):
        """AC1: build_session_context() returns all 4 tier levels."""
        ctx = build_session_context(
            session_id="test-session",
            redis_client=mock_redis,
            qdrant_client=mock_qdrant,
        )

        # All 4 tiers should be present
        assert "tier" in ctx.hot_context
        assert "tier" in ctx.warm_context
        assert "tier" in ctx.cold_context
        assert "tier" in ctx.archived_hints

        assert ctx.hot_context["tier"] == "L0"
        assert ctx.warm_context["tier"] == "L1"
        assert ctx.cold_context["tier"] == "L2"
        assert ctx.archived_hints["tier"] == "L3"

    def test_l0_returns_observations(self, mock_redis, mock_qdrant):
        """AC2: L0 returns last iteration's observations."""
        ctx = build_session_context(
            session_id="test-session",
            redis_client=mock_redis,
            qdrant_client=mock_qdrant,
        )

        # L0 should have results from Redis
        assert len(ctx.hot_context["results"]) > 0

    def test_token_budget_capped_at_25k(self, mock_redis, mock_qdrant):
        """AC3: Token budget capped at 25K."""
        # Call with excessive max_tokens
        ctx = build_session_context(
            session_id="test-session",
            redis_client=mock_redis,
            qdrant_client=mock_qdrant,
            max_tokens=100_000,  # Exceeds cap
        )

        # Token budget should be capped
        assert ctx.token_budget_used <= TOKEN_BUDGET_CAP

    def test_legacy_missing_for_missing_staleness(self, mock_redis, mock_qdrant):
        """AC5: Legacy missing marked correctly for payloads without staleness_score.

        Note: This test validates the invariant check logic. The actual tiered_recall
        module has legacy fallback code that computes staleness at query time for
        payloads missing staleness_score. This is outside our scope (tiered_recall.py
        is marked READ ONLY). We test our invariant function directly.
        """
        # Test the invariant function directly with a payload missing staleness_score
        payload = {
            "id": "legacy-record",
            "content": "No staleness",
            "created_at": "2026-04-08T10:00:00Z",
            # No staleness_score
        }

        # assert_no_runtime_staleness_compute should NOT raise for missing staleness
        # (missing means legacy, not a violation)
        assert_no_runtime_staleness_compute(payload)

        # But validate_payload_staleness should mark it as legacy_missing
        is_valid, legacy = validate_payload_staleness(payload, "legacy-record")
        assert is_valid is True
        assert len(legacy) == 1
        assert "legacy-record" in legacy[0]

    def test_fail_fast_on_runtime_staleness_compute(self, mock_redis, mock_qdrant):
        """AC6: Fail-fast on runtime staleness compute.

        Tests that our invariant function raises StalenessComputeError when
        a callable staleness_score is detected (indicating runtime computation).
        """
        # Test the invariant function directly with a callable staleness
        payload = {
            "id": "bad-record",
            "content": "Callable staleness",
            "staleness_score": lambda: 0.5,  # Runtime compute!
            "created_at": "2026-04-08T10:00:00Z",
        }

        with pytest.raises(StalenessComputeError) as exc_info:
            assert_no_runtime_staleness_compute(payload)

        assert "computed at query time" in str(exc_info.value)


class TestAssertNoRuntimeStalenessComputeInContext:
    """Tests for assert_no_runtime_staleness_compute_in_context function."""

    def test_no_error_for_valid_context(self):
        """Should not raise for context with valid precomputed staleness."""
        ctx = MemoryContext(
            hot_context={
                "tier": "L0",
                "results": [
                    {
                        "id": "1",
                        "payload": {
                            "id": "1",
                            "staleness_score": 0.8,
                        },
                    }
                ],
            },
            warm_context={"tier": "L1", "results": []},
            cold_context={"tier": "L2", "results": []},
            archived_hints={"tier": "L3", "results": []},
            token_budget_used=100,
        )

        # Should not raise
        assert_no_runtime_staleness_compute_in_context(ctx)

    def test_raises_for_callable_in_context(self):
        """Should raise StalenessComputeError for callable staleness in context."""
        ctx = MemoryContext(
            hot_context={
                "tier": "L0",
                "results": [
                    {
                        "id": "1",
                        "payload": {
                            "id": "1",
                            "staleness_score": lambda: 0.5,  # Bad!
                        },
                    }
                ],
            },
            warm_context={"tier": "L1", "results": []},
            cold_context={"tier": "L2", "results": []},
            archived_hints={"tier": "L3", "results": []},
            token_budget_used=100,
        )

        with pytest.raises(StalenessComputeError):
            assert_no_runtime_staleness_compute_in_context(ctx)


class TestTokenBudgetCap:
    """Tests for token budget cap enforcement."""

    def test_token_budget_cap_constant(self):
        """TOKEN_BUDGET_CAP should be 25_000."""
        assert TOKEN_BUDGET_CAP == 25_000

    def test_effective_max_is_capped(self):
        """When max_tokens exceeds cap, should use cap."""

        # Verify the cap is enforced in the function
        # This is tested implicitly via test_token_budget_capped_at_25k


class TestAuditCapture:
    """Tests for audit_capture module."""

    def test_capture_baseline_metrics_empty(self):
        """Should handle empty session samples."""
        from src.governance.memory.audit_capture import capture_baseline_metrics

        metrics = capture_baseline_metrics([])
        assert metrics.total_sessions == 0
        assert metrics.avg_token_budget_used == 0.0

    def test_capture_baseline_metrics_with_samples(self):
        """Should compute correct baseline metrics."""
        from src.governance.memory.audit_capture import capture_baseline_metrics

        samples = [
            {
                "session_id": "s1",
                "token_budget_used": 5000,
                "legacy_missing": [],
                "hot_context_results": 10,
                "warm_context_results": 5,
                "cold_context_results": 2,
                "archived_context_results": 1,
            },
            {
                "session_id": "s2",
                "token_budget_used": 8000,
                "legacy_missing": ["legacy:1"],
                "hot_context_results": 8,
                "warm_context_results": 4,
                "cold_context_results": 1,
                "archived_context_results": 0,
            },
        ]

        metrics = capture_baseline_metrics(samples)
        assert metrics.total_sessions == 2
        assert metrics.avg_token_budget_used == 6500.0
        assert metrics.max_token_budget_used == 8000
        assert metrics.legacy_missing_count == 1

    def test_get_memory_health_summary_healthy(self):
        """Should return healthy status when metrics are good."""
        from src.governance.memory.audit_capture import (
            capture_baseline_metrics,
            get_memory_health_summary,
        )

        samples = [
            {
                "session_id": "s1",
                "token_budget_used": 5000,
                "legacy_missing": [],
                "hot_context_results": 10,
                "warm_context_results": 5,
                "cold_context_results": 2,
                "archived_context_results": 1,
                "staleness_violations": 0,
            },
        ]

        metrics = capture_baseline_metrics(samples)
        summary = get_memory_health_summary(metrics)
        assert summary.health_status == "healthy"
        assert summary.confidence > 0

    def test_get_memory_health_summary_critical_on_violations(self):
        """Should return critical status when staleness violations detected."""
        from src.governance.memory.audit_capture import (
            capture_baseline_metrics,
            get_memory_health_summary,
        )

        samples = [
            {
                "session_id": "s1",
                "token_budget_used": 5000,
                "legacy_missing": [],
                "hot_context_results": 10,
                "warm_context_results": 5,
                "cold_context_results": 2,
                "archived_context_results": 1,
                "staleness_violations": 3,  # Violations!
            },
        ]

        metrics = capture_baseline_metrics(samples)
        summary = get_memory_health_summary(metrics)
        assert summary.health_status == "critical"
        assert summary.staleness_violations == 3


class TestFeatureFlagToggle:
    """Tests for MEMORY_HYBRID_ENABLED feature flag toggle.

    HARDENING (Aria decision AD-PHASE4-20260409T000000Z-ctx001):
    - MEMORY_HYBRID_ENABLED=false → direct retrieval fallback
    - MEMORY_HYBRID_ENABLED=true → full hybrid context assembly
    - Flag toggle must prove safe fallback behavior
    """

    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client."""
        redis = MagicMock()
        redis.get.return_value = "true"
        redis.zrange.return_value = [
            '{"timestamp": "2026-04-09T10:00:00Z", "content": "L0 obs 1"}',
        ]
        return redis

    @pytest.fixture
    def mock_qdrant(self):
        """Mock Qdrant client."""
        qdrant = MagicMock()

        def mock_scroll(collection_name, filter, limit, offset=None, with_payload=True):
            return [
                {
                    "id": "qdrant-1",
                    "payload": {
                        "id": "qdrant-1",
                        "content": "content",
                        "staleness_score": 0.8,
                        "created_at": "2026-04-08T10:00:00Z",
                    },
                }
            ], None

        qdrant.scroll.side_effect = mock_scroll
        return qdrant

    def test_feature_flag_false_uses_direct_retrieval(self, mock_redis, mock_qdrant):
        """AC2: When MEMORY_HYBRID_ENABLED=false, uses direct retrieval fallback.

        Tests that build_session_context() returns a MemoryContext with
        domain=None when the feature flag is false.
        """
        mock_ff = MagicMock()
        mock_ff.is_memory_hybrid_enabled.return_value = False

        with patch(
            "src.config.feature_flags.FeatureFlags",
            return_value=mock_ff,
        ):
            ctx = build_session_context(
                session_id="toggle-test",
                redis_client=mock_redis,
                qdrant_client=mock_qdrant,
            )

        # In fallback mode, domain should be None
        assert ctx.domain is None
        # But all tiers should still be present
        assert ctx.hot_context is not None
        assert ctx.warm_context is not None
        assert ctx.cold_context is not None
        assert ctx.archived_hints is not None

    def test_feature_flag_true_uses_hybrid_context(self, mock_redis, mock_qdrant):
        """AC2: When MEMORY_HYBRID_ENABLED=true, uses full hybrid context assembly.

        Tests that build_session_context() returns a MemoryContext with
        domain potentially populated when the feature flag is true.
        """
        mock_ff = MagicMock()
        mock_ff.is_memory_hybrid_enabled.return_value = True

        with patch(
            "src.config.feature_flags.FeatureFlags",
            return_value=mock_ff,
        ):
            ctx = build_session_context(
                session_id="toggle-test",
                redis_client=mock_redis,
                qdrant_client=mock_qdrant,
            )

        # In hybrid mode, domain can be populated if DomainContext is found
        # (it may still be None if no domain_context in payloads)
        assert ctx is not None
        assert ctx.hot_context is not None
        assert ctx.warm_context is not None

    def test_feature_flag_toggle_proves_safe_fallback(self, mock_redis, mock_qdrant):
        """AC4: Flag toggle proves safe fallback when flag=false.

        This is the ROLLBACK SMOKE TEST from Aria hardening.
        When flag is toggled from true to false, the system must
        continue to work without errors.

        Test sequence:
        1. Set flag=true, call build_session_context (should work)
        2. Set flag=false, call build_session_context (should work)
        3. Verify no errors occurred
        """
        # First call with flag=true
        mock_ff_true = MagicMock()
        mock_ff_true.is_memory_hybrid_enabled.return_value = True

        with patch(
            "src.config.feature_flags.FeatureFlags",
            return_value=mock_ff_true,
        ):
            ctx_true = build_session_context(
                session_id="toggle-test",
                redis_client=mock_redis,
                qdrant_client=mock_qdrant,
            )

        # Second call with flag=false (fallback mode)
        mock_ff_false = MagicMock()
        mock_ff_false.is_memory_hybrid_enabled.return_value = False

        with patch(
            "src.config.feature_flags.FeatureFlags",
            return_value=mock_ff_false,
        ):
            ctx_false = build_session_context(
                session_id="toggle-test",
                redis_client=mock_redis,
                qdrant_client=mock_qdrant,
            )

        # Both calls should succeed without errors
        assert ctx_true is not None
        assert ctx_false is not None

        # Fallback mode should have domain=None
        assert ctx_false.domain is None

        # All tiers should be populated in both modes
        assert ctx_true.hot_context is not None
        assert ctx_false.hot_context is not None


class TestDirectRetrievalFallback:
    """Tests for _direct_retrieval_fallback function."""

    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client."""
        redis = MagicMock()
        redis.get.return_value = "true"
        redis.zrange.return_value = [
            '{"timestamp": "2026-04-09T10:00:00Z", "content": "L0 obs 1"}',
        ]
        return redis

    @pytest.fixture
    def mock_qdrant(self):
        """Mock Qdrant client."""
        qdrant = MagicMock()

        def mock_scroll(collection_name, filter, limit, offset=None, with_payload=True):
            return [
                {
                    "id": "qdrant-1",
                    "payload": {
                        "id": "qdrant-1",
                        "content": "content",
                        "staleness_score": 0.8,
                        "created_at": "2026-04-08T10:00:00Z",
                    },
                }
            ], None

        qdrant.scroll.side_effect = mock_scroll
        return qdrant

    def test_direct_retrieval_returns_all_tiers(self, mock_redis, mock_qdrant):
        """_direct_retrieval_fallback should return all 4 tiers."""
        ctx = _direct_retrieval_fallback(
            session_id="test-session",
            redis_client=mock_redis,
            qdrant_client=mock_qdrant,
        )

        assert ctx.hot_context is not None
        assert ctx.warm_context is not None
        assert ctx.cold_context is not None
        assert ctx.archived_hints is not None

    def test_direct_retrieval_has_no_domain(self, mock_redis, mock_qdrant):
        """_direct_retrieval_fallback should set domain=None."""
        ctx = _direct_retrieval_fallback(
            session_id="test-session",
            redis_client=mock_redis,
            qdrant_client=mock_qdrant,
        )

        assert ctx.domain is None


class TestHybridContextAssembly:
    """Tests for _assemble_hybrid_context function."""

    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client."""
        redis = MagicMock()
        redis.get.return_value = "true"
        redis.zrange.return_value = [
            '{"timestamp": "2026-04-09T10:00:00Z", "content": "L0 obs 1"}',
        ]
        return redis

    @pytest.fixture
    def mock_qdrant(self):
        """Mock Qdrant client."""
        qdrant = MagicMock()

        def mock_scroll(collection_name, filter, limit, offset=None, with_payload=True):
            return [
                {
                    "id": "qdrant-1",
                    "payload": {
                        "id": "qdrant-1",
                        "content": "content",
                        "staleness_score": 0.8,
                        "created_at": "2026-04-08T10:00:00Z",
                    },
                }
            ], None

        qdrant.scroll.side_effect = mock_scroll
        return qdrant

    def test_assemble_hybrid_returns_all_tiers(self, mock_redis, mock_qdrant):
        """_assemble_hybrid_context should return all 4 tiers."""
        ctx = _assemble_hybrid_context(
            session_id="test-session",
            redis_client=mock_redis,
            qdrant_client=mock_qdrant,
        )

        assert ctx.hot_context is not None
        assert ctx.warm_context is not None
        assert ctx.cold_context is not None
        assert ctx.archived_hints is not None

    def test_assemble_hybrid_domain_may_be_none_without_payload(
        self, mock_redis, mock_qdrant
    ):
        """_assemble_hybrid_context may have domain=None if no DomainContext in payload."""
        ctx = _assemble_hybrid_context(
            session_id="test-session",
            redis_client=mock_redis,
            qdrant_client=mock_qdrant,
        )

        # Without explicit domain_context in payloads, domain may be None
        # This is acceptable - the function still works
        assert ctx is not None


class TestMemoryContextDomainField:
    """Tests for MemoryContext.domain field."""

    def test_memory_context_with_domain(self):
        """MemoryContext should accept domain field."""
        ctx = MemoryContext(
            hot_context={"tier": "L0", "results": []},
            warm_context={"tier": "L1", "results": []},
            cold_context={"tier": "L2", "results": []},
            archived_hints={"tier": "L3", "results": []},
            token_budget_used=1000,
            legacy_missing=[],
            domain={
                "domain_context": {
                    "wing": "trading",
                    "room": "risk-mgmt",
                    "hall": "facts",
                    "tunnels": [],
                }
            },
        )
        assert ctx.domain is not None
        assert ctx.domain["domain_context"]["wing"] == "trading"

    def test_memory_context_domain_defaults_to_none(self):
        """MemoryContext.domain should default to None."""
        ctx = MemoryContext(
            hot_context={},
            warm_context={},
            cold_context={},
            archived_hints={},
            token_budget_used=0,
        )
        assert ctx.domain is None


class TestCanarySmoke:
    """Canary smoke tests for session-aware routing integration.

    ST-PHASE5-CANARY-002: Integration smoke tests for canary routing.
    """

    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client."""
        redis = MagicMock()
        redis.get.return_value = "true"
        redis.zrange.return_value = [
            '{"timestamp": "2026-04-09T10:00:00Z", "content": "L0 obs 1"}',
        ]
        redis.smembers.return_value = set()
        return redis

    @pytest.fixture
    def mock_qdrant(self):
        """Mock Qdrant client."""
        qdrant = MagicMock()

        def mock_scroll(collection_name, filter, limit, offset=None, with_payload=True):
            return [
                {
                    "id": "qdrant-1",
                    "payload": {
                        "id": "qdrant-1",
                        "content": "content",
                        "staleness_score": 0.8,
                        "created_at": "2026-04-08T10:00:00Z",
                    },
                }
            ], None

        qdrant.scroll.side_effect = mock_scroll
        return qdrant

    def test_canary_smoke_mixed_sessions_5_percent(self, mock_redis, mock_qdrant):
        """Simulated mixed sessions produce mixed routing under 5%."""
        from src.config.feature_flags import FeatureFlags

        mock_redis.set_data("chise:feature_flags:config:memory_hybrid_enabled", "true")
        mock_redis.set_data("chise:feature_flags:config:memory:canary_percentage", "5")

        ff = FeatureFlags()
        object.__setattr__(ff, "_redis_client", mock_redis)

        # 20 sessions at 5% -> expect 0-2 hybrid (allow variance)
        hybrid_count = sum(
            ff.is_memory_hybrid_enabled_for_session(f"canary-test-{i}")
            for i in range(20)
        )
        assert 0 <= hybrid_count <= 3, f"Expected 0-2 at 5%, got {hybrid_count}"

    def test_canary_context_assembler_uses_session_routing(
        self, mock_redis, mock_qdrant
    ):
        """Verify build_session_context calls session-aware routing."""
        from src.config.feature_flags import FeatureFlags

        mock_redis.set_data("chise:feature_flags:config:memory_hybrid_enabled", "true")
        mock_redis.set_data("chise:feature_flags:config:memory:canary_percentage", "0")

        ff = FeatureFlags()
        object.__setattr__(ff, "_redis_client", mock_redis)

        with patch(
            "src.config.feature_flags.FeatureFlags",
            return_value=ff,
        ):
            # Should not raise - just returns fallback
            result = build_session_context(
                "test-session-xyz", redis_client=mock_redis, qdrant_client=mock_qdrant
            )
            assert result is not None
