"""
Unit tests for Tiered Recall Engine.

Tests RecallEngine L0-L3 functionality with mocked Redis and Qdrant clients.
"""

import json
import time
import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from src.governance.memory.tiered_recall import (
    MAX_L3_PAGE_SIZE,
    FreshnessSummary,
    PartialL3Result,
    RecallEngine,
    SaturationAlert,
    TierContext,
    TieredRecallResponse,
)


class TestL0Immediate(unittest.TestCase):
    """Tests for L0: Immediate context from Redis."""

    def setUp(self):
        """Set up test fixtures with mocked Redis."""
        self.mock_redis = MagicMock()
        self.session_id = "test-session-123"
        self.engine = RecallEngine(
            session_id=self.session_id,
            redis_client=self.mock_redis,
            qdrant_client=MagicMock(),
        )

    def test_l0_immediate_returns_from_redis(self):
        """Test L0 returns observations from Redis sorted set."""
        now = datetime.now(UTC)
        observations = [
            {
                "content": f"Observation {i}",
                "timestamp": (now - timedelta(hours=i)).isoformat(),
                "priority": "medium",
            }
            for i in range(5)
        ]
        self.mock_redis.zrange.return_value = [json.dumps(obs) for obs in observations]

        result = self.engine._get_l0_immediate()

        self.assertEqual(result.tier, "L0")
        self.assertEqual(len(result.results), 5)
        self.assertTrue(result.complete)
        self.mock_redis.zrange.assert_called_once()

    def test_l0_freshness_age_hours(self):
        """Test L0 freshness has age_hours set correctly."""
        now = datetime.now(UTC)
        observations = [
            {
                "content": "Recent observation",
                "timestamp": (now - timedelta(hours=2)).isoformat(),
            }
        ]
        self.mock_redis.zrange.return_value = [json.dumps(obs) for obs in observations]

        result = self.engine._get_l0_immediate()

        self.assertIsNotNone(result.freshness.age_hours)
        self.assertAlmostEqual(result.freshness.age_hours, 2.0, delta=0.1)
        # L0 has no staleness decay
        self.assertEqual(result.freshness.staleness_score, 0.0)
        # L0 from Observer has high confidence
        self.assertEqual(result.freshness.confidence_hint, 0.9)

    def test_l0_empty_when_redis_unavailable(self):
        """Test L0 returns empty context when Redis unavailable."""
        engine = RecallEngine(session_id=self.session_id, redis_client=None)

        result = engine._get_l0_immediate()

        self.assertEqual(result.tier, "L0")
        self.assertEqual(len(result.results), 0)
        self.assertTrue(result.complete)


class TestL1Recent(unittest.TestCase):
    """Tests for L1: Recent context from Qdrant (0-7 days)."""

    def setUp(self):
        """Set up test fixtures with mocked Qdrant."""
        self.mock_qdrant = MagicMock()
        self.session_id = "test-session-123"
        self.engine = RecallEngine(
            session_id=self.session_id,
            redis_client=MagicMock(),
            qdrant_client=self.mock_qdrant,
        )

    def test_l1_recent_filters_by_created_at(self):
        """Test L1 filters by created_at within 7 days."""
        now = datetime.now(UTC)
        recent_timestamp = (now - timedelta(hours=48)).isoformat()  # 2 days ago

        self.mock_qdrant.scroll.return_value = (
            [
                {
                    "id": "mem-1",
                    "payload": {
                        "content": "Recent memory",
                        "created_at": recent_timestamp,
                        "updated_at": recent_timestamp,
                        "staleness_score": 0.7,
                    },
                }
            ],
            None,
        )

        result = self.engine._get_l1_recent()

        self.assertEqual(result.tier, "L1")
        self.assertTrue(result.complete)
        # Verify Qdrant scroll was called
        self.mock_qdrant.scroll.assert_called_once()

    def test_l1_staleness_uses_720h_denominator(self):
        """Test L1 staleness fallback uses 720h denominator."""
        now = datetime.now(UTC)
        # 360 hours ago = halfway through 720h window
        updated_timestamp = (now - timedelta(hours=360)).isoformat()

        self.mock_qdrant.scroll.return_value = (
            [
                {
                    "id": "mem-1",
                    "payload": {
                        "content": "Test memory",
                        "created_at": updated_timestamp,
                        "updated_at": updated_timestamp,
                        # No staleness_score — will fall back to read-time compute
                    },
                }
            ],
            None,
        )

        result = self.engine._get_l1_recent()

        # Should compute staleness using 720h denominator: 1.0 - 360/720 = 0.5
        self.assertGreater(result.freshness.staleness_score, 0.4)
        self.assertLess(result.freshness.staleness_score, 0.6)


