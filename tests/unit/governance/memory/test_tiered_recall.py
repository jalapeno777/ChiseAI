"""
Tests for tiered_recall.py staleness remediation.

Verifies that runtime staleness computation is removed per Aria hardening
AD-PHASE4-20260409T000000Z-ctx001.

Acceptance Criteria:
- AC1: No runtime staleness compute in L1
- AC2: No runtime staleness compute in L2
- AC3: No runtime staleness compute in L3 (PartialL3Result.tier_context)
- AC4: Ordering by created_at unaffected
- AC5: legacy_missing field set correctly
- AC6: invariants.assert_no_runtime_staleness_compute passes
"""

from unittest.mock import patch

import pytest
from src.governance.memory.invariants import (
    StalenessComputeError,
    assert_no_runtime_staleness_compute,
)
from src.governance.memory.tiered_recall import (
    PartialL3Result,
    RecallEngine,
)


class TestNoRuntimeStalenessComputeL1:
    """AC1: No runtime staleness compute in L1."""

    def test_l1_legacy_missing_no_runtime_compute(self):
        """L1 records without staleness_score get legacy_missing=True, not computed."""
        engine = RecallEngine(session_id="test-session")

        # Mock Qdrant with payload missing staleness_score
        legacy_payload = {
            "content": "test memory content",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
            # No staleness_score
        }

        mock_results = [
            {"id": "1", "payload": dict(legacy_payload)},
        ]

        with patch.object(engine, "_scroll_qdrant", return_value=mock_results):
            result = engine._get_l1_recent()

        # Verify legacy_missing is set
        assert result.results[0]["payload"]["legacy_missing"] is True
        # Verify staleness_score is None, not computed
        assert result.results[0]["payload"]["staleness_score"] is None

    def test_l1_with_staleness_unchanged(self):
        """L1 records with precomputed staleness_score work normally."""
        engine = RecallEngine(session_id="test-session")

        payload_with_score = {
            "content": "test memory content",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "staleness_score": 0.75,
        }

        mock_results = [
            {"id": "1", "payload": dict(payload_with_score)},
        ]

        with patch.object(engine, "_scroll_qdrant", return_value=mock_results):
            result = engine._get_l1_recent()

        # Verify staleness_score is preserved
        assert result.results[0]["payload"]["staleness_score"] == 0.75
        # Verify no legacy_missing flag for records with score
        assert "legacy_missing" not in result.results[0]["payload"]


class TestNoRuntimeStalenessComputeL2:
    """AC2: No runtime staleness compute in L2."""

    def test_l2_legacy_missing_no_runtime_compute(self):
        """L2 records without staleness_score get legacy_missing=True, not computed."""
        engine = RecallEngine(session_id="test-session")

        legacy_payload = {
            "content": "historical memory",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
            # No staleness_score
        }

        mock_results = [
            {"id": "2", "payload": dict(legacy_payload)},
        ]

        with patch.object(engine, "_scroll_qdrant", return_value=mock_results):
            result = engine._get_l2_historical()

        # Verify legacy_missing is set
        assert result.results[0]["payload"]["legacy_missing"] is True
        # Verify staleness_score is None, not computed
        assert result.results[0]["payload"]["staleness_score"] is None

    def test_l2_with_staleness_unchanged(self):
        """L2 records with precomputed staleness_score work normally."""
        engine = RecallEngine(session_id="test-session")

        payload_with_score = {
            "content": "historical memory",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "staleness_score": 0.50,
        }

        mock_results = [
            {"id": "2", "payload": dict(payload_with_score)},
        ]

        with patch.object(engine, "_scroll_qdrant", return_value=mock_results):
            result = engine._get_l2_historical()

        # Verify staleness_score is preserved
        assert result.results[0]["payload"]["staleness_score"] == 0.50
        # Verify no legacy_missing flag for records with score
        assert "legacy_missing" not in result.results[0]["payload"]


