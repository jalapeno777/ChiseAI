"""
Unit tests for Tiered Recall Engine.

Tests RecallEngine L0-L2 functionality with mocked Redis and Qdrant clients.
"""

import json
import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from src.governance.memory.tiered_recall import (
    FEATURE_FLAG_KEY,
    L0_MAX_AGE_HOURS,
    L1_MAX_AGE_HOURS,
    L2_MAX_AGE_HOURS,
    FreshnessSummary,
    RecallEngine,
    TierContext,
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

    def test_l1_staleness_decay_168h(self):
        """Test L1 staleness score reflects 168h (7 day) decay."""
        now = datetime.now(UTC)
        # 84 hours ago = halfway through L1 window
        updated_timestamp = (now - timedelta(hours=84)).isoformat()

        self.mock_qdrant.scroll.return_value = (
            [
                {
                    "id": "mem-1",
                    "payload": {
                        "content": "Test memory",
                        "created_at": updated_timestamp,
                        "updated_at": updated_timestamp,
                        "staleness_score": max(0.0, 1.0 - 84 / L1_MAX_AGE_HOURS),
                    },
                }
            ],
            None,
        )

        result = self.engine._get_l1_recent()

        # staleness_score should be precomputed (0.5 at 84h into 168h window)
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

    def test_l2_staleness_decay_720h(self):
        """Test L2 staleness score reflects 720h (30 day) decay."""
        now = datetime.now(UTC)
        # 360 hours ago = halfway through L2 window
        updated_timestamp = (now - timedelta(hours=360)).isoformat()

        self.mock_qdrant.scroll.return_value = (
            [
                {
                    "id": "mem-1",
                    "payload": {
                        "content": "Test memory",
                        "created_at": updated_timestamp,
                        "updated_at": updated_timestamp,
                        "staleness_score": max(0.0, 1.0 - 360 / L2_MAX_AGE_HOURS),
                    },
                }
            ],
            None,
        )

        result = self.engine._get_l2_historical()

        # staleness_score should be precomputed (0.5 at 360h into 720h window)
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
    """Tests for feature flag constants."""

    def test_feature_flag_key_format(self):
        """Test feature flag key follows expected format."""
        self.assertTrue(FEATURE_FLAG_KEY.startswith("chise:feature_flags:"))
        self.assertIn("tiered_recall", FEATURE_FLAG_KEY)

    def test_tier_constants(self):
        """Test tier age constants are correct."""
        self.assertEqual(L0_MAX_AGE_HOURS, 24)
        self.assertEqual(L1_MAX_AGE_HOURS, 168)  # 7 days
        self.assertEqual(L2_MAX_AGE_HOURS, 720)  # 30 days


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


if __name__ == "__main__":
    unittest.main()