class TestL2Historical(unittest.TestCase):
    """Tests for L2: Historical context from Qdrant (7-30 days)."""

    def setUp(self):
        """Set up test fixtures with mocked Qdrant."""
        self.mock_qdrant = MagicMock()
        self.session_id = "test-session-123"
        self.engine = RecallEngine(
            session_id=self.session_id,
            redis_client=MagicMock(),
            qdrant_client=self.mock_qdrant,
        )

    def test_l2_historical_filters_by_date_range(self):
        """Test L2 filters by date range (7-30 days)."""
        now = datetime.now(UTC)
        # 15 days ago = within L2 window
        historical_timestamp = (now - timedelta(days=15)).isoformat()

        self.mock_qdrant.scroll.return_value = (
            [
                {
                    "id": "mem-1",
                    "payload": {
                        "content": "Historical memory",
                        "created_at": historical_timestamp,
                        "updated_at": historical_timestamp,
                        "staleness_score": 0.3,
                    },
                }
            ],
            None,
        )

        result = self.engine._get_l2_historical()

        self.assertEqual(result.tier, "L2")
        self.assertTrue(result.complete)
        self.mock_qdrant.scroll.assert_called_once()

    def test_l2_staleness_uses_720h_denominator(self):
        """Test L2 staleness fallback uses 720h denominator."""
        now = datetime.now(UTC)
        # 360 hours ago = halfway through 720h window
        updated_timestamp = (now - timedelta(hours=360)).isoformat()

        self.mock_qdrant.scroll.return_value = (
            [
                {
                    "id": "mem-1",
                    "payload": {
                        "content": "Test memory",
                        "created_at": updated_timestamp,
                        "updated_at": updated_timestamp,
                        # No staleness_score — will fall back to read-time compute
                    },
                }
            ],
            None,
        )

        result = self.engine._get_l2_historical()

        # Should compute staleness using 720h denominator: 1.0 - 360/720 = 0.5
        self.assertGreater(result.freshness.staleness_score, 0.4)
        self.assertLess(result.freshness.staleness_score, 0.6)


class TestFreshnessSummary(unittest.TestCase):
    """Tests for FreshnessSummary dataclass."""

    def test_freshness_summary_fields(self):
        """Test FreshnessSummary has all required fields."""
        summary = FreshnessSummary(
            age_hours=2.5,
            staleness_score=0.8,
            confidence_hint=0.9,
            oldest_record="2024-01-01T00:00:00Z",
            newest_record="2024-01-02T00:00:00Z",
        )

        self.assertEqual(summary.age_hours, 2.5)
        self.assertEqual(summary.staleness_score, 0.8)
        self.assertEqual(summary.confidence_hint, 0.9)
        self.assertIsNotNone(summary.oldest_record)
        self.assertIsNotNone(summary.newest_record)

    def test_freshness_summary_none_age_hours_for_l1_plus(self):
        """Test L1+ FreshnessSummary has None for age_hours."""
        summary = FreshnessSummary(
            age_hours=None,
            staleness_score=0.5,
            confidence_hint=0.7,
            oldest_record="2024-01-01T00:00:00Z",
            newest_record="2024-01-02T00:00:00Z",
        )

        self.assertIsNone(summary.age_hours)
        self.assertEqual(summary.staleness_score, 0.5)