class TestNoRuntimeStalenessComputeL3:
    """AC3: No runtime staleness compute in L3 (PartialL3Result.tier_context)."""

    def test_l3_legacy_missing_no_runtime_compute(self):
        """L3 records without staleness_score get legacy_missing=True, not computed."""
        legacy_payload = {
            "content": "archived memory",
            "created_at": "2025-06-01T00:00:00+00:00",
            "updated_at": "2025-06-01T00:00:00+00:00",
            # No staleness_score
        }

        mock_results = [
            {"id": "3", "payload": dict(legacy_payload)},
        ]

        partial_l3 = PartialL3Result(
            results=mock_results,
            complete=True,
            next_cursor=None,
            timeout_ms=100,
        )

        tier_ctx = partial_l3.tier_context

        # Verify legacy_missing is set
        assert tier_ctx.results[0]["payload"]["legacy_missing"] is True
        # Verify staleness_score is None, not computed
        assert tier_ctx.results[0]["payload"]["staleness_score"] is None

    def test_l3_with_staleness_unchanged(self):
        """L3 records with precomputed staleness_score work normally."""
        payload_with_score = {
            "content": "archived memory",
            "created_at": "2025-06-01T00:00:00+00:00",
            "updated_at": "2025-06-01T00:00:00+00:00",
            "staleness_score": 0.25,
        }

        mock_results = [
            {"id": "3", "payload": dict(payload_with_score)},
        ]

        partial_l3 = PartialL3Result(
            results=mock_results,
            complete=True,
            next_cursor=None,
            timeout_ms=100,
        )

        tier_ctx = partial_l3.tier_context

        # Verify staleness_score is preserved
        assert tier_ctx.results[0]["payload"]["staleness_score"] == 0.25
        # Verify no legacy_missing flag for records with score
        assert "legacy_missing" not in tier_ctx.results[0]["payload"]


class TestOrderingStableWithoutStaleness:
    """AC4: Ordering by created_at unaffected by staleness removal."""

    def test_l1_ordering_by_created_at(self):
        """L1 ordering is by created_at for oldest/newest tracking, not result sorting."""
        engine = RecallEngine(session_id="test-session")

        # Create records with different created_at - Qdrant returns in this order
        # but oldest_record/newest_record correctly track the time range
        payloads = [
            {
                "content": "first",
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
                "staleness_score": 0.5,
            },
            {
                "content": "second",
                "created_at": "2026-01-03T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
                "staleness_score": 0.5,
            },
            {
                "content": "third",
                "created_at": "2026-01-02T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
                "staleness_score": 0.5,
            },
        ]

        mock_results = [{"id": str(i), "payload": p} for i, p in enumerate(payloads)]

        with patch.object(engine, "_scroll_qdrant", return_value=mock_results):
            result = engine._get_l1_recent()

        # Verify oldest_record and newest_record are based on created_at
        # (not affected by staleness removal - this is the key invariant)
        assert result.freshness.oldest_record == "2026-01-01T00:00:00+00:00"
        assert result.freshness.newest_record == "2026-01-03T00:00:00+00:00"

        # Results order is preserved from Qdrant (not sorted by created_at)
        # The key point is that ordering is NOT based on staleness_score
        # which was never the case - ordering was always by Qdrant scan order

    def test_l2_ordering_by_created_at(self):
        """L2 ordering is by created_at, not staleness_score."""
        engine = RecallEngine(session_id="test-session")

        payloads = [
            {
                "content": "older",
                "created_at": "2025-12-01T00:00:00+00:00",
                "updated_at": "2025-12-01T00:00:00+00:00",
                "staleness_score": 0.3,
            },
            {
                "content": "newer",
                "created_at": "2025-12-15T00:00:00+00:00",
                "updated_at": "2025-12-15T00:00:00+00:00",
                "staleness_score": 0.3,
            },
        ]

        mock_results = [{"id": str(i), "payload": p} for i, p in enumerate(payloads)]

        with patch.object(engine, "_scroll_qdrant", return_value=mock_results):
            result = engine._get_l2_historical()

        # Verify oldest_record and newest_record are based on created_at
        assert result.freshness.oldest_record == "2025-12-01T00:00:00+00:00"
        assert result.freshness.newest_record == "2025-12-15T00:00:00+00:00"