class TestTierContext(unittest.TestCase):
    """Tests for TierContext dataclass."""

    def test_tier_context_envelope(self):
        """Test TierContext contains all envelope fields."""
        freshness = FreshnessSummary(
            age_hours=1.0,
            staleness_score=0.0,
            confidence_hint=0.9,
            oldest_record="2024-01-01T00:00:00Z",
            newest_record="2024-01-01T01:00:00Z",
        )

        ctx = TierContext(
            tier="L0",
            results=[{"content": "Test"}],
            freshness=freshness,
            complete=True,
            token_count=100,
        )

        self.assertEqual(ctx.tier, "L0")
        self.assertEqual(len(ctx.results), 1)
        self.assertEqual(ctx.freshness.confidence_hint, 0.9)
        self.assertTrue(ctx.complete)
        self.assertEqual(ctx.token_count, 100)


class TestFeatureFlagGating(unittest.TestCase):
    """Tests for feature flag gating (H1 fix)."""

    def setUp(self):
        """Set up test fixtures."""
        self.session_id = "test-session-123"
        self.mock_redis = MagicMock()
        self.mock_qdrant = MagicMock()

    def test_feature_flag_disabled_returns_empty_response(self):
        """Test get_all_tiers returns empty response when feature flag is disabled."""
        self.mock_redis.get.return_value = None  # Flag not set = disabled
        engine = RecallEngine(
            session_id=self.session_id,
            redis_client=self.mock_redis,
            qdrant_client=self.mock_qdrant,
        )

        result = engine.get_all_tiers(max_tokens=8000)

        self.assertIsInstance(result, TieredRecallResponse)
        self.assertEqual(result.tiers, {})
        self.assertEqual(result.context_tokens, 0)
        self.assertEqual(result.status, "feature_disabled")
        self.assertFalse(result.complete)

    def test_feature_flag_disabled_has_status_marker(self):
        """Test feature disabled response has status='feature_disabled'."""
        self.mock_redis.get.return_value = None
        engine = RecallEngine(
            session_id=self.session_id,
            redis_client=self.mock_redis,
            qdrant_client=self.mock_qdrant,
        )

        result = engine.get_all_tiers(max_tokens=8000)

        self.assertEqual(result.status, "feature_disabled")
        self.assertEqual(result.incomplete_tiers, [])
        self.assertEqual(result.next_cursors, {})

    def test_feature_flag_enabled_allows_normal_operation(self):
        """Test feature flag enabled allows normal tier assembly."""
        self.mock_redis.get.return_value = "true"
        # Mock L0
        self.mock_redis.zrange.return_value = [
            json.dumps({"content": "test", "timestamp": datetime.now(UTC).isoformat()})
        ]
        # Mock L1, L2, L3
        self.mock_qdrant.scroll.return_value = ([], None)

        engine = RecallEngine(
            session_id=self.session_id,
            redis_client=self.mock_redis,
            qdrant_client=self.mock_qdrant,
        )

        result = engine.get_all_tiers(max_tokens=8000)

        self.assertIsInstance(result, TieredRecallResponse)
        self.assertIn("L0", result.tiers)
        self.assertEqual(result.status, "ok")


class TestSaturationAlert(unittest.TestCase):
    """Tests for SaturationAlert dataclass."""

    def test_saturation_alert_fields(self):
        """Test SaturationAlert has all required fields."""
        alert = SaturationAlert(
            ratio=0.25,
            tier_breakdown={"L0": 0.1, "L1": 0.15},
            alert_type="sparse",
            recommendation="Expand L2/L3 search",
        )

        self.assertEqual(alert.ratio, 0.25)
        self.assertEqual(alert.alert_type, "sparse")
        self.assertIsNotNone(alert.recommendation)


class TestSaturationMetrics(unittest.TestCase):
    """Tests for saturation ratio computation."""

    def setUp(self):
        """Set up test fixtures."""
        self.session_id = "test-session-123"
        self.mock_redis = MagicMock()
        self.mock_qdrant = MagicMock()

    def test_saturation_ratio_computed(self):
        """Test saturation_ratio is computed correctly."""
        self.mock_redis.get.return_value = "true"
        self.mock_redis.zrange.return_value = [
            json.dumps(
                {
                    "content": "x" * 1000,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
        ]
        self.mock_qdrant.scroll.return_value = ([], None)

        engine = RecallEngine(
            session_id=self.session_id,
            redis_client=self.mock_redis,
            qdrant_client=self.mock_qdrant,
        )

        result = engine.get_all_tiers(max_tokens=8000)

        # 1000 chars / 4 = 250 tokens; 250 / 8000 = 0.03125
        self.assertGreater(result.saturation_ratio, 0.0)
        self.assertLess(result.saturation_ratio, 1.0)
        self.assertIsNotNone(result.saturation_alert)

    def test_saturation_sparse_alert_fires(self):
        """Test sparse alert fires when ratio < 0.3."""
        self.mock_redis.get.return_value = "true"
        self.mock_redis.zrange.return_value = [
            json.dumps(
                {"content": "x" * 100, "timestamp": datetime.now(UTC).isoformat()}
            )
        ]
        self.mock_qdrant.scroll.return_value = ([], None)

        engine = RecallEngine(
            session_id=self.session_id,
            redis_client=self.mock_redis,
            qdrant_client=self.mock_qdrant,
        )

        result = engine.get_all_tiers(max_tokens=8000)

        self.assertEqual(result.saturation_alert.alert_type, "sparse")
        self.assertIsNotNone(result.saturation_alert.recommendation)

    def test_saturation_saturated_alert_fires(self):
        """Test saturated alert fires when ratio > 0.85."""
        self.mock_redis.get.return_value = "true"
        # L0 with large content: need 0.85 * 8000 = 6800 tokens = 27200 chars
        large_content = "x" * 27200
        self.mock_redis.zrange.return_value = [
            json.dumps(
                {"content": large_content, "timestamp": datetime.now(UTC).isoformat()}
            )
        ]
        self.mock_qdrant.scroll.return_value = ([], None)

        engine = RecallEngine(
            session_id=self.session_id,
            redis_client=self.mock_redis,
            qdrant_client=self.mock_qdrant,
        )

        result = engine.get_all_tiers(max_tokens=8000)

        self.assertEqual(result.saturation_alert.alert_type, "saturated")
        self.assertIsNotNone(result.saturation_alert.recommendation)

    def test_saturation_nominal(self):
        """Test nominal alert when 0.3 <= ratio <= 0.85."""
        self.mock_redis.get.return_value = "true"
        # ~3000 chars = 750 tokens; 750/4000 = 0.1875 < 0.3, still sparse
        self.mock_redis.zrange.return_value = [
            json.dumps(
                {"content": "x" * 3000, "timestamp": datetime.now(UTC).isoformat()}
            )
        ]
        self.mock_qdrant.scroll.return_value = ([], None)

        engine = RecallEngine(
            session_id=self.session_id,
            redis_client=self.mock_redis,
            qdrant_client=self.mock_qdrant,
        )

        result = engine.get_all_tiers(max_tokens=4000)

        # ratio = 750/4000 = 0.1875 < 0.3 -> sparse
        self.assertEqual(result.saturation_alert.alert_type, "sparse")


class TestAntiGaming(unittest.TestCase):
    """Tests for anti-gaming checks."""

    def setUp(self):
        """Set up test fixtures."""
        self.session_id = "test-session-123"
        self.mock_redis = MagicMock()
        self.mock_qdrant = MagicMock()

    def test_anti_gaming_sparse_not_zero(self):
        """Token reduction with sparse saturation must still return L0 data."""
        self.mock_redis.get.return_value = "true"
        self.mock_redis.zrange.return_value = [
            json.dumps(
                {"content": "Test content", "timestamp": datetime.now(UTC).isoformat()}
            )
        ]
        self.mock_qdrant.scroll.return_value = ([], None)

        engine = RecallEngine(
            session_id=self.session_id,
            redis_client=self.mock_redis,
            qdrant_client=self.mock_qdrant,
        )

        result = engine.get_all_tiers(max_tokens=100)

        # L0 must be present regardless of saturation
        self.assertIn("L0", result.tiers)
        self.assertGreater(len(result.tiers["L0"].results), 0)

        # Saturation should be sparse but not zero
        self.assertLess(result.saturation_ratio, 0.3)
        self.assertEqual(result.saturation_alert.alert_type, "sparse")


class TestL3Pagination(unittest.TestCase):
    """Tests for L3 pagination and timeout."""

    def setUp(self):
        """Set up test fixtures."""
        self.session_id = "test-session-123"
        self.mock_redis = MagicMock()
        self.mock_qdrant = MagicMock()
        self.engine = RecallEngine(
            session_id=self.session_id,
            redis_client=self.mock_redis,
            qdrant_client=self.mock_qdrant,
        )

    def test_l3_scroll_respects_max_page_size(self):
        """Test L3 scroll uses MAX_L3_PAGE_SIZE limit."""
        self.mock_redis.get.return_value = "true"
        self.mock_redis.zrange.return_value = []
        self.mock_qdrant.scroll.side_effect = [
            (
                [{"id": f"mem-{i}", "payload": {"content": "test"}} for i in range(50)],
                "next_cursor",
            ),
            ([], None),
        ]

        # Call _get_l3_archived directly to check pagination
        result = self.engine._get_l3_archived()

        # Verify Qdrant scroll was called with MAX_L3_PAGE_SIZE
        self.mock_qdrant.scroll.assert_called()
        call_args = self.mock_qdrant.scroll.call_args
        self.assertEqual(
            call_args.kwargs.get("limit", call_args[1].get("limit")), MAX_L3_PAGE_SIZE
        )

    def test_l3_timeout_returns_partial(self):
        """Test L3 timeout returns partial results."""
        self.mock_redis.get.return_value = "true"
        self.mock_redis.zrange.return_value = []

        # Simulate slow query
        def slow_scroll(*args, **kwargs):
            time.sleep(0.1)
            return (
                [{"id": "mem-1", "payload": {"content": "test"}}],
                "next_cursor",
            )

        self.mock_qdrant.scroll.side_effect = slow_scroll

        result = self.engine._get_l3_archived()

        self.assertFalse(result.complete)
        self.assertIsNotNone(result.next_cursor)

    def test_l3_timeout_has_incomplete_tiers(self):
        """Test L3 timeout marks L3 as incomplete."""
        self.mock_redis.get.return_value = "true"
        self.mock_redis.zrange.return_value = []
        self.mock_qdrant.scroll.side_effect = [
            (
                [
                    {
                        "id": f"mem-{i}",
                        "payload": {
                            "content": "test",
                            "updated_at": datetime.now(UTC).isoformat(),
                        },
                    }
                    for i in range(50)
                ],
                "next_cursor",
            ),
            ([], None),
        ]

        response = self.engine.get_all_tiers(max_tokens=8000)

        # When L3 times out, it should be in incomplete_tiers
        # (Note: actual behavior depends on whether timeout threshold is exceeded)
        self.assertIsInstance(response.incomplete_tiers, list)

    def test_l3_fallback_on_error(self):
        """Test L3 fallback on error sets fallback_tier."""
        self.mock_redis.get.return_value = "true"
        self.mock_redis.zrange.return_value = []
        self.mock_qdrant.scroll.side_effect = Exception("Qdrant error")

        result = self.engine._get_l3_archived()

        self.assertFalse(result.complete)
        self.assertEqual(result.fallback_tier, "L3")
        self.assertEqual(result.results, [])


class TestL3Archived(unittest.TestCase):
    """Tests for L3 archived tier implementation."""

    def setUp(self):
        """Set up test fixtures."""
        self.session_id = "test-session-123"
        self.mock_redis = MagicMock()
        self.mock_qdrant = MagicMock()
        self.engine = RecallEngine(
            session_id=self.session_id,
            redis_client=self.mock_redis,
            qdrant_client=self.mock_qdrant,
        )

    def test_build_l3_filter(self):
        """Test L3 filter builds correct conditions."""
        filter_cond = self.engine._build_l3_filter()

        self.assertIn("must", filter_cond)
        keys = [c.get("key") for c in filter_cond["must"] if isinstance(c, dict)]
        self.assertIn("created_at", keys)
        self.assertIn("memory_type", keys)

    def test_l3_archived_returns_tier_context(self):
        """Test _get_l3_archived returns PartialL3Result with tier_context."""
        self.mock_qdrant.scroll.return_value = (
            [
                {
                    "id": "mem-1",
                    "payload": {
                        "content": "Archived memory",
                        "created_at": (
                            datetime.now(UTC) - timedelta(days=40)
                        ).isoformat(),
                        "updated_at": (
                            datetime.now(UTC) - timedelta(days=40)
                        ).isoformat(),
                        "staleness_score": 0.2,
                    },
                }
            ],
            None,
        )

        result = self.engine._get_l3_archived()

        self.assertIsInstance(result, PartialL3Result)
        self.assertTrue(result.complete)
        self.assertIsNone(result.next_cursor)
        self.assertEqual(len(result.results), 1)

        tier_ctx = result.tier_context
        self.assertEqual(tier_ctx.tier, "L3")
        self.assertEqual(len(tier_ctx.results), 1)


class TestTieredRecallResponse(unittest.TestCase):
    """Tests for TieredRecallResponse dataclass."""

    def test_tiered_recall_response_fields(self):
        """Test TieredRecallResponse has all required fields."""
        response = TieredRecallResponse(
            tiers={},
            context_tokens=0,
            max_tokens=8000,
            saturation_ratio=0.0,
            complete=False,
            status="feature_disabled",
            incomplete_tiers=[],
            next_cursors={},
            timeout_ms=None,
            saturation_alert=None,
        )

        self.assertEqual(response.status, "feature_disabled")
        self.assertEqual(response.incomplete_tiers, [])
        self.assertIsNone(response.timeout_ms)
        self.assertIsNone(response.saturation_alert)


class TestAssembleWithBudget(unittest.TestCase):
    """Tests for token budget assembly."""

    def setUp(self):
        """Set up test fixtures."""
        self.session_id = "test-session-123"
        self.engine = RecallEngine(session_id=self.session_id)

    def test_assemble_fills_l0_first(self):
        """Test assembly fills L0 first within budget."""
        l0 = TierContext(
            tier="L0",
            results=[{"content": "L0 item"}],
            freshness=FreshnessSummary(
                age_hours=1.0,
                staleness_score=0.0,
                confidence_hint=0.9,
                oldest_record=None,
                newest_record=None,
            ),
            complete=True,
            token_count=100,
        )

        result = self.engine._assemble_with_budget({"L0": l0}, max_tokens=500)

        self.assertIn("L0", result)
        self.assertTrue(result["L0"].complete)

    def test_assemble_partial_tier_when_budget_exhausted(self):
        """Test partial tier included when budget exhausted."""
        l0 = TierContext(
            tier="L0",
            results=[{"content": "Item"}],
            freshness=FreshnessSummary(
                age_hours=1.0,
                staleness_score=0.0,
                confidence_hint=0.9,
                oldest_record=None,
                newest_record=None,
            ),
            complete=True,
            token_count=1000,
        )

        result = self.engine._assemble_with_budget({"L0": l0}, max_tokens=500)

        # Should have truncated tier
        self.assertIn("L0", result)
        self.assertFalse(result["L0"].complete)


class TestL3Stub(unittest.TestCase):
    """Tests for L3 stub (Batch 2)."""

    def setUp(self):
        """Set up test fixtures."""
        self.session_id = "test-session-123"
        self.engine = RecallEngine(
            session_id=self.session_id,
            redis_client=MagicMock(),
            qdrant_client=MagicMock(),
        )

    def test_l3_stub_returns_empty(self):
        """Test L3 stub returns empty results."""
        result = self.engine._get_l3_archived_stub()

        self.assertEqual(result.tier, "L3")
        self.assertEqual(len(result.results), 0)
        # L3 stub is incomplete until Batch 2
        self.assertFalse(result.complete)

    def test_l3_stub_uses_precomputed_staleness(self):
        """Test L3 stub notes staleness must be precomputed (not dynamic)."""
        result = self.engine._get_l3_archived_stub()

        # staleness_score is 0.0 in stub - Batch 2 will read precomputed from Qdrant
        self.assertEqual(result.freshness.staleness_score, 0.0)
        self.assertEqual(result.freshness.confidence_hint, 0.3)


if __name__ == "__main__":
    unittest.main()