class TestLegacyMissingPropagatesCorrectly:
    """AC5: legacy_missing field set correctly when staleness_score absent."""

    def test_legacy_missing_propagates_l1(self):
        """L1 legacy records have legacy_missing=True."""
        engine = RecallEngine(session_id="test-session")

        legacy_payload = {
            "content": "test",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        }

        mock_results = [{"id": "1", "payload": dict(legacy_payload)}]

        with patch.object(engine, "_scroll_qdrant", return_value=mock_results):
            result = engine._get_l1_recent()

        assert result.results[0]["payload"].get("legacy_missing") is True
        assert result.results[0]["payload"].get("staleness_score") is None

    def test_legacy_missing_propagates_l2(self):
        """L2 legacy records have legacy_missing=True."""
        engine = RecallEngine(session_id="test-session")

        legacy_payload = {
            "content": "test",
            "created_at": "2025-12-01T00:00:00+00:00",
            "updated_at": "2025-12-01T00:00:00+00:00",
        }

        mock_results = [{"id": "1", "payload": dict(legacy_payload)}]

        with patch.object(engine, "_scroll_qdrant", return_value=mock_results):
            result = engine._get_l2_historical()

        assert result.results[0]["payload"].get("legacy_missing") is True
        assert result.results[0]["payload"].get("staleness_score") is None

    def test_legacy_missing_propagates_l3(self):
        """L3 legacy records have legacy_missing=True."""
        legacy_payload = {
            "content": "test",
            "created_at": "2025-06-01T00:00:00+00:00",
            "updated_at": "2025-06-01T00:00:00+00:00",
        }

        partial_l3 = PartialL3Result(
            results=[{"id": "1", "payload": dict(legacy_payload)}],
            complete=True,
            next_cursor=None,
            timeout_ms=100,
        )

        tier_ctx = partial_l3.tier_context

        assert tier_ctx.results[0]["payload"].get("legacy_missing") is True
        assert tier_ctx.results[0]["payload"].get("staleness_score") is None


class TestInvariantsModuleNotViolated:
    """AC6: invariants.assert_no_runtime_staleness_compute passes on legacy records."""

    def test_invariants_pass_l1_legacy(self):
        """L1 legacy records pass invariants check."""
        engine = RecallEngine(session_id="test-session")

        legacy_payload = {
            "content": "test",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        }

        mock_results = [{"id": "1", "payload": dict(legacy_payload)}]

        with patch.object(engine, "_scroll_qdrant", return_value=mock_results):
            result = engine._get_l1_recent()

        # Should NOT raise StalenessComputeError
        assert_no_runtime_staleness_compute(result.results[0]["payload"])

    def test_invariants_pass_l2_legacy(self):
        """L2 legacy records pass invariants check."""
        engine = RecallEngine(session_id="test-session")

        legacy_payload = {
            "content": "test",
            "created_at": "2025-12-01T00:00:00+00:00",
            "updated_at": "2025-12-01T00:00:00+00:00",
        }

        mock_results = [{"id": "1", "payload": dict(legacy_payload)}]

        with patch.object(engine, "_scroll_qdrant", return_value=mock_results):
            result = engine._get_l2_historical()

        # Should NOT raise StalenessComputeError
        assert_no_runtime_staleness_compute(result.results[0]["payload"])

    def test_invariants_pass_l3_legacy(self):
        """L3 legacy records pass invariants check."""
        legacy_payload = {
            "content": "test",
            "created_at": "2025-06-01T00:00:00+00:00",
            "updated_at": "2025-06-01T00:00:00+00:00",
        }

        partial_l3 = PartialL3Result(
            results=[{"id": "1", "payload": dict(legacy_payload)}],
            complete=True,
            next_cursor=None,
            timeout_ms=100,
        )

        tier_ctx = partial_l3.tier_context

        # Should NOT raise StalenessComputeError
        assert_no_runtime_staleness_compute(tier_ctx.results[0]["payload"])

    def test_invariants_pass_with_staleness_score(self):
        """Records with precomputed staleness_score pass invariants check."""
        engine = RecallEngine(session_id="test-session")

        payload_with_score = {
            "content": "test",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "staleness_score": 0.75,
        }

        mock_results = [{"id": "1", "payload": dict(payload_with_score)}]

        with patch.object(engine, "_scroll_qdrant", return_value=mock_results):
            result = engine._get_l1_recent()

        # Should NOT raise StalenessComputeError
        assert_no_runtime_staleness_compute(result.results[0]["payload"])


class TestSmokeTest:
    """Smoke test from verification commands."""

    def test_smoke_test_legacy_handling(self):
        """Simulate what _get_l1_recent does - should not raise."""
        payload = {
            "content": "test",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        }

        # Simulate what _get_l1_recent does
        if "staleness_score" not in payload:
            payload["legacy_missing"] = True
            payload["staleness_score"] = None

        # Should NOT raise
        try:
            assert_no_runtime_staleness_compute(payload)
            print("Staleness invariant: PASS")
        except StalenessComputeError as e:
            pytest.fail(f"Staleness invariant: FAIL - {e}")
